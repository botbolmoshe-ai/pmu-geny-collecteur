import unittest
from datetime import datetime, timezone
from pmu_geny.sync_google_sheets import matching_pct,plan_sheet

class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.depart='2026-11-17T14:00:00+01:00'
        self.now=datetime(2026,11,17,16,tzinfo=timezone.utc)
        self.arr={'verifie_utc':'2026-11-17T14:10:00+01:00','arrivee':[
            {'rang':i,'numero':i} for i in (1,2,3)]}
    def pred(self,nums):
        return {'calcul_utc':'2026-11-17T13:00:00+01:00','top3':[{'numero':n} for n in nums]}
    def test_four_scores(self):
        for nums,expected in [([4,5,6],0),([1,4,5],33.33),([2,1,5],66.67),([3,2,1],100)]:
            self.assertEqual(matching_pct(self.pred(nums),self.arr,self.depart,self.now),expected)
    def test_invalid_or_missing_proofs(self):
        for p in ({},self.pred([1,1,2]),{**self.pred([1,2,3]),'calcul_utc':self.depart},
                  {**self.pred([1,2,3]),'non_partants_confirmes':[1]}):
            self.assertEqual(matching_pct(p,self.arr,self.depart,self.now),'')
        self.assertEqual(matching_pct(self.pred([1,2,3]),{**self.arr,'verifie_utc':'2099-01-01T00:00:00+00:00'},self.depart,self.now),'')
    def test_numeric_values_and_clear(self):
        before={'course_key':'x','matching_direct_pct':100,'matching_ml_pct':33.33}
        after={**before,'matching_direct_pct':0,'matching_ml_pct':''}
        headers,changes,append=plan_sheet(list(before),[before],{'x':after},'Résultats & Analyse')
        self.assertFalse(append)
        self.assertEqual({headers[c-1]:v for _,c,v in changes},{'matching_direct_pct':0,'matching_ml_pct':''})
