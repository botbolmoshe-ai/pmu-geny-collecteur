"""Rapprocher les arrivées PMU des versions attestées pour chaque réunion."""
from collections import defaultdict
from functools import lru_cache
from hashlib import sha256
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .echeances_production import PARIS, PHASES_LECTURE, course_annulee, identite_course, instant, lire, reunions_du_jour, sauver
from .resultats_v18 import classement_podium

REPRISE = timedelta(minutes=30)
DELAI = timedelta(minutes=30)


def inventaire_confirme(record):
    return record.get('inventaire_pmu_verifie') is True


# Instantanés déjà publics sur pmu-data, antérieurs aux TOP3 qu'ils documentent.
ARCHIVES_PROGRAMME = {
    '2026-11-25': (
        'd0f654aca65ea778130171ffdc4f1a77436085d6',
        'e21d067472694e1c92e135a9b88fa5e473400d5a',
    ),
}
REPRISES_PROGRAMME = {'2026-11-25_R2', '2026-11-25_R4'}


@lru_cache(maxsize=4)
def programmes_archives(date):
    archives = []
    for commit in ARCHIVES_PROGRAMME.get(date, ()):
        path = f'sources_pmu/programme_{date}.json'
        try:
            payload = subprocess.check_output(
                ['git', 'show', f'{commit}:{path}'], cwd=Path(__file__).resolve().parents[1],
                stderr=subprocess.DEVNULL, timeout=5)
            programme = json.loads(payload)
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        archives.append((instant(programme.get('date_controle_utc')),
                         {item['code']: item for item in programme['inventaire_reunions']}))
    return tuple(archives)


def revision_preuves(reunion):
    if reunion in REPRISES_PROGRAMME:
        refs = ARCHIVES_PROGRAMME[reunion.split('_', 1)[0]]
        return sha256(''.join(refs).encode()).hexdigest()
    return None


def relecture_preuves_due(reunion, record):
    revision = revision_preuves(reunion)
    return bool(revision and record.get('revision_preuves_programme') != revision)


def depart_archive(cache, key, method, proof, identite):
    from .performance_prospective import retrouver

    date, code = key.split('_', 1)
    archives = programmes_archives(date)
    if not archives:
        return None
    version = retrouver(cache, key, method, proof)
    depart_original = instant(version.get('depart')) if version else None
    calcul = instant(proof.get('calcul_utc'))
    for capture, courses in archives:
        course = courses.get(code, {})
        if (depart_original and capture and calcul and capture <= calcul
                and identite_course(course) == identite
                and instant(course.get('depart')) == depart_original):
            return depart_original
    return None


def planifier_rapprochements(cache, now, *, prochaines=None):
    cache = Path(cache)
    day = now.astimezone(PARIS).date()
    dates = {day.isoformat(), (day - timedelta(days=1)).isoformat()}
    # Les reprises déjà engagées survivent à la rotation J/J-1.
    for path in (cache/'rapprochements').glob('????-??-??_R*.json'):
        if (record := lire(path)) and (record.get('statut') == 'INCOMPLET'
                                       or not record.get('publication_sheets_utc')
                                       or not inventaire_confirme(record)
                                       or relecture_preuves_due(path.stem, record)):
            dates.add(path.stem.split('_')[0])
    due = []
    for date in sorted(dates):
        for reunion in reunions_du_jour(cache, date):
            last = reunion['dernier_depart']
            if not last:
                continue
            key = reunion['reunion']
            previous = lire(cache/'rapprochements'/f'{key}.json')
            if (previous.get('statut') == 'COMPLET' and previous.get('publication_sheets_utc')
                    and inventaire_confirme(previous) and not relecture_preuves_due(key, previous)):
                continue
            # Pas de lancement en masse sur les archives préexistantes.
            if not previous and now > last + timedelta(hours=36):
                continue
            echeance = last + DELAI
            retry = instant(previous.get('prochaine_reprise_utc'))
            disponible = max(echeance, retry) if retry and previous.get('publication_sheets_utc') else echeance
            if now < disponible:
                if prochaines is not None:
                    prochaines.append(disponible)
                continue
            due.append({'reunion': key, 'date': date, 'echeance': echeance.isoformat()})
    return due


def podium_officiel(cache, key, depart, now):
    arrival = lire(cache/'arrivees'/f'{key}.json')
    checked = instant(arrival.get('verifie_utc'))
    if (arrival.get('source') != 'PMU_API_PARTICIPANTS' or not checked
            or not depart < checked <= now):
        return None
    podium = classement_podium(arrival.get('arrivee', []))
    return podium if podium and podium == arrival.get('podium_definitif_pmu') else None


def comparer(cache, key, depart, podium, certificat, *, rejets=None, course=None):
    from .performance_prospective import prevision_publiee

    scores = {}
    for phase in PHASES_LECTURE:
        proof = certificat.get(phase, {})
        for method, version in proof.get('versions', {}).items():
            read_at = instant(version.get('lecture_sheets_utc'))
            if not read_at or read_at != instant(version.get('publication_utc')):
                if rejets is not None:
                    rejets[f'{phase}_{method}'] = 'RELECTURE_SHEETS_NON_PROUVEE'
                continue
            source = version.get('programme_pmu', {})
            identity = identite_course(course) if course else None
            original = instant(source.get('depart')) if identity and source.get('identite') == identity else None
            try:
                if not original and identity:
                    original = depart_archive(cache, key, method, version, identity)
                doc, numbers = prevision_publiee(cache, key, method, version, depart,
                                                depart_programme=original)
            except (KeyError, TypeError, ValueError, OSError) as exc:
                if rejets is not None:
                    rejets[f'{phase}_{method}'] = str(exc) if isinstance(exc, ValueError) else 'ARCHIVE_INVALIDE'
                continue
            scores[f'{phase}_{method}'] = {'hits_top3': len(numbers.intersection(podium)),
                                          'sha256': version['sha256'],
                                          'numeros': [horse['numero'] for horse in doc['top3']],
                                          'calcul_utc': version['calcul_utc'],
                                          'statut_modele': doc.get('statut', '')}
    return scores


