from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock

from pmu_geny import avis_24h_trot as source
from pmu_geny.echeances_production import sauver


HEADLINE = 'Un nouveau test pour Pouliche Exemple'
URL = 'https://province-courses.fr/24H/article_PDF.php?id=442'
PAGE = f"""
<div><span>Actualité</span> - <small>21.11.2026</small></div>
<h3>{HEADLINE}</h3>
<p>Pouliche Exemple revient à Vincennes dimanche dans le Prix de Démonstration,
quand les mâles disputeront le Prix de Vérification.</p>
"""
COURSE = {'code': 'R1C2', 'date': '2026-11-22', 'hippodrome': 'Vincennes',
          'nom': 'Prix de Démonstration', 'depart': '2026-11-22T15:00:00+01:00'}
NOW = datetime(2026, 11, 21, 21, tzinfo=timezone.utc)


class Avis24hTests(TestCase):
    def test_article_rattache_a_un_seul_prix(self):
        self.assertIsNotNone(source.article(PAGE, HEADLINE, COURSE, 'POULICHE EXEMPLE', NOW))
        self.assertIsNone(source.article(PAGE, HEADLINE, {**COURSE, 'nom': 'Prix de Vérification'},
                                         'POULICHE EXEMPLE', NOW))
        self.assertIsNone(source.article(PAGE, HEADLINE, COURSE, 'AUTRE CHEVAL', NOW))
        self.assertIsNone(source.article(PAGE, HEADLINE, {**COURSE, 'date': '2026-11-29'},
                                         'POULICHE EXEMPLE', NOW))

    def test_collecte_preuve_deduplication_et_limite_depart(self):
        with TemporaryDirectory() as directory:
            cache = Path(directory)
            sauver(cache/'sources_pmu/programme_2026-11-22.json', {'programme': [COURSE]})
            sauver(cache/'partants_actuels/2026-11-22_R1C2.json', {'chevaux': {
                '8': {'nom': 'POULICHE EXEMPLE', 'statut_np': 'PARTANT'}}})
            fetch = Mock(side_effect=[f'<a href="{URL}">{HEADLINE}</a>', PAGE])
            self.assertEqual(source.collecter(cache, fetch=fetch, clock=lambda: NOW), 1)
            self.assertEqual(source.collecter(cache, fetch=fetch, clock=lambda: NOW), 0)
            self.assertEqual(fetch.call_count, 2)
            doc = source.lire(cache/'avis_editoriaux/2026-11-22_R1C2.json')
            row = source.champs_sheet(doc, 8, 'Pouliche Exemple', source.instant(COURSE['depart']), NOW)
            self.assertEqual(row['avis_24h_trot'], HEADLINE)
            self.assertIn(URL, row['source_24h_trot'])
            self.assertFalse(source.champs_sheet(doc, 8, 'Pouliche Exemple', NOW, NOW))
