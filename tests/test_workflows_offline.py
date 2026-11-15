"""Compiler aussi le Python intégré aux workflows, avant la production."""
import re
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
