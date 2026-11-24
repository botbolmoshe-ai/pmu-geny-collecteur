"""Planifier et attester les publications H-3/H-2, sans dépendance réseau."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from collections import defaultdict
import os
import re
from pathlib import Path
from dashboard.trot_analytics.dates import PARIS, instant_iso as instant

PHASES = {'H3': timedelta(hours=3), 'H2': timedelta(hours=2)}
PHASES_LECTURE = (*PHASES, 'H1')
VERSION_JALONS = 'H3_H2'
PHASE_SUIVANTE = dict(zip(PHASES, tuple(PHASES)[1:]))
MARGE = timedelta(minutes=30)  # fraîcheur des données, inchangée
# Quatre ticks au plus par heure. Conserver presque toute la fenêtre d'une
# heure pour absorber plusieurs ticks manquants, avec un cycle observé à 3 min 30.
ANTICIPATION = timedelta(minutes=55)


def lire(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}


def sauver(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    tmp.replace(path)


def courses_du_jour(cache, now):
    day = now.astimezone(PARIS).date().isoformat()
    return day, lire(Path(cache)/'sources_pmu'/f'programme_{day}.json').get('programme', [])


STATUTS_PUBLIES = {'PUBLIE_A_TEMPS', 'PUBLIE_EN_RETARD'}


def reunions_du_jour(cache, day, *, inventaire=None):
    programme = lire(Path(cache)/'sources_pmu'/f'programme_{day}.json')
    if inventaire is None:
        inventaire = programme.get('inventaire_reunions', programme.get('programme', []))
    groupes = defaultdict(list)
    for course in inventaire:
        ident = re.fullmatch(r'(R[1-9]\d*)C[1-9]\d*', course.get('code', ''))
        if ident:
            groupes[ident[1]].append(course)
    for ident, courses in sorted(groupes.items()):
        attendues = [c for c in courses if c.get('top3_attendu', True)]
        if not attendues:
            continue
        departs = [instant(c.get('depart')) for c in courses]
        hippodromes = {c['hippodrome'].strip().casefold() for c in courses if c.get('hippodrome')}
        coherent = (all(d and d.astimezone(PARIS).date().isoformat() == day for d in departs)
                    and len(hippodromes) <= 1
                    and len({c['code'] for c in courses}) == len(courses))
        yield {
            'reunion': f'{day}_{ident}', 'date': day, 'courses': courses,
            'hippodrome': next((c['hippodrome'] for c in courses if c.get('hippodrome')), None),
            'attendues': attendues, 'coherente': coherent,
            'premier_depart': min(departs).astimezone(timezone.utc) if coherent else None,
            'dernier_depart': max(departs).astimezone(timezone.utc) if coherent else None,
        }


def creneau_nocturne(now):
    return not 7 <= now.astimezone(PARIS).hour < 21


FRAICHEUR_PREPARATION_NOCTURNE = timedelta(hours=24)


def profil_preparation_disponible(cache, date, course, now):
    depart = instant(course.get('depart'))
    if not depart or depart <= now:
        return True
    profil = lire(cache / 'partants_actuels' / f"{date}_{course['code']}.json")
    capture = instant(profil.get('capture_utc'))
    chevaux = profil.get('chevaux', {})
    declares = course.get('nombre_declares')
    return bool(capture and timedelta(0) <= now - capture <= FRAICHEUR_PREPARATION_NOCTURNE
                and chevaux and (not declares or len(chevaux) == int(declares)))


def preparation_nocturne(cache, now):
    local = now.astimezone(PARIS)
    date = (local.date() + timedelta(days=local.hour >= 21)).isoformat()
    sources = cache / 'sources_pmu'
    programme = lire(sources / f'programme_{date}.json')
    controle = instant(programme.get('date_controle_utc'))
    if (controle and timedelta(0) <= now - controle <= FRAICHEUR_PREPARATION_NOCTURNE
            and all(profil_preparation_disponible(cache, date, course, now)
                    for course in programme.get('programme', []))):
        return None
    diagnostic = lire(sources / f'diagnostic_{date}.json')
    dernier_essai = instant(diagnostic.get('horodatage_utc'))
    if dernier_essai and timedelta(0) <= now - dernier_essai < timedelta(hours=1):
        return None
    return date


def planifier(cache, now, force=False):
    if now.tzinfo is None:
        raise ValueError('Heure avec fuseau obligatoire')
    now = now.astimezone(timezone.utc)
    cache = Path(cache)
    previous = lire(cache/'orchestration/production_etat.json')
    last = instant(previous.get('dernier_global_publie_utc'))
    day = now.astimezone(PARIS).date().isoformat()
    nuit = creneau_nocturne(now)
    global_due = not nuit and (force or not last or not timedelta(0) <= now-last < timedelta(hours=1))
    preparation = preparation_nocturne(cache, now) if nuit else None
    needs, upcoming, erreurs = [], [], []
    for reunion in (() if nuit else reunions_du_jour(cache, day)):
        key = reunion['reunion']
        first = reunion['premier_depart']
        if not first:
            erreurs.append({'reunion': key, 'motif': 'PROGRAMME_REUNION_INCOHERENT'})
            continue
        if now >= first:
            continue
        certificate = lire(cache/'jalons/reunions'/f'{key}.json')
        fulfilled = {phase for phase in PHASES
                     if certificate.get(phase, {}).get('statut') in STATUTS_PUBLIES
                     and certificate[phase].get('courses_attendues') == sorted(
                         c['code'] for c in reunion['attendues'])
                     and instant(certificate[phase].get('reference_utc')) == first
                     and instant(certificate[phase].get('echeance')) == first - PHASES[phase]}
        # Une exécution ne peut attester qu'une version par réunion.
        for phase in reversed(PHASES):
            deadline = first - PHASES[phase]
            start = deadline - ANTICIPATION
            if phase in fulfilled:
                continue
            if now < start:
                upcoming.append(start)
                continue
            suivante = PHASE_SUIVANTE.get(phase)
            if suivante and now >= first - PHASES[suivante] - ANTICIPATION:
                continue
            for c in reunion['attendues']:
                needs.append({'course': f"{day}_{c['code']}", 'reunion': key,
                              'phase': phase, 'echeance': deadline.isoformat()})
            break
    prochain_jalon = min(upcoming).isoformat() if upcoming else None
    if not nuit and last and last+timedelta(hours=1)>now:
        upcoming.append(last+timedelta(hours=1))
    needs.sort(key=lambda item: (instant(item['echeance']) < now, instant(item['echeance']), item['course']))
    selection = list(dict.fromkeys(item['course'].split('_', 1)[1] for item in needs))
    from .rapprochement_reunions import planifier_rapprochements
    results = planifier_rapprochements(cache, now, prochaines=upcoming)
    secours = bool(selection or results or preparation or (
        global_due and (not last or now - last >= timedelta(hours=2))))
    return {'plan_utc':now.isoformat(), 'date':day, 'erreurs': erreurs, 'version_jalons':VERSION_JALONS,
            'executer':bool(global_due or selection or results or preparation),
            'mode': ('JALONS' if selection else 'RAPPROCHEMENT' if results else
                     'PREPARATION_JOUR' if preparation else 'GLOBAL' if global_due else 'ATTENTE'),
            'date_preparation': preparation, 'secours_pmu': secours,
            'selection':selection, 'prochain_jalon_utc':prochain_jalon, 'jalons_dus':needs, 'rapprochements_dus':results,
            'prochain_besoin_utc':min(upcoming).isoformat() if upcoming else None}


def besoin_pmu(cache, now):
    """Réserver le créneau avant une échéance, même si le cron est retardé."""
    if creneau_nocturne(now):
        return motif_pause_collecte_nocturne(cache, now)
    plan = planifier(cache, now)
    prochain = instant(plan['prochain_jalon_utc'])
    if plan['executer'] or (prochain and prochain <= now + timedelta(minutes=30)):
        return 'ECHEANCE_PMU_PRIORITAIRE'
    return None


# Sous-processus (240 s), cadence adaptative (60 s), sauvegarde et relais.
MARGE_COLLECTE = timedelta(minutes=8)


def limite_collecte_nocturne(cache, now):
    local = now.astimezone(PARIS)
    if 7 <= local.hour < 21:
        return timedelta(), 'HORS_CRENEAU_NOCTURNE'
    date_fin = local.date() + timedelta(days=int(local.hour >= 21))
    fin = datetime.combine(date_fin, datetime.min.time(), PARIS).replace(hour=7)
    restant = fin.astimezone(timezone.utc) - now - MARGE_COLLECTE
    if restant <= timedelta():
        return timedelta(), 'HORS_CRENEAU_NOCTURNE'
    plan = planifier(cache, now)
    if plan['executer']:
        return timedelta(), 'ECHEANCE_PMU_PRIORITAIRE'
    besoin = instant(plan['prochain_besoin_utc'])
    if besoin:
        restant = min(restant, besoin - now - MARGE_COLLECTE)
    if restant <= timedelta():
        return timedelta(), 'ECHEANCE_PMU_PRIORITAIRE'
    return restant, None


def motif_pause_collecte_nocturne(cache, now):
    return limite_collecte_nocturne(cache, now)[1]


def budget_collecte_nocturne(cache, now):
    restant, _ = limite_collecte_nocturne(cache, now)
    return min(15, restant // timedelta(minutes=1))


def etat_cooldown_geny(cache, now, *, prod=None, back=None):
    """Dater l'observation et conserver l'échéance, même après expiration."""
    cache = Path(cache)
    if prod is None:
        prod = lire(cache / 'collecte_incrementale/etat.json')
    if back is None:
        back = lire(cache / 'rattrapage_historiques/etat.json')
    journal = lire(cache / 'etat_persistant.json')
    incident = journal.get('dernier_blocage_geny') or {}
    blocked = instant(incident.get('utc'))
    pauses = [instant(state.get('prochain_acces_geny_utc')) for state in (prod, back)]
    if blocked:
        pauses.append(blocked + timedelta(minutes=30))
        pauses.append(instant(incident.get('reprise_au_plus_tot_utc')))
    deadline = max((pause for pause in pauses if pause), default=None)
    active = bool(deadline and deadline > now)
    return {
        'controle_utc': now.isoformat(),
        'dernier_incident': incident if blocked else None,
        'echeance_utc': deadline.isoformat() if deadline else None,
        'actif': active,
        'etat': 'ACTIF' if active else 'EXPIRE' if deadline else 'ABSENT',
    }


def pause_geny_active(cache, now, *, prod=None, back=None):
    state = etat_cooldown_geny(cache, now, prod=prod, back=back)
    return instant(state['echeance_utc']) if state['actif'] else None


def plan_collecte(cache, now, *, nocturne=False):
    """Contrôle léger avant installation du navigateur et des dépendances."""
    cache = Path(cache)
    result = {'plan_utc': now.isoformat(), 'executer': True, 'geny': True,
              'mode': 'HISTORIQUES_NOCTURNES' if nocturne else 'HISTORIQUES'}
    cooldown = etat_cooldown_geny(cache, now)
    result['cooldown_geny'] = cooldown
    if cooldown['actif']:
        result.update(geny=False, prochain_acces_geny_utc=cooldown['echeance_utc'])
    motif = motif_pause_collecte_nocturne(cache, now) if nocturne else besoin_pmu(cache, now)
    if motif:
        secours = motif == 'ECHEANCE_PMU_PRIORITAIRE' and planifier(cache, now)['secours_pmu']
        return {**result, 'executer': False, 'motif': motif, 'geny': False, 'secours_pmu': secours}
    if cooldown['actif']:
        prod = lire(cache / 'collecte_incrementale/etat.json')
        pending = prod.get('sync_kpi') == 'A_REPRENDRE' or any(
            h.get('sync') == 'A_FAIRE'
            and (not (retry := instant(h.get('prochaine_sync_utc'))) or retry <= now)
            for h in prod.get('chevaux', {}).values())
        return {**result, 'executer': nocturne or pending, 'motif': 'COOLDOWN_GENY_GLOBAL'}
    return result


def relais_historiques(cache, now, plan, *, nocturne=False):
    """Relayer seulement après une tâche PMU utile et persistée."""
    mode = plan.get('mode')
    debut = instant(plan.get('plan_utc'))
    if mode not in {'PREPARATION_JOUR', 'RAPPROCHEMENT', 'GLOBAL', 'JALONS'} or not debut or debut > now:
        return False
    if mode == 'GLOBAL':
        last = instant(lire(Path(cache) / 'orchestration/production_etat.json').get('dernier_global_publie_utc'))
        if not last or not debut <= last <= now:
            return False
    nuit = creneau_nocturne(now)
    if (nocturne and not nuit) or (nuit and budget_collecte_nocturne(cache, now) < 2):
        return False
    return plan_collecte(cache, now, nocturne=nuit)['executer']


def relais_nocturne(cache, now, plan):
    return relais_historiques(cache, now, plan, nocturne=True)


def prevision_valide(doc, depart, now, ml=False, key=None):
    created = instant(doc.get('calcul_utc'))
    try:
        numbers = [int(h['numero']) for h in doc.get('top3', [])]
    except (KeyError, ValueError, TypeError):
        return False
    if (not created or not created <= now < depart or len(numbers) != 3 or len(set(numbers)) != 3
            or any(not 1<=n<=30 for n in numbers)):
        return False
    if instant(doc.get('depart')) != depart:
        return False
    if key and doc.get('date','')+'_'+doc.get('course','') != key:
        return False
    if ml and doc.get('statut') not in ('ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE','ML_ENTRAINE_NON_CALIBRE'):
        return False
    if ml and doc.get('experimental'):
        trained = instant(doc.get('entrainement_utc'))
        labelled = instant(doc.get('dernier_label_entrainement_utc'))
        if not trained or not labelled or not labelled <= trained <= created:
            return False
    return True


def preuves_sheets(rows, now, *, observations_verifiees=False):
    """Reconstituer les sélections effectivement lisibles dans le registre."""
    from dashboard.trot_analytics.dates import meme_date_sheets

    groups = defaultdict(list)
    for row in rows:
        day, code = row.get('date_course'), row.get('rncn')
        if day and code:
            groups[f'{day}_{code}'].append(row)
    proofs = {}
    for key, group in groups.items():
        for kind, rank, selected, version in (
            ('direct', 'top3_direct_rang', 'top3_direct_top3', 'top3_direct_utc'),
            ('ml', 'ml_rang', 'ml_top3', 'version_ml_utc'),
        ):
            picked = [row for row in group if row.get(selected) == 'OUI']
            if len(picked) != 3 or any(r.get('non_partant') != 'PARTANT' for r in picked):
                continue
            try:
                ranking = sorted((int(r[rank]), int(r['numero'])) for r in picked)
            except (KeyError, TypeError, ValueError):
                continue
            first_version = picked[0].get(version)
            if ([i for i, _ in ranking] == [1, 2, 3] and instant(first_version)
                    and all(meme_date_sheets(version, r.get(version), first_version) for r in picked[1:])):
                proofs.setdefault(key, {})[kind] = {'numeros': [n for _, n in ranking],
                                                     'calcul_utc': first_version}
    result = {'lecture_utc': now.isoformat(), 'courses': proofs}
    from .ipr import actif
    if observations_verifiees and actif():
        from .ipr_prospectif import donnees_sheets
        day = now.astimezone(PARIS).date().isoformat()
        result['ipr'] = donnees_sheets(row for row in rows if row.get('date_course', '') >= day)
    return result


def enregistrer_publication(cache, now, plan, publie, *, sheets=None):
    """Appeler après Sheets : une tentative ou un calcul seul ne vaut pas publication."""
    from dashboard.trot_analytics.dates import meme_date_sheets
    cache = Path(cache)
    report = {'controle_utc':now.isoformat(), 'publication_reussie':bool(publie),
              'plan':plan, 'courses':[], 'erreurs':list(plan.get('erreurs', []))}
    day = plan.get('date') or now.astimezone(PARIS).date().isoformat()
    reunions = list(reunions_du_jour(cache, day))
    by_course = {c['code']: r for r in reunions for c in r['attendues']}
    phases_dues = {(item['course'], item['phase']) for item in plan.get('jalons_dus', [])}
    observation = instant(sheets.get('lecture_utc')) if sheets else None
    sheets_confirme = bool(publie and observation and observation <= now)
    if plan.get('mode') in ('GLOBAL', 'JALONS', 'RAPPROCHEMENT'):
        report['publication_reussie'] = sheets_confirme
        if not sheets_confirme:
            report['erreurs'].append({'motif': 'PUBLICATION_SHEETS_NON_PROUVEE'})
    if sheets_confirme and plan.get('mode') in ('GLOBAL', 'JALONS'):
        courses = [c for r in reunions if r['coherente'] for c in r['attendues']]
        for c in courses:
            if plan.get('mode')=='JALONS' and c['code'] not in plan.get('selection',[c['code']]):
                continue
            depart = instant(c.get('depart'))
            if not depart or depart <= now:
                continue  # Aucune attestation de publication pré-départ rétrospective.
            key = day+'_'+c['code']
            profile = lire(cache/'partants_actuels'/f'{key}.json')
            captured = instant(profile.get('capture_utc'))
            try:
                eligible = {int(n) for n,h in profile.get('chevaux',{}).items() if h.get('statut_np')=='PARTANT'}
            except (ValueError,TypeError,AttributeError):
                report['erreurs'].append({'course':key,'motif':'PARTANTS_SCHEMA_INVALIDE'})
                continue
            proofs = {}
            docs = {}
            for kind, suffix in (('direct','direct'), ('ml','ml_latest')):
                path = cache/'pronostics'/f'{key}_{suffix}.json'
                doc = lire(path)
                valid = prevision_valide(doc, depart, now, ml=kind=='ml', key=key)
                if (not valid or not captured or not timedelta(0)<=now-captured<=MARGE
                        or not {int(h['numero']) for h in doc.get('top3',[])}.issubset(eligible)):
                    report['erreurs'].append({'course':key, 'mode':kind, 'motif':'TOP3_ABSENT_OU_INVALIDE'})
                    continue
                observed = sheets.get('courses', {}).get(key, {}).get(kind, {})
                numbers = [int(h['numero']) for h in doc['top3']]
                if (observed.get('numeros') != numbers
                        or not meme_date_sheets('calcul_utc', observed.get('calcul_utc'), doc['calcul_utc'])
                        or captured > observation or not instant(doc['calcul_utc']) <= observation < depart):
                    report['erreurs'].append({'course': key, 'mode': kind, 'motif': 'TOP3_NON_CONFIRME_SHEETS'})
                    continue
                docs[kind] = doc
                proofs[kind] = {'calcul_utc':doc['calcul_utc'], 'publication_utc':observation.isoformat(),
                    'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'fichier':str(path.relative_to(cache)), 'empreinte_modele':doc.get('empreinte_modele'),
                    'lecture_sheets_utc':observation.isoformat(), 'capture_partants_utc':captured.isoformat()}
            if 'direct' in proofs:
                from .maturite_ml import certify_shadow
                certify_shadow(cache, key, proofs['direct'], observation)
                sauver(cache/'publications'/'direct'/f'{key}.json',
                       {'course': key, 'depart': depart.isoformat(), 'versions': {'direct': proofs['direct']}})
            if len(proofs) == 2:
                sauver(cache/'publications'/f'{key}.json',
                       {'course':key,'depart':depart.isoformat(),'versions':proofs})
            phases = lire(cache/'jalons'/f'{key}.json')
            for phase, offset in PHASES.items():
                if phases.get(phase, {}).get('statut') in STATUTS_PUBLIES:
                    continue
                first = by_course[c['code']]['premier_depart']
                deadline = first-offset
                if ((key, phase) not in phases_dues or observation is None
                        or observation >= first or now < deadline-ANTICIPATION):
                    continue
                selected = {}
                for kind, proof in proofs.items():
                    if instant(proof['calcul_utc']) < max(
                            deadline-ANTICIPATION, instant(plan['plan_utc'])):
                        continue
                    stamp = instant(proof['calcul_utc']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                    frozen = cache/'jalons'/key/f'{phase}_{kind}_{stamp}.json'
                    if not frozen.exists():
                        sauver(frozen, docs[kind])
                    frozen_doc = lire(frozen)
                    # Une copie présente reste immuable ; ne pas l'attribuer à un autre calcul.
                    if frozen_doc != docs[kind]:
                        continue
                    selected[kind] = {**proof, 'fichier':str(frozen.relative_to(cache)),
                                      'sha256':hashlib.sha256(frozen.read_bytes()).hexdigest()}
                complete = len(selected) == 2
                phases[phase] = {'echeance':deadline.isoformat(), 'controle_utc':now.isoformat(),
                    'reference_utc':first.isoformat(), 'demarrage_utc':plan['plan_utc'], 'version_jalons':VERSION_JALONS,
                    'fin_calcul_utc':max((p['calcul_utc'] for p in selected.values()), default=None),
                    'publication_utc':observation.isoformat() if complete else None,
                    'statut':('PUBLIE_A_TEMPS' if observation<=deadline else 'PUBLIE_EN_RETARD') if complete else 'INCOMPLET',
                    'retard_secondes':max(0, (observation-deadline).total_seconds()), 'versions':selected}
                if not complete:
                    report['erreurs'].append({'course':key,'phase':phase,'motif':'JALON_INCOMPLET'})
                elif observation>deadline:
                    report['erreurs'].append({'course':key,'phase':phase,'motif':'JALON_PUBLIE_EN_RETARD'})
            if phases:
                sauver(cache/'jalons'/f'{key}.json', phases)
            report['courses'].append({'course':key, 'top3_direct_et_ml':len(proofs)==2, 'jalons':phases})
        if plan.get('mode') == 'GLOBAL' and observation:
            # Un retard attesté est une anomalie, pas un échec de publication globale.
            # Ne pas redéclencher indéfiniment le global au détriment des historiques.
            # Le cache ancien d'un programme ne suffit pas à valider un cycle global.
            days = [now.astimezone(PARIS).date()+timedelta(days=n) for n in (0,1)]
            stamps = [instant(lire(cache/'sources_pmu'/f'programme_{d}.json').get('date_controle_utc')) for d in days]
            if all(s and timedelta(0)<=now-s<=MARGE for s in stamps):
                sauver(cache/'orchestration/production_etat.json',
                       {'dernier_global_publie_utc':now.isoformat()})
    report['rapprochements'] = []
    if plan.get('mode') == 'RAPPROCHEMENT':
        for item in plan.get('rapprochements_dus', []):
            path = cache/'rapprochements'/f"{item['reunion']}.json"
            record = lire(path)
            if not record:
                # Le programme PMU peut repousser le dernier départ après la
                # planification initiale. Le rapprochement est alors différé
                # légitimement : ne pas faire échouer la certification.
                current = next((r for r in reunions_du_jour(cache, item['date'])
                                if r['reunion'] == item['reunion']), None)
                from .rapprochement_reunions import DELAI
                if current and current['dernier_depart'] and now < current['dernier_depart'] + DELAI:
                    report['rapprochements'].append({
                        'reunion': item['reunion'], 'statut': 'DIFFERE_DEPART_REPORTE',
                        'prochaine_echeance_utc': (current['dernier_depart'] + DELAI).isoformat()})
                    continue
                report['erreurs'].append({'reunion': item['reunion'], 'motif': 'RAPPROCHEMENT_NON_DEMARRE'})
                continue
            if sheets_confirme and not record.get('publication_sheets_utc'):
                record['publication_sheets_utc'] = observation.isoformat()
                sauver(path, record)
            report['rapprochements'].append({
                field: record.get(field) for field in ('reunion', 'echeance', 'declenchement_utc', 'statut',
                                                       'arrivees_a_reprendre', 'publication_sheets_utc')
            })
    report['reunions'] = []
    for reunion in reunions:
        key = reunion['reunion']
        first = reunion['premier_depart']
        expected = sorted(c['code'] for c in reunion['attendues'])
        path = cache/'jalons/reunions'/f'{key}.json'
        records = lire(path)
        for phase, offset in PHASES.items():
            if not first or now < first-offset-ANTICIPATION:
                continue
            previous = records.get(phase, {})
            if previous.get('statut') in STATUTS_PUBLIES:
                continue
            per_course = {}
            for code in expected:
                proof = lire(cache/'jalons'/f'{day}_{code}.json').get(phase, {})
                if (instant(proof.get('reference_utc')) == first
                        and instant(proof.get('echeance')) == first-offset):
                    per_course[code] = proof
            complete = len(per_course) == len(expected) and all(
                p['statut'] in STATUTS_PUBLIES for p in per_course.values())
            due = any((f'{day}_{code}', phase) in phases_dues for code in expected)
            if not due and now <= first-offset:
                continue
            status = 'ECHEC' if due and not sheets_confirme else 'INCOMPLET'
            if complete:
                status = ('PUBLIE_A_TEMPS' if all(p['statut'] == 'PUBLIE_A_TEMPS'
                          for p in per_course.values()) else 'PUBLIE_EN_RETARD')
            records[phase] = {
                'statut': status, 'reference_utc': first.isoformat(), 'version_jalons':VERSION_JALONS,
                'hippodrome': reunion['hippodrome'],
                'inventaire': [{'code': c['code'], 'statut_pmu': c.get('statut_pmu'),
                                'top3_attendu': c.get('top3_attendu', True)} for c in reunion['courses']],
                'echeance': (first-offset).isoformat(), 'courses_attendues': expected,
                'demarrage_utc': min((p['demarrage_utc'] for p in per_course.values()),
                                     default=plan.get('plan_utc')),
                'fin_calcul_utc': max((p['fin_calcul_utc'] for p in per_course.values()
                                      if p.get('fin_calcul_utc')), default=None),
                'publication_utc': max((p['publication_utc'] for p in per_course.values()),
                                       default=None) if complete else None,
                'courses': per_course,
            }
            if due and status != 'PUBLIE_A_TEMPS':
                report['erreurs'].append({'reunion': key, 'phase': phase, 'motif': status})
        if records:
            sauver(path, records)
            report['reunions'].append({'reunion': key, 'jalons': records})
    from .ipr import actif
    if actif():
        from .ipr_prospectif import certifier, mesurer
        try:
            if sheets_confirme:
                report['ipr_jalons_figes'] = certifier(cache, plan, sheets)
            bilan = mesurer(cache, now)
            sauver(cache/'ipr/bilan.json', bilan)
            print(f'IPR_BILAN courses_prospectives={bilan["depuis_activation"]}', flush=True)
        except Exception as exc:
            report['ipr_controle'] = 'INDISPONIBLE'
            print(f'::warning::Contrôle IPR indisponible ({type(exc).__name__})', flush=True)
    sauver(cache/'qualite/dernier_controle_production.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default='cache_pmu')
    parser.add_argument('--plan', default='resultats/plan_production.json')
    parser.add_argument('--certifier', action='store_true')
    parser.add_argument('--strict', action='store_true')
    parser.add_argument('--collecte', action='store_true')
    parser.add_argument('--collecte-nocturne', action='store_true')
    parser.add_argument('--collecte-selon-heure', action='store_true')
    parser.add_argument('--preuve-sheets')
    parser.add_argument('--relais-nocturne', action='store_true')
    parser.add_argument('--relais-historiques', action='store_true')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.relais_nocturne or args.relais_historiques:
        autorise = relais_historiques(args.cache, now, lire(args.plan), nocturne=args.relais_nocturne)
        raise SystemExit(0 if autorise else 1)
    if args.certifier:
        result = enregistrer_publication(args.cache, now, lire(args.plan), os.getenv('PUBLICATION_REUSSIE')=='true',
                                            sheets=lire(args.preuve_sheets) if args.preuve_sheets else None)
    else:
        collecte = args.collecte or args.collecte_nocturne or args.collecte_selon_heure
        nuit = creneau_nocturne(now)
        nocturne = args.collecte_nocturne or (args.collecte_selon_heure and nuit)
        if collecte:
            result = plan_collecte(args.cache, now, nocturne=nocturne)
        else:
            result = planifier(args.cache, now, force=os.getenv('FORCER_AUTO')=='true')
        if not collecte and (mode := os.getenv('MODE_PRODUCTION', 'auto')) != 'auto':
            autorise = not creneau_nocturne(now) or mode in {'decouvrir', 'collecter', 'consolider'}
            result.update(executer=autorise, mode='MANUEL' if autorise else 'ATTENTE')
        sauver(args.plan, result)
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:
                f.write('executer='+str(result['executer']).lower()+'\n')
                f.write('mode='+result['mode']+'\n')
                f.write('nocturne='+str(nocturne if collecte else nuit).lower()+'\n')
                if collecte:
                    f.write('geny='+str(result['geny']).lower()+'\n')
                    f.write('secours_pmu='+str(result.get('secours_pmu', False)).lower()+'\n')
    print(json.dumps(result, ensure_ascii=False))
    if args.certifier and args.strict and (not result['publication_reussie'] or result['erreurs']):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
