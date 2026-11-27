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
        self.depart = self.now+timedelta(hours=4)
        self.key = '2026-11-17_R3C1'
        for day in ('2026-11-17','2026-11-18'):
            e.sauver(self.cache/'sources_pmu'/f'programme_{day}.json',{
                'date_controle_utc':self.now.isoformat(), 'programme':[
                    {'code':'R3C1','depart':self.depart.isoformat()}] if day=='2026-11-17' else []})
        self.mark_global(self.now)

    def mark_global(self, now):
        e.sauver(self.cache/'orchestration/production_etat.json',{'dernier_global_publie_utc':now.isoformat()})

    def mark_preparation(self, now):
        day = (now.astimezone(e.PARIS).date()
               + timedelta(days=now.astimezone(e.PARIS).hour >= 21)).isoformat()
        e.sauver(self.cache/'sources_pmu'/f'programme_{day}.json',
                 {'date_controle_utc': now.isoformat(), 'programme': []})

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

    def test_pause_commune_active_et_expiree_sur_un_creneau_nocturne(self):
        now = datetime(2026, 11, 22, 2, 40, tzinfo=timezone.utc)
        self.mark_preparation(now)
        for code in ('403', '429'):
            with self.subTest(code=code):
                e.sauver(self.cache / 'rattrapage_historiques/etat.json', {
                    'prochain_acces_geny_utc': (now - timedelta(days=2)).isoformat()})
                e.sauver(self.cache / 'etat_persistant.json', {'dernier_blocage_geny': {
                    'utc': now.isoformat(), 'code': code}})
                active = e.plan_collecte(self.cache, now, nocturne=True)
                self.assertTrue(active['executer'])
                self.assertFalse(active['geny'])
                self.assertEqual(active['prochain_acces_geny_utc'],
                                 (now + timedelta(minutes=30)).isoformat())
                self.assertEqual(active['cooldown_geny']['etat'], 'ACTIF')
                expired = e.plan_collecte(self.cache, now + timedelta(minutes=30), nocturne=True)
                self.assertTrue(expired['executer'])
                self.assertTrue(expired['geny'])
                self.assertNotIn('prochain_acces_geny_utc', expired)
                self.assertEqual(expired['cooldown_geny']['etat'], 'EXPIRE')
                self.assertEqual(expired['cooldown_geny']['echeance_utc'], active['prochain_acces_geny_utc'])
                self.assertEqual(expired['cooldown_geny']['dernier_incident']['code'], code)

    def test_echeance_commune_la_plus_tardive_reste_active(self):
        now = self.now
        e.sauver(self.cache / 'etat_persistant.json', {'dernier_blocage_geny': {
            'utc': (now - timedelta(hours=1)).isoformat(), 'code': '429'}})
        deadline = now + timedelta(minutes=5)
        e.sauver(self.cache / 'collecte_incrementale/etat.json', {'prochain_acces_geny_utc': deadline.isoformat()})
        self.assertEqual(e.pause_geny_active(self.cache, now), deadline)
        self.assertIsNone(e.pause_geny_active(self.cache, deadline))

    def test_relais_apres_preparation_sans_relacher_garde_arrivees(self):
        now = datetime(2026, 11, 22, 2, 40, tzinfo=timezone.utc)
        run = e.planifier(self.cache, now)
        self.assertEqual(run['mode'], 'PREPARATION_JOUR')
        self.assertFalse(e.relais_nocturne(self.cache, now, run))
        self.mark_preparation(now)
        self.assertTrue(e.relais_nocturne(self.cache, now, run))
        self.assertFalse(e.relais_nocturne(self.cache, now, {**run, 'mode': 'ATTENTE'}))
        e.sauver(self.cache / 'sources_pmu/programme_2026-11-21.json', {'programme': [
            {'code': 'R1C1', 'depart': (now - timedelta(hours=2)).isoformat()},
        ]})
        self.assertEqual(e.planifier(self.cache, now)['mode'], 'ATTENTE')  # programme incohérent
        e.sauver(self.cache / 'sources_pmu/programme_2026-11-22.json', {
            'date_controle_utc': now.isoformat(), 'programme': [
                {'code': 'R1C1', 'depart': (now - timedelta(hours=1)).isoformat()},
            ],
        })
        self.assertEqual(e.planifier(self.cache, now)['mode'], 'RAPPROCHEMENT')
        self.assertFalse(e.relais_nocturne(self.cache, now, run))

    def test_global_perime_ne_bloque_pas_la_nuit_mais_reprend_a_7h(self):
        for day in ('2026-03-29', '2026-10-25'):
            with self.subTest(day=day):
                matin = datetime.fromisoformat(f'{day}T07:00').replace(tzinfo=e.PARIS).astimezone(timezone.utc)
                nuit = matin - timedelta(hours=1)
                self.mark_preparation(nuit)
                self.mark_global(nuit - timedelta(hours=8))
                self.assertEqual(e.planifier(self.cache, nuit, force=True)['mode'], 'ATTENTE')
                self.assertIsNone(e.besoin_pmu(self.cache, nuit))
                self.assertTrue(e.plan_collecte(self.cache, nuit, nocturne=True)['executer'])
                self.assertEqual(e.planifier(self.cache, matin)['mode'], 'GLOBAL')
                self.assertTrue(e.plan_collecte(self.cache, matin)['secours_pmu'])

    def test_21h_ne_declenche_que_la_preparation_manquante(self):
        soir = datetime(2026, 11, 24, 21, tzinfo=e.PARIS)
        self.mark_global(soir - timedelta(hours=3))
        self.assertEqual(e.planifier(self.cache, soir - timedelta(minutes=1))['mode'], 'GLOBAL')
        plan = e.planifier(self.cache, soir)
        self.assertEqual((plan['mode'], plan['date_preparation']), ('PREPARATION_JOUR', '2026-11-25'))
        self.assertTrue(e.plan_collecte(self.cache, soir, nocturne=True)['secours_pmu'])
        self.mark_preparation(soir)
        self.assertEqual(e.planifier(self.cache, soir)['mode'], 'ATTENTE')
        self.assertTrue(e.plan_collecte(self.cache, soir, nocturne=True)['executer'])

    def test_creneau_nocturne_suit_paris_ete_hiver_et_garde_la_marge(self):
        for month, hour_utc in ((1, 5), (7, 4)):
            with self.subTest(month=month):
                now = datetime(2026, month, 17, hour_utc, 12, tzinfo=timezone.utc)
                self.mark_preparation(now)
                self.assertTrue(e.plan_collecte(self.cache, now, nocturne=True)['executer'])
                for minute in (53, 59):
                    end = now.replace(minute=minute)
                    self.assertEqual(e.plan_collecte(self.cache, end, nocturne=True)['motif'],
                                     'HORS_CRENEAU_NOCTURNE')
                after = now.replace(hour=hour_utc + 1, minute=0)
                self.assertEqual(e.plan_collecte(self.cache, after, nocturne=True)['motif'],
                                 'HORS_CRENEAU_NOCTURNE')

    def test_budget_nocturne_franchit_minuit_et_reserve_les_arrivees(self):
        now = datetime(2026, 11, 17, 22, 55, tzinfo=timezone.utc)
        self.mark_global(now)
        e.sauver(self.cache / 'sources_pmu/programme_2026-11-17.json', {'programme': []})
        self.assertEqual(e.budget_collecte_nocturne(self.cache, now), 15)
        e.sauver(self.cache / 'sources_pmu/programme_2026-11-17.json', {'programme': [{
            'code': 'R1C1', 'depart': (now - timedelta(minutes=18)).isoformat(),
        }]})
        self.assertEqual(e.budget_collecte_nocturne(self.cache, now), 4)
        self.assertEqual(e.motif_pause_collecte_nocturne(self.cache, now + timedelta(minutes=5)),
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
        self.assertEqual(certificate['versions']['ml']['capture_partants_utc'], now.isoformat())

    def test_h3_reserve_trente_minutes_et_reste_du_si_non_publie(self):
        now=self.now+timedelta(minutes=30)
        plan=e.planifier(self.cache,now)
        self.assertEqual(plan['mode'],'JALONS')
        self.assertEqual(plan['selection'],['R3C1'])
        self.assertEqual(plan['jalons_dus'][0]['phase'],'H3')
        self.assertEqual(e.besoin_pmu(self.cache,now),'ECHEANCE_PMU_PRIORITAIRE')

    def test_anticipation_55_minutes_sans_relacher_la_fraicheur(self):
        before=self.now+timedelta(minutes=4)
        self.assertEqual(e.planifier(self.cache,before)['mode'],'ATTENTE')
        opened=self.now+timedelta(minutes=5)
        self.assertEqual(e.planifier(self.cache,opened)['jalons_dus'][0]['phase'],'H3')
        self.predictions(opened)
        late=opened+timedelta(minutes=31)
        report=self.publish(late, e.planifier(self.cache, opened))
        self.assertFalse(report['courses'][0]['top3_direct_et_ml'])
        self.assertEqual(e.lire(self.cache/'jalons'/f'{self.key}.json')['H3']['statut'],'INCOMPLET')

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

    def test_publication_reussie_gel_immuable_puis_h2(self):
        now=self.now+timedelta(minutes=40)
        self.predictions(now)
        plan=e.planifier(self.cache,now)
        report=self.publish(now,plan)
        self.assertEqual(report['erreurs'],[])
        h2=e.lire(self.cache/'jalons'/f'{self.key}.json')['H3']
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
        self.assertEqual(phases['H2']['statut'],'PUBLIE_A_TEMPS')

    def test_tick_manquant_et_echeances_concurrentes(self):
        day = self.key.split('_')[0]
        path = self.cache/'sources_pmu'/f'programme_{day}.json'
        data = e.lire(path)
        second = self.depart + timedelta(hours=1, minutes=20)
        data['programme'].append({'code': 'R1C1', 'depart': second.isoformat()})
        e.sauver(path, data)
        tick = self.depart - timedelta(hours=2, minutes=35)
        plan = e.planifier(self.cache, tick)
        self.assertEqual([(item['course'], item['phase'], item['echeance']) for item in plan['jalons_dus']], [
            (self.key, 'H2', (self.depart-timedelta(hours=2)).isoformat()),
            (f'{day}_R1C1', 'H3', (second-timedelta(hours=3)).isoformat()),
        ])
        result = e.enregistrer_publication(self.cache, tick, plan, False)
        first, = [r for r in result['reunions'] if r['reunion'] == f'{day}_R3']
        self.assertEqual(first['jalons']['H3']['statut'], 'INCOMPLET')
        self.assertNotIn('H1', first['jalons'])

    def test_ancien_h2_reste_h2_et_ancien_h1_reste_immuable(self):
        from pmu_geny.kpi_registre import calculer_kpi, plan_kpi

        path = self.cache/'jalons/reunions/2026-11-17_R3.json'
        old_h2_at = self.depart - timedelta(hours=2, minutes=1)
        old_h2 = {'statut': 'PUBLIE_A_TEMPS', 'reference_utc': self.depart.isoformat(),
                  'echeance': (self.depart-timedelta(hours=2)).isoformat(),
                  'publication_utc': old_h2_at.isoformat(), 'courses_attendues': ['R3C1']}
        old_h1 = {**old_h2, 'echeance': (self.depart-timedelta(hours=1)).isoformat()}
        e.sauver(path, {'H2': old_h2, 'H1': old_h1})
        now = self.depart - timedelta(minutes=50)
        plan = e.planifier(self.cache, now)
        self.assertEqual(plan['jalons_dus'], [])
        e.enregistrer_publication(self.cache, now, plan, False)
        certs = e.lire(path)
        self.assertEqual(certs['H2'], old_h2)
        self.assertEqual(certs['H1'], old_h1)
        source = {'Courses & Prévisions': {}, 'Résultats & Analyse': {}}
        metrics = calculer_kpi(self.cache, source, now)
        self.assertEqual(metrics['Échéances · H-2 publiées à temps'][0], 1)
        self.assertEqual(metrics['Échéances · H-3 dépassées sans preuve à temps'][0], 1)
        updates = plan_kpi([[], ['ML', 'Échéances · H2 publiées à temps', 5, 'Historique', 5]], metrics)
        updates_by_label = {row['values'][0][1]: row for row in updates if row['range'].startswith("'Data Quality & KPI'!A")}
        self.assertNotIn('Échéances · H2 publiées à temps', updates_by_label)
        self.assertEqual(updates_by_label['Échéances · H-2 publiées à temps']['values'][0][4], 1)

    def test_echec_sheets_ne_certifie_ni_jalon_ni_cycle_global(self):
        now=self.now+timedelta(minutes=40);self.predictions(now)
        before=(self.cache/'orchestration/production_etat.json').read_bytes()
        e.enregistrer_publication(self.cache,now,{'mode':'GLOBAL'},False)
        self.assertFalse((self.cache/'publications'/f'{self.key}.json').exists())
        self.assertFalse((self.cache/'jalons'/f'{self.key}.json').exists())
        self.assertEqual((self.cache/'orchestration/production_etat.json').read_bytes(),before)
        self.assertTrue(e.planifier(self.cache,now)['executer'])

    def test_h3_incomplet_reessaie_sans_reecrire_les_copies(self):
        now=self.now+timedelta(minutes=35);self.predictions(now,ml=False)
        self.publish(now)
        incomplete = e.lire(self.cache/'jalons'/f'{self.key}.json')['H3']
        self.assertEqual(incomplete['statut'], 'INCOMPLET')
        self.assertIsNone(incomplete['publication_utc'])
        self.assertEqual(set(incomplete['versions']), {'direct'})
        copies={p:p.read_bytes() for p in (self.cache/'jalons'/self.key).glob('*.json')}
        later=now+timedelta(minutes=5);self.predictions(later)
        self.publish(later)
        self.assertEqual(e.lire(self.cache/'jalons'/f'{self.key}.json')['H3']['statut'],'PUBLIE_A_TEMPS')
        for p,data in copies.items():self.assertEqual(p.read_bytes(),data)

    def test_horodatage_calcul_avant_deadline_ne_masque_pas_publication_tardive(self):
        now=self.now+timedelta(minutes=59);self.predictions(now)
        published=self.now+timedelta(minutes=62)
        self.publish(published, e.planifier(self.cache, now))
        phase=e.lire(self.cache/'jalons'/f'{self.key}.json')['H3']
        self.assertEqual(phase['statut'],'PUBLIE_EN_RETARD')
        self.assertEqual(phase['retard_secondes'],120)

    def test_relecture_future_ne_certifie_pas_une_publication(self):
        now = self.now + timedelta(minutes=40)
        self.predictions(now)
        report = self.publish(now, observation=now + timedelta(seconds=1))
        self.assertFalse(report['publication_reussie'])
        self.assertIn('PUBLICATION_SHEETS_NON_PROUVEE', [row['motif'] for row in report['erreurs']])
        self.assertFalse((self.cache/'publications'/f'{self.key}.json').exists())

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
        self.assertEqual(report['reunions'][0]['jalons']['H3']['statut'], 'INCOMPLET')
        self.assertEqual([r['course'] for r in report['courses']], [self.key, '2026-11-17_R3C2'])

    def test_reunion_complete_et_lecture_ponctuelle_avant_certification(self):
        start = self.now + timedelta(minutes=50)
        day = self.key.split('_')[0]
        program_path = self.cache/'sources_pmu'/f'programme_{day}.json'
        program = e.lire(program_path)
        second = self.depart + timedelta(minutes=40)
        program['programme'].append({'code': 'R3C2', 'depart': second.isoformat()})
        e.sauver(program_path, program)
        self.predictions(start)
        key = f'{day}_R3C2'
        e.sauver(self.cache/'partants_actuels'/f'{key}.json',
                 e.lire(self.cache/'partants_actuels'/f'{self.key}.json'))
        for suffix in ('direct', 'ml_latest'):
            doc = e.lire(self.cache/'pronostics'/f'{self.key}_{suffix}.json')
            e.sauver(self.cache/'pronostics'/f'{key}_{suffix}.json',
                     {**doc, 'course': 'R3C2', 'depart': second.isoformat()})
        deadline = self.depart - timedelta(hours=3)
        plan = e.planifier(self.cache, start)
        result = self.publish(deadline + timedelta(seconds=3), plan,
                              observation=deadline - timedelta(seconds=1))
        h2 = result['reunions'][0]['jalons']['H3']
        self.assertEqual(h2['statut'], 'PUBLIE_A_TEMPS')
        self.assertEqual(h2['courses_attendues'], ['R3C1', 'R3C2'])
        self.assertEqual(h2['publication_utc'], (deadline - timedelta(seconds=1)).isoformat())
        self.assertEqual(result['erreurs'], [])

    def test_ecrivains_sheets_dans_la_meme_file_sans_annulation(self):
        import yaml
        root=Path(__file__).resolve().parents[1]/'.github/workflows'
        for name, jobs in {
            'pmu-v16.yml': ('traiter-course',),
            'historiques-incrementaux.yml': ('publication', 'recensement'),
            'rattrapage-historiques.yml': ('rattrapage',),
            'validation-iterative-v21.yml': ('dates-registre',),
            'migration-structure-geny.yml': (),
        }.items():
            config=yaml.load((root/name).read_text(),Loader=yaml.BaseLoader)
            expected = {'group':'pmu-donnees-production', 'cancel-in-progress':'false','queue':'max'}
            for job in jobs:
                self.assertEqual(config['jobs'][job]['concurrency'], expected)
            if not jobs:
                self.assertEqual(config['concurrency'], expected)

    def test_cli_fait_echouer_un_controle_fonctionnel_non_publie(self):
        from unittest.mock import patch
        plan=self.cache/'plan.json';e.sauver(plan,{'mode':'GLOBAL'})
        with patch('sys.argv',['echeances','--cache',str(self.cache),'--plan',str(plan),'--certifier','--strict']), \
             patch.dict('os.environ',{'PUBLICATION_REUSSIE':'false'}),patch('builtins.print'):
            with self.assertRaises(SystemExit) as exc:e.main()
        self.assertEqual(exc.exception.code,2)
        self.assertFalse(e.lire(self.cache/'qualite/dernier_controle_production.json')['publication_reussie'])


    def test_depart_pmu_reporte_ne_fait_pas_echouer_certification(self):
        now = self.now
        day = now.date().isoformat()
        self.mark_global(now)
        old = {'code': 'R7C1', 'date': day, 'hippodrome': 'Vincennes',
               'depart': (now - timedelta(minutes=40)).isoformat()}
        e.sauver(self.cache/'sources_pmu'/f'programme_{day}.json', {
            'programme': [old], 'inventaire_reunions': [old]})
        plan = e.planifier(self.cache, now)
        self.assertEqual(plan['mode'], 'RAPPROCHEMENT')
        self.assertEqual(len(plan['rapprochements_dus']), 1)
        postponed = {**old, 'depart': (now + timedelta(minutes=10)).isoformat()}
        e.sauver(self.cache/'sources_pmu'/f'programme_{day}.json', {
            'programme': [postponed], 'inventaire_reunions': [postponed]})
        report = e.enregistrer_publication(
            self.cache, now, plan, True, sheets={'lecture_utc': now.isoformat()})
        self.assertFalse(any(x.get('motif') == 'RAPPROCHEMENT_NON_DEMARRE'
                             for x in report['erreurs']))
        self.assertEqual(report['rapprochements'][0]['statut'], 'DIFFERE_DEPART_REPORTE')
        later = now + timedelta(minutes=41)
        self.assertEqual(e.planifier(self.cache, later)['mode'], 'RAPPROCHEMENT')


if __name__=='__main__':unittest.main()
