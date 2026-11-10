import unittest
from pmu_geny.sync_google_sheets import course_key, colname, plan_sheet
class BridgeTests(unittest.TestCase):
    def test_cols(self):self.assertEqual(colname(53),'BA')
    def test_hippodrome_normalise(self):self.assertEqual(course_key('2026-11-11','HIPPODROME DE PARIS-VINCENNES','R2C4'),'2026-11-11|VINCENNES|R2C4')
    def test_course_key(self):self.assertEqual(course_key('2026-11-11','Vincennes','R2C4'),'2026-11-11|VINCENNES|R2C4')
    def test_idempotent_update(self):
        headers=['course_key','numero','cheval']; existing=[{'course_key':'x','numero':'1','cheval':'A'}]
        incoming={'x|1':{'course_key':'x','numero':'1','cheval':'A','ml_rang':'2'}}
        h,u,a=plan_sheet(headers,existing,incoming,'Courses & Prévisions')
        self.assertEqual(a,[]);self.assertIn('ml_rang',h);self.assertIn((2,h.index('ml_rang')+1,'2'),u)
    def test_append(self):
        h,u,a=plan_sheet(['course_key','numero'],[],{'x|2':{'course_key':'x','numero':'2'}},'Courses & Prévisions')
        self.assertEqual(len(a),1)
    def test_missing_key_fails(self):
        with self.assertRaises(ValueError):plan_sheet(['cheval'],[],{},'Courses & Prévisions')
if __name__=='__main__':unittest.main()
