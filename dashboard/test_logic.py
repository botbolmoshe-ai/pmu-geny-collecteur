import unittest
from datetime import datetime,timezone
from trot_analytics.logic import records,selected,matching,result_matching
class Tests(unittest.TestCase):
    def test_matching(self):
        self.assertEqual([matching(x) for x in (0,1,2,3,None,'')],[0,33.33,66.67,100,None,None])
    def test_selection(self):
        rows=[{'N°':i,'TOP3 direct · Sélection':'OUI','TOP3 direct · Rang':i,'Non-partant (NP)':'PARTANT'} for i in (1,2,3)]
        self.assertEqual(len(selected(rows,'direct')),3)
        rows[0]['Non-partant (NP)']='NON_PARTANT'
        self.assertEqual(selected(rows,'direct'),[])
    def test_records(self):
        self.assertEqual(records([['a','b'],[1,2],[]]),[{'a':1,'b':2}])
    def test_result(self):
        row={'Départ (Paris)':'2026-11-17T13:00:00+01:00','Arrivée · Vérifiée UTC':'2026-11-17T13:10:00+01:00','Évaluation · État':'EVALUE','Arrivée · N° officiels':'1,2,3','TOP3 direct · Chevaux':'1,2,4','TOP3 direct · Heure calcul UTC':'2026-11-17T12:00:00+01:00','TOP3 direct · Chevaux à l’arrivée (0–3)':2}
        now=datetime(2026,11,17,14,tzinfo=timezone.utc)
        self.assertEqual(result_matching(row,'direct',now),66.67)
        self.assertIsNone(result_matching(row,'ml',now))
        row['TOP3 direct · Heure calcul UTC']=row['Départ (Paris)']
        self.assertIsNone(result_matching(row,'direct',now))
if __name__=='__main__': unittest.main()
