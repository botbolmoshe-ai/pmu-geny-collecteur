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
                                            sheets={'lecture_utc': now.isoformat(), 'rapprochements_verifies': ['2026-11-21_R1']})
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

    def test_scores_figes_alimentent_les_onglets_et_kpi(self):
        from pmu_geny.kpi_registre import calculer_kpi
        from pmu_geny.sync_google_sheets import source_rows
        import hashlib

        now = self.last + timedelta(minutes=30)
        course_key = f'{self.day}_R1C1'
        plans = {}
        for phase, remaining, numbers in [('H3', 190, [1, 4, 5]), ('H2', 130, [1, 2, 3]), ('H1', 70, [1, 4, 5])]:
            stamp = (self.first - timedelta(minutes=remaining)).isoformat()
            path = Path('jalons')/course_key/f'{phase}.json'
            production.sauver(self.cache/path, {
                'date': self.day, 'course': 'R1C1', 'depart': self.first.isoformat(),
                'calcul_utc': stamp, 'statut': 'ML_ENTRAINE_NON_CALIBRE',
                'top3': [{'numero': n} for n in numbers],
            })
            version = {'publication_utc': stamp, 'lecture_sheets_utc': stamp,
                       'calcul_utc': stamp, 'fichier': str(path),
                       'sha256': hashlib.sha256((self.cache/path).read_bytes()).hexdigest()}
            plans[phase] = {'versions': {'direct': version, 'ml': version}}
        result = {'source': 'PMU_API_PARTICIPANTS', 'verifie_utc': now.isoformat(),
                  'podium_definitif_pmu': [1, 2, 3],
                  'arrivee': [{'numero': n, 'rang': n} for n in (1, 2, 3)]}
        production.sauver(self.cache/'arrivees'/f'{course_key}.json', result)
        scores = rapprochement.comparer(self.cache, course_key, self.first, [1, 2, 3], plans)
        production.sauver(self.cache/'rapprochements'/f'{self.day}_R1.json', {
            'date': self.day, 'reunion': f'{self.day}_R1', 'statut': 'INCOMPLET',
            'declenchement_utc': now.isoformat(), 'arrivees_a_reprendre': ['R1C2'],
            'courses': {'R1C1': {'statut': 'ARRIVEE_OFFICIELLE',
                                'scores': {k: v for k, v in scores.items() if not k.startswith('H3_')}}}})
        source = source_rows(self.cache)
        report, = source['Résultats & Analyse'].values()
        self.assertEqual(report['score_h2_direct'], 3)
        self.assertEqual(report['score_h1_ml'], 1)
        self.assertEqual(report['top3_direct_numeros'], '1,2,3')
        self.assertEqual(report['matching_ml_pct'], 100.0)
        self.assertEqual(report['top3_ml_calcule_utc'], plans['H2']['versions']['ml']['calcul_utc'])
        self.assertEqual(report['jalon_compare'], 'H-2')
        report_path = self.cache/'rapprochements'/f'{self.day}_R1.json'
        record = production.lire(report_path)
        record['courses']['R1C1']['scores'] = {
            key: value for key, value in scores.items() if not key.startswith('H1_')}
        production.sauver(report_path, record)
        production.sauver(self.cache/'jalons'/f'{course_key}.json', {
            'H3': {'statut': 'PUBLIE_A_TEMPS', 'echeance': (self.first-timedelta(hours=3)).isoformat(),
                   'publication_utc': (self.first-timedelta(minutes=185)).isoformat()}})
        source = source_rows(self.cache)
        current, = source['Résultats & Analyse'].values()
        self.assertEqual(current['score_h3_ml'], 1)
        self.assertEqual(current['score_h2_direct'], 3)
        self.assertEqual(current['jalon_compare'], 'H-2')
        self.assertEqual(current['top3_direct_numeros'], '1,2,3')
        self.assertEqual(current['jalon_h3_statut'], 'PUBLIE_A_TEMPS')
        self.assertEqual(current['jalon_h3_publication_utc'], (self.first-timedelta(minutes=185)).isoformat())
        quality = calculer_kpi(self.cache, source, now)
        self.assertEqual(quality['H+30 · Arrivées à reprendre'][0], 1)
        self.assertEqual(quality['H+30 · 7 j · H2_direct · Moyenne sur 3'][0], 3)
        self.assertEqual(quality['H+30 · 7 j · H3_ml · Moyenne sur 3'][0], 1)

    def test_un_bilan_issu_du_cache_filtre_est_rouvert(self):
        self.write_programme(self.day, self.courses[1:2])
        now = self.last + timedelta(minutes=31)
        key = f'{self.day}_R1'
        path = self.cache/'rapprochements'/f'{key}.json'
        production.sauver(path, {'reunion': key, 'statut': 'COMPLET',
                                'publication_sheets_utc': now.isoformat()})
        plan = production.planifier(self.cache, now)
        self.assertEqual(plan['mode'], 'RAPPROCHEMENT')
        official = [{**course, 'podium_definitif_pmu': [1, 2, 3]} for course in self.courses[:2]]
        participants = {'participants': [{'numPmu': n, 'ordreArrivee': n} for n in (1, 2, 3)]}
        with patch('pmu_geny.auto_v18.programme_diagnostic', return_value=(
                [], {'inventaire_reunions': official})), patch(
                'pmu_geny.auto_v18.get_json', side_effect=[{}, participants, participants]):
            rapprochement.rapprocher(self.cache, plan, lambda: now)
        report = production.lire(path)
        self.assertTrue(report['inventaire_pmu_verifie'])
        self.assertEqual(report['statut'], 'COMPLET')
        self.assertEqual(set(report['courses']), {'R1C1', 'R1C2'})
