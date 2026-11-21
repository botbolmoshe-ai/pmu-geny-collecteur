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


def matrix(rows, fields=FEATURES):
    return np.asarray([[numeric(r['features'].get(k)) if numeric(r['features'].get(k)) is not None
                        else np.nan for k in fields] for r in rows])


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



def evaluate_hybrid(rows, direct_scores, ml_scores):
    """Combiner les deux rangs à poids égaux sur le même relevé."""
    grouped = defaultdict(list)
    for index, row in enumerate(rows):
        grouped[row['course']].append(index)
    combined = np.zeros(len(rows))
    for indices in grouped.values():
        for scores in (direct_scores, ml_scores):
            ranked = sorted(indices, key=lambda index: (-scores[index], rows[index]['numero']))
            for rank, index in enumerate(ranked):
                combined[index] -= rank
    return evaluate(rows, combined)


def paired_interval(left, right):
    common = sorted(set(left) & set(right))
    if not common:
        return None
    delta = np.asarray([left[k] - right[k] for k in common])
    rng = np.random.default_rng(42)
    boot = np.concatenate([rng.choice(delta, size=(250, len(delta)), replace=True).mean(axis=1)
                           for _ in range(40)])
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



def tester_profils_ml(model, train, validation, test):
    """Comparer les ajouts sur les mêmes partants, hors entraînement."""
    from sklearn.base import clone
    from .profils_partants import SIGNAUX_PROFILS

    y_fit = [row['y'] for row in train + validation]
    reference = clone(model).fit(matrix(train + validation), y_fit)
    base = evaluate(test, reference.predict_proba(matrix(test))[:, 1])
    couverture = {}
    for nom, groupe in (('train', train), ('validation', validation), ('test', test)):
        couverture[nom] = {}
        for champ in SIGNAUX_PROFILS:
            valeurs = [row['features'].get(champ) for row in groupe]
            couverture[nom][champ] = {'positifs': valeurs.count(1), 'negatifs': valeurs.count(0),
                                      'non_evalues': valeurs.count(None)}
    variantes = {}
    for champs in [(champ,) for champ in SIGNAUX_PROFILS] + [SIGNAUX_PROFILS]:
        nom = '+'.join(champs)
        if not all(couverture[periode][champ]['positifs'] and couverture[periode][champ]['negatifs']
                   for periode in couverture for champ in champs):
            variantes[nom] = {'statut': 'DONNEES_INSUFFISANTES'}
            continue
        fields = FEATURES + champs
        trial = clone(model).fit(matrix(train + validation, fields), y_fit)
        mesure = evaluate(test, trial.predict_proba(matrix(test, fields))[:, 1])
        variantes[nom] = {'statut': 'EVALUE', 'avec': mesure,
                          'ecart': paired_interval(mesure['hits_par_course'], base['hits_par_course'])}
    return {'couverture': couverture, 'sans': base, 'variantes': variantes}


