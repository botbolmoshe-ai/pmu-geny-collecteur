"""Recette PMU sur 48 heures virtuelles avec pannes aux interfaces réseau."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from pmu_geny import echeances_production as prod
from pmu_geny import rapprochement_reunions as resultats
from pmu_geny.moteur_sheets import ErreurSynchronisation
from pmu_geny.sync_google_sheets import DISPLAY_NAMES, publier_plan, source_rows


class Recette48h(TestCase):
    def test_collision_reprise_et_interdiction_de_certifier_sans_relecture(self):
        with TemporaryDirectory() as tmp:
            cache = Path(tmp)
            origine = datetime(2026, 11, 23, tzinfo=timezone.utc)
            jours = [origine + timedelta(days=i) for i in range(2)]
            trace = []
            for jour in jours:
                date = jour.date().isoformat()
                courses = [
                    {'date': date, 'code': f'R{reunion}C{n}', 'hippodrome': 'Vincennes',
                     'depart': (jour + timedelta(hours=h, minutes=m)).isoformat(),
                     'podium_definitif_pmu': [1, 2, 3]}
                    for reunion, n, h, m in [(1, 1, 9, 30), (1, 2, 10, 0), (2, 1, 12, 34)]
                ]
                prod.sauver(cache/'sources_pmu'/f'programme_{date}.json',
                            {'programme': courses, 'inventaire_reunions': courses,
                             'date_controle_utc': (jour - timedelta(hours=2)).isoformat()})
                collision = jour + timedelta(hours=10, minutes=30)
                self.assertNotIn(f'{date}_R1', {r['reunion'] for r in
                                 resultats.planifier_rapprochements(cache, collision-timedelta(seconds=1))})
                plan = prod.planifier(cache, collision)
                self.assertEqual(plan['mode'], 'JALONS')
                self.assertEqual(plan['selection'], ['R2C1'])
                self.assertIn(f'{date}_R1', {r['reunion'] for r in plan['rapprochements_dus']})
                # Le plan rafraîchi après acquisition peut manquer l'obligation initiale.
                plan_path = cache/'plan.json'
                prod.sauver(plan_path, {**plan, 'rapprochements_dus': []})
                podium = {'participants': [{'numPmu': n, 'ordreArrivee': n} for n in (1, 2, 3)]}
                with patch('pmu_geny.auto_v18.programme_diagnostic', return_value=(
                        [], {'inventaire_reunions': courses})), patch(
                        'pmu_geny.auto_v18.get_json', side_effect=[{}, podium, podium]):
                    plan = resultats.rattraper_obligations(cache, plan_path, lambda: collision)
                path = cache/'rapprochements'/f'{date}_R1.json'
                self.assertEqual(prod.lire(path)['statut'], 'COMPLET')
                engine = Mock(cache=cache)
                engine.metadata.return_value = {'Résultats & Analyse': {}}
                engine.source.return_value = source_rows(cache)
                expected = engine.source.return_value['Résultats & Analyse']
                rows = [row for row in expected.values() if row.get('reunion_pmu') == f'{date}_R1']
                self.assertEqual(len(rows), 2)
                headers = ['course_key', 'reunion_pmu', 'rapprochement_statut',
                           'rapprochement_arrivee_statut', 'rapprochement_declenchement_utc', 'jalon_compare']
                table = [[DISPLAY_NAMES.get(field, field) for field in headers],
                         *[[row.get(field, '') for field in headers] for row in rows]]
                with patch('pmu_geny.sync_google_sheets.lire_feuille_complete', return_value=table[:-1]):
                    with self.assertRaises(ErreurSynchronisation):
                        publier_plan(engine, plan)
                failed = prod.enregistrer_publication(cache, collision, plan, False)
                self.assertFalse(failed['publication_reussie'])
                self.assertNotIn('publication_sheets_utc', prod.lire(path))
                # Nouveau runner après 60 minutes de ticks manqués. Pas de nouvel accès PMU pour R1.
                retry = collision + timedelta(hours=1)
                plan = prod.planifier(cache, retry)
                with patch('pmu_geny.auto_v18.get_json') as network:
                    resultats.rapprocher(cache, plan, lambda: retry)
                network.assert_not_called()
                with patch('pmu_geny.sync_google_sheets.lire_feuille_complete', return_value=table):
                    proofs = publier_plan(engine, plan)
                self.assertIn(f'{date}_R1', proofs)
                certificate = prod.enregistrer_publication(cache, retry, plan, True, sheets={
                    'lecture_utc': retry.isoformat(), 'rapprochements_verifies': sorted(proofs)})
                self.assertTrue(certificate['publication_reussie'])
                self.assertEqual(prod.lire(path)['publication_sheets_utc'], retry.isoformat())
                self.assertEqual(prod.lire(path)['declenchement_utc'], collision.isoformat())
                after = prod.planifier(cache, retry + timedelta(minutes=1))
                self.assertNotIn(f'{date}_R1', {r['reunion'] for r in after['rapprochements_dus']})
                trace.append((collision.isoformat(), retry.isoformat(), sorted(proofs)))
                if jour == jours[0]:
                    # Une deuxième réunion de la veille a été traitée par le cycle de soirée.
                    prod.sauver(cache/'rapprochements'/f'{date}_R2.json',
                                {'statut': 'COMPLET', 'inventaire_pmu_verifie': True,
                                 'publication_sheets_utc': (jour + timedelta(hours=14)).isoformat()})
            fin = origine + timedelta(hours=48)
            prod.planifier(cache, fin)
            print('RECETTE_48H', origine.isoformat(), fin.isoformat(), trace)

    def test_jalon_avant_7h_et_global_restreint(self):
        with TemporaryDirectory() as tmp:
            cache = Path(tmp)
            now = datetime(2026, 11, 24, 4, 56, tzinfo=timezone.utc)
            date = now.date().isoformat()
            prod.sauver(cache/'sources_pmu'/f'programme_{date}.json', {'programme': [
                {'code': 'R1C1', 'date': date, 'depart': f'{date}T09:00:00+01:00'}]})
            plan = prod.planifier(cache, now, force=True)
            self.assertEqual(plan['mode'], 'JALONS')
            self.assertEqual(plan['jalons_dus'][0]['phase'], 'H3')
            self.assertTrue(prod.plan_collecte(cache, now, nocturne=True)['secours_pmu'])

    def test_vrai_cycle_deux_jours_avec_panne_cron_et_arrivee_ex_aequo(self):
        from pmu_geny.auto_v18 import BASE
        from pmu_geny.cycle_production import executer

        with TemporaryDirectory() as tmp:
            cache = Path(tmp)
            plan_path = cache/'plan.json'
            start = datetime(2026, 12, 1, tzinfo=timezone.utc)
            now = start
            retries = set()
            checkpoints = {}

            def pmu(url):
                relative = url.removeprefix(BASE).split('/')
                date = datetime.strptime(relative[0], '%d%m%Y').replace(tzinfo=timezone.utc)
                depart = date + timedelta(hours=9)
                if len(relative) > 1:
                    self.assertEqual(relative[1:], ['R2', 'C1', 'participants'])
                    ranks = {4: 1, 6: 1, 8: 3} if now >= depart else {}
                    return {'participants': [
                        {'numPmu': n, 'nom': f'Cheval {n}', 'statut': 'PARTANT',
                         'ordreArrivee': ranks.get(n), 'musique': '1a2a3a'}
                        for n in range(1, 9)]}
                final = now >= depart + timedelta(minutes=30)
                course = {'numOrdre': 1, 'heureDepart': int(depart.timestamp() * 1000),
                          'nombreDeclaresPartants': 8, 'specialite': 'TROT_ATTELE',
                          'libelle': 'Prix de recette', 'montantPrix': 18000, 'distance': 2800,
                          'arriveeDefinitive': final, 'ordreArrivee': [[6, 4], [8], [1]] if final else []}
                annulee = {**course, 'numOrdre': 2, 'statut': 'COURSE_ANNULEE',
                           'heureDepart': int((depart + timedelta(minutes=45)).timestamp() * 1000)}
                return {'programme': {'reunions': [{'numOfficiel': 2, 'pays': 'FRA',
                        'hippodrome': {'libelleLong': 'Chartres'}, 'courses': [course, annulee]}]}}

            with patch('pmu_geny.auto_v18.get_json', side_effect=pmu), patch(
                    'socket.socket.connect', side_effect=AssertionError('réseau interdit')):
                for tick in range(48 * 4):
                    now = start + timedelta(minutes=15 * tick)
                    if now.date() == start.date() and 6 <= now.hour < 12:
                        continue
                    plan = prod.planifier(cache, now)
                    if not plan['executer']:
                        continue
                    prod.sauver(plan_path, plan)
                    executer(cache, plan_path, lambda: now)
                    plan = resultats.rattraper_obligations(cache, plan_path, lambda: now)
                    if plan['mode'] == 'PREPARATION_JOUR':
                        continue
                    source = source_rows(cache, now=now)
                    engine = Mock(cache=cache)
                    engine.source.return_value = source
                    engine.metadata.return_value = {'Résultats & Analyse': {}}
                    rows = list(source['Résultats & Analyse'].values())
                    headers = ['course_key', 'reunion_pmu', 'rapprochement_statut',
                               'rapprochement_arrivee_statut', 'rapprochement_declenchement_utc',
                               'jalon_compare', 'arrivee_officielle_numeros']
                    grid = [[DISPLAY_NAMES.get(k, k) for k in headers],
                            *[[row.get(k, '') for k in headers] for row in rows]]
                    due = [item['reunion'] for item in plan['rapprochements_dus']]
                    if due and due[0] not in retries:
                        retries.update(due)
                        with patch('pmu_geny.sync_google_sheets.lire_feuille_complete', return_value=grid[:1]):
                            with self.assertRaises(ErreurSynchronisation):
                                publier_plan(engine, plan)
                        prod.enregistrer_publication(cache, now, plan, False)
                        self.assertFalse(prod.lire(cache/'rapprochements'/f'{due[0]}.json').get('publication_sheets_utc'))
                        continue
                    with patch('pmu_geny.sync_google_sheets.lire_feuille_complete', return_value=grid):
                        verified = publier_plan(engine, plan)
                    proof = prod.preuves_sheets(list(source['Courses & Prévisions'].values()), now)
                    prod.enregistrer_publication(cache, now, plan, True,
                                                sheets={**proof, 'rapprochements_verifies': sorted(verified)})
                    state = prod.lire(cache/'orchestration/production_etat.json')
                    if state:
                        checkpoints[now.date().isoformat()] = state['dernier_global_publie_utc']

            self.assertEqual(len(retries), 2)
            self.assertEqual(len(checkpoints), 2)
            for i in range(2):
                day = (start + timedelta(days=i)).date().isoformat()
                meeting = prod.lire(cache/'rapprochements'/f'{day}_R2.json')
                self.assertEqual(meeting['statut'], 'COMPLET')
                self.assertEqual(meeting['courses']['R2C1']['podium'], [4, 6, 8])
                self.assertEqual(meeting['courses']['R2C2']['statut'], 'COURSE_ANNULEE')
                self.assertLess(prod.instant(meeting['declenchement_utc']),
                                prod.instant(meeting['publication_sheets_utc']))
                self.assertEqual(meeting['echeance'], f'{day}T09:30:00+00:00')
                for path in (cache/'pronostics').glob(f'{day}_R*.json'):
                    prediction = prod.lire(path)
                    if prediction.get('calcul_utc') and prediction.get('depart'):
                        self.assertLess(prod.instant(prediction['calcul_utc']), prod.instant(prediction['depart']))
            print('RECETTE_CYCLE_PYTHON_48H', sorted(retries), checkpoints)
