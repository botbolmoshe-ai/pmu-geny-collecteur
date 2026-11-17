"""Non-régression : une sélection invalidée efface les cellules obsolètes."""
import unittest
from pmu_geny.sync_google_sheets import plan_sheet

class PublicationTests(unittest.TestCase):
    def test_rangs_selection_et_score_effaces_sur_retrait(self):
        before={'course_key':'course','numero':'1','top3_direct_top3':'OUI',
                'top3_direct_rang':1,'top3_direct_score':3.5}
        after={**before,'top3_direct_top3':'','top3_direct_rang':'','top3_direct_score':''}
        headers,changes,append=plan_sheet(list(before),[before],{'one':after},'Courses & Prévisions')
        self.assertFalse(append)
        self.assertEqual({headers[col-1]:value for _,col,value in changes},
                         {'top3_direct_top3':'','top3_direct_rang':'','top3_direct_score':''})
