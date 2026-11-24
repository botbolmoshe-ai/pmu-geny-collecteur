import unittest
from datetime import datetime

from pmu_geny.signaux_geny import candidat_classement, signaux


class SignauxGenyTests(unittest.TestCase):
    def setUp(self):
        self.observation = datetime.fromisoformat('2026-11-14T10:00:00+01:00')
        self.course = {'depart': '2026-11-14T14:00:00+01:00', 'discipline': 'Monté',
                       'hippodrome': 'Vincennes', 'distance_m': 2175, 'allocation_eur': 46000,
                       'parametres_pmu': {'parcours': 'Grande piste', 'typeDepart': 'Autostart'}}
        self.history = {'extrait_utc': '2026-11-14T08:00:00+01:00',
                        'source_url': 'https://www.geny.com/cheval/123',
                        'performances': [
                            self.performance('2026-11-01', 1),
                            self.performance('2026-11-02', 2),
                            self.performance('2026-11-14', 1),
                        ]}
        self.link = {'cheval_id': '123', 'methode': 'NOM_EXACT_UNIQUE', 'historique': self.history}

    def performance(self, day, rank):
        return {'date': day, 'classement': str(rank), 'discipline': 'Monté',
                'hippodrome': 'Vincennes', 'distance_m': 2175,
                'texte_source': f"{day[-2:]}/11/26 | Vincennes | Monté | 2 175 | GP | G | Auto | Dur | "
                                f"Crse D | 46 000 € | A. Gendrot | 1'13''0 | 6.5 | {rank} | e"}

    def test_signals_use_only_proven_earlier_rows(self):
        actual = signaux(self.course, {'driver_jockey': 'A Gendrot'}, self.link, self.observation)
        self.assertEqual(actual, {
            'geny_forme_parcours': 4.25, 'geny_forme_autostart': 4.25,
            'geny_forme_tandem': 4.25, 'geny_chrono_parcours': 73.0, 'geny_forme_niveau': 4.25,
        })

    def test_future_capture_and_ambiguous_dates_are_excluded(self):
        self.history['extrait_utc'] = '2026-11-14T11:00:00+01:00'
        self.assertEqual(signaux(self.course, {}, self.link, self.observation), {})
        self.history['extrait_utc'] = '2026-11-14T08:00:00+01:00'
        self.history['performances'].append(self.performance('2026-11-02', 4))
        self.assertEqual(signaux(self.course, {}, self.link, self.observation), {})

    def test_candidate_never_scores_an_unranked_runner(self):
        ranking = [(1, 2.5), (2, 2), (3, 1.9), (4, 1.8)]
        self.assertIsNone(candidat_classement(ranking, {5: {'geny_forme_parcours': 5}}))
        self.assertEqual(candidat_classement(ranking, {
            4: {'geny_forme_parcours': 5},
        })['top3'], [1, 4, 2])
