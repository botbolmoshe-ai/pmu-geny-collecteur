"""Regressions expert opinions and auditable horse identity."""
import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from pmu_geny.liaison_chevaux_v22 import etablir
from pmu_geny.avis_experts_v22 import collecter, parser_zone_quinte, url_quinte
from pmu_geny.sync_google_sheets import source_rows

COURSE={'date':'2026-11-12','code':'R1C1',
        'nom':'PRIX MARCEL LAURENT','hippodrome':'HIPPODROME DE PARIS-VINCENNES',
        'depart':'2026-11-12T13:55:00+01:00'}
HTML='''<html><body><h1>Tiercé Quarté Quinté Vincennes Prix Marcel Laurent</h1>
<table><tr><th>N°</th><th>Cheval</th><th>Avis</th></tr>
<tr><td>1</td><td>Lombok Jiel DP/PA</td><td><img alt="Positif" src="avis.png"></td></tr>
<tr><td>2</td><td>Frank Gio D4</td><td><img alt="Neutre"></td></tr>
<tr><td>3</td><td>Magic Night</td><td><img alt="Négatif"></td></tr>
</table></body></html>'''

class TestExpertsAndIdentity(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)
 def write(self,path,data):
  target=self.root/path;target.parent.mkdir(parents=True,exist_ok=True)
  target.write_text(json.dumps(data),encoding='utf-8')
 def test_date_source(self):
  self.assertEqual(url_quinte('2026-11-12'),
                   'https://www.zone-turf.fr/quinte/jeudi-12-novembre-2026/')
 def test_zone_expert_exact_num_name_before_depart(self):
  raw={'participants':[{'numPmu':1,'nomCheval':'Lombok Jiel'},
                        {'numPmu':2,'nomCheval':'Frank Gio'},
                        {'numPmu':3,'nomCheval':'Magic Night'}]}
  now=datetime(2026,11,11,13,0,tzinfo=timezone.utc)
  self.assertEqual(collecter(self.root,COURSE,raw,now,fetch=lambda url:HTML),
                   'ZONE_TURF_AVIS_RECUPERES')
  d=json.loads((self.root/'avis_experts/2026-11-12_R1C1.json').read_text())
  self.assertEqual(d['chevaux']['1']['avis_zone_turf'],'Avis positif (Zone-Turf)')
  self.assertEqual(d['chevaux']['2']['avis_zone_turf'],'Avis neutre (Zone-Turf)')
  self.assertEqual(d['chevaux']['3']['avis_zone_turf'],'Avis negatif (Zone-Turf)')
  self.assertEqual(collecter(self.root,COURSE,raw,now,fetch=lambda url:None),
                   'ZONE_TURF_AVIS_RECUPERES')
 def test_ambiguous_horse_name_and_race_never_attributed(self):
  self.assertEqual(parser_zone_quinte(HTML,{**COURSE,'nom':'PRIX AUTRE'}, {'1':{'nom':'Lombok Jiel'}}),{})
  self.assertEqual(parser_zone_quinte(HTML,COURSE,{'1':{'nom':'Cheval Different'}}),{})
 def test_stable_geny_id_first_over_name(self):
  self.write('etat_persistant.json',{'chevaux':{
    '1111':{'nom':'Lombok Jiel','statut':'COMPLET'},
    '2222':{'nom':'Lombok Jiel','statut':'COMPLET'}}})
  for ident in ('1111','2222'):
   self.write(f'historiques/{ident}/historique_geny.json',
     {'statut':'COMPLET','performances':[{'date':'2026-01-01','classement':'1'}]})
  self.write('orchestration/correspondances_geny.json',{'2026-11-12_R1C1':'GENY-9999'})
  self.write('manifestes/GENY-9999.json',{'courses':[{'course_id':'GENY-9999',
    'partants':[{'numero':1,'nom':'Lombok Jiel','id':'1111'}]}]})
  got=etablir(self.root,COURSE,[{'numero':1,'nom':'Lombok Jiel'}])
  self.assertEqual(got['1']['cheval_id'],'1111')
  self.assertEqual(got['1']['methode'],'ID_GENY_MANIFESTE_VERIFIE')
  got=etablir(self.root,COURSE,[{'numero':1,'nom':'Autre Cheval'}])
  self.assertEqual(got['1']['methode'],'NON_ASSOCIE')
  got=etablir(self.root,COURSE,[{'numero':1,'nom':'Lombok Jiel'}])
  self.assertEqual(got['1']['methode'],'ID_GENY_MANIFESTE_VERIFIE')
  (self.root/'orchestration/correspondances_geny.json').unlink()
  got=etablir(self.root,COURSE,[{'numero':1,'nom':'Lombok Jiel'}])
  self.assertEqual(got['1']['methode'],'NOM_AMBIGU')

if __name__=='__main__':unittest.main()
