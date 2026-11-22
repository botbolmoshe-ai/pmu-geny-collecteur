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
                    self.assertEqual(len(commands), 2 if nocturne == 'true' else 1)
                    self.assertTrue(all(('--local' in cmd.split()) == (geny == 'false') for cmd in commands))

    def test_budget_nocturne_court_garde_du_temps_pour_le_fond(self):
        path = Path(__file__).resolve().parents[1] / '.github/workflows/historiques-incrementaux.yml'
        steps = yaml.safe_load(path.read_text())['jobs']['historiques']['steps']
        script = next(step['run'] for step in steps if 'GENY_AUTORISE' in step.get('env', {}))
        python_mock = """python() {
          case "$1 $2" in
            '-c '*) echo "$SIMULATED_BUDGET";;
            '-m pmu_geny.historiques_incrementaux') echo "$*"; SIMULATED_BUDGET="$PMU_BUDGET_AFTER";;
            *) echo "$*";;
          esac
        }
        """
        for after in ('3', '0'):
            with self.subTest(budget_recalcule=after):
                output = subprocess.check_output(
                    ['bash', '-e', '-c', python_mock + script], text=True,
                    env={**os.environ, 'COLLECTE_NOCTURNE': 'true', 'GENY_AUTORISE': 'true',
                         'MAX_MINUTES': '7', 'SIMULATED_BUDGET': '5', 'PMU_BUDGET_AFTER': after})
                self.assertIn('historiques_incrementaux --cache cache_pmu --max-minutes 2', output)
                if after == '3':
                    self.assertIn('rattrapage_historiques --cache cache_pmu --max-minutes 3', output)
                else:
                    self.assertNotIn('rattrapage_historiques', output)
                    self.assertIn('RATTRAPAGE_FOND_DIFFERE BUDGET_CRENEAU_NOCTURNE', output)