def rattraper_obligations(cache, plan_path, clock=lambda: datetime.now(timezone.utc)):
    """Préserver les obligations du plan et inclure celles échues pendant le cycle."""
    plan = lire(plan_path)
    if not plan:
        raise ValueError('Plan de production absent')
    obligations = {item['reunion']: item for item in plan.get('rapprochements_dus', [])}
    obligations.update({item['reunion']: item for item in planifier_rapprochements(cache, clock())})
    plan['rapprochements_dus'] = list(obligations.values())
    sauver(plan_path, plan)
    if obligations:
        rapprocher(cache, plan, clock)
    return plan


def rapprocher(cache, plan, clock=lambda: datetime.now(timezone.utc)):
    from .auto_v18 import BASE, get_json, programme_diagnostic
    from .resultats_v18 import enregistrer_resultats

    cache = Path(cache)
    programmes = {}
    for item in plan.get('rapprochements_dus', []):
        date, key = item['date'], item['reunion']
        reunion = next((r for r in reunions_du_jour(cache, date) if r['reunion'] == key), None)
        started = clock()
        if not reunion or not reunion['dernier_depart'] or started < reunion['dernier_depart'] + DELAI:
            continue
        path = cache/'rapprochements'/f'{key}.json'
        old = lire(path)
        if old and 'inventaire_pmu_verifie' in old and (
                not old.get('publication_sheets_utc') or
                (old.get('statut') == 'COMPLET' and not relecture_preuves_due(key, old))):
            continue
        url = BASE + datetime.fromisoformat(date).strftime('%d%m%Y')
        programme_path = cache/'sources_pmu'/f'programme_{date}.json'
        if date not in programmes:
            try:
                _, diagnostic = programme_diagnostic(get_json(url), date)
                programmes[date] = diagnostic['inventaire_reunions']
                cached = lire(programme_path)
                sauver(programme_path, {**cached, 'inventaire_reunions': programmes[date]})
            except (ValueError, OSError, TypeError, KeyError, RuntimeError):
                programmes[date] = None
        programme = programmes[date]
        current = next((r for r in reunions_du_jour(cache, date, inventaire=programme)
                        if r['reunion'] == key and r['coherente']), None) if programme is not None else None
        verified_inventory = current is not None
        if current:
            reunion = current
            if started < current['dernier_depart'] + DELAI:
                continue
        rows = {}
        for course in reunion['courses']:
            code = course['code']
            course_key = f'{date}_{code}'
            if course_annulee(course):
                rows[code] = {'statut': 'COURSE_ANNULEE', 'podium': None,
                              'top3_attendu': False, 'scores': {}}
                continue
            depart = instant(course['depart'])
            podium = podium_officiel(cache, course_key, depart, clock())
            status = 'ARRIVEE_MANQUANTE'
            if not podium:
                try:
                    if verified_inventory:
                        raw = get_json(url + '/' + code.replace('C', '/C', 1) + '/participants')
                        status = 'ARRIVEE_NON_VERIFIEE'
                        if course.get('podium_definitif_pmu'):
                            enregistrer_resultats(cache, course, raw, observe=clock())
                        podium = podium_officiel(cache, course_key, depart, clock())
                except (ValueError, OSError, TypeError, KeyError, RuntimeError):
                    pass
            certificate = lire(cache/'jalons'/f'{course_key}.json')
            rows[code] = {'statut': 'ARRIVEE_OFFICIELLE' if podium else status,
                          'podium': podium, 'top3_attendu': course.get('top3_attendu', True),
                          'scores': comparer(cache, course_key, depart, podium, certificate, course=course) if podium else {}}
        pending = sorted(code for code, row in rows.items()
                         if not row['podium'] and row['statut'] != 'COURSE_ANNULEE')
        finished = clock()
        deadline = reunion['dernier_depart'] + DELAI
        incomplete = bool(pending or not verified_inventory)
        revision = revision_preuves(key)
        sauver(path, {**item, 'echeance': deadline.isoformat(),
                      **({'revision_preuves_programme': revision} if revision and verified_inventory
                         and len(programmes_archives(date)) == len(ARCHIVES_PROGRAMME[date]) else {}),
                      'reference_utc': reunion['dernier_depart'].isoformat(),
                      'inventaire_pmu_verifie': verified_inventory,
                      'declenchement_utc': old.get('declenchement_utc', started.isoformat()),
                      'retard_declenchement_secondes': old.get('retard_declenchement_secondes',
                          (started - (reunion['dernier_depart'] + DELAI)).total_seconds()),
                      'dernier_demarrage_utc': started.isoformat(), 'fin_utc': finished.isoformat(),
                      'statut': 'INCOMPLET' if incomplete else 'COMPLET',
                      'arrivees_a_reprendre': pending,
                      'prochaine_reprise_utc': (finished + REPRISE).isoformat() if incomplete else None,
                      'courses': rows, 'performances': aggreger(rows.values())})


def aggreger(rows):
    scores = defaultdict(list)
    for row in rows:
        for label, score in row.get('scores', {}).items():
            scores[label].append(score['hits_top3'])
    return {label: {'courses': len(values), 'moyenne_sur_3': sum(values)/len(values),
                    'exact_3_sur_3': values.count(3)} for label, values in scores.items()}
