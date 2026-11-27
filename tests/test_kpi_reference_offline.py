import unittest
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from pmu_geny.kpi_registre import calculer_kpi,plan_kpi,totaux_reference

class KPIReferenceTests(unittest.TestCase):
    def test_maturity_metrics_are_re_read_without_duplicate_append(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from pmu_geny.ml_v19 import save, train
        from pmu_geny.moteur_sheets import SynchroniseurSheets
        from test_v26_chaine_offline import SheetsSession

        with TemporaryDirectory() as tmp:
            cache = Path(tmp)
            train(cache)
            save(cache/'ml/modele_experimental_actif.json', {
                'statut': 'ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE', 'sha256_modele': 'a'*64,
            })
            session = SheetsSession()
            engine = SynchroniseurSheets(cache, 'test', session=session)
            source = {'Courses & Prévisions': {}, 'Résultats & Analyse': {}}
            first = engine._synchroniser_kpi(engine.metadata(), source)
            self.assertGreater(first['Data Quality & KPI']['indicateurs_actualises'], 25)
            version = next(row for row in session.tables['Data Quality & KPI']
                           if row[1] == 'Maturité ML · Version en service')
            self.assertEqual(version[2], 'a'*64)
            second = engine._synchroniser_kpi(engine.metadata(), source)
            self.assertEqual(second['Data Quality & KPI']['indicateurs_actualises'], 0)

    def test_kpi_agrandit_une_grille_pleine_avant_publication(self):
        import re
        from pmu_geny.moteur_sheets import SynchroniseurSheets
        from test_v26_chaine_offline import Response, SheetsSession

        class TightSheet(SheetsSession):
            row_count = 2

            def get(self, url, **kwargs):
                response = super().get(url, **kwargs)
                if '/values' not in url:
                    for sheet in response.data['sheets']:
                        properties = sheet['properties']
                        if properties['title'] == 'Data Quality & KPI':
                            properties['gridProperties']['rowCount'] = self.row_count
                return response

            def post(self, url, **kwargs):
                data = kwargs['json']
                if 'requests' in data:
                    self.row_count += data['requests'][0]['appendDimension']['length']
                    return Response({})
                for item in data['data']:
                    if int(re.search(r'\d+$', item['range'])[0]) > self.row_count:
                        response = Response({})
                        response.status_code = 400
                        return response
                return super().post(url, **kwargs)

        with TemporaryDirectory() as folder:
            session = TightSheet()
            engine = SynchroniseurSheets(folder, 'test', session=session)
            source = {'Courses & Prévisions':{}, 'Résultats & Analyse':{}}
            first = engine._synchroniser_kpi(engine.metadata(), source)['Data Quality & KPI']
            self.assertGreater(first['indicateurs_verifies'], 0)
            self.assertEqual(session.row_count, len(session.tables['Data Quality & KPI']))
            second = engine._synchroniser_kpi(engine.metadata(), source)['Data Quality & KPI']
            self.assertEqual(second['indicateurs_actualises'], 0)

    def test_j_j1_emploient_les_lignes_relues_et_exigent_la_provenance_du_f(self):
        from pmu_geny.sync_google_sheets import canonical_headers
        headers = canonical_headers(['Date', 'Non-partant (NP)', 'Ferrure', 'PMU · État ferrure',
                                     'Historique · État', 'Historique · Nb performances récupérées'])
        first = dict(zip(headers, ('2026-11-18', 'PARTANT', 'F')))
        other = dict(zip(headers, ('2026-11-19', 'PARTANT', 'F', 'CONVENTION_PMU', 'HISTO_PARTIEL_GENY', 2)))
        rows = [first, other, {**other, 'non_partant':'NON_PARTANT'}]
        with TemporaryDirectory() as folder:
            metrics = calculer_kpi(folder, {'Courses & Prévisions':{}, 'Résultats & Analyse':{}},
                                   datetime(2026,11,18,10,tzinfo=timezone.utc), sheets_courses=rows)
        self.assertEqual(metrics['J · Ferrures inconnues'][0], 1)
        self.assertEqual(metrics['J · Ferrés (F)'][0], 0)
        self.assertEqual(metrics['J+1 · Ferrés (F)'][0], 1)
        self.assertEqual(metrics['J+1 · Historiques partiels'][0], 1)
        self.assertEqual(metrics['J+1 · Historiques complets'][0], 0)
        self.assertEqual(metrics['J+1 · Historiques publiés avec performances'][0], 1)

    def test_ml_counts_and_denominators_same_snapshot(self):
        participants={
            str(i):{'course_key':'C1' if i<2 else 'C2','cheval':f'Cheval {i}',
                    'ml_modele_statut':status,'ml_top3':selection}
            for i,(status,selection) in enumerate([
                ('ML_NON_ENTRAINE',''),('ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE','OUI'),
                ('ML_NON_PUBLIE_AVANT_DEPART','')])}
        with TemporaryDirectory() as folder:
            metrics=calculer_kpi(Path(folder),{'Courses & Prévisions':participants,
                'Résultats & Analyse':{}},datetime(2026,11,18,10,tzinfo=timezone.utc))
        self.assertEqual(metrics['Participations recensées'][0],3)
        self.assertEqual(metrics['Participations avec sélection ML publiée'][0],1)
        self.assertEqual(metrics['Participations avec modèle ML non entraîné'][0],1)
        refs=totaux_reference(metrics)
        self.assertEqual(refs['Participations avec sélection ML publiée'],3)
        self.assertEqual(refs['Participations avec modèle ML non entraîné'],3)
        self.assertEqual(refs['Courses évaluées'],2)
        self.assertEqual(refs['Taux de TOP3 exact (3 sur 3)'],0)

    def test_repair_stale_denominator_even_when_value_unchanged(self):
        label='Participations avec sélection ML publiée'
        metrics={label:(63,'preuve'),'Participations recensées':(1558,'preuve')}
        sheet=[['Dimension','Indicateur','Valeur','Définition','Total'],
               ['ML',label,63,'preuve',1568],
               ['Historique','Lignes de performances',100,'=FORMULA()',100]]
        updates=plan_kpi(sheet,metrics)
        self.assertEqual(updates,[{'range':"'Data Quality & KPI'!C2:E2",'values':[[63,'preuve',1558]]}])
        sheet[1][4]=1558
        self.assertEqual(plan_kpi(sheet,metrics),[])

    def test_inconnus_et_formules_preserves(self):
        sheet=[['A','B','C','D','E'],['groupe','Autre',0,'','=NBVAL(A:A)']]
        self.assertEqual(plan_kpi(sheet,{'Autre':(1,'preuve')}),
                         [{'range':"'Data Quality & KPI'!C2:D2",'values':[[1,'preuve']]}])

    def test_workflow_kpi_after_certification(self):
        workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/pmu-v16.yml').read_text()
        self.assertLess(workflow.index("PMU_KPI_DIFFERE: 'true'"),workflow.index('Certifier les publications'))
        self.assertLess(workflow.index('Certifier les publications'),workflow.index("PMU_KPI_ONLY: 'true'"))
        self.assertLess(workflow.index('Conserver les preuves meme'),workflow.index("PMU_KPI_ONLY: 'true'"))

    def test_kpi_reflete_un_jalon_tardif_si_la_publication_est_relue(self):
        import yaml

        workflow = Path(__file__).resolve().parents[1] / '.github/workflows/pmu-v16.yml'
        steps = yaml.safe_load(workflow.read_text())['jobs']['traiter-course']['steps']
        kpi = next(step for step in steps if step.get('env', {}).get('PMU_KPI_ONLY') == 'true')
        self.assertIn("steps.publication.conclusion == 'success'", kpi['if'])
        self.assertIn("steps.persistance_finale.conclusion == 'success'", kpi['if'])
        self.assertNotIn('steps.certification.conclusion', kpi['if'])
