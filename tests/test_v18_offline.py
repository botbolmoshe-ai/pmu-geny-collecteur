import json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from pmu_geny.auto_v18 import programme,np_participants,update_np
from pmu_geny.pronostics_v18 import preparer_top3

class TestV18(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
  self.manifest={'courses':[{'course_id':'GENY-99','partants':[{'numero':i,'id':str(i),'nom':'Cheval'+str(i)} for i in range(1,5)]}]}
  self.course={'date':'2026-11-15','code':'R2C1','depart':'2026-11-15T16:30:00+01:00'}
 def test_programme_france(self):
  inp={'programme':{'reunions':[{'numOfficiel':2,'hippodrome':{'pays':'FRANCE','libelleCourt':'Vincennes'},'courses':[{'numOrdre':1,'heureDepart':1794756600000,'nombreDeclaresPartants':4,'libelle':'Prix exemple','specialite':'TROT_MONTE'}]}]}}
  # L'heure doit rester du même jour, pas de conversion silencieuse.
  r=programme(inp,'2026-11-15');self.assertEqual(len(r),1);self.assertEqual(r[0]['code'],'R2C1')
 def test_np_zero_requires_all_flags(self):
  participants={'participants':[{'numPmu':i,'nonPartant':False} for i in range(1,5)]}
  self.assertEqual(sum(np_participants(participants,self.manifest).values()),0)
  del participants['participants'][0]['nonPartant']
  with self.assertRaises(ValueError):np_participants(participants,self.manifest)
 def test_np_and_frozen_top3(self):
  participants={'participants':[{'numPmu':i,'nonPartant':i==4} for i in range(1,5)]}
  update_np(self.root,self.course,self.manifest,participants)
  for i in range(1,5):
   file=self.root/'historiques'/str(i)/'historique_geny.json';file.parent.mkdir(parents=True,exist_ok=True)
   file.write_text(json.dumps({'performances':[{'date':'2026-11-01','classement':str(i)}, {'date':'2026-10-20','classement':str(i)}]}))
  now=datetime(2026,11,15,15,15,tzinfo=ZoneInfo('Europe/Paris'))
  # Simuler date de validation NP dans la bonne fenêtre temporelle.
  p=self.root/'participations'/'GENY-99.json';doc=json.loads(p.read_text());doc['date_controle_utc']=now.astimezone(timezone.utc).isoformat();p.write_text(json.dumps(doc))
  result=preparer_top3(self.root,self.course,self.manifest,now)
  self.assertEqual(result,'FIGE_BASELINE_EXPERIMENTALE')
  saved=json.loads((self.root/'pronostics'/'2026-11-15_R2C1_top3.json').read_text())
  self.assertEqual([x['numero'] for x in saved['top3']],[1,2,3])
  self.assertEqual(preparer_top3(self.root,self.course,self.manifest,now+timedelta(minutes=5)),'DEJA_FIGE')
if __name__=='__main__':unittest.main()
