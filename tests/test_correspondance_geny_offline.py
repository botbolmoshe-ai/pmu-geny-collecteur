from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from dashboard.trot_analytics.correspondance_geny import (
    AMBIGUE, BLOQUEE, CHAMP, CONFIRMEE, KPI_PREFIX, NON_EFFECTUEE, NON_TROUVEE, STATUTS,
)
from pmu_geny import historiques_incrementaux as inc
from pmu_geny.historique_individuel import collecter, rechercher
from pmu_geny.identites_chevaux import memoriser_tentative, IndexGeny
from pmu_geny.kpi_registre import calculer_kpi, totaux_reference
from pmu_geny.liens_geny_course import url_fiche_canonique
from pmu_geny.sync_google_sheets import plan_sheet, source_rows


class CorrespondanceGenyTests(TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = Path(tmp.name)
        self.now = datetime.now(timezone.utc)
        self.date = (self.now - timedelta(days=1)).date().isoformat()
        self.engagement = self.date + '_R1C1'
        self.horse = {'nom': "Étoile d'Or", 'engagement': self.engagement, 'numero': '1', 'id_pmu': 'p123'}
        inc.ecrire(self.cache/'sources_pmu'/f'programme_{self.date}.json', {'programme': [{
            'code': 'R1C1', 'depart': (self.now - timedelta(days=1)).isoformat(), 'hippodrome': 'Vincennes'}]})
        inc.ecrire(self.cache/'partants_actuels'/f'{self.engagement}.json', {
            'chevaux': {'1': {**self.horse, 'statut_np': 'PARTANT'}}})

    def publier(self):
        source = source_rows(self.cache, now=self.now)
        rows = source['Courses & Prévisions']
        return source, rows, next(iter(rows.values()))

    def test_transitions_notes_et_pronostics_figes(self):
        source, rows, row = self.publier()
        self.assertEqual(row[CHAMP], NON_EFFECTUEE)
        headers = ['course_key', 'numero', 'top3_direct_top3']
        for motif, attendu in (
            ('RECHERCHE_GENY_NON_INTERPRETABLE', BLOQUEE),
            ('RECHERCHE_GENY_SANS_NOM_EXACT', NON_TROUVEE),
            ('RECHERCHE_GENY_NOM_AMBIGU', AMBIGUE),
        ):
            memoriser_tentative(self.horse, {'statut': motif}, self.now.isoformat(), acces=True)
            inc.ecrire(self.cache/inc.QUEUE, {'chevaux': {'fixture': self.horse}})
            source, rows, row = self.publier()
            self.assertEqual(row[CHAMP], attendu)
            self.assertIn(motif, row['_note_correspondance_geny'])
            self.assertFalse(row.get('top3_direct_top3'))
            output, changes, appends = plan_sheet(headers, [row | {CHAMP: '', 'top3_direct_top3': 'OUI'}],
                {next(iter(rows)): {'course_key': row['course_key'], 'numero': '1', CHAMP: attendu}}, 'Courses & Prévisions')
            self.assertEqual(changes, [(2, output.index(CHAMP) + 1, attendu)])
            self.assertFalse(appends)
        resolution = {'geny': {'nom': "Etoile d'Or", 'id': '123456', 'url_geny': 'https://www.geny.com/cheval/123456'},
                      'preuve': 'COURSE_GENY_VERIFIEE', 'nom_attendu': self.horse['nom'],
                      'resolution_utc': self.now.isoformat(), 'id_pmu': self.horse['id_pmu']}
        inc.ecrire(self.cache/'sources_geny/identites/123456.json', resolution)
        source, rows, row = self.publier()
        self.assertEqual(row[CHAMP], CONFIRMEE)
        self.assertFalse(row['historique_statut'].startswith('HISTO_OK'))
        label = KPI_PREFIX + STATUTS[CONFIRMEE][0]
        metrics = calculer_kpi(self.cache, source, self.now)
        self.assertEqual(metrics[label][0], 1)
        self.assertEqual(totaux_reference(metrics)[label], 1)

    def test_recherche_nominale_interdite_ne_demarre_pas_le_navigateur(self):
        with patch('pmu_geny.historique_individuel.recherche_autorisee', return_value=False), \
             patch('playwright.sync_api.sync_playwright') as navigateur:
            page = Mock()
            with self.assertRaisesRegex(ValueError, 'NON_AUTORISEE'):
                rechercher(self.horse, page)
            page.goto.assert_not_called()
            report = collecter(self.horse, self.cache)
            self.assertEqual(report['statut'], 'RECHERCHE_GENY_NON_AUTORISEE')
            navigateur.assert_not_called()

    def test_fiche_canonique_conserve_le_slug_et_ecarte_la_variante_de_course(self):
        url = 'https://www.geny.com/cheval/123456-etoile/course/22222'
        self.assertEqual(url_fiche_canonique(url), 'https://www.geny.com/cheval/123456-etoile')

    def test_id_pmu_stable_ne_resout_pas_un_conflit_de_preuves(self):
        proof = {'preuve': 'FICHE_GENY_VERIFIEE', 'nom_attendu': self.horse['nom'],
                 'resolution_utc': self.now.isoformat(), 'id_pmu': self.horse['id_pmu']}
        for ident in ('123456', '654321'):
            inc.ecrire(self.cache/f'sources_geny/identites/{ident}.json', proof | {
                'geny': {'nom': self.horse['nom'], 'id': ident, 'url_geny': f'https://www.geny.com/cheval/{ident}'}})
        self.assertEqual(IndexGeny(self.cache).resoudre(self.horse['nom'], id_pmu=self.horse['id_pmu']),
                         ({}, 'NOM_AMBIGU'))


    def test_relecture_sheets_valide_le_statut_et_publie_la_note_une_fois(self):
        from pmu_geny.moteur_sheets import ErreurSynchronisation, SynchroniseurSheets

        moteur = SynchroniseurSheets(self.cache, 'fixture', session=Mock())
        expected = {'race|1': {CHAMP: BLOQUEE, '_note_correspondance_geny': 'RECHERCHE_GENY_NON_AUTORISEE'}}
        headers = ['course_key', 'numero', CHAMP]
        tab = 'Courses & Prévisions'
        properties = {'sheetId': 123}
        keys = {'valueRanges': [{'values': [['race']]}, {'values': [[1]]}]}
        note = expected['race|1']['_note_correspondance_geny']
        cell = {'effectiveValue': {'stringValue': BLOQUEE}}
        grid = {'sheets': [{'data': [{'rowData': [{'values': [cell]}]}]}]}
        with patch('pmu_geny.moteur_sheets.get_lecture'), patch.object(moteur, 'check',
            side_effect=[keys, grid, {}, keys, grid, keys, grid]):
            self.assertEqual(moteur._controler_correspondances(tab, properties, headers, expected, formater=False), 1)
            entry = moteur.session.raw.post.call_args.kwargs['json']['requests'][0]['updateCells']
            self.assertEqual(entry['rows'], [{'values': [{'note': note}]}])
            cell['note'] = note
            self.assertEqual(moteur._controler_correspondances(tab, properties, headers, expected, formater=False), 1)
            self.assertEqual(moteur.session.raw.post.call_count, 1)
            cell['effectiveValue']['stringValue'] = NON_EFFECTUEE
            with self.assertRaisesRegex(ErreurSynchronisation, 'non confirmée'):
                moteur._controler_correspondances(tab, properties, headers, expected, formater=False)
