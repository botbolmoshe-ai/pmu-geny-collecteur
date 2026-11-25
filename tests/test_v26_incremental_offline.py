import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pmu_geny.collecte_geny_v4 import parse_career,lire_classement
from pmu_geny.controle_historique import classifier
from unittest.mock import patch,Mock

from pmu_geny import historiques_incrementaux as inc

UTC = timezone.utc


def doc(stamp, rows=None):
    if rows is None:
        rows = [{'date': (stamp-timedelta(days=10)).date().isoformat(),
                 'hippodrome': 'Vincennes', 'discipline': 'Attelé',
                 'distance_m': '2700', 'classement': '3', 'texte_source': 'preuve A','ferrure':'F'}]
    return {'statut': 'COMPLET', 'nombre_annonce_geny': len(rows), 'nombre_extrait': len(rows),
            'performances': rows, 'extrait_utc': stamp.isoformat(),
            'source_url': 'https://www.geny.com/cheval/123456-test/course/1698061'}


class IncrementalTests(unittest.TestCase):
    def test_resultat_tb_explicite_ne_bloque_pas_une_carriere_complete(self):
        row='09/06/25 | Rânes | Attelé | 2 150 | D | - | Herbe | Crse H | 12 000 € | C. Testard | Tb'
        parsed=parse_career('CARRIÈRE\nsur 1 courses',[row])
        self.assertEqual(parsed['performances'][0]['classement'],'Tb')
        self.assertEqual(classifier(parsed),('COMPLET',[]))
        self.assertEqual(lire_classement(['C. Testard','Tb','00:00','/','00:00']),'Tb')
        self.assertEqual(lire_classement(['C. Testard','TB_INCONNU']),'')
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        self.now = datetime.now(UTC)
        self.day = self.now.date().isoformat()
        self.engagement = self.day+'_R1C1'
        self.gen = {'id': '123456', 'nom': 'Test',
                    'url_geny': 'https://www.geny.com/cheval/123456-test/course/1698061'}
        inc.ecrire(self.cache/'etat_persistant.json', {'version': 1, 'chevaux': {}})
        inc.ecrire(self.cache/'partants_actuels'/f'{self.engagement}.json',
                   {'chevaux': {'1': {'nom': 'Test', 'statut_np': 'PARTANT'}}})
        inc.ecrire(self.cache/'orchestration/correspondances_geny.json',
                   {self.engagement: 'GENY-1698061'})
        self.sleep = patch.object(inc.time, 'sleep')
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def seed(self, stamp=None):
        data = doc(stamp or self.now-timedelta(days=2))
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json', data)
        inc.ecrire(self.cache/'etat_persistant.json', {'version': 1, 'chevaux': {
            '123456': {'id': '123456', 'nom': 'Test', 'statut': 'COMPLET',
                       'maj_utc': self.now.isoformat()}}})
        return data

    def collect(self, horse, out):
        out = self.cache/'extraction/123456'
        old = inc.capture_valide(self.cache, '123456')
        data = doc(datetime.now(UTC), copy.deepcopy(old['performances']) if old else None)
        inc.ecrire(out/'historique_geny.json', data)
        return {'complet': True, 'identite_verifiee': True, 'statut': 'COMPLET',
                'geny': self.gen, 'dossier': str(out)}

    def test_reutilise_les_liens_de_course_dans_le_meme_passage_sans_pause(self):
        inc.ecrire(self.cache/'partants_actuels'/f'{self.engagement}.json', {'chevaux': {
            '1': {'nom': 'Test', 'statut_np': 'PARTANT'},
            '2': {'nom': 'Autre', 'statut_np': 'PARTANT'},
        }})
        seen = []

        def collect(horse, out):
            seen.append(horse['numero'])
            if horse['numero'] == '1':
                inc.ecrire(out/'liens_course.json', {
                    'engagement': self.engagement, 'source_url': horse['course_url'],
                    'course_geny_id': '1698061', 'capture_utc': datetime.now(UTC).isoformat(),
                    'http': 200, 'chevaux': {
                        '1': self.gen,
                        '2': {'id': '123457', 'nom': 'Autre', 'url_geny': 'https://www.geny.com/cheval/123457'},
                    },
                })
                inc.ecrire(out/'historique_geny.json', doc(datetime.now(UTC)))
                return {'complet': True, 'identite_verifiee': True,
                        'geny': self.gen, 'dossier': str(out)}
            self.assertEqual(horse['geny']['id'], '123457')
            return {'statut': 'ACCES_LIMITE_429'}

        with patch.object(inc.time, 'sleep') as pause:
            state = inc.run(self.cache, collect=collect, sync=lambda h: {})
        self.assertEqual(seen, ['1', '2'])
        self.assertEqual(state['motif_fin_passage'], 'COOLDOWN')
        self.assertEqual(state['chevaux']['123456']['sync'], 'OK')
        pause.assert_not_called()

    def test_capture_validee_annule_un_ancien_delai_d_echec(self):
        self.seed()
        horse={'nom':'Test','id':'123456','geny':self.gen,
               'prochain_essai_utc':(self.now+timedelta(hours=6)).isoformat()}
        inc.accepter(self.cache,horse,self.collect(horse,self.cache/'capture'))
        self.assertNotIn('prochain_essai_utc',horse)
        self.assertEqual(horse['erreur'],'')

    def test_echec_garde_les_motifs_et_les_compteurs_distincts(self):
        self.seed(self.now-timedelta(days=3))
        result={'complet':False,'identite_verifiee':True,'statut':'DONNEES_INCOMPLETES',
                'motifs':['CHAMP_MANQUANT:classement:1']}
        state=inc.run(self.cache,collect=lambda h,p:result,sync=lambda h:{})
        horse=state['chevaux']['123456']
        self.assertEqual(horse['dernier_echec_collecte']['motifs'],result['motifs'])
        self.assertEqual(horse['dernier_echec_collecte']['statut'],'DONNEES_INCOMPLETES')
        self.assertEqual(state['bilan']['tentatives_collecte'],1)
        self.assertEqual(state['bilan']['captures_validees'],0)
        self.assertEqual(state['bilan']['collectes_rejetees'],1)

    def test_production_cede_apres_sauvegarde_et_publication_du_cheval(self):
        self.seed(self.now-timedelta(days=3));checkpoints=[]
        stop=Mock(side_effect=[None,'PRIORITE_PRODUCTION_EN_ATTENTE'])
        collect=Mock(side_effect=self.collect);sync=Mock(return_value={})
        state=inc.run(self.cache,collect=collect,sync=sync,stop_requested=stop,
                      checkpoint=lambda c:checkpoints.append(inc.lire(c/inc.QUEUE)))
        collect.assert_called_once();sync.assert_called_once()
        self.assertEqual(state['motif_fin_passage'],'PRIORITE_PRODUCTION_EN_ATTENTE')
        self.assertEqual(state['chevaux']['123456']['sync'],'OK')
        self.assertTrue(any(s['bilan'].get('captures_validees')==1 for s in checkpoints))

    def test_migration_utilise_date_source_pas_date_migration(self):
        data = self.seed()
        state = inc.alimenter(self.cache, self.now)
        self.assertEqual(state['chevaux']['123456']['historique_complet_au_utc'], data['extrait_utc'])
        self.assertTrue(state['chevaux']['123456']['motif_actualisation'])

    def test_complete_recent_aucune_requete(self):
        self.seed(self.now)
        def interdit(*args):
            raise AssertionError('Geny ne doit pas etre consulte')
        result = inc.run(self.cache, collect=interdit, sync=interdit)
        self.assertEqual(result['bilan']['tentatives_collecte'], 0)

    def test_date_absente_non_fabriquee(self):
        data = self.seed(self.now)
        data.pop('extrait_utc')
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json', data)
        h = inc.alimenter(self.cache, self.now)['chevaux']['123456']
        self.assertIsNone(h['historique_complet_au_utc'])
        self.assertEqual(h['motif_actualisation'], 'HISTORIQUE_ABSENT_OU_NON_DATE')

    def test_nouvelle_course_declenche_actualisation_avant_ttl(self):
        h = {'historique_complet_au_utc': (self.now-timedelta(hours=2)).isoformat(),
             'derniere_course_officielle_utc': (self.now-timedelta(hours=1)).isoformat(),
             'derniere_performance_date': self.day}
        self.assertEqual(inc.actualisation_requise(h, self.now), 'NOUVELLE_COURSE_OFFICIELLE')

    def test_publication_geny_retardee_reste_a_completer(self):
        now = datetime(2026, 11, 24, 12, tzinfo=UTC)
        h = {'historique_complet_au_utc': now.isoformat(),
             'derniere_course_officielle_utc': (now-timedelta(hours=1)).isoformat(),
             'derniere_performance_date': (now-timedelta(days=1)).date().isoformat()}
        self.assertEqual(inc.actualisation_requise(h, now), 'PUBLICATION_GENY_EN_ATTENTE')

    def test_checkpoint_avant_sheets_et_sans_recollecte_au_second_passage(self):
        self.seed()
        events = []
        def checkpoint(cache):
            saved = inc.lire(cache/inc.QUEUE)
            self.assertFalse(any(h.get('collecte') == 'EN_COURS' for h in saved['chevaux'].values()))
            events.append(('checkpoint', saved))
        def sync(h):
            self.assertEqual(events[-1][0], 'checkpoint')
            self.assertEqual(events[-1][1]['chevaux']['123456']['sync'], 'A_FAIRE')
            self.assertIsNotNone(inc.capture_valide(self.cache, '123456'))
            events.append(('sync', None))
            return {'OK': True}
        with patch.object(inc, 'executer_enfant', wraps=self.collect) as collect:
            first = inc.run(self.cache, collect=collect, checkpoint=checkpoint, sync=sync)
            self.assertEqual(first['chevaux']['123456']['sync'], 'OK')
            second = inc.run(self.cache, collect=collect, checkpoint=checkpoint, sync=sync)
            self.assertEqual(collect.call_count, 1)
            self.assertEqual(second['bilan']['tentatives_collecte'], 0)

    def test_erreur_sheets_reprise_sans_geny(self):
        self.seed()
        def fail(h):
            raise RuntimeError('Sheets indisponible')
        first = inc.run(self.cache, collect=self.collect, sync=fail)
        self.assertEqual(first['chevaux']['123456']['sync'], 'A_FAIRE')
        first['chevaux']['123456']['prochaine_sync_utc'] = (self.now-timedelta(minutes=1)).isoformat()
        inc.ecrire(self.cache/inc.QUEUE, first)
        def interdit(*args):
            raise AssertionError('recollecte interdite')
        result = inc.run(self.cache, collect=interdit, sync=lambda h: {'ok': True})
        self.assertEqual(result['chevaux']['123456']['sync'], 'OK')
        self.assertEqual(result['bilan']['tentatives_collecte'], 0)

    def test_refus_global_403_et_429(self):
        for code in ('403', '429'):
            with self.subTest(code=code):
                statefile = self.cache/inc.QUEUE
                statefile.unlink(missing_ok=True)
                inc.ecrire(self.cache/'etat_persistant.json', {'version': 1, 'chevaux': {}})
                def refuse(h, out):
                    return {'statut': 'ACCES_REFUSE_403' if code == '403' else 'ACCES_LIMITE_429'}
                first = inc.run(self.cache, collect=refuse)
                self.assertEqual(first['bilan']['tentatives_collecte'], 1)
                self.assertEqual(inc.lire(self.cache/'etat_persistant.json')['dernier_blocage_geny']['code'], code)
                result = inc.run(self.cache, collect=refuse)
                self.assertEqual(result['bilan']['tentatives_collecte'], 0)

    def test_historique_plus_pauvre_ne_remplace_pas_existant(self):
        old = self.seed()
        report = self.collect({}, None)
        reduced = doc(self.now, [])
        inc.ecrire(Path(report['dossier'])/'historique_geny.json', reduced)
        with self.assertRaisesRegex(ValueError, 'REGRESSION'):
            inc.accepter(self.cache, {'nom': 'Test', 'id': '123456'}, report)
        self.assertEqual(inc.capture_valide(self.cache, '123456'), old)

    def test_partiel_ne_remplace_pas_complet(self):
        old = self.seed()
        report = self.collect({}, None)
        report['complet'] = False
        with self.assertRaisesRegex(ValueError, 'NON_VALIDE'):
            inc.accepter(self.cache, {'nom': 'Test'}, report)
        self.assertEqual(inc.capture_valide(self.cache, '123456'), old)

    def test_identifiant_different_refuse(self):
        report = self.collect({}, None)
        with self.assertRaisesRegex(ValueError, 'IDENTIFIANT'):
            inc.accepter(self.cache, {'nom': 'Test', 'id': '999999'}, report)

    def test_ancien_snapshot_archive_et_pronostics_intacts(self):
        old = self.seed()
        protected = ['pronostics/fige.json', 'ml/instantanes/fige.json', 'arrivees/fige.json']
        for name in protected:
            inc.ecrire(self.cache/name, {'preuve': name})
        before = {name: (self.cache/name).read_bytes() for name in protected}
        result = inc.run(self.cache, collect=self.collect, sync=lambda h: {})
        self.assertEqual(result['chevaux']['123456']['sync'], 'OK')
        archive = next((self.cache/'historiques_versions/123456').glob('*.json'))
        self.assertEqual(inc.lire(archive), old)
        self.assertEqual(before, {name: (self.cache/name).read_bytes() for name in protected})

    def test_deux_courses_meme_cheval_un_seul_travail(self):
        self.seed()
        inc.ecrire(self.cache/'partants_actuels'/f'{self.day}_R1C2.json',
                   {'chevaux': {'7': {'nom': 'Test', 'statut_np': 'PARTANT'}}})
        state = inc.alimenter(self.cache, self.now)
        self.assertEqual(len(state['chevaux']), 1)

    def test_np_non_mis_en_file(self):
        inc.ecrire(self.cache/'partants_actuels'/f'{self.engagement}.json',
                   {'chevaux': {'1': {'nom': 'Test', 'statut_np': 'NON_PARTANT'}}})
        self.assertEqual(inc.alimenter(self.cache, self.now)['chevaux'], {})

    def test_etat_corrompu_arrete_sans_effacer(self):
        (self.cache/'collecte_incrementale').mkdir()
        path = self.cache/inc.QUEUE
        path.write_text('{invalide')
        with self.assertRaises(json.JSONDecodeError):
            inc.alimenter(self.cache, self.now)
        self.assertEqual(path.read_text(), '{invalide')

    def test_checkpoint_echoue_arrete_avant_requete(self):
        def checkpoint(cache):
            raise RuntimeError('push refuse')
        def collect(*args):
            raise AssertionError('requete interdite')
        with self.assertRaisesRegex(RuntimeError, 'push refuse'):
            inc.run(self.cache, collect=collect, checkpoint=checkpoint)

    def test_manifest_materialise_seulement_si_identites_completes(self):
        self.seed(self.now)
        state = inc.alimenter(self.cache, self.now)
        inc.materialiser_manifestes(self.cache, state)
        manifest = inc.lire(self.cache/'manifestes/GENY-1698061.json')
        self.assertEqual(manifest['courses'][0]['partants'][0]['id'], '123456')
        self.assertEqual(manifest['courses'][0]['nombre_partants_attendu'], 1)

    def test_nouvelle_identite_reprise_sous_id_stable(self):
        result = inc.run(self.cache, collect=self.collect, sync=lambda h: {})
        self.assertEqual(set(result['chevaux']), {'123456'})
        self.assertEqual(result['chevaux']['123456']['sync'], 'OK')

    def test_dpg_conserve_sans_place_inventee(self):
        from pmu_geny.collecte_geny_v4 import lire_classement
        self.assertEqual(lire_classement(['Dpg']), 'Dpg')

    def test_suffixe_video_reel_ne_masque_pas_dai(self):
        from pmu_geny.collecte_geny_v4 import lire_classement
        self.assertEqual(lire_classement(['D', '-', 'Herbe', '14000 €', 'J. Debost',
                                          'Dai', '00:00', '/', '00:00']), 'Dai')
        self.assertEqual(lire_classement(['1', 'e', '00:00', '/', '00:00']), '1')
        self.assertEqual(lire_classement(['14 000 €', '35']), '')


if __name__ == '__main__':
    unittest.main()
