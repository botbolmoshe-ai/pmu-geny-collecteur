"""Contrats observés PMU/Equidia/ZEturf : identité, temps, profils et exports."""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from pmu_geny.sources_experts_v23 import (parser_equidia,parser_zeturf,parser_pmu,
    collecter,champs_sheet,completer_partants,links)
from pmu_geny.partants_actuels_v21 import enregistrer
from pmu_geny.sync_google_sheets import plan_sheet
C={'date':'2026-11-12','code':'R1C1','nom':'PRIX TEST','hippodrome':'HIPPODROME DE PARIS-VINCENNES','depart':'2026-11-12T13:55:00+01:00'}
RAW={'participants':[{'numPmu':1,'nom':'TEST CHEVAL','age':5,'sexe':'MALES','statut':'PARTANT'}]}
P={'1':{'nom':'TEST CHEVAL'}}
NOW=datetime(2026,11,11,20,0,tzinfo=timezone.utc)
EQ={'v2/courses/2026-11-12/R1/C1':{'reunion':{'date_reunion':'2026-11-12','lib_reunion':'PARIS-VINCENNES'},'liblong_prix_course':'PRIX TEST','partants':[{'num_partant':1,'cheval':{'nom_cheval':'TEST CHEVAL','age_cheval':5,'sexe_cheval':'M','gains_carriere':888175}}]},'courses/2026-11-12/R1/C1/pronostic':{'status':'published','pronostic_analyses':[{'num_partant':1,'cheval':{'nom_cheval':'TEST CHEVAL'},'position':1,'analysis_horse':'Commentaire publié.'}]}}
def eqhtml(d=EQ):return '<script id="serverApp-state" type="application/json">'+json.dumps(d)+'</script>'
ZE='''<h1 class="nom-course"><span class="hippodrome">VINCENNES</span>12/11/2026</h1><h2 class="nom-course">Prix Test</h2><table class="table-runners"><tr data-runner="1"><td><a class="horse-name">TEST CHEVAL (NP)<span>tooltip</span></a></td><td class="record"><b>1\'10"2</b><br>888 175 €</td><td class="sexe-age">M/5</td><td><div id="deferres-1_content" role="tooltip">Déferré des postérieurs et plaqué des antérieurs</div></td><td class="info"><span class="score-ia-hidden">Commentaire ZEturf.</span></td></tr></table><div class="prono-cards"><span class="numero-cheval-card">1</span></div>'''
PR={'dateReunion':1794438000000,'numeroReunion':1,'numeroCourse':1,'selection':[{'num_partant':1,'rang':1,'id_nav_partant':'20261112-VIN-1-1','commentaire':'Commentaire publié.'}]}
class TestSources(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def fetch(self,url):
  if '/pronostics' in url:return json.dumps(PR)
  if 'equidia.fr/courses/' in url:return eqhtml()
  if '/programmes-et-pronostics-' in url:return '<a href="/fr/reunion-du-jour/2026-11-12/R3-vincennes">Vincennes</a>'
  if '/reunion-du-jour/' in url:return '<a href="/fr/course-du-jour/2026-11-12/R3C1-vincennes-prix-test">Test</a>'
  if '/course-du-jour/' in url:return ZE
  raise AssertionError(url)
 def test_observed_schemas_and_gain_not_chrono(self):
  eq=parser_equidia(eqhtml(),C,P);ze=parser_zeturf(ZE,C,P)
  self.assertEqual(eq['pronostic'],[1]);self.assertEqual(ze['pronostic'],[1])
  self.assertEqual(ze['chevaux']['1']['profil']['gains_euros'],888175)
  self.assertEqual(ze['chevaux']['1']['profil']['ferrure'],'DP/PA')
  self.assertEqual(parser_pmu(PR,C,P)['pronostic'],[1])
 def test_wrong_race_date_name_and_horse_rejected(self):
  with self.assertRaises(ValueError):parser_equidia(eqhtml(),{**C,'nom':'PRIX AUTRE'},P)
  with self.assertRaises(ValueError):parser_zeturf(ZE.replace('12/11/2026','13/11/2026'),C,P)
  with self.assertRaises(ValueError):parser_pmu({**PR,'numeroCourse':2},C,P)
  self.assertEqual(parser_equidia(eqhtml(),C,{'1':{'nom':'TEST CHEVAL II'}})['chevaux'],{})
  self.assertEqual(parser_zeturf(ZE,C,{'1':{'nom':'TEST CHEVAL II'}})['pronostic'],[])
 def test_collecte_pmu_seule_cache_et_aucun_complement_tiers(self):
  enregistrer(self.root,C,RAW)
  called=[]
  def fetch(url):
   called.append(url)
   return self.fetch(url)
  self.assertEqual(collecter(self.root,C,RAW,NOW,fetch),'EXPERTS_1_SUR_1')
  d=json.loads((self.root/'avis_experts/2026-11-12_R1C1.json').read_text())
  self.assertEqual(set(d['sources']),{'pmu'})
  self.assertEqual(len(called),1);self.assertIn('online.turfinfo.api.pmu.fr',called[0])
  act=json.loads((self.root/'partants_actuels/2026-11-12_R1C1.json').read_text())['chevaux']['1']
  self.assertNotIn('gains_euros',act);self.assertNotIn('ferrure',act)
  self.assertEqual(act['statut_np'],'PARTANT')
  self.assertEqual(collecter(self.root,C,RAW,NOW,lambda _:self.fail('cache non réutilisé')),'EXPERTS_1_SUR_1')
  self.assertEqual(champs_sheet(d,'1').get('prono_zeturf',''),'')
  self.assertEqual(champs_sheet(d,'1')['prono_pmu'],'1')
 def test_secondary_title_and_changed_horse(self):
  self.assertEqual(parser_zeturf(ZE.replace('Prix Test</h2>','Prix Test (Prix Ancien)</h2>'),C,P)['pronostic'],[1])
  d={'version':23,'sources':{'equidia':{}},'chevaux':{'1':{'nom':'TEST CHEVAL','avis_equidia':'ancien'}}}
  self.assertEqual(champs_sheet(d,'1','AUTRE CHEVAL').get('avis_equidia',''),'')
 def test_same_race_links_with_bet_queries_are_one_candidate(self):
  self.assertEqual(links('<a href="/fr/race?prefill=1">a</a><a href="/fr/race?prefill=3">b</a><a href="https://other.fr/fr/race">c</a>',r'/fr/race'),['/fr/race'])
 def test_after_depart_no_fetch_or_write(self):
  after=datetime(2026,11,12,14,tzinfo=timezone.utc)
  self.assertEqual(collecter(self.root,C,RAW,after,lambda _:self.fail('requête après départ')),'APRES_DEPART')
  self.assertFalse((self.root/'avis_experts').exists())
 def test_unavailable_never_neutral_and_legacy_not_relabelled(self):
  def fail(url):raise OSError('indisponible')
  collecter(self.root,C,RAW,NOW,fail)
  d=json.loads((self.root/'avis_experts/2026-11-12_R1C1.json').read_text())
  self.assertNotIn('equidia',d['sources'])
  self.assertEqual(d['sources']['pmu']['statut_pronostic'],'NON_PUBLIE_OU_NON_ACCESSIBLE')
  self.assertEqual(champs_sheet(d,'1').get('avis_equidia',''),'')
  self.assertEqual(champs_sheet({'chevaux':{'1':{'avis_zone_turf':'ancien avis'}}},'1').get('avis_zeturf',''),'')
 def test_empty_expert_value_clears_stale_cell(self):
  h=['course_key','numero','avis_equidia'];rows=[dict(zip(h,['k','1','ancien']))]
  _,changes,_=plan_sheet(h,rows,{'x':{'course_key':'k','numero':'1','avis_equidia':''}},'Courses & Prévisions')
  self.assertIn((2,3,''),changes)

 def test_colonne_equidia_supprimee_non_recreee_et_voisine_preservee(self):
  headers=['course_key','numero','avis_pmu','avis_zeturf']
  rows=[dict(zip(headers,['k','1','Avis PMU','']))]
  actual,updates,appends=plan_sheet(headers,rows,{'k':{'course_key':'k','numero':'1',
      'avis_equidia':'','avis_pmu':'Avis PMU actualisé'}},'Courses & Prévisions')
  self.assertNotIn('avis_equidia',actual)
  self.assertIn((2,3,'Avis PMU actualisé'),updates)
  self.assertEqual(appends,[])
 def test_caracteristiques_pmu_sont_conservees_sans_lecture_tierce(self):
  enregistrer(self.root,C,{ 'participants':[ {**RAW['participants'][0],'gainsCarriere':777000}]})
  collecter(self.root,C,RAW,NOW,self.fetch)
  act=json.loads((self.root/'partants_actuels/2026-11-12_R1C1.json').read_text())['chevaux']['1']
  self.assertEqual(act['gains_euros'],777000)
  self.assertEqual(act['divergences_sources'],[])

 def test_anciens_avis_tiers_ne_sont_plus_republies(self):
  legacy={'version':23,'sources':{'pmu':{'parametres':{'conditions':'Conditions PMU'}},
       'equidia':{'url':'https://www.equidia.fr','pronostic':[1]},
       'zeturf':{'url':'https://www.zeturf.fr','pronostic':[1]}},
       'chevaux':{'1':{'nom':'TEST CHEVAL','avis_pmu':'Texte PMU',
                      'avis_equidia':'Texte Equidia','avis_zeturf':'Texte ZEturf'}}}
  fields=champs_sheet(legacy,'1','TEST CHEVAL')
  self.assertEqual(fields['avis_pmu'],'Texte PMU')
  for source in ('equidia','zeturf'):
   for prefix in ('avis_','prono_','source_'):self.assertNotIn(prefix+source,fields)
  self.assertEqual(fields['conditions_course'],'Conditions PMU')
  self.assertEqual(fields['synthese_actualite'],'PMU: Texte PMU')

 def test_anciens_complements_tiers_retires_sans_effacer_pmu(self):
  enregistrer(self.root,C,RAW)
  path=self.root/'partants_actuels/2026-11-12_R1C1.json'
  data=json.loads(path.read_text());h=data['chevaux']['1']
  h.update(ferrure='D4',gains_euros=20000,provenance_champs={
     'ferrure':{'source':'equidia'},'gains_euros':{'source':'zeturf'},
     'age_ans':{'source':'PMU_API_PARTICIPANTS'}})
  path.write_text(json.dumps(data))
  completer_partants(self.root,C)
  h=json.loads(path.read_text())['chevaux']['1']
  self.assertNotIn('ferrure',h);self.assertNotIn('gains_euros',h)
  self.assertEqual(h['age_ans'],5)

 def test_reseau_equidia_et_zeturf_refuse_avant_requete(self):
  from pmu_geny.sources_experts_v23 import fetch_public
  with patch('pmu_geny.sources_experts_v23.urlopen') as opening:
   for url in ('https://www.equidia.fr/courses/test','https://www.zeturf.fr/fr/test'):
    with self.assertRaisesRegex(ValueError,'HOTE_NON_AUTORISE'):fetch_public(url)
   opening.assert_not_called()

 def test_capture_ml_ne_complete_plus_les_criteres_depuis_zone_turf(self):
  from pmu_geny.ml_v19 import snapshot_pmu
  path=self.root/'avis_experts/2026-11-12_R1C1.json';path.parent.mkdir(parents=True)
  path.write_text(json.dumps({'chevaux':{'1':{'profil_zone_turf':{
       'age_ans':9,'gains_euros':999999,'sexe':'Femelle','ferrure':'D4'}}}}))
  raw={'participants':[{'numPmu':n,'nom':'CHEVAL '+str(n),'nonPartant':False} for n in range(1,4)]}
  self.assertEqual(snapshot_pmu(self.root,C,raw,NOW),'CAPTURE_PMU')
  path=self.root/'ml/instantanes/2026-11-12_R1C1.json'
  captured=path.read_bytes();features=json.loads(captured)['chevaux'][0]['features']
  for key in ('age_ans','gains_euros','sexe_femelle','ferrure_d4'):
   self.assertIsNone(features[key])
  raw['participants'][0].update(age=8,gainsCarriere=100000)
  self.assertEqual(snapshot_pmu(self.root,C,raw,NOW),'DEJA_CAPTURE')
  self.assertEqual(path.read_bytes(),captured)

 def test_vider_un_critere_courant_ne_vide_pas_une_ferrure_historique(self):
  headers=['cle_performance','ferrure']
  _,updates,_=plan_sheet(headers,[{'cle_performance':'k','ferrure':'D4'}],
      {'k':{'cle_performance':'k','ferrure':''}},'Historique chevaux')
  self.assertEqual(updates,[])
  _,updates,_=plan_sheet(['course_key','numero','ferrure'],
      [{'course_key':'k','numero':'1','ferrure':'D4'}],
      {'k':{'course_key':'k','numero':'1','ferrure':''}},'Courses & Prévisions')
  self.assertIn((2,3,''),updates)
if __name__=='__main__':unittest.main()
