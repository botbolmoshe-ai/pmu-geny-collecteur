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
  self.assertEqual(got['1']['methode'],'NOM_AMBIGU_ID_CONFIRME')
  got=etablir(self.root,COURSE,[{'numero':1,'nom':'Autre Cheval'}])
  self.assertEqual(got['1']['methode'],'NON_ASSOCIE')
  got=etablir(self.root,COURSE,[{'numero':1,'nom':'Lombok Jiel'}])
  self.assertEqual(got['1']['methode'],'NOM_AMBIGU_ID_CONFIRME')
  (self.root/'orchestration/correspondances_geny.json').unlink()
  got=etablir(self.root,COURSE,[{'numero':1,'nom':'Lombok Jiel'}])
  self.assertEqual(got['1']['methode'],'NOM_AMBIGU')

 def test_partant_age_sexe_gains_ferrure(self):
  from pmu_geny.partants_actuels_v21 import extraire_partants
  d=extraire_partants({'participants':[{
   'numPmu':1,'nomCheval':'LOMBOK JIEL','age':5,'sexe':'M',
   'gainsCarriere':888175,'ferrure':'DP/PA','nonPartant':False}]})
  self.assertEqual(d[1]['age_ans'],5)
  self.assertEqual(d[1]['sexe'],'Mâle')
  self.assertEqual(d[1]['gains_euros'],888175)
  self.assertEqual(d[1]['ferrure'],'DP/PA')
 def test_public_pmu_centimes_and_shoeing_enums(self):
  from pmu_geny.partants_actuels_v21 import extraire_partants
  raw={'participants':[
   {'numPmu':1,'nom':'LOMBOK JIEL','age':5,'sexe':'MALES',
    'deferre':'PROTEGE_ANTERIEURS_DEFERRRE_POSTERIEURS',
    'gainsParticipant':{'gainsCarriere':88817500}},
   {'numPmu':2,'nom':'FRANK GIO','age':5,'sexe':'MALES',
    'deferre':'DEFERRE_ANTERIEURS',
    'gainsParticipant':{'gainsCarriere':140059000}},
   {'numPmu':3,'nom':'TROT TEST','age':5,'sexe':'HONGRES',
    'deferre':'DEFERRE_ANTERIEURS_POSTERIEURS',
    'gainsParticipant':{'gainsCarriere':3250000}}]}
  d=extraire_partants(raw)
  self.assertEqual((d[1]['ferrure'],d[1]['sexe'],d[1]['gains_euros']),
                   ('DP/PA','Mâle',888175))
  self.assertEqual((d[2]['ferrure'],d[2]['gains_euros']),('DA',1400590))
  self.assertEqual((d[3]['ferrure'],d[3]['sexe'],d[3]['gains_euros']),
                   ('D4','Hongre',32500))

 def test_historic_ferrure_explicit_only(self):
  from pmu_geny.partants_actuels_v21 import ferrure_historique_explicite
  self.assertEqual(ferrure_historique_explicite('Vincennes 2100 D4 1e'),'D4')
  self.assertEqual(ferrure_historique_explicite('Vincennes 2100 D - dur 5e'),'')
 def test_real_archived_zone_profile(self):
  from pmu_geny.avis_experts_v22 import parser_zone_profils
  ref=Path('reference_pmu')
  page=ref/'avis_experts/pages/2026-11-12_quinte.html'
  entrants=ref/'partants_actuels/2026-11-12_R1C1.json'
  if not page.exists() or not entrants.exists():self.skipTest('archives non montées')
  raw=json.loads(entrants.read_text(encoding='utf-8'))
  participants=raw['chevaux']
  result=parser_zone_profils(page.read_text(encoding='utf-8'),COURSE,participants)
  self.assertIn('1',result)
  self.assertEqual(result['1']['age_ans'],5)
  self.assertEqual(result['1']['sexe'],'Mâle')
  self.assertEqual(result['1']['gains_euros'],888175)
  self.assertEqual(result['1']['ferrure'],'DP/PA')
 def test_report_fields_are_compact_and_essential(self):
  from pmu_geny.sync_google_sheets import REPORT_COLUMNS,DISPLAY_NAMES,canonical_headers
  self.assertEqual(len(REPORT_COLUMNS),36)
  for nums, names in (('top3_direct_numeros','top3_direct_noms'),
                      ('top3_ml_numeros','top3_ml_noms'),
                      ('arrivee_officielle_numeros','arrivee_officielle_noms')):
   self.assertEqual(REPORT_COLUMNS[REPORT_COLUMNS.index(nums)+1],names)
  self.assertEqual(REPORT_COLUMNS[18:20],('matching_direct_pct','matching_ml_pct'))
  for mode in ('direct','ml'):
   start=REPORT_COLUMNS.index(f'gagnant_{mode}_numero')
   self.assertEqual(REPORT_COLUMNS[start:start+4],
                    tuple(f'gagnant_{mode}_{field}' for field in ('numero','nom','rang','verdict')))
  self.assertEqual(canonical_headers([DISPLAY_NAMES[x] for x in REPORT_COLUMNS]),list(REPORT_COLUMNS))

if __name__=='__main__':unittest.main()
