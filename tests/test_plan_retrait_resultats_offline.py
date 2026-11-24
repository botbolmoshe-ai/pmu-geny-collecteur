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
