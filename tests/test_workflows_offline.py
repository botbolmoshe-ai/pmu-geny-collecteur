"""Compiler aussi le Python intégré aux workflows, avant la production."""
import os
import re
import subprocess
import unittest
from pathlib import Path

import yaml


class WorkflowSyntaxTests(unittest.TestCase):
    def test_python_embarque_compile_sans_execution(self):
        total = 0
        for path in (Path(__file__).resolve().parents[1] / '.github/workflows').glob('*.yml'):
            workflow = yaml.safe_load(path.read_text())
            for job in workflow.get('jobs', {}).values():
                for step in job.get('steps', []):
                    script = step.get('run', '')
                    for match in re.finditer(r"python - <<'(\w+)'\n(.*?)^\1$", script, re.M | re.S):
                        with self.subTest(workflow=path.name, step=step.get('name')):
                            compile(match[2], str(path), 'exec')
                        total += 1
        self.assertGreaterEqual(total, 3, 'Les blocs Python de production doivent être contrôlés')

    def test_collecte_locale_sans_navigateur_au_niveau_de_l_etape_actions(self):
        path = Path(__file__).resolve().parents[1] / '.github/workflows/historiques-incrementaux.yml'
        steps = yaml.safe_load(path.read_text())['jobs']['historiques']['steps']
        script = next(step['run'] for step in steps if 'GENY_AUTORISE' in step.get('env', {}))
        python_mock = 'python() { if [[ "$1" == "-c" ]]; then echo 15; else echo "$*"; fi; }\n'
        for nocturne in ('true', 'false'):
            for geny in ('false', 'true'):
                with self.subTest(nocturne=nocturne, geny=geny):
                    output = subprocess.check_output(
                        ['bash', '-e', '-c', python_mock + script], text=True,
                        env={**os.environ, 'COLLECTE_NOCTURNE': nocturne,
                             'GENY_AUTORISE': geny, 'MAX_MINUTES': '7'})
                    commands = [line for line in output.splitlines() if line.startswith('-m pmu_geny.')]
                    self.assertEqual(len(commands), 1)
                    self.assertNotIn('rattrapage_historiques', output)
                    self.assertTrue(all(('--local' in cmd.split()) == (geny == 'false') for cmd in commands))

    def test_rattrapage_automatique_reverifie_la_marge_avant_geny(self):
        path = Path(__file__).resolve().parents[1] / '.github/workflows/rattrapage-historiques.yml'
        config = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
        self.assertIn('schedule', config['on'])
        steps = config['jobs']['rattrapage']['steps']
        script = next(step['run'] for step in steps if step.get('name', '').startswith('Inventorier'))
        mock = """date() { echo 02; }
        python() { if [[ "$1" == -c ]]; then echo "$PMU_BUDGET"; else echo "$*"; fi; }
        """
        for budget in ('3', '0'):
            with self.subTest(budget=budget):
                output = subprocess.check_output(['bash', '-e', '-c', mock + script], text=True,
                    env={**os.environ, 'PMU_BUDGET': budget, 'MAX_MINUTES': '7', 'PASSAGE_PLANIFIE': 'true',
                         'ACTUALISER_INVENTAIRE': 'false', 'RECONCILIER_IDENTITES': 'false',
                         'ARCHIVES_DIAGNOSTICS': ''})
                if budget == '3':
                    self.assertIn('--max-minutes 3 --publier --dedie --nocturne', output)
                else:
                    self.assertNotIn('rattrapage_historiques', output)
                    self.assertIn('RATTRAPAGE_DIFFERE_HORS_CRENEAU_OU_ECHEANCE_PMU', output)

    def test_cinq_workflows_publics_et_fuseau_paris(self):
        workflows = Path(__file__).resolve().parents[1] / '.github/workflows'
        configs = [yaml.load(path.read_text(), Loader=yaml.BaseLoader) for path in workflows.glob('*.yml')]
        self.assertEqual({config['name'] for config in configs}, {
            '01 — PMU Production', '02 — Geny Collecte incrémentale', '03 — Geny Rattrapage global',
            '04 — Validation moteur PMU', '05 — Validation TROT Analytics',
        })
        for config in configs:
            self.assertEqual(config['env']['TZ'], 'Europe/Paris')
            for schedule in config['on'].get('schedule', []):
                self.assertEqual(schedule['timezone'], 'Europe/Paris')

    def test_declenchements_sous_le_verrou_et_sans_doublon(self):
        root = Path(__file__).resolve().parents[1] / '.github/workflows'
        historique = yaml.safe_load((root / 'historiques-incrementaux.yml').read_text())
        pmu = yaml.safe_load((root / 'pmu-v16.yml').read_text())
        fond = yaml.safe_load((root / 'rattrapage-historiques.yml').read_text())
        collecter = historique['jobs']['historiques']
        publier = historique['jobs']['publication']
        self.assertEqual(historique['concurrency'], fond['concurrency'])
        self.assertEqual(historique['concurrency']['group'], 'pmu-geny-acquisition')
        self.assertIn('pmu-geny-acquisition', pmu['concurrency']['group'])
        self.assertEqual(pmu['jobs']['traiter-course']['concurrency'], publier['concurrency'])
        self.assertEqual(fond['jobs']['rattrapage']['concurrency'], publier['concurrency'])
        self.assertEqual(publier['concurrency']['group'], 'pmu-donnees-production')
        self.assertIn('geny-lecture-', collecter['concurrency']['group'])
        self.assertIn('pmu-donnees-production', collecter['concurrency']['group'])
        self.assertIn("GENY_ACQUISITION_INDEPENDANTE != 'false'", collecter['concurrency']['group'])
        self.assertIn("GENY_ACQUISITION_INDEPENDANTE != 'false'", collecter['env']['ACQUISITION_INDEPENDANTE'])
        self.assertEqual(publier['needs'], 'historiques')
        acquisition = next(s for s in collecter['steps'] if '--acquisition-seule' in s.get('run', ''))
        self.assertNotIn('GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON', acquisition['env'])
        self.assertTrue(any('--publication-seule' in step.get('run', '') for step in publier['steps']))
        self.assertEqual(historique['jobs']['historiques']['permissions']['actions'], 'write')
        self.assertEqual(pmu['permissions']['actions'], 'write')
        secours = next(step for step in historique['jobs']['historiques']['steps']
                       if step.get('name', '').startswith('Demander un cycle'))
        self.assertIn("steps.plan.outputs.secours_pmu == 'true'", secours['if'])
        relais = pmu['jobs']['traiter-course']['steps'][-1]['run']
        commandes = '''gh() {
          if [[ "$1" == api ]]; then printf '%s' "$RUN_ACTIF"; else echo "$*"; fi
        }
        python() { return 0; }
        '''
        for script, workflow in ((secours['run'], 'pmu-v16.yml'), (relais, 'historiques-incrementaux.yml')):
            for actif in ('', '123'):
                with self.subTest(workflow=workflow, actif=actif):
                    stdout = subprocess.check_output(
                        ['bash', '-e', '-c', commandes + script], text=True,
                        env={**os.environ, 'RUN_ACTIF': actif, 'GITHUB_REPOSITORY': 'exemple/pmu'})
                    self.assertEqual(stdout.count(f'workflow run {workflow}'), int(not actif))
        for nocturne, option, attendu in (('true', 'true', False), ('false', '', True),
                                           ('false', 'false', False)):
            stdout = subprocess.check_output(
                ['bash', '-e', '-c', commandes + relais], text=True,
                env={**os.environ, 'RUN_ACTIF': '', 'GITHUB_REPOSITORY': 'exemple/pmu',
                     'GENY_ACQUISITION_INDEPENDANTE': option, 'PMU_NOCTURNE': nocturne})
            self.assertEqual('acquisition_independante=true' in stdout, attendu)

    def test_rattrapage_dedie_valide_budget_et_selectionne_le_mode_selon_paris(self):
        path = Path(__file__).resolve().parents[1] / '.github/workflows/rattrapage-historiques.yml'
        steps = yaml.safe_load(path.read_text())['jobs']['rattrapage']['steps']
        check = steps[0]['run']
        for value, expected in (('1', 0), ('15', 0), ('0', 2), ('20', 2), ('2.5', 2)):
            with self.subTest(budget=value):
                result = subprocess.run(['bash', '-e', '-c', check], text=True, capture_output=True,
                                        env={**os.environ, 'MAX_MINUTES': value})
                self.assertEqual(result.returncode, expected)
        script = next(step['run'] for step in steps if step.get('name', '').startswith('Inventorier'))
        mock = 'date() { echo "$HEURE_PARIS"; }\npython() { echo "$*"; }\n'
        for heure, nocturne in (('06', True), ('07', False), ('20', False), ('21', True)):
            with self.subTest(heure=heure):
                output = subprocess.check_output(
                    ['bash', '-e', '-c', mock + script], text=True,
                    env={**os.environ, 'HEURE_PARIS': heure, 'MAX_MINUTES': '15',
                         'ACTUALISER_INVENTAIRE': 'false', 'RECONCILIER_IDENTITES': 'false',
                         'ARCHIVES_DIAGNOSTICS': ''})
                command = next(line for line in output.splitlines() if line.startswith('-m '))
                self.assertIn('--dedie', command.split())
                self.assertIn('--max-minutes 15', command)
                self.assertEqual('--nocturne' in command.split(), nocturne)
