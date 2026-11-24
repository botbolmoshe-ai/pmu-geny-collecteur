import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pmu_geny import echeances_production as production
from pmu_geny import historiques_incrementaux as incremental
from pmu_geny import rattrapage_historiques as rattrapage
from pmu_geny.cadence_geny import CadenceGeny, reprise_serveur
from pmu_geny.historique_individuel import observer_http_geny


class CadenceTest(unittest.TestCase):
    def setUp(self):
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.cache = Path(temporaire.name)
        self.now = datetime(2026, 11, 24, 10, tzinfo=timezone.utc)

    def test_reservation_survit_a_un_arret_entre_deux_runners(self):
        CadenceGeny(self.cache).reserver(self.now)
        suivant = CadenceGeny(self.cache)
        self.assertGreaterEqual(suivant.delai(self.now + timedelta(seconds=240)), 30)
        suivant.terminer(self.now + timedelta(seconds=240))
        self.assertEqual(CadenceGeny(self.cache).delai(self.now + timedelta(seconds=269)), 1)
        self.assertEqual(CadenceGeny(self.cache).delai(self.now + timedelta(seconds=270)), 0)

    def test_retry_after_precede_la_reprise_a_60_puis_30(self):
        reprise = self.now + timedelta(hours=2)
        incremental.suspendre_geny(self.cache, {}, self.now, '429', reprise.isoformat())
        self.assertEqual(production.pause_geny_active(self.cache, self.now + timedelta(minutes=31)), reprise)
        self.assertIsNone(production.pause_geny_active(self.cache, reprise))

        for index in range(4):
            CadenceGeny(self.cache).terminer(reprise + timedelta(minutes=index), valide=True)
        CadenceGeny(self.cache).terminer(reprise + timedelta(minutes=4), valide=False)
        for index in range(9):
            CadenceGeny(self.cache).terminer(reprise + timedelta(minutes=5 + index), valide=True)
            self.assertEqual(CadenceGeny(self.cache).intervalle, 60)
        dixieme = reprise + timedelta(minutes=14)
        CadenceGeny(self.cache).terminer(dixieme, valide=True)
        self.assertEqual(CadenceGeny(self.cache).delai(dixieme), 30)

    def test_compte_les_requetes_reelles_et_les_indications_serveur(self):
        callbacks = {}
        context = SimpleNamespace(on=lambda event, action: callbacks.update({event: action}))
        mesure = observer_http_geny(context, self.cache)
        for url in ('https://www.geny.com/cheval/1234', 'https://media.geny.com/a.png',
                    'https://example.org/tiers', 'https://notgeny.com/tiers'):
            callbacks['request'](SimpleNamespace(url=url))
        response = SimpleNamespace(url='https://www.geny.com/cheval/1234', status=429,
                                   header_value=Mock(return_value='7200'))
        callbacks['response'](response)
        callbacks['response'](SimpleNamespace(url='https://media.geny.com/a.png', status=403,
                                              header_value=Mock(return_value='5')))
        self.assertEqual(mesure['requetes'], 2)
        self.assertEqual(mesure['reponses_refusees'], {'403': 1, '429': 1})
        self.assertGreater(production.instant(mesure['reprise_au_plus_tot_utc']),
                           datetime.now(timezone.utc) + timedelta(minutes=119))
        self.assertEqual(incremental.lire(self.cache / 'http_geny.json'), mesure)
        self.assertEqual(reprise_serveur('Tue, 24 Nov 2026 12:00:00 GMT', self.now),
                         self.now + timedelta(hours=2))
        self.assertIsNone(reprise_serveur('invalide', self.now))

    def test_deux_files_partagent_la_cadence_et_cedent_a_pmu_avant_nouvel_acces(self):
        base = {'chevaux': {'premier': {'nom': 'Premier'}, 'suivant': {'nom': 'Suivant'}}}
        heure = self.now
        monotone = 0.0
        acces = []

        def avancer(secondes):
            nonlocal heure, monotone
            heure += timedelta(seconds=secondes)
            monotone += secondes

        def collecter(horse, out):
            acces.append((horse['nom'], heure))
            avancer(2)
            return {'statut': 'INCOMPLET'}

        def premier_choix(state, now, attempts):
            return ('premier', 'COLLECTE') if not attempts else (None, 'TERMINE')

        def suivant(state, now, attempts):
            return ('suivant', 'COLLECTE') if not attempts else (None, 'TERMINE')

        def file_neuve(*args):
            return {'chevaux': {key: dict(value) for key, value in base['chevaux'].items()}}

        def checkpoint(cache):
            if not acces:
                self.assertGreater(CadenceGeny(cache).delai(heure), 0)

        with patch.object(incremental, 'datetime', Mock(wraps=datetime, now=lambda tz: heure)), \
             patch.object(incremental.time, 'monotonic', side_effect=lambda: monotone), \
             patch.object(incremental.time, 'sleep', side_effect=avancer), \
             patch.object(incremental, 'alimenter', side_effect=file_neuve), \
             patch.object(incremental, 'materialiser_manifestes'), \
             patch.object(incremental, 'prochaine_tache', side_effect=premier_choix), \
             patch.object(rattrapage, 'preparer', side_effect=file_neuve), \
             patch.object(rattrapage, 'bilan', return_value=dict.fromkeys((
                 'contextes_distincts_sans_identifiant', 'noms_distincts_sans_identifiant',
                 'identifiants_sans_carriere_complete'), 0)), \
             patch.object(rattrapage, 'prochaine_tache', side_effect=suivant), \
             patch.object(rattrapage, 'cle_travail_geny', return_value='suivant'), \
             patch.object(rattrapage, 'preparer_noms_passes'), \
             patch.object(rattrapage, 'persister_etat'), \
             patch.object(rattrapage, 'rapport', return_value={}):
            incremental.run(self.cache, collect=collecter, cadence_geny=True,
                            checkpoint=lambda cache: checkpoint(cache) if (cache / 'etat_persistant.json').exists() else None)
            arret = incremental.run(self.cache, mode='rattrapage', collect=collecter, cadence_geny=True,
                                    stop_requested=lambda: 'ECHEANCE_PMU_PRIORITAIRE' if monotone >= 12 else None)
            self.assertEqual(arret['motif_fin_passage'], 'ECHEANCE_PMU_PRIORITAIRE')
            self.assertEqual(len(acces), 1)
            incremental.run(self.cache, mode='rattrapage', collect=collecter, cadence_geny=True)

        self.assertEqual(acces, [('Premier', self.now), ('Suivant', self.now + timedelta(seconds=32))])