def tester_profils_direct(cache, test):
    """Isoler le départage sur les versions Direct certifiées et relues dans Sheets."""
    from .echeances_production import instant, lire
    from .liaison_chevaux_v22 import nom_normalise
    from .performance_prospective import prevision_publiee
    from .profils_partants import SIGNAUX_PROFILS

    fields = {'sans': (), **{champ: (champ,) for champ in SIGNAUX_PROFILS},
              'avec_les_deux': SIGNAUX_PROFILS}
    hits = {nom: {} for nom in fields}
    selections_modifiees = Counter()
    couverture = Counter()
    groupes = defaultdict(dict)
    for row in test:
        groupes[row['course']][row['numero']] = row
    for course, partants in groupes.items():
        depart = instant(next(iter(partants.values()))['depart'])
        certificat = (lire(cache / 'publications/direct' / f'{course}.json')
                      or lire(cache / 'publications' / f'{course}.json'))
        preuve = certificat.get('versions', {}).get('direct', {})
        lecture, publication = (instant(preuve.get(key))
                                for key in ('lecture_sheets_utc', 'publication_utc'))
        calcul = instant(preuve.get('calcul_utc'))
        if not (depart and calcul and lecture and publication and calcul <= lecture <= publication < depart):
            continue
        try:
            doc, top3_publie = prevision_publiee(cache, course, 'direct', preuve, depart)
            observation = instant(doc.get('donnees_observees_utc'))
            if (not observation or observation > calcul
                    or doc.get('version_profils') not in ('trot-attele-v2', 'trot-attele-v3')):
                continue
            classement = doc['classement_complet']
            podium = {n for n, row in partants.items() if row['y']}
            signaux = doc['profils_partants']
            if ({h['numero'] for h in classement} != partants.keys()
                    or any(not h.get('nom') or nom_normalise(h['nom']) != nom_normalise(
                        partants[h['numero']].get('nom')) for h in classement)):
                continue
            evaluations = {}
            etiquettes = {}
            for h in classement:
                n = h['numero']
                signal = signaux.get(str(n), {})
                if signal and nom_normalise(signal.get('nom')) != nom_normalise(h['nom']):
                    raise ValueError('Profil et partant incohérents')
                etiquettes[n] = tuple(champ for champ in SIGNAUX_PROFILS
                                      if signal.get(champ, bool(signal.get(champ.removeprefix('est_')))))
            for nom, colonnes in fields.items():
                def ordre(h):
                    priorite = max((2 if champ == 'est_crack' else 1
                                    for champ in colonnes if champ in etiquettes[h['numero']]), default=0)
                    return -h['score_direct'], -priorite, h['numero']

                evaluations[nom] = {h['numero'] for h in sorted(classement, key=ordre)[:3]}
            if evaluations['avec_les_deux'] != top3_publie:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        couverture.update(champ for valeurs in etiquettes.values() for champ in valeurs)
        for nom, selection in evaluations.items():
            hits[nom][course] = len(selection & podium)
            selections_modifiees[nom] += selection != evaluations['sans']
    resultats = {'courses': len(hits['sans']),
                 'positifs': {champ: couverture[champ] for champ in SIGNAUX_PROFILS}}
    if hits['sans']:
        resultats['sans'] = summary(hits['sans'])
        resultats['variantes'] = {
            nom: {**summary(hits[nom]), 'selections_modifiees': selections_modifiees[nom],
                  'ecart': paired_interval(hits[nom], hits['sans'])}
            for nom in fields if nom != 'sans'}
    resultats['statut'] = 'EVALUE' if any(couverture.values()) else 'DONNEES_INSUFFISANTES'
    return resultats


