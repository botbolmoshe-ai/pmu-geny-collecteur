import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from pmu_geny import echeances_production as e


class EcheancesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name)
        self.now = datetime(2026,11,17,9,tzinfo=timezone.utc)
        self.depart = self.now+timedelta(hours=3)
        self.key = '2026-11-17_R3C1'
        for day in ('2026-11-17','2026-11-18'):
            e.sauver(self.cache/'sources_pmu'/f'programme_{day}.json',{
                'date_controle_utc':self.now.isoformat(), 'programme':[
                    {'code':'R3C1','depart':self.depart.isoformat()}] if day=='2026-11-17' else []})
        self.mark_global(self.now)

    def mark_global(self, now):
        e.sauver(self.cache/'orchestration/production_etat.json',{'dernier_global_publie_utc':now.isoformat()})

    def predictions(self, now, ml=True):
        profile={'capture_utc':now.isoformat(),'chevaux':{str(n):{'statut_np':'PARTANT'} for n in (1,2,3)}}
        e.sauver(self.cache/'partants_actuels'/f'{self.key}.json', profile)
        direct={'date':'2026-11-17','course':'R3C1','depart':self.depart.isoformat(),
                'calcul_utc':now.isoformat(),'top3':[{'numero':n} for n in (1,2,3)]}
        e.sauver(self.cache/'pronostics'/f'{self.key}_direct.json', direct)
        if ml:
            e.sauver(self.cache/'pronostics'/f'{self.key}_ml_latest.json',{
                **direct,'experimental':True,'entrainement_utc':self.now.isoformat(),
                'statut':'ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE',
                'dernier_label_entrainement_utc':(self.now-timedelta(days=1)).isoformat()})

    def publish(self, now, plan=None, *, observation=None):
        plan = plan or e.planifier(self.cache, now)
        observation = observation or now
        proof = {'lecture_utc': observation.isoformat(), 'courses': {}}
        for path in (self.cache/'pronostics').glob('*.json'):
            document = e.lire(path)
            key = document['date'] + '_' + document['course']
            method = 'ml' if path.stem.endswith('_ml_latest') else 'direct'
            proof['courses'].setdefault(key, {})[method] = {
                'calcul_utc': document['calcul_utc'],
                'numeros': [h['numero'] for h in document['top3']]}
        return e.enregistrer_publication(self.cache, now, plan, True, sheets=proof)

    def test_tick_leger_puis_cycle_global_horaire(self):
        self.assertEqual(e.planifier(self.cache,self.now)['mode'],'ATTENTE')
        self.assertEqual(e.planifier(self.cache,self.now,force=True)['mode'],'GLOBAL')
        self.assertEqual(e.planifier(self.cache,self.now+timedelta(hours=1))['mode'],'JALONS')

    def test_collecte_ne_charge_pas_navigateur_pendant_pause_sauf_publication_a_reprendre(self):
        e.sauver(self.cache/'etat_persistant.json',{'dernier_blocage_geny':{'utc':self.now.isoformat(),'code':'403'}})
        self.assertFalse(e.plan_collecte(self.cache,self.now)['executer'])
        e.sauver(self.cache/'collecte_incrementale/etat.json',{'chevaux':{'x':{'sync':'A_FAIRE'}}})
        self.assertFalse(e.plan_collecte(self.cache,self.now)['executer'])
        earlier = self.now - timedelta(minutes=40)
        self.mark_global(earlier)
        self.assertTrue(e.plan_collecte(self.cache,earlier)['executer'])
        later=self.now+timedelta(hours=1)
        self.assertEqual(e.plan_collecte(self.cache,later)['motif'],'ECHEANCE_PMU_PRIORITAIRE')

    def test_creneau_nocturne_suit_paris_ete_hiver_et_garde_la_marge(self):
        for month, hour_utc in ((1, 3), (7, 2)):
            with self.subTest(month=month):
                now = datetime(2026, month, 17, hour_utc, 12, tzinfo=timezone.utc)
                self.mark_global(now)
                self.assertTrue(e.plan_collecte(self.cache, now, nocturne=True)['executer'])
                for minute in (53, 59):
                    end = now.replace(minute=minute)
                    self.assertEqual(e.plan_collecte(self.cache, end, nocturne=True)['motif'],
                                     'HORS_CRENEAU_NOCTURNE')
                after = now.replace(hour=hour_utc + 1, minute=0)
                self.assertEqual(e.plan_collecte(self.cache, after, nocturne=True)['motif'],
                                 'HORS_CRENEAU_NOCTURNE')

    def test_collecte_nocturne_cede_avant_un_besoin_pmu(self):
        now = datetime(2026, 11, 17, 1, 12, tzinfo=timezone.utc)
        self.mark_global(now - timedelta(minutes=54))
        self.assertEqual(e.plan_collecte(self.cache, now, nocturne=True)['motif'],
                         'ECHEANCE_PMU_PRIORITAIRE')
        self.mark_global(now)
        e.sauver(self.cache / 'sources_pmu/programme_2026-11-17.json', {'programme': [{
            'code': 'R1C1', 'depart': (now + timedelta(hours=3)).isoformat(),
        }]})
        self.assertEqual(e.plan_collecte(self.cache, now, nocturne=True)['motif'],
                         'ECHEANCE_PMU_PRIORITAIRE')

    def test_relecture_sheets_justifie_la_version_avant_depart(self):
        now = self.now + timedelta(minutes=20)
        self.predictions(now)
        plan = e.planifier(self.cache, now)
        rows = [{'date_course': '2026-11-17', 'rncn': 'R3C1', 'numero': str(n),
                 'non_partant': 'PARTANT', 'top3_direct_rang': str(n), 'ml_rang': str(n),
                 'top3_direct_top3': 'OUI', 'ml_top3': 'OUI', 'top3_direct_utc': now.isoformat(),
                 'version_ml_utc': now.isoformat()} for n in (1, 2, 3)]
        proof = e.preuves_sheets(rows, now)
        proof['courses'][self.key]['ml']['numeros'].reverse()
        failed = e.enregistrer_publication(self.cache, now, plan, True, sheets=proof)
        self.assertIn('TOP3_NON_CONFIRME_SHEETS', {row['motif'] for row in failed['erreurs']})
        self.assertFalse((self.cache/'publications'/f'{self.key}.json').exists())
        direct_only = e.lire(self.cache/'publications'/'direct'/f'{self.key}.json')
        self.assertEqual(set(direct_only['versions']), {'direct'})
        self.assertEqual(direct_only['versions']['direct']['lecture_sheets_utc'], now.isoformat())

        report = e.enregistrer_publication(self.cache, now, plan, True, sheets=e.preuves_sheets(rows, now))
        self.assertEqual(report['erreurs'], [])
        certificate = e.lire(self.cache/'publications'/f'{self.key}.json')
        self.assertEqual(certificate['versions']['ml']['lecture_sheets_utc'], now.isoformat())

    def test_h2_reserve_trente_minutes_et_reste_du_si_non_publie(self):
        now=self.now+timedelta(minutes=30)
        plan=e.planifier(self.cache,now)
        self.assertEqual(plan['mode'],'JALONS')
        self.assertEqual(plan['selection'],['R3C1'])
        self.assertEqual(plan['jalons_dus'][0]['phase'],'H2')
        self.assertEqual(e.besoin_pmu(self.cache,now),'ECHEANCE_PMU_PRIORITAIRE')

    def test_anticipation_55_minutes_sans_relacher_la_fraicheur(self):
        before=self.now+timedelta(minutes=4)
        self.assertEqual(e.planifier(self.cache,before)['mode'],'ATTENTE')
        opened=self.now+timedelta(minutes=5)
        self.assertEqual(e.planifier(self.cache,opened)['jalons_dus'][0]['phase'],'H2')
        self.predictions(opened)
        late=opened+timedelta(minutes=31)
        report=self.publish(late, e.planifier(self.cache, opened))
        self.assertFalse(report['courses'][0]['top3_direct_et_ml'])
        self.assertEqual(e.lire(self.cache/'jalons'/f'{self.key}.json')['H2']['statut'],'INCOMPLET')

    def test_retard_atteste_ne_reinitialise_pas_indefiniment_le_global(self):
        now=self.now+timedelta(minutes=62)
        self.predictions(now)
        for day in ('2026-11-17','2026-11-18'):
            path=self.cache/'sources_pmu'/f'programme_{day}.json'
            doc=e.lire(path);doc['date_controle_utc']=now.isoformat();e.sauver(path,doc)
        plan = {**e.planifier(self.cache,now), 'mode': 'GLOBAL'}
        report = self.publish(now, plan)
        self.assertIn('JALON_PUBLIE_EN_RETARD', [x['motif'] for x in report['erreurs']])
        self.assertEqual(e.lire(self.cache/'orchestration/production_etat.json')['dernier_global_publie_utc'],now.isoformat())
        self.assertEqual(e.planifier(self.cache,now)['mode'],'ATTENTE')

    def test_publication_reussie_gel_immuable_puis_h1(self):
        now=self.now+timedelta(minutes=40)
        self.predictions(now)
        plan=e.planifier(self.cache,now)
        report=self.publish(now,plan)
        self.assertEqual(report['erreurs'],[])
        h2=e.lire(self.cache/'jalons'/f'{self.key}.json')['H2']
        self.assertEqual(h2['statut'],'PUBLIE_A_TEMPS')
        path=self.cache/h2['versions']['ml']['fichier']; frozen=path.read_bytes()
        self.assertEqual(hashlib.sha256(frozen).hexdigest(),h2['versions']['ml']['sha256'])
        self.mark_global(now)
        self.assertFalse(e.planifier(self.cache,now)['executer'])
        later=self.now+timedelta(minutes=95)
        self.predictions(later)
        self.publish(later)
        self.assertEqual(path.read_bytes(),frozen)
        phases=e.lire(self.cache/'jalons'/f'{self.key}.json')
        self.assertEqual(phases['H1']['statut'],'PUBLIE_A_TEMPS')

    def test_echec_sheets_ne_certifie_ni_jalon_ni_cycle_global(self):
        now=self.now+timedelta(minutes=40);self.predictions(now)
        before=(self.cache/'orchestration/production_etat.json').read_bytes()
        e.enregistrer_publication(self.cache,now,{'mode':'GLOBAL'},False)
        self.assertFalse((self.cache/'publications'/f'{self.key}.json').exists())
        self.assertFalse((self.cache/'jalons'/f'{self.key}.json').exists())
        self.assertEqual((self.cache/'orchestration/production_etat.json').read_bytes(),before)
        self.assertTrue(e.planifier(self.cache,now)['executer'])

    def test_h2_incomplet_reessaie_sans_reecrire_les_copies(self):
        now=self.now+timedelta(minutes=35);self.predictions(now,ml=False)
        self.publish(now)
        self.assertEqual(e.lire(self.cache/'jalons'/f'{self.key}.json')['H2']['statut'],'INCOMPLET')
        copies={p:p.read_bytes() for p in (self.cache/'jalons'/self.key).glob('*.json')}
        later=now+timedelta(minutes=5);self.predictions(later)
        self.publish(later)
        self.assertEqual(e.lire(self.cache/'jalons'/f'{self.key}.json')['H2']['statut'],'PUBLIE_A_TEMPS')
        for p,data in copies.items():self.assertEqual(p.read_bytes(),data)

    def test_horodatage_calcul_avant_deadline_ne_masque_pas_publication_tardive(self):
        now=self.now+timedelta(minutes=59);self.predictions(now)
        published=self.now+timedelta(minutes=62)
        self.publish(published, e.planifier(self.cache, now))
        phase=e.lire(self.cache/'jalons'/f'{self.key}.json')['H2']
        self.assertEqual(phase['statut'],'PUBLIE_EN_RETARD')
        self.assertEqual(phase['retard_secondes'],120)

    def test_pas_de_certificat_predepart_retroactif(self):
        self.predictions(self.depart-timedelta(minutes=1))
        e.enregistrer_publication(self.cache,self.depart,{'mode':'GLOBAL'},True)
        self.assertFalse((self.cache/'publications'/f'{self.key}.json').exists())
        self.assertFalse((self.cache/'jalons'/f'{self.key}.json').exists())

    def test_np_et_ml_futur_ou_course_etrangere_invalident_le_controle(self):
        now=self.now+timedelta(minutes=40);self.predictions(now)
        path=self.cache/'pronostics'/f'{self.key}_ml_latest.json';original=e.lire(path)
        for field,value in [('course','R3C2'),('entrainement_utc',(now+timedelta(seconds=1)).isoformat())]:
            with self.subTest(field=field):
                e.sauver(path,{**original,field:value})
                report=self.publish(now)
                self.assertEqual(report['erreurs'][0]['mode'],'ml')
        e.sauver(path,original)
        profile=self.cache/'partants_actuels'/f'{self.key}.json';data=e.lire(profile)
        data['chevaux']['3']['statut_np']='NON_PARTANT';e.sauver(profile,data)
        report=self.publish(now)
        self.assertEqual({r['mode'] for r in report['erreurs'] if 'mode' in r},{'direct','ml'})
        self.assertIn('JALON_INCOMPLET',[r['motif'] for r in report['erreurs']])

    def test_cycle_global_non_valide_sur_programme_ancien(self):
        now=self.now+timedelta(minutes=40);self.predictions(now)
        before=(self.cache/'orchestration/production_etat.json').read_bytes()
        self.publish(now, {**e.planifier(self.cache,now), 'mode': 'GLOBAL'})
        self.assertEqual((self.cache/'orchestration/production_etat.json').read_bytes(),before)

    def test_cycle_cible_ne_recertifie_pas_les_courses_non_rafraichies(self):
        now=self.now+timedelta(minutes=40);self.predictions(now)
        path=self.cache/'sources_pmu/programme_2026-11-17.json';data=e.lire(path)
        data['programme'].append({'code':'R3C2','depart':(self.depart+timedelta(minutes=35)).isoformat()})
        e.sauver(path,data)
        plan = e.planifier(self.cache, now)
        self.assertEqual(plan['selection'], ['R3C1', 'R3C2'])
        report = self.publish(now, plan)
        self.assertEqual(report['reunions'][0]['jalons']['H2']['statut'], 'INCOMPLET')
        self.assertEqual([r['course'] for r in report['courses']], [self.key, '2026-11-17_R3C2'])

    def test_trois_ecrivains_file_max_et_unique_verrou(self):
        import yaml
        root=Path(__file__).resolve().parents[1]/'.github/workflows'
        for name in ('pmu-v16.yml','historiques-incrementaux.yml','rattrapage-historiques.yml'):
            config=yaml.load((root/name).read_text(),Loader=yaml.BaseLoader)
            self.assertEqual(config['concurrency'],{'group':'pmu-donnees-production',
                'cancel-in-progress':'false','queue':'max'})

    def test_cli_fait_echouer_un_controle_fonctionnel_non_publie(self):
        from unittest.mock import patch
        plan=self.cache/'plan.json';e.sauver(plan,{'mode':'GLOBAL'})
        with patch('sys.argv',['echeances','--cache',str(self.cache),'--plan',str(plan),'--certifier','--strict']), \
             patch.dict('os.environ',{'PUBLICATION_REUSSIE':'false'}),patch('builtins.print'):
            with self.assertRaises(SystemExit) as exc:e.main()
        self.assertEqual(exc.exception.code,2)
        self.assertFalse(e.lire(self.cache/'qualite/dernier_controle_production.json')['publication_reussie'])


if __name__=='__main__':unittest.main()
