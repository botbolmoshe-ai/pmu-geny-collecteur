import unittest
from datetime import datetime,timedelta,timezone
from scripts.boucle_historiques import choisir
from unittest.mock import patch
import subprocess

NOW=datetime(2026,11,12,22,tzinfo=timezone.utc)
def horse(collecte='A_FAIRE',sync='A_FAIRE',tentatives=0):
    return {'collecte':collecte,'sync':sync,'tentatives':tentatives,'sync_tentatives':0}

class BoucleTests(unittest.TestCase):
    def test_git_checkpoint_is_retried_after_transient_rejection(self):
        from scripts.boucle_historiques import pousser_checkpoint
        calls=[]
        def fake_git(*args):
            calls.append(args)
            if args[0]=='push' and sum(c[0]=='push' for c in calls)==1:
                raise subprocess.CalledProcessError(1,['git',*args])
        with patch('scripts.boucle_historiques.git',side_effect=fake_git),patch('scripts.boucle_historiques.time.sleep'):
            pousser_checkpoint()
        self.assertEqual(sum(c[0]=='push' for c in calls),2)
        self.assertTrue(any(c[0]=='merge-base' for c in calls))
    def test_success_already_synced_is_never_collected_again(self):
        state={'chevaux':{'done':horse('COMPLET','OK'),'next':horse()}}
        self.assertEqual(choisir(state,NOW),('next','COLLECTE'))
    def test_sheet_retry_does_not_repeat_geny_request(self):
        state={'chevaux':{'saved':horse('COMPLET','A_REPRENDRE'),'next':horse()}}
        self.assertEqual(choisir(state,NOW),('saved','SYNC'))
    def test_cooldown_applies_to_every_horse(self):
        state={'chevaux':{'a':horse(),'b':horse()},'prochain_acces_geny_utc':(NOW+timedelta(minutes=30)).isoformat()}
        self.assertEqual(choisir(state,NOW),(None,'COOLDOWN'))
        self.assertEqual(choisir(state,NOW+timedelta(minutes=31)),('a','COLLECTE'))
    def test_sync_continues_during_source_cooldown(self):
        state={'chevaux':{'saved':horse('COMPLET')},'prochain_acces_geny_utc':(NOW+timedelta(minutes=30)).isoformat()}
        self.assertEqual(choisir(state,NOW),('saved','SYNC'))
    def test_attempt_limit_and_explicit_resume(self):
        h=horse(tentatives=2);state={'chevaux':{'a':h}}
        self.assertEqual(choisir(state,NOW),(None,'TERMINE'))
        h['tentatives_execution']=0
        self.assertEqual(choisir(state,NOW),('a','COLLECTE'))
    def test_complete_file_never_goes_back_to_source(self):
        h=horse('COMPLET','A_REPRENDRE');h['sync_tentatives']=3
        self.assertEqual(choisir({'chevaux':{'a':h}},NOW),(None,'TERMINE'))

if __name__=='__main__':unittest.main()
