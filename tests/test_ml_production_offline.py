"""Contrats de production ML : temps, NP, extraction partagee et promotion."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import joblib
import numpy as np

from pmu_geny import cycle_ml
from pmu_geny.ml_v19 import (FEATURES, MODEL_SCHEMA, dataset, load, pmu_rows,
                            predict_pmu, save, snapshot_pmu, train)


class ProfileModel:
    def predict_proba(self, vectors):
        # Le test verifie que gains et age PMU arrivent vraiment au modele live.
        assert np.all(vectors[:, FEATURES.index('age_ans')] == 5)
        score = vectors[:, FEATURES.index('gains_euros')] / 100000
        return np.column_stack([1 - score, score])


class ProductionMLTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 11, 15, 11, tzinfo=timezone.utc)
        self.course = {'date': '2026-11-15', 'code': 'R1C1', 'depart': '2026-11-15T15:00:00+01:00',
                       'nombre_declares': 4, 'distance_m': 2100}
        self.raw = {'participants': [{'numPmu': n, 'nom': f'CHEVAL {n}', 'nonPartant': False,
                                     'musique': '1a2a3a', 'age': 5, 'sexe': 'HONGRES',
                                     'gainsCarriere': n * 10000, 'ferrure': 'D4'} for n in range(1, 5)]}

    def model(self, **extra):
        path = self.root / 'ml/modele.joblib'
        path.parent.mkdir(parents=True, exist_ok=True)
        packed = {'model': ProfileModel(), 'features': FEATURES, 'schema': MODEL_SCHEMA,
                  'modele': 'test', 'statut': 'ML_ENTRAINE_NON_CALIBRE', **extra}
        joblib.dump(packed, path)
        return path

    def examples(self):
        for day in ['2026-11-12', '2026-11-13', '2026-11-14']:
            key = day + '_R1C1'
            save(self.root / 'ml/instantanes' / (key + '.json'), {
                'date': day, 'code': 'R1C1', 'depart': day + 'T12:00:00+00:00',
                'capture_utc': day + 'T10:00:00+00:00',
                'features_schema': MODEL_SCHEMA, 'source': 'PMU_API_PARTICIPANTS',
                'chevaux': [{'numero': n, 'features': {'pmu_score_direct': n}} for n in range(1, 5)]})
            save(self.root / 'arrivees' / (key + '.json'), {
                'date': day, 'course': 'R1C1', 'source': 'PMU_API_PARTICIPANTS', 'verifie_utc': day + 'T13:00:00+00:00',
                'arrivee': [{'numero': n, 'rang': n} for n in [1, 2, 3]]})

    def test_capture_and_inference_use_same_profiles_without_geny(self):
        self.model()
        for n, partant in enumerate(self.raw['participants'], 1):
            partant.update(nomCheval={'nom': f'CHEVAL {n}'}, nom=f'Autre libellé {n}',
                           driver=f'Driver {n}', entraineur=f'Entraîneur {n}')
        self.assertEqual(snapshot_pmu(self.root, self.course, self.raw, self.now), 'CAPTURE_PMU')
        snap_path = self.root / 'ml/instantanes/2026-11-15_R1C1.json'
        before = snap_path.read_bytes()
        rows = pmu_rows(self.root, self.course, self.raw, self.now)[1]
        self.assertEqual([h['features'] for h in load(snap_path)['chevaux']], [h['features'] for h in rows])
        self.assertEqual(predict_pmu(self.root, self.course, self.raw, self.now), 'ML_CALCULE')
        doc = load(self.root / 'pronostics/2026-11-15_R1C1_ml_latest.json')
        self.assertEqual([(h['numero'], h['nom']) for h in doc['top3']],
                         [(4, 'CHEVAL 4'), (3, 'CHEVAL 3'), (2, 'CHEVAL 2')])
        self.assertEqual([h['nom'] for h in load(snap_path)['chevaux']],
                         [f'CHEVAL {n}' for n in range(1, 5)])
        self.raw['participants'][3]['nonPartant'] = True
        self.assertEqual(predict_pmu(self.root, self.course, self.raw, self.now + timedelta(minutes=1)), 'ML_CALCULE')
        doc = load(self.root / 'pronostics/2026-11-15_R1C1_ml_latest.json')
        self.assertEqual([h['numero'] for h in doc['top3']], [3, 2, 1])
        self.assertEqual(snap_path.read_bytes(), before)
        self.assertEqual(len(list((self.root / 'pronostics/versions').glob('*.json'))), 1)

    def test_experimental_or_obsolete_models_are_never_used(self):
        self.model(statut='EXPERIMENTAL_NON_CALIBRE_NON_DEPLOYE')
        self.assertEqual(predict_pmu(self.root, self.course, self.raw, self.now), 'MODELE_NON_PROMU')
        self.model(schema='v19.1')
        self.assertEqual(predict_pmu(self.root, self.course, self.raw, self.now), 'MODELE_SCHEMA_OBSOLETE_REENTRAINEMENT_REQUIS')

    def test_existing_experimental_model_serves_during_schema_transition(self):
        from pmu_geny.cycle_ml_actif import POINTEUR, STATUT
        from pmu_geny.maturite_ml import sha
        from pmu_geny.ml_v19 import LEGACY_FEATURES

        path = self.root / 'ml/modeles_experimentaux/precedent/modele.joblib'
        path.parent.mkdir(parents=True)
        joblib.dump({'model': ProfileModel(), 'features': LEGACY_FEATURES,
                     'schema': 'pmu-podium-v33', 'modele': 'test', 'statut': STATUT,
                     'entrainement_utc': '2026-11-14T16:00:00+00:00',
                     'dernier_label_entrainement_utc': '2026-11-14T15:00:00+00:00'}, path)
        save(self.root / POINTEUR, {'statut': STATUT, 'fichier_modele': str(path.relative_to(self.root)),
                                   'sha256_modele': sha(path)})
        self.assertEqual(predict_pmu(self.root, self.course, self.raw, self.now), 'ML_EXPERIMENTAL_CALCULE')
        doc = load(self.root/'pronostics/2026-11-15_R1C1_ml_latest.json')
        self.assertEqual(doc['features_schema'], 'pmu-podium-v33')
        self.assertEqual([row['numero'] for row in doc['top3']], [4, 3, 2])

    def test_live_gates_and_unknown_np(self):
        self.model()
        for stamp in ['2026-11-14T12:00:00+01:00',
                      '2026-11-15T15:00:00+01:00', '2026-11-15T21:01:00+01:00']:
            self.assertEqual(predict_pmu(self.root, self.course, self.raw, datetime.fromisoformat(stamp)), 'HORS_FENETRE_DECISION')
        del self.raw['participants'][0]['nonPartant']
        self.assertEqual(predict_pmu(self.root, self.course, self.raw, self.now), 'NP_NON_VERIFIE')
        self.assertFalse((self.root / 'pronostics').exists())

    def test_premier_calcul_ml_possible_des_le_debut_du_jour(self):
        self.model()
        early=datetime.fromisoformat('2026-11-15T00:05:00+01:00')
        self.assertEqual(predict_pmu(self.root,self.course,self.raw,early),'ML_CALCULE')

    def test_dataset_rejects_future_labels_missing_podium_and_unknown_np(self):
        self.examples()
        self.assertEqual(dataset(self.root, self.now)[1], 3)
        path = self.root / 'ml/instantanes/2026-11-12_R1C1.json'
        doc = load(path); doc['np_non_verifies'] = 1; save(path, doc)
        path = self.root / 'ml/instantanes/2026-11-13_R1C1.json'
        doc = load(path); doc['chevaux'][2]['numero'] = 5; save(path, doc)
        path = self.root / 'arrivees/2026-11-14_R1C1.json'
        doc = load(path); doc['verifie_utc'] = '2026-11-16T12:00:00+00:00'; save(path, doc)
        self.assertEqual(dataset(self.root, self.now), ([], 0))

    def test_malformed_records_do_not_abort_the_batch(self):
        self.examples()
        path = self.root / 'ml/instantanes/2026-11-12_R1C1.json'
        save(path, ['format invalide'])
        self.assertEqual(dataset(self.root, self.now)[1], 2)

    def test_connections_use_only_prior_labels_and_same_discipline(self):
        from pmu_geny.ml_v19 import scores_intervenants
        self.examples()
        for path in (self.root/'ml/instantanes').glob('*.json'):
            doc = load(path)
            for row in doc['chevaux']:
                row['features']['discipline_montee'] = int(doc['date'] == '2026-11-14')
                row['intervenants_pmu'] = {'entraineur_score': 'DUPONT'}
            save(path, doc)
        self.assertEqual(scores_intervenants(self.root, self.now, 'm'), {})
        self.assertEqual(scores_intervenants(self.root, self.now, 'a'),
                         {('entraineur_score', 'DUPONT'): 7/13})
        earlier = datetime.fromisoformat('2026-11-13T12:30:00+00:00')
        self.assertEqual(scores_intervenants(self.root, earlier, 'a'), {})

    def prospective_candidate(self):
        from pmu_geny.maturite_ml import CANDIDATE, sha, thresholds
        artifact = self.root / 'ml/staged.joblib'
        artifact.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({'model': ProfileModel(), 'features': FEATURES, 'schema': MODEL_SCHEMA,
                     'statut': 'ML_ENTRAINE_NON_CALIBRE', 'modele': 'test'}, artifact)
        digest = sha(artifact)
        path = self.root / 'ml/candidats' / digest / 'modele.joblib'
        path.parent.mkdir(parents=True, exist_ok=True)
        artifact.replace(path)
        limits = thresholds()
        for limit in limits.values():
            limit.update(courses=1, observations=1, prospectives=2)
        candidate = {'sha256': digest, 'modele': 'test', 'seuils': limits, 'rapport': 'test',
                     'entrainement_utc': '2026-11-14T15:00:00+00:00',
                     'dernier_label_entrainement_utc': '2026-11-14T14:00:00+00:00',
                     'apprentissage_final': {}}
        save(self.root / CANDIDATE, candidate)
        return candidate

    def test_candidate_waits_for_prospective_evidence(self):
        self.prospective_candidate()
        path = self.model()
        before = path.read_bytes()
        status = train(self.root, now=self.now)
        self.assertEqual(status['etat'], 'EVALUATION_PROSPECTIVE')
        self.assertEqual(status['prospective']['courses'], 0)
        self.assertFalse(status['promotion_production'])
        self.assertEqual(path.read_bytes(), before)

    def test_prospective_decision_keeps_or_promotes_exact_candidate(self):
        from pmu_geny.maturite_ml import sha
        self.examples()
        path = self.model()
        before = path.read_bytes()
        for advantage in (False, True):
            with self.subTest(advantage=advantage):
                candidate = self.prospective_candidate()
                result = [{'course': str(n), 'scores': {'direct': 2, 'ml': 3 if advantage else 2},
                           'couverture': {'observations': 4, 'completes': 4}} for n in range(2)]
                with patch('pmu_geny.maturite_ml.comparisons', return_value=result), \
                     patch('pmu_geny.maturite_ml.coverage', return_value={'completude': 1}):
                    status = train(self.root, now=self.now)
                self.assertEqual(status['promotion_production'], advantage)
                if advantage:
                    self.assertEqual(sha(path), candidate['sha256'])
                    self.assertEqual(load(self.root/'ml/preuve_promotion.json')['preuve'], result)
                else:
                    self.assertEqual(path.read_bytes(), before)

    def test_shadow_requires_same_observation_and_a_certified_predeparture_publication(self):
        from pmu_geny.echeances_production import enregistrer_publication
        from pmu_geny.maturite_ml import comparisons, score_shadow
        from pmu_geny.top3_independants_v22 import calculer

        candidate = self.prospective_candidate()
        key = self.course['date'] + '_R1C1'
        save(self.root/'sources_pmu'/f"programme_{self.course['date']}.json", {'programme': [self.course]})
        save(self.root/'partants_actuels'/f'{key}.json', {
            'capture_utc': self.now.isoformat(),
            'chevaux': {str(n): {'statut_np': 'PARTANT'} for n in range(1, 5)},
        })
        calculer(self.root, self.course, self.raw, now=self.now)
        score_shadow(self.root, self.course, self.raw, self.now + timedelta(seconds=1), lambda: self.now)
        target = self.root/'ml/prospectif'/candidate['sha256']/f'{key}.json'
        self.assertFalse(target.exists())
        score_shadow(self.root, self.course, self.raw, self.now, lambda: self.now)
        self.assertTrue(target.exists())
        checked = self.now + timedelta(hours=5)
        save(self.root/'arrivees'/f'{key}.json', {
            'source': 'PMU_API_PARTICIPANTS', 'verifie_utc': checked.isoformat(),
            'arrivee': [{'numero': n, 'rang': rank} for rank, n in enumerate((4, 3, 2), 1)],
        })
        enregistrer_publication(self.root, self.now, {'mode': 'GLOBAL'}, False)
        self.assertEqual(comparisons(self.root, candidate, checked), [])
        direct = load(self.root/'pronostics'/f'{key}_direct.json')
        enregistrer_publication(self.root, self.now, {'mode': 'GLOBAL'}, True, sheets={
            'lecture_utc': self.now.isoformat(),
            'courses': {key: {'direct': {'calcul_utc': direct['calcul_utc'],
                                        'numeros': [horse['numero'] for horse in direct['top3']]}}},
        })
        self.assertEqual(comparisons(self.root, candidate, checked)[0]['scores'], {'direct': 2, 'ml': 3})
        payload = load(target)
        payload['ml'] = [1, 2, 3]
        save(target, payload)
        self.assertEqual(comparisons(self.root, candidate, checked), [])

    def test_production_thresholds_are_not_lowered(self):
        self.examples()
        with patch('pmu_geny.experience_ml.run') as experiment:
            status = train(self.root, now=self.now)
        self.assertEqual((status['etat'], status['minimum_courses'], status['minimum_lignes']), ('INSUFFISANT', 150, 1500))
        self.assertEqual(status['seuils']['PRODUCTION']['prospectives'], 100)
        experiment.assert_not_called()

    def test_direct_failure_does_not_block_pmu_ml_capture(self):
        from pmu_geny.auto_v18 import run
        course = {**self.course, 'nom': 'PRIX TEST', 'hippodrome': 'VINCENNES'}
        with patch('pmu_geny.auto_v18.get_json', return_value=self.raw), \
             patch('pmu_geny.auto_v18.programme_diagnostic', return_value=([course], {})), \
             patch('pmu_geny.contexte_meteo_v20.collecter_meteo', return_value='TEST'), \
             patch('pmu_geny.sources_experts_v23.collecter', return_value='TEST'), \
             patch('pmu_geny.top3_independants_v22.calculer', side_effect=ValueError('direct indisponible')), \
             patch('pmu_geny.historiques_incrementaux.alimenter'), patch('builtins.print'):
            state = run(self.root, course['date'], [], 0, max_discoveries=0, now=self.now)
        entry = state['courses']['R1C1']
        self.assertEqual(entry['statut_snapshot_ml'], 'CAPTURE_PMU')
        self.assertEqual(entry['statut_ml'], 'ML_NON_ENTRAINE')
        self.assertIn('direct indisponible', entry['erreur_paliers_independants'])


class DailyMLTests(unittest.TestCase):
    def test_delayed_cron_and_dataset_fingerprint(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            now = datetime.fromisoformat('2026-11-15T20:45:00+01:00')
            with patch('pmu_geny.cycle_ml.train', return_value={'etat': 'INSUFFISANT'}) as training:
                self.assertEqual(cycle_ml.run(root, now)['etat'], 'INSUFFISANT')
                self.assertEqual(cycle_ml.run(root, now + timedelta(hours=1))['etat'], 'DEJA_TRAITE')
                save(root / 'arrivees/new.json', {'nouveau': True})
                self.assertEqual(cycle_ml.run(root, now + timedelta(hours=1))['etat'], 'INSUFFISANT')
                self.assertEqual(training.call_count, 2)

    def test_timezone_summer_winter_and_force_preserves_training_gate(self):
        with TemporaryDirectory() as folder:
            with patch('pmu_geny.cycle_ml.train', return_value={'etat': 'INSUFFISANT'}) as training:
                for stamp in ['2026-07-15T17:59:00+00:00', '2026-11-15T18:59:00+00:00']:
                    self.assertEqual(cycle_ml.run(folder, datetime.fromisoformat(stamp))['etat'], 'PROMOTION_DIFFEREE_20H_PARIS')
                training.assert_not_called()
                self.assertEqual(cycle_ml.run(folder, datetime.fromisoformat('2026-07-15T18:45:00+00:00'))['etat'], 'INSUFFISANT')
                self.assertEqual(cycle_ml.run(folder, datetime.fromisoformat('2026-11-15T19:45:00+00:00'))['etat'], 'INSUFFISANT')
                cycle_ml.run(folder, datetime.fromisoformat('2026-11-15T10:00:00+00:00'), force=True)
                self.assertEqual(training.call_count, 3)

    def test_failed_attempt_can_resume(self):
        with TemporaryDirectory() as folder:
            now = datetime.fromisoformat('2026-11-15T22:00:00+01:00')
            with patch('pmu_geny.cycle_ml.train', side_effect=RuntimeError('interruption')):
                with self.assertRaises(RuntimeError):cycle_ml.run(folder, now)
            self.assertFalse((Path(folder) / 'ml/cycle.json').exists())


if __name__ == '__main__':
    unittest.main()
