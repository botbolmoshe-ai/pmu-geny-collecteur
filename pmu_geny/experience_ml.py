"""Premier apprentissage local; aucune promotion ni reconstitution de features.

Le jeu test est un rejeu retrospectif, pas une prediction publiee avant course.
Les seuils de production de ml_v19 restent inchanges.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .ml_v19 import FEATURES, MODEL_SCHEMA, dataset, numeric, save


def split_days(records, validation_day, test_day):
    if not validation_day < test_day:
        raise ValueError('Validation strictement anterieure au test requise')
    train = [r for r in records if r['depart'][:10] < validation_day]
    validation = [r for r in records if r['depart'][:10] == validation_day]
    test = [r for r in records if r['depart'][:10] == test_day]
    if not all((train, validation, test)):
        raise ValueError('Trois periodes chronologiques non vides requises')
    ids = [{r['course'] for r in group} for group in (train, validation, test)]
    if any(ids[i] & ids[j] for i in range(3) for j in range(i)):
        raise ValueError('Course presente dans plusieurs periodes')
    if max(r['depart'] for r in train) >= min(r['depart'] for r in validation):
        raise ValueError('Ordre temporel train/validation invalide')
    if max(r['depart'] for r in validation) >= min(r['depart'] for r in test):
        raise ValueError('Ordre temporel validation/test invalide')
    return train, validation, test


def admissible(cache, as_of):
    """Valide les etiquettes et la chronologie sans modifier les captures."""
    records, _ = dataset(cache, now=as_of)
    accepted = {r['course'] for r in records}
    rejected = {p.stem: 'CAPTURE_OU_ARRIVEE_NON_ADMISSIBLE'
                for p in (cache / 'ml/instantanes').glob('*.json') if p.stem not in accepted}
    return records, rejected


def matrix(rows):
    return np.asarray([[numeric(r['features'].get(k)) if numeric(r['features'].get(k)) is not None
                        else np.nan for k in FEATURES] for r in rows])


def summary(hits):
    values = list(hits.values())
    return {'courses': len(values), 'chevaux_retrouves': sum(values),
            'moyenne': float(np.mean(values)),
            'au_moins_2_sur_3': sum(v >= 2 for v in values),
            'exact_3_sur_3': values.count(3),
            'distribution': dict(sorted(Counter(values).items()))}


def evaluate(rows, scores):
    grouped = defaultdict(list)
    for row, score in zip(rows, scores):
        grouped[row['course']].append((row, float(score)))
    hits, selections = {}, {}
    for course, ranked in grouped.items():
        selected = sorted(ranked, key=lambda item: (-item[1], item[0]['numero']))[:3]
        hits[course] = sum(row['y'] for row, _ in selected)
        selections[course] = [row['numero'] for row, _ in selected]
    return {**summary(hits), 'hits_par_course': hits, 'selections': selections}


def paired_interval(left, right):
    common = sorted(set(left) & set(right))
    if not common:
        return None
    delta = np.asarray([left[k] - right[k] for k in common])
    rng = np.random.default_rng(42)
    boot = rng.choice(delta, size=(10000, len(delta)), replace=True).mean(axis=1)
    return {'courses': len(common), 'ecart_moyen': float(delta.mean()),
            'ic95_bootstrap_par_course': np.quantile(boot, [0.025, 0.975]).tolist()}


def modeles():
    """Même définition déterministe pour l'évaluation et l'apprentissage actif."""
    return {
        'regression_logistique': make_pipeline(
            SimpleImputer(strategy='constant', fill_value=-1, add_indicator=True, keep_empty_features=True),
            StandardScaler(), LogisticRegression(max_iter=2000, class_weight='balanced', random_state=42)),
        'gradient_boosting': make_pipeline(
            SimpleImputer(strategy='constant', fill_value=-1, keep_empty_features=True),
            HistGradientBoostingClassifier(max_iter=120, max_leaf_nodes=9, l2_regularization=2, random_state=42)),
    }


def run(cache, output, validation_day, test_day, now=None):
    cache, output = Path(cache), Path(output)
    # Le modele experimental ne peut pas ecraser le modele ou statut de production.
    inside_source = output.resolve() == cache.resolve() or cache.resolve() in output.resolve().parents
    experiences = (cache / 'ml/experiences').resolve()
    if inside_source and experiences not in output.resolve().parents:
        raise ValueError('Sortie experimentale obligatoirement hors du cache source')
    output.mkdir(parents=True, exist_ok=True)
    as_of = now or datetime.now(timezone.utc)
    records, rejected = admissible(cache, as_of)
    train, validation, test = split_days(records, validation_day, test_day)
    def latest_label(rows):
        return max(datetime.fromisoformat(r['verifie_utc']) for r in rows)
    def earliest_capture(rows):
        return min(datetime.fromisoformat(r['capture_utc']) for r in rows)
    validation_cutoff = earliest_capture(validation)
    train = [row for row in train if datetime.fromisoformat(row['verifie_utc']) < validation_cutoff]
    if not train or len({r['y'] for r in train}) < 2:
        raise ValueError('Etiquettes train insuffisantes avant la première capture de validation')
    test_cutoff = earliest_capture(test)
    validation = [row for row in validation if datetime.fromisoformat(row['verifie_utc']) < test_cutoff]
    if not validation:
        raise ValueError('Etiquettes de validation indisponibles a la premiere capture test')
    report = {'statut': 'EXPERIMENTAL_NON_CALIBRE_NON_DEPLOYE', 'execute_utc': as_of.isoformat(),
              'nature_evaluation': 'REJEU_RETROSPECTIF_HORS_ECHANTILLON',
              'regle_selection': 'moyenne TOP3 validation decroissante, puis Brier croissant',
              'validation_day': validation_day, 'test_day': test_day,
              'courses_admissibles': len({r['course'] for r in records}),
              'dernier_label_entrainement_avant_test': latest_label(train + validation).isoformat(),
              'premiere_capture_test': earliest_capture(test).isoformat(),
              'lignes_admissibles': len(records), 'rejets': rejected,
              'decoupage': {label: {'courses': len({r['course'] for r in group}), 'lignes': len(group),
                                    'premier_depart': min(r['depart'] for r in group),
                                    'dernier_depart': max(r['depart'] for r in group)}
                           for label, group in [('train', train), ('validation', validation), ('test', test)]},
              'couverture_features': {k: sum(numeric(r['features'].get(k)) is not None for r in records)
                                      for k in FEATURES},
              'limites': ['Historique tres court, schemas v22.0/v22.1 heterogenes.',
                         'Scores non calibres: aucune probabilite de podium publiee.',
                         'Finalite officielle des arrivees non tracee par le collecteur actuel.',
                         'Le test est retrospectif et ne constitue pas une prediction live.',
                         'Le score PMU capture et le TOP3 direct publie peuvent utiliser des heures differentes.']}
    # Empreintes de toutes les sources utilisees: aucune variable reconstruite.
    report['sources_sha256'] = {str(f.relative_to(cache)): hashlib.sha256(f.read_bytes()).hexdigest()
                               for folder in ('ml/instantanes', 'arrivees')
                               for f in sorted((cache / folder).glob('*.json'))}
    models = modeles()
    x_train, x_validation = matrix(train), matrix(validation)
    y_train, y_validation = [r['y'] for r in train], [r['y'] for r in validation]
    validation_scores = {}
    for name, model in models.items():
        model.fit(x_train, y_train)
        score = model.predict_proba(x_validation)[:, 1]
        validation_scores[name] = {**evaluate(validation, score),
                                   'brier_score_brut': float(brier_score_loss(y_validation, score)),
                                   'log_loss_score_brut': float(log_loss(y_validation, score, labels=[0, 1]))}
    winner = min(models, key=lambda name: (-validation_scores[name]['moyenne'],
                                          validation_scores[name]['brier_score_brut'], name))
    report['validation'] = validation_scores
    from sklearn.base import clone
    from .maturite_ml import CRITERIA, coverage
    report['ablation_validation'] = {}
    ablations = {**CRITERIA,
        'Historique comparable': ('forme_geny_comparable', 'courses_30j', 'courses_60j', 'courses_120j',
                                  'podiums_30j', 'podiums_120j', 'victoires_120j', 'disqualifications_120j',
                                  'score_forme', 'forme_30j', 'forme_ancien', 'jours_repos',
                                  'distance_ecart_m', 'aptitude_hippodrome', 'taux_podium_distance'),
        'Distance': ('distance_m', 'distance_ecart_m', 'taux_podium_distance', 'forme_geny_comparable'),
    }
    for criterion, keys in ablations.items():
        indices = [FEATURES.index(key) for key in keys]
        if not np.isfinite(x_train[:, indices]).any() or not np.isfinite(x_validation[:, indices]).any():
            report['ablation_validation'][criterion] = {'etat': 'DONNEES_INSUFFISANTES'}
            continue
        train_masked, validation_masked = x_train.copy(), x_validation.copy()
        train_masked[:, indices] = np.nan
        validation_masked[:, indices] = np.nan
        ablated = clone(models[winner]).fit(train_masked, y_train)
        evaluation = evaluate(validation, ablated.predict_proba(validation_masked)[:, 1])
        report['ablation_validation'][criterion] = {
            'moyenne_sans_critere': evaluation['moyenne'],
            'ecart_avec_modele_complet': paired_interval(
                validation_scores[winner]['hits_par_course'], evaluation['hits_par_course']),
        }
    report['modele_choisi_avant_test'] = winner
    # Refit sur train+validation uniquement; la journee test reste inconnue du modele.
    model = models[winner]
    fitted_rows = train + validation
    qualified_fit = [row for row in fitted_rows if row['capture_qualifiante']]
    report['apprentissage_final'] = {**coverage(qualified_fit),
                                     'courses': len({r['course'] for r in qualified_fit}),
                                     'observations_totales': len(fitted_rows)}
    model.fit(matrix(fitted_rows), [r['y'] for r in fitted_rows])
    scores = model.predict_proba(matrix(test))[:, 1]
    report['test_ml'] = evaluate(test, scores)
    # Benchmark forme PMU au MEME instant de capture; limiter au sous-ensemble complet.
    by_course = defaultdict(list)
    for row in test:
        by_course[row['course']].append(row)
    comparable = [row for rows in by_course.values()
                  if all(numeric(r['features'].get('pmu_score_direct')) is not None for r in rows)
                  for row in rows]
    if comparable:
        report['test_forme_pmu_capture'] = evaluate(
            comparable, [r['features']['pmu_score_direct'] for r in comparable])
        report['ecart_ml_forme_capture'] = paired_interval(
            report['test_ml']['hits_par_course'], report['test_forme_pmu_capture']['hits_par_course'])
    published_hits = {}
    for course, rows in by_course.items():
        path = cache / 'pronostics' / f'{course}_direct.json'
        if not path.exists():
            continue
        doc = json.loads(path.read_text())
        stamp = datetime.fromisoformat(doc['calcul_utc'])
        depart = datetime.fromisoformat(rows[0]['depart'])
        numbers = [int(h['numero']) for h in doc.get('top3', [])]
        if stamp >= depart or len(set(numbers)) != 3:
            continue
        podium = {r['numero'] for r in rows if r['y']}
        published_hits[course] = len(set(numbers) & podium)
    if published_hits:
        report['test_direct_publie'] = {**summary(published_hits), 'hits_par_course': published_hits}
        report['ecart_ml_direct_publie'] = paired_interval(report['test_ml']['hits_par_course'], published_hits)
    report['promotion_production'] = False
    joblib.dump({'model': model, 'features': FEATURES, 'schema': MODEL_SCHEMA, 'statut': report['statut'],
                 'modele': winner, 'dernier_depart_entrainement': max(r['depart'] for r in fitted_rows),
                 'test_exclu_entrainement': test_day}, output / 'modele_experimental.joblib')
    save(output / 'rapport.json', report)
    save(output / 'scores_test.json', [{'course': r['course'], 'numero': r['numero'],
                                       'score_non_calibre': float(s), 'y': r['y']}
                                      for r, s in zip(test, scores)])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--sortie', required=True)
    parser.add_argument('--validation', required=True)
    parser.add_argument('--test', required=True)
    args = parser.parse_args()
    report = run(args.cache, args.sortie, args.validation, args.test)
    print(json.dumps({k: v for k, v in report.items() if k not in ('sources_sha256', 'validation')},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
