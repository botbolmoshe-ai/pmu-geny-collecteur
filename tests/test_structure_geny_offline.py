import unittest

from pmu_geny.collecte_geny_v4 import parse_career
from pmu_geny.migration_geny import plages_migration, planifier, verifier
from pmu_geny.structure_geny import structurer
from pmu_geny.sync_google_sheets import plan_sheet

MONTÉ = "14/11/26 | Vincennes | Monté | 2 175 | GP | G | - | Dur | Crse D | 46 000 € | A. Gendrot | 1'13''0 | 6 | e"
ENGHIEN = "11/08/24 | Enghien | Attelé | 2 150 | G | Auto | Dur | Crse F | 12 000 € | J-M. Lesne | 6.6 | Dai"
URL = 'https://www.geny.com/cheval/123-test'


class StructureGeny(unittest.TestCase):
    def test_real_rows(self):
        first = structurer(MONTÉ)
        self.assertEqual(first['piste_geny'], 'GP')
        self.assertEqual(first['categorie_geny'], 'D')
        self.assertEqual(first['terrain_geny'], 'Dur')
        self.assertEqual(first['allocation_geny_eur'], 46000)
        self.assertEqual(first['chrono_geny_sec_km'], 73.0)
        self.assertNotIn('depart_geny', first)
        self.assertNotIn('cote_geny_historique', first)
        second = structurer(ENGHIEN)
        self.assertEqual(second['depart_geny'], 'Auto')
        self.assertEqual(second['driver_geny'], 'J-M. Lesne')
        self.assertEqual(second['cote_geny_historique'], 6.6)
        self.assertNotIn('piste_geny', second)
        self.assertNotIn('chrono_geny_sec_km', second)

    def test_missing_and_ambiguous(self):
        text = MONTÉ.replace('GP | G', 'PP | D').replace('Dur', 'Herbe').replace('Crse D', 'Gr. II')
        parsed = structurer(text)
        self.assertEqual((parsed['piste_geny'], parsed['terrain_geny'], parsed['groupe_geny']),
                         ('PP', 'Herbe', 'II'))
        self.assertNotIn('categorie_geny', parsed)
        self.assertNotIn('ferrure', parsed)
        self.assertNotIn('piste_geny', structurer(text.replace('PP', 'PP | GP')))
        self.assertEqual(structurer('Qualification | ' + text)['geny_parsing_motifs'], 'qualification')
        self.assertEqual(structurer(URL), {})

    def test_collection_keeps_raw(self):
        row, = parse_career('CARRIÈRE\n' + ENGHIEN, [ENGHIEN])['performances']
        self.assertEqual(row['texte_source'], ENGHIEN)
        self.assertEqual(row['driver_geny'], 'J-M. Lesne')

    def test_mixed_legacy_and_idempotence(self):
        headers = ['cle_performance', 'source_url', 'chrono_geny_sec_km']
        raw = [headers, ['a', MONTÉ, 75], ['b', URL], ['dup', MONTÉ], ['dup', ENGHIEN]]
        archives = {'b': {'texte_source': ENGHIEN}}
        rows = [dict(zip(headers, r)) for r in raw[1:]]
        fields, updates, conflicts, duplicates = planifier(headers, rows, archives)
        self.assertEqual(conflicts, {'chrono_geny_sec_km': 1})
        self.assertEqual(duplicates, 1)
        self.assertTrue(all(row < 4 for row, _, _ in updates))
        after = [fields] + [r + [''] * (len(fields) - len(r)) for r in raw[1:]]
        for row, col, value in updates:
            after[row - 1][col - 1] = value
        verifier(raw, after, headers, fields, updates)
        migrated = [dict(zip(fields, r)) for r in after[1:]]
        self.assertEqual(migrated[1]['url_source_geny'], URL)
        self.assertEqual(migrated[1]['texte_source'], ENGHIEN)
        self.assertEqual(planifier(fields, migrated, archives)[1], [])
        after[2][1] = ''
        with self.assertRaises(ValueError):
            verifier(raw, after, headers, fields, updates)

    def test_sparse_write_skips_existing_cells(self):
        self.assertEqual(plages_migration('Historique chevaux', [(4, 2, 'a'), (6, 2, 'b')]),
                         [{'range': "'Historique chevaux'!B4", 'values': [['a'], [None], ['b']]}])

    def test_regular_sync_preserves_real_legacy_url(self):
        headers = ['cle_performance', 'source_url', 'texte_source']
        _, updates, _ = plan_sheet(headers, [{'cle_performance': 'b', 'source_url': URL}],
                                    {'b': {'cle_performance': 'b', 'source_url': ENGHIEN,
                                           'texte_source': ENGHIEN}}, 'Historique chevaux')
        self.assertEqual(updates, [(2, 3, ENGHIEN)])
