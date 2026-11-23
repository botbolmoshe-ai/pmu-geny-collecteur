"""Non-régression, concurrence et appels API du moteur commun."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock

from test_v26_chaine_offline import SheetsSession,Response
from pmu_geny.moteur_sheets import SynchroniseurSheets,SynchronisationOccupee,ErreurSynchronisation,verrou_local


class SessionTracee(SheetsSession):
    def __init__(self):
        super().__init__();self.reads=[]
    def get(self,url,**kwargs):
        self.reads.append(url);return super().get(url,**kwargs)


class MoteurTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name)
        env=patch.dict(os.environ,{'PMU_SHEETS_LOCK_DIR':self.tmp.name,
            'PMU_SHEETS_CONTROLES':str(self.cache/'controle.jsonl'),'GITHUB_STEP_SUMMARY':'',
            'GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON':'{}'})
        env.start();self.addCleanup(env.stop)
        console=patch('builtins.print');console.start();self.addCleanup(console.stop)
        self.source={'Historique chevaux':{'perf':{'cle_performance':'perf','identifiant_cheval':'123456',
            'cheval':'Test','classement':'3'}},'Courses & Prévisions':{},'Résultats & Analyse':{}}

    def test_les_deux_declencheurs_donnent_le_meme_historique(self):
        full,scoped=SessionTracee(),SessionTracee()
        full.tables['Résultats & Analyse']=[['course_key']]
        with patch('pmu_geny.sync_google_sheets.source_rows',return_value=self.source), \
             patch('pmu_geny.kpi_registre.calculer_kpi',return_value={}):
            SynchroniseurSheets(self.cache,'fake-full',session=full).synchroniser_tables(
                self.source,scope='CYCLE_PMU',full_source=True)
            SynchroniseurSheets(self.cache,'fake-scoped',session=scoped).synchroniser_cheval(
                {'nom':'Test','geny':{'id':'123456'}})
        self.assertEqual(full.tables['Historique chevaux'],scoped.tables['Historique chevaux'])

    def test_suppression_equidia_puis_actualisation_de_la_voisine_sans_decalage(self):
        class Colonnes(SessionTracee):
            def post(self,url,**kwargs):
                if 'requests' in kwargs['json']:
                    self.writes.append((url,kwargs))
                    for request in kwargs['json']['requests']:
                        if 'deleteDimension' not in request:continue
                        r=request['deleteDimension']['range']
                        for row in self.tables['Courses & Prévisions']:
                            del row[r['startIndex']:r['endIndex']]
                    return Response({})
                return super().post(url,**kwargs)
        session=Colonnes();session.tables['Courses & Prévisions']=[
            ['course_key','numero','Avis expert Equidia','Avis expert PMU',
             'Avis expert ZEturf','Pronostic Equidia · Ordre publié','Pronostic ZEturf · Ordre publié',
             'Source Equidia · URL et collecte UTC','Source ZEturf · URL et collecte UTC'],
            ['k','1','ancien avis','PMU ancien','avis ZEturf','1,2,3','1,2,3','source E','source Z']]
        engine=SynchroniseurSheets(self.cache,'fake',session=session)
        source={'Courses & Prévisions':{'k':{'course_key':'k','numero':'1','avis_pmu':'PMU actualisé'}}}
        first=engine.synchroniser_tables(source,scope='CYCLE_PMU',allow_structure=True)
        second=engine.synchroniser_tables(source,scope='CYCLE_PMU',allow_structure=True)
        self.assertNotIn('Avis expert Equidia',session.tables['Courses & Prévisions'][0])
        self.assertFalse(any('equidia' in h.lower() or 'zeturf' in h.lower()
                             for h in session.tables['Courses & Prévisions'][0]))
        self.assertEqual(session.tables['Courses & Prévisions'][1][2],'PMU actualisé')
        self.assertEqual(second['Courses & Prévisions']['cellules_actualisees'],0)

    def test_verrou_local_refuse_un_second_ecrivain_avant_toute_requete(self):
        session=SessionTracee();engine=SynchroniseurSheets(self.cache,'fake',session=session)
        with verrou_local('fake'):
            with self.assertRaises(SynchronisationOccupee):
                engine.synchroniser_tables(self.source,scope='TEST')
        self.assertEqual(session.reads,[]);self.assertEqual(session.writes,[])
        # Le verrou est libéré même après une erreur.
        engine.synchroniser_tables({'Historique chevaux':self.source['Historique chevaux']},scope='TEST')

    def test_echec_maj_ne_poursuit_pas_avec_les_ajouts(self):
        class Refus(SessionTracee):
            def post(self,url,**kwargs):
                self.writes.append((url,kwargs))
                return type('Bad',(),{'status_code':503})()
        session=Refus();session.tables['Historique chevaux'].append(['perf','123456','Test','2'])
        incoming={**self.source['Historique chevaux'],
                  'nouveau':{'cle_performance':'nouveau','identifiant_cheval':'123456','cheval':'Test','classement':'4'}}
        with self.assertRaises(ErreurSynchronisation):
            SynchroniseurSheets(self.cache,'fake',session=session).synchroniser_tables(
                {'Historique chevaux':incoming},scope='TEST')
        self.assertEqual(len(session.writes),1)
        self.assertFalse(any(url.endswith(':append') for url,kwargs in session.writes))

    def test_append_commis_mais_reponse_perdue_reprise_sans_doublon(self):
        class ReponsePerdue(SessionTracee):
            fail=True
            def post(self,url,**kwargs):
                result=super().post(url,**kwargs)
                if url.endswith(':append') and self.fail:
                    self.fail=False;raise TimeoutError('Reponse perdue apres commit')
                return result
        session=ReponsePerdue();engine=SynchroniseurSheets(self.cache,'fake',session=session)
        source={'Historique chevaux':self.source['Historique chevaux']}
        with self.assertRaises(TimeoutError):engine.synchroniser_tables(source,scope='TEST')
        second=engine.synchroniser_tables(source,scope='TEST')
        self.assertEqual(second['Historique chevaux']['lignes_ajoutees'],0)
        self.assertEqual(len(session.tables['Historique chevaux']),2)

    def test_anomalie_historique_bloque_avant_modification_des_autres_onglets(self):
        from pmu_geny.controle_sync_sheets import BlocageSynchronisation
        session=SessionTracee()
        session.tables['Historique chevaux']+=[['perf','123456','Test','3']]*2
        source={'Courses & Prévisions':{'c':{'course_key':'course1','numero':'1','cheval':'MODIF'}},
                'Historique chevaux':self.source['Historique chevaux']}
        with self.assertRaises(BlocageSynchronisation):
            SynchroniseurSheets(self.cache,'fake',session=session).synchroniser_tables(source,scope='CYCLE_PMU')
        self.assertEqual(session.writes,[])

    def test_consolidation_kpi_et_connexion_une_fois_par_passage(self):
        from scripts.synchroniser_un_historique import synchroniser
        horses=[{'nom':f'Horse{i}','geny':{'id':str(1000+i)}} for i in range(1,4)]
        def simulate(shared):
            session=SessionTracee();stage=[0]
            session.tables['Courses & Prévisions']=session.tables['Courses & Prévisions'][:1]+[
                [f'course{i}',str(i),f'Horse{i}','','','','OUI'] for i in range(1,4)]
            def source(*args):
                return {'Historique chevaux':{str(i):{'cle_performance':str(i),'identifiant_cheval':str(1000+i),
                         'cheval':f'Horse{i}','classement':'3'} for i in range(1,stage[0]+1)},
                        'Courses & Prévisions':{str(i):{'course_key':f'course{i}','numero':str(i),
                         'cheval':f'Horse{i}','date_course':'2026-11-14','historique_statut':'HISTO_OK_NOM',
                         'historique_nb_courses_datees':1} for i in range(1,stage[0]+1)},
                        'Résultats & Analyse':{}}
            with patch('pmu_geny.sync_google_sheets.source_rows',side_effect=source), \
                 patch('pmu_geny.kpi_registre.calculer_kpi',side_effect=lambda *args, **kwargs:{'Indicateur test':(stage[0],'preuve')}), \
                 patch('pmu_geny.moteur_sheets.ouvrir_session',return_value=session) as opened:
                engine=SynchroniseurSheets(self.cache,'fake') if shared else None
                for i,horse in enumerate(horses,1):
                    stage[0]=i
                    if shared:engine.synchroniser_cheval(horse,include_kpi=False)
                    else:synchroniser(horse,'fake',cache=self.cache)
                if shared:engine.synchroniser_kpi()
                sessions=opened.call_count
            kpi_reads=sum('Data%20Quality' in url or 'Data Quality' in url for url in session.reads)
            return session,sessions,kpi_reads
        baseline,old_sessions,old_kpi=simulate(False)
        grouped,new_sessions,new_kpi=simulate(True)
        self.assertEqual(baseline.tables,grouped.tables)
        self.assertEqual((old_sessions,new_sessions),(3,1))
        self.assertEqual((old_kpi,new_kpi),(3,1))
        old_calls=len(baseline.reads)+len(baseline.writes)
        new_calls=len(grouped.reads)+len(grouped.writes)
        self.assertLess(new_calls,old_calls)
        report={'chevaux':3,'avant':{'sessions':old_sessions,'lectures_kpi':old_kpi,'appels_api':old_calls},
                'moteur_partage':{'sessions':new_sessions,'lectures_kpi':new_kpi,'appels_api':new_calls},
                'contenu_final_identique':True}
        Path('resultats/validation-moteur-unique').mkdir(parents=True,exist_ok=True)
        Path('resultats/validation-moteur-unique/simulation.json').write_text(json.dumps(report,indent=2))

    def test_workflows_partagent_le_verrou_et_ne_s_annulent_pas(self):
        import yaml
        root=Path(__file__).resolve().parents[1]
        groups=[]
        for file in ('pmu-v16.yml','historiques-incrementaux.yml'):
            config=yaml.load((root/'.github/workflows'/file).read_text(),Loader=yaml.BaseLoader)
            groups.append(config['concurrency']['group'])
            self.assertEqual(config['concurrency']['cancel-in-progress'],'false')
        self.assertEqual(groups[0], 'pmu-donnees-production')
        self.assertTrue(groups[1].endswith("|| 'pmu-donnees-production' }}"))

    def test_reprise_kpi_seule_sans_recollecter_ni_republier_les_chevaux(self):
        from datetime import datetime,timedelta,timezone
        from pmu_geny import historiques_incrementaux as inc
        from test_v26_incremental_offline import doc
        now=datetime.now(timezone.utc);engagement=now.date().isoformat()+'_R1C1'
        old=doc(now-timedelta(days=2))
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json',old)
        inc.ecrire(self.cache/'etat_persistant.json',{'version':1,'chevaux':{
            '123456':{'id':'123456','nom':'Test','statut':'COMPLET'}}})
        inc.ecrire(self.cache/'partants_actuels'/f'{engagement}.json',{'chevaux':{
            '1':{'nom':'Test','statut_np':'PARTANT'}}})
        inc.ecrire(self.cache/'orchestration/correspondances_geny.json',{engagement:'GENY-1698061'})
        def collect(horse,out):
            dest=self.cache/'extraction/123456';data=doc(datetime.now(timezone.utc),old['performances'])
            inc.ecrire(dest/'historique_geny.json',data)
            return {'complet':True,'identite_verifiee':True,'statut':'COMPLET',
                    'geny':{'id':'123456','nom':'Test','url_geny':data['source_url']},'dossier':str(dest)}
        failed=Mock();failed.synchroniser_cheval.return_value={}
        failed.synchroniser_kpi.side_effect=RuntimeError('KPI indisponible')
        resumed=Mock();resumed.synchroniser_kpi.return_value={}
        with patch.dict(os.environ,{'GOOGLE_SHEETS_ID':'fake'}), \
             patch('pmu_geny.moteur_sheets.SynchroniseurSheets',side_effect=[failed,resumed]) as factory, \
             patch.object(inc.time,'sleep'),patch.object(inc,'executer_enfant',wraps=collect) as extraction:
            with self.assertRaisesRegex(RuntimeError,'KPI indisponible'):
                inc.run(self.cache,publier=True,checkpoint=lambda cache:None,collect=extraction)
            self.assertEqual(inc.lire(self.cache/inc.QUEUE)['sync_kpi'],'A_REPRENDRE')
            result=inc.run(self.cache,publier=True,checkpoint=lambda cache:None,collect=extraction)
        self.assertEqual(result['sync_kpi'],'OK');self.assertEqual(extraction.call_count,1)
        self.assertEqual(factory.call_count,2);resumed.synchroniser_cheval.assert_not_called()
        failed.synchroniser_cheval.assert_called_once()
        self.assertFalse(failed.synchroniser_cheval.call_args.kwargs['include_kpi'])
        resumed.synchroniser_kpi.assert_called_once();failed.fermer.assert_called_once()


if __name__=='__main__':unittest.main()
