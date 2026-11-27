from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from dashboard.trot_analytics.dates import nombre_paris
from pmu_geny.echeances_production import sauver
from pmu_geny.moteur_sheets import ErreurSynchronisation
from pmu_geny.supervision_sheets import (
    CHECKPOINT, INCREMENTAL, MAPPING, REFERENTIEL, SUPERVISION, SUPERVISION_HEADERS,
    _publier_vue, lignes_referentiel, lignes_supervision, prochain_tick,
)


class SupervisionTests(unittest.TestCase):
    def setUp(self):
        workspace = TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.cache = Path(workspace.name)
        self.now = datetime(2026, 11, 27, 13, 16, tzinfo=timezone.utc)

    def test_publication_ciblee_ne_masque_pas_le_retard_global(self):
        prev = self.now-timedelta(hours=2, minutes=49)
        sauver(self.cache/CHECKPOINT, {
            'dernier_global_publie_utc': prev.isoformat(),
            'dernier_jalon_publie_utc': (self.now-timedelta(minutes=10)).isoformat(),
            'derniere_publication_pmu_utc': (self.now+timedelta(minutes=1)).isoformat(),
        })
        rows = {row[1]: row for row in lignes_supervision(self.cache, self.now)[1:]}
        self.assertEqual(rows['Cycle global J/J+1'][2], 'En retard')
        self.assertEqual(rows['Cycle global J/J+1'][3], nombre_paris(prev))
        self.assertEqual(rows['Cycle global J/J+1'][6], 169)
        self.assertEqual(rows['Publication PMU'][2], 'Horodatage futur')
        self.assertNotEqual(rows['Jalons H-3 / H-2'][3], rows['Cycle global J/J+1'][3])

    def test_tick_paris_change_de_jour_et_suit_le_passage_a_l_heure_d_ete(self):
        spring = datetime(2026, 3, 29, 0, 59, tzinfo=timezone.utc)
        self.assertEqual(prochain_tick(spring, (7, 22, 37, 52)), '2026-03-29T01:07:00+00:00')
        self.assertEqual(prochain_tick(spring, (7, 22, 37, 52), jour=True), '2026-03-29T05:07:00+00:00')

    def test_referentiel_identite_et_historique_separes_sans_doublons(self):
        now = self.now.isoformat()
        engagement = '2026-11-27_R2C1'
        url = 'https://www.geny.com/cheval/12345-test/course/6789'
        sauver(self.cache/MAPPING, {engagement: 'GENY-6789'})
        horse = {'nom': 'Test', 'engagement': engagement, 'numero': '4', 'id_pmu': '42'}
        autre = {'nom': 'Autre', 'engagement': engagement, 'numero': '5', 'id_pmu': '43'}
        sauver(self.cache/INCREMENTAL, {'chevaux': {
            'one': horse, 'other': {**autre, 'recherche_identite_geny': {
                'statut': 'RECHERCHE_BLOQUEE', 'motif': 'ACCES_GENY_429', 'utc': now,
                'reprise_utc': (self.now+timedelta(minutes=30)).isoformat(),
            }},
        }})
        sauver(self.cache/'rattrapage_historiques/etat.json', {'chevaux': {
            'duplicate': {**horse, 'id': '12345', 'geny': {'id': '12345', 'url_geny': url}},
        }})
        sauver(self.cache/'sources_geny/identites/preuve.json', {
            'nom_attendu': 'Test', 'id_pmu': '42', 'resolution_utc': now,
            'preuve': 'RECHERCHE_GENY_NOM_EXACT', 'geny': {'id': '12345', 'nom': 'Test', 'url_geny': url},
        })
        with patch('pmu_geny.identites_chevaux.courses_verifiees', return_value=[]):
            rows = lignes_referentiel(self.cache, [], self.now)
        data = {row[1]: row for row in rows[1:]}
        self.assertEqual(len(rows)-1, len(data))
        self.assertEqual(set(data), {'course:'+engagement, 'geny:12345', 'pmu:43'})
        self.assertEqual(data['geny:12345'][5:12], [
            '42', 'Test', '12345', url, 'CORRESPONDANCE_CONFIRMEE', 'GENY_IDENTIFIE_CARRIERE_MANQUANTE', 0,
        ])
        self.assertEqual(data['pmu:43'][9], 'RECHERCHE_BLOQUEE')
        self.assertEqual(data['pmu:43'][14], nombre_paris(self.now+timedelta(minutes=30)))

    def test_publication_relie_et_ne_reecrit_pas_une_vue_identique(self):
        engine = Mock(base='https://sheets.invalid')
        props = {'sheetId': 9, 'gridProperties': {'rowCount': 50, 'columnCount': len(SUPERVISION_HEADERS)}}
        rows = [list(SUPERVISION_HEADERS), ['PMU', 'Cycle global', 'À jour', nombre_paris(self.now)]]
        reader = 'pmu_geny.sync_google_sheets.lire_feuille_complete'
        with patch(reader, side_effect=[rows[:1], rows, rows]):
            _publier_vue(engine, SUPERVISION, rows, props, {3, 4})
            _publier_vue(engine, SUPERVISION, rows, props, {3, 4})
        self.assertEqual(engine.session.post.call_count, 1)
        self.assertEqual(engine.session.post.call_args.kwargs['json']['data'][0]['values'][1], rows[1])
        with patch(reader, return_value=rows[:1]), self.assertRaises(ErreurSynchronisation):
            _publier_vue(engine, SUPERVISION, rows, props, {3, 4})

    def test_creation_atomique_presente_deux_vues_filtrees(self):
        engine = Mock(base='https://sheets.invalid')
        engine.metadata.return_value = {}
        rows = [['Type', 'Clé'], ['Course', 'clé test']]
        with patch('pmu_geny.sync_google_sheets.lire_feuille_complete', return_value=rows):
            _publier_vue(engine, REFERENTIEL, rows, None, set())
        requests = engine.session.post.call_args_list[0].kwargs['json']['requests']
        self.assertIn('addSheet', requests[0])
        filters = [request['addFilterView']['filter'] for request in requests if 'addFilterView' in request]
        self.assertEqual([view['title'] for view in filters],
                         ['Toutes les correspondances', 'Courses PMU–Geny', 'Chevaux PMU–Geny'])
        self.assertEqual(filters[1]['filterSpecs'][0]['filterCriteria']['hiddenValues'], ['Cheval'])