def run(cache, output, validation_day, test_day, now=None, *, select_research=False):
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
        return min(datetime.fromisoformat(r.get('observation_utc', r['capture_utc'])) for r in rows)
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
              'limites': ['Schémas historiques hétérogènes : variables non conservées laissées manquantes.',
                         'Scores non calibres: aucune probabilite de podium publiee.',
                         'Finalite officielle des arrivees non tracee par le collecteur actuel.',
                         'Le test est retrospectif et ne constitue pas une prediction live.',
                         'Le TOP3 direct publié est comparé uniquement si le même relevé et sa relecture Sheets sont prouvés.']}
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
    from .ml_v19 import DEPART_RESEARCH, FERRURE_RESEARCH
    report['ablation_validation'] = {}
    ablations = {**CRITERIA,
        'Historique comparable': ('forme_geny_comparable', 'courses_30j', 'courses_60j', 'courses_120j',
                                  'podiums_30j', 'podiums_120j', 'victoires_120j', 'disqualifications_120j',
                                  'score_forme', 'forme_30j', 'forme_ancien', 'jours_repos',
                                  'distance_ecart_m', 'aptitude_hippodrome', 'taux_podium_distance'),
        'Distance': ('distance_m', 'distance_ecart_m', 'taux_podium_distance', 'forme_geny_comparable'),
    }
    for criterion, keys in ablations.items():
        indices = [FEATURES.index(key) for key in keys if key in FEATURES]
        if not indices:
            continue
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
    research = {
        'Ferrure · même poids': (FERRURE_RESEARCH[0],),
        'Ferrure · écart modéré': (FERRURE_RESEARCH[1],),
        'Ferrure · coefficients actuels': (FERRURE_RESEARCH[2],),
        'Tandem cheval-driver': ('tandem_podium_lisse', 'tandem_courses'),
        'Avis PMU structuré': ('avis_pmu_structure',),
        **DEPART_RESEARCH,
    }
    report['variantes_validation'] = {}
    chosen_fields = FEATURES
    eligible = {}
    for name, additions in research.items():
        train_observed = sum(all(numeric(r['features'].get(k)) is not None for k in additions) for r in train)
        validation_observed = sum(all(numeric(r['features'].get(k)) is not None for k in additions) for r in validation)
        result = {'observations_train': train_observed, 'observations_validation': validation_observed}
        report['variantes_validation'][name] = result
        if not train_observed or not validation_observed:
            result['etat'] = 'DONNEES_INSUFFISANTES'
            continue
        fields = FEATURES + additions
        trial = clone(models[winner]).fit(matrix(train, fields), y_train)
        trial_scores = trial.predict_proba(matrix(validation, fields))[:, 1]
        evaluation = evaluate(validation, trial_scores)
        comparison = paired_interval(evaluation['hits_par_course'], validation_scores[winner]['hits_par_course'])
        result.update(etat='EVALUE', moyenne=evaluation['moyenne'], ecart_avec_reference=comparison,
                      couverture_par_discipline={discipline: sum(
                          row['features'].get('discipline_montee') == value
                          and all(numeric(row['features'].get(k)) is not None for k in additions)
                          for row in validation) for discipline, value in [('attelé', 0), ('monté', 1)]})
        if comparison['ic95_bootstrap_par_course'][0] > 0:
            eligible[name] = fields
    if select_research and eligible:
        best = max(eligible, key=lambda name: (report['variantes_validation'][name]['moyenne'], name))
        chosen_fields = eligible[best]
        report['variante_choisie_avant_test'] = best
    report['modele_choisi_avant_test'] = winner
    # Refit sur train et validation. Le test ne modifie aucun paramètre.
    model = models[winner]
    fitted_rows = train + validation
    qualified_fit = [row for row in fitted_rows if row['capture_qualifiante']]
    report['apprentissage_final'] = {**coverage(qualified_fit),
                                     'courses': len({r['course'] for r in qualified_fit}),
                                     'observations_totales': len(fitted_rows)}
    model.fit(matrix(fitted_rows, chosen_fields), [r['y'] for r in fitted_rows])
    scores = model.predict_proba(matrix(test, chosen_fields))[:, 1]
    report['test_ml'] = evaluate(test, scores)
    report['profils_partants'] = {
        'ml': tester_profils_ml(model, train, validation, test),
        'direct': tester_profils_direct(cache, test),
    }
    # Benchmark forme PMU au MEME instant de capture; limiter au sous-ensemble complet.
    by_course = defaultdict(list)
    for row in test:
        by_course[row['course']].append(row)
    comparable_ids = {course for course, rows in by_course.items()
                      if all(numeric(r['features'].get('pmu_score_direct')) is not None for r in rows)}
    if comparable_ids:
        comparable = [(row, score) for row, score in zip(test, scores) if row['course'] in comparable_ids]
        rows, ml_scores = zip(*comparable)
        direct_scores = [numeric(r['features']['pmu_score_direct']) for r in rows]
        direct = report['test_forme_pmu_capture'] = evaluate(rows, direct_scores)
        hybrid = report['test_hybride_rangs_egaux'] = evaluate_hybrid(rows, direct_scores, ml_scores)
        ml_hits = report['test_ml']['hits_par_course']
        report['ecart_ml_forme_capture'] = paired_interval(ml_hits, direct['hits_par_course'])
        report['ecart_hybride_forme_capture'] = paired_interval(hybrid['hits_par_course'], direct['hits_par_course'])
        report['ecart_hybride_ml'] = paired_interval(hybrid['hits_par_course'], ml_hits)
        report['test_comparable_par_discipline'] = {}
        for label, discipline in (('attelé', 0), ('monté', 1)):
            courses = {row['course'] for row in rows if row['features'].get('discipline_montee') == discipline}
            if courses:
                report['test_comparable_par_discipline'][label] = {
                    name: summary({course: hits[course] for course in sorted(courses)})
                    for name, hits in [('forme_capture', direct['hits_par_course']),
                                       ('ml', ml_hits), ('hybride', hybrid['hits_par_course'])]
                }
    from .echeances_production import instant, lire
    from .performance_prospective import retrouver
    published_hits = {}
    for course, rows in by_course.items():
        certificate = lire(cache / 'publications' / f'{course}.json')
        proof = certificate.get('versions', {}).get('direct', {})
        if not proof:
            continue
        doc = retrouver(cache, course, 'direct', proof)
        observed = instant(rows[0].get('observation_utc'))
        start = instant(rows[0]['depart'])
        published = instant(proof.get('publication_utc'))
        read = instant(proof.get('lecture_sheets_utc'))
        if (not doc or not observed or not read or not published or not start
                or instant(doc.get('donnees_observees_utc')) != observed
                or not observed <= read <= published < start):
            continue
        numbers = {int(h['numero']) for h in doc['top3']}
        if len(numbers) == 3:
            published_hits[course] = len(numbers & {r['numero'] for r in rows if r['y']})
    if published_hits:
        report['test_direct_publie'] = {**summary(published_hits), 'hits_par_course': published_hits}
        report['ecart_ml_direct_publie'] = paired_interval(report['test_ml']['hits_par_course'], published_hits)
    report['promotion_production'] = False
    joblib.dump({'model': model, 'features': chosen_fields, 'schema': MODEL_SCHEMA, 'statut': report['statut'],
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
