"""Recette de projection courante et de reprise de publication du ticket #138."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from dashboard.trot_analytics.correspondance_geny import AMBIGUE, CHAMP, CONFIRMEE, NON_EFFECTUEE
from pmu_geny.historiques_incrementaux import course_geny_connue, ecrire, lire
from pmu_geny.moteur_sheets import SynchroniseurSheets, SynchronisationOccupee, verrou_local
from pmu_geny.reconciliation_historiques import ReconciliationHistoriques
from pmu_geny.sync_google_sheets import publier_plan
from test_v26_chaine_offline import SheetsSession


NOW = datetime(2026, 11, 28, tzinfo=timezone.utc)
STAMP = '2026-11-15T16:56:00+00:00'
TAB = 'Courses & Prévisions'


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.cache = Path(root.name)
        config = patch.dict('os.environ', {
            'PMU_SHEETS_CONTROLES': str(self.cache/'controle.jsonl'),
            'PMU_SHEETS_LOCK_DIR': str(self.cache),
        })
        config.start()
        self.addCleanup(config.stop)

    def capture(self, ident, name, *, total=1, partial=False):
        url = f'https://www.geny.com/cheval/{ident}'
        perf = {'date': '2026-11-13', 'hippodrome': 'Vincennes', 'discipline': 'Monté',
                'distance_m': 2175, 'classement': '8', 'chrono': "1’12’’8"}
        folder = 'historiques_partiels' if partial else 'historiques'
        ecrire(self.cache/folder/ident/'historique_geny.json', {
            'nom': name, 'extrait_utc': STAMP, 'source_url': url, 'identite_verifiee': True,
            'statut': 'PARTIEL_HISTORIQUE' if partial else 'COMPLET',
            'nombre_annonce_geny': total, 'nombre_extrait': 1, 'performances': [perf],
        })
        row = {'identifiant_cheval': ident, 'cheval': name, 'source_url': url,
               'cle_performance': f'{ident}|2026-11-13|VINCENNES', 'date_course_historique': perf['date']}
        return {**row, **{field: value for field, value in perf.items() if field != 'date'}}

    def test_deux_captures_posterieures_et_identite_de_course_du_troisieme_cas(self):
        rows = [self.capture('2802343', 'Lovely Jenilou'), self.capture('2805504', 'Lacienda Flash')]
        for number, row in enumerate(rows, 1):
            current = {'course_key': '2026-11-13|VINCENNES|R1C2', 'numero': str(number),
                       'cheval': row['cheval'], 'historique_statut': 'HISTO_NON_COLLECTE'}
            announced = ReconciliationHistoriques(self.cache, [], now=NOW).diagnostiquer(current)
            published = ReconciliationHistoriques(self.cache, rows, now=NOW).diagnostiquer(current)
            self.assertEqual(announced['historique_statut'], 'HISTO_PUBLICATION_EN_ATTENTE')
            self.assertTrue(published['historique_statut'].startswith('HISTO_OK'))
            self.assertEqual(published['historique_nb_courses_datees'], 1)
            self.assertEqual(published['historique_maj_utc'], STAMP)
        self.assertEqual(course_geny_connue(self.cache, '2026-11-14_R3C1'), 'GENY-1698473')
        amiral = ReconciliationHistoriques(self.cache, rows, now=NOW).diagnostiquer({
            'course_key': '2026-11-14|MARSEILLE BORELY|R3C1', 'numero': '3', 'cheval': "L’AMIRAL TURGOT"})
        self.assertEqual(amiral[CHAMP], CONFIRMEE)
        self.assertEqual(amiral['_id_geny_correspondance'], '2816916')
        self.assertEqual(amiral['historique_statut'], 'GENY_IDENTIFIE_CARRIERE_MANQUANTE')
        unknown = ReconciliationHistoriques(self.cache, rows, now=NOW).diagnostiquer({
            'course_key': '2026-11-14|MARSEILLE BORELY|R3C1', 'numero': '3', 'cheval': "Autre nom"})
        self.assertEqual(unknown[CHAMP], NON_EFFECTUEE)

    def test_partiel_et_deux_homonymes_ne_deviennent_pas_complets(self):
        first = self.capture('2800991', 'Même nom', total=2, partial=True)
        row = {'course_key': '2026-11-13|VINCENNES|R1C2', 'numero': '1', 'cheval': 'MEME NOM'}
        a = ReconciliationHistoriques(self.cache, [first], now=NOW).diagnostiquer(row)
        self.assertEqual((a['historique_statut'], a['historique_nb_courses_datees']), ('HISTO_PARTIEL_GENY', 1))
        second = self.capture('2800992', 'Même nom')
        b = ReconciliationHistoriques(self.cache, [first, second], now=NOW).diagnostiquer(row)
        self.assertEqual((b[CHAMP], b['historique_nb_courses_datees']), (AMBIGUE, 0))

    def test_alias_inter_sources_publie_sous_sa_cle_historique(self):
        current = self.capture('2724812', 'Jiska de Dream')
        legacy = {**current, 'identifiant_cheval': '1717076', 'cle_performance': 'clé conservée',
                  'source_url': 'https://www.zone-turf.fr/cheval/jiska-de-dream-1717076/resume-de-carriere/'}
        recon = ReconciliationHistoriques(self.cache, [legacy], now=NOW)
        found = recon.diagnostiquer({'course_key': '2026-11-16|CAGNES|R6C6',
                                      'numero': '6', 'cheval': 'JISKA DE DREAM'})
        self.assertEqual(found['_id_geny_correspondance'], '2724812')
        self.assertTrue(found['historique_statut'].startswith('HISTO_OK'))
        self.assertEqual(legacy['cle_performance'], 'clé conservée')

    def test_relecture_idempotence_verrou_et_figements(self):
        publication = self.capture('2802343', 'Lovely Jenilou')
        session = SheetsSession()
        tab_history = 'Historique chevaux'
        session.tables[tab_history] = [list(publication), list(publication.values())]
        headers = ['course_key', 'numero', 'cheval', CHAMP, 'historique_statut',
                   'historique_nb_courses_datees', 'historique_maj_utc', 'baseline_top3']
        session.tables[TAB] = [headers, ['2026-11-13|VINCENNES|R1C2', '1', 'Lovely Jenilou',
            CONFIRMEE, 'HISTO_NON_COLLECTE', '0', '', 'OUI']]
        path = self.cache/'pronostics'/'2026-11-13_R1C2_top3.json'
        ecrire(path, {'top3': [{'numero': 1}], 'calcul_utc': '2026-11-13T14:00:00+00:00'})
        freeze = path.read_bytes()
        engine = SynchroniseurSheets(self.cache, 'fake-reconciliation', session=session)
        with verrou_local(engine.spreadsheet):
            with self.assertRaises(SynchronisationOccupee):
                engine.synchroniser_correspondances()
        with patch.object(engine, '_controler_correspondances', return_value=1):
            first = engine.synchroniser_correspondances()[TAB]
            second = engine.synchroniser_correspondances()[TAB]
        self.assertEqual(first['reconciliation_historiques']['ecarts_avant']['historique_publie_affiche_absent'], 1)
        self.assertEqual(second['cellules_actualisees'], 0)
        self.assertEqual(second['reconciliation_historiques']['ecarts_avant'], {})
        self.assertEqual(session.tables[TAB][1][-1], 'OUI')
        self.assertEqual(path.read_bytes(), freeze)


    def test_capture_avec_variantes_du_meme_resultat_reste_partielle(self):
        row = self.capture('2731917', 'Jazz Pettevinière', total=2)
        path = self.cache/'historiques/2731917/historique_geny.json'
        doc = lire(path)
        first = doc['performances'][0]
        doc['performances'] = [{**first, 'texte_source': 'Crse E | Nc'},
                               {**first, 'texte_source': 'Nc'}]
        doc['nombre_extrait'] = 2
        ecrire(path, doc)
        recon = ReconciliationHistoriques(self.cache, [row], now=NOW)
        status, count, _, note = recon.historique('2731917')
        self.assertEqual((status, count), ('HISTO_PARTIEL_GENY', 1))
        self.assertIn('1/2 signatures sportives distinctes', note)

    def test_publications_pmu_ne_rejouent_pas_un_ancien_diagnostic(self):
        row = {'date_course': '2026-11-27', 'rncn': 'R1C2', 'course_key': 'course',
               'numero': '1', 'historique_statut': 'HISTO_NON_COLLECTE',
               CHAMP: NON_EFFECTUEE, 'top3_direct_top3': 'OUI'}
        for mode in ('GLOBAL', 'JALONS'):
            with self.subTest(mode=mode):
                engine = Mock()
                engine.source.return_value = {TAB: {'partant': row}, 'Résultats & Analyse': {}}
                publier_plan(engine, {'mode': mode, 'date': row['date_course'], 'selection': [row['rncn']]})
                tables = engine.synchroniser_tables.call_args_list[0].args[0]
                self.assertNotIn('Historique chevaux', tables)
                self.assertNotIn('historique_statut', tables[TAB]['partant'])
                self.assertNotIn(CHAMP, tables[TAB]['partant'])
                self.assertEqual(tables[TAB]['partant']['top3_direct_top3'], 'OUI')


if __name__ == '__main__':
    unittest.main()
