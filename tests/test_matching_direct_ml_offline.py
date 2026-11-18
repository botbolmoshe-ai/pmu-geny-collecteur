import unittest
from datetime import datetime, timezone
from pmu_geny.sync_google_sheets import matching_pct,plan_sheet,source_rows,conclusion_methodes
from tempfile import TemporaryDirectory
from pathlib import Path
from pmu_geny.ml_v19 import save

class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.depart='2026-11-12T14:00:00+01:00'
        self.now=datetime(2026,11,12,16,tzinfo=timezone.utc)
        self.arr={'verifie_utc':'2026-11-12T14:10:00+01:00','arrivee':[
            {'rang':i,'numero':i} for i in (1,2,3)]}
    def pred(self,nums):
        return {'calcul_utc':'2026-11-12T13:00:00+01:00','top3':[{'numero':n} for n in nums]}
    def test_four_scores(self):
        for nums,expected in [([4,5,6],0),([1,4,5],33.33),([2,1,5],66.67),([3,2,1],100)]:
            self.assertEqual(matching_pct(self.pred(nums),self.arr,self.depart,self.now),expected)
    def test_invalid_or_missing_proofs(self):
        for p in ({},self.pred([1,1,2]),{**self.pred([1,2,3]),'calcul_utc':self.depart},
                  {**self.pred([1,2,3]),'non_partants_confirmes':[1]}):
            self.assertEqual(matching_pct(p,self.arr,self.depart,self.now),'')
        self.assertEqual(matching_pct(self.pred([1,2,3]),{**self.arr,'verifie_utc':'2099-01-01T00:00:00+00:00'},self.depart,self.now),'')
    def test_invalid_podium_and_invalid_chronology(self):
        self.assertEqual(matching_pct(self.pred([1,2,31]),self.arr,self.depart,self.now),'')
        self.assertEqual(matching_pct(self.pred([1,2,3]),{**self.arr,'verifie_utc':self.depart},self.depart,self.now),'')
        self.assertEqual(matching_pct(self.pred([1,2,3]),{**self.arr,'arrivee':[{'rang':i,'numero':1} for i in (1,2,3)]},self.depart,self.now),'')
    def test_conclusions_ne_designent_pas_de_faux_gagnant(self):
        self.assertEqual(conclusion_methodes({'Direct':0,'ML':0}), 'Échec commun : aucun cheval retrouvé (0/3)')
        self.assertEqual(conclusion_methodes({'Direct':0,'ML':''}), 'Direct : 0/3 ; aucune autre méthode évaluable')
        self.assertTrue(conclusion_methodes({'Direct':33.33,'ML':33.33}).startswith('Égalité en tête'))
        self.assertTrue(conclusion_methodes({'Direct':66.67,'ML':33.33}).startswith('Meilleure méthode : Direct'))
        self.assertTrue(conclusion_methodes({'Direct':'','ML':''}).startswith('Aucune prévision'))

    def test_numeric_values_and_clear(self):
        before={'course_key':'x','matching_direct_pct':100,'matching_ml_pct':33.33}
        after={**before,'matching_direct_pct':0,'matching_ml_pct':''}
        headers,changes,append=plan_sheet(list(before),[before],{'x':after},'Résultats & Analyse')
        self.assertFalse(append)
        self.assertEqual({headers[c-1]:v for _,c,v in changes},{'matching_direct_pct':0,'matching_ml_pct':''})

    def test_source_publie_matching_distinct_sur_une_arrivee_verifiee(self):
        with TemporaryDirectory() as folder:
            root=Path(folder); day='2026-11-12'; code='R3C1'
            save(root/'sources_pmu'/f'programme_{day}.json',{'programme':[{
                'date':day,'code':code,'depart':self.depart,'hippodrome':'VINCENNES'}]})
            save(root/'arrivees'/f'{day}_{code}.json',self.arr)
            save(root/'pronostics'/f'{day}_{code}_direct.json',self.pred([1,2,4]))
            save(root/'pronostics'/f'{day}_{code}_ml_latest.json',self.pred([4,5,6]))
            item=next(iter(source_rows(root)['Résultats & Analyse'].values()))
            self.assertEqual(item['matching_direct_pct'],66.67)
            self.assertEqual(item['matching_ml_pct'],0)
            self.assertTrue(item['conclusion'].startswith('Meilleure méthode : Direct'))
            save(root/'pronostics'/f'{day}_{code}_direct.json',self.pred([4,5,6]))
            item=next(iter(source_rows(root)['Résultats & Analyse'].values()))
            self.assertTrue(item['conclusion'].startswith('Échec commun'))
            save(root/'pronostics'/f'{day}_{code}_direct.json',{**self.pred([1,2,3]),'calcul_utc':self.depart})
            item=next(iter(source_rows(root)['Résultats & Analyse'].values()))
            self.assertEqual(item['conclusion'],'ML : 0/3 ; aucune autre méthode évaluable')
            (root/'pronostics'/f'{day}_{code}_ml_latest.json').unlink()
            item=next(iter(source_rows(root)['Résultats & Analyse'].values()))
            self.assertEqual(item['matching_ml_pct'],'')
