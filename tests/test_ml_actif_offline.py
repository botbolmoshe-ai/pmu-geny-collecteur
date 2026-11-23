import hashlib
import json
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch

import joblib
from pmu_geny.cycle_ml_actif import entrainer,modele_disponible,POINTEUR,STATUT
from pmu_geny.ml_v19 import ACTIVE_FEATURES,ACTIVE_MODEL_SCHEMA,MODEL_SCHEMA,load,save,predict_pmu,snapshot_pmu
from pmu_geny.kpi_registre import calculer_kpi,plan_kpi


class ActifTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name);self.now=datetime(2026,11,17,1,tzinfo=timezone.utc)
        self.course={'date':'2026-11-17','code':'R3C1','depart':'2026-11-17T14:12:00+01:00',
                     'distance_m':2700,'nombre_declares':4}
        self.raw={'participants':[{'numPmu':n,'nom':'Test '+str(n),'nonPartant':False,
            'age':5,'sexe':'HONGRES','gainsCarriere':n*10000,'musique':'1a2a3a','ferrure':'D4'} for n in range(1,5)]}

    def exemple(self,day='2026-11-16'):
        snap=self.cache/'ml/instantanes'/f'{day}_R1C1.json'
        save(snap,{'date':day,'code':'R1C1','depart':day+'T12:00:00+00:00',
            'capture_utc':day+'T10:00:00+00:00','chevaux':[{'numero':n,
            'features':{'pmu_score_direct':n,'age_ans':5}} for n in range(1,5)]})
        save(self.cache/'arrivees'/snap.name,{'date':day,'course':'R1C1','verifie_utc':day+'T13:00:00+00:00',
            'arrivee':[{'numero':n,'rang':n} for n in (1,2,3)]})
        return snap

    def test_entraine_meme_une_seule_periode_et_predit_sans_promotion(self):
        snap=self.exemple();frozen=snap.read_bytes()
        fit=entrainer(self.cache,self.now)
        self.assertEqual(fit['statut'],STATUT);self.assertEqual((fit['courses'],fit['lignes']),(1,4))
        self.assertFalse(fit['promotion_production']);self.assertFalse((self.cache/'ml/modele.joblib').exists())
        self.assertEqual(predict_pmu(self.cache,self.course,self.raw,self.now),'ML_EXPERIMENTAL_CALCULE')
        result=load(self.cache/'pronostics/2026-11-17_R3C1_ml_latest.json')
        self.assertEqual(len(result['top3']),3);self.assertTrue(result['experimental'])
        self.assertEqual(result['statut'],STATUT);self.assertFalse(result['promotion_production'])
        self.assertIn('score_non_calibre',result['top3'][0])
        self.assertEqual(result['features_schema'],ACTIVE_MODEL_SCHEMA)
        self.assertEqual(result['variables_modele'],list(ACTIVE_FEATURES))
        self.assertEqual(result['couverture_variables']['position_autostart_absolue'],0)
        self.assertNotIn('proba_podium_estimee',result['top3'][0])
        self.assertEqual(snap.read_bytes(),frozen)

    def test_enrichissement_apprend_une_valeur_documentee_et_signale_les_absences(self):
        snap=self.exemple();data=load(snap)
        data.update(features_schema=MODEL_SCHEMA,source='PMU_API_PARTICIPANTS')
        data['chevaux'][0]['features'].update(depart_autostart=0,recul_depart_m=0)
        data['chevaux'][1]['features'].update(depart_autostart=1,position_autostart_absolue=2)
        save(snap,data);original=snap.read_bytes()
        fit=entrainer(self.cache,self.now)
        packed=joblib.load(modele_disponible(self.cache))
        self.assertEqual(packed['features'],ACTIVE_FEATURES)
        self.assertEqual(fit['couverture_variables']['depart_autostart'],2)
        self.assertEqual(fit['couverture_variables']['recul_depart_m'],1)
        self.assertEqual(fit['couverture_variables']['tandem_courses'],0)
        imputer=packed['model'].named_steps['simpleimputer']
        self.assertIn(ACTIVE_FEATURES.index('depart_autostart'),imputer.indicator_.features_)
        self.assertEqual(snap.read_bytes(),original)

    def test_pas_de_reentrainement_pour_des_captures_non_encore_etiquetees(self):
        self.exemple();a=entrainer(self.cache,self.now);path=modele_disponible(self.cache)
        before=path.read_bytes()
        snapshot_pmu(self.cache,self.course,self.raw,self.now)
        b=entrainer(self.cache,self.now+timedelta(minutes=1))
        self.assertEqual(b['execution'],'DONNEES_INCHANGEES');self.assertEqual(a['entrainement_utc'],b['entrainement_utc'])
        self.assertNotEqual(a['verification_utc'],b['verification_utc']);self.assertEqual(path.read_bytes(),before)

    def test_aucun_modele_si_les_arrivees_sont_futures_ou_les_variables_absentes(self):
        snap=self.exemple()
        arr=load(self.cache/'arrivees'/snap.name);arr['verifie_utc']='2099-01-01T00:00:00+00:00'
        save(self.cache/'arrivees'/snap.name,arr)
        self.assertEqual(entrainer(self.cache,self.now)['statut'],'ML_EXPERIMENTAL_ATTENTE_DONNEES')
        self.assertIsNone(modele_disponible(self.cache))
        self.exemple();data=load(snap)
        for h in data['chevaux']:h['features']={}
        save(snap,data)
        self.assertIn('Aucune variable',entrainer(self.cache,self.now)['motif'])
        self.assertIsNone(modele_disponible(self.cache))

    def test_modele_trafique_et_inference_retroactive_sont_refuses(self):
        self.exemple();entrainer(self.cache,self.now)
        path=modele_disponible(self.cache);original=path.read_bytes();path.write_bytes(original+b'corruption')
        self.assertIsNone(modele_disponible(self.cache));path.write_bytes(original)
        self.assertEqual(predict_pmu(self.cache,self.course,self.raw,
            datetime.fromisoformat(self.course['depart'])),'HORS_FENETRE_DECISION')
        packed=joblib.load(path);packed['entrainement_utc']='2099-01-01T00:00:00+00:00';joblib.dump(packed,path)
        meta=load(self.cache/POINTEUR);meta['sha256_modele']=hashlib.sha256(path.read_bytes()).hexdigest();save(self.cache/POINTEUR,meta)
        self.assertEqual(predict_pmu(self.cache,self.course,self.raw,self.now),'MODELE_EXPERIMENTAL_CHRONOLOGIE_INVALIDE')

    def test_modele_corrompu_est_reentraine_et_non_reutilise(self):
        self.exemple();entrainer(self.cache,self.now);path=modele_disponible(self.cache)
        path.write_bytes(b'corrompu')
        self.assertEqual(entrainer(self.cache,self.now+timedelta(minutes=1))['execution'],'ENTRAINE')
        self.assertIsNotNone(modele_disponible(self.cache))

    def test_depart_franchi_durant_le_calcul_ne_produit_aucune_prevision(self):
        from pmu_geny.top3_independants_v22 import calculer
        self.exemple();entrainer(self.cache,self.now)
        after=datetime.fromisoformat(self.course['depart'])+timedelta(seconds=1)
        self.assertEqual(predict_pmu(self.cache,self.course,self.raw,self.now,clock=lambda:after),'HORS_FENETRE_DECISION')
        self.assertEqual(snapshot_pmu(self.cache,self.course,self.raw,self.now,clock=lambda:after),'TROP_TARD')
        self.assertEqual(calculer(self.cache,self.course,self.raw,self.now,clock=lambda:after)['direct'],'APRES_DEPART')
        self.assertFalse(list((self.cache/'pronostics').glob('*')))
        self.assertFalse((self.cache/'ml/instantanes/2026-11-17_R3C1.json').exists())

    def test_kpi_rend_visible_le_fit_et_n_ajoute_les_lignes_qu_une_fois(self):
        self.exemple();entrainer(self.cache,self.now)
        metrics=calculer_kpi(self.cache,{'Courses & Prévisions':{},'Résultats & Analyse':{},'Historique chevaux':{}})
        owned={k:v for k,v in metrics.items() if k.startswith('ML expérimental · ')}
        self.assertEqual(len(owned),5);self.assertEqual(owned['ML expérimental · Courses apprises'][0],1)
        values=[['Dimension','Indicateur','Valeur','Définition','Total'],['Autre','Indicateur utilisateur',7,'Conserver']]
        first=plan_kpi(values,metrics);self.assertGreaterEqual(len(first),5)
        values.extend(u['values'][0] for u in first)
        self.assertEqual(plan_kpi(values,metrics),[])

    def test_cycle_de_nuit_prepare_top3_et_debloque_les_historiques_du_jour(self):
        from pmu_geny import auto_v18
        from pmu_geny import historiques_incrementaux as inc
        from pmu_geny.preparation_prochaines import appliquer
        course={**self.course,'nom':'PRIX TEST','hippodrome':'VINCENNES','discipline':'TROT_ATTELE'}
        save(self.cache/'orchestration/correspondances_geny.json',{'2026-11-17_R3C1':'GENY-1698061'})
        with patch.object(auto_v18,'get_json',return_value=self.raw), \
             patch.object(auto_v18,'programme_diagnostic',return_value=([course],{})), \
             patch.object(auto_v18,'datetime',wraps=datetime) as clock, \
             patch('pmu_geny.partants_actuels_v21.datetime',wraps=datetime) as profiles_clock, \
             patch('pmu_geny.contexte_meteo_v20.collecter_meteo',return_value='TEST'), \
             patch('pmu_geny.sources_experts_v23.collecter',return_value='TEST'), \
             patch('builtins.print'):
            clock.now.return_value=self.now;profiles_clock.now.return_value=self.now
            result=auto_v18.run(self.cache,'2026-11-17',[],0,max_discoveries=0,now=self.now)
        forecast=load(self.cache/'pronostics/2026-11-17_R3C1_direct.json')
        self.assertEqual(len(forecast['top3']),3)
        self.assertEqual(result['courses']['R3C1']['statut_snapshot_ml'],'CAPTURE_PMU')
        save(self.cache/'sources_pmu/programme_2026-11-18.json',{'date_controle_utc':self.now.isoformat(),'programme':[]})
        state=inc.alimenter(self.cache,self.now);appliquer(self.cache,state,self.now)
        state['passage_utc']=self.now.isoformat()
        key,action=inc.prochaine_tache(state,self.now,{})
        self.assertEqual(action,'COLLECTE');self.assertTrue(key.startswith('2026-11-17_R3C1_'))
        self.assertEqual(state['preparation_prochaines_courses']['couverture_par_jour']['2026-11-17']['sans_historique_complet'],4)
