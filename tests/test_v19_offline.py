import csv,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from pmu_geny.ml_v19 import features,snapshot,dataset,train,export_comparatif,FEATURES
from pmu_geny.cotes_v19 import collecter,extraire_cote
from pmu_geny.pronostics_v18 import preparer_top3,actualiser_top3_np
from pmu_geny.auto_v18 import save

class TestV19(unittest.TestCase):
 def setUp(self):
  self.d=tempfile.TemporaryDirectory();self.addCleanup(self.d.cleanup);self.root=Path(self.d.name)
  self.now=datetime(2026,11,15,14,15,tzinfo=timezone.utc)
  self.course={'date':'2026-11-15','code':'R2C1','depart':'2026-11-15T16:30:00+01:00','nombre_declares':5,'hippodrome':'Vincennes'}
  self.manifest={'courses':[{'course_id':'GENY-99','partants':[{'numero':i,'id':str(i),'nom':f'Cheval{i}'} for i in range(1,6)]}]}
  for i in range(1,6):
   save(self.root/'historiques'/str(i)/'historique_geny.json',{'performances':[{'date':'2026-11-01','classement':str(i)}, {'date':'2026-10-20','classement':str(i)}]})
  save(self.root/'participations'/'GENY-99.json',{'date_controle_utc':self.now.isoformat(),'chevaux':[{'numero':i,'statut_participation':'PARTANT'} for i in range(1,6)]})
 def test_no_odds_in_features(self):
  self.assertFalse(any('cote' in x or 'rapport' in x for x in FEATURES))
  f=features(self.manifest['courses'][0]['partants'][0],{'performances':[{'date':'2026-11-01','classement':'1'},{'date':'2026-11-20','classement':'1'}]},self.course)
  self.assertEqual(f['courses_120j'],1)
 def test_ml_requires_labeled_historical_courses(self):
  self.assertEqual(snapshot(self.root,self.course,self.manifest,self.now),'CAPTURE')
  examples,courses=dataset(self.root)
  self.assertEqual(courses,0)
  self.assertEqual(train(self.root)['etat'],'INSUFFISANT')
 def test_cotes_before_start_only(self):
  participants={'participants':[{'numPmu':1,'rapportDirect':4.8},{'numPmu':2,'rapportDirect':0}]}
  self.assertEqual(collecter(self.root,self.course,participants,self.now),'COTES_PARTIELLES')
  data=json.loads((self.root/'cotes'/'2026-11-15_R2C1.json').read_text())
  self.assertEqual(data['chevaux'][0]['cote'],4.8)
  self.assertIsNone(data['chevaux'][1]['cote'])
  self.assertEqual(collecter(self.root,self.course,participants,self.now+timedelta(hours=2)),'APRES_DEPART_SANS_RELEVE')
 def test_dernier_rapport_direct(self):
  self.assertEqual(extraire_cote({'dernierRapportDirect':{'rapport':3.7},'rapportDirect':9}), (3.7,'dernierRapportDirect'))
  self.assertEqual(extraire_cote({'dernierRapportDirect':{'rapport':'4,2'}}), (4.2,'dernierRapportDirect'))
  for value in (0, -1, True, float('inf'), float('nan'), None):
   self.assertEqual(extraire_cote({'dernierRapportDirect':{'rapport':value}}), (None,None))
  participants={'participants':[{'numPmu':1,'dernierRapportDirect':{'rapport':3.7}}]}
  self.assertEqual(collecter(self.root,self.course,participants,self.now),'COTES_PARTIELLES')
  self.assertEqual(collecter(self.root,self.course,participants,self.now),'COTES_PARTIELLES')
  data=json.loads((self.root/'cotes'/'2026-11-15_R2C1.json').read_text())
  self.assertEqual(len(data['releves']),1)
  self.assertEqual(collecter(self.root,self.course,participants,datetime.fromisoformat(self.course['depart'])),'APRES_DEPART_SANS_RELEVE')
 def test_retrait_updates_baseline_and_csv(self):
  from zoneinfo import ZoneInfo
  now=datetime(2026,11,15,15,15,tzinfo=ZoneInfo('Europe/Paris'))
  data=json.loads((self.root/'participations'/'GENY-99.json').read_text());data['date_controle_utc']=now.isoformat();save(self.root/'participations'/'GENY-99.json',data)
  self.assertEqual(preparer_top3(self.root,self.course,self.manifest,now),'FIGE_BASELINE_EXPERIMENTALE')
  data['chevaux'][0]['statut_participation']='NON_PARTANT';data['date_controle_utc']=(now+timedelta(minutes=30)).isoformat();save(self.root/'participations'/'GENY-99.json',data)
  self.assertEqual(actualiser_top3_np(self.root,self.course,self.manifest,now+timedelta(minutes=30)),'ACTUALISE')
  latest=json.loads((self.root/'pronostics'/'2026-11-15_R2C1_baseline_latest.json').read_text())
  self.assertEqual([x['numero'] for x in latest['top3']],[2,3,4])
  path=export_comparatif(self.root,self.course,self.manifest)
  with path.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f,delimiter=';'))
  self.assertEqual(len(rows),5)
  self.assertEqual(rows[0]['baseline_top3'],'OUI')
  self.assertEqual(rows[0]['baseline_final_top3'],'')
  self.assertEqual(rows[3]['baseline_final_top3'],'OUI')
  self.assertEqual(rows[0]['ml_etat'],'ML_NON_ENTRAINE')
if __name__=='__main__':unittest.main()
