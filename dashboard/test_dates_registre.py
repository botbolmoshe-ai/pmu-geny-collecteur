from datetime import timedelta
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


    def test_plan_ne_touche_pas_aux_clefs_formules_et_indices(self):
        from pmu_geny.migration_dates_sheets import planifier

        def text(value):
            return {'userEnteredValue': {'stringValue': value}}

        headers = ['Clé course (technique)', 'Historique · Mise à jour UTC',
                   'IPR · Score', 'Date', 'Calcul']
        props = {'sheetId': 1, 'gridProperties': {'columnCount': 5}}
        stamp = '2026-10-25T02:15:04.123456+01:00'
        rows = {1: [text(label) for label in headers],
                2: [text('2026-10-25_R1C1'), text(stamp),
                    {'userEnteredValue': {'numberValue': 0.75}},
                    text('25/10/2026'), {'userEnteredValue': {'formulaValue': '=1+2'}}]}
        _, updates, ignored = planifier('Courses & Prévisions', props, rows)
        self.assertEqual(updates, {3: {2: vers_nombre('Date', '2026-10-25')}, 5: {
            1: 'Paris · Historique · Mise à jour', 2: nombre_paris(stamp)}})
        self.assertFalse(ignored)
        self.assertEqual(rows[2][1], text(stamp))
