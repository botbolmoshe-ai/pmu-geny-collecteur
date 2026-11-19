from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pmu_geny.departs_trot import depart_partant_pmu
from pmu_geny.ferrures_geny import enrichir
from pmu_geny.formes_contextuelles_v32 import forme_meme_depart
from pmu_geny.ml_v19 import load, pmu_rows
from pmu_geny.partants_actuels_v21 import enregistrer, extraire_partants
from pmu_geny.sync_google_sheets import source_rows


class DepartsTrotTests(unittest.TestCase):
    def setUp(self):
        self.course = {
            'date': '2026-11-19', 'code': 'R3C6', 'depart': '2026-11-19T18:55:00+01:00',
            'hippodrome': 'HIPPODROME DE PARIS-VINCENNES', 'distance_m': 2100, 'discipline': 'TROT_ATTELE',
            'parametres_pmu': {'categorieParticularite': 'AUTOSTART'},
        }
        self.now = datetime(2026, 11, 19, 11, 50, tzinfo=timezone.utc)
        self.url = 'https://www.geny.com/cheval/123-test'

    def test_position_sourcee_capacites_et_absences(self):
        partant = {'numPmu': 2, 'placeCorde': 8}
        vincennes = depart_partant_pmu(self.course, partant)
        self.assertEqual((vincennes['position'], vincennes['ligne'], vincennes['capacite']), (8, 1, 9))
        cabourg = depart_partant_pmu({**self.course, 'hippodrome': 'CABOURG', 'distance_m': 2725}, partant)
        self.assertEqual((cabourg['position'], cabourg['ligne'], cabourg['capacite']), (8, 2, 7))
        self.assertNotIn('position', depart_partant_pmu(self.course, {'numPmu': 2}))
        unknown = depart_partant_pmu({**self.course, 'hippodrome': 'Autre'}, partant)
        self.assertEqual(unknown['position'], 8)
        self.assertNotIn('ligne', unknown)
        explicit = {**self.course, 'parametres_pmu': {
            'conditions': "Départ à l'Autostart. 8 au premier rang."}}
        self.assertEqual(depart_partant_pmu(explicit, {'placeCorde': 9})['ligne'], 2)

    def test_non_partant_et_depart_volte_distinct_de_l_inconnu(self):
        active = {'numPmu': 10, 'statut': 'PARTANT', 'placeCorde': 10, 'handicapDistance': 2125}
        withdrawn = {'numPmu': 1, 'statut': 'NON_PARTANT', 'placeCorde': 1}
        profiles = extraire_partants({'participants': [withdrawn, active]}, course=self.course)
        self.assertNotIn('depart_trot', profiles[1])
        self.assertEqual(profiles[10]['depart_trot']['ligne'], 2)
        volte = depart_partant_pmu({**self.course, 'parametres_pmu': {'typeDepart': 'ELASTIQUE'}}, active)
        self.assertEqual((volte['mode'], volte['recul_m']), ('Volté', 25))
        unknown = depart_partant_pmu({**self.course, 'parametres_pmu': {}}, active)
        self.assertEqual(unknown['recul_m'], 25)
        self.assertNotIn('mode', unknown)
        self.assertNotIn('position', unknown)

    def test_relecture_apres_depart_ne_remplace_pas_la_position_capturee(self):
        from pmu_geny.auto_v18 import save

        with TemporaryDirectory() as tmp, patch('pmu_geny.partants_actuels_v21.datetime', wraps=datetime) as clock:
            root = Path(tmp)
            path = root / 'partants_actuels/2026-11-19_R3C6.json'
            save(root / 'sources_pmu/programme_2026-11-19.json', {'programme': [self.course]})
            clock.now.return_value = self.now
            enregistrer(root, self.course, {'participants': [
                {'numPmu': 1, 'nom': 'A', 'statut': 'PARTANT', 'placeCorde': 9}]})
            clock.now.return_value = datetime(2026, 11, 19, 20, tzinfo=timezone.utc)
            enregistrer(root, self.course, {'participants': [
                {'numPmu': 1, 'nom': 'A', 'statut': 'PARTANT', 'placeCorde': 3},
                {'numPmu': 2, 'nom': 'B', 'statut': 'PARTANT', 'placeCorde': 4}]})
            doc = load(path)['chevaux']
            self.assertEqual(doc['1']['depart_trot']['position'], 9)
            self.assertNotIn('depart_trot', doc['2'])
            rows = {str(row['numero']): row for row in source_rows(root)['Courses & Prévisions'].values()}
            self.assertEqual(rows['1']['ligne_autostart'], 1)
            self.assertEqual(rows['2'].get('ligne_autostart', ''), '')

    def test_historique_geny_explicite_sans_fuite_temporelle(self):
        participation = {'rang': 2, 'positionDepart': 7, 'recul': 0,
            'hippodrome': {'nom': 'Vincennes', 'nationaliteIso': 'FR'},
            'course': {'id': 123, 'distance': 2100, 'specialite': 'ATTELE',
                       'depart': 'AUTOSTART', 'dateHeureCourse': '2026-11-10T14:00:00'}}
        row = {'date': '2026-11-10', 'hippodrome': 'Vincennes', 'discipline': 'Attelé',
               'distance_m': '2100', 'classement': '2'}
        doc = {'performances': [row], 'extrait_utc': '2026-11-18T12:00:00+00:00', 'source_url': self.url}
        with patch('pmu_geny.ferrures_geny.participations', return_value=[participation]):
            enrichir(doc, '', '123', self.url, '2026-11-09T12:00:00+00:00')
            self.assertNotIn('depart_trot', row)
            enrichir(doc, '', '123', self.url, doc['extrait_utc'])
        self.assertEqual(row['depart_trot']['position'], 7)
        self.assertIsNotNone(forme_meme_depart(doc, self.course, {}, self.now))
        row['depart_trot']['capture_utc'] = '2026-11-19T18:00:00+00:00'
        self.assertIsNone(forme_meme_depart(doc, self.course, {}, self.now))

    def test_ml_capture_les_champs_candidats_sans_cotes(self):
        raw = {'participants': [
            {'numPmu': n, 'statut': 'PARTANT', 'nom': f'Cheval {n}', 'placeCorde': n + 6,
             'dernierRapportDirect': {'rapport': 4.3}} for n in (1, 2, 3, 4)]}
        with TemporaryDirectory() as tmp:
            status, rows, _ = pmu_rows(Path(tmp), self.course, raw, self.now)
        self.assertEqual(status, 'OK')
        self.assertEqual(rows[-1]['features']['ligne_autostart'], 2)
        self.assertEqual(rows[-1]['features']['position_autostart_relative'], 0)
        self.assertEqual(rows[-1]['features']['distance_autostart'], 2100)
        self.assertFalse(any('cote' in key for key in rows[-1]['features']))
