import unittest
from pmu_geny.rapprochement_v20_6 import rapprocher,index_from_anchors

BASE='https://www.geny.com/course/123-2026-11-11-vincennes-prix-de-beauvais'
COURSE={'date':'2026-11-11','hippodrome':'HIPPODROME DE PARIS-VINCENNES','nom':'Prix de Beauvais','num_reunion':2,'num_course':4}

class TestRC(unittest.TestCase):
    def test_direct(self):
        x=index_from_anchors([{'href':BASE,'r':2,'c':4}], '2026-11-11')
        d=rapprocher(COURSE,x)
        self.assertEqual(d['methode'],'DATE_HIPPODROME_RC')
    def test_wrong_hippodrome(self):
        x=index_from_anchors([{'href':BASE.replace('vincennes','reims'),'r':2,'c':4}], '2026-11-11')
        self.assertNotEqual(rapprocher(COURSE,x)['statut'],'CORRESPONDANCE_CONFIRMEE')
    def test_wrong_date(self):
        x=index_from_anchors([{'href':BASE.replace('2026-11-11','2026-11-10'),'r':2,'c':4}], '2026-11-10')
        self.assertNotEqual(rapprocher(COURSE,x)['statut'],'CORRESPONDANCE_CONFIRMEE')
    def test_duplicate_codes(self):
        x=index_from_anchors([{'href':BASE,'r':2,'c':4},{'href':BASE.replace('123','456'),'r':2,'c':4}], '2026-11-11')
        self.assertEqual(rapprocher(COURSE,x)['statut'],'CORRESPONDANCE_AMBIGUE')
    def test_conflicting_name(self):
        x=index_from_anchors([{'href':BASE.replace('beauvais','paris'),'r':2,'c':4}], '2026-11-11')
        self.assertEqual(rapprocher(COURSE,x)['statut'],'CONFLIT_CODE_ET_NOM')
    def test_fallback(self):
        x=index_from_anchors([{'href':BASE}], '2026-11-11')
        self.assertEqual(rapprocher(COURSE,x)['methode'],'NOM_SECOURS')
    def test_conflicting_codes_not_silently_name_matched(self):
        x=index_from_anchors([{'href':BASE,'r':2,'c':5}], '2026-11-11')
        self.assertEqual(rapprocher(COURSE,x)['statut'],'AUCUNE_CORRESPONDANCE_FIABLE')
    def test_index_keeps_rc(self):
        x=index_from_anchors([{'href':BASE,'text':'Partants','r':'2','c':'4'}, {'href':BASE+'/partants-pronostics','text':'Plus de texte'}], '2026-11-11')
        self.assertEqual((x[0]['r'],x[0]['c']),(2,4))

if __name__=='__main__': unittest.main()
