"""Priorité nocturne aux historiques manquants des partants déjà recensés."""
import copy
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pmu_geny import historiques_incrementaux as inc
from pmu_geny import rattrapage_historiques as back


class NuitTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,15,1,tzinfo=ZoneInfo('Europe/Paris'))
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.cache=Path(self.tmp.name)

    def horse(self,engagement,*,missing=True,known=False):
        return {'nom':'Test','engagement':engagement,'numero':'1','vu_utc':self.now.isoformat(),
            'sync':'SANS_MODIFICATION','collecte':'A_REPRENDRE',
            'motif_actualisation':'HISTORIQUE_ABSENT_OU_NON_DATE' if missing else 'VERIFICATION_PERIODIQUE',
            **({'geny':{'id':'123456','url_geny':'https://www.geny.com/cheval/123456'}} if known else
               {'course_url':'https://www.geny.com/course/1698061/partants-pronostics'})}

    def test_nuit_paris_et_changements_d_heure(self):
        for day in ('2026-03-29','2026-10-25','2026-11-15'):
            for hour,minute,expected in [(6,59,True),(7,0,False),(20,59,False),(21,0,True)]:
                local=datetime.fromisoformat(f'{day}T{hour:02}:{minute:02}').replace(tzinfo=ZoneInfo('Europe/Paris'))
                self.assertEqual(inc.nuit_collecte(local.astimezone(timezone.utc)),expected)

    def test_production_nuit_partant_sans_historique_avant_actualisation(self):
        horses={'ancien':self.horse('2026-11-14_R1C1'),
                'actualiser':self.horse('2026-11-15_R1C1',missing=False,known=True),
                'manquant':self.horse('2026-11-15_R1C9')}
        state={'passage_utc':self.now.isoformat(),'chevaux':horses}
        self.assertEqual(inc.prochaine_tache(state,self.now,{}),('manquant','COLLECTE'))
        self.assertEqual(inc.prochaine_tache(state,self.now,{('COLLECTE','manquant'):1}),('ancien','COLLECTE'))

    def test_carriere_manquante_avant_ferrures_meme_en_journee(self):
        for hour in (1,10):
            now=self.now.replace(hour=hour)
            missing=self.horse('2026-11-14_R1C9')
            enrichment=self.horse('2026-11-15_R1C1',known=True)
            enrichment['motif_actualisation']='FERRURES_HISTORIQUES_A_COMPLETER'
            for h in (missing,enrichment):h['vu_utc']=now.isoformat()
            state={'passage_utc':now.isoformat(),'chevaux':{'ferrures':enrichment,'carriere':missing}}
            with self.subTest(hour=hour):
                self.assertEqual(inc.prochaine_tache(state,now,{}),('carriere','COLLECTE'))

    def test_selection_de_jour_conserve_priorite_aux_engagements_futurs(self):
        now=self.now.replace(hour=10)
        horses={'ancien':self.horse('2026-11-14_R1C1'),
                'actualiser':self.horse('2026-11-15_R1C1',missing=False,known=True),
                'manquant':self.horse('2026-11-15_R1C9')}
        for h in horses.values():h['vu_utc']=now.isoformat()
        state={'passage_utc':now.isoformat(),'chevaux':horses}
        self.assertEqual(inc.prochaine_tache(state,now,{}),('actualiser','COLLECTE'))

    def test_rattrapage_nuit_partant_avant_ancien_lien_deja_prouve(self):
        state={'chevaux':{'ancien':self.horse('2026-11-10_R1C1',known=True),
                          'partant':self.horse('2026-11-15_R1C1')}}
        self.assertEqual(back.prochaine_tache(state,self.now,{}),('partant','COLLECTE'))
        self.assertEqual(back.prochaine_tache(state,self.now.replace(hour=10),{}),('ancien','COLLECTE'))

    def test_nuit_j1_avant_j0_et_anciens_dans_les_deux_collecteurs(self):
        now=datetime(2026,11,15,22,tzinfo=ZoneInfo('Europe/Paris'))
        demain=self.horse('2026-11-16_R1C1')
        jour=self.horse('2026-11-15_R1C1',known=True)
        ancien=self.horse('2026-11-10_R1C1',known=True)
        ancien['priorite_identite_corrigee']=True
        for h in (demain,jour,ancien):h['vu_utc']=now.isoformat()
        state={'passage_utc':now.isoformat(),'chevaux':{
            'ancien_corrige':ancien,'jour':jour,'demain':demain}}
        self.assertEqual(inc.prochaine_tache(copy.deepcopy(state),now,{}),('demain','COLLECTE'))
        self.assertEqual(back.prochaine_tache(copy.deepcopy(state),now,{}),('demain','COLLECTE'))
        self.assertEqual(back.prochaine_tache(copy.deepcopy(state),now,{('COLLECTE','demain'):1})[0],'jour')

    def test_nuit_priorite_j1_ne_contourne_pas_cooldown(self):
        now=datetime(2026,11,15,22,tzinfo=ZoneInfo('Europe/Paris'))
        state={'passage_utc':now.isoformat(),'chevaux':{
            'demain':self.horse('2026-11-16_R1C1')},
            'prochain_acces_geny_utc':(now+timedelta(minutes=30)).isoformat()}
        self.assertEqual(inc.prochaine_tache(state,now,{}),(None,'COOLDOWN'))
        self.assertEqual(back.prochaine_tache(state,now,{}),(None,'COOLDOWN'))

    def test_nouvel_engagement_d_une_cible_ancienne_est_prioritaire_sans_changer_le_lot(self):
        horse=self.horse('2020-01-01_R1C1',known=True)
        horse['engagement_prioritaire']='2026-11-15_R1C2'
        self.assertEqual(inc.priorite_engagement(horse,self.now,manquant=True),1)
        # Un engagement du jour reste prioritaire sur les anciens, mais J+1 passe avant lui.
        self.assertEqual(horse['engagement'],'2020-01-01_R1C1')

    def test_pause_403_et_delais_de_reprise_restent_prioritaires(self):
        horse=self.horse('2026-11-15_R1C1');horse['prochain_essai_utc']=(self.now+timedelta(hours=1)).isoformat()
        state={'passage_utc':self.now.isoformat(),'chevaux':{'partant':horse}}
        self.assertIsNone(inc.prochaine_tache(state,self.now,{})[0])
        self.assertIsNone(back.prochaine_tache(state,self.now,{})[0])
        horse.pop('prochain_essai_utc');state['prochain_acces_geny_utc']=(self.now+timedelta(minutes=30)).isoformat()
        self.assertEqual(inc.prochaine_tache(state,self.now,{}),(None,'COOLDOWN'))
        self.assertEqual(back.prochaine_tache(state,self.now,{}),(None,'COOLDOWN'))

    def test_sync_echouee_se_reprend_sans_nouvelle_collecte_meme_la_nuit(self):
        state={'passage_utc':self.now.isoformat(),'chevaux':{'partant':self.horse('2026-11-15_R1C1'),
               'sauvegarde':{'sync':'A_FAIRE'}},'prochain_acces_geny_utc':(self.now+timedelta(minutes=30)).isoformat()}
        self.assertEqual(inc.prochaine_tache(copy.deepcopy(state),self.now,{}),('sauvegarde','SYNC'))
        self.assertEqual(back.prochaine_tache(copy.deepcopy(state),self.now,{}),('sauvegarde','SYNC'))

    def seed_index(self,ambiguous=False):
        day='2026-11-15'
        inc.ecrire(self.cache/'etat_persistant.json',{'version':1,'chevaux':{}})
        inc.ecrire(self.cache/'partants_actuels'/f'{day}_R1C1.json',{'chevaux':{'1':{'nom':'Test'}}})
        inc.ecrire(self.cache/'orchestration'/f'{day}.json',{'courses':{
            'R1C1':{'nom':'PRIX TEST','hippodrome':'VINCENNES'}}})
        candidate={'geny_id':'1698061','date':day,'slug':'vincennes prix test',
            'url':'https://www.geny.com/course/1698061-prix-test','r':1,'c':1,'code_rc_verifie':True}
        candidates=[candidate,{**candidate,'geny_id':'1698062'}] if ambiguous else [candidate]
        inc.ecrire(self.cache/'sources_geny'/f'index_{day}.json',{'statut':'OK','courses':candidates})

    def test_index_sauvegarde_resout_le_lien_du_partant_sans_requete_geny(self):
        self.seed_index()
        with patch('requests.get',side_effect=AssertionError('Aucun nouvel acces reseau')):
            state=inc.alimenter(self.cache,self.now)
        horse=next(iter(state['chevaux'].values()))
        self.assertEqual(horse['course_url'],'https://www.geny.com/course/1698061/partants-pronostics')
        state['passage_utc']=self.now.isoformat()
        self.assertEqual(inc.prochaine_tache(state,self.now,{})[1],'COLLECTE')

    def test_index_course_ambigu_declenche_une_recherche_par_nom(self):
        self.seed_index(ambiguous=True);state=inc.alimenter(self.cache,self.now)
        horse=next(iter(state['chevaux'].values()));self.assertNotIn('course_url',horse)
        state['passage_utc']=self.now.isoformat()
        self.assertTrue(horse['recherche_geny_par_nom'])
        self.assertEqual(inc.prochaine_tache(state,self.now,{})[1],'COLLECTE')


if __name__=='__main__':unittest.main()
