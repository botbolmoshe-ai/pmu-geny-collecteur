"""Comparer des enrichissements TOP3 sur des captures PMU déjà figées."""
import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import json
from pathlib import Path

import numpy as np

from pmu_geny.experience_ml import evaluate, matrix, modeles
from pmu_geny.ml_v19 import DEPART_RESEARCH, FEATURES, dataset, load, numeric

RELATIVE = ('forme_pmu_discipline', 'forme_geny_comparable', 'pmu_score_direct', 'gains_euros')
STRUCTURE = tuple(field for fields in DEPART_RESEARCH.values() for field in fields)


def ajouter_ecarts_medians(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row['course']].append(row)
    results = []
    for group in groups.values():
        medians = {}
        for field in RELATIVE:
            values = [value for r in group if (value := numeric(r['features'].get(field))) is not None]
            medians[field] = float(np.median(values)) if values else None
        for row in group:
            features = dict(row['features'])
            for field, median in medians.items():
                value = numeric(features.get(field))
                if value is not None and median is not None:
                    features[f'ecart_mediane_{field}'] = value - median
            results.append({**row, 'features': features})
    return results


def comparer(cache, first_test, as_of, published=None):
    cache = Path(cache)
    rows, _ = dataset(cache, now=as_of)
    rows = [row for row in rows if row['capture_qualifiante']]
    # La cohorte expérimentale exige la confirmation explicite du podium PMU.
    official = {}
    for key in {row['course'] for row in rows}:
        result = load(cache/'arrivees'/f'{key}.json', {})
        official[key] = result.get('podium_definitif_pmu') == [
            row['numero'] for row in sorted(result.get('arrivee', []), key=lambda r: r['rang'])
            if row['rang'] in (1, 2, 3)]
    rows = ajouter_ecarts_medians(row for row in rows if official[row['course']])
    test = [row for row in rows if row['depart'][:10] >= first_test]
    if not test:
        raise ValueError('Aucune capture test admissible')
    first_observed = min(datetime.fromisoformat(row['observation_utc']) for row in test)
    train = [row for row in rows if row['depart'][:10] < first_test
             and datetime.fromisoformat(row['verifie_utc']) < first_observed]
    if len({row['y'] for row in train}) < 2:
        raise ValueError('Apprentissage insuffisant avant le premier relevé test')
    relative = tuple(f'ecart_mediane_{field}' for field in RELATIVE)
    variants = {'logistique_reference': FEATURES, 'logistique_relative': FEATURES + relative,
                'logistique_depart': FEATURES + STRUCTURE,
                'logistique_relative_depart': FEATURES + relative + STRUCTURE}
    resultats = {}
    for name, fields in variants.items():
        model = modeles()['regression_logistique'].fit(matrix(train, fields), [row['y'] for row in train])
        resultats[name] = evaluate(test, model.predict_proba(matrix(test, fields))[:, 1])
    observed = {row['course']: row['observation_utc'] for row in test}
    published = published or {}
    common = {}
    for row in published.get('resultats', []):
        # Joindre les publications seulement si la même observation est prouvée.
        key = row['course']
        if key in observed and row.get('observation_utc') == observed[key]:
            common[key] = row['scores']
    return {'nature': 'EXPERIMENTATION_RETROSPECTIVE_NON_DEPLOYEE',
            'contrainte_etiquettes_avant_utc': first_observed.isoformat(),
            'train_courses': len({row['course'] for row in train}), 'test_courses': len(observed),
            'couverture_train': {field: sum(numeric(r['features'].get(field)) is not None for r in train)
                                 for field in (*RELATIVE, *STRUCTURE)},
            'couverture_test': {field: sum(numeric(r['features'].get(field)) is not None for r in test)
                                for field in (*RELATIVE, *STRUCTURE)},
            'variantes': resultats, 'publications_exactement_appariees': common}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cache', type=Path)
    parser.add_argument('debut_test', type=date.fromisoformat)
    args = parser.parse_args()
    report = comparer(args.cache, args.debut_test.isoformat(), datetime.now(timezone.utc),
                       load(args.cache/'ml/performance_prospective.json', {}))
    print(json.dumps(report, ensure_ascii=False, indent=2))
