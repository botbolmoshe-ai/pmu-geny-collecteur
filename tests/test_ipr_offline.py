import os
from datetime import datetime, timedelta
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from dashboard.trot_analytics.usages import IPR
from pmu_geny.echeances_production import preuves_sheets, sauver
from pmu_geny.ipr import VERSION, calculer, enregistrer, evaluer_cheval
from pmu_geny.ipr_prospectif import certifier, donnees_sheets, mesurer
from pmu_geny.moteur_sheets import SynchroniseurSheets
from pmu_geny.sync_google_sheets import COMPARE_COLUMNS, DISPLAY_NAMES, canonical_headers, plan_sheet
from test_v26_chaine_offline import Response, SheetsSession

STAMP = datetime.fromisoformat('2026-11-23T10:00:00+01:00')
COURSE = {'date': '2026-11-23', 'code': 'R1C1', 'depart': '2026-11-23T13:00:00+01:00',
          'hippodrome': 'Vincennes', 'discipline': 'Attelé', 'distance_m': 2700,
          'nombre_declares': 4, 'parametres_pmu': {'typeDepart': 'Volté', 'parcours': 'GP'}}
PROFILE = {'nom': 'Test', 'statut_np': 'PARTANT', 'ferrure': 'D4'}
ROW = {'date': '2026-11-20', 'hippodrome': 'Vincennes', 'discipline': 'Attelé',
       'distance_m': 2700, 'classement': '3', 'nombre_partants': 9, 'piste': 'GP', 'ferrure': 'D4'}
KEY = '2026-11-23_R1C1'
TAB = 'Courses & Prévisions'


def lien(*rows, stamp=STAMP):
    return {'cheval_id': '123', 'methode': 'NOM_EXACT_UNIQUE',
            'historique': {'extrait_utc': stamp.isoformat(), 'source_url': 'https://www.geny.com/cheval/123',
                           'performances': list(rows)}}


def ligne(n, **fields):
    return {'date_course': COURSE['date'], 'rncn': COURSE['code'], 'course_key': KEY, 'numero': str(n), **fields}


