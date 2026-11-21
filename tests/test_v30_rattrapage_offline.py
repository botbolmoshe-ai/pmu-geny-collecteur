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

    def test_extension_explicite_archive_l_ancien_lot_et_conserve_les_preuves(self):
        self.seed(complete=True,covered=True)
        original=back.preparer(self.cache,self.now);inc.ecrire(self.cache/back.QUEUE,original)
        journal=inc.lire(self.cache/'etat_persistant.json')
        journal['chevaux']['999999']={'nom':'Nouveau déjà rencontré'}
        inc.ecrire(self.cache/'etat_persistant.json',journal)
        revised=back.actualiser_inventaire(self.cache,self.now+timedelta(minutes=1))
        self.assertEqual(set(revised['chevaux']),{'123456','999999'})
        self.assertEqual(revised['inventaire_id'],original['inventaire_id'])
        self.assertEqual(revised['revision_inventaire'],2)
        self.assertEqual(revised['chevaux']['123456']['rattrapage_complet_au_utc'],
                         original['chevaux']['123456']['rattrapage_complet_au_utc'])
        extension=revised['extensions_inventaire'][0]
        self.assertEqual((extension['cibles_avant'],extension['cibles_ajoutees'],extension['cibles_apres']),(1,1,2))
        archived=inc.lire(self.cache/extension['archive_precedente'])
        self.assertEqual(archived,original)
        revised.pop('cles_initiales')
        back.actualiser_cohortes(self.cache, revised)
        cohorts = back.rapport(revised)['cohortes']
        self.assertEqual(cohorts['initiale']['publiees'], 1)
        self.assertEqual(cohorts['extensions']['cibles'], 1)
        again=back.actualiser_inventaire(self.cache,self.now+timedelta(minutes=2))
        self.assertEqual(again['revision_inventaire'],2)
        self.assertEqual(again['extensions_inventaire'],revised['extensions_inventaire'])
        self.assertEqual(again['phase_reprise'],'CARRIERES_MANQUANTES')

    def test_lot_96_suit_une_reconciliation_prouvee_sans_changer_de_denominateur(self):
        reference = inc.lire(Path(back.__file__).with_name('rattrapage_lot_96.json'))
        self.assertEqual(len(set(reference['identifiants_origine'])), 96)
        original = reference['identifiants_origine'][0]
        horse = {'id': '987654321', 'collecte': 'COMPLET', 'sync': 'OK',
                 'historique_complet_au_utc':self.now.isoformat(),
                 'rattrapage_complet_au_utc':self.now.isoformat()}
        state = {'inventaire_id': reference['inventaire_id'], 'chevaux': {original: horse}}
        self.assertEqual(back.bilan_lot_96(state)['publiees'], 0)
        horse['reconciliation_identite'] = {
            'verification_utc': self.now.isoformat(), 'identifiants': {'geny':horse['id'], 'zone_turf':original},
        }
        lot = back.bilan_lot_96(state)
        self.assertEqual((lot['cibles'], lot['publiees'], lot['restantes']), (96,1,95))

    def test_carriere_absente_ancienne_avant_enrichissement_ferrure_deja_lie(self):
        state={'chevaux':{
            'ferrures':{'nom':'Complet','geny':{'id':'123456'},'engagement':'2099-01-01_R1C1',
                'motif_actualisation':'FERRURES_HISTORIQUES_A_COMPLETER','collecte':'COMPLET',
                'historique_complet_au_utc':self.now.isoformat(),'rattrapage_complet_au_utc':self.now.isoformat(),
                'ferrures_manquantes':5},
            'absent':{'id':'999999','nom':'Absent','engagement':'2020-01-01_R1C1',
                'lien_candidat':'https://www.geny.com/cheval/999999','collecte':'A_REPRENDRE',
                'motif_actualisation':'HISTORIQUE_ABSENT_PARTIEL_OU_NON_DATE'}}}
        for hour in (1,12):
            with self.subTest(hour=hour):
                self.assertEqual(back.prochaine_tache(state,self.now.replace(hour=hour),{}),('absent','COLLECTE'))
        self.assertEqual(back.prochaine_tache(state,self.now,{('COLLECTE','absent'):1}),('ferrures','COLLECTE'))

    def test_identifiant_connu_avant_contexte_a_resoudre_sans_sauter_la_validation(self):
        now=self.now.replace(hour=12)
        state={'chevaux':{
            'contexte':{'nom':'Sans identifiant','numero':'1','collecte':'A_REPRENDRE',
                'course_url':'https://www.geny.com/course/1698061/partants-pronostics',
                'motif_actualisation':'HISTORIQUE_ABSENT_PARTIEL_OU_NON_DATE'},
            '123456':{'id':'123456','nom':'Identifié','collecte':'A_REPRENDRE',
                'lien_candidat':'https://www.geny.com/cheval/123456',
                'motif_actualisation':'HISTORIQUE_ABSENT_PARTIEL_OU_NON_DATE'}}}
        self.assertEqual(back.prochaine_tache(state,now,{}),('123456','COLLECTE'))
        state['chevaux']['123456']['prochain_essai_utc']=(now+timedelta(hours=1)).isoformat()
        self.assertEqual(back.prochaine_tache(state,now,{}),('contexte','COLLECTE'))
        self.assertNotIn('geny',state['chevaux']['123456'])

    def test_bilan_distingue_carriere_absente_et_ferrures_sans_doubler_l_identifiant(self):
        stamp=self.now.isoformat()
        state={'chevaux':{
            'a':{'id':'123456'},'alias':{'id':'123456','cible_equivalente_a':'a'},
            'b':{'id':'999999','historique_complet_au_utc':stamp,'rattrapage_complet_au_utc':stamp,
                 'sync':'OK','ferrures_manquantes':2},'sans_id':{}},'sync_kpi':'OK'}
        report=back.bilan(state)
        self.assertEqual(report['identifiants_sans_carriere_complete'],1)
        self.assertEqual(report['carrieres_distinctes_a_completer'],2)
        self.assertEqual(report['contextes_distincts_sans_identifiant'],1)
        self.assertEqual(report['historiques_ferrures_a_completer'],1)
        self.assertEqual(state['phase_reprise'],'CARRIERES_MANQUANTES')
        for key in ('a','alias','sans_id'):
            state['chevaux'][key].update(historique_complet_au_utc=stamp,rattrapage_complet_au_utc=stamp,sync='OK')
        back.bilan(state);self.assertEqual(state['phase_reprise'],'ENRICHISSEMENTS_FERRURES')
        state['chevaux']['b']['ferrures_manquantes']=0
        back.bilan(state);self.assertEqual(state['phase_reprise'],'TERMINE')

    def test_ancienne_preuve_ne_cache_pas_une_capture_devenue_invalide(self):
        self.seed(complete=True,covered=True)
        state=back.preparer(self.cache,self.now);inc.ecrire(self.cache/back.QUEUE,state)
        data=inc.lire(self.cache/'historiques/123456/historique_geny.json')
        data['nombre_annonce_geny']=2
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json',data)
        revised=back.preparer(self.cache,self.now+timedelta(minutes=1))
        self.assertFalse(revised['chevaux']['123456'].get('rattrapage_complet_au_utc'))
        self.assertEqual(revised['bilan']['identifiants_sans_carriere_complete'],1)

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

    def test_capture_plus_recente_ne_reutilise_pas_une_ancienne_preuve_sheet(self):
        self.seed(complete=True,covered=True)
        state=back.preparer(self.cache,self.now);inc.ecrire(self.cache/back.QUEUE,state)
        old_stamp=state['chevaux']['123456']['rattrapage_complet_au_utc']
        data=doc(self.now)
        data['performances'].append({**data['performances'][0],'date':'2026-11-15','texte_source':'nouvelle course'})
        data['nombre_annonce_geny']=data['nombre_extrait']=2
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json',data)
        snapshot=inc.lire(self.cache/back.INVENTAIRE);snapshot['ids_couverts']=[]
        inc.ecrire(self.cache/back.INVENTAIRE,snapshot)
        fresh=back.preparer(self.cache,self.now)
        self.assertEqual(fresh['chevaux']['123456']['sync'],'A_FAIRE')
        self.assertEqual(fresh['chevaux']['123456']['rattrapage_complet_au_utc'],old_stamp)
        self.assertEqual(fresh['bilan']['cibles_completees'],0)
        self.assertEqual(back.prochaine_tache(fresh,self.now,{}),('123456','SYNC'))

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
        self.assertEqual(inc.lire(self.cache/'etat_persistant.json')['chevaux']['123456']['origine'],'RATTRAPAGE_GLOBAL')
        self.assertEqual(before,{name:(self.cache/name).read_bytes() for name in protected})

    def test_publication_echouee_reprise_sans_geny(self):
        self.seed()
        sync=Mock(side_effect=RuntimeError('Sheets indisponible'))
        first=inc.run(self.cache,mode='rattrapage',collect=self.collect,sync=sync)
        first['chevaux']['123456']['prochaine_sync_utc']=(self.now-timedelta(minutes=1)).isoformat()
        inc.ecrire(self.cache/back.QUEUE,first)
        collect=Mock(side_effect=AssertionError('Ne pas recollecter'))
        second=inc.run(self.cache,mode='rattrapage',max_chevaux=0,collect=collect,sync=lambda h:{})
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
        self.assertEqual(config['concurrency'],{'group':'pmu-donnees-production','cancel-in-progress':'false','queue':'max'})
        self.assertIn('workflow_dispatch',config['on'])
        self.assertNotEqual(back.QUEUE,inc.QUEUE)

    def test_identite_de_capture_contradictoire_n_est_pas_declaree_complete(self):
        self.seed(complete=True,covered=True)
        data=doc(self.now);data['identifiant_cheval']='999999'
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json',data)
        state=back.preparer(self.cache,self.now)
        self.assertFalse(state['chevaux']['123456'].get('rattrapage_complet_au_utc'))

    def test_nom_sans_course_est_eligible_a_la_recherche_individuelle(self):
        snapshot=inc.lire(self.cache/back.INVENTAIRE)
        snapshot['chevaux']=[{'nom':'Sans lien'}];inc.ecrire(self.cache/back.INVENTAIRE,snapshot)
        state=back.preparer(self.cache,self.now);state['sync_kpi']='OK';back.bilan(state)
        key = next(iter(state['chevaux']))
        self.assertEqual(back.prochaine_tache(state,self.now,{}),(key,'COLLECTE'))
        self.assertEqual(back.prochaine_tache(state,self.now,{('NOM', 'SANSLIEN'): 1}),(None,'TERMINE_PASSAGE'))
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

    def test_erreur_ancienne_effacee_seulement_apres_preuve_de_completion(self):
        self.seed(complete=True,covered=True)
        state=back.preparer(self.cache,self.now)
        state['chevaux']['123456'].update(erreur='ancien échec',
            prochain_essai_utc=(self.now+timedelta(hours=6)).isoformat())
        inc.ecrire(self.cache/back.QUEUE,state)
        refreshed=back.preparer(self.cache,self.now)
        horse=refreshed['chevaux']['123456']
        self.assertEqual(horse['erreur'],'');self.assertNotIn('prochain_essai_utc',horse)

    def test_preuve_ancienne_ne_cache_ni_date_future_ni_identifiant_ou_url_differents(self):
        self.seed(complete=True,covered=True)
        original=inc.lire(self.cache/'historiques/123456/historique_geny.json')
        state=back.preparer(self.cache,self.now)
        for changes in ({'extrait_utc':(self.now+timedelta(days=1)).isoformat()},
                        {'identifiant_cheval':'999999'},
                        {'source_url':'https://www.geny.com/cheval/999999-autre'}):
            with self.subTest(changes=changes):
                inc.ecrire(self.cache/back.QUEUE,state)
                inc.ecrire(self.cache/'historiques/123456/historique_geny.json',{**original,**changes})
                checked=back.preparer(self.cache,self.now)
                self.assertFalse(checked['chevaux']['123456'].get('rattrapage_complet_au_utc'))

    def test_collecteur_courant_cede_uniquement_au_cycle_pmu(self):
        response=Mock();response.json.return_value={'workflow_runs':[
            {'path':'.github/workflows/rattrapage-historiques.yml'},
            {'path':'.github/workflows/historiques-incrementaux.yml'}]}
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'owner/repo','GH_TOKEN':'factice'}), \
             patch('requests.get',return_value=response):
            paths={'.github/workflows/pmu-v16.yml'}
            self.assertIsNone(back.priorite_production(paths))
            response.json.return_value={'workflow_runs':[{'path':'.github/workflows/pmu-v16.yml'}]}
            self.assertEqual(back.priorite_production(paths),'PRIORITE_PRODUCTION_EN_ATTENTE')

    def test_conflit_apres_completion_reouvre_la_verification(self):
        self.seed(complete=True,covered=True)
        state=back.preparer(self.cache,self.now)
        state['chevaux']['123456']['conflit_identite']=True
        inc.ecrire(self.cache/back.QUEUE,state)
        checked=back.preparer(self.cache,self.now)
        self.assertFalse(checked['chevaux']['123456'].get('rattrapage_complet_au_utc'))
        self.assertEqual(checked['chevaux']['123456']['collecte'],'IDENTITE_A_VERIFIER')

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

    def test_priorite_detecte_un_cycle_pmu_queued(self):
        pending, queued = Mock(), Mock()
        pending.json.return_value = {'workflow_runs': []}
        queued.json.return_value = {'workflow_runs': [{'path': '.github/workflows/pmu-v16.yml@main'}]}
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'owner/repo',
                                     'GH_TOKEN': 'factice'}), patch('requests.get', side_effect=[pending, queued]) as get:
            self.assertEqual(back.priorite_production({'.github/workflows/pmu-v16.yml'}),
                             'PRIORITE_PRODUCTION_EN_ATTENTE')
        self.assertNotIn('created', get.call_args_list[0].kwargs['params'])
        self.assertTrue(get.call_args_list[1].kwargs['params']['created'].startswith('>='))

    def test_courses_passees_regroupe_la_casse_et_recense_les_conflits(self):
        source = 'PMU_API_PARTICIPANTS'
        for index, name in enumerate(('Étoile du Nord', 'étoile du nord'), 1):
            race = f'2020-01-0{index}_R1C1.json'
            inc.ecrire(self.cache/'arrivees'/race, {
                'source': source, 'verifie_utc': '2020-01-03T10:00:00+00:00',
                'arrivee': [{'numero': 3, 'rang': 1}],
            })
            inc.ecrire(self.cache/'partants_actuels'/race, {'source': source, 'chevaux': {
                '1': {'nom': name, 'statut_np': 'PARTANT'},
                '2': {'nom': 'Non partant', 'statut_np': 'NON_PARTANT'},
            }})
        state = {'chevaux': {
            'c1': {'nom': 'Étoile du Nord', 'motif_actualisation': 'MANQUANT'},
            'c2': {'nom': 'étoile du nord', 'motif_actualisation': 'MANQUANT'},
        }}
        back.preparer_noms_passes(self.cache, state, self.now)
        report = inc.lire(self.cache/back.QUEUE.parent/'courses_passees_par_nom.json')
        self.assertEqual(set(report['noms']), {'étoile du nord'})
        self.assertEqual(report['noms']['étoile du nord']['courses'],
                         {'2020-01-01_R1C1': ['1'], '2020-01-02_R1C1': ['1']})
        self.assertEqual(back.prochaine_tache(state, self.now, {}), ('c1', 'COLLECTE'))
        self.assertEqual(back.prochaine_tache(state, self.now, {('COLLECTE', 'c1'): 1}),
                         (None, 'TERMINE_PASSAGE'))
        state['chevaux']['c1']['id'] = '12345'
        state['chevaux']['c2']['id'] = '67890'
        back.preparer_noms_passes(self.cache, state, self.now)
        self.assertEqual(state['courses_passees_par_nom']['bilan'], {'IDENTITE_A_VERIFIER': 1})
        self.assertEqual(back.prochaine_tache(state, self.now, {}), (None, 'TERMINE_PASSAGE'))

    def test_formats_sheet_et_pmu_designent_un_seul_contexte(self):
        day='2020-01-01'
        inc.ecrire(self.cache/'partants_actuels'/f'{day}_R1C1.json',{'chevaux':{'1':{'nom':'Test'}}})
        targets=back.inventaire_local(self.cache,{'chevaux':[{'nom':'Test','numero':'1',
            'engagement':day+'|VINCENNES|R1C1','origine':'SHEETS:Courses & Prévisions'}]})
        self.assertEqual(len(targets),1)
        self.assertEqual(next(iter(targets.values()))['engagement'],day+'_R1C1')

    def test_lot_existant_conserve_deux_observations_mais_ne_collecte_qu_une_fois(self):
        day='2020-01-01'
        snapshot=inc.lire(self.cache/back.INVENTAIRE)
        snapshot['chevaux']=[{'nom':'Test','numero':'1','engagement':day+'|VINCENNES|R1C1'}]
        inc.ecrire(self.cache/back.INVENTAIRE,snapshot)
        inc.ecrire(self.cache/'partants_actuels'/f'{day}_R1C1.json',{'chevaux':{'1':{'nom':'Test'}}})
        inc.ecrire(self.cache/'orchestration/correspondances_geny.json',{day+'_R1C1':'GENY-1698061'})
        inc.ecrire(self.cache/back.QUEUE,{'version':1,'mode':'RATTRAPAGE_GLOBAL','inventaire_id':'lot-fige',
            'sync_kpi':'A_REPRENDRE','chevaux':{
                'ancien-a':{'nom':'Test','numero':'1','engagement':day+'_R1C1'},
                'ancien-b':{'nom':'Test','engagement':day+'|VINCENNES|R1C1'}}})
        collect=Mock(side_effect=self.collect)
        state=inc.run(self.cache,mode='rattrapage',collect=collect,
            sync=lambda h:{'Historique chevaux':{'lignes_ajoutees':1}})
        self.assertEqual(state['inventaire_id'],'lot-fige')
        self.assertEqual(set(state['chevaux']),{'ancien-a','ancien-b'})
        self.assertEqual(collect.call_count,1)
        self.assertEqual(state['bilan']['cibles_completees'],2)
        self.assertEqual(state['bilan']['cibles_equivalentes'],1)
        self.assertEqual(state['bilan']['ajouts_confirmes'],1)
        again=back.preparer(self.cache,datetime.now(timezone.utc))
        self.assertEqual(again['bilan']['ajouts_confirmes'],1)
        report=inc.lire(self.cache/back.QUEUE.parent/'bilan.json')
        self.assertNotIn('chevaux',report);self.assertEqual(report['inventaire_id'],'lot-fige')

    def test_deux_courses_differentes_ne_sont_pas_des_alias_sur_le_seul_nom(self):
        snapshot=inc.lire(self.cache/back.INVENTAIRE)
        snapshot['chevaux']=[{'nom':'Homonyme','numero':'1','engagement':'2020-01-01|VINCENNES|R1C1'},
                             {'nom':'Homonyme','numero':'1','engagement':'2020-01-02|VINCENNES|R1C1'}]
        inc.ecrire(self.cache/back.INVENTAIRE,snapshot)
        state=back.preparer(self.cache,self.now)
        self.assertEqual(state['bilan']['cibles_inventoriees'],2)
        self.assertEqual(state['bilan']['cibles_equivalentes'],0)

    def test_numero_absent_reste_non_resolu_si_nom_ambigu_dans_la_meme_course(self):
        day='2020-01-01';engagement=day+'|VINCENNES|R1C1'
        snapshot=inc.lire(self.cache/back.INVENTAIRE)
        snapshot['chevaux']=[{'nom':'Test','numero':'1','engagement':engagement},
                             {'nom':'Test','numero':'2','engagement':engagement}]
        inc.ecrire(self.cache/back.INVENTAIRE,snapshot)
        inc.ecrire(self.cache/back.QUEUE,{'version':1,'inventaire_id':'fige','chevaux':{
            'ancienne-cible':{'nom':'Test','engagement':engagement}}})
        state=back.preparer(self.cache,self.now)
        self.assertFalse(state['chevaux']['ancienne-cible'].get('numero'))
        self.assertEqual(state['bilan']['liens_a_resoudre'],1)

    def test_identifiant_observe_sans_url_n_est_qu_un_candidat_a_verifier(self):
        snapshot=inc.lire(self.cache/back.INVENTAIRE)
        snapshot['chevaux']=[{'id':'999999','nom':'Vu dans Sheet'}]
        inc.ecrire(self.cache/back.INVENTAIRE,snapshot)
        state=back.preparer(self.cache,self.now);horse=state['chevaux']['999999']
        self.assertNotIn('geny',horse)
        self.assertEqual(horse['lien_candidat'],'https://www.geny.com/cheval/999999')
        self.assertEqual(back.prochaine_tache(state,self.now,{}),('999999','COLLECTE'))

    def test_page_candidate_exige_http_identifiant_final_et_nom(self):
        from pmu_geny.historique_individuel import verifier_candidat
        horse={'id':'123456','nom':'Test'};url='https://www.geny.com/cheval/123456-test'
        self.assertEqual(verifier_candidat(horse,url,200,'Cheval TEST',self.cache)['id'],'123456')
        for final,status,text in [(url,404,'Test'),('https://www.geny.com/cheval/999999',200,'Test'),
                                   (url,200,'Autre cheval'),('https://example.com/cheval/123456',200,'Test')]:
            with self.assertRaisesRegex(ValueError,'LIEN_CANDIDAT_NON_VERIFIE'):
                verifier_candidat(horse,final,status,text,self.cache)

    def test_inventaire_reconnait_une_performance_sous_sa_cle_deja_publiee(self):
        session=SheetsSession()
        session.tables['Historique chevaux']=[
            ['cle_performance','identifiant_cheval','cheval','classement','date_course_historique',
             'hippodrome','discipline','distance_m','chrono'],
            ['ancienne','123456','Test','3','2020-01-01','Vincennes','Attelé','2700',"1'15"]]
        source={'Historique chevaux':{'nouvelle':{'cle_performance':'nouvelle','identifiant_cheval':'123456',
            'cheval':'Test','classement':'3','date_course_historique':'2020-01-01','hippodrome':'Vincennes',
            'discipline':'Attelé','distance_m':'2700','chrono':"1'15"}},
            'Courses & Prévisions':{},'Résultats & Analyse':{}}
        with patch.dict(os.environ,{'PMU_SHEETS_LOCK_DIR':str(self.cache),
             'PMU_SHEETS_CONTROLES':str(self.cache/'controle.jsonl'),'GITHUB_STEP_SUMMARY':''}), \
             patch('pmu_geny.sync_google_sheets.source_rows',return_value=source),patch('builtins.print'):
            inventory=SynchroniseurSheets(self.cache,'fake',session=session).inventaire_rattrapage()
        self.assertEqual(inventory['ids_couverts'],['123456'])
        self.assertEqual(session.writes,[])

    def test_delai_production_du_meme_cheval_respecte_dans_le_stock(self):
        self.seed()
        retry=(self.now+timedelta(hours=6)).isoformat()
        inc.ecrire(self.cache/inc.QUEUE,{'version':1,'chevaux':{
            'autre-contexte':{'nom':'TEST','prochain_essai_utc':retry}}})
        state=back.preparer(self.cache,self.now)
        self.assertEqual(state['chevaux']['123456']['prochain_essai_utc'],retry)
        self.assertEqual(back.prochaine_tache(state,self.now,{}),(None,'TERMINE_PASSAGE'))

    def test_autre_contexte_du_partant_en_attente_exclu_du_fond(self):
        candidate={'nom':'Test','id':'123456','geny':{'id':'123456'},
                   'motif_actualisation':'HISTORIQUE_ABSENT_PARTIEL_OU_NON_DATE'}
        state={'noms_partants_proteges':['TEST'],'chevaux':{
            'ancien':candidate,'autre':{**candidate,'id':'999999','nom':'Autre'}}}
        self.assertEqual(back.prochaine_tache(state,self.now,{}),('autre','COLLECTE'))
        # La protection porte sur les requêtes Geny, pas la reprise d'une publication.
        candidate['sync']='A_FAIRE'
        self.assertEqual(back.prochaine_tache(state,self.now,{}),('ancien','SYNC'))

    def test_creneau_libre_collecte_stock_sans_toucher_previsions_puis_cede_au_partant(self):
        from pmu_geny.preparation_prochaines import autoriser_fond
        from zoneinfo import ZoneInfo
        self.seed()
        today=self.now.astimezone(ZoneInfo('Europe/Paris')).date()
        departure=self.now+timedelta(hours=3)
        day=departure.astimezone(ZoneInfo('Europe/Paris')).date().isoformat();engagement=day+'_R1C8'
        for date in (today,today+timedelta(days=1)):
            program=[{'code':'R1C8','depart':departure.isoformat()}] if date.isoformat()==day else []
            inc.ecrire(self.cache/'sources_pmu'/f'programme_{date}.json',
                       {'date_controle_utc':self.now.isoformat(),'programme':program})
        inc.ecrire(self.cache/'partants_actuels'/f'{engagement}.json',
                   {'capture_utc':self.now.isoformat(),'chevaux':{'1':{
                       'nom':'Prioritaire','statut_np':'PARTANT','age_ans':5,
                       'sexe':'Femelle','gains_euros':1000,'ferrure':'D4'}}})
        inc.ecrire(self.cache/'orchestration/correspondances_geny.json',{engagement:'GENY-1698061'})
        queue={'version':1,'chevaux':{engagement+'_1':{'nom':'Prioritaire',
            'prochain_essai_utc':(self.now+timedelta(hours=6)).isoformat()}}}
        inc.ecrire(self.cache/inc.QUEUE,queue)
        prediction=self.cache/'pronostics'/f'{engagement}_direct.json'
        snapshot=self.cache/'ml/instantanes'/f'{engagement}.json'
        inc.ecrire(prediction,{'calcul_utc':self.now.isoformat(),'top3':[{'numero':n} for n in (1,2,3)]})
        inc.ecrire(snapshot,{'capture_utc':self.now.isoformat(),'chevaux':[]})
        frozen={p:p.read_bytes() for p in (prediction,snapshot,self.cache/inc.QUEUE)}
        self.assertIsNone(autoriser_fond(self.cache,self.now))
        collect=Mock(side_effect=self.collect)
        state=inc.run(self.cache,mode='rattrapage',max_chevaux=1,collect=collect,
            sync=lambda h:{},checkpoint=lambda c:None,
            stop_requested=lambda:autoriser_fond(self.cache,datetime.now(timezone.utc)))
        self.assertEqual(state['bilan']['captures_validees'],1)
        self.assertEqual(collect.call_args.args[0]['nom'],'Test')
        self.assertIn('PRIORITAIRE',state['noms_partants_proteges'])
        for p,data in frozen.items():self.assertEqual(p.read_bytes(),data)
        queue['chevaux'][engagement+'_1']['prochain_essai_utc']=self.now.isoformat()
        inc.ecrire(self.cache/inc.QUEUE,queue)
        collect.reset_mock()
        state=inc.run(self.cache,mode='rattrapage',collect=collect,
            sync=lambda h:{},checkpoint=lambda c:None,
            stop_requested=lambda:autoriser_fond(self.cache,datetime.now(timezone.utc)))
        collect.assert_not_called()
        self.assertEqual(state['motif_fin_passage'],'PARTANT_PRIORITAIRE_DISPONIBLE')

    def test_bilan_retient_le_dernier_controle_date_meme_apres_nettoyage_des_lignes(self):
        state={'chevaux':{
            'ancien':{'sync_utc':'2026-11-14T21:00:00+00:00','sync_details':{'Historique chevaux':{
                'controle':{'statut':'VALIDE','lignes_apres':15647}}}},
            'recent':{'sync_utc':'2026-11-14T23:00:00+00:00','sync_details':{'Historique chevaux':{
                'controle':{'statut':'VALIDE','lignes_apres':14465}}}},
            'sans-date':{'sync_details':{'Historique chevaux':{'controle':{'statut':'VALIDE','lignes_apres':99999}}}}}}
        report=back.rapport(state)
        self.assertEqual(report['derniere_ecriture_controlee']['lignes_apres'],14465)
        self.assertEqual(report['derniere_ecriture_controlee']['sync_utc'],'2026-11-14T23:00:00+00:00')


if __name__=='__main__':unittest.main()
