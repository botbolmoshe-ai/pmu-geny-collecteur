import csv, json, tempfile, unittest
from pathlib import Path
from pmu_geny.export_v17 import exporter
from pmu_geny.participation_pmu import enregistrer

class TestV17(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.manifest={'courses':[{'course_id':'GENY-1697377', 'nombre_partants_attendu':3,
    'partants':[{'id':str(1000+i),'numero':i+1,'nom':f'Cheval{i}'} for i in range(3)]}]}
  for i in range(3):
   f=self.root/'historiques'/str(1000+i)/'historique_geny.json'
   f.parent.mkdir(parents=True,exist_ok=True)
   f.write_text(json.dumps({'statut':'COMPLET','nombre_annonce_geny':1,'nombre_extrait':1,
      'performances':[{'date':'2026-10-10','hippodrome':'Vincennes','classement':'Di'}]}))
 def test_empty_control_means_unknown(self):
  summary=exporter(self.manifest,self.root,self.root/'exports')[0]
  self.assertEqual(summary['np_non_verifie'],3)
  self.assertEqual(summary['performances'],3)
  with (self.root/'exports/GENY-1697377/suivi_chevaux.csv').open(encoding='utf-8-sig',newline='') as f:
   rows=list(csv.DictReader(f,delimiter=';'))
  self.assertEqual(len(rows),3)
  self.assertTrue(all(r['eligible_top3']=='A_VERIFIER' for r in rows))
 def test_pmu_confirmation_and_export(self):
  enregistrer(self.manifest,self.root/'participations','https://www.pmu.fr/turf/', '1,3',True,True)
  summary=exporter(self.manifest,self.root,self.root/'exports')[0]
  self.assertEqual(summary['np_confirme'],2)
  self.assertEqual(summary['np_non_verifie'],0)
  with (self.root/'exports/GENY-1697377/suivi_chevaux.csv').open(encoding='utf-8-sig',newline='') as f:
   rows=list(csv.DictReader(f,delimiter=';'))
  self.assertEqual([r['eligible_top3'] for r in rows],['NON','OUI','NON'])
 def test_partial_confirmation(self):
  enregistrer(self.manifest,self.root/'participations','https://pmu.fr/turf/', '2',False,True)
  summary=exporter(self.manifest,self.root,self.root/'exports')[0]
  self.assertEqual(summary['np_confirme'],1)
  self.assertEqual(summary['np_non_verifie'],2)
 def test_unverified_source_refused(self):
  with self.assertRaises(ValueError):
   enregistrer(self.manifest,self.root/'participations','https://example.org/', '1',True,True)
  with self.assertRaises(ValueError):
   enregistrer(self.manifest,self.root/'participations','https://www.pmu.fr/turf/', '1',True,False)

if __name__=='__main__': unittest.main()
