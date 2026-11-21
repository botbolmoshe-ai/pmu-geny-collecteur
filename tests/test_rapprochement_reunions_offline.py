from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pmu_geny import echeances_production as production
from pmu_geny import rapprochement_reunions as rapprochement


class RapprochementReunionsTests(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.cache = Path(temp.name)
        self.day = '2026-11-21'
        self.first = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)
        self.last = self.first + timedelta(minutes=35)
        self.courses = [
            {'code': code, 'date': self.day, 'hippodrome': 'Vincennes', 'depart': depart.isoformat()}
            for code, depart in [('R1C1', self.first), ('R1C2', self.last),
                                 ('R2C1', self.first + timedelta(hours=3))]
        ]
        self.write_programme(self.day, self.courses)

    def write_programme(self, day, courses):
        production.sauver(self.cache/'sources_pmu'/f'programme_{day}.json', {'programme': courses})

    def test_deux_reunions_meme_hippodrome_et_echeance_commune_aux_courses(self):
        now = self.first - timedelta(hours=2, minutes=35)
        plan = production.planifier(self.cache, now, force=True)
        self.assertEqual(plan['mode'], 'JALONS')
        self.assertEqual(plan['selection'], ['R1C1', 'R1C2'])
        self.assertEqual({row['echeance'] for row in plan['jalons_dus']},
                         {(self.first-timedelta(hours=2)).isoformat()})
        self.assertEqual(production.besoin_pmu(self.cache, now), 'ECHEANCE_PMU_PRIORITAIRE')
        later = production.planifier(self.cache, now + timedelta(hours=3))
        self.assertEqual(later['selection'], ['R2C1'])

    def test_changement_heure_automne(self):
        self.day = '2026-10-25'
        self.write_programme(self.day, [
            {'code': 'R1C1', 'depart': '2026-10-25T02:50:00+02:00'},
            {'code': 'R1C2', 'depart': '2026-10-25T02:15:00+01:00'}])
        reunion, = production.reunions_du_jour(self.cache, self.day)
        self.assertEqual(reunion['premier_depart'].isoformat(), '2026-10-25T00:50:00+00:00')
        self.assertEqual(reunion['dernier_depart'].isoformat(), '2026-10-25T01:15:00+00:00')

    def test_h30_provisoire_indisponible_et_reprise_ciblee(self):
        self.write_programme(self.day, self.courses[:2])
        now = self.last + timedelta(minutes=30)
        self.assertEqual(rapprochement.planifier_rapprochements(self.cache, now-timedelta(seconds=1)), [])
        plan = production.planifier(self.cache, now)
        self.assertEqual(plan['mode'], 'RAPPROCHEMENT')
        result_path = self.cache/'rapprochements/2026-11-21_R1.json'
        official, provisional = [{**c, 'podium_definitif_pmu': podium}
                                 for c, podium in zip(self.courses, ([1, 2, 3], []))]
        participants = {'participants': [{'numPmu': n, 'ordreArrivee': n} for n in (1, 2, 3)]}
        with patch('pmu_geny.auto_v18.programme_diagnostic', return_value=(
                [], {'inventaire_reunions': [official, provisional]})), patch(
                'pmu_geny.auto_v18.get_json', side_effect=[{}, participants, participants]):
            rapprochement.rapprocher(self.cache, plan, lambda: now)
        first = production.lire(result_path)
        self.assertEqual(first['statut'], 'INCOMPLET')
        self.assertEqual(first['arrivees_a_reprendre'], ['R1C2'])
        self.assertEqual(first['courses']['R1C2']['statut'], 'ARRIVEE_NON_VERIFIEE')
        # Un échec Sheets relance l'écriture, sans retoucher les arrivées.
        with patch('pmu_geny.auto_v18.get_json') as network:
            rapprochement.rapprocher(self.cache, production.planifier(self.cache, now), lambda: now)
        network.assert_not_called()
        production.enregistrer_publication(self.cache, now, plan, True,
                                            sheets={'lecture_utc': now.isoformat()})
        later = now + timedelta(minutes=30)
        plan = production.planifier(self.cache, later)
        verified = {**provisional, 'podium_definitif_pmu': [1, 2, 3]}
        with patch('pmu_geny.auto_v18.programme_diagnostic', return_value=(
                [], {'inventaire_reunions': [official, verified]})), patch(
                'pmu_geny.auto_v18.get_json', side_effect=[{}, participants]) as network:
            rapprochement.rapprocher(self.cache, plan, lambda: later)
        self.assertEqual(network.call_count, 2)
        final = production.lire(result_path)
        self.assertEqual(final['statut'], 'COMPLET')
        self.assertEqual(final['declenchement_utc'], now.isoformat())
        self.assertEqual(final['arrivees_a_reprendre'], [])
