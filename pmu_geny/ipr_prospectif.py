"""Geler les versions IPR relues dans Sheets et évaluer les arrivées PMU."""
from collections import defaultdict
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from statistics import median

from dashboard.trot_analytics.dates import meme_date_sheets
from dashboard.trot_analytics.usages import IPR
from .echeances_production import ANTICIPATION, PARIS, PHASES, instant, lire, sauver
from .ipr import VERSION
from .performance_prospective import prevision_publiee


def donnees_sheets(rows):
    groups = defaultdict(dict)
    for row in rows:
        if row.get('ipr_version') and row.get('date_course') and row.get('rncn'):
            key = f"{row['date_course']}_{row['rncn']}"
            number = str(row.get('numero'))
            if number in groups[key]:
                groups[key][number] = None
            else:
                groups[key][number] = {field: row.get(field, '') for field in IPR.libelles}
    return dict(groups)


def certifier(cache, plan, sheets):
    from .sync_google_sheets import sheet_value

    cache = Path(cache)
    publication = instant(sheets.get('lecture_utc'))
    start = instant(plan.get('plan_utc'))
    if not publication or not start:
        return {}
    counts = {}
    for item in plan.get('jalons_dus', []):
        key, phase = item['course'], item['phase']
        deadline = instant(item.get('echeance'))
        if not deadline or phase not in PHASES:
            continue
        forecast = lire(cache/'ipr'/f'{key}.json')
        observed = instant(forecast.get('observation_utc'))
        calculated = instant(forecast.get('calcul_utc'))
        depart = instant(forecast.get('depart'))
        if (forecast.get('version') != VERSION or forecast.get('preparation') or not forecast.get('top3')
                or not depart or not observed or not calculated
                or not max(start, deadline-ANTICIPATION) <= observed <= calculated <= publication
                or publication >= min(depart, deadline+PHASES[phase])):
            continue
        expected = forecast['chevaux']
        actual = sheets.get('ipr', {}).get(key, {})
        if set(actual) != set(expected) or any(
            actual[n] is None or any(
                not meme_date_sheets(field, actual[n].get(field, ''), sheet_value(field, expected[n].get(field)))
                for field in IPR.libelles) for n in expected
        ):
            continue
        frozen = cache/'ipr'/'jalons'/f'{key}_{phase}_{VERSION}.json'
        if not frozen.exists():
            sauver(frozen, {'prevision': forecast, 'echeance_utc': deadline.isoformat(),
                           'publication_utc': publication.isoformat(), 'phase': phase})
        counts[key] = phase
    return counts


def podium_verifie(arrival, key, depart, now):
    checked = instant(arrival.get('verifie_utc'))
    if (arrival.get('source') != 'PMU_API_PARTICIPANTS' or not checked or not depart < checked <= now
            or f"{arrival.get('date')}_{arrival.get('course')}" != key):
        return None
    podium = [r for r in arrival.get('arrivee', []) if r.get('rang') in (1, 2, 3)]
    numbers = {r.get('numero') for r in podium}
    if {r['rang'] for r in podium} == {1, 2, 3} and len(numbers) == len(podium) == 3:
        return numbers
    return None


