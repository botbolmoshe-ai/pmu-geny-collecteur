"""Auditer en lecture seule un checkpoint pmu-data et rejouer le score actif."""
import argparse
from collections import Counter
from pathlib import Path

from pmu_geny.cycle_ml_actif import POINTEUR, modele_actif, modele_disponible
from pmu_geny.echeances_production import PHASES, instant
from pmu_geny.experience_ml import evaluate, matrix, modeles, paired_interval, summary
from pmu_geny.ml_v19 import (
    ACTIVE_FEATURES, CHRONO_RESEARCH, DEPART_RESEARCH, FEATURES, FERRURE_RESEARCH,
    dataset, load, numeric, save,
)
from pmu_geny.performance_prospective import prevision_publiee
from pmu_geny.profils_partants import SIGNAUX_PROFILS


FAMILLES = {
    'autostart': tuple(field for group, fields in DEPART_RESEARCH.items()
                       if 'autostart' in group.lower() or group == 'Mode de départ et distance'
                       for field in fields),
    'recul': ('recul_depart_m',),
    'forme_meme_depart': DEPART_RESEARCH['Forme Geny par mode de départ'],
    'chronos': CHRONO_RESEARCH,
    'ferrures_historiques': (*FERRURE_RESEARCH, 'ferrures_historiques_comparees'),
    'tandem': ('tandem_podium_lisse', 'tandem_courses'),
    'avis_pmu': ('avis_pmu_structure',),
    'profils': SIGNAUX_PROFILS,
    'effectif_sorties_comparables': ('sorties_geny_comparables_120j',),
}


def couverture(rows):
    result = {}
    for field in ACTIVE_FEATURES:
        values = [numeric(row['features'].get(field)) for row in rows]
        present = [value for value in values if value is not None]
        result[field] = {'renseignees': len(present), 'absentes': len(values) - len(present),
                         'zeros': present.count(0), 'min': min(present, default=None),
                         'max': max(present, default=None)}
    return result


def rejeu(rows):
    variants = {'reference': FEATURES, 'enrichi': ACTIVE_FEATURES,
                **{f'sans_{name}': tuple(k for k in ACTIVE_FEATURES if k not in fields)
                   for name, fields in FAMILLES.items()}}
    hits = {name: {} for name in (*variants, 'forme_pmu')}
    folds = []
    for day in sorted({r['depart'][:10] for r in rows}):
        test = [r for r in rows if r['depart'][:10] == day]
        cutoff = min(instant(r['observation_utc']) for r in test)
        train = [r for r in rows if r['depart'][:10] < day and instant(r['verifie_utc']) < cutoff]
        n_train = len({r['course'] for r in train})
        if n_train < 20:
            continue
        folds.append({'jour': day, 'courses_train': n_train,
                      'courses_test': len({r['course'] for r in test}),
                      'partants_test': len(test), 'coupure_utc': cutoff.isoformat()})
        for name, fields in variants.items():
            algorithm = 'regression_logistique'
            model = modeles()[algorithm] if name == 'reference' else modele_actif(algorithm)
            model.fit(matrix(train, fields), [r['y'] for r in train])
            scores = model.predict_proba(matrix(test, fields))[:, 1].round(5)
            hits[name].update(evaluate(test, scores)['hits_par_course'])
        # Référence disponible sur chaque capture, distincte du Direct publié.
        scores = [r['features'].get('pmu_score_direct') for r in test]
        hits['forme_pmu'].update(evaluate(test, [-1 if x is None else x for x in scores])['hits_par_course'])
    return {'blocs': folds, 'familles': FAMILLES,
            'resultats': {name: {**summary(values),
                                 'hit_at_3': sum(v > 0 for v in values.values()) / len(values),
                                 'enrichi_moins_variante': paired_interval(hits['enrichi'], values)}
                          for name, values in hits.items() if values}}