class IprTests(unittest.TestCase):
    def test_score_relatif_dai_et_absences(self):
        percentile = evaluer_cheval(COURSE, PROFILE, lien(ROW), STAMP)
        self.assertEqual(percentile['ipr_score'], 75)
        fail = evaluer_cheval(COURSE, PROFILE, lien({**ROW, 'classement': 'DAI'}), STAMP)
        self.assertEqual(fail['ipr_score'], 0)
        self.assertIn('100%', fail['ipr_motifs'])
        different = {**ROW, 'date': '2026-11-19', 'discipline': 'Monté'}
        too_far = {**ROW, 'date': '2026-11-18', 'distance_m': 2000}
        late = {**ROW, 'date': '2026-11-23', 'classement': '1'}
        cases = (lien(different, too_far, late), lien(ROW, ROW),
                 lien(ROW, stamp=STAMP + timedelta(seconds=1)),
                 {**lien(ROW), 'methode': 'NOM_AMBIGU'}, lien())
        for link in cases:
            self.assertIsNone(evaluer_cheval(COURSE, PROFILE, link, STAMP)['ipr_score'])
        older = {**ROW, 'date': '2026-11-17', 'classement': '1', 'ferrure': None}
        default = evaluer_cheval(COURSE, PROFILE, lien(ROW, older), STAMP)
        start = {'mode': 'Autostart', 'capture_utc': STAMP.isoformat(),
                 'source': 'GENY_DONNEES_STRUCTUREES', 'url': 'https://www.geny.com/course/1'}
        changed = evaluer_cheval(COURSE, PROFILE, lien(ROW, {**older, 'depart_trot': start}), STAMP)
        self.assertLess(changed['ipr_score'], default['ipr_score'])
        self.assertGreater(changed['ipr_couverture'], default['ipr_couverture'])

    def test_np_inconnus_et_preparation_interdisent_le_top3(self):
        profils = {n: dict(PROFILE) for n in range(1, 5)}
        links = {str(n): lien({**ROW, 'classement': str(n)}) for n in range(1, 5)}
        profils[4]['statut_np'] = 'NON_PARTANT'
        doc = calculer(COURSE, profils, links, STAMP, STAMP)
        self.assertEqual(doc['top3'], [1, 2, 3])
        self.assertIsNone(doc['chevaux']['4']['ipr_score'])
        self.assertEqual(doc['partants'], ['1', '2', '3'])
        profils[4]['statut_np'] = 'NP_NON_VERIFIE'
        unknown = calculer(COURSE, profils, links, STAMP, STAMP)
        self.assertFalse(unknown['top3'])
        self.assertIsNone(unknown['chevaux']['1']['ipr_score'])
        yesterday = STAMP - timedelta(days=1)
        profils[4]['statut_np'] = 'NON_PARTANT'
        prep = calculer(COURSE, profils, {n: lien(ROW, stamp=yesterday) for n in links}, yesterday, yesterday)
        self.assertEqual(prep['chevaux']['1']['ipr_score'], 75)
        self.assertFalse(prep['top3'])
        self.assertTrue(prep['preparation'])

    def test_version_immuable_et_hors_coupure(self):
        raw = {'participants': [{'numPmu': n, 'nom': f'Test {n}', 'nonPartant': False}
                                for n in range(1, 5)]}
        with TemporaryDirectory() as tmp, patch('pmu_geny.liaison_chevaux_v22.etablir',
                return_value={str(n): lien(ROW) for n in range(1, 5)}) as linker:
            root = Path(tmp)
            self.assertEqual(enregistrer(root, COURSE, raw, STAMP, lambda: STAMP), 'CALCULE')
            latest = root/'ipr'/f'{KEY}.json'
            first = latest.read_bytes()
            self.assertEqual(enregistrer(root, COURSE, raw, STAMP, lambda: STAMP), 'DEJA_CALCULE')
            self.assertEqual(enregistrer(root, COURSE, raw, STAMP, lambda: STAMP + timedelta(hours=3)), 'HORS_COUPURE')
            self.assertEqual(first, latest.read_bytes())
            self.assertEqual(len(list((root/'ipr'/'versions').rglob('*.json'))), 1)
            linker.assert_called_once()

    def test_certificat_exige_les_valeurs_relues_avant_depart(self):
        forecast = calculer(COURSE, {n: PROFILE for n in range(1, 5)},
                            {str(n): lien({**ROW, 'classement': str(n)}) for n in range(1, 5)}, STAMP, STAMP)
        ceremony = STAMP + timedelta(minutes=2)
        plan = {'plan_utc': STAMP.isoformat(), 'jalons_dus': [
            {'course': KEY, 'phase': 'H3', 'echeance': STAMP.isoformat()}]}
        published_rows = [ligne(n, **{k: row.get(k) if row.get(k) is not None else '' for k in IPR.libelles})
                          for n, row in forecast['chevaux'].items()]
        proof = {'lecture_utc': ceremony.isoformat(), 'ipr': donnees_sheets(published_rows)}
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sauver(root/'ipr'/f'{KEY}.json', forecast)
            self.assertFalse(certifier(root, plan, {**proof, 'ipr': donnees_sheets([*published_rows, published_rows[0]])}))
            self.assertFalse(certifier(root, plan, {**proof, 'lecture_utc': COURSE['depart']}))
            self.assertEqual(certifier(root, plan, proof), {KEY: 'H3'})
            path = root/'ipr'/'jalons'/f'{KEY}_H3_{VERSION}.json'
            frozen = path.read_bytes()
            certifier(root, plan, proof)
            self.assertEqual(path.read_bytes(), frozen)
            verified = STAMP + timedelta(hours=4)
            sauver(root/'arrivees'/f'{KEY}.json', {'date': COURSE['date'], 'course': COURSE['code'],
                   'source': 'PMU_API_PARTICIPANTS', 'verifie_utc': verified.isoformat(),
                   'arrivee': [{'numero': n, 'rang': n} for n in (1, 2, 3)]})
            self.assertEqual(mesurer(root, verified)['agrege'][0]['exact_3_sur_3'], 1)
            self.assertIsNone(mesurer(root, verified)['agrege'][0]['appariements']['direct'])


