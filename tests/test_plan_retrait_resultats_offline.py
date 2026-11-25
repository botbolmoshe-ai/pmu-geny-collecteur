import unittest

from pmu_geny.plan_retrait_resultats import planifier, verifier_projection


class PlanRetraitResultatsTests(unittest.TestCase):
    def test_retrait_scope_idempotence_et_conservation(self):
        before = [
            ['Clé course (technique)', 'Score H-1 · Direct', 'TOP3 ML · Matching (%)',
             'Paris · H-2 · Publication', 'Paris · Arrivée · Vérifiée', 'Jalon comparé'],
            ['key', 2, 0, 42000.4, 42000.6, 'H-2'],
        ]
        plan = planifier(before[0])
        self.assertEqual([r['colonne'] for r in plan['retraits']], ['B', 'D'])
        after = [plan['en_tetes_attendus'], ['key', 0, 42000.6, 'H-2']]
        verifier_projection(before, after, plan)
        self.assertEqual(planifier(after[0])['retraits'], [])
        with self.assertRaisesRegex(ValueError, 'ligne 2'):
            verifier_projection(before, [after[0], ['key', '', 42000.6, 'H-2']], plan)

    def test_refus_ambiguite_sur_cle(self):
        with self.assertRaisesRegex(ValueError, 'ambigus'):
            planifier(['course_key', 'Clé course (technique)'])

    def test_migration_relecture_idempotente_et_sauvegarde_avant_ecriture(self):
        from unittest.mock import Mock, patch
        from pmu_geny.plan_retrait_resultats import TAB, retrait_sauvegarde

        engine = Mock(spreadsheet='registre-hors-ligne', base='https://sheets.invalid/test')
        engine.metadata.return_value = {TAB: {'sheetId': 12}}
        before = [['course_key', 'Score H-2 · ML', 'matching_ml_pct'], ['r', 0, 0]]
        after = [['course_key', 'matching_ml_pct'], ['r', 0]]
        timeline = Mock()
        timeline.attach_mock(engine.session.post, 'post')
        with patch('pmu_geny.sync_google_sheets.lire_feuille_complete', side_effect=[before, before, after, after]):
            result = retrait_sauvegarde(engine, timeline.backup, appliquer=True)
            second = retrait_sauvegarde(engine, timeline.backup, appliquer=True)
        self.assertEqual(result['retraits'][0]['colonne'], 'B')
        self.assertEqual(second['retraits'], [])
        self.assertEqual([call[0] for call in timeline.mock_calls], ['backup', 'post'])
        self.assertEqual(engine.session.post.call_args.kwargs['json']['requests'], [
            {'deleteDimension': {'range': {
                'sheetId': 12, 'dimension': 'COLUMNS', 'startIndex': 1, 'endIndex': 2,
            }}}
        ])

    def test_migration_refuse_modification_concurrente(self):
        from unittest.mock import Mock, patch
        from pmu_geny.plan_retrait_resultats import TAB, retrait_sauvegarde

        engine = Mock(spreadsheet='registre-hors-ligne', base='https://sheets.invalid/test')
        engine.metadata.return_value = {TAB: {'sheetId': 12}}
        before = [['course_key', 'Score H-2 · ML'], ['r', 0]]
        concurrent = [before[0], ['r', 1]]
        with patch('pmu_geny.sync_google_sheets.lire_feuille_complete', side_effect=[before, concurrent]):
            with self.assertRaisesRegex(ValueError, 'depuis la sauvegarde'):
                retrait_sauvegarde(engine, Mock(), appliquer=True)
        engine.session.post.assert_not_called()

    def test_publication_ne_recree_pas_les_colonnes_retirees(self):
        from pmu_geny.plan_retrait_resultats import TAB
        from pmu_geny.sync_google_sheets import DETAILS_JALONS, plan_sheet

        record = {'course_key': 'r', 'score_h2_ml': 0, 'jalon_h2_statut': 'PUBLIE_A_TEMPS',
                  'matching_ml_pct': 0, 'jalon_compare': 'H-2'}
        for initial in (['course_key'], ['course_key', 'score_h2_ml']):
            headers, _, rows = plan_sheet(initial, [], {'r': record}, TAB)
            self.assertEqual(set(headers) & DETAILS_JALONS, set(initial) & DETAILS_JALONS)
            projected = dict(zip(headers, rows[0]))
            self.assertEqual(projected['matching_ml_pct'], 0)
            self.assertEqual(projected['jalon_compare'], 'H-2')
            if 'score_h2_ml' in initial:
                self.assertEqual(projected['score_h2_ml'], 0)
