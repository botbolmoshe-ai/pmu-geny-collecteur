"""Exercise the real app with a local read-only Sheets double, never real keys."""
import importlib.util
from datetime import datetime,timedelta,timezone,time
from pathlib import Path
import unittest
from unittest.mock import MagicMock,patch
from zoneinfo import ZoneInfo

READY=all(importlib.util.find_spec(m) is not None for m in ('streamlit','pandas','plotly','googleapiclient'))


@unittest.skipUnless(READY,'Installer dashboard/requirements.txt pour le test de navigation')
class AppTests(unittest.TestCase):
    def setUp(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        st.cache_data.clear()
        self.now=datetime.now(timezone.utc)
        self.today=self.now.astimezone(ZoneInfo('Europe/Paris')).date()
        self.app=AppTest.from_file(str(Path(__file__).with_name('app.py')),default_timeout=15)
        self.app.secrets['app_password']='mot-de-passe-test-local-uniquement'
        self.app.secrets['google_service_account']={}
        self.app.secrets['spreadsheet_id']='registre-test-local'
        self.api=MagicMock()
        self.build=patch('googleapiclient.discovery.build',return_value=self.api)
        self.credentials=patch('google.oauth2.service_account.Credentials.from_service_account_info',return_value=object())
        self.mock_build=self.build.start();self.addCleanup(self.build.stop)
        self.credentials.start();self.addCleanup(self.credentials.stop)

    def source(self,history=True,odds=False,market_top3=False,dual_profile=False,ipr=False):
        from trot_analytics.quality_dates import VALUE,TOTAL
        day=self.today.isoformat();depart=datetime.combine(self.today,time(12),ZoneInfo('Europe/Paris'))
        courses=[{'Clé course (technique)':day+'|R1C1','Date':day,'Course R/C':'R1C1','Hippodrome':'VINCENNES',
            'Départ (Paris)':depart.isoformat(),'Discipline':'Attelé','Distance (m)':2700,
            'Course · Nom PMU':'PRIX TEST','Course · Catégorie PMU':'Course C','Course · Âges admis':'5 ans',
            'Course · Allocation (€)':53000,'Course · Parcours':'Grande piste','Course · Mode de départ':'Autostart',
            'Autostart · Position assignée': n + 2, 'Autostart · Ligne': 1,
            'N°':n,'Cheval':f'Cheval test {n}','Non-partant (NP)':'PARTANT',
            'Cotes · Valeur': n+0.5, 'Cotes · Relevé UTC': (min(self.now, depart)-timedelta(minutes=5)).isoformat(),
            'TOP3 direct · Rang':n,'TOP3 direct · Sélection':'OUI','ML · Rang':n,'ML · Sélection':'OUI',
            'Gagnant potentiel direct · Sélection':'OUI' if n==1 else '',
            'Gagnant potentiel ML · Sélection':'OUI' if n==1 else '',
            'Historique · Nb performances récupérées':2,'Ferrure · Course du jour':'D4',
            'Profil du cheval': {1:'Crack',2:'Haut potentiel'}.get(n,''),
            'Profil · Indices': {1:'2 podiums en Groupe I/II',2:'2 podiums sur 3'}.get(n,''),
            'Âge (ans)':5,'Sexe':'Hongre','Gains carrière (€)':0} for n in (1,2,3)]
        if ipr:
            from trot_analytics.usages import IPR
            for index, row in enumerate(courses):
                values = {
                    'ipr_score': 0 if index == 0 else None,
                    'ipr_rang_shadow': 1 if index == 0 else None,
                    'ipr_confiance': 'FAIBLE' if index == 0 else 'NON ÉVALUABLE',
                    'ipr_n_historiques_comparables': 3 if index == 0 else 0,
                    'ipr_couverture': 16.7 if index == 0 else None,
                    'ipr_version': 'ipr-v1',
                    'ipr_calcul_utc': self.now.isoformat(),
                    'ipr_statut': IPR.usage,
                    'ipr_motifs': 'Une sortie <ambiguë>',
                }
                row.update({IPR.libelles[k]: value for k, value in values.items()})
        if dual_profile:
            courses[0].update({'Profil du cheval': 'Crack confirmé + Haut potentiel',
                               'Profil · Indices': 'Geny : preuves des deux profils'})
        if odds:
            stamp = min(self.now, depart) - timedelta(minutes=5)
            courses[0].update({'Cotes · Valeur': 7.5, 'Cotes · Relevé UTC': stamp.isoformat()})
        if market_top3:
            for row in courses:
                row.update({'Cotes · Sélection': 'OUI', 'Cotes · Rang': 4 - row['N°']})
        kpis=[{'Dimension':'Historique','Indicateur':'Taux de couverture',VALUE:0.75,TOTAL:4,'Définition / réserve':'Fixture locale'}]
        yesterday=self.today-timedelta(days=1)
        old=datetime.combine(yesterday,time(12),ZoneInfo('Europe/Paris'))
        snapshots=[{**kpis[0],'Date du relevé':d.isoformat(),'Relevé UTC':stamp.isoformat(),VALUE:value}
                   for d,stamp,value in ((yesterday,old,0.25),(self.today,self.now,0.75))]
        def table(rows):
            if not rows:return {'values':[]}
            keys=list(rows[0]);return {'values':[keys,*[[r.get(k,'') for k in keys] for r in rows]]}
        data=[table(courses),{'values':[['Date']]},table(kpis)]
        if history:data.append(table(snapshots))
        self.api.spreadsheets().get().execute.return_value={'sheets':[{'properties':{'title':'Historique qualité'}}] if history else []}
        self.api.spreadsheets().values().batchGet().execute.return_value={'valueRanges':data}

    def test_authentication_blocks_reads_until_login(self):
        self.app.run()
        self.assertEqual(len(self.app.exception),0)
        self.mock_build.assert_not_called()
        self.assertTrue(any('Version interface :' in x.value for x in self.app.caption))

    def test_navigation_date_filters_and_optional_history(self):
        self.source()
        self.app.session_state.authenticated=True
        self.app.run();self.assertEqual(len(self.app.exception),0)
        for page in ('Courses','Résultats','Performance','Qualité'):
            self.app.radio[0].set_value(page).run()
            self.assertEqual(len(self.app.exception),0,page)
        self.assertEqual(len(self.app.date_input),1)
        self.app.selectbox(key='quality_mode').set_value('Relevés historiques').run()
        self.app.date_input(key='quality_period').set_value((self.today-timedelta(days=1),self.today)).run()
        self.assertEqual(len(self.app.exception),0)
        self.assertEqual(len(self.app.error),0)
        self.assertEqual(list(self.app.dataframe[0].value['Nombre / valeur']),['25,0 %','75,0 %'])
        self.app.selectbox(key='quality_mode').set_value('Registre actuel').run()
        self.assertEqual(len(self.app.date_input),0)
        import streamlit as st
        st.cache_data.clear();self.source(history=False)
        self.app.button[0].click().run()
        self.app.selectbox(key='quality_mode').set_value('Relevés historiques').run()
        self.assertEqual(len(self.app.exception),0)
        self.assertTrue(any('Aucun relevé' in x.value for x in self.app.info))


    def test_profils_de_course_dans_le_tableau_et_styles(self):
        self.source()
        self.app.session_state.authenticated=True
        self.app.run()
        self.app.radio[0].set_value('Courses').run()
        self.assertEqual(len(self.app.exception), 0)
        tableau = self.app.dataframe[0]
        self.assertIn('PRIX TEST', self.app.expander[0].label)
        captions = [caption.value for caption in self.app.caption]
        self.assertTrue(any('Course C' in line and '53\u202f000 €' in line for line in captions))
        self.assertTrue(any('5 ans' in line and 'Grande piste · Autostart' in line for line in captions))
        self.assertEqual(list(tableau.value['Âge (ans)']), [5, 5, 5])
        self.assertEqual(list(tableau.value['Autostart · Position assignée']), [3, 4, 5])
        self.assertEqual(list(tableau.value['Cote PMU']), [1.5, 2.5, 3.5])
        ranges = self.api.spreadsheets().values().batchGet.call_args.kwargs['ranges']
        self.assertIn("'Courses & Prévisions'", ranges)
        self.assertIn('**Gagnant potentiel direct : 1 — Cheval test 1**',
                      [item.value for item in self.app.markdown])
        self.assertIn('**Gagnant potentiel ML : 1 — Cheval test 1**',
                      [item.value for item in self.app.markdown])
        self.assertEqual(list(tableau.value['Profil du cheval']), ['Crack confirmé', 'Haut potentiel', 'Non évaluable'])
        css = getattr(tableau.proto, "arrow_data", tableau.proto).styler.styles
        self.assertIn('background-color: #4b2574', css)
        self.assertIn('background-color: #123b72', css)
        self.assertIn('font-weight: bold', css)

    def test_ipr_est_lu_du_registre_et_affiche_en_italique(self):
        self.source(ipr=True)
        self.app.session_state.authenticated=True
        self.app.run()
        self.app.radio[0].set_value('Courses').run()
        self.assertFalse(self.app.exception)
        html = next(item.proto.body for item in self.app.get('html') if 'Indice de performance relative' in item.proto.body)
        self.assertIn('<em>IPR · Score (/100)</em>', html)
        self.assertIn('<em>EXPÉRIMENTAL — NON UTILISÉ DANS LES PRONOSTICS</em>', html)
        self.assertIn('<em>0</em>', html)
        self.assertIn('<em>—</em>', html)
        self.assertIn('&lt;ambiguë&gt;', html)
        self.assertIn('**Gagnant potentiel direct : 1 — Cheval test 1**',
                      [item.value for item in self.app.markdown])

    def test_ipr_affiche_en_police_normale_apres_promotion(self):
        from trot_analytics.observations import tableau_observations
        from trot_analytics.usages import IPR, PRODUCTION

        labels = IPR.libelles
        html = tableau_observations([{'N°': 1, 'Cheval': 'Test', labels['ipr_version']: 'v2',
                                    labels['ipr_score']: 75, labels['ipr_statut']: PRODUCTION}], IPR)
        self.assertIn('<td>75</td>', html)
        self.assertNotIn('<em>', html)

    def test_cumul_filtre_et_fiche_cheval(self):
        self.source(dual_profile=True)
        self.app.session_state.authenticated=True
        self.app.run()
        self.app.radio[0].set_value('Courses').run()
        self.app.multiselect(key='profils_filtre').set_value(['Haut potentiel']).run()
        self.assertFalse(self.app.exception)
        self.assertEqual(list(self.app.dataframe[0].value['N°']), [1, 2])
        fiche = next(widget for widget in self.app.selectbox if widget.label == 'Fiche cheval')
        fiche.set_value(0).run()
        self.assertFalse(self.app.exception)
        self.assertTrue(any('Geny : preuves des deux profils' in x.value for x in self.app.text))
        badge = self.app.get('html')[-1].proto.body
        self.assertIn('★ Crack confirmé', badge)
        self.assertIn('◆ Haut potentiel', badge)
        self.assertIn('#ffdf75', badge)
        self.assertIn('#75eee1', badge)

    def test_cote_horodatee_visible_sans_selection_de_marche(self):
        self.source(odds=True)
        self.app.session_state.authenticated=True
        self.app.run()
        self.app.radio[0].set_value('Courses').run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.dataframe[0].value['Cote PMU'].iloc[0], 7.5)
        self.assertTrue(any('Dernier relevé PMU à' in x.value for x in self.app.caption))
        self.assertTrue(any('TOP3 Cotes indisponible' in x.value for x in self.app.caption))

    def test_courses_charge_le_top3_cotes_meme_si_un_ancien_module_est_en_memoire(self):
        from types import ModuleType
        from trot_analytics import logic

        legacy = ModuleType('logic')
        for name in ('records', 'number', 'timestamp', 'result_matching'):
            setattr(legacy, name, getattr(logic, name))
        legacy.selected = lambda rows, method: {'direct': [], 'ml': []}[method]
        self.source(market_top3=True)
        self.app.session_state.authenticated = True
        with patch.dict('sys.modules', {'logic': legacy}):
            self.app.run()
            self.app.radio[0].set_value('Courses').run()
        self.assertFalse(self.app.exception)
        self.assertIn('**TOP3 Cotes** · 3 — 2 — 1', [item.value for item in self.app.markdown])

    def test_performance_real_page_and_filters(self):
        self.source()
        d=self.today-timedelta(days=1)
        t=datetime.combine(d,time(12),ZoneInfo('Europe/Paris'))
        row={'Clé course (technique)':d.isoformat()+'|VINCENNES|R1C1',
             'Date':d.isoformat(),'Course R/C':'R1C1','Hippodrome':'VINCENNES','Départ (Paris)':t.isoformat(),
             'Arrivée · Vérifiée UTC':(t+timedelta(minutes=15)).isoformat(),
             'Évaluation · État':'EVALUE','Arrivée · N° officiels':'1,2,3',
             'TOP3 direct · Chevaux':'1,2,4','TOP3 direct · Heure calcul UTC':(t-timedelta(hours=1)).isoformat(),
             'TOP3 direct · Chevaux à l’arrivée (0–3)':2,'TOP3 direct · Matching (%)':66.67,
             'TOP3 ML · Chevaux':'4,5,6','TOP3 ML · Chevaux à l’arrivée (0–3)':0,
             'TOP3 ML · Matching (%)':0,'ML · Statut':'ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE',
             'TOP3 direct · Noms':'A · B · D','TOP3 ML · Noms':'D · E · F',
             'Arrivée · Noms officiels':'A · B · C',
             'Gagnant potentiel direct · N°':'1','Gagnant potentiel direct · Nom':'A',
             'Gagnant potentiel direct · Rang officiel':'1','Gagnant potentiel direct · Verdict':'Trouvé',
             'Gagnant potentiel ML · N°':'4','Gagnant potentiel ML · Nom':'ENTRAINEUR',
             'Gagnant potentiel ML · Rang officiel':'7','Gagnant potentiel ML · Verdict':'Non trouvé'}
        data=self.api.spreadsheets().values().batchGet().execute.return_value['valueRanges']
        data[1]={'values':[list(row),list(row.values())]}
        self.app.session_state.authenticated=True
        self.app.run()
        self.app.radio[0].set_value('Résultats').run()
        self.app.date_input[0].set_value(d).run()
        result = self.app.dataframe[0].value
        columns = ['Direct', 'Direct · Noms', 'ML', 'ML · Noms', 'Podium enregistré', 'Podium · Noms']
        self.assertEqual(list(result.columns[1:7]), columns)
        self.assertEqual(result.iloc[0][columns].tolist(),
                         ['1,2,4', 'A · B · D', '4,5,6', 'D · E · F', '1,2,3', 'A · B · C'])
        self.assertEqual(result.iloc[0]['Gagnant potentiel direct · Verdict'],'Trouvé')
        self.assertEqual(result.iloc[0]['Gagnant potentiel ML · Rang officiel'],'7')
        self.assertEqual(result.iloc[0]['Gagnant potentiel ML · Nom'],'D')
        self.assertEqual(result.iloc[0]['Arrivée lue dans le flux PMU (Paris)'],d.strftime('%d/%m/%Y')+' 12:15')
        self.app.radio[0].set_value('Performance').run()
        self.assertEqual(len(self.app.exception),0)
        self.assertEqual(len(self.app.error),0)
        self.assertEqual(self.app.metric[0].value,'1/1')
        self.assertEqual(len(self.app.get('plotly_chart')),2)
        self.app.radio(key='performance_mode').set_value('Par jour').run()
        self.assertEqual(len(self.app.exception),0)
        self.assertEqual(len(self.app.get('plotly_chart')),2)