def mesurer(cache, now):
    from .experience_ml import paired_interval

    cache = Path(cache)
    details = []
    by_phase = defaultdict(list)
    for path in sorted((cache/'ipr'/'jalons').glob('*.json')):
        certificate = lire(path)
        forecast = certificate['prevision']
        day, code, phase = forecast['date'], forecast['course'], certificate['phase']
        key = f'{day}_{code}'
        depart, published = (instant(v) for v in (forecast['depart'], certificate['publication_utc']))
        if not depart or not published or published >= depart:
            continue
        podium = podium_verifie(lire(cache/'arrivees'/f'{key}.json'), key, depart, now)
        if not podium:
            continue
        scores = {'ipr': len(set(forecast['top3']) & podium)}
        proof = lire(cache/'jalons'/f'{key}.json').get(phase, {})
        comparators = proof.get('versions', {})
        for method in ('direct', 'ml'):
            try:
                evidence = comparators[method]
                doc, selected = prevision_publiee(cache, key, method, evidence, depart)
                read = instant(evidence.get('lecture_sheets_utc'))
                observed = instant(doc.get('donnees_observees_utc'))
                if (read != published or instant(proof.get('echeance')) != instant(certificate['echeance_utc'])
                        or observed != instant(forecast['observation_utc'])
                        or {str(r['numero']) for r in doc['classement_complet']} != set(forecast['partants'])):
                    continue
                scores[method] = len(selected & podium)
            except (KeyError, TypeError, ValueError):
                continue
        rows = forecast['chevaux']
        eligible = forecast['partants']
        evaluated = sum(rows[n]['ipr_score'] is not None for n in eligible)
        detail = {'course': key, 'phase': phase, 'version': forecast['version'],
                  'discipline': forecast['discipline'], 'depart_trot': forecast['mode_depart'],
                  'distance': forecast['distance'], 'scores': scores, 'partants': len(eligible),
                  'partants_notes': evaluated, 'preuve_sha256': sha256(path.read_bytes()).hexdigest()}
        details.append(detail)
        by_phase[phase, forecast['version']].append(detail)
    end = now.astimezone(PARIS).date()
    start = (end - timedelta(days=6)).isoformat()
    end = end.isoformat()
    weekly = [row for row in details if start <= row['course'][:10] <= end]
    aggregates = []
    for (phase, version), rows in sorted(by_phase.items()):
        rows = [r for r in rows if start <= r['course'][:10] <= end]
        if not rows:
            continue
        scores = {r['course']: r['scores']['ipr'] for r in rows}
        aggregate = {'phase': phase, 'version': version, 'courses': len(scores),
                     'moyenne_sur_3': sum(scores.values()) / len(scores),
                     'exact_3_sur_3': sum(value == 3 for value in scores.values()),
                     'taux_partants_notes': sum(r['partants_notes'] for r in rows) / sum(r['partants'] for r in rows),
                     'appariements': {method: paired_interval(scores, {
                         r['course']: r['scores'][method] for r in rows if method in r['scores']})
                         for method in ('direct', 'ml')}}
        segments = {}
        for field in ('discipline', 'depart_trot', 'distance'):
            groups = defaultdict(list)
            for row in rows:
                groups[str(row[field]) if row[field] else 'INCONNU'].append(row['scores']['ipr'])
            segments[field] = {label: {'courses': len(values), 'moyenne_sur_3': sum(values)/len(values)}
                               for label, values in groups.items()}
        aggregates.append({**aggregate, 'segments': segments})
    all_latest = [lire(path) for path in (cache/'ipr').glob('????-??-??_R*C*.json')]
    latest = [d for d in all_latest if start <= d.get('date', '') <= end and not d.get('preparation')]
    horses = [d['chevaux'][n] for d in latest for n in d['partants']]
    values = [h['ipr_score'] for h in horses if h.get('ipr_score') is not None]
    previous_start = (now.astimezone(PARIS).date() - timedelta(days=13)).isoformat()
    previous = [h['ipr_score'] for d in all_latest
                if previous_start <= d.get('date', '') < start and not d.get('preparation')
                for h in d['chevaux'].values() if h.get('ipr_score') is not None]
    last = max((instant(d['observation_utc']) for d in latest), default=None)
    return {'debut': start, 'fin': end, 'controle_utc': now.isoformat(), 'courses': weekly,
            'depuis_activation': len(details), 'agrege': aggregates, 'usage': IPR.usage,
            'suivi': {'courses': len(latest), 'partants': len(horses), 'scores': len(values),
                      'taux_calcul': len(values)/len(horses) if horses else None,
                      'dernier_releve_utc': last.isoformat() if last else None,
                      'mediane_score': median(values) if values else None,
                      'ecart_mediane_semaine_precedente': median(values)-median(previous) if values and previous else None,
                      'taux_manquants': {k: sum(h.get(k) is None for h in horses)/len(horses)
                                          for k in IPR.libelles} if horses else {}}}
