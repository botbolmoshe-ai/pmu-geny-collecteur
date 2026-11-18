"""Recette des profils, du TOP3 et de leur publication dans le registre."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmu_geny.echeances_production import lire, sauver
from pmu_geny.moteur_sheets import SynchroniseurSheets
from pmu_geny.profils_partants import detecter_crack, detecter_haut_potentiel, sorties_verifiees
from pmu_geny.sync_google_sheets import source_rows
from pmu_geny.top3_independants_v22 import calculer
from test_v26_chaine_offline import Response, SheetsSession

NOW = datetime(2026, 11, 18, 10, tzinfo=timezone.utc)
COURSE = {'date': '2026-11-18', 'code': 'R1C1', 'depart': '2026-11-18T12:00:00+00:00',
          'hippodrome': 'Vincennes', 'discipline': 'TROT_ATTELE', 'distance_m': 2700,
          'nombre_declares': 4}


def historique(elite=False, rangs=('1', '2', '9', '8', '7', '5')):
    sorties = []
    for i, rang in enumerate(rangs):
        jour = date.fromisoformat(COURSE['date']) - timedelta(days=7 * (i + 1))
        groupe = ('Gr. I' if i == 0 else 'Gr. II') if elite and i < 2 else 'Gr. III'
        sorties.append({'date': jour.isoformat(), 'classement': rang, 'discipline': 'Attelé',
                        'distance_m': '2500', 'hippodrome': 'Vincennes',
                        'texte_source': f'{jour:%d/%m/%y} | Vincennes | Attelé | 2 500 | {groupe}'})
    return {'statut': 'COMPLET', 'extrait_utc': (NOW - timedelta(hours=1)).isoformat(),
            'source_url': 'https://www.geny.com/test', 'performances': sorties}


def liaison(document):
    return {'cheval_id': '1', 'methode': 'NOM_EXACT_UNIQUE', 'historique': document}


class TestProfils(unittest.TestCase):
    def test_regles_independantes_et_distance(self):
        elite = sorties_verifiees(COURSE, liaison(historique(True)), NOW)
        potentiel = sorties_verifiees(COURSE, liaison(historique()), NOW)
        self.assertIn('Groupe I/II', detecter_crack(elite, 250_000))
        self.assertIsNone(detecter_crack(potentiel, 250_000))
        self.assertIn('hausse', detecter_haut_potentiel(potentiel, 5))
        self.assertIsNone(detecter_haut_potentiel(potentiel, 6))
        self.assertIsNotNone(detecter_haut_potentiel(elite, 5))
        loin = sorties_verifiees({**COURSE, 'distance_m': 3500}, liaison(historique()), NOW)
        self.assertIsNone(detecter_haut_potentiel(loin, 5))

    def test_gains_crack_et_taux_de_disqualification(self):
        fiabilite_limite = historique(True, ('1', '2', 'Dai', '8', '7', '5', '9', 'Di', 'Nc', 'Arr'))
        sorties = sorties_verifiees(COURSE, liaison(fiabilite_limite), NOW)
        for gains in (249_999.99, None, True, float('nan')):
            with self.subTest(gains=gains):
                self.assertIsNone(detecter_crack(sorties, gains))
        indices = detecter_crack(sorties, 250_000)
        self.assertIn('250 000 €', indices)
        self.assertIn('2 disq. sur 10', indices)
        self.assertIsNone(detecter_haut_potentiel(sorties, 5))
        fiabilite_limite['performances'][-1]['classement'] = 'Dpg'
        sorties = sorties_verifiees(COURSE, liaison(fiabilite_limite), NOW)
        self.assertIsNone(detecter_crack(sorties, 250_000))

    def test_potentiel_une_disqualification_admise_sur_dix_seulement(self):
        rangs = ('1', '2', 'Da', '8', '7', '5', 'Nc', 'Arr', 'Tb', '6')
        doc = historique(rangs=rangs)
        sorties = sorties_verifiees(COURSE, liaison(doc), NOW)
        self.assertIn('1 disq. sur 10', detecter_haut_potentiel(sorties, 5))
        self.assertIsNone(detecter_haut_potentiel(sorties[:9], 5))
        # Un résultat non interprétable dans la fenêtre ne prouve pas la fiabilité.
        doc['performances'][7]['classement'] = ''
        sorties = sorties_verifiees(COURSE, liaison(doc), NOW)
        self.assertIsNone(detecter_haut_potentiel(sorties, 5))

    def test_rendez_vous_groupes_espaces_et_recents(self):
        doc = historique()
        for i, sortie in enumerate(doc['performances']):
            groupe = 'Groupe 3' if i == 0 else 'Gr. III' if i == 5 else 'Crse A'
            sortie['texte_source'] = sortie['texte_source'].rsplit(' | ', 1)[0] + f' | {groupe}'
        sorties = sorties_verifiees(COURSE, liaison(doc), NOW)
        self.assertIn('2 sorties en Groupe I–III', detecter_haut_potentiel(sorties, 5))
        doc['performances'][-1]['date'] = '2026-10-15'
        sorties = sorties_verifiees(COURSE, liaison(doc), NOW)
        self.assertIsNone(detecter_haut_potentiel(sorties, 5))
        doc = historique()
        for sortie in doc['performances']:
            sortie['texte_source'] = sortie['texte_source'].replace('Gr. III', 'Crse A')
        for jour in ('2026-06-18', '2026-03-30'):
            doc['performances'].append({**doc['performances'][-1], 'date': jour,
                                        'texte_source': 'Date | Vincennes | Attelé | 2 500 | Gr. III'})
        sorties = sorties_verifiees(COURSE, liaison(doc), NOW)
        self.assertIsNone(detecter_haut_potentiel(sorties, 5))
        doc['performances'][0]['texte_source'] = doc['performances'][0]['texte_source'].replace(
            'Crse A', 'Gr. II')
        sorties = sorties_verifiees(COURSE, liaison(doc), NOW)
        self.assertIsNotNone(detecter_haut_potentiel(sorties, 5))

    def test_fuite_temporelle_et_discipline(self):
        doc = historique(True)
        for champ, valeur in (('extrait_utc', '2026-11-18T10:01:00+00:00'),
                              ('source_url', ''), ('extrait_utc', '2026-11-18T09:00:00')):
            self.assertEqual(sorties_verifiees(COURSE, liaison({**doc, champ: valeur}), NOW), [])
        self.assertEqual(sorties_verifiees({**COURSE, 'discipline': 'Monté'}, liaison(doc), NOW), [])
        self.assertEqual(sorties_verifiees(COURSE, {**liaison(doc), 'methode': 'NOM_AMBIGU'}, NOW), [])
        for jour in (COURSE['date'], '2026-11-19'):
            doc['performances'].append({**doc['performances'][0], 'date': jour})
        doc['performances'].append({**doc['performances'][0], 'date': '2026-11-17', 'discipline': 'Monté'})
        self.assertEqual(len(sorties_verifiees(COURSE, liaison(doc), NOW)), 6)

    def test_doublons_et_resultat_manquant(self):
        doc = historique(True)
        doc['performances'].append(doc['performances'][0].copy())
        sorties = sorties_verifiees(COURSE, liaison(doc), NOW)
        self.assertEqual(len(sorties), 6)
        self.assertIsNotNone(detecter_crack(sorties, 250_000))
        doc['performances'].append({**doc['performances'][0], 'classement': '3'})
        sorties = sorties_verifiees(COURSE, liaison(doc), NOW)
        self.assertIsNone(detecter_crack(sorties, 250_000))
        self.assertIsNone(detecter_haut_potentiel(sorties, 5))

    def test_prevision_source_sheets_et_retrait(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            day = COURSE['date']
            sauver(cache / f'sources_pmu/programme_{day}.json', {'programme': [COURSE]})
            chevaux = [{'numPmu': i, 'nom': f'Cheval {i}', 'musique': '1a2a3a',
                        'nonPartant': False, 'age': 5,
                        'gainsParticipant': {'gainsCarriere': 25_000_000}}
                       for i in range(1, 5)]
            fichier_partants = cache / f'partants_actuels/{day}_R1C1.json'
            fichier_direct = cache / f'pronostics/{day}_R1C1_direct.json'
            sauver(fichier_partants, {'chevaux': {str(i): {'nom': f'Cheval {i}', 'statut_np': 'PARTANT'}
                                                 for i in range(1, 5)}})
            liens = {'3': liaison(historique()), '4': liaison(historique(True))}
            with patch('pmu_geny.liaison_chevaux_v22.etablir', return_value=liens), \
                 patch('pmu_geny.formes_contextuelles_v32.noter_partant', return_value={
                     'score': 3, 'source_forme': 'TEST', 'qualite': 'TEST',
                     'musique_exploitable': 1, 'historique_exploitable': 0}):
                calculer(cache, COURSE, {'participants': chevaux}, NOW)
                doc = lire(fichier_direct)
                self.assertEqual([h['numero'] for h in doc['top3']], [4, 3, 1])
                self.assertEqual(doc['version_profils'], 'trot-attele-v2')
                self.assertEqual(doc['profils_partants']['4']['gains_carriere_euros'], 250_000)
                self.assertIsNotNone(doc['profils_partants']['4']['haut_potentiel'])
                lignes = {row['numero']: row for row in source_rows(cache)['Courses & Prévisions'].values()}
                self.assertEqual(lignes['4']['profil_partant'], 'Crack')
                self.assertEqual(lignes['3']['profil_partant'], 'Haut potentiel')
                self.assertIn('250 000 €', lignes['4']['profil_partant_indices'])
                self.assertIn('Groupe I–III', lignes['3']['profil_partant_indices'])
                self.assertEqual(lignes['1']['profil_partant'], '')
                # Un statut NP reçu entre deux calculs efface aussi le format.
                publication = lire(fichier_partants)
                publication['chevaux']['4']['statut_np'] = 'NON_PARTANT'
                sauver(fichier_partants, publication)
                lignes = {row['numero']: row for row in source_rows(cache)['Courses & Prévisions'].values()}
                self.assertEqual(lignes['4']['profil_partant'], '')
                chevaux[3]['nonPartant'] = True
                calculer(cache, COURSE, {'participants': chevaux}, NOW + timedelta(minutes=15))
                self.assertEqual([h['numero'] for h in lire(fichier_direct)['top3']], [3, 1, 2])
                self.assertTrue(list((cache / 'pronostics/versions').glob('*_direct_*.json')))
                avant = fichier_direct.read_bytes()
                calculer(cache, COURSE, {'participants': chevaux}, NOW + timedelta(hours=2))
                self.assertEqual(fichier_direct.read_bytes(), avant)


class TestMiseEnForme(unittest.TestCase):
    def test_formules_formats_idempotence_et_nouvelles_lignes(self):
        class Session(SheetsSession):
            def __init__(self):
                super().__init__()
                self.rules = []
                self.lignes = 100
                self.ecritures_formats = 0

            def get(self, url, **kwargs):
                response = super().get(url, **kwargs)
                for sheet in response.data.get('sheets', []):
                    if sheet['properties']['title'] == 'Courses & Prévisions':
                        sheet['conditionalFormats'] = self.rules.copy()
                        sheet['properties']['gridProperties']['rowCount'] = self.lignes
                return response

            def post(self, url, **kwargs):
                if url.endswith(':batchUpdate') and 'requests' in kwargs['json']:
                    for request in kwargs['json']['requests']:
                        item = request.get('addConditionalFormatRule')
                        if item:
                            self.rules.insert(item['index'], item['rule'])
                            self.ecritures_formats += 1
                        item = request.get('updateConditionalFormatRule')
                        if item:
                            self.rules[item['index']] = item['rule']
                            self.ecritures_formats += 1
                    return Response({})
                if url.endswith(':append'):
                    self.lignes += len(kwargs['json']['values'])
                return super().post(url, **kwargs)

        tab = 'Courses & Prévisions'
        session = Session()
        session.tables[tab] = [['course_key', 'numero', 'Cheval'], ['k', '1', 'Étoile']]
        source = {tab: {'k|1': {'course_key': 'k', 'numero': '1', 'profil_partant': 'Crack'}}}
        with tempfile.TemporaryDirectory() as tmp:
            engine = SynchroniseurSheets(Path(tmp), 'test', session=session)
            engine.synchroniser_tables(source, scope='TEST', allow_structure=True)
            engine.synchroniser_tables(source, scope='TEST', allow_structure=True)
            self.assertEqual(session.ecritures_formats, 2)
            session.tables[tab].extend([[''] for _ in range(98)])
            source[tab]['k|2'] = {'course_key': 'k', 'numero': '2', 'cheval': 'Junior',
                                  'profil_partant': 'Haut potentiel'}
            engine.synchroniser_tables(source, scope='TEST', allow_structure=True)
            self.assertEqual(session.ecritures_formats, 4)
            engine.synchroniser_tables(source, scope='TEST', allow_structure=True)
            self.assertEqual(session.ecritures_formats, 4)
        self.assertEqual(len(session.rules), 2)
        self.assertEqual(session.tables[tab][1][3], 'Crack')
        for rule, statut in zip(session.rules, ('Crack', 'Haut potentiel')):
            self.assertEqual([r['startColumnIndex'] for r in rule['ranges']], [2, 3])
            self.assertEqual([r['endRowIndex'] for r in rule['ranges']], [101, 101])
            condition = rule['booleanRule']['condition']
            self.assertEqual(condition['values'][0]['userEnteredValue'], f'=$D2="{statut}"')
            self.assertTrue(rule['booleanRule']['format']['textFormat']['bold'])
