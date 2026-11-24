"""Évalue les candidats Geny hors ligne, sur les mêmes partants que chaque référence."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path

from .echeances_production import instant, lire
from .experience_ml import evaluate, matrix, paired_interval
from .ml_v19 import ACTIVE_FEATURES, dataset
from .cycle_ml_actif import modele_actif
from .liaison_chevaux_v22 import nom_normalise
from .signaux_geny import FIELDS, ajustement, signaux


def indexer_captures(cache, ids):
    index = {}
    for ident in ids:
        paths = [cache / folder / ident / 'historique_geny.json'
                 for folder in ('historiques', 'historiques_partiels')]
        paths.extend(sorted((cache / 'historiques_versions' / ident).glob('*.json')))
        for path in paths:
            doc = lire(path)
            stamp = instant(doc.get('extrait_utc'))
            if stamp:
                key = ident, stamp, doc.get('source_url')
                other = index.setdefault(key, doc)
                if other.get('performances') != doc.get('performances'):
                    index[key] = {}
    return index


def reconstruire(cache, rows):
    captures = indexer_captures(cache, {r['cheval_id'] for r in rows if r['cheval_id']})
    groups = defaultdict(list)
    for row in rows:
        groups[row['course']].append(row)
    for key, group in groups.items():
        day, code = key.split('_')
        snapshot = lire(cache / 'ml/instantanes' / f'{key}.json')
        individuals = {int(h['numero']): h for h in snapshot['chevaux']}
        observation = instant(group[0]['observation_utc'])
        programme = lire(cache / 'sources_pmu' / f'programme_{day}.json')
        programme_stamp = instant(programme.get('date_controle_utc'))
        course = {}
        if programme_stamp and programme_stamp <= observation:
            course = next((r for r in programme.get('programme', [])
                           if r.get('date') == day and r.get('code') == code
                           and instant(r.get('depart')) == instant(group[0]['depart'])), {})
        for row in group:
            h = individuals[row['numero']]
            features = row['features']
            available = {field: features[field] for field in FIELDS if field in features}
            if available or not row['capture_qualifiante']:
                row['geny'] = available
                continue
            stamp = instant(h.get('historique_extrait_utc'))
            hist = captures.get((row['cheval_id'], stamp, h.get('source_historique')), {})
            info = {**course, 'depart': row['depart'], 'distance_m': features.get('distance_m')}
            if features.get('discipline_montee') in (0, 1):
                info['discipline'] = 'm' if features['discipline_montee'] else 'a'
            if features.get('depart_autostart') == 1:
                info['parametres_pmu'] = {**info.get('parametres_pmu', {}), 'typeDepart': 'Auto'}
            row['geny'] = signaux(info, {'driver_jockey': row['intervenants_pmu'].get('driver_score')},
                                  {'historique': hist, 'cheval_id': row['cheval_id'],
                                   'methode': h.get('methode_liaison')}, observation)
    return groups


def rejouer_classements(cache, groups, mode):
    hits = {}
    for key, rows in groups.items():
        if mode == 'direct':
            paths = [cache/'pronostics'/f'{key}_direct.json',
                     *(cache/'pronostics/versions').glob(f'{key}_direct_*.json'),
                     *(cache/'jalons'/key).glob('*_direct_*.json')]
        else:
            paths = [cache/'ipr'/f'{key}.json', *(cache/'ipr/versions'/key).rglob('*.json')]
        observation = instant(rows[0]['observation_utc'])
        depart = instant(rows[0]['depart'])
        by_number = {row['numero']: row for row in rows}
        for path in paths:
            doc = lire(path)
            observed = instant(doc.get('donnees_observees_utc') if mode == 'direct' else doc.get('observation_utc'))
            calculated = instant(doc.get('calcul_utc'))
            if observed != observation or not calculated or not observed <= calculated < depart:
                continue
            if mode == 'direct':
                ranking = [(r['numero'], r.get('score_direct'), r.get('nom')) for r in doc.get('classement_complet', [])]
                baseline = [r['numero'] for r in doc.get('top3', [])]
            else:
                if doc.get('preparation') or {int(n) for n in doc.get('partants', [])} != set(by_number):
                    continue
                ranking = [(int(n), doc['chevaux'][n].get('ipr_score'), doc['chevaux'][n].get('nom')) for n in doc['partants']]
                ranking = [(n, score / 20 if score is not None else None, name) for n, score, name in ranking]
                baseline = doc.get('top3', [])
            if (len(baseline) != 3 or len(set(baseline)) != 3 or not set(baseline) <= by_number.keys()
                    or any(n not in by_number or nom_normalise(name) != nom_normalise(by_number[n]['nom'])
                           for n, _, name in ranking)
                    or (mode == 'direct' and {n for n, _, _ in ranking} != set(by_number))):
                continue
            ranking = [(n, score) for n, score, _ in ranking if score is not None]
            if len(ranking) < 3:
                continue
            if mode == 'ipr':
                order = {n: r['ipr_rang_shadow'] for n, r in
                         ((int(n), doc['chevaux'][n]) for n in doc['partants'])}
                ranking.sort(key=lambda r: order[r[0]])
            frozen = doc.get('candidat_geny') or {}
            selected = frozen.get('top3', [])
            ranked_numbers = {number for number, _ in ranking}
            if not (frozen.get('version') == 'geny-contexte-v1'
                    and len(selected) == len(set(selected)) == 3 and set(selected) <= ranked_numbers):
                if not any(by_number[n]['geny'] for n, _ in ranking):
                    continue
                trial = sorted(ranking, key=lambda item: -(
                    item[1] + ajustement(by_number[item[0]]['geny'], item[1])))
                selected = [n for n, _ in trial[:3]]
            hits[key] = [sum(by_number[n]['y'] for n in baseline),
                         sum(by_number[n]['y'] for n in selected)]
            break
    return hits


def rejouer_ml(rows):
    by_day = defaultdict(list)
    for row in rows:
        by_day[row['course'][:10]].append(row)
    hits = {}
    baseline = ACTIVE_FEATURES
    for day, group in sorted(by_day.items()):
        cutoff = min(instant(r['observation_utc']) for r in group)
        train = [r for r in rows if r['course'][:10] < day and instant(r['verifie_utc']) < cutoff]
        if len({r['course'] for r in train}) < 20:
            continue
        fields = tuple(f for f in FIELDS if len({r['geny'][f] for r in train if f in r['geny']}) >= 2)
        if not fields:
            continue
        supported = {r['course'] for r in group if any(f in r['geny'] for f in fields)}
        test = [r for r in group if r['course'] in supported]
        if not test:
            continue
        for r in train + test:
            r['features'] = {**r['features'], **r['geny']}
        scores = []
        for spec in (baseline, baseline + fields):
            model = modele_actif('regression_logistique')
            model.fit(matrix(train, spec), [r['y'] for r in train])
            scores.append(evaluate(test, model.predict_proba(matrix(test, spec))[:, 1])['hits_par_course'])
        hits.update({key: [scores[0][key], scores[1][key]] for key in supported})
    return hits


def bilan(cache, now):
    rows, _ = dataset(cache, now)
    rows = [r for r in rows if r['capture_qualifiante']]
    groups = reconstruire(cache, rows)
    measures = {mode: rejouer_classements(cache, groups, mode) for mode in ('direct', 'ipr')}
    measures['ml'] = rejouer_ml(rows)
    common = set.intersection(*(set(results) for results in measures.values()))

    def summary(results):
        reference = {k: value[0] for k, value in results.items()}
        candidate = {k: value[1] for k, value in results.items()}
        return {'courses': len(results), 'podiums_reference': sum(reference.values()),
                'podiums_candidat': sum(candidate.values()), 'appariement': paired_interval(candidate, reference)}

    return {'courses_admissibles': len(groups), 'partants_admissibles': len(rows),
            'observations_par_variable': {
                field: sum(field in row['geny'] for row in rows) for field in FIELDS},
            'par_mode': {mode: summary(result) for mode, result in measures.items()},
            'courses_communes': len(common),
            'comparaison_commune': {mode: summary({k: result[k] for k in common}) for mode, result in measures.items()}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--coupure', type=instant, default=datetime.now(timezone.utc))
    args = parser.parse_args()
    print(json.dumps(bilan(args.cache, args.coupure), ensure_ascii=False, indent=2))
