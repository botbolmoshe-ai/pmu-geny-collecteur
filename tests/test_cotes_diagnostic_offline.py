from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from pmu_geny.cotes_v19 import collecter, dernier_releve


class CotesDiagnosticTests(TestCase):
    def test_champ_absent_et_rapport_rejete_sont_distincts(self):
        now = datetime(2026, 11, 21, tzinfo=timezone.utc)
        course = {'date': '2026-11-21', 'code': 'R1C1', 'nombre_declares': 3,
                  'depart': (now + timedelta(hours=1)).isoformat()}
        participants = {'participants': [
            {'numPmu': 1, 'statut': 'PARTANT'},
            {'numPmu': 2, 'statut': 'PARTANT', 'dernierRapportDirect': {'indisponible': True}},
            {'numPmu': 3, 'statut': 'PARTANT', 'dernierRapportDirect': {'rapport': 5}},
        ]}
        with TemporaryDirectory() as directory:
            cache = Path(directory)
            self.assertEqual(collecter(cache, course, participants, now), 'COTES_PARTIELLES')
            report = dernier_releve(cache, course)
        self.assertEqual(report['cotes_extraites'], 1)
        self.assertEqual(report['diagnostic_derniere_lecture'], {
            'chevaux_sans_champ_rapport': 1,
            'chevaux_sans_cote_valide': 2,
            'champ_present:dernierRapportDirect': 2,
            'rapport_indisponible_ou_hors_simple_gagnant_direct': 1,
            'chevaux_avec_cote_valide': 1,
        })