def preuves_appariees(cache, entries, as_of, *, phase=None):
    direct, ml, rejects = {}, {}, Counter()
    for key, certificate in entries:
        arrival = load(cache / 'arrivees' / f'{key}.json', {})
        depart = instant(certificate.get('depart'))
        limite = depart
        if phase:
            reference = instant(certificate.get('reference_utc'))
            if not reference or instant(certificate.get('echeance')) != reference - PHASES[phase]:
                rejects['REFERENCE_JALON_NON_ATTESTEE'] += 1
                continue
            day, code = key.split('_', 1)
            programme = load(cache / 'sources_pmu' / f'programme_{day}.json', {})
            courses = programme.get('inventaire_reunions', programme.get('programme', []))
            departs = [instant(c.get('depart')) for c in courses if c.get('code') == code]
            depart = departs[0] if len(departs) == 1 else None
            limite = reference
        checked = instant(arrival.get('verifie_utc'))
        if not depart or not checked or checked > as_of:
            rejects['arrivee_non_disponible'] += 1
            continue
        if checked <= depart:
            rejects['arrivee_anterieure_ou_egale_au_depart'] += 1
            continue
        podium = [h for h in arrival.get('arrivee', []) if h.get('rang') in (1, 2, 3)]
        numbers = {h.get('numero') for h in podium}
        if (arrival.get('source') != 'PMU_API_PARTICIPANTS'
                or f"{arrival.get('date')}_{arrival.get('course')}" != key or len(podium) != len(numbers)
                or len(numbers) != 3 or {h['rang'] for h in podium} != {1, 2, 3}):
            rejects['arrivee_non_admissible'] += 1
            continue
        try:
            versions = certificate['versions']
            left, a = prevision_publiee(cache, key, 'direct', versions['direct'], depart)
            right, b = prevision_publiee(cache, key, 'ml', versions['ml'], depart)
            if phase and not all(
                (created := instant(proof.get('calcul_utc')))
                and (read := instant(proof.get('lecture_sheets_utc')))
                and created <= read <= instant(proof.get('publication_utc')) < limite
                for proof in (versions['direct'], versions['ml'])
            ):
                raise ValueError('LECTURE_SHEETS_NON_ATTESTEE')
            observation = instant(left.get('donnees_observees_utc'))
            if not observation or observation != instant(right.get('donnees_observees_utc')):
                raise ValueError('RELEVES_DIFFERENTS_OU_INCONNUS')
            if observation > min(instant(left['calcul_utc']), instant(right['calcul_utc'])):
                raise ValueError('RELEVE_POSTERIEUR_AU_CALCUL')
        except (KeyError, TypeError, ValueError) as exc:
            rejects[str(exc)] += 1
            continue
        direct[key], ml[key] = len(a & numbers), len(b & numbers)
    return {'paires': len(ml), 'rejets': dict(rejects),
            'direct': summary(direct) if direct else None, 'ml': summary(ml) if ml else None,
            'ml_moins_direct': paired_interval(ml, direct)}


def audit(cache, as_of, revision):
    rows, n = dataset(cache, as_of)
    qualified = [r for r in rows if r['capture_qualifiante']]
    by_course = {r['course']: r for r in rows}
    snapshots = {p.stem: load(p) for p in (cache / 'ml/instantanes').glob('*.json')}
    rejected = {}
    for key in sorted(set(snapshots) - set(by_course)):
        arrival = load(cache / 'arrivees' / f'{key}.json', {})
        checked = instant(arrival.get('verifie_utc'))
        rejected[key] = ('ARRIVEE_ABSENTE' if not arrival else 'ARRIVEE_POSTERIEURE_A_L_AUDIT'
                         if checked and checked > as_of else 'CAPTURE_OU_ARRIVEE_NON_ADMISSIBLE')
    published = [(p.stem, load(p)) for p in sorted((cache / 'publications').glob('*.json'))]
    phases = [(p.stem, load(p)) for p in sorted((cache / 'jalons').glob('*.json'))]
    prior = load(cache / 'ml/performance_prospective.json', {})
    arrivals = prior.get('resultats', [])
    pointer = load(cache / POINTEUR, {})
    return {
        'revision_pmu_data': revision, 'arrete_utc': as_of.isoformat(),
        'modele': {'modele_promu_present': (cache / 'ml/modele.joblib').is_file(),
                   'pointeur_experimental_verifie': modele_disponible(cache) is not None,
                   'pointeur_experimental': pointer},
        'captures': {'total': len(snapshots), 'admissibles': n, 'observations': len(rows),
                     'qualifiantes': len({r['course'] for r in qualified}),
                     'observations_qualifiantes': len(qualified),
                     'schemas_admis': dict(Counter(snapshots[k].get('features_schema') for k in by_course)),
                     'rejets': rejected, 'podiums_admis': sum(r['y'] for r in rows),
                     'liaisons_qualifiantes': dict(Counter(
                         h.get('methode_liaison', 'NON_RENSEIGNEE')
                         for k, r in by_course.items() if r['capture_qualifiante']
                         for h in snapshots[k]['chevaux']))},
        'distributions_qualifiantes': {field: dict(Counter(
            str(r['features'].get(field)) for r in qualified))
            for field in ('discipline_montee', 'distance_m', 'depart_autostart')},
        'couverture_toutes_observations': couverture(rows),
        'couverture_qualifiantes': couverture(qualified),
        'rejeu_chronologique': rejeu(rows),
        'prospectif_historique': {
            'nombre': len(arrivals),
            'empreintes_modeles': len({r.get('empreinte_modele') for r in arrivals}),
            'ml_moins_direct': paired_interval(
                {r['course']: r['scores']['ml'] for r in arrivals},
                {r['course']: r['scores']['direct'] for r in arrivals}),
            'horodatages_anormaux': [r['course'] for r in arrivals
                                    if not instant(r['depart']) < instant(r['arrivee_verifiee_utc']) <= as_of]},
        'prospectif_meme_releve': preuves_appariees(cache, published, as_of),
        'jalons_meme_releve': {phase: preuves_appariees(
            cache, [(key, doc[phase]) for key, doc in phases if phase in doc], as_of, phase=phase)
            for phase in PHASES},
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--arrete', type=instant, required=True)
    parser.add_argument('--sortie', type=Path, required=True)
    args = parser.parse_args()
    if args.arrete is None:
        parser.error('--arrete doit être horodaté avec fuseau')
    save(args.sortie, audit(args.cache, args.arrete, args.revision))