class FormatsSession(SheetsSession):
    def __init__(self, headers):
        super().__init__()
        self.tables[TAB] = [headers[:], [KEY, '1', 'Témoin']]
        self.formats = {}
        self.width = len(headers)

    def get(self, url, **kwargs):
        query = kwargs.get('params', {})
        if 'startColumn,rowData' not in query.get('fields', ''):
            response = super().get(url, **kwargs)
            if query.get('fields', '').startswith('sheets(properties'):
                for sheet in response.data['sheets']:
                    if sheet['properties']['title'] == TAB:
                        sheet['properties']['gridProperties']['columnCount'] = self.width
            return response
        fields = query['fields']
        if fields.count('(') != fields.count(')'):
            return type('BadRequest', (), {'status_code': 400})()
        blocks = []
        for a1 in query['ranges']:
            letters = re.search(r'!([A-Z]+)1:', a1)[1]
            index = 0
            for char in letters:
                index = index * 26 + ord(char) - 64
            index -= 1
            rowdata = []
            for row in range(2):
                cell = dict(self.formats.get((row, index), {}))
                if len(self.tables[TAB][row]) > index and row == 0:
                    cell['userEnteredValue'] = {'stringValue': self.tables[TAB][row][index]}
                rowdata.append({'values': [cell]})
            blocks.append({'startColumn': index, 'rowData': rowdata})
        return Response({'sheets': [{'data': blocks}]})

    def post(self, url, **kwargs):
        payload = kwargs['json']
        if 'requests' not in payload:
            return super().post(url, **kwargs)
        self.writes.append((url, payload))
        for req in payload['requests']:
            if 'appendDimension' in req:
                self.width += req['appendDimension']['length']
            elif 'repeatCell' in req and 'italic' in req['repeatCell']['fields']:
                cell = req['repeatCell']
                grid = cell['range']
                index = grid['startColumnIndex']
                for row in range(grid['startRowIndex'], grid.get('endRowIndex', 2)):
                    self.formats[row, index] = cell['cell']
        return Response({})


class IprSheetsTests(unittest.TestCase):
    def test_migration_a_droite_style_durable_et_zero_distinct_du_vide(self):
        raw_headers = ['course_key', 'numero', 'cheval', *COMPARE_COLUMNS]
        raw_headers = list(dict.fromkeys(raw_headers))
        visible_headers = [DISPLAY_NAMES.get(k, k) for k in raw_headers]
        session = FormatsSession(visible_headers)
        row = ligne(1, cheval='Témoin', ipr_score=0, ipr_statut=IPR.usage, ipr_version=VERSION)
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {'IPR_SHADOW_ENABLED': 'true'}):
            engine = SynchroniseurSheets(tmp, 'fake-ipr', session=session)
            def sync(source):
                return engine._synchroniser_onglet(TAB, {'1': source}, engine.metadata()[TAB],
                                                  full_source=False, allow_structure=True)
            with patch.object(engine, '_formater_profils'):
                sync(row)
                self.assertTrue(engine.observations_verifiees)
                self.assertEqual(canonical_headers(session.tables[TAB][0]), [*raw_headers, *IPR.libelles])
                first_index = len(raw_headers)
                self.assertEqual(session.tables[TAB][1][first_index], 0)
                self.assertTrue(session.formats[(0, first_index)]['userEnteredFormat']['textFormat']['italic'])
                self.assertEqual(session.formats[(0, first_index)]['note'], IPR.usage)
                self.assertTrue(session.formats[(1, first_index)]['userEnteredFormat']['textFormat']['italic'])
                self.assertNotIn((0, first_index-1), session.formats)
                count = len(session.writes)
                sync(row)
                self.assertEqual(len(session.writes), count)
                sync({**row, 'ipr_score': ''})
                self.assertEqual(session.tables[TAB][1][first_index], '')
                with patch.object(engine, '_formater_observations', side_effect=RuntimeError):
                    sync(row)
                self.assertFalse(engine.observations_verifiees)
                self.assertNotIn('ipr', preuves_sheets([row], STAMP,
                                                     observations_verifiees=engine.observations_verifiees))
        with patch.dict(os.environ, {'IPR_SHADOW_ENABLED': 'false'}):
            self.assertEqual(plan_sheet(raw_headers, [], {}, TAB)[0], raw_headers)
