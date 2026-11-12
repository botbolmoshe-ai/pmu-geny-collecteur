"""Quota reel, arret source et couverture des lignes sans manifeste Geny."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.simuler_collecte import scenario_quota
from pmu_geny.sync_google_sheets import source_rows

def write(p,d):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d),encoding='utf-8')

class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        write(self.root/'historiques/1/historique_geny.json',{'statut':'COMPLET','nombre_annonce_geny':2,'nombre_extrait':2,
            'performances':[{'date':d,'hippodrome':'Vincennes','discipline':'Attelé','distance_m':'2700','classement':'1'} for d in ['2026-10-01','2026-10-15']]})

    def test_cached_course_does_not_consume_next_course_budget(self):
        old=scenario_quota(self.root,False,'premiere_course_en_cache')
        new=scenario_quota(self.root,True,'premiere_course_en_cache')
        self.assertEqual(old['tentatives_simulees'],0)
        self.assertEqual(new['tentatives_simulees'],6)
        self.assertEqual(new['quota_annonce_consomme'],6)

    def test_unused_budget_is_shared_between_courses(self):
        old=scenario_quota(self.root,False,'premiere_course_a_completer')
        new=scenario_quota(self.root,True,'premiere_course_a_completer')
        self.assertEqual(old['tentatives_simulees'],3)
        self.assertEqual(new['tentatives_simulees'],6)
        self.assertEqual(new['courses_servies'],2)

    def test_refusal_stops_all_further_collection(self):
        for optimized in [False,True]:
            result=scenario_quota(self.root,optimized,'refus_429')
            self.assertEqual(result['tentatives_simulees'],1)
            self.assertEqual(result['nouveaux_historiques_simules'],0)
            self.assertTrue(result['arret_429_respecte'])

class CoverageTests(unittest.TestCase):
    def test_participant_results_and_selection_labels_do_not_require_geny(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);key='2026-11-12_R1C1'
            write(root/'sources_pmu/programme_2026-11-12.json',{'programme':[{'date':'2026-11-12','code':'R1C1','hippodrome':'Vincennes','depart':'2026-11-12T14:00:00+01:00'}]})
            write(root/'partants_actuels'/f'{key}.json',{'chevaux':{str(n):{'nom':f'H{n}','statut_np':'NON_PARTANT' if n==5 else 'PARTANT'} for n in range(1,6)}})
            ranking=[{'numero':n,'score_direct':6-n} for n in range(1,5)]
            write(root/'pronostics'/f'{key}_direct.json',{'classement_complet':ranking,'top3':ranking[:3]})
            write(root/'arrivees'/f'{key}.json',{'arrivee':[{'numero':n,'rang':i} for i,n in enumerate([3,2,1,4],1)]})
            rows=source_rows(root)['Courses & Prévisions']
            by_number={r['numero']:r for r in rows.values()}
            self.assertEqual(by_number['3']['arrivee_rang'],1)
            self.assertEqual(by_number['4']['arrivee_rang'],4)
            self.assertEqual(by_number['1']['top3_direct_top3'],'OUI')
            self.assertEqual(by_number['4']['top3_direct_top3'],'NON')
            self.assertEqual(by_number['5']['top3_direct_top3'],'NON_PARTANT')
            self.assertEqual(by_number['1']['ml_top3'],'NON_CALCULE')
            self.assertEqual(by_number['5']['ml_top3'],'NON_PARTANT')
            self.assertEqual(sum(r['top3_direct_top3']=='OUI' for r in rows.values()),3)

if __name__=='__main__':unittest.main()
