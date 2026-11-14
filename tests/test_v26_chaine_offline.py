"""Vérifications d'intégration des checkpoints Git et des écritures Sheets."""
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote
from unittest.mock import patch

from pmu_geny import historiques_incrementaux as inc
from scripts.synchroniser_un_historique import synchroniser


class Response:
    status_code=200
    def __init__(self, data):
        self.data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self.data


class SheetsSession:
    def __init__(self):
        self.tables = {
            'Historique chevaux': [['cle_performance', 'identifiant_cheval', 'cheval', 'classement']],
            'Courses & Prévisions': [['course_key', 'numero', 'cheval', 'historique_statut',
                                      'historique_nb_courses_datees', 'historique_maj_utc', 'baseline_top3'],
                                     ['course1', '1', 'Test', '', '', '', 'OUI']],
            'Data Quality & KPI': [['A', 'B', 'C', 'D', 'E'], ['groupe', 'Indicateur test', 0, '', '=NBVAL(A:A)']]}
        self.writes = []
    def get(self, url, **kwargs):
        if '/values/' not in url:
            return Response({'sheets': [{'properties': {'title': tab, 'sheetId': i,
                        'gridProperties': {'columnCount': len(rows[0]), 'rowCount': 100}}}
                        for i, (tab, rows) in enumerate(self.tables.items())]})
        tab, bounds = unquote(url.split('/values/')[1]).split('!')
        tab=tab.strip("'")
        match=re.fullmatch(r'([A-Z]+)(\d+):([A-Z]+)(\d+)',bounds)
        if not match:return Response({'values':[row[:] for row in self.tables[tab]]})
        def column(label):
            result=0
            for ch in label:result=result*26+ord(ch)-64
            return result
        first,last=column(match[1])-1,column(match[3])
        rows=[row[first:last] for row in self.tables[tab][int(match[2])-1:int(match[4])]]
        return Response({'values':rows})
    def post(self, url, **kwargs):
        data = kwargs['json']
        self.writes.append((url, data))
        if url.endswith(':append'):
            tab = unquote(url.split('/values/')[1]).split('!')[0].strip("'")
            self.tables[tab].extend(data['values'])
        else:
            for entry in data['data']:
                tab, cell = entry['range'].split('!')
                match = re.match(r'([A-Z]+)(\d+)', cell)
                col = 0
                for ch in match[1]:
                    col = col*26+ord(ch)-64
                row = int(match[2])-1
                dest = self.tables[tab.strip("'")][row]
                while len(dest) < col+len(entry['values'][0])-1:
                    dest.append('')
                dest[col-1:col-1+len(entry['values'][0])] = entry['values'][0]
        return Response({})


