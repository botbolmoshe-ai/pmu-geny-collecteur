import unittest
from datetime import datetime,timedelta,timezone
from scripts.boucle_historiques import choisir

NOW=datetime(2026,11,12,22,tzinfo=timezone.utc)
def horse(collecte='A_FAIRE',sync='A_FAIRE',tentatives=0):
    return {'collecte':collecte,'sync':sync,'tentatives':tentatives,'sync_tentatives':0}

class BoucleTests(unittest.TestCase):
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
