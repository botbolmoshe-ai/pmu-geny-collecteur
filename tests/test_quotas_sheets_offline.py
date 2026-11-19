import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from pmu_geny.lectures_sheets import get_lecture
from pmu_geny.moteur_sheets import SynchroniseurSheets
from pmu_geny.sync_google_sheets import lire_feuille_complete
from test_v26_chaine_offline import Response
from test_v29_moteur_unique_offline import SessionTracee


class QuotaTests(unittest.TestCase):
    def test_grille_23000_lignes_7_lectures_avec_cles_independantes_et_relecture(self):
        class Big(SessionTracee):
            def get(self,url,**kwargs):
                response=super().get(url,**kwargs)
                if '/values' not in url:
                    for sheet in response.data['sheets']:
                        if sheet['properties']['title']=='Historique chevaux':
                            sheet['properties']['gridProperties']['rowCount']=23000
                return response
        s=Big();s.tables['Historique chevaux'].append(['ancien','999999','Ancien','2'])
        before=copy.deepcopy(s.tables['Courses & Prévisions'])
        source={'Historique chevaux':{'nouveau':{'cle_performance':'nouveau','identifiant_cheval':'123456',
                                                'cheval':'Test','classement':'3'}}}
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{
            'PMU_SHEETS_LOCK_DIR':tmp,'PMU_SHEETS_CONTROLES':tmp+'/controle.jsonl','GITHUB_STEP_SUMMARY':''}),patch('builtins.print'):
            engine=SynchroniseurSheets(Path(tmp),'fake',session=s)
            first=engine.synchroniser_tables(source,scope='TEST')
            self.assertEqual(engine.session.lectures,7)
            self.assertEqual(first['Historique chevaux']['lignes_ajoutees'],1)
            self.assertTrue(any('/values/' in u for u in s.reads))
            again=engine.synchroniser_tables(source,scope='TEST')
            self.assertEqual(again['Historique chevaux']['lignes_ajoutees'],0)
        self.assertEqual(s.tables['Courses & Prévisions'],before)
        self.assertEqual(len(s.tables['Historique chevaux']),3)

    def test_batch_incomplet_ou_mal_identifie_est_refuse(self):
        props={'gridProperties':{'rowCount':4000,'columnCount':3}}
        for response in ({'valueRanges':[]},
                         {'valueRanges':[{'range':"'Autre'!A1:C2000"},{'range':"'Historique chevaux'!A2001:C4000"}]},
                         {'valueRanges':[{'range':"'Historique chevaux'!A1:C2000"}]}):
            with self.subTest(response=response):
                session=Mock();session.get.return_value=Response(response)
                with self.assertRaises(ValueError):lire_feuille_complete(session,'base','Historique chevaux',props)
                session.post.assert_not_called()

    def test_429_attend_et_respecte_retry_after_sans_rejouer_ecriture(self):
        limited=Response({});limited.status_code=429;limited.headers={'Retry-After':'30'}
        session=Mock();session.get.side_effect=[limited,Response({'ok':True})]
        with patch('pmu_geny.lectures_sheets.time.sleep') as sleep:
            self.assertEqual(get_lecture(session,'base').status_code,200)
        sleep.assert_called_once_with(30);session.post.assert_not_called()

    def test_429_retries_bornes_et_delai_long_sans_essai_anticipe(self):
        limited=Response({});limited.status_code=429;limited.headers={}
        session=Mock();session.get.return_value=limited
        with patch('pmu_geny.lectures_sheets.time.sleep') as sleep:
            self.assertEqual(get_lecture(session,'base').status_code,429)
        self.assertEqual(session.get.call_count,4)
        self.assertEqual([c.args[0] for c in sleep.call_args_list],[15,30,60])
        session.reset_mock();limited.headers={'Retry-After':'120'}
        with patch('pmu_geny.lectures_sheets.time.sleep') as sleep:
            self.assertEqual(get_lecture(session,'base').status_code,429)
        session.get.assert_called_once();sleep.assert_not_called()
