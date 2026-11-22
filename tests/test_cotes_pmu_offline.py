"""Collecte pré-départ, conservation et publication du marché PMU."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from pmu_geny.auto_v18 import run, save
from pmu_geny.cotes_v19 import calculer_cotes, collecter, dernier_releve
from pmu_geny.kpi_registre import calculer_kpi
from pmu_geny.sync_google_sheets import plan_sheet, source_rows


class CotesPMUTests(TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.cache = Path(folder.name)
        self.now = datetime(2026, 11, 19, 11, tzinfo=timezone.utc)
        self.depart = self.now + timedelta(hours=2)
        self.course = {'code': 'R3C1', 'date': '2026-11-19', 'nom': 'Prix test',
                       'depart': self.depart.isoformat(), 'hippodrome': 'Vincennes',
                       'nombre_declares': 5}
        self.key = '2026-11-19_R3C1'
        self.programme = self.cache / 'sources_pmu/programme_2026-11-19.json'
        self.prediction = self.cache / 'pronostics' / f'{self.key}_cotes.json'

    def participant(self, num, cote=None, *, statut='PARTANT', report=None):
        row = {'numPmu': num, 'nom': f'Cheval {num}', 'statut': statut}
        if cote is not None:
            row['dernierRapportDirect'] = {
                'rapport': cote, 'typePari': 'SIMPLE_GAGNANT', 'typeRapport': 'DIRECT',
                'numPmu1': num, 'dateRapport': int((report or self.now).timestamp() * 1000),
            }
        return row

    def relever(self, rows, now=None):
        return collecter(self.cache, self.course, {'participants': rows}, now or self.now)

    def test_cycle_global_prepare_toutes_les_courses_attendues_de_la_reunion(self):
        extra = {**self.course, 'code': 'R3C2', 'depart': (self.depart + timedelta(minutes=30)).isoformat()}
        participants = {'participants': [{**self.participant(n), 'musique': '1a2a3a'} for n in range(1, 6)]}
        with (
            patch('pmu_geny.auto_v18.programme_diagnostic', return_value=(
                [self.course], {'courses_jalons': [self.course, extra]})),
            patch('pmu_geny.auto_v18.get_json', side_effect=[{}, participants, participants]) as fetch,
            patch('pmu_geny.contexte_meteo_v20.collecter_meteo', return_value='TEST') as meteo,
            patch('pmu_geny.sources_experts_v23.collecter', return_value='TEST') as experts,
            patch('pmu_geny.historiques_incrementaux.alimenter'),
            patch('builtins.print'),
        ):
            run(self.cache, self.course['date'], [], 0, max_discoveries=0, now=self.now, production=True)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(meteo.call_count, 1)
        self.assertEqual(experts.call_count, 1)
        for code in (self.course['code'], extra['code']):
            self.assertTrue((self.cache/'pronostics'/f"{self.course['date']}_{code}_direct.json").exists())

    def test_cache_partiel_conserve_les_cotes_et_leurs_dates(self):
        first = [self.participant(i, i + 1) for i in range(1, 6)]
        self.assertEqual(self.relever(first), 'COTES_RELEVEES')
        later = self.now + timedelta(minutes=5)
        self.relever(first, later)
        self.assertEqual(len(dernier_releve(self.cache, self.course)['releves']), 1)
        self.relever([self.participant(1, 18, report=later), self.participant(2)], later + timedelta(seconds=1))
        doc = dernier_releve(self.cache, self.course)
        self.assertEqual([x['cote'] for x in doc['chevaux']], [18, 3, 4, 5, 6])
        self.assertEqual(doc['chevaux'][1]['heure_utc'], self.now.isoformat())
        self.assertEqual(collecter(self.cache, self.course, None, later + timedelta(minutes=1)), 'COTES_CONSERVEES')
        self.assertEqual(dernier_releve(self.cache, self.course), doc)
        self.assertFalse(list(self.cache.rglob('*.lock')))
        self.assertEqual(calculer_cotes(self.cache, self.course, later + timedelta(minutes=1)), 'CALCULE_COMPLET')

    def test_rapport_futur_ou_ancien_et_retrait(self):
        first = [self.participant(i, i) for i in range(1, 6)]
        self.relever(first)
        calculer_cotes(self.cache, self.course, self.now)
        later = self.now + timedelta(minutes=5)
        self.relever([
            self.participant(1, 1, statut='NON_PARTANT'),
            self.participant(2, 60, report=self.now - timedelta(seconds=1)),
            self.participant(3, 50, report=later + timedelta(seconds=1)),
        ], later)
        self.assertEqual(calculer_cotes(self.cache, self.course, later), 'CALCULE_COMPLET')
        from pmu_geny.auto_v18 import load
        selected = load(self.prediction)['top3']
        self.assertEqual([(x['numero'], x['cote']) for x in selected], [(2, 2), (3, 3), (4, 4)])
        archive, = (self.cache / 'pronostics/versions').glob('*_cotes_*.json')
        self.assertEqual(load(archive)['top3'][0]['numero'], 1)
        before = self.prediction.read_bytes()
        self.assertEqual(self.relever(first, self.depart), 'APRES_DEPART_SANS_RELEVE')
        self.assertEqual(calculer_cotes(self.cache, self.course, self.depart), 'APRES_DEPART')
        self.assertEqual(self.prediction.read_bytes(), before)

    def test_source_sheets_independante_et_top3_partiel(self):
        save(self.programme, {'programme': [self.course]})
        self.relever([self.participant(1, 4), self.participant(2, 2), self.participant(3, 6),
                      self.participant(4), self.participant(5, statut='NON_PARTANT')])
        source = source_rows(self.cache)
        tab = 'Courses & Prévisions'
        rows = source[tab]
        headers, changes, values = plan_sheet(['course_key', 'numero'], [], rows, tab)
        self.assertEqual(changes, [])
        self.assertEqual(len(values), 5)
        self.assertEqual([row[headers.index('top3_cotes_valeur')] for row in values], [4.0, 2.0, 6.0, '', ''])
        self.assertTrue(all(not row.get('top3_cotes_top3') for row in rows.values()))
        self.assertEqual(calculer_cotes(self.cache, self.course, self.now), 'CALCULE_PARTIEL')
        source = source_rows(self.cache)
        published = list(source[tab].values())
        self.assertEqual([row.get('top3_cotes_rang') for row in published], [2, 1, 3, '', ''])
        self.assertEqual(published[0]['top3_cotes_statut'], 'PARTIEL')
        kpis = calculer_kpi(self.cache, source, self.now)
        self.assertEqual(kpis['Cotes PMU · Chevaux éligibles'][0], 4)
        self.assertEqual(kpis['Cotes PMU · Cotes manquantes'][0], 1)
        self.assertEqual(kpis['Cotes PMU · Taux de couverture'][0], 0.75)
        self.assertEqual(kpis['Cotes PMU · Taux de TOP3 complets'][0], 0)

    def test_un_appel_participants_et_publication_malgre_un_echec_enrichissement(self):
        raw = {'participants': [self.participant(i, i) for i in range(1, 6)]}
        with patch('pmu_geny.auto_v18.get_json', side_effect=[{}, raw]) as api, \
             patch('pmu_geny.auto_v18.programme_diagnostic', return_value=([self.course], {})), \
             patch('pmu_geny.partants_actuels_v21.enregistrer', side_effect=ValueError('profil indisponible')), \
             patch('pmu_geny.top3_independants_v22.calculer', side_effect=ValueError('direct indisponible')), \
             patch('pmu_geny.contexte_meteo_v20.collecter_meteo', return_value='TEST'), \
             patch('pmu_geny.sources_experts_v23.collecter', return_value='TEST'), \
             patch('pmu_geny.historiques_incrementaux.alimenter'), patch('builtins.print'):
            state = run(self.cache, self.course['date'], [], 0, max_discoveries=0, now=self.now)
        self.assertEqual(api.call_count, 2)
        self.assertTrue(api.call_args.args[0].endswith('/R3/C1/participants'))
        self.assertEqual(state['courses']['R3C1']['statut_top3_cotes'], 'CALCULE_COMPLET')
        self.assertEqual(len(source_rows(self.cache)['Courses & Prévisions']), 5)
