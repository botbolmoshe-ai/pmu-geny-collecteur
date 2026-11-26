import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from pmu_geny import historiques_incrementaux as inc
from pmu_geny import historique_individuel as individuel
from pmu_geny.collecte_geny_v4 import collecter_page
from pmu_geny.historiques_partiels import conserver
from pmu_geny.liaison_chevaux_v22 import etablir
from pmu_geny.sync_google_sheets import source_rows
from test_v26_incremental_offline import doc


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        self.geny={'id':'123456','nom':'Test','url_geny':'https://www.geny.com/cheval/123456-test/course/1698061'}
        self.horse={'nom':'Test','engagement':'2026-11-17_R3C1','numero':'1',
                    'course_url':'https://www.geny.com/course/1698061/partants-pronostics'}
        self.pw=Mock();self.browser=self.pw.chromium.launch.return_value
        self.ctx=self.browser.new_context.return_value;self.page=self.ctx.new_page.return_value
        self.ctx.pages=[self.page]

    def test_un_seul_navigateur_et_la_fiche_canonique_deja_chargee_est_reutilisee(self):
        self.page.url=self.geny['url_geny'].split('/course/')[0]
        with patch('playwright.sync_api.sync_playwright') as driver, \
             patch.object(individuel,'resolve',return_value=self.geny) as resolve, \
             patch.object(individuel,'extraire_cheval',side_effect=TimeoutError('interruption')) as extract, \
             patch.object(individuel.time,'sleep') as sleep:
            driver.return_value.__enter__.return_value=self.pw
            result=individuel.collecter(self.horse,self.out)
        self.pw.chromium.launch.assert_called_once();self.browser.new_context.assert_called_once()
        resolve.assert_called_once_with(self.horse,self.out,self.page,arreter=ANY)
        self.assertIs(extract.call_args.kwargs['page'],self.page)
        self.assertTrue(extract.call_args.kwargs['page_chargee']);sleep.assert_not_called()
        self.browser.close.assert_called_once()
        self.assertEqual(result['geny'],self.geny)
        self.assertEqual(inc.lire(self.out/'resolution_geny.json')['geny'],self.geny)

    def test_lien_connu_evite_la_resolution_de_la_course(self):
        self.page.url='about:blank'
        with patch('playwright.sync_api.sync_playwright') as driver, \
             patch.object(individuel,'resolve') as resolve, \
             patch.object(individuel,'extraire_cheval',return_value={'statut':'ACCES_REFUSE_403'}) as extract:
            driver.return_value.__enter__.return_value=self.pw
            result=individuel.collecter({**self.horse,'geny':self.geny},self.out)
        resolve.assert_not_called();extract.assert_called_once()
        self.assertEqual(result['statut'],'ACCES_REFUSE_403')

    def test_refus_a_la_resolution_arrete_avant_toute_extraction(self):
        with patch('playwright.sync_api.sync_playwright') as driver, \
             patch.object(individuel,'resolve',side_effect=RuntimeError('ACCES_LIMITE_429')), \
             patch.object(individuel,'extraire_cheval') as extract:
            driver.return_value.__enter__.return_value=self.pw
            result=individuel.collecter(self.horse,self.out)
        extract.assert_not_called();self.assertEqual(result['statut'],'ACCES_LIMITE_429')

    def test_page_deja_chargee_refusee_sans_nouvelle_navigation(self):
        page=Mock();page.title.return_value='Accès refusé - Geny'
        page.locator.return_value.inner_text.return_value='403\nAccès refusé'
        page.content.return_value='<title>Accès refusé - Geny</title>'
        with patch('pmu_geny.collecte_geny_v4.parse_career') as parse:
            self.assertEqual(collecter_page(page,self.geny['url_geny'],self.out,
                                            page_chargee=True,http_status=403),3)
        page.goto.assert_not_called();parse.assert_not_called()

    def test_resolution_sauvee_reprise_apres_arret_du_sous_processus(self):
        proof={'geny':self.geny,'engagement':self.horse['engagement'],'numero':'1'}
        inc.ecrire(self.out/'resolution_geny.json',proof)
        horse=copy.deepcopy(self.horse);inc.memoriser_resolution(horse,{},self.out)
        self.assertEqual(horse['geny'],self.geny);self.assertNotIn('id',horse)
        other={**self.horse,'numero':'2'};inc.memoriser_resolution(other,{},self.out)
        self.assertNotIn('geny',other)
        bad={**self.geny,'url_geny':'https://www.geny.com.evil.test/cheval/123456'}
        inc.memoriser_resolution(other,{'geny':bad},self.out);self.assertNotIn('geny',other)


class HistoriquesPartielsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name);self.now=datetime.now(timezone.utc)
        self.document=doc(self.now);self.document.update(nombre_annonce_geny=4,statut='PARTIEL_A_CONTROLER',complet=False)
        self.geny={'id':'123456','nom':'Test','url_geny':self.document['source_url']}
        self.folder=self.cache/'capture';inc.ecrire(self.folder/'historique_geny.json',self.document)
        self.report={'complet':False,'statut':'PARTIEL_HISTORIQUE','motifs':['NB_COURSES_DIFFERENT:1/4'],
                     'identite_verifiee':True,'geny':self.geny,'dossier':str(self.folder)}
        self.horse={'nom':'Test'}
        inc.ecrire(self.cache/'etat_persistant.json',{'version':1,'chevaux':{}})

    def test_partiel_exploitable_sans_inventer_une_completion(self):
        self.assertTrue(conserver(self.cache,self.horse,self.report))
        self.assertIsNone(inc.capture_valide(self.cache,'123456'))
        self.assertNotIn('historique_complet_au_utc',self.horse)
        self.assertEqual(self.horse['collecte'],'PARTIEL_HISTORIQUE')
        self.assertEqual(inc.lire(self.cache/'etat_persistant.json')['chevaux']['123456']['statut'],'PARTIEL')
        link=etablir(self.cache,{'date':'2026-11-17','code':'R3C1'},[{'numero':1,'nom':'Test'}])['1']
        self.assertEqual(link['cheval_id'],'123456')
        self.assertEqual(link['historique']['statut'],'PARTIEL_HISTORIQUE')
        rows=source_rows(self.cache)['Historique chevaux']
        self.assertEqual(len(rows),1)
        self.assertEqual(next(iter(rows.values()))['statut_verification'],'EXTRACTION_GENY_PARTIELLE')

    def test_lignes_invalides_ou_futures_ecartees(self):
        invalid={**self.document['performances'][0],'date':self.now.date().isoformat(),'classement':''}
        future={**invalid,'date':(self.now+timedelta(days=2)).date().isoformat(),'classement':'1'}
        data={**self.document,'performances':self.document['performances']+[invalid,future]}
        inc.ecrire(self.folder/'historique_geny.json',data)
        self.assertTrue(conserver(self.cache,self.horse,self.report))
        self.assertEqual(self.horse['nombre_performances_partielles'],1)

    def test_remplacement_du_partiel_archive_la_capture_precedente(self):
        self.assertTrue(conserver(self.cache,self.horse,self.report))
        target=self.cache/'historiques_partiels/123456/historique_geny.json'
        previous=inc.lire(target)
        changed=copy.deepcopy(self.document)
        changed['performances'][0]['date']=(self.now-timedelta(days=5)).date().isoformat()
        inc.ecrire(self.folder/'historique_geny.json',changed)
        self.assertTrue(conserver(self.cache,self.horse,self.report))
        archives=list((self.cache/'historiques_versions/123456').glob('partiel-*.json'))
        self.assertEqual(len(archives),1);self.assertEqual(inc.lire(archives[0]),previous)

    def test_identite_refus_date_et_doublons_sont_bloquants(self):
        cases=[({'identite_verifiee':False},{}),({'statut':'ACCES_REFUSE_403'},{}),
               ({'geny':{**self.geny,'nom':'Autre'}},{}),
               ({},{'source_url':self.geny['url_geny'].replace('123456','999999')}),
               ({},{'extrait_utc':(self.now+timedelta(days=1)).isoformat()}),
               ({},{'performances':self.document['performances']*2})]
        for report,document in cases:
            inc.ecrire(self.folder/'historique_geny.json',{**self.document,**document})
            with self.subTest(report=report,document=document):
                self.assertFalse(conserver(self.cache,copy.deepcopy(self.horse), {**self.report,**report}))
                self.assertFalse((self.cache/'historiques_partiels').exists())

    def test_complet_prioritaire_et_pas_de_doublon_dans_la_source_sheets(self):
        self.assertTrue(conserver(self.cache,self.horse,self.report))
        complete=doc(self.now);inc.ecrire(self.cache/'historiques/123456/historique_geny.json',complete)
        before=(self.cache/'historiques/123456/historique_geny.json').read_bytes()
        self.assertTrue(conserver(self.cache,self.horse,self.report))
        self.assertEqual((self.cache/'historiques/123456/historique_geny.json').read_bytes(),before)
        link=etablir(self.cache,{'date':'2026-11-17','code':'R3C1'},[{'numero':1,'nom':'Test'}])['1']
        self.assertEqual(link['historique']['statut'],'COMPLET')
        rows=source_rows(self.cache)['Historique chevaux'];self.assertEqual(len(rows),1)
        self.assertEqual(next(iter(rows.values()))['statut_verification'],'EXTRACTION_GENY')

    def test_publication_partielle_puis_complete_sans_reinsertion(self):
        from pmu_geny.moteur_sheets import SynchroniseurSheets
        from test_v26_chaine_offline import SheetsSession
        self.assertTrue(conserver(self.cache,self.horse,self.report))
        partial=source_rows(self.cache)['Historique chevaux']
        session=SheetsSession();headers=list(next(iter(partial.values())))
        session.tables['Historique chevaux']=[headers]
        with patch.dict('os.environ',{'PMU_SHEETS_CONTROLES':str(self.cache/'controles.jsonl')}):
            engine=SynchroniseurSheets(self.cache,'fake-partiel',session=session)
            first=engine.synchroniser_tables({'Historique chevaux':partial},scope='TEST')
            full=doc(self.now);inc.ecrire(self.cache/'historiques/123456/historique_geny.json',full)
            second=engine.synchroniser_tables({'Historique chevaux':source_rows(self.cache)['Historique chevaux']},scope='TEST')
        self.assertEqual(first['Historique chevaux']['lignes_ajoutees'],1)
        self.assertEqual(second['Historique chevaux']['lignes_ajoutees'],0)
        self.assertEqual(len(session.tables['Historique chevaux']),2)
        row=dict(zip(headers,session.tables['Historique chevaux'][1]))
        self.assertEqual(row['statut_verification'],'EXTRACTION_GENY')

    def test_ml_distingue_partiel_et_complet_sans_modifier_les_instantanes(self):
        from pmu_geny.ml_v19 import pmu_rows
        self.assertTrue(conserver(self.cache,self.horse,self.report))
        course={'date':'2026-11-17','code':'R3C1','depart':'2026-11-17T14:12:00+01:00',
                'hippodrome':'VINCENNES','distance_m':2700,'discipline':'TROT_ATTELE'}
        raw={'participants':[{'numPmu':i,'nom':name,'nonPartant':False} for i,name in enumerate(('Test','Autre','Troisième'),1)]}
        frozen=self.cache/'ml/instantanes/2026-11-16_R1C1.json';inc.ecrire(frozen,{'preuve':'immutable'})
        before=frozen.read_bytes()
        status,rows,detail=pmu_rows(self.cache,course,raw,self.now)
        self.assertEqual(status,'OK');self.assertEqual(detail['historiques_complets_reutilises'],0)
        self.assertEqual(detail['historiques_partiels_reutilises'],1)
        self.assertFalse(rows[0]['historique_complet']);self.assertTrue(rows[0]['historique_ok'])
        self.assertEqual(frozen.read_bytes(),before)

    def test_cycle_compte_publie_et_reprend_le_partiel_sans_recollecte(self):
        engagement=self.now.date().isoformat()+'_R1C1'
        inc.ecrire(self.cache/'partants_actuels'/f'{engagement}.json',{'chevaux':{'1':{'nom':'Test'}}})
        inc.ecrire(self.cache/'orchestration/correspondances_geny.json',{engagement:'GENY-1698061'})
        snapshots=[]
        def checkpoint(cache):snapshots.append(inc.lire(cache/inc.QUEUE))
        with patch.object(inc.time,'sleep'):
            state=inc.run(self.cache,collect=lambda h,p:self.report,checkpoint=checkpoint,
                          sync=Mock(side_effect=RuntimeError('Sheets indisponible')))
            self.assertEqual(state['bilan']['captures_partielles'],1)
            self.assertEqual(state['bilan']['captures_validees'],0)
            self.assertEqual(state['bilan']['collectes_rejetees'],0)
            self.assertTrue(any(s['chevaux'].get('123456',{}).get('sync')=='A_FAIRE' for s in snapshots))
            self.assertEqual(state['statut'],'PARTIEL_REPRENABLE')
            state['chevaux']['123456']['prochaine_sync_utc']=(self.now-timedelta(minutes=1)).isoformat()
            inc.ecrire(self.cache/inc.QUEUE,state)
            collect=Mock(side_effect=AssertionError('aucune recollecte'))
            resumed=inc.run(self.cache,collect=collect,sync=lambda h:{})
        collect.assert_not_called();self.assertEqual(resumed['chevaux']['123456']['sync'],'OK')

    def test_partiel_apres_une_course_officielle_ne_requiert_pas_un_fichier_complet(self):
        day=self.now.date().isoformat();engagement=day+'_R1C1'
        inc.ecrire(self.cache/'partants_actuels'/f'{engagement}.json',{'chevaux':{'1':{'nom':'Test'}}})
        inc.ecrire(self.cache/'orchestration/correspondances_geny.json',{engagement:'GENY-1698061'})
        inc.ecrire(self.cache/'orchestration'/f'{day}.json',{'courses':{'R1C1':{
            'depart':(self.now-timedelta(hours=1)).isoformat()}}})
        inc.ecrire(self.cache/'arrivees'/f'{engagement}.json',{'arrivee':[{'numero':1,'rang':3}]})
        with patch.object(inc.time,'sleep'):
            result=inc.run(self.cache,collect=lambda h,p:self.report,sync=lambda h:{})
        horse=result['chevaux']['123456']
        self.assertEqual(horse['collecte'],'PARTIEL_HISTORIQUE')
        self.assertNotIn('dernier_echec_collecte',horse)
        self.assertEqual(result['bilan']['captures_partielles'],1)
        self.assertEqual(horse['sync'],'OK')
