"""Inventaire exhaustif, reprise et isolation du rattrapage."""
import copy
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import Mock,patch

from pmu_geny import historiques_incrementaux as inc
from pmu_geny import rattrapage_historiques as back
from pmu_geny.moteur_sheets import SynchroniseurSheets
from test_v26_incremental_offline import doc
from test_v26_chaine_offline import SheetsSession


class RepriseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name);self.now=datetime.now(timezone.utc)
        inc.ecrire(self.cache/'etat_persistant.json',{'version':1,'chevaux':{}})
        inc.ecrire(self.cache/back.INVENTAIRE,{'capture_utc':self.now.isoformat(),'chevaux':[],
                                              'ids_couverts':[],'lignes_historique':0})
        sleep=patch.object(inc.time,'sleep');sleep.start();self.addCleanup(sleep.stop)

    def seed(self,*,complete=False,covered=False):
        inc.ecrire(self.cache/'etat_persistant.json',{'version':1,'chevaux':{
            '123456':{'id':'123456','nom':'Test','statut':'PARTIEL'}}})
        old=(self.now-timedelta(days=60)).date().isoformat()+'_R1C1'
        inc.ecrire(self.cache/'partants_actuels'/f'{old}.json',{'chevaux':{
            '1':{'nom':'Test','statut_np':'NON_PARTANT'}}})
        inc.ecrire(self.cache/'orchestration/correspondances_geny.json',{old:'GENY-1698061'})
        data=doc(self.now-timedelta(days=30))
        if not complete:data['nombre_annonce_geny']=2
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json',data)
        if covered:
            snapshot=inc.lire(self.cache/back.INVENTAIRE);snapshot['ids_couverts']=['123456']
            inc.ecrire(self.cache/back.INVENTAIRE,snapshot)

    def collect(self,horse,out):
        dest=self.cache/'extraction/123456';inc.ecrire(dest/'historique_geny.json',doc(datetime.now(timezone.utc)))
        return {'complet':True,'identite_verifiee':True,'statut':'COMPLET',
                'geny':{'id':'123456','nom':'Test','url_geny':doc(self.now)['source_url']},'dossier':str(dest)}

    def test_passe_ancien_np_journal_et_sheet_sans_fenetre_glissante(self):
        self.seed()
        snapshot=inc.lire(self.cache/back.INVENTAIRE)
        snapshot['chevaux']=[{'id':'999999','nom':'Uniquement Sheet','origine':'SHEETS:Historique chevaux'}]
        inc.ecrire(self.cache/back.INVENTAIRE,snapshot)
        self.assertEqual(inc.alimenter(self.cache,self.now)['chevaux'],{})
        state=back.preparer(self.cache,self.now)
        self.assertEqual(set(state['chevaux']),{'123456','999999'})
        self.assertEqual(back.prochaine_tache(state,self.now,{})[0],'123456')

    def test_inventaire_fige_ne_perd_pas_les_cibles_ni_ne_grossit_a_chaque_passage(self):
        self.seed();state=back.preparer(self.cache,self.now);inc.ecrire(self.cache/back.QUEUE,state)
        journal=inc.lire(self.cache/'etat_persistant.json')
        journal['chevaux']['999999']={'nom':'Nouveau'};inc.ecrire(self.cache/'etat_persistant.json',journal)
        later=back.preparer(self.cache,self.now+timedelta(days=100))
        self.assertEqual(set(later['chevaux']),{'123456'})
        self.assertEqual(state['inventaire_id'],later['inventaire_id'])
        self.assertEqual(back.prochaine_tache(later,self.now+timedelta(days=100),{})[0],'123456')

    def test_capture_complete_datee_deja_publiee_ne_recollecte_pas(self):
        self.seed(complete=True,covered=True)
        state=back.preparer(self.cache,self.now);horse=state['chevaux']['123456']
        self.assertTrue(horse['rattrapage_complet_au_utc'])
        self.assertEqual(back.prochaine_tache(state,self.now,{}),(None,'TERMINE_PASSAGE'))
        self.assertNotEqual(state['statut'],'TERMINE')  # Les KPI restent à consolider.
        state['sync_kpi']='OK';back.bilan(state);self.assertEqual(state['statut'],'TERMINE')

    def test_capture_complete_absente_du_sheet_demande_uniquement_sync(self):
        self.seed(complete=True)
        state=back.preparer(self.cache,self.now)
        self.assertEqual(back.prochaine_tache(state,self.now,{}),('123456','SYNC'))

    def test_date_absente_ou_future_ne_prouve_pas_completion(self):
        self.seed(complete=True,covered=True)
        for stamp in (None,(self.now+timedelta(days=1)).isoformat()):
            data=doc(self.now);data['extrait_utc']=stamp
            inc.ecrire(self.cache/'historiques/123456/historique_geny.json',data)
            state=back.preparer(self.cache,self.now)
            self.assertFalse(state['chevaux']['123456'].get('rattrapage_complet_au_utc'))

    def test_succes_checkpoint_avant_sheet_reprise_sans_recollecte_et_production_intacte(self):
        self.seed();protected=['pronostics/fige.json','ml/instantanes/fige.json','arrivees/fige.json',str(inc.QUEUE)]
        for name in protected:inc.ecrire(self.cache/name,{'preuve':'intacte'})
        inc.ecrire(self.cache/inc.QUEUE,{'version':1,'chevaux':{},'preuve':'intacte'})
        before={name:(self.cache/name).read_bytes() for name in protected}
        events=[];engine=Mock();engine.synchroniser_cheval.return_value={'Historique chevaux':{'lignes_ajoutees':1}}
        engine.synchroniser_kpi.return_value={}
        def checkpoint(cache):events.append(inc.lire(cache/back.QUEUE))
        def publication(horse,**kwargs):
            self.assertEqual(events[-1]['chevaux']['123456']['sync'],'A_FAIRE')
            self.assertIsNotNone(inc.capture_valide(self.cache,'123456'))
            return {'Historique chevaux':{'lignes_ajoutees':1}}
        engine.synchroniser_cheval.side_effect=publication
        collect=Mock(side_effect=self.collect)
        with patch.dict(os.environ,{'GOOGLE_SHEETS_ID':'fake'}),patch('pmu_geny.moteur_sheets.SynchroniseurSheets',return_value=engine):
            first=inc.run(self.cache,mode='rattrapage',publier=True,checkpoint=checkpoint,collect=collect)
            second=inc.run(self.cache,mode='rattrapage',publier=True,checkpoint=checkpoint,collect=collect)
        self.assertEqual(first['statut'],'TERMINE');self.assertEqual(second['statut'],'TERMINE')
        self.assertEqual(collect.call_count,1);engine.synchroniser_cheval.assert_called_once()
        self.assertEqual(engine.synchroniser_cheval.call_args.kwargs,{'include_kpi':False,'include_courses':False})
        self.assertEqual(first['bilan']['ajouts_confirmes'],1)
        self.assertEqual(before,{name:(self.cache/name).read_bytes() for name in protected})

    def test_publication_echouee_reprise_sans_geny(self):
        self.seed()
        sync=Mock(side_effect=RuntimeError('Sheets indisponible'))
        first=inc.run(self.cache,mode='rattrapage',collect=self.collect,sync=sync)
        first['chevaux']['123456']['prochaine_sync_utc']=(self.now-timedelta(minutes=1)).isoformat()
        inc.ecrire(self.cache/back.QUEUE,first)
        collect=Mock(side_effect=AssertionError('Ne pas recollecter'))
        second=inc.run(self.cache,mode='rattrapage',collect=collect,sync=lambda h:{})
        collect.assert_not_called();self.assertEqual(second['chevaux']['123456']['sync'],'OK')

    def test_blocage_403_partage_avec_production_sans_contournement(self):
        self.seed()
        collect=Mock(return_value={'statut':'ACCES_REFUSE_403'})
        state=inc.run(self.cache,mode='rattrapage',collect=collect)
        self.assertEqual(collect.call_count,1)
        self.assertIn('prochain_acces_geny_utc',state)
        self.assertEqual(inc.lire(self.cache/'etat_persistant.json')['dernier_blocage_geny']['code'],'403')
        inc.run(self.cache,mode='rattrapage',collect=collect)
        self.assertEqual(collect.call_count,1)

    def test_noms_ambigus_ne_fusionnent_pas_les_identifiants(self):
        inc.ecrire(self.cache/'etat_persistant.json',{'chevaux':{
            '111111':{'nom':'Homonyme'},'222222':{'nom':'Homonyme'}}})
        snapshot=inc.lire(self.cache/back.INVENTAIRE)
        snapshot['chevaux']=[{'nom':'Homonyme','engagement':'2020-01-01_R1C1','numero':'2'}]
        targets=back.inventaire_local(self.cache,snapshot)
        self.assertEqual(len(targets),3)
        self.assertEqual(sum(bool(x.get('id')) for x in targets.values()),2)

    def test_index_geny_local_resout_une_ancienne_course_sans_requete(self):
        self.seed()
        (self.cache/'orchestration/correspondances_geny.json').unlink()
        day=(self.now-timedelta(days=60)).date().isoformat()
        inc.ecrire(self.cache/'orchestration'/f'{day}.json',{'courses':{'R1C1':{'nom':'PRIX TEST','hippodrome':'VINCENNES'}}})
        inc.ecrire(self.cache/'sources_geny'/f'index_{day}.json',{'statut':'OK','courses':[{'geny_id':'1698061',
            'date':day,'slug':'vincennes prix test','url':'https://www.geny.com/course/1698061-prix-test',
            'r':1,'c':1,'code_rc_verifie':True}]})
        state=back.preparer(self.cache,self.now)
        self.assertIn('/course/1698061/',state['chevaux']['123456']['course_url'])

    def test_fichiers_corrompus_et_inventaire_absent_arretent_sans_reinitialiser(self):
        self.seed();path=self.cache/back.QUEUE;path.parent.mkdir(exist_ok=True);path.write_text('{invalide')
        with self.assertRaises(json.JSONDecodeError):back.preparer(self.cache,self.now)
        self.assertEqual(path.read_text(),'{invalide')
        (self.cache/back.INVENTAIRE).unlink()
        with self.assertRaisesRegex(ValueError,'INVENTAIRE_SHEETS_REQUIS'):back.preparer(self.cache,self.now)

    def test_moteur_rattrapage_preserve_courses_resultats_et_formules(self):
        self.seed();session=SheetsSession();before=copy.deepcopy(session.tables)
        source={'Historique chevaux':{'p':{'cle_performance':'p','identifiant_cheval':'123456','cheval':'Test'}},
                'Courses & Prévisions':{'c':{'course_key':'course1','numero':'1','cheval':'Test','historique_statut':'HISTO_OK_NOM'}},
                'Résultats & Analyse':{}}
        with patch.dict(os.environ,{'PMU_SHEETS_LOCK_DIR':str(self.cache),'PMU_SHEETS_CONTROLES':str(self.cache/'controles.jsonl'),'GITHUB_STEP_SUMMARY':''}), \
             patch('pmu_geny.sync_google_sheets.source_rows',return_value=source),patch('builtins.print'):
            engine=SynchroniseurSheets(self.cache,'fake',session=session)
            first=engine.synchroniser_cheval({'nom':'Test','geny':{'id':'123456'}},include_courses=False,include_kpi=False)
            second=engine.synchroniser_cheval({'nom':'Test','geny':{'id':'123456'}},include_courses=False,include_kpi=False)
            inventory=engine.inventaire_rattrapage()
        self.assertEqual(first['Historique chevaux']['lignes_ajoutees'],1)
        self.assertEqual(second['Historique chevaux']['lignes_ajoutees'],0)
        self.assertEqual(session.tables['Courses & Prévisions'],before['Courses & Prévisions'])
        self.assertEqual(session.tables['Data Quality & KPI'],before['Data Quality & KPI'])
        self.assertEqual(inventory['ids_couverts'],['123456'])
        self.assertEqual(inventory['controle']['statut'],'VALIDE')

    def test_workflow_independant_file_distincte_et_verrou_commun(self):
        import yaml
        root=Path(__file__).resolve().parents[1]
        config=yaml.load((root/'.github/workflows/rattrapage-historiques.yml').read_text(),Loader=yaml.BaseLoader)
        self.assertEqual(config['concurrency'],{'group':'pmu-donnees-production','cancel-in-progress':'false'})
        self.assertIn('workflow_dispatch',config['on'])
        self.assertNotEqual(back.QUEUE,inc.QUEUE)

    def test_identite_de_capture_contradictoire_n_est_pas_declaree_complete(self):
        self.seed(complete=True,covered=True)
        data=doc(self.now);data['identifiant_cheval']='999999'
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json',data)
        state=back.preparer(self.cache,self.now)
        self.assertFalse(state['chevaux']['123456'].get('rattrapage_complet_au_utc'))

    def test_aucune_tache_eligible_ne_signifie_pas_stock_termine(self):
        snapshot=inc.lire(self.cache/back.INVENTAIRE)
        snapshot['chevaux']=[{'id':'999999','nom':'Sans lien'}];inc.ecrire(self.cache/back.INVENTAIRE,snapshot)
        state=back.preparer(self.cache,self.now);state['sync_kpi']='OK';back.bilan(state)
        self.assertEqual(back.prochaine_tache(state,self.now,{}),(None,'TERMINE_PASSAGE'))
        self.assertEqual(state['statut'],'PARTIEL_REPRENABLE')
        self.assertEqual(state['bilan']['liens_a_resoudre'],1)

    def test_reprise_kpi_seule_apres_echec_sans_double_collecte(self):
        self.seed();first=Mock();second=Mock()
        first.synchroniser_cheval.return_value={};first.synchroniser_kpi.side_effect=RuntimeError('KPI indisponible')
        second.synchroniser_kpi.return_value={};collect=Mock(side_effect=self.collect)
        with patch.dict(os.environ,{'GOOGLE_SHEETS_ID':'fake'}), \
             patch('pmu_geny.moteur_sheets.SynchroniseurSheets',side_effect=[first,second]):
            with self.assertRaisesRegex(RuntimeError,'KPI indisponible'):
                inc.run(self.cache,mode='rattrapage',publier=True,checkpoint=lambda c:None,collect=collect)
            pending=inc.lire(self.cache/back.QUEUE)
            self.assertEqual(pending['sync_kpi'],'A_REPRENDRE');self.assertNotEqual(pending['statut'],'TERMINE')
            done=inc.run(self.cache,mode='rattrapage',publier=True,checkpoint=lambda c:None,collect=collect)
        self.assertEqual(done['statut'],'TERMINE');self.assertEqual(collect.call_count,1)
        second.synchroniser_cheval.assert_not_called();second.synchroniser_kpi.assert_called_once()

    def test_checkpoint_git_conserve_file_production_et_recharge_reprise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';remote=root/'remote.git';cache=root/'cache'
            def git(*args,cwd=None):
                return subprocess.check_output(['git',*args],cwd=cwd,text=True,stderr=subprocess.DEVNULL).strip()
            git('init','--bare',str(remote));git('init','-b','main',str(repo))
            git('config','user.name','Test',cwd=repo);git('config','user.email','test@example.invalid',cwd=repo)
            (repo/'code.txt').write_text('code');git('add','.',cwd=repo);git('commit','-m','code',cwd=repo)
            git('remote','add','origin',str(remote),cwd=repo);git('switch','-c','pmu-data',cwd=repo)
            inc.ecrire(repo/inc.QUEUE,{'preuve':'production intacte'})
            inc.ecrire(repo/'pronostics/fige.json',{'preuve':'figee'})
            inc.ecrire(repo/'etat_persistant.json',{'version':1,'chevaux':{}})
            git('add','.',cwd=repo);git('commit','-m','data',cwd=repo);git('push','origin','pmu-data',cwd=repo)
            git('switch','main',cwd=repo)
            inc.ecrire(cache/inc.QUEUE,{'preuve':'NE PAS PUBLIER'})
            inc.ecrire(cache/back.QUEUE,{'version':1,'chevaux':{},'preuve':'reprise'})
            inc.ecrire(cache/back.INVENTAIRE,{'preuve':'inventaire'})
            inc.ecrire(cache/'historiques/123456/historique_geny.json',{'preuve':'capture'})
            inc.ecrire(cache/'etat_persistant.json',{'version':1,'chevaux':{}})
            with patch.object(inc,'__file__',str(repo/'pmu_geny/historiques_incrementaux.py')):
                inc.checkpoint_distant(cache,queue=back.QUEUE)
            self.assertEqual(json.loads(git('show','pmu-data:'+str(inc.QUEUE),cwd=remote)),{'preuve':'production intacte'})
            self.assertEqual(json.loads(git('show','pmu-data:'+str(back.QUEUE),cwd=remote))['preuve'],'reprise')
            self.assertEqual(json.loads(git('show','pmu-data:'+str(back.INVENTAIRE),cwd=remote))['preuve'],'inventaire')
            self.assertEqual(json.loads(git('show','pmu-data:pronostics/fige.json',cwd=remote)),{'preuve':'figee'})

    def test_priorite_production_termine_passage_avant_le_cheval_suivant(self):
        self.seed();collect=Mock(side_effect=AssertionError('Ne pas commencer'))
        result=inc.run(self.cache,mode='rattrapage',collect=collect,
                       stop_requested=lambda:'PRIORITE_PRODUCTION_EN_ATTENTE')
        collect.assert_not_called()
        self.assertEqual(result['motif_fin_passage'],'PRIORITE_PRODUCTION_EN_ATTENTE')
        self.assertEqual(result['statut'],'PARTIEL_REPRENABLE')

    def test_priorite_verifie_les_workflows_et_cede_si_controle_indisponible(self):
        response=Mock();response.json.return_value={'workflow_runs':[{'path':'.github/workflows/rattrapage-historiques.yml'}]}
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'owner/repo','GH_TOKEN':'secret-factice'}), \
             patch('requests.get',return_value=response) as get:
            self.assertIsNone(back.priorite_production())
            response.json.return_value={'workflow_runs':[{'path':'.github/workflows/pmu-v16.yml'}]}
            self.assertEqual(back.priorite_production(),'PRIORITE_PRODUCTION_EN_ATTENTE')
            get.side_effect=RuntimeError('API indisponible')
            self.assertEqual(back.priorite_production(),'PRIORITE_PRODUCTION_NON_VERIFIABLE')


if __name__=='__main__':unittest.main()
