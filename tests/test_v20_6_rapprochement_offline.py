import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from pmu_geny.rapprochement_v20_6 import index_from_anchors, rapprocher
from pmu_geny.planification_v20_2 import selectionner_courses

class Correspondances(unittest.TestCase):
    def test_vincennes_exact(self):
        c={'nom':'Prix de Beauvais','hippodrome':'HIPPODROME DE PARIS-VINCENNES'}
        a=[{'href':'https://www.geny.com/course/1697377-2026-11-10-vincennes-prix-de-beauvais/partants-pronostics', 'text':'Partants / Pronos / Stats'}]
        idx=index_from_anchors(a,'2026-11-10')
        self.assertEqual(len(idx),1)
        d=rapprocher(c,idx)
        self.assertEqual(d['statut'],'CORRESPONDANCE_CONFIRMEE')
        self.assertEqual(d['geny_id'],'1697377')
    def test_other_hippodrome_never_matched(self):
        c={'nom':'Prix de Beauvais','hippodrome':'HIPPODROME DE PARIS-VINCENNES'}
        idx=index_from_anchors([{'href':'https://www.geny.com/course/100-2026-11-10-reims-prix-de-beauvais','text':''}], '2026-11-10')
        self.assertNotEqual(rapprocher(c,idx)['statut'],'CORRESPONDANCE_CONFIRMEE')
    def test_short_name_sponsor(self):
        c={'nom':'Prix Bellino II','hippodrome':'HIPPODROME DE LYON-LA SOIE'}
        idx=index_from_anchors([{'href':'https://www.geny.com/course/123-2026-11-11-lyon-la-soie-prix-bellino-ii','text':'Partants'}],'2026-11-11')
        self.assertEqual(rapprocher(c,idx)['statut'],'CORRESPONDANCE_CONFIRMEE')
    def test_ambiguous_same_race(self):
        c={'nom':'Prix de Beauvais','hippodrome':'Vincennes'}
        idx=index_from_anchors([{'href':f'https://www.geny.com/course/{i}-2026-11-10-vincennes-prix-de-beauvais','text':''} for i in [123,456]],'2026-11-10')
        self.assertEqual(rapprocher(c,idx)['statut'],'CORRESPONDANCE_AMBIGUE')
    def test_no_name_match(self):
        c={'nom':'Prix de Beauvais','hippodrome':'Vincennes'}
        idx=index_from_anchors([{'href':'https://www.geny.com/course/123-2026-11-10-vincennes-prix-de-paris','text':''}],'2026-11-10')
        self.assertNotEqual(rapprocher(c,idx)['statut'],'CORRESPONDANCE_CONFIRMEE')
    def test_future_selection_on_light_when_explicitly_enabled(self):
        p=ZoneInfo('Europe/Paris')
        now=datetime(2026,11,10,18,15,tzinfo=p)
        c={'code':'R4C1','depart':datetime(2026,11,11,15,30,tzinfo=p).isoformat(),'priorite_metier':'P1'}
        self.assertEqual(len(selectionner_courses([c],now,'2026-11-11',[],True,{})),1)
    def test_dedup_links(self):
        url='https://www.geny.com/course/123-2026-11-11-vincennes-prix-test'
        a=[{'href':url,'text':''},{'href':url+'/partants-pronostics','text':'Prix Test'}]
        self.assertEqual(len(index_from_anchors(a,'2026-11-11')),1)
if __name__=='__main__': unittest.main()
