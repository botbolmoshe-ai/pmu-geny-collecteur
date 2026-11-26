"""Identification durable indépendante de la disponibilité d'une carrière."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from pmu_geny import historiques_incrementaux as inc
from pmu_geny import rattrapage_historiques as back
from pmu_geny.historique_individuel import candidats_recherche, rechercher
from pmu_geny.liaison_chevaux_v22 import etablir


class IdentificationGenyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.cache = Path(temporary.name)
        self.now = datetime.now(timezone.utc)
        self.horse = {'nom': 'Étoile du Nord', 'id': '123456', 'numero': 1,
                      'url_geny': 'https://www.geny.com/cheval/123456-etoile-du-nord'}

    def test_manifest_without_career_identifies_existing_engagements(self):
        inc.ecrire(self.cache/'manifestes/GENY-1234.json', {'courses': [
            {'course_id': 'GENY-1234', 'partants': [self.horse]}]})
        inc.ecrire(self.cache/back.INVENTAIRE, {'capture_utc': self.now.isoformat(), 'chevaux': []})
        engagements = ('2020-01-01_R1C1', '2020-01-02_R1C2')
        inc.ecrire(self.cache/back.QUEUE, {'version': 1, 'inventaire_id': 'fige',
                   'chevaux': {race: {'nom': 'ETOILE DU NORD', 'numero': '7', 'engagement': race}
                               for race in engagements}})
        state = back.preparer(self.cache, self.now)
        self.assertEqual(state['bilan']['noms_distincts_sans_identifiant'], 0)
        self.assertEqual(state['bilan']['contextes_distincts_sans_identifiant'], 0)
        self.assertEqual(state['bilan']['identifiants_sans_carriere_complete'], 1)
        for race in engagements:
            self.assertEqual(state['chevaux'][race]['id'], '123456')
            self.assertEqual(state['chevaux'][race]['engagement'], race)
            self.assertEqual(state['chevaux'][race]['numero'], '7')
            self.assertNotIn('historique_complet_au_utc', state['chevaux'][race])
        links = etablir(self.cache, {'date': '2020-01-02', 'code': 'R1C2'},
                        [{'numero': 7, 'nom': 'Étoile-du-Nord'}])
        self.assertEqual(links['7']['cheval_id'], '123456')
        self.assertEqual(links['7']['historique'], {})

    def test_identity_is_persisted_and_shared_when_career_request_gets_429(self):
        inc.ecrire(self.cache/back.INVENTAIRE, {'capture_utc': self.now.isoformat(), 'chevaux': [
            {'nom': self.horse['nom'], 'numero': '1', 'engagement': '2020-01-01_R1C1'},
            {'nom': 'ETOILE DU NORD', 'numero': '8', 'engagement': '2020-01-02_R1C2'},
        ]})
        geny = {**self.horse, 'preuve': 'RECHERCHE_GENY_NOM_EXACT'}

        def collect(horse, out):
            inc.ecrire(out/'resolution_geny.json', {'geny': geny, 'preuve': geny['preuve'],
                       'nom_attendu': horse['nom'], 'numero': str(horse['numero']),
                       'engagement': horse['engagement'], 'resolution_utc': self.now.isoformat()})
            return {'geny': geny, 'statut': 'ACCES_LIMITE_429'}

        with patch.object(inc, 'Path', wraps=Path) as path:
            path.side_effect = lambda p: self.cache/'resultats' if p == 'resultats/incremental' else Path(p)
            result = inc.run(self.cache, mode='rattrapage', collect=collect)
        self.assertEqual({h['id'] for h in result['chevaux'].values()}, {'123456'})
        self.assertEqual(result['motif_fin_passage'], 'COOLDOWN')
        self.assertEqual(result['bilan']['cibles_completees'], 0)
        self.assertEqual(len(list((self.cache/'sources_geny/identites').glob('*.json'))), 1)
        link = etablir(self.cache, {'date': '2020-02-02', 'code': 'R1C1'}, [self.horse])
        self.assertEqual(link['1']['cheval_id'], '123456')
        self.assertEqual(link['1']['historique'], {})

    def test_timeout_after_identification_keeps_published_proof(self):
        from subprocess import TimeoutExpired

        inc.ecrire(self.cache/back.INVENTAIRE, {'capture_utc': self.now.isoformat(), 'chevaux': [
            {'nom': self.horse['nom'], 'numero': '1', 'engagement': '2020-01-01_R1C1'},
        ]})

        def collect(horse, out):
            proof = 'RECHERCHE_GENY_NOM_EXACT'
            inc.ecrire(out/'resolution_geny.json', {'geny': {**self.horse, 'preuve': proof},
                       'preuve': proof, 'nom_attendu': horse['nom'], 'numero': str(horse['numero']),
                       'engagement': horse['engagement'], 'resolution_utc': self.now.isoformat()})
            raise TimeoutExpired('historique_individuel', 240)

        output = self.cache/'resultats'
        with patch.object(inc, 'Path', side_effect=lambda p: output if p == 'resultats/incremental' else Path(p)), \
                patch.object(inc.time, 'sleep'):
            state = inc.run(self.cache, mode='rattrapage', collect=collect)
        horse = next(iter(state['chevaux'].values()))
        self.assertEqual(horse['id'], '123456')
        self.assertEqual(horse['collecte'], 'A_REPRENDRE')
        self.assertEqual(state['bilan']['identifiants_sans_carriere_complete'], 1)
        self.assertEqual(len(list((self.cache/'sources_geny/identites').glob('*.json'))), 1)

    def test_retry_is_shared_across_engagements_of_one_confirmed_id(self):
        from datetime import timedelta

        retry = self.now + timedelta(hours=6)
        inc.ecrire(self.cache/back.INVENTAIRE, {'capture_utc': self.now.isoformat(), 'chevaux': []})
        inc.ecrire(self.cache/back.QUEUE, {'version': 1, 'inventaire_id': 'fige', 'chevaux': {
            'old': {**self.horse, 'engagement': '2020-01-01_R1C1', 'prochain_essai_utc': retry.isoformat()},
            'new': {**self.horse, 'engagement': '2020-01-02_R1C2', 'numero': 2},
        }})
        state = back.preparer(self.cache, self.now)
        self.assertEqual(state['chevaux']['new']['prochain_essai_utc'], retry.isoformat())
        self.assertEqual(back.prochaine_tache(state, self.now, {}), (None, 'TERMINE_PASSAGE'))
        self.assertEqual(back.prochaine_tache(state, retry, {})[1], 'COLLECTE')
        self.assertEqual(back.prochaine_tache(state, retry, {('IDENTIFIANT', '123456'): 1}),
                         (None, 'TERMINE_PASSAGE'))

    def test_country_suffix_requires_geny_nationality(self):
        from pmu_geny.liaison_chevaux_v22 import nom_geny_concordant

        self.assertTrue(nom_geny_concordant('JUNKIE (SWE)', {'nom': 'Junkie', 'nationalite_geny': 'SE'}))
        self.assertFalse(nom_geny_concordant('JUNKIE (SWE)', {'nom': 'Junkie', 'nationalite_geny': 'IT'}))
        self.assertFalse(nom_geny_concordant('JUNKIE (SWE)', {'nom': 'Junkie'}))
        links = etablir(self.cache, {'date': '2020-01-01', 'code': 'R1C1'},
                        [{'numero': 12, 'nom': 'JUNKIE (SWE)'}])
        self.assertEqual(links['12']['cheval_id'], '2736204')

    def test_geny_search_checks_exact_query_and_keeps_homonyms(self):
        names = [('123456', 'Étoile du Nord'), ('234567', 'Etoile du Nord'),
                 ('345678', 'Étoile du Nord II')]
        query = {'dehydratedAt': 1, 'queryKey': ['recherche', self.horse['nom']],
                 'state': {'status': 'success', 'data': [
                     {'urlV2': 'cheval/'+ident, 'titre': 'Fiche cheval - '+name, 'type': 'CHEVAL',
                      'resume': f'âge : {age} ans'} for age, (ident, name) in enumerate(names, 4)]}}
        # The hydrated query can follow a length-prefixed text record on the same line.
        flight = '3:T3,abc28:'+json.dumps(query, ensure_ascii=False)
        html = '<script>self.__next_f.push('+json.dumps([1, flight])+')</script>'
        self.assertEqual(set(candidats_recherche(html, self.horse['nom'])), {'123456', '234567'})
        with self.assertRaisesRegex(ValueError, 'NON_INTERPRETABLE'):
            candidats_recherche(html, 'Autre cheval')

        page = Mock(url='https://www.geny.com/recherche?q=Etoile')
        page.goto.return_value.status = 200
        page.content.return_value = html
        with patch('pmu_geny.historique_individuel.diagnostic_acces', return_value=''), \
             patch('pmu_geny.historique_individuel.recherche_autorisee', return_value=True):
            with self.assertRaisesRegex(ValueError, 'NOM_AMBIGU'):
                rechercher(self.horse, page)
            resolved = rechercher({**self.horse, 'annee_naissance_pmu': self.now.year-4}, page)
        self.assertEqual(resolved['id'], '123456')
        self.assertEqual(len(resolved['homonymes']), 2)
        query['state']['data'][0]['resume'] += ', pays : Suède, discipline : Trot'
        flight = '28:'+json.dumps(query, ensure_ascii=False)
        page.content.return_value = '<script>self.__next_f.push('+json.dumps([1, flight])+')</script>'
        with patch('pmu_geny.historique_individuel.diagnostic_acces', return_value=''), \
             patch('pmu_geny.historique_individuel.recherche_autorisee', return_value=True):
            alias = rechercher({'nom': self.horse['nom']+' (SWE)'}, page)
        self.assertEqual(alias['id'], '123456')
        self.assertEqual(alias['nom_pmu'], self.horse['nom']+' (SWE)')
        self.assertNotIn('SWE', page.goto.call_args.args[0])
