"""Relevés pré-départ du simple gagnant PMU et classement de marché."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import fcntl
from math import isfinite
from pathlib import Path
from tempfile import gettempdir

from .ml_v19 import load, numeric, save

KEYS = ('dernierRapportDirect', 'rapportDirect', 'coteDirect', 'cote', 'rapportProbable')


def instant(value):
    try:
        stamp = datetime.fromisoformat(value)
        return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
    except (TypeError, ValueError):
        return None


def cote_valide(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip().replace(',', '.')
    cote = numeric(value)
    return cote if cote is not None and isfinite(cote) and cote > 0 else None


def _rapport(participant, observed=None, depart=None, *, diagnostic=None):
    for key in KEYS:
        value = participant.get(key)
        if value is None:
            continue
        if diagnostic is not None:
            diagnostic[f'champ_present:{key}'] += 1
        reported = None
        if isinstance(value, dict):
            if (value.get('indisponible') is True or
                    value.get('typePari') not in (None, 'SIMPLE_GAGNANT') or
                    value.get('typeRapport') not in (None, 'DIRECT')):
                if diagnostic is not None:
                    diagnostic['rapport_indisponible_ou_hors_simple_gagnant_direct'] += 1
                continue
            number = value.get('numPmu1')
            if number is not None and str(number) != str(participant.get('numPmu', number)):
                if diagnostic is not None:
                    diagnostic['numero_rapport_incoherent'] += 1
                continue
            timestamp = value.get('dateRapport')
            if timestamp is not None:
                try:
                    reported = datetime.fromtimestamp(int(timestamp) / 1000, timezone.utc)
                except (TypeError, ValueError, OverflowError, OSError):
                    if diagnostic is not None:
                        diagnostic['horodatage_invalide'] += 1
                    continue
                if (observed is not None and reported > observed) or (depart is not None and reported >= depart):
                    if diagnostic is not None:
                        diagnostic['rapport_hors_fenetre'] += 1
                    continue
            value = value.get('rapport', value.get('valeur'))
        cote = cote_valide(value)
        if cote is not None:
            return cote, key, reported
        if diagnostic is not None:
            diagnostic['valeur_invalide'] += 1
    return None, None, None


def extraire_cote(participant):
    cote, champ, _ = _rapport(participant)
    return cote, champ


def dernier_releve(cache, course):
    """Relire aussi les archives V19 dont le dernier instantané était incomplet."""
    path = Path(cache) / 'cotes' / f"{course['date']}_{course['code']}.json"
    doc = load(path, {}) or {}
    if not doc or doc.get('schema') == 2:
        return doc
    depart = instant(course.get('depart'))
    if depart is None:
        return {}
    latest = {}
    for releve in [*doc.get('releves', []), doc]:
        for row in releve.get('chevaux', []):
            observed = instant(row.get('heure_utc'))
            cote = cote_valide(row.get('cote'))
            if observed is None or observed >= depart or cote is None:
                continue
            old = latest.get(row['numero'])
            if old is None or observed >= instant(old['heure_utc']):
                latest[row['numero']] = {**row, 'cote': cote}
    return {**doc, 'chevaux': list(latest.values())}


def _nouveaux_partants(participants, observed, depart, diagnostic):
    from .auto_v18 import _list, _num
    from .partants_actuels_v21 import statut_participation

    rows = {}
    for participant in _list(participants or {}, 'participants', 'partants'):
        if not isinstance(participant, dict):
            return {}
        number = _num(participant, 'numPmu', 'num', 'numero', 'numeroPmu')
        if not number or number < 0 or number in rows:
            return {}
        np = statut_participation(participant)
        cote, champ, reported = None, None, None
        if np != 'NON_PARTANT':
            cote, champ, reported = _rapport(participant, observed, depart, diagnostic=diagnostic)
            if not any(participant.get(key) is not None for key in KEYS):
                diagnostic['chevaux_sans_champ_rapport'] += 1
            diagnostic['chevaux_avec_cote_valide' if cote is not None else 'chevaux_sans_cote_valide'] += 1
        name = next((participant[key] for key in ('nomCheval', 'nom', 'nomParticipant')
                     if isinstance(participant.get(key), str) and participant[key].strip()), '')
        rows[number] = {
            'numero': number, 'nom': name, 'statut_np': np, 'cote': cote,
            'source': 'PMU_API_PARTICIPANTS' if cote is not None else '',
            'champ_pmu': champ or '', 'heure_utc': observed.isoformat() if cote is not None else '',
            'date_rapport_utc': reported.isoformat() if reported else '',
            'statut': 'RELEVE_HORODATE' if cote is not None else 'NON_DISPONIBLE',
        }
    return rows


def _chemin_verrou(cache, key):
    # Un fichier partagé par les processus qui utilisent ce cache, hors des données persistées.
    scope = sha256(str(Path(cache).resolve()).encode()).hexdigest()
    return Path(gettempdir()) / f'pmu-cotes-{scope}-{key}.lock'


def collecter(cache, course, participants, now=None):
    now = now or datetime.now(timezone.utc)
    depart = instant(course['depart'])
    if now.tzinfo is None or depart is None:
        raise ValueError('Fuseau obligatoire')
    now = now.astimezone(timezone.utc)
    if now >= depart:
        return 'APRES_DEPART_SANS_RELEVE'
    diagnostic = Counter()
    incoming = _nouveaux_partants(participants, now, depart, diagnostic)
    path = Path(cache) / 'cotes' / f"{course['date']}_{course['code']}.json"
    with _chemin_verrou(cache, f'{path.stem}_cotes').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = dernier_releve(cache, course)
        if not incoming:
            has_odds = any(row.get('cote') is not None for row in old.get('chevaux', []))
            return 'COTES_CONSERVEES' if has_odds else 'COTES_INDISPONIBLES'
        checked = instant(old.get('controle_utc'))
        if checked is not None and now <= checked:
            return old['statut']
        return _actualiser(path, course, old, incoming, now, diagnostic)


def _actualiser(path, course, old, incoming, now, diagnostic):
    rows = {row['numero']: row for row in old.get('chevaux', [])}
    changes = []
    for n, observed in incoming.items():
        previous = rows.get(n, {})
        row = {**previous, **observed}
        row['nom'] = observed['nom'] or previous.get('nom', '')
        if observed['statut_np'] == 'NP_NON_VERIFIE':
            row['statut_np'] = previous.get('statut_np', 'NP_NON_VERIFIE')
        if row['statut_np'] == 'NON_PARTANT':
            row.update(cote=None, heure_utc='', date_rapport_utc='', champ_pmu='', source='', statut='NON_PARTANT')
        elif previous.get('cote') is not None:
            old_report = instant(previous.get('date_rapport_utc'))
            new_report = instant(observed['date_rapport_utc'])
            if observed['cote'] is None or (old_report is not None and (new_report is None or new_report <= old_report)):
                for field in ('cote', 'heure_utc', 'date_rapport_utc', 'champ_pmu', 'source', 'statut'):
                    row[field] = previous.get(field, '')
        if (not previous or row.get('heure_utc') != previous.get('heure_utc') or
                row['statut_np'] != previous.get('statut_np')):
            changes.append(row)
        rows[n] = row

    eligible = [row for row in rows.values() if row.get('statut_np') != 'NON_PARTANT']
    count = sum(row.get('cote') is not None for row in eligible)
    expected = course.get('nombre_declares')
    complete = expected is not None and len(rows) == int(expected)
    missing = max(0, int(expected or 0) - len(rows)) + len(eligible) - count
    eligible_count = count + missing
    coverage = count / eligible_count if eligible_count else None
    if not count:
        status = 'COTES_NON_EXTRAITES'
    elif not changes and not any(row.get('cote') is not None for row in incoming.values()):
        status = 'COTES_CONSERVEES'
    else:
        status = 'COTES_RELEVEES' if complete and not missing else 'COTES_PARTIELLES'
    history = old.get('releves', [])
    if changes:
        history = [*history, {'heure_utc': now.isoformat(), 'chevaux': changes}]
    save(path, {
        'schema': 2, 'date': course['date'], 'course': course['code'], 'depart': course['depart'],
        'controle_utc': now.isoformat(), 'chevaux': list(rows.values()), 'releves': history,
        'diagnostic_derniere_lecture': dict(diagnostic),
        'liste_complete': complete, 'partants_eligibles': eligible_count, 'cotes_extraites': count,
        'cotes_manquantes': missing, 'couverture': coverage, 'statut': status,
        'derniere_cote_utc': max((row['heure_utc'] for row in eligible if row.get('cote') is not None), default=''),
    })
    return status


def calculer_cotes(cache, course, now, clock=None):
    """Publier le marché à partir du relevé canonique, avec versions pré-départ."""
    depart = instant(course['depart'])
    if depart is None or now.tzinfo is None:
        raise ValueError('Fuseau obligatoire')
    if now >= depart:
        return 'APRES_DEPART'
    archive_key = f"{course['date']}_{course['code']}_cotes"
    directory = Path(cache) / 'pronostics'
    with _chemin_verrou(cache, archive_key).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        doc = dernier_releve(cache, course)
        if doc.get('schema') != 2:
            return 'DONNEES_INSUFFISANTES'
        checked = instant(doc['controle_utc'])
        if checked > now:
            return 'RELEVE_PLUS_RECENT'
        rows = doc['chevaux']
        withdrawn = sorted(row['numero'] for row in rows if row.get('statut_np') == 'NON_PARTANT')
        ranking = sorted((row for row in rows if row.get('cote') is not None
                          and (observed := instant(row.get('heure_utc'))) and observed < depart
                          and observed <= now),
                         key=lambda row: (row['cote'], row['numero']))
        eligible = doc['partants_eligibles']
        if len(ranking) < 3:
            status = 'DONNEES_INSUFFISANTES'
        else:
            status = 'COMPLET' if doc['liste_complete'] and len(ranking) == eligible else 'PARTIEL'
        old = load(directory / f'{archive_key}.json', {}) or {}
        previous = instant(old.get('calcul_utc'))
        captured = clock() if clock else now
        if captured >= depart:
            return 'APRES_DEPART'
        if previous is not None and previous >= captured:
            return 'ANCIEN_RELEVE_PLUS_COMPLET'
        predicted = {
            'date': course['date'], 'course': course['code'], 'depart': course['depart'],
            'mode': 'COTES', 'version_moteur': 'cotes-v2', 'statut': status,
            'non_partants_confirmes': withdrawn, 'observations': len(ranking),
            'partants_eligibles': eligible,
            'donnees_observees_utc': max((row['heure_utc'] for row in ranking), default=''),
            'classement_complet': ranking if len(ranking) >= 3 else [],
            'top3': ranking[:3] if len(ranking) >= 3 else [],
        }
        if any(old.get(field) != value for field, value in predicted.items()):
            if previous is not None:
                key = previous.strftime('%Y%m%dT%H%M%S%fZ')
                archive = directory / 'versions' / f'{archive_key}_{key}.json'
                if not archive.exists():
                    save(archive, old)
            captured = captured.astimezone(timezone.utc).isoformat()
            save(directory / f'{archive_key}.json', {
                **predicted, 'calcul_utc': captured,
                'premier_calcul_utc': old.get('premier_calcul_utc', captured),
            })
    return 'CALCULE_' + status if len(ranking) >= 3 else status
