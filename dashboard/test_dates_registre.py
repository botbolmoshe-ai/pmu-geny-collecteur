import unittest

from dashboard.trot_analytics.dates import EPOCH, afficher_source, nombre_paris, vers_nombre
from pmu_geny.dates_registre import projection


class DatesRegistreTests(unittest.TestCase):
    def test_instants_paris(self):
        for raw, wall in (
            ('2026-03-29T00:59:00Z', '2026-03-29T01:59'),
            ('2026-03-29T01:00:00Z', '2026-03-29T03:00'),
            ('2026-10-25T02:15:00+02:00', '2026-10-25T02:15'),
            ('2026-10-25T02:15:00+01:00', '2026-10-25T02:15'),
            ('2026-11-22T23:36:48.804558+00:00', '2026-11-23T00:36'),
            ('22/11/2026 23:36:48', '2026-11-23T00:36'),
        ):
            from datetime import timedelta
            with self.subTest(raw=raw):
                self.assertEqual((EPOCH + timedelta(days=nombre_paris(raw))).isoformat(timespec='minutes'),
                                 wall)
        self.assertEqual(nombre_paris('25/10/2026 02:15', utc=False), '25/10/2026 02:15')

    def test_dates_natives_et_vides(self):
        stamp = '2026-11-22T23:36:48.804558+00:00'
        self.assertAlmostEqual(projection('extraction_utc', vers_nombre('extraction_utc', stamp)),
                               nombre_paris(stamp), places=10)
        self.assertEqual(projection('heure_depart_paris', 46349.25), 46349.25)
        self.assertEqual(vers_nombre('Date', '22/11/2026'), vers_nombre('Date', '2026-11-22'))
        self.assertEqual(projection('historique_maj_utc', ''), '')
        self.assertEqual(projection('historique_maj_utc', None), '')

    def test_url_et_texte_source(self):
        url = 'https://example.com/2026-11-22?q=a%20b'
        self.assertEqual(afficher_source(url + ' · publié le 2026-11-22 · lu 2026-11-22T23:36:48Z'),
                         url + ' · publié le 22/11/2026 · lu 23/11/2026 00:36 (Paris)')
        self.assertEqual(afficher_source('14/11/26 | Vincennes | Monté'),
                         '14/11/26 | Vincennes | Monté')
