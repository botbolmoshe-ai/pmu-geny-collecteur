import tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from pmu_geny import historiques_incrementaux as inc
from pmu_geny.preparation_prochaines import appliquer,autoriser_fond

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
        inc.ecrire(self.cache/'partants_actuels'/f'{engagement}.json',{'capture_utc':self.now.isoformat(),'chevaux':{'1':{
            'nom':nom,'statut_np':'PARTANT','age_ans':5,'sexe':'Femelle','gains_euros':1000,'ferrure':'D4'}}})
        inc.ecrire(self.cache/'pronostics'/f'{engagement}_direct.json',
                   {'calcul_utc':self.now.isoformat(),'top3':[{'numero':n} for n in (1,2,3)]})
        return engagement,engagement+'_1'

    def state(self,engagement,key):
        h={'nom':'Future','engagement':engagement,'numero':'1','vu_utc':self.now.isoformat(),
           'course_url':'https://www.geny.com/course/1698706/partants-pronostics',
           'motif_actualisation':'HISTORIQUE_ABSENT_OU_NON_DATE'}
        return {'passage_utc':self.now.isoformat(),'chevaux':{key:h}}

    def test_cheval_encore_a_courir_avant_tous_les_anciens(self):
        e,k=self.course('R1C8','2026-11-16T18:00:00+01:00');s=self.state(e,k)
        s['chevaux']['ancien']={**s['chevaux'][k],'engagement':'2026-11-16_R1C1'}
        appliquer(self.cache,s,self.now)
        self.assertEqual(inc.prochaine_tache(s,self.now,{}),(k,'COLLECTE'))
        self.assertEqual(inc.prochaine_tache(s,self.now,{('COLLECTE',k):1}),(None,'TERMINE'))
        self.assertIsNotNone(autoriser_fond(self.cache,self.now))

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

    def test_fond_reste_bloque_pendant_un_delai_de_reessai(self):
        e,k=self.course('R1C8','2026-11-16T18:00:00+01:00');s=self.state(e,k)
        s['chevaux'][k]['prochain_essai_utc']=(self.now+timedelta(hours=6)).isoformat()
        inc.ecrire(self.cache/inc.QUEUE,s)
        self.assertEqual(autoriser_fond(self.cache,self.now),'PREPARATION_PROCHAINES_COURSES_INCOMPLETE')

    def test_absence_prevision_ne_bloque_pas_enrichissement_des_partants_prepares(self):
        e,k=self.course('R1C8','2026-11-16T18:00:00+01:00');s=self.state(e,k)
        (self.cache/'pronostics'/f'{e}_direct.json').unlink()
        appliquer(self.cache,s,self.now)
        self.assertEqual(inc.prochaine_tache(s,self.now,{}),(k,'COLLECTE'))
        self.assertFalse(s['preparation_prochaines_courses']['pret'])

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
             patch('pmu_geny.preparation_prochaines.autoriser_fond',return_value='PREPARATION_INCOMPLETE'), \
             patch('pmu_geny.moteur_sheets.SynchroniseurSheets') as engine, \
             patch.object(inc,'checkpoint_distant') as checkpoint:
            back.main()
        engine.assert_not_called();checkpoint.assert_called_once()
        self.assertEqual(inc.lire(self.cache/back.QUEUE)['motif_fin_passage'],'PREPARATION_INCOMPLETE')
