from unittest import TestCase

from pmu_geny.formes_contextuelles_v32 import chronos_comparables


class ChronosComparablesTests(TestCase):
    def test_ne_retenient_que_les_sorties_proches_et_anterieures(self):
        course = {'depart': '2026-11-21T13:00:00+01:00', 'discipline': 'Attelé',
                  'hippodrome': 'Vincennes', 'distance_m': 2700}
        base = {'discipline': 'Attelé', 'hippodrome': 'Vincennes', 'distance_m': 2700,
                'classement': '3', 'chrono': "1'14''2"}
        history = {'performances': [
            {**base, 'date': '2026-11-10'},
            {**base, 'date': '2026-10-25', 'chrono': '1’15”8'.replace('”', '"')},
            {**base, 'date': '2026-11-21', 'chrono': "1'10''0"},
            {**base, 'date': '2026-11-09', 'classement': 'DAI'},
            {**base, 'date': '2026-11-08', 'chrono': "0'39''8"},
            {**base, 'date': '2026-11-07', 'distance_m': 2100},
            {**base, 'date': '2026-11-06', 'hippodrome': 'Enghien'},
            {**base, 'date': '2026-11-05', 'discipline': 'Monté'},
        ]}
        self.assertEqual(chronos_comparables(history, course), {
            'chrono_comparable_mediane_sec_km': 75.0, 'chrono_comparable_nb_sorties': 2,
        })
