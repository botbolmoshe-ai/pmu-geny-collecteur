import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from datetime import datetime, timezone

from pmu_geny.experience_ml import evaluate, paired_interval, split_days
from pmu_geny.ml_v19 import load, snapshot_pmu


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
