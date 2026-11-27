from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmu_geny import historiques_incrementaux as inc
from pmu_geny import recensement_historiques as recensement


class RecensementTests(unittest.TestCase):
    def test_examine_le_perimetre_et_reprend_apres_pause_sans_rejouer(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            jour = '2026-10-01'
            inc.ecrire(cache/'sources_pmu'/f'programme_{jour}.json', {'programme': [
                {'code': 'R1C1', 'hippodrome': 'Paris-Vincennes', 'nombre_declares': 3},
                {'code': 'R2C1', 'hippodrome': 'Autre', 'nombre_declares': 1},
            ]})
            inc.ecrire(cache/'partants_actuels'/f'{jour}_R1C1.json', {'chevaux': {
                '1': {'nom': 'Premier', 'statut_np': 'PARTANT'},
                '2': {'nom': 'Deuxieme', 'statut_np': 'PARTANT'},
                '3': {'nom': 'Retire', 'statut_np': 'NON_PARTANT'},
            }})
            hors_perimetre = f'{jour}_R2C1_1'
            inc.ecrire(cache/inc.QUEUE, {'version': 1, 'chevaux': {
                hors_perimetre: {'nom': 'Autre', 'sync': 'A_FAIRE'},
            }})
            essais = []

            def collecte(horse, _):
                essais.append(horse['nom'])
                if horse['nom'] == 'Premier':
                    return {'statut': 'ACCES_LIMITE_429'}
                return {'complet': True}

            def accepter(_, horse, __, *, origine):
                horse.update(id='12345', collecte='COMPLET', sync='A_FAIRE',
                             historique_complet_au_utc=datetime.now(timezone.utc).isoformat())

            def sync(_):
                return {'Historique chevaux': {'controle': {'statut': 'VALIDE'}, 'lignes_ajoutees': 2}}

            options = {'max_minutes': None, 'perimetre': (jour, 'Vincennes'), 'collect': collecte, 'sync': sync}
            with patch.object(inc, 'accepter', accepter):
                premier = inc.run(cache, **options)
                self.assertEqual(premier['motif_fin_passage'], 'COOLDOWN')
                self.assertEqual(premier['chevaux'][f'{jour}_R1C1_1']['motif'], 'ACCES_LIMITE_429')
                self.assertEqual(premier['bilan']['statuts'],
                                 {'REFUS_GENY': 1, 'A_EXAMINER': 1, 'NON_PARTANT': 1})
                etat = inc.lire(cache/inc.QUEUE)
                etat.pop('prochain_acces_geny_utc')
                inc.ecrire(cache/inc.QUEUE, etat)
                inc.ecrire(cache/'etat_persistant.json', {'dernier_blocage_geny': {
                    'code': '429', 'utc': (datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()}})
                deuxieme = inc.run(cache, **options)
                self.assertEqual(deuxieme['motif_fin_passage'], 'RECENSEMENT_TERMINE')
                self.assertEqual(deuxieme['bilan']['statuts'], {'REFUS_GENY': 1, 'PUBLIE': 1, 'NON_PARTANT': 1})
                self.assertEqual(deuxieme['chevaux'][f'{jour}_R1C1_2']['performances_ajoutees'], 2)
                self.assertEqual(inc.run(cache, **options)['bilan'], deuxieme['bilan'])
                self.assertEqual(essais, ['Premier', 'Deuxieme'])
                self.assertEqual(inc.lire(cache/inc.QUEUE)['chevaux'][hors_perimetre]['sync'], 'A_FAIRE')
                chemin, _ = recensement.ouvrir(cache, jour, 'Vincennes')
                self.assertTrue((cache/chemin).is_file())
