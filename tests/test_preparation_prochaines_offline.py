import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from pmu_geny import historiques_incrementaux as inc
from pmu_geny.preparation_prochaines import appliquer,autoriser_fond,decision_fond

class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name);self.now=datetime(2026,11,16,12,tzinfo=timezone.utc)
        for day in ('2026-11-16','2026-11-17'):
            inc.ecrire(self.cache/'sources_pmu'/f'programme_{day}.json',
                       {'date_controle_utc':self.now.isoformat(),'programme':[]})
        inc.ecrire(self.cache/'etat_persistant.json',{'chevaux':{}})

    def course(self,code,depart,nom='Future'):
        day=depart[:10];p=self.cache/'sources_pmu'/f'programme_{day}.json'
        s=inc.lire(p);s['programme'].append({'code':code,'depart':depart});inc.ecrire(p,s)
        engagement=day+'_'+code
        mappings=inc.lire(self.cache/'orchestration/correspondances_geny.json')
        mappings[engagement]='GENY-1698706'
        inc.ecrire(self.cache/'orchestration/correspondances_geny.json',mappings)
        inc.ecrire(self.cache/'partants_actuels'/f'{engagement}.json',{'capture_utc':self.now.isoformat(),'chevaux':{'1':{
            'nom':nom,'statut_np':'PARTANT','age_ans':5,'sexe':'Femelle','gains_euros':1000,'ferrure':'D4'}}})
        inc.ecrire(self.cache/'pronostics'/f'{engagement}_direct.json',
                   {'calcul_utc':self.now.isoformat(),'top3':[{'numero':n} for n in (1,2,3)]})
        return engagement,engagement+'_1'

    def state(self,engagement,key):
        h={'nom':'Future','engagement':engagement,'numero':'1','vu_utc':self.now.isoformat(),
           'course_url':'https://www.geny.com/course/1698706/partants-pronostics',
           'motif_actualisation':'HISTORIQUE_ABSENT_OU_NON_DATE'}
        return {'version':1,'passage_utc':self.now.isoformat(),'chevaux':{key:h}}

    def test_cheval_encore_a_courir_avant_tous_les_anciens(self):
        e,k=self.course('R1C8','2026-11-16T18:00:00+01:00');s=self.state(e,k)
        s['chevaux']['ancien']={**s['chevaux'][k],'engagement':'2026-11-16_R1C1'}
        appliquer(self.cache,s,self.now)
        self.assertEqual(inc.prochaine_tache(s,self.now,{}),(k,'COLLECTE'))
        self.assertEqual(inc.prochaine_tache(s,self.now,{('COLLECTE',k):1}),(None,'TERMINE'))
        self.assertIsNotNone(autoriser_fond(self.cache,self.now))

    def test_nuit_jour_seulement_dans_l_ordre_des_departs_sans_top3(self):
        self.now = self.now.replace(hour=1)
        for day in ('2026-11-16', '2026-11-17'):
            inc.ecrire(self.cache / 'sources_pmu' / f'programme_{day}.json',
                       {'date_controle_utc': self.now.isoformat(), 'programme': []})
        early, early_key = self.course('R1C2', '2026-11-16T09:00:00+01:00')
        late, late_key = self.course('R1C1', '2026-11-16T18:00:00+01:00', nom='Plus tard')
        _, next_key = self.course('R3C1', '2026-11-17T09:00:00+01:00', nom='Demain')
        for engagement in (early, late):
            (self.cache / 'pronostics' / f'{engagement}_direct.json').unlink()
        state = inc.alimenter(self.cache, self.now, sauvegarder=False)
        state['passage_utc'] = self.now.isoformat()
        appliquer(self.cache, state, self.now, nocturne=True)
        self.assertEqual(inc.prochaine_tache(state, self.now, {}), (early_key, 'COLLECTE'))
        attempts = {('COLLECTE', early_key): 1}
        self.assertEqual(inc.prochaine_tache(state, self.now, attempts), (late_key, 'COLLECTE'))
        self.assertIsNone(state['chevaux'][next_key]['depart_a_venir_utc'])
        self.assertEqual(decision_fond(self.cache, self.now, nocturne=True)['motif'],
                         'CRENEAU_NOCTURNE_APRES_PREPARATION')
        self.assertEqual(decision_fond(self.cache, self.now.replace(hour=6), nocturne=True)['motif'],
                         'PARTANT_PRIORITAIRE_DISPONIBLE')
        for key in (early_key, late_key):
            state['chevaux'][key]['prochain_essai_utc'] = (self.now + timedelta(hours=1)).isoformat()
        inc.ecrire(self.cache / inc.QUEUE, state)
        self.assertTrue(decision_fond(self.cache, self.now, nocturne=True)['autorise'])

    def test_course_deja_partie_exclue_meme_si_jour_identique(self):
        e,k=self.course('R1C1','2026-11-16T12:00:00+01:00');s=self.state(e,k)
        appliquer(self.cache,s,self.now)
        self.assertEqual(inc.prochaine_tache(s,self.now,{}),(None,'TERMINE'))

    def test_prochain_engagement_le_plus_proche_pour_un_id_unique(self):
        a,k=self.course('R1C8','2026-11-16T18:00:00+01:00')
        b,_=self.course('R3C1','2026-11-17T14:00:00+01:00')
        s=self.state(b,'123456');s['chevaux']['123456']['id']='123456'
        inc.ecrire(self.cache/'etat_persistant.json',{'chevaux':{'123456':{'nom':'Future'}}})
        appliquer(self.cache,s,self.now)
        self.assertEqual(s['chevaux']['123456']['engagement'],a)

    def test_fond_utilise_attente_locale_puis_cede_des_reessai_possible(self):
        e,k=self.course('R1C8','2026-11-16T18:00:00+01:00');s=self.state(e,k)
        s['chevaux'][k]['prochain_essai_utc']=(self.now+timedelta(hours=6)).isoformat()
        inc.ecrire(self.cache/inc.QUEUE,s)
        decision=decision_fond(self.cache,self.now)
        self.assertTrue(decision['autorise'])
        self.assertFalse(decision['preparation_complete'])
        self.assertEqual(decision['motif'],'CRENEAU_LIBRE_ENTRE_PARTANTS')
        s['chevaux'][k]['prochain_essai_utc']=self.now.isoformat()
        inc.ecrire(self.cache/inc.QUEUE,s)
        self.assertEqual(autoriser_fond(self.cache,self.now),'PARTANT_PRIORITAIRE_DISPONIBLE')

    def test_creneau_borne_respecte_le_jalon_et_la_cadence(self):
        self.course('R1C8', '2026-11-16T18:00:00+01:00')
        inc.ecrire(self.cache/'orchestration/production_etat.json',
                   {'dernier_global_publie_utc':self.now.isoformat()})
        decision = decision_fond(self.cache, self.now, reserve=True)
        self.assertTrue(decision['creneau_reserve'])
        inc.ecrire(self.cache/'rattrapage_historiques/etat.json',
                   {'dernier_creneau_reserve_utc':self.now.isoformat()})
        self.assertEqual(decision_fond(self.cache, self.now, reserve=True)['motif'],
                         'PARTANT_PRIORITAIRE_DISPONIBLE')
        inc.ecrire(self.cache/'rattrapage_historiques/etat.json', {})
        self.assertFalse(decision_fond(self.cache, self.now+timedelta(minutes=55), reserve=True)['autorise'])

    def attente(self,minutes=360):
        e,k=self.course('R1C8','2026-11-16T18:00:00+01:00')
        s=self.state(e,k)
        s['chevaux'][k]['prochain_essai_utc']=(self.now+timedelta(minutes=minutes)).isoformat()
        inc.ecrire(self.cache/inc.QUEUE,s)
        return e,k,s

    def test_attente_jour_ne_masque_pas_un_partant_disponible_demain(self):
        self.attente()
        e,k=self.course('R3C1','2026-11-17T14:00:00+01:00',nom='Demain')
        d=decision_fond(self.cache,self.now)
        self.assertFalse(d['autorise'])
        self.assertEqual(d['tache_prioritaire'],{'cle':k,'action':'COLLECTE'})

    def test_reprise_prioritaire_imminente_garde_le_creneau(self):
        e,k,s=self.attente(minutes=5)
        self.assertEqual(autoriser_fond(self.cache,self.now),'REPRISE_PARTANT_PRIORITAIRE_IMMINENTE')
        s['chevaux'][k]['prochain_essai_utc']=(self.now+timedelta(minutes=6)).isoformat()
        inc.ecrire(self.cache/inc.QUEUE,s)
        self.assertIsNone(autoriser_fond(self.cache,self.now))

    def test_pause_globale_respectee_depuis_journal_et_les_deux_files(self):
        e,k,s=self.attente()
        for code in ('403','429'):
            with self.subTest(code=code):
                inc.ecrire(self.cache/'etat_persistant.json',{'chevaux':{},
                    'dernier_blocage_geny':{'utc':(self.now-timedelta(minutes=5)).isoformat(),'code':code}})
                self.assertEqual(autoriser_fond(self.cache,self.now),'COOLDOWN_GENY_GLOBAL')
        inc.ecrire(self.cache/'etat_persistant.json',{'chevaux':{},
            'dernier_blocage_geny':{'utc':(self.now-timedelta(minutes=31)).isoformat(),'code':'403'}})
        self.assertIsNone(autoriser_fond(self.cache,self.now))
        inc.ecrire(self.cache/'etat_persistant.json',{'chevaux':{}})
        for queue in (inc.QUEUE,Path('rattrapage_historiques/etat.json')):
            with self.subTest(queue=str(queue)):
                data=inc.lire(self.cache/queue,s)
                data['prochain_acces_geny_utc']=(self.now+timedelta(minutes=1)).isoformat()
                inc.ecrire(self.cache/queue,data)
                self.assertEqual(autoriser_fond(self.cache,self.now),'COOLDOWN_GENY_GLOBAL')
                data.pop('prochain_acces_geny_utc');inc.ecrire(self.cache/queue,data)
        self.assertIsNone(autoriser_fond(self.cache,self.now))

    def test_publication_en_attente_bloque_meme_si_delai_sync_non_ecoule(self):
        e,k,s=self.attente()
        s['chevaux'][k].update(sync='A_FAIRE',prochaine_sync_utc=(self.now+timedelta(minutes=10)).isoformat())
        inc.ecrire(self.cache/inc.QUEUE,s)
        self.assertIsNotNone(autoriser_fond(self.cache,self.now))

    def test_attente_locale_ne_masque_pas_profil_perime_ou_prevision_absente(self):
        e,k,s=self.attente()
        path=self.cache/'partants_actuels'/f'{e}.json';profile=inc.lire(path)
        old={**profile,'capture_utc':(self.now-timedelta(hours=7)).isoformat()}
        inc.ecrire(path,old)
        self.assertEqual(autoriser_fond(self.cache,self.now),'PREPARATION_PROCHAINES_COURSES_INCOMPLETE')
        inc.ecrire(path,profile)
        (self.cache/'pronostics'/f'{e}_direct.json').unlink()
        self.assertEqual(autoriser_fond(self.cache,self.now),'PREPARATION_PROCHAINES_COURSES_INCOMPLETE')

    def test_observation_du_creneau_ne_modifie_aucun_fichier_source(self):
        self.attente()
        before={str(p):p.read_bytes() for p in self.cache.rglob('*') if p.is_file()}
        self.assertIsNone(autoriser_fond(self.cache,self.now))
        after={str(p):p.read_bytes() for p in self.cache.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_absence_prevision_ne_bloque_pas_enrichissement_des_partants_prepares(self):
        e,k=self.course('R1C8','2026-11-16T18:00:00+01:00');s=self.state(e,k)
        (self.cache/'pronostics'/f'{e}_direct.json').unlink()
        appliquer(self.cache,s,self.now)
        self.assertEqual(inc.prochaine_tache(s,self.now,{}),(k,'COLLECTE'))
        self.assertFalse(s['preparation_prochaines_courses']['pret'])
        self.assertIn('PREVISION_PRELIMINAIRE_ABSENTE',
                      [b['motif'] for b in s['preparation_prochaines_courses']['blocages']])

    def test_collecte_possible_si_ferrure_absente_avec_identite_pmu(self):
        e,k=self.course('R1C8','2026-11-16T18:00:00+01:00');s=self.state(e,k)
        path=self.cache/'partants_actuels'/f'{e}.json'
        data=inc.lire(path);data['chevaux']['1']['ferrure']='';inc.ecrire(path,data)
        appliquer(self.cache,s,self.now)
        self.assertEqual(inc.prochaine_tache(s,self.now,{}),(k,'COLLECTE'))
        self.assertFalse(s['preparation_prochaines_courses']['pret'])

    def test_collecte_interdite_si_profil_pmu_perime(self):
        e,k=self.course('R1C8','2026-11-16T18:00:00+01:00');s=self.state(e,k)
        path=self.cache/'partants_actuels'/f'{e}.json'
        data=inc.lire(path);data['capture_utc']=(self.now-timedelta(hours=7)).isoformat();inc.ecrire(path,data)
        appliquer(self.cache,s,self.now)
        self.assertEqual(inc.prochaine_tache(s,self.now,{}),(None,'TERMINE'))

    def test_fond_autorise_quand_preparation_et_historique_complets(self):
        e,k=self.course('R1C8','2026-11-16T18:00:00+01:00');s=self.state(e,'123456')
        s['chevaux']['123456']['id']='123456'
        inc.ecrire(self.cache/'etat_persistant.json',{'chevaux':{'123456':{'nom':'Future'}}})
        from test_v26_incremental_offline import doc
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json',doc(self.now))
        inc.ecrire(self.cache/inc.QUEUE,s)
        self.assertIsNone(autoriser_fond(self.cache,self.now))
        (self.cache/'sources_pmu/programme_2026-11-17.json').write_text('{}')
        self.assertIsNotNone(autoriser_fond(self.cache,self.now))

    def test_fond_differe_avant_toute_lecture_sheets(self):
        from unittest.mock import patch
        from pmu_geny import rattrapage_historiques as back
        import os
        inc.ecrire(self.cache/back.QUEUE,{'chevaux':{'old':{'nom':'Ancien'}}})
        with patch('sys.argv',['rattrapage','--cache',str(self.cache),'--publier']), \
             patch.dict(os.environ,{'GOOGLE_SHEETS_ID':'test','GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON':'{}'}), \
             patch.object(back,'priorite_production',return_value=None), \
             patch('pmu_geny.echeances_production.besoin_pmu',return_value=None), \
             patch('pmu_geny.preparation_prochaines.autoriser_fond',return_value='PREPARATION_INCOMPLETE'), \
             patch('pmu_geny.moteur_sheets.SynchroniseurSheets') as engine, \
             patch.object(inc,'checkpoint_distant') as checkpoint:
            back.main()
        engine.assert_not_called();checkpoint.assert_called_once()
        self.assertEqual(inc.lire(self.cache/back.QUEUE)['motif_fin_passage'],'PREPARATION_INCOMPLETE')

    def test_publication_locale_autorisee_quand_geny_est_en_pause(self):
        from unittest.mock import patch
        from pmu_geny import rattrapage_historiques as back
        import os

        state = {'chevaux': {'old': {'nom': 'Ancien', 'sync': 'A_FAIRE'}}}
        inc.ecrire(self.cache / back.QUEUE, state)
        inc.ecrire(self.cache / back.INVENTAIRE, {'instantane': True})
        with patch('sys.argv', ['rattrapage', '--cache', str(self.cache), '--publier']), \
             patch.dict(os.environ, {'GOOGLE_SHEETS_ID': 'test', 'GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON': '{}'}), \
             patch.object(back, 'priorite_production', return_value=None), \
             patch.object(back, 'preparer', return_value=state), \
             patch('pmu_geny.echeances_production.besoin_pmu', return_value=None), \
             patch('pmu_geny.preparation_prochaines.autoriser_fond', return_value='COOLDOWN_GENY_GLOBAL'), \
             patch.object(inc, 'checkpoint_distant'), \
             patch.object(inc, 'run', return_value=state) as run:
            back.main()
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs['max_chevaux'], 0)
        self.assertTrue(run.call_args.kwargs['publier'])
        self.assertIn('stop_requested', run.call_args.kwargs)


    def test_alerte_consecutive_ignore_priorite_pmu_pause_et_double_creneau(self):
        from datetime import timedelta
        from pmu_geny.rattrapage_historiques import suivre_creneau_nocturne

        def observe(previous, minutes, *, reason='BUDGET_TEMPS_ATTEINT', pause=None, progress=False):
            return suivre_creneau_nocturne(previous, self.now + timedelta(minutes=minutes),
                                           reason=reason, pause=pause, progress=progress)

        first = observe({}, 0)
        self.assertEqual(observe(first, 1)['consecutifs_sans_progression'], 1)
        second = observe(first, 30)
        self.assertEqual(observe(second, 60)['consecutifs_sans_progression'], 3)
        self.assertEqual(observe(second, 60, reason='ECHEANCE_PMU_PRIORITAIRE')['consecutifs_sans_progression'], 0)
        self.assertEqual(observe(second, 60, pause=self.now + timedelta(hours=2))['consecutifs_sans_progression'], 0)
        self.assertEqual(observe(second, 90)['consecutifs_sans_progression'], 1)
        progress = observe(second, 60, progress=True)
        self.assertEqual(observe(progress, 61)['consecutifs_sans_progression'], 0)
