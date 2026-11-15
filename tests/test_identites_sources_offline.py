"""Régression réelle : deux lignes Zone-Turf, une carrière Geny, aucun doublon."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from pmu_geny import historiques_incrementaux as inc
from pmu_geny import rattrapage_historiques as back
from pmu_geny.identites_chevaux import correspondances, qualifier_observation, source_identifiant
from pmu_geny.moteur_sheets import SynchroniseurSheets
from pmu_geny.sync_google_sheets import reconcilier_cles_historiques
from test_v26_chaine_offline import SheetsSession


class IdentitesSourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        self.now = datetime.now(timezone.utc)
        self.proof = correspondances()[0]
        self.legacy = {'id': '1717076', 'nom': 'JISKA DE DREAM',
            'source_url': self.proof['urls_sources']['zone_turf'], 'origine': 'SHEETS:Historique chevaux'}
        self.snapshot = {'capture_utc': self.now.isoformat(), 'chevaux': [self.legacy],
                         'ids_couverts': [], 'lignes_historique': 2}
        inc.ecrire(self.cache / back.INVENTAIRE, self.snapshot)
        inc.ecrire(self.cache / 'etat_persistant.json', {'chevaux': {}})
        env = patch.dict(os.environ, {'PMU_SHEETS_CONTROLES': str(self.cache / 'controles.jsonl'),
                                     'GITHUB_STEP_SUMMARY': ''})
        env.start(); self.addCleanup(env.stop)
        quiet = patch('builtins.print'); quiet.start(); self.addCleanup(quiet.stop)

    def rows(self):
        before, incoming = [], {}
        for perf in self.proof['performances_rapprochees']:
            row = {'identifiant_cheval': '1717076', 'cheval': self.proof['nom'],
                   'date_course_historique': perf['date'], 'hippodrome': perf['hippodrome'],
                   **{k: perf[k] for k in ('discipline', 'distance_m', 'classement', 'chrono', 'ferrure')},
                   'cle_performance': perf['cle_historique'], 'source_url': self.legacy['source_url']}
            row['chrono'] = row['chrono'].replace("''", '"')
            before.append(row)
            canonical = {**row, 'identifiant_cheval': '2724812', 'chrono': perf['chrono'],
                         'cle_performance': '2724812|' + perf['date'] + '|' + perf['hippodrome'].upper(),
                         'source_url': 'ligne Geny extraite et vérifiée'}
            incoming[canonical['cle_performance']] = canonical
        row = {**next(iter(incoming.values())), 'date_course_historique': '2026-11-01',
               'cle_performance': '2724812|2026-11-01|MARSEILLE-VIVAUX'}
        incoming[row['cle_performance']] = row
        return before, incoming

    def test_sources_distinctes_et_hotes_exactement_controles(self):
        self.assertEqual(source_identifiant('1717076', self.legacy['source_url']), 'zone_turf')
        self.assertEqual(source_identifiant('2724812', self.proof['url_geny']), 'geny')
        self.assertEqual(source_identifiant('1717076', self.proof['url_geny']), '')
        self.assertEqual(source_identifiant('1717076', self.legacy['source_url'].replace('zone-turf.fr', 'zone-turf.fr.evil.test')), '')

    def test_correspondance_exige_le_nom_et_la_source(self):
        resolved = qualifier_observation(self.legacy)
        self.assertEqual(resolved['id'], '2724812')
        self.assertEqual(resolved['identifiants_sources'], {'zone_turf': '1717076', 'geny': '2724812'})
        wrong = qualifier_observation({**self.legacy, 'nom': 'HOMONYME INCONNU'})
        self.assertEqual(wrong['id'], '')
        self.assertTrue(wrong['identifiant_externe_non_reconcilie'])

    def test_autre_numero_externe_ne_devient_jamais_un_candidat_geny(self):
        self.snapshot['chevaux'] = [{**self.legacy, 'id': '9999999', 'nom': 'Autre cheval',
            'source_url': 'https://www.zone-turf.fr/cheval/autre-cheval-9999999/resume-de-carriere/'}]
        inc.ecrire(self.cache / back.INVENTAIRE, self.snapshot)
        state = back.preparer(self.cache, self.now)
        h = state['chevaux']['zone_turf:9999999']
        self.assertFalse(h.get('id')); self.assertNotIn('lien_candidat', h)
        self.assertEqual(h['collecte'], 'IDENTITE_A_VERIFIER')

    def test_migration_conserve_la_cible_figee_et_priorise_la_reprise(self):
        state = back.preparer(self.cache, self.now)
        state['chevaux'] = {'1717076': {'nom': self.proof['nom'], 'id': '1717076',
            'erreur': 'IDENTIFIANT_NON_CONCORDANT', 'prochain_essai_utc': '2099-01-01T00:00:00+00:00'}}
        inc.ecrire(self.cache / back.QUEUE, state)
        migrated = back.preparer(self.cache, self.now)
        self.assertEqual(set(migrated['chevaux']), {'1717076'})
        h = migrated['chevaux']['1717076']
        self.assertEqual(h['id'], '2724812')
        self.assertEqual(h['identifiant_historique_original'], '1717076')
        self.assertEqual(h['geny']['url_geny'], self.proof['url_geny'])
        self.assertNotIn('prochain_essai_utc', h)
        self.assertEqual(migrated['inventaire_id'], state['inventaire_id'])
        self.assertEqual(back.prochaine_tache(migrated, self.now, {}), ('1717076', 'COLLECTE'))
        inc.ecrire(self.cache / back.QUEUE, migrated)
        self.assertEqual(back.preparer(self.cache, self.now)['chevaux']['1717076']['id'], '2724812')

    def test_ancienne_file_externe_non_reconciliee_est_bloquee(self):
        self.snapshot['chevaux'] = [{**self.legacy, 'nom': 'Autre cheval'}]
        inc.ecrire(self.cache / back.INVENTAIRE, self.snapshot)
        state = back.preparer(self.cache, self.now)
        state['chevaux'] = {'1717076': {'id': '1717076', 'nom': 'Autre cheval',
                                      'lien_candidat': 'https://www.geny.com/cheval/1717076'}}
        inc.ecrire(self.cache / back.QUEUE, state)
        h = back.preparer(self.cache, self.now)['chevaux']['1717076']
        self.assertFalse(h.get('id')); self.assertNotIn('lien_candidat', h)
        self.assertEqual(h['collecte'], 'IDENTITE_A_VERIFIER')

    def test_reconciliation_conserve_les_deux_cles_et_ne_mutile_pas_les_entrees(self):
        before, incoming = self.rows(); original = copy.deepcopy((before, incoming))
        merged = reconcilier_cles_historiques(before, incoming)
        self.assertEqual(len(merged), 3)
        self.assertTrue({r['cle_performance'] for r in before} <= set(merged))
        self.assertTrue(all(row['identifiant_cheval'] == '2724812' for row in merged.values()))
        self.assertEqual((before, incoming), original)

    def test_publication_commune_ajoute_seulement_le_manquant_et_rejoue_sans_doublon(self):
        before, incoming = self.rows()
        session = SheetsSession(); headers = list(before[0])
        session.tables['Historique chevaux'] = [headers] + [[r[k] for k in headers] for r in before]
        engine = SynchroniseurSheets(self.cache, 'fake-identites', session=session)
        source = {'Historique chevaux': incoming}
        first = engine.synchroniser_tables(source, scope='RATTRAPAGE')
        second = engine.synchroniser_tables(source, scope='CYCLE_PMU', full_source=True)
        self.assertEqual(first['Historique chevaux']['lignes_ajoutees'], 1)
        self.assertEqual(second['Historique chevaux']['lignes_ajoutees'], 0)
        self.assertEqual(second['Historique chevaux']['controle']['statut'], 'VALIDE')
        self.assertEqual(len(session.tables['Historique chevaux']), 4)

    def test_desaccord_chrono_ou_ferrure_bloque_avant_toute_ecriture(self):
        for field in ('chrono', 'ferrure'):
            before, incoming = self.rows()
            next(iter(incoming.values()))[field] = 'INCOHERENT'
            session = SheetsSession(); headers = list(before[0])
            session.tables['Historique chevaux'] = [headers] + [[r[k] for k in headers] for r in before]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'INTERSOURCE_NON_CONCORDANTE'):
                SynchroniseurSheets(self.cache, 'fake-identites', session=session).synchroniser_tables(
                    {'Historique chevaux': incoming}, scope='RATTRAPAGE')
            self.assertEqual(session.writes, [])

    def test_le_controle_identifiant_geny_reste_bloquant(self):
        with self.assertRaisesRegex(ValueError, 'IDENTIFIANT_NON_CONCORDANT'):
            inc.accepter(self.cache, {'nom': self.proof['nom'], 'id': '2724812'},
                {'complet': True, 'identite_verifiee': True, 'geny': {'id': '999999'}})

    def test_doublon_preexistant_entre_sources_bloque_dans_les_deux_ordres(self):
        before, incoming = self.rows()
        canonical = {**next(iter(incoming.values())), 'cle_performance': 'autre-cle-existante'}
        for rows in ([canonical] + before, before + [canonical]):
            with self.assertRaisesRegex(ValueError, 'CORRESPONDANCE_HISTORIQUE_AMBIGUE'):
                reconcilier_cles_historiques(rows, incoming)

    def test_ancien_id_avec_url_geny_deja_corrigee_est_aussi_reconcilie(self):
        resolved=qualifier_observation({**self.legacy,'source_url':self.proof['url_geny']})
        self.assertEqual(resolved['id'],'2724812')
        self.assertEqual(resolved['identifiants_sources']['zone_turf'],'1717076')

    def repair_case(self):
        from test_v26_incremental_offline import doc
        before,incoming=self.rows()
        # Le cas réellement oublié : ID Zone-Turf, URL Geny et chrono absent.
        before[0].update(source_url=self.proof['url_geny'],chrono='',driver_jockey='Driver conservé')
        before[1]['driver_jockey']='Autre driver conservé'
        for row in incoming.values():row['driver_jockey']=''
        perfs=[{'date':r['date_course_historique'],**{k:r[k] for k in
            ('hippodrome','discipline','distance_m','classement','chrono','ferrure')}} for r in incoming.values()]
        document=doc(self.now,perfs);document['source_url']=self.proof['url_geny']
        inc.ecrire(self.cache/'historiques/2724812/historique_geny.json',document)
        class AtomicSession(SheetsSession):
            def post(self,url,**kwargs):
                if not url.endswith(':batchUpdate') or 'requests' not in kwargs['json']:
                    return super().post(url,**kwargs)
                from test_v26_chaine_offline import Response
                self.writes.append((url,kwargs['json']))
                for req in kwargs['json']['requests']:
                    if 'updateCells' in req:
                        data=req['updateCells'];start=data['start'];row=self.tables['Historique chevaux'][start['rowIndex']]
                        row[start['columnIndex']]=data['rows'][0]['values'][0]['userEnteredValue']['stringValue']
                    else:
                        bounds=req['deleteDimension']['range']
                        del self.tables['Historique chevaux'][bounds['startIndex']:bounds['endIndex']]
                return Response({})
        session=AtomicSession();headers=list(before[0])
        session.tables['Historique chevaux']=[headers]+[[r.get(k,'') for k in headers] for r in before+list(incoming.values())]
        engine=SynchroniseurSheets(self.cache,'fake-identites',session=session)
        return engine,session,incoming

    def test_reparation_sauvegarde_distante_avant_suppression_et_rejoue_sans_perte(self):
        from pmu_geny.reconcilier_identites_sheets import reparer
        engine,session,incoming=self.repair_case();events=[]
        def checkpoint(cache):
            files=list((cache/'historiques_versions/reconciliations_identites').glob('*.json'))
            self.assertEqual(len(files),1)
            events.append((len(session.writes),json.loads(files[0].read_text())['statut']))
        with patch.object(engine,'source',return_value={'Historique chevaux':incoming}):
            result=reparer(engine,checkpoint=checkpoint)
            again=reparer(engine,checkpoint=checkpoint)
        self.assertEqual(result['lignes_supprimees'],2)
        self.assertEqual(again['lignes_supprimees'],0)
        self.assertEqual(events,[(0,'SAUVEGARDE_AVANT_ECRITURE'),(1,'VALIDE')])
        self.assertEqual(len(session.tables['Historique chevaux']),4)
        rows=[dict(zip(session.tables['Historique chevaux'][0],r)) for r in session.tables['Historique chevaux'][1:]]
        self.assertEqual({r['identifiant_cheval'] for r in rows},{'2724812'})
        self.assertEqual({r['driver_jockey'] for r in rows},{'Driver conservé','Autre driver conservé',''})

    def test_echec_sauvegarde_interdit_toute_suppression(self):
        from pmu_geny.reconcilier_identites_sheets import reparer
        engine,session,incoming=self.repair_case()
        with patch.object(engine,'source',return_value={'Historique chevaux':incoming}), \
             self.assertRaisesRegex(RuntimeError,'Sauvegarde refusée'):
            reparer(engine,checkpoint=lambda cache:(_ for _ in ()).throw(RuntimeError('Sauvegarde refusée')))
        self.assertEqual(session.writes,[])

    def test_reparation_refuse_un_changement_de_distance(self):
        from pmu_geny.reconcilier_identites_sheets import reparer
        engine,session,incoming=self.repair_case()
        headers=session.tables['Historique chevaux'][0]
        session.tables['Historique chevaux'][1][headers.index('distance_m')]='9999'
        with patch.object(engine,'source',return_value={'Historique chevaux':incoming}), \
             self.assertRaisesRegex(ValueError,'DOUBLON_INTERSOURCE_NON_PROUVE'):
            reparer(engine,checkpoint=lambda cache:self.fail('Sauvegarde inutile'))
        self.assertEqual(session.writes,[])

    def test_snapshot_conserve_la_source_necessaire_a_la_reconciliation(self):
        before, _ = self.rows(); session = SheetsSession(); headers = list(before[0])
        session.tables['Historique chevaux'] = [headers] + [[r[k] for k in headers] for r in before]
        engine = SynchroniseurSheets(self.cache, 'fake-identites', session=session)
        with patch.object(engine, 'source', return_value={'Historique chevaux': {}}):
            snapshot = engine.inventaire_rattrapage()
        horses = [h for h in snapshot['chevaux'] if h['id'] == '1717076']
        self.assertEqual(len(horses), 1)
        self.assertEqual(horses[0]['source_url'], self.legacy['source_url'])
        self.assertEqual(session.writes, [])


if __name__ == '__main__':
    unittest.main()
