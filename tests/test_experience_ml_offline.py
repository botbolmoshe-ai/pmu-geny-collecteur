import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from datetime import datetime, timezone

from pmu_geny.experience_ml import (
    evaluate, modeles, paired_interval, split_days,
    tester_profils_direct, tester_profils_ml,
)
from pmu_geny.ml_v19 import load, save, snapshot_pmu


class TestExperienceML(unittest.TestCase):
    def test_calendar_split_holds_out_whole_courses(self):
        rows = [{'course': day + '_R1C1', 'depart': day + 'T12:00:00+01:00', 'numero': n}
                for day in ['2026-11-13', '2026-11-14', '2026-11-15'] for n in [1, 2, 3]]
        a, b, c = split_days(rows, '2026-11-14', '2026-11-15')
        self.assertEqual([len(x) for x in (a, b, c)], [3, 3, 3])
        self.assertEqual({r['depart'][:10] for r in a}, {'2026-11-13'})
        with self.assertRaises(ValueError):
            split_days(rows, '2026-11-15', '2026-11-14')

    def test_top3_counts_by_race_and_breaks_ties_by_number(self):
        rows = [{'course': 'a', 'numero': n, 'y': int(n in [1, 2, 4])} for n in [4, 3, 2, 1]]
        report = evaluate(rows, [1, 1, 1, 1])
        self.assertEqual(report['selections']['a'], [1, 2, 3])
        self.assertEqual(report['chevaux_retrouves'], 2)
        self.assertEqual(paired_interval({'a': 2}, {'a': 1})['ecart_moyen'], 1)

    def test_profils_direct_isoles_sur_la_prevision_certifiee(self):
        with TemporaryDirectory() as folder:
            cache = Path(folder)
            course = '2026-11-15_R1C1'
            depart = '2026-11-15T15:00:00+01:00'
            rows = [{'course': course, 'depart': depart, 'numero': n,
                     'nom': f'Cheval {n}', 'y': int(n in (1, 4, 5))} for n in range(1, 6)]
            classement = [{'numero': r['numero'], 'nom': r['nom'], 'score_direct': 5} for r in rows]
            path = cache / 'pronostics' / f'{course}_direct.json'
            doc = {'date': '2026-11-15', 'course': 'R1C1', 'depart': depart,
                   'version_profils': 'trot-attele-v3', 'donnees_observees_utc': '2026-11-15T12:00:00+01:00',
                   'calcul_utc': '2026-11-15T12:01:00+01:00', 'classement_complet': classement,
                   'top3': [classement[i] for i in (3, 4, 0)],
                   'profils_partants': {'4': {'nom': 'Cheval 4', 'est_crack': True},
                                        '5': {'nom': 'Cheval 5', 'est_haut_potentiel': True}}}
            save(path, doc)
            certificat = cache / 'publications/direct' / f'{course}.json'
            preuve = {'fichier': str(path.relative_to(cache)), 'calcul_utc': doc['calcul_utc'],
                      'lecture_sheets_utc': '2026-11-15T12:02:00+01:00',
                      'publication_utc': '2026-11-15T12:03:00+01:00',
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            save(certificat, {'depart': depart, 'versions': {'direct': preuve}})
            rapport = tester_profils_direct(cache, rows)
            self.assertEqual(rapport['sans']['chevaux_retrouves'], 1)
            self.assertEqual(rapport['variantes']['est_crack']['chevaux_retrouves'], 2)
            self.assertEqual(rapport['variantes']['est_haut_potentiel']['chevaux_retrouves'], 2)
            self.assertEqual(rapport['variantes']['avec_les_deux']['chevaux_retrouves'], 3)
            save(certificat, {'depart': depart, 'versions': {'direct': {**preuve, 'publication_utc': depart}}})
            self.assertEqual(tester_profils_direct(cache, rows)['courses'], 0)

    def test_profils_ml_test_hors_apprentissage_et_valeurs_manquantes(self):
        groupes = []
        for course in ('train', 'validation', 'test'):
            groupes.append([
                {'course': course, 'numero': n, 'y': int(n >= 3),
                 'features': {'est_crack': int(n >= 3)}} for n in range(1, 6)])
        rapport = tester_profils_ml(modeles()['regression_logistique'], *groupes)
        self.assertEqual(rapport['sans']['chevaux_retrouves'], 1)
        self.assertEqual(rapport['variantes']['est_crack']['avec']['chevaux_retrouves'], 3)
        self.assertEqual(rapport['variantes']['est_haut_potentiel']['statut'], 'DONNEES_INSUFFISANTES')

    def test_snapshot_preserves_horse_name_and_immutability(self):
        with TemporaryDirectory() as folder:
            course = {'date': '2026-11-15', 'code': 'R1C1', 'depart': '2026-11-15T15:00:00+01:00',
                      'nombre_declares': 3, 'distance_m': 2100}
            raw = {'participants': [{'numPmu': n, 'nom': f'CHEVAL {n}', 'nonPartant': False,
                                     'musique': '1a2a3a', 'age': 5, 'sexe': 'HONGRES', 'ferrure': 'DEFERRE_DES_QUATRE_PIEDS'}
                                    for n in range(1, 4)]}
            now = datetime(2026, 11, 15, 11, tzinfo=timezone.utc)
            with patch('pmu_geny.liaison_chevaux_v22.etablir', return_value={}):
                self.assertEqual(snapshot_pmu(folder, course, raw, now), 'CAPTURE_PMU')
                path = Path(folder) / 'ml/instantanes/2026-11-15_R1C1.json'
                before = path.read_bytes()
                self.assertEqual([r['nom'] for r in load(path)['chevaux']], ['CHEVAL 1', 'CHEVAL 2', 'CHEVAL 3'])
                self.assertEqual(snapshot_pmu(folder, course, raw, now), 'DEJA_CAPTURE')
                self.assertEqual(before, path.read_bytes())


if __name__ == '__main__':
    unittest.main()
