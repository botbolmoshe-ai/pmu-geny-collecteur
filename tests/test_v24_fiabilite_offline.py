"""Regressions metier: musique PMU reelle, retraits, registre et KPI sans reseau."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pmu_geny.top3_independants_v22 import _musique, _form_score, calculer
from pmu_geny.pronostics_v18 import preparer_top3, actualiser_top3_np
from pmu_geny.kpi_registre import calculer_kpi, plan_kpi
from pmu_geny.sync_google_sheets import plan_sheet

NOW=datetime(2026,11,12,12,tzinfo=timezone.utc)

def write(path,doc):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(doc),encoding='utf-8')

class MusiqueTests(unittest.TestCase):
    def test_compact_and_spaced_have_identical_tokens_and_score(self):
        self.assertEqual(_musique('1a2a3a'),['1a','2a','3a'])
        self.assertEqual(_form_score({'musique':'1a2a3a'}),9.98)
        self.assertEqual(_form_score({'musique':'1a2a3a'}),_form_score({'musique':'1a 2a 3a'}))

    def test_years_and_two_digit_positions(self):
        self.assertEqual(_musique('12a(25)2a3m(2024)Da'),['12a','2a','3m','Da'])
        self.assertEqual(_form_score({'musique':'12a'}),0)
        self.assertEqual(_form_score({'musique':'1a(25)2a3a'}),9.98)

    def test_disqualifications_do_not_hide_the_next_performance(self):
        self.assertEqual(_musique('DaDa1a'),['Da','Da','1a'])
        self.assertEqual(_form_score({'musique':'DaDa1a'}),3.8)
        self.assertEqual(_musique('Da0aTaAaRa1a'),['Da','0a','Ta','Aa','Ra'])

    def test_archive_and_invalid_formats(self):
        self.assertEqual(_musique({'libelle':'1-2-3'}),['1','2','3'])
        self.assertEqual(_musique('inconnue'),[])
        self.assertIsNone(_form_score({'musique':None}))

class RetraitTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.course={'date':'2026-11-12','code':'R1C1','depart':(NOW+timedelta(minutes=65)).isoformat(),'nombre_declares':4}
        self.raw={'participants':[{'numPmu':i,'nom':f'H{i}','musique':f'{i}a','nonPartant':False,'rapportDirect':i+1} for i in range(1,5)]}
        self.manifest={'courses':[{'course_id':'GENY-TEST','partants':[{'numero':i,'id':str(i),'nom':f'H{i}'} for i in range(1,5)]}]}
        for i in range(1,5):
            write(self.root/'historiques'/str(i)/'historique_geny.json',{'performances':[{'date':'2026-11-01','classement':str(i)},{'date':'2026-10-20','classement':str(i)}]})

    def document(self,mode):return json.loads((self.root/'pronostics'/f'2026-11-12_R1C1_{mode}.json').read_text())

    def np(self,minutes=0,withdrawn=(1,)):
        write(self.root/'participations/GENY-TEST.json',{'date_controle_utc':(NOW-timedelta(minutes=minutes)).isoformat(),'chevaux':[{'numero':i,'statut_participation':'NON_PARTANT' if i in withdrawn else 'PARTANT'} for i in range(1,5)]})

    def test_withdrawal_refreshes_both_direct_and_market(self):
        calculer(self.root,self.course,self.raw,NOW)
        self.raw['participants'][0]['nonPartant']=True
        result=calculer(self.root,self.course,self.raw,NOW+timedelta(minutes=1))
        for mode in ('direct','cotes'):
            self.assertEqual(result[mode],'CALCULE_COMPLET')
            self.assertEqual([h['numero'] for h in self.document(mode)['top3']],[2,3,4])
        archive=list((self.root/'pronostics/versions').glob('*direct*'))
        self.assertEqual(len(archive),1)
        self.assertEqual(json.loads(archive[0].read_text())['top3'][0]['numero'],1)

    def test_withdrawal_persists_when_next_flag_is_unknown(self):
        self.raw['participants'][0]['nonPartant']=True
        calculer(self.root,self.course,self.raw,NOW)
        del self.raw['participants'][0]['nonPartant']
        calculer(self.root,self.course,self.raw,NOW+timedelta(minutes=1))
        self.assertNotIn(1,[h['numero'] for h in self.document('direct')['top3']])

    def test_explicit_reinstatement_is_recorded(self):
        self.raw['participants'][0]['nonPartant']=True
        calculer(self.root,self.course,self.raw,NOW)
        self.raw['participants'][0]['nonPartant']=False
        calculer(self.root,self.course,self.raw,NOW+timedelta(minutes=1))
        self.assertEqual(self.document('direct')['top3'][0]['numero'],1)

    def test_insufficient_remaining_horses_invalidates_latest_selection(self):
        calculer(self.root,self.course,self.raw,NOW)
        for h in self.raw['participants'][:2]:h['nonPartant']=True
        calculer(self.root,self.course,self.raw,NOW+timedelta(minutes=1))
        for mode in ('direct','cotes'):
            self.assertEqual(self.document(mode)['top3'],[])
            self.assertEqual(self.document(mode)['classement_complet'],[])

    def test_no_retroactive_update(self):
        calculer(self.root,self.course,self.raw,NOW)
        before=self.document('direct')
        self.raw['participants'][0]['nonPartant']=True
        self.assertEqual(calculer(self.root,self.course,self.raw,NOW+timedelta(hours=2))['direct'],'APRES_DEPART')
        self.assertEqual(self.document('direct'),before)

    def test_stale_np_is_excluded_from_initial_baseline(self):
        self.np(minutes=31)
        self.assertEqual(preparer_top3(self.root,self.course,self.manifest,NOW),'FIGE_BASELINE_EXPERIMENTALE')
        self.assertEqual([h['numero'] for h in self.document('top3')['top3']],[2,3,4])
        self.assertEqual(self.document('top3')['statut_np'],'NP_NON_VERIFIE')

    def test_future_np_is_not_used(self):
        self.np(minutes=-1)
        preparer_top3(self.root,self.course,self.manifest,NOW)
        self.assertEqual(self.document('top3')['top3'][0]['numero'],1)

    def test_stale_np_updates_baseline_without_changing_original(self):
        self.np(withdrawn=())
        preparer_top3(self.root,self.course,self.manifest,NOW)
        before=self.document('top3')
        self.np(minutes=31)
        self.assertEqual(actualiser_top3_np(self.root,self.course,self.manifest,NOW),'ACTUALISE')
        self.assertEqual([h['numero'] for h in self.document('baseline_latest')['top3']],[2,3,4])
        self.assertEqual(self.document('top3'),before)

class RegistreTests(unittest.TestCase):
    def test_zero_score_is_numeric_even_when_previous_score_is_text(self):
        headers=['course_key','score_direct','score_ml']
        h,updates,appends=plan_sheet(headers,[{'course_key':'x','score_direct':'0','score_ml':''}],{'x':{'course_key':'x','score_direct':0,'score_ml':''}},'Résultats & Analyse')
        self.assertIn((2,2,0),updates)
        self.assertIsInstance(updates[0][2],int)
        self.assertFalse(appends)

    def test_withdrawn_selection_and_rank_are_cleared_in_sheet(self):
        h,updates,a=plan_sheet(['course_key','numero','top3_direct_top3','top3_direct_rang'],[{'course_key':'x','numero':'1','top3_direct_top3':'OUI','top3_direct_rang':'1'}],{'x|1':{'course_key':'x','numero':'1','top3_direct_top3':'','top3_direct_rang':''}},'Courses & Prévisions')
        self.assertIn((2,3,''),updates)
        self.assertIn((2,4,''),updates)

    def test_numeric_append_and_idempotence(self):
        h,u,a=plan_sheet(['course_key','score_direct'],[],{'x':{'course_key':'x','score_direct':'0'}},'Résultats & Analyse')
        self.assertEqual(a[0][1],0)
        old=[dict(zip(h,a[0]))]
        self.assertEqual(plan_sheet(h,old,{'x':{'course_key':'x','score_direct':'0'}},'Résultats & Analyse')[1:],([],[]))

class KpiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source={'Courses & Prévisions':{'a':{'course_key':'a','cheval':'Étoile','historique_statut':'HISTO_OK_NOM','historique_nb_courses_datees':'4','age_ans':4,'sexe':'Femelle','gains_euros':0,'ferrure':'D4'},'b':{'course_key':'b','cheval':'ETOILE','historique_nb_courses_datees':'','historique_statut':'HISTO_NON_COLLECTE'}},'Historique chevaux':{},'Résultats & Analyse':{'a':{'course_key':'a','date_course':'2026-11-12','rncn':'R1C1','heure_depart_paris':(NOW-timedelta(hours=1)).isoformat(),'arrivee_officielle_numeros':'4,5,6'}}}
        write(self.root/'arrivees/2026-11-12_R1C1.json',{'source':'PMU_API_PARTICIPANTS','verifie_utc':NOW.isoformat(),'arrivee':[{'numero':n,'rang':i} for i,n in enumerate([4,5,6],1)]})
        write(self.root/'pronostics/2026-11-12_R1C1_direct.json',{'calcul_utc':(NOW-timedelta(hours=2)).isoformat(),'top3':[{'numero':n} for n in [1,2,3]]})

    def test_zero_hits_are_evaluated_and_histories_require_positive_number(self):
        m=calculer_kpi(self.root,self.source,NOW)
        self.assertEqual(m['Courses évaluées'][0],1)
        self.assertEqual(m['Moyenne de chevaux TOP3 retrouvés'][0],0)
        self.assertEqual(m['Courses avec arrivée vérifiée'][0],1)
        self.assertEqual(m['Partants avec historique disponible'][0],1)
        self.assertEqual(m['Chevaux distincts rencontrés'][0],1)
        self.assertEqual(m['Partants avec âge, sexe, gains et ferrure'][0],1)
        self.assertEqual(m['Lignes sans gains'][0],1)

    def test_post_departure_prediction_is_not_evaluated(self):
        write(self.root/'pronostics/2026-11-12_R1C1_direct.json',{'calcul_utc':NOW.isoformat(),'top3':[{'numero':n} for n in [4,5,6]]})
        m=calculer_kpi(self.root,self.source,NOW)
        self.assertEqual(m['Courses évaluées'][0],0)
        self.assertEqual(m['Moyenne de chevaux TOP3 retrouvés'][0],'')

    def test_kpi_updates_follow_labels_instead_of_fixed_positions(self):
        m=calculer_kpi(self.root,self.source,NOW)
        table=[['Dimension','Indicateur','Valeur','Définition'],['Personnelle','Mon indicateur',42,'À conserver'],['Résultats','Courses évaluées',0,'Ancien calcul']]
        updates=plan_kpi(table,m)
        self.assertFalse(any("A2:" in u['range'] or "C2:" in u['range'] for u in updates))
        self.assertEqual(updates[0]['range'],"'Data Quality & KPI'!C3:E3")
        self.assertEqual(updates[0]['values'][0][2],m['Courses distinctes collectées'][0])
        self.assertEqual(updates[0]['values'][0][0],1)

    def test_perimetre_resultats_inclut_les_courses_sans_ligne_de_partant(self):
        from pmu_geny.kpi_registre import PERIMETRE_RESULTATS, totaux_reference
        self.source['Résultats & Analyse']['c'] = {
            'course_key': 'c', 'date_course': '2026-11-12', 'rncn': 'R1C2',
            'heure_depart_paris': (NOW-timedelta(hours=1)).isoformat(),
            'arrivee_officielle_numeros': '1,2,3',
        }
        metrics = calculer_kpi(self.root, self.source, NOW)
        totals = totaux_reference(metrics)
        self.assertEqual(metrics['Courses distinctes collectées'][0], 2)
        self.assertEqual(metrics[PERIMETRE_RESULTATS][0], 3)
        self.assertEqual(totals['Courses avec arrivée officielle'], 3)
        self.assertEqual(totals['Courses avec sélection TOP3 direct'], 2)

    def test_fraicheur_geny_reprise_depuis_le_journal_et_dimension_corrigee(self):
        label = 'Collecte · Geny · Acquisition incrémentale validée UTC'
        capture = (NOW - timedelta(minutes=12)).isoformat()
        write(self.root/'etat_persistant.json', {'chevaux': {
            '123456': {'origine': 'COLLECTE_INCREMENTALE_PRODUCTION', 'statut': 'COMPLET',
                       'historique_complet_au_utc': capture},
            '234567': {'origine': 'RATTRAPAGE_GLOBAL', 'statut': 'COMPLET',
                       'historique_complet_au_utc': NOW.isoformat()},
        }})
        metrics = calculer_kpi(self.root, self.source, NOW)
        self.assertEqual(metrics[label][0], capture)
        updates = plan_kpi([['Dimension', 'Indicateur'], ['ML', label]], metrics)
        self.assertEqual(updates[0]['range'], "'Data Quality & KPI'!A2:D2")
        self.assertEqual(updates[0]['values'][0][:3], ['Collecte', label, capture])

    def test_real_reference_reconciles_all_13_races_and_historical_baseline(self):
        if not Path('reference_pmu').is_dir():self.skipTest('reference facultative absente')
        from pmu_geny.qualite_registre_v21 import evaluer
        m=calculer_kpi('reference_pmu')
        self.assertGreaterEqual(m['Courses avec arrivée vérifiée'][0],13)
        self.assertGreaterEqual(m['Courses évaluées'][0],13)
        self.assertTrue(any(c['top3_historique_fige'] for c in evaluer('reference_pmu')['courses']))

if __name__=='__main__':unittest.main()
