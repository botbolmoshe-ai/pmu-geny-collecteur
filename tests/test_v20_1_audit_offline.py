import tempfile, unittest, json
from pathlib import Path
from pmu_geny.audit_predictif_v20_1 import analyser_course,bilan_global
from pmu_geny.ml_v19 import FEATURES

class AuditTests(unittest.TestCase):
 def test_audit_et_exclusion_cotes(self):
  self.assertFalse(any('cote' in x or 'rapport' in x for x in FEATURES))
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);key='2026-11-10_R2C8';cid='GENY-1697377'
   def write(rel,data):
    f=p/rel;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(json.dumps(data),encoding='utf8')
   write(f'arrivees/{key}.json',{'source':'PMU','arrivee':[{'numero':2,'rang':1},{'numero':4,'rang':2},{'numero':1,'rang':3}]})
   write(f'pronostics/{key}_top3.json',{'classement_complet':[{'numero':1},{'numero':2},{'numero':3},{'numero':4}]})
   write(f'pronostics/{key}_ml_latest.json',{'classement_complet':[{'numero':4},{'numero':2},{'numero':1},{'numero':3}]})
   write(f'cotes/{key}.json',{'chevaux':[{'numero':1,'cote':2.0,'heure_utc':'2026-11-10T13:59:00+00:00'},{'numero':2,'cote':3.0,'heure_utc':'2026-11-10T13:59:00+00:00'},{'numero':3,'cote':4.0,'heure_utc':'2026-11-10T13:59:00+00:00'},{'numero':4,'cote':12.0,'heure_utc':'2026-11-10T13:59:00+00:00'}]})
   course={'date':'2026-11-10','code':'R2C8','depart':'2026-11-10T15:00:00+01:00'}
   manifest={'courses':[{'course_id':cid,'partants':[{'numero':i,'nom':str(i)} for i in range(1,5)]}]}
   self.assertEqual(analyser_course(p,course,manifest),'AUDIT_ENREGISTRE')
   audit=json.loads((p/'audits'/f'{key}.json').read_text())
   self.assertEqual(audit['comparaison']['baseline_h1']['hits_top3'],2)
   self.assertEqual(audit['comparaison']['ml']['hits_top3'],3)
   self.assertEqual(audit['comparaison']['marche_indicatif']['hits_top3'],2)
   self.assertEqual(audit['diagnostic']['comparaison_ml_marche'],'ML_MIEUX')
   self.assertEqual(audit['diagnostic']['outsiders_detectes'],1)
   self.assertTrue(Path(bilan_global(p)).exists())
 def test_pas_audit_sans_arrivee(self):
  with tempfile.TemporaryDirectory() as d:
   self.assertEqual(analyser_course(d,{'date':'2026-11-10','code':'R1C1','depart':'2026-11-10T15:00:00+01:00'}, {'courses':[{'partants':[]}]}),'ARRIVEE_NON_VERIFIEE')
if __name__=='__main__':unittest.main()
