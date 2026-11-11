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
 def test_collect_cache_duplicate_text_and_complete_only_gaps(self):
  enregistrer(self.root,C,RAW)
  self.assertEqual(collecter(self.root,C,RAW,NOW,self.fetch),'EXPERTS_3_SUR_3')
  d=json.loads((self.root/'avis_experts/2026-11-12_R1C1.json').read_text())
  self.assertEqual(d['avis_identiques'][0]['sources'],['pmu','equidia'])
  act=json.loads((self.root/'partants_actuels/2026-11-12_R1C1.json').read_text())['chevaux']['1']
  self.assertEqual(act['gains_euros'],888175);self.assertEqual(act['ferrure'],'DP/PA')
  self.assertEqual(act['provenance_champs']['gains_euros']['source'],'equidia')
  self.assertEqual(act['statut_np'],'PARTANT')
  self.assertEqual(collecter(self.root,C,RAW,NOW,lambda _:self.fail('cache non réutilisé')),'EXPERTS_3_SUR_3')
  self.assertEqual(champs_sheet(d,'1')['prono_zeturf'],'1')
 def test_secondary_title_and_changed_horse(self):
  self.assertEqual(parser_zeturf(ZE.replace('Prix Test</h2>','Prix Test (Prix Ancien)</h2>'),C,P)['pronostic'],[1])
  d={'version':23,'sources':{'equidia':{}},'chevaux':{'1':{'nom':'TEST CHEVAL','avis_equidia':'ancien'}}}
  self.assertEqual(champs_sheet(d,'1','AUTRE CHEVAL')['avis_equidia'],'')
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
  self.assertEqual(d['sources']['equidia']['statut'],'INDISPONIBLE')
  self.assertEqual(champs_sheet(d,'1')['avis_equidia'],'')
  self.assertEqual(champs_sheet({'chevaux':{'1':{'avis_zone_turf':'ancien avis'}}},'1')['avis_zeturf'],'')
 def test_empty_expert_value_clears_stale_cell(self):
  h=['course_key','numero','avis_equidia'];rows=[dict(zip(h,['k','1','ancien']))]
  _,changes,_=plan_sheet(h,rows,{'x':{'course_key':'k','numero':'1','avis_equidia':''}},'Courses & Prévisions')
  self.assertIn((2,3,''),changes)
 def test_source_conflict_keeps_pmu(self):
  enregistrer(self.root,C,{ 'participants':[ {**RAW['participants'][0],'gainsCarriere':777000}]})
  collecter(self.root,C,RAW,NOW,self.fetch)
  act=json.loads((self.root/'partants_actuels/2026-11-12_R1C1.json').read_text())['chevaux']['1']
  self.assertEqual(act['gains_euros'],777000)
  self.assertTrue(any(x['champ']=='gains_euros' for x in act['divergences_sources']))
if __name__=='__main__':unittest.main()
