"""Rapprocher les arrivées PMU des versions attestées pour chaque réunion."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .echeances_production import PARIS, PHASES, instant, lire, reunions_du_jour, sauver

REPRISE = timedelta(minutes=30)
DELAI = timedelta(minutes=30)


def inventaire_confirme(record):
    return record.get('inventaire_pmu_verifie') is True


def planifier_rapprochements(cache, now):
    cache = Path(cache)
    day = now.astimezone(PARIS).date()
    dates = {day.isoformat(), (day - timedelta(days=1)).isoformat()}
    # Les reprises déjà engagées survivent à la rotation J/J-1.
    for path in (cache/'rapprochements').glob('????-??-??_R*.json'):
        if (record := lire(path)) and (record.get('statut') == 'INCOMPLET'
                                       or not record.get('publication_sheets_utc')
                                       or not inventaire_confirme(record)):
            dates.add(path.stem.split('_')[0])
    due = []
    for date in sorted(dates):
        for reunion in reunions_du_jour(cache, date):
            last = reunion['dernier_depart']
            if not last or now < last + DELAI:
                continue
            key = reunion['reunion']
            previous = lire(cache/'rapprochements'/f'{key}.json')
            if (previous.get('statut') == 'COMPLET' and previous.get('publication_sheets_utc')
                    and inventaire_confirme(previous)):
                continue
            # Pas de lancement en masse sur les archives préexistantes.
            if not previous and now > last + timedelta(hours=36):
                continue
            retry = instant(previous.get('prochaine_reprise_utc'))
            if retry and now < retry and previous.get('publication_sheets_utc'):
                continue
            due.append({'reunion': key, 'date': date, 'echeance': (last + DELAI).isoformat()})
    return due


def podium_officiel(cache, key, depart, now):
    arrival = lire(cache/'arrivees'/f'{key}.json')
    checked = instant(arrival.get('verifie_utc'))
    if (arrival.get('source') != 'PMU_API_PARTICIPANTS' or not checked
            or not depart < checked <= now):
        return None
    ranks = sorted((row['rang'], row['numero']) for row in arrival.get('arrivee', [])
                   if row.get('rang') in (1, 2, 3))
    podium = [number for _, number in ranks]
    if ([rank for rank, _ in ranks] == [1, 2, 3] and len(set(podium)) == 3
            and podium == arrival.get('podium_definitif_pmu')):
        return podium
    return None


def comparer(cache, key, depart, podium, certificat):
    from .performance_prospective import prevision_publiee

    scores = {}
    for phase in PHASES:
        proof = certificat.get(phase, {})
        for method, version in proof.get('versions', {}).items():
            read_at = instant(version.get('lecture_sheets_utc'))
            if not read_at or read_at != instant(version.get('publication_utc')):
                continue
            try:
                doc, numbers = prevision_publiee(cache, key, method, version, depart)
            except (KeyError, TypeError, ValueError, OSError):
                continue
            scores[f'{phase}_{method}'] = {'hits_top3': len(numbers.intersection(podium)),
                                          'sha256': version['sha256'],
                                          'numeros': [horse['numero'] for horse in doc['top3']],
                                          'calcul_utc': version['calcul_utc'],
                                          'statut_modele': doc.get('statut', '')}
    return scores


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
                not old.get('publication_sheets_utc') or old.get('statut') == 'COMPLET'):
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
                          'scores': comparer(cache, course_key, depart, podium, certificate) if podium else {}}
        pending = sorted(code for code, row in rows.items() if not row['podium'])
        finished = clock()
        deadline = reunion['dernier_depart'] + DELAI
        incomplete = bool(pending or not verified_inventory)
        sauver(path, {**item, 'echeance': deadline.isoformat(),
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
