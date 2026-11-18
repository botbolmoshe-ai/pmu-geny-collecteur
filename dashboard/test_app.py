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

    def source(self,history=True):
        from quality_dates import VALUE,TOTAL
        day=self.today.isoformat();depart=datetime.combine(self.today,time(12),ZoneInfo('Europe/Paris'))
        courses=[{'Clé course (technique)':day+'|R1C1','Date':day,'Course R/C':'R1C1','Hippodrome':'VINCENNES',
            'Départ (Paris)':depart.isoformat(),'Discipline':'Attelé','Distance (m)':2700,
            'N°':n,'Cheval':f'Cheval test {n}','Non-partant (NP)':'PARTANT',
            'TOP3 direct · Rang':n,'TOP3 direct · Sélection':'OUI','ML · Rang':n,'ML · Sélection':'OUI',
            'Historique · Nb performances récupérées':2,'Ferrure · Course du jour':'D4',
            'Âge (ans)':5,'Sexe':'Hongre','Gains carrière (€)':0} for n in (1,2,3)]
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
        self.assertTrue(any('Version interface : 2026.11.18.1' in x.value for x in self.app.caption))

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


    def test_performance_real_page_and_filters(self):
        self.source()
        d=self.today-timedelta(days=1)
        t=datetime.combine(d,time(12),ZoneInfo('Europe/Paris'))
        row={'Clé course (technique)':d.isoformat()+'|VINCENNES|R1C1',
             'Date':d.isoformat(),'Hippodrome':'VINCENNES','Départ (Paris)':t.isoformat(),
             'Arrivée · Vérifiée UTC':(t+timedelta(minutes=15)).isoformat(),
             'Évaluation · État':'EVALUE','Arrivée · N° officiels':'1,2,3',
             'TOP3 direct · Chevaux':'1,2,4','TOP3 direct · Heure calcul UTC':(t-timedelta(hours=1)).isoformat(),
             'TOP3 direct · Chevaux à l’arrivée (0–3)':2,'TOP3 direct · Matching (%)':66.67,
             'TOP3 ML · Chevaux':'4,5,6','TOP3 ML · Chevaux à l’arrivée (0–3)':0,
             'TOP3 ML · Matching (%)':0,'ML · Statut':'ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE'}
        data=self.api.spreadsheets().values().batchGet().execute.return_value['valueRanges']
        data[1]={'values':[list(row),list(row.values())]}
        self.app.session_state.authenticated=True
        self.app.run()
        self.app.radio[0].set_value('Performance').run()
        self.assertEqual(len(self.app.exception),0)
        self.assertEqual(len(self.app.error),0)
        self.assertEqual(self.app.metric[0].value,'1/1')
        self.assertEqual(len(self.app.get('plotly_chart')),2)
        self.app.radio(key='performance_mode').set_value('Par jour').run()
        self.assertEqual(len(self.app.exception),0)
        self.assertEqual(len(self.app.get('plotly_chart')),2)
