from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from pmu_geny import historiques_incrementaux as inc
from pmu_geny import resolution_identites_courses as resolution
from pmu_geny.identites_chevaux import IndexGeny


class ResolutionCoursesTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = Path(tmp.name)
        self.now = datetime(2026, 11, 17, 0, 12, tzinfo=timezone.utc)
        self.state = {'chevaux': {}}
        self.checkpoint = Mock()
        self.clock = lambda: self.now

    def course(self, index, names, *, mapped=True):
        engagement = f'2026-11-16_R1C{index}'
        ident = str(1698700+index)
        source = {'source': 'PMU_API_PARTICIPANTS', 'chevaux': {}}
        for number, name in enumerate(names, 1):
            number = str(number)
            target = {'engagement': engagement, 'numero': number, 'nom': name}
            self.state['chevaux'][f'{engagement}_{number}'] = target
            source['chevaux'][number] = {'nom': name}
        inc.ecrire(self.cache/'partants_actuels'/f'{engagement}.json', source)
        if mapped:
            path = self.cache/'orchestration/correspondances_geny.json'
            mapping = inc.lire(path)
            mapping[engagement] = f'GENY-{ident}'
            inc.ecrire(path, mapping)
        return engagement

    def reply(self, course):
        horses = {n: {'nom': name, 'id': str(23000+int(n)),
                      'url_geny': f'https://www.geny.com/cheval/{23000+int(n)}'}
                  for n, name in course['partants'].items()}
        return {'statut': 'PAGE_LUE', 'preuve':{'http': 200,
                'engagement': course['engagement'], 'source_url': course['url'],
                'course_geny_id': course['id'], 'capture_utc': self.now.isoformat(),
                'chevaux': horses}}

    def run_passage(self, collect, stop=lambda: None):
        return resolution.passage(self.cache, self.state, stop_requested=stop,
                                  checkpoint=self.checkpoint, collect=collect, now=self.clock)

    def test_une_page_confirme_plusieurs_identites_et_priorise_la_course_la_plus_dense(self):
        self.course(1, ['Opale'])
        expected = self.course(2, ['Orion', 'Océane'])
        self.course(3, ['Ouragan'], mapped=False)
        collect = Mock(side_effect=self.reply)
        self.assertTrue(self.run_passage(collect))
        collect.assert_called_once()
        self.assertEqual(collect.call_args.args[0]['engagement'], expected)
        pilot = inc.lire(self.cache/resolution.PILOTE)
        self.assertEqual(pilot['identites_confirmees'], 2)
        self.assertEqual(pilot['exclusions_inventaire'], {'COURSE_GENY_A_RAPPROCHER': 1})
        self.checkpoint.assert_called_once()
        index = IndexGeny(self.cache)
        self.assertEqual(index.resoudre('Orion', 'GENY-1698702', 1)[0]['id'], '23001')
        self.assertEqual(index.resoudre('Océane', 'GENY-1698702', 2)[0]['id'], '23002')
        self.assertFalse((self.cache/'historiques').exists())

    def test_conflit_et_absence_ne_deviennent_pas_des_preuves(self):
        engagement = self.course(1, ['Opale', 'Orion', 'Océane', 'Ouragan'])
        def collect(course):
            result = self.reply(course)
            horses = result['preuve']['chevaux']
            horses['2']['nom'] = 'Orme'
            horses['3']['id'] = horses['1']['id']
            del horses['4']
            return result
        self.assertTrue(self.run_passage(collect))
        self.assertFalse((self.cache/'sources_geny/liens'/f'{engagement}.json').exists())
        result = inc.lire(self.cache/resolution.PILOTE)['courses'][engagement]
        self.assertEqual(set(result['conflits']), {'1', '2', '3'})
        self.assertEqual(result['numeros_sans_lien'], ['4'])

    def test_403_partage_la_pause_et_la_file_reprend_sans_plafond(self):
        engagement = self.course(1, ['Opale'])
        refused = Mock(return_value={'statut': 'ACCES_REFUSE_403'})
        self.assertTrue(self.run_passage(refused))
        journal = inc.lire(self.cache/'etat_persistant.json')
        self.assertEqual(journal['dernier_blocage_geny']['code'], '403')
        self.assertEqual(inc.instant(self.state['prochain_acces_geny_utc']), self.now+timedelta(minutes=30))
        self.assertFalse(self.run_passage(refused, stop=lambda: 'COOLDOWN_GENY_GLOBAL'))
        others = [self.course(n, [f'Cheval {n}']) for n in range(2, 14)]
        self.assertFalse(self.run_passage(refused))
        self.now += timedelta(minutes=31)
        read = Mock(side_effect=self.reply)
        self.assertTrue(self.run_passage(read))
        self.assertEqual(read.call_args.args[0]['engagement'], min(others))
        pilot = inc.lire(self.cache/resolution.PILOTE)
        self.assertEqual(set(pilot['courses']), {engagement, *others})
        self.assertEqual(pilot['courses'][engagement]['statut'], 'DIFFERE_REFUS_GENY')
        self.assertEqual(pilot['statut'], 'EN_COURS')
        refused.assert_called_once()

    def test_page_publique_lue_une_fois_et_redirection_vers_autre_course_refusee(self):
        self.course(1, ['Opale'])
        course = resolution.inventaire(self.cache, self.state)[0][0]
        page = Mock(url=course['url'].replace('1698701', '1698702'))
        page.goto.return_value.status = 200
        page.content.return_value = '<html></html>'
        page.title.return_value = 'Geny'
        page.locator.return_value.inner_text.return_value = ''
        self.assertEqual(resolution.lire_page(course, page=page)['statut'], 'COURSE_GENY_NON_CONFIRMEE')
        page.goto.assert_called_once()