class ChaineTests(unittest.TestCase):
    def test_plan_corrompu_bloque_avant_tout_post_sheets(self):
        from pmu_geny.controle_sync_sheets import BlocageSynchronisation
        session=SheetsSession()
        session.tables['Historique chevaux'].append(['perf','123456','Test','3'])
        source={'Historique chevaux':{'x':{'cle_performance':'perf','identifiant_cheval':'123456','cheval':'Test','classement':'3'}},
                'Courses & Prévisions':{},'Résultats & Analyse':{}}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict('os.environ',{'GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON':'{}','PMU_SHEETS_CONTROLES':str(Path(tmp)/'controle.jsonl')}), \
             patch('google.oauth2.service_account.Credentials.from_service_account_info',return_value=object()), \
             patch('google.auth.transport.requests.AuthorizedSession',return_value=session), \
             patch('pmu_geny.sync_google_sheets.source_rows',return_value=source), \
             patch('pmu_geny.sync_google_sheets.plan_sheet',return_value=(session.tables['Historique chevaux'][0],[],[['perf','123456','Test','3']])), \
             patch('builtins.print'):
            with self.assertRaisesRegex(BlocageSynchronisation,'REINSERTION'):
                synchroniser({'nom':'Test','geny':{'id':'123456'}},'fake',cache=Path(tmp))
        self.assertEqual(session.writes,[])

    def test_cycle_pmu_alimente_file_sans_collecte_geny_et_respecte_jour_j(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        from pmu_geny.auto_v18 import run
        now = datetime(2026, 11, 13, 10, tzinfo=ZoneInfo('Europe/Paris'))
        for tomorrow in (False, True):
            with self.subTest(tomorrow=tomorrow), tempfile.TemporaryDirectory() as tmp:
                cache = Path(tmp)
                departure = now+timedelta(days=int(tomorrow), hours=1)
                day = departure.date().isoformat()
                course = {'date': day, 'code': 'R1C1', 'depart': departure.isoformat(),
                          'nom': 'PRIX TEST', 'hippodrome': 'VINCENNES', 'nombre_declares': 3,
                          'distance_m': 2700, 'discipline': 'TROT_ATTELE', 'priorite_metier': 'P1'}
                raw = {'participants': [{'numPmu': i, 'nom': 'Cheval '+str(i), 'nonPartant': False}
                                        for i in range(1, 4)]}
                with patch('pmu_geny.auto_v18.get_json', return_value=raw), \
                     patch('pmu_geny.auto_v18.programme_diagnostic', return_value=([course], {})), \
                     patch('pmu_geny.contexte_meteo_v20.collecter_meteo', return_value='TEST'), \
                     patch('pmu_geny.sources_experts_v23.collecter', return_value='TEST'), \
                     patch('pmu_geny.top3_independants_v22.calculer', return_value='TEST') as top3, \
                     patch('pmu_geny.cotes_v19.collecter', return_value='TEST'), \
                     patch('pmu_geny.ml_v19.snapshot_pmu', return_value='TEST') as snapshot, \
                     patch('pmu_geny.traitement_course.extraire_cheval') as legacy, \
                     patch('pmu_geny.decouverte_partants.produire_manifest') as discovery:
                    run(cache, day, [], 0, max_discoveries=0, now=now)
                    legacy.assert_not_called()
                    discovery.assert_not_called()
                    self.assertEqual(top3.call_count, 0 if tomorrow else 1)
                    self.assertEqual(snapshot.call_count, 0 if tomorrow else 1)
                    self.assertEqual(len(inc.lire(cache/inc.QUEUE)['chevaux']), 3)

    def test_sheets_idempotent_sans_toucher_top3_ni_formule_kpi(self):
        session = SheetsSession()
        source = {
            'Historique chevaux': {'perf': {'cle_performance': 'perf', 'identifiant_cheval': '123456',
                                             'cheval': 'Test', 'classement': '3'}},
            'Courses & Prévisions': {'c': {'course_key': 'course1', 'numero': '1', 'cheval': 'Test',
                                           'date_course': '2026-11-13', 'historique_statut': 'HISTO_OK_NOM',
                                           'historique_nb_courses_datees': 1,
                                           'historique_maj_utc': '2026-11-13T12:00:00+00:00',
                                           'baseline_top3': 'NON'}},
            'Résultats & Analyse': {}}
        horse = {'nom': 'Test', 'geny': {'id': '123456'}}
        with patch.dict('os.environ', {'GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON': '{}'}), \
             patch('google.oauth2.service_account.Credentials.from_service_account_info', return_value=object()), \
             patch('google.auth.transport.requests.AuthorizedSession', return_value=session), \
             patch('pmu_geny.sync_google_sheets.source_rows', return_value=source), \
             patch('pmu_geny.kpi_registre.calculer_kpi', return_value={'Indicateur test': (1, 'preuve')}):
            first = synchroniser(horse, 'fake', cache=Path('/tmp/unused'))
            second = synchroniser(horse, 'fake', cache=Path('/tmp/unused'))
        self.assertEqual(first['Historique chevaux']['lignes_ajoutees'], 1)
        self.assertEqual(second['Historique chevaux']['lignes_ajoutees'], 0)
        self.assertEqual(second['Courses & Prévisions']['cellules_actualisees'], 0)
        self.assertEqual(session.tables['Courses & Prévisions'][1][-1], 'OUI')
        self.assertEqual(session.tables['Data Quality & KPI'][1][4], '=NBVAL(A:A)')
        self.assertEqual(len(session.tables['Historique chevaux']), 2)

    def test_checkpoint_git_reel_rechargeable_et_fichiers_figes_intacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, remote, cache = root/'repo', root/'remote.git', root/'cache'
            def git(*args, cwd=None):
                return subprocess.check_output(['git', *args], cwd=cwd, text=True,
                                               stderr=subprocess.DEVNULL).strip()
            git('init', '--bare', str(remote))
            git('init', '-b', 'main', str(repo))
            git('config', 'user.name', 'Test', cwd=repo)
            git('config', 'user.email', 'test@example.invalid', cwd=repo)
            (repo/'code.txt').write_text('code')
            git('add', '.', cwd=repo)
            git('commit', '-m', 'code', cwd=repo)
            git('remote', 'add', 'origin', str(remote), cwd=repo)
            git('switch', '-c', 'pmu-data', cwd=repo)
            inc.ecrire(repo/'pronostics/fige.json', {'preuve': 'intacte'})
            inc.ecrire(repo/'etat_persistant.json', {'version': 1, 'chevaux': {}})
            git('add', '.', cwd=repo)
            git('commit', '-m', 'data', cwd=repo)
            git('push', 'origin', 'pmu-data', cwd=repo)
            git('switch', 'main', cwd=repo)
            inc.ecrire(cache/inc.QUEUE, {'version': 1, 'chevaux': {'123456': {'sync': 'A_FAIRE'}}})
            inc.ecrire(cache/'etat_persistant.json', {'version': 1, 'chevaux': {'123456': {'statut': 'COMPLET'}}})
            inc.ecrire(cache/'historiques/123456/historique_geny.json', {'preuve': 'historique valide'})
            # Même si un appelant fournit un fichier de prévision modifié, il n'est pas publié.
            inc.ecrire(cache/'pronostics/fige.json', {'preuve': 'ne doit pas etre publiee'})
            with patch.object(inc, '__file__', str(repo/'pmu_geny/historiques_incrementaux.py')):
                inc.checkpoint_distant(cache)
            queue = json.loads(git('show', 'pmu-data:collecte_incrementale/etat.json', cwd=remote))
            frozen = json.loads(git('show', 'pmu-data:pronostics/fige.json', cwd=remote))
            self.assertEqual(queue['chevaux']['123456']['sync'], 'A_FAIRE')
            self.assertEqual(frozen, {'preuve': 'intacte'})

    def test_fenetres_decision_jour_j_et_dst(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        from pmu_geny.planification_v20_2 import decision_autorisee
        paris = ZoneInfo('Europe/Paris')
        for day in ('2026-03-29', '2026-10-25', '2026-11-13'):
            for hour, minute, expected in [(6,59,False),(7,0,True),(20,59,True),(21,0,True),(21,1,False)]:
                now = datetime.fromisoformat(f'{day}T{hour:02}:{minute:02}:00').replace(tzinfo=paris)
                with self.subTest(day=day, hour=hour, minute=minute):
                    self.assertEqual(decision_autorisee(now, day, now+timedelta(hours=1)), expected)
                    self.assertFalse(decision_autorisee(now, (now+timedelta(days=1)).date().isoformat(), now+timedelta(days=1)))
                    self.assertFalse(decision_autorisee(now, day, now))


if __name__ == '__main__':
    unittest.main()
