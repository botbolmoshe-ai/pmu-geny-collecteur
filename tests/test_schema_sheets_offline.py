import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pmu_geny import historiques_incrementaux as inc
from pmu_geny.kpi_registre import calculer_kpi,plan_kpi
from pmu_geny.moteur_sheets import SynchroniseurSheets,regrouper_cellules
from pmu_geny.sync_google_sheets import canonical_headers,RETIRED_SHEET_COLUMNS,source_rows
from test_v26_chaine_offline import SheetsSession,Response


class ColonnesSession(SheetsSession):
    def post(self,url,**kwargs):
        if 'requests' not in kwargs['json']:return super().post(url,**kwargs)
        self.writes.append((url,kwargs['json']))
        for request in kwargs['json']['requests']:
            if 'deleteDimension' in request:
                r=request['deleteDimension']['range'];tab=list(self.tables)[r['sheetId']]
                for row in self.tables[tab]:del row[r['startIndex']:r['endIndex']]
            elif 'appendDimension' in request:
                r=request['appendDimension'];tab=list(self.tables)[r['sheetId']]
                for row in self.tables[tab]:row.extend(['']*r['length'])
        return Response({})


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name)
        env=patch.dict('os.environ',{'PMU_SHEETS_CONTROLES':str(self.cache/'controles.jsonl')})
        env.start();self.addCleanup(env.stop)

    def test_retrait_trois_onglets_sans_decalage_ni_recreation_au_deuxieme_passage(self):
        session=ColonnesSession()
        session.tables['Historique chevaux']=[
            ['identifiant_cheval','rncn','cheval','driver_jockey','extraction_utc','cle_performance','ferrure'],
            ['123456','R1C1','Test','Ancien','2026-11-01T12:00:00+00:00','perf','D4']]
        session.tables['Courses & Prévisions']=[
            ['course_key','numero','ML · Probabilité calibrée','Experts · Disponibilité par source','PMU · Complétude fiche'],
            ['k','1','0.5','Ancien','Ancien']]
        session.tables['Résultats & Analyse']=[
            ['course_key','score_cotes','score_direct','conclusion','top3_ml_numeros'],
            ['k','2','0','Ancien','']]
        source={'Historique chevaux':{'perf':{'identifiant_cheval':'123456','cheval':'Test',
            'extraction_utc':'2026-11-01T12:00:00+00:00','cle_performance':'perf','ferrure':'D4'}},
            'Courses & Prévisions':{'k':{'course_key':'k','numero':'1','couverture_experts':'PMU reçu',
                                      'actuel_statut':'FERRURE_DISPONIBLE_SOURCEE'}},
            'Résultats & Analyse':{'k':{'course_key':'k','score_direct':0,'conclusion':'Direct 0/3'}}}
        engine=SynchroniseurSheets(self.cache,'fake-schema',session=session)
        engine.synchroniser_tables(source,scope='TEST',allow_structure=True,full_source=True)
        structural=sum('requests' in x[1] for x in session.writes)
        second=engine.synchroniser_tables(source,scope='TEST',allow_structure=True,full_source=True)
        self.assertEqual(sum('requests' in x[1] for x in session.writes),structural)
        for tab in source:
            heads=canonical_headers(session.tables[tab][0])
            self.assertFalse(set(heads)&RETIRED_SHEET_COLUMNS[tab])
            self.assertEqual(len(session.tables[tab]),2)
            self.assertEqual(second[tab]['lignes_ajoutees'],0)
            self.assertEqual(second[tab]['cellules_actualisees'],0)
        h=dict(zip(canonical_headers(session.tables['Historique chevaux'][0]),session.tables['Historique chevaux'][1]))
        self.assertEqual((h['cle_performance'],h['cheval'],h['ferrure']),('perf','Test','D4'))
        self.assertIn('Capture historique · UTC',session.tables['Historique chevaux'][0])
        r=dict(zip(canonical_headers(session.tables['Résultats & Analyse'][0]),session.tables['Résultats & Analyse'][1]))
        self.assertEqual(r['score_direct'],0)

    def test_publication_exclut_les_champs_retires_et_garde_le_ml_actif(self):
        raw={'Courses & Prévisions':{'k':{'course_key':'2026-11-17|VINCENNES|R3C1','numero':'1',
             'date_course':'2026-11-17','ml_proba_podium':0.5,'ml_top3':'OUI','ml_rang':1,
             'top3_cotes_top3':'OUI'}},'Historique chevaux':{},'Résultats & Analyse':{}}
        original=copy.deepcopy(raw)
        with patch('pmu_geny.sync_google_sheets.source_rows',return_value=raw):
            published=SynchroniseurSheets(self.cache,'fake',session=SheetsSession()).source()
        row=published['Courses & Prévisions']['k']
        self.assertEqual(row['ml_top3'],'OUI');self.assertEqual(row['ml_rang'],1)
        self.assertNotIn('ml_proba_podium',row);self.assertNotIn('top3_cotes_top3',row)
        self.assertEqual(raw,original)

    def test_date_capture_source_et_rang_arrivee_sans_manifeste(self):
        day='2026-11-16';course={'date':day,'code':'R1C1','depart':day+'T15:00:00+01:00','hippodrome':'VINCENNES'}
        inc.ecrire(self.cache/'sources_pmu'/f'programme_{day}.json',{'programme':[course]})
        inc.ecrire(self.cache/'partants_actuels'/f'{day}_R1C1.json',{'chevaux':{'1':{'nom':'Test'}}})
        inc.ecrire(self.cache/'arrivees'/f'{day}_R1C1.json',{'arrivee':[
            {'numero':2,'rang':1},{'numero':3,'rang':2},{'numero':1,'rang':3}]})
        inc.ecrire(self.cache/'etat_persistant.json',{'chevaux':{'123456':{'nom':'Test','statut':'COMPLET'}}})
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json',{'statut':'COMPLET',
            'extrait_utc':'2026-11-10T13:00:00+01:00','performances':[{'date':'2026-11-01',
            'hippodrome':'Vincennes','classement':'2','discipline':'Attelé','distance_m':'2700'}]})
        rows=source_rows(self.cache)
        self.assertEqual(next(iter(rows['Historique chevaux'].values()))['extraction_utc'],'2026-11-10T12:00:00+00:00')
        self.assertEqual(next(iter(rows['Courses & Prévisions'].values()))['arrivee_rang'],3)
        self.assertEqual(next(iter(rows['Résultats & Analyse'].values()))['etat_ml'],'ML_NON_ENTRAINE')

    def test_mises_a_jour_massives_regroupees_sans_ecraser_les_trous(self):
        updates=[(row,3,str(row)) for row in range(2,18500) if row not in (10,200)]
        updates.extend([(5,1,0),(7,1,'A'),(8,1,'B')])
        blocks=regrouper_cellules('Historique chevaux',updates)
        self.assertLess(len(blocks),20)
        rebuilt={}
        import re
        for block in blocks:
            cell=block['range'].split('!')[1];m=re.fullmatch(r'([A-Z]+)(\d+)',cell)
            col=ord(m[1])-64
            for offset,value in enumerate(block['values']):rebuilt[(int(m[2])+offset,col)]=value[0]
        self.assertEqual(rebuilt,{(r,c):v for r,c,v in updates})
        self.assertNotIn((10,3),rebuilt);self.assertNotIn((200,3),rebuilt)

    def test_kpi_ml_compte_les_selections_et_nettoie_les_formules_orphelines(self):
        rows={str(i):{'course_key':'k','ml_rang':i,'ml_top3':'OUI' if i<=3 else ''} for i in range(1,5)}
        metrics=calculer_kpi(self.cache,{'Courses & Prévisions':rows,'Historique chevaux':{},'Résultats & Analyse':{}})
        self.assertEqual(metrics['Participations avec sélection ML publiée'][0],3)
        plan=plan_kpi([['Dimension','Indicateur','Valeur','Définition','Total'],
            ['','','','',10],['ML','Participations avec sélection ML publiée',4,'Ancien',4]],metrics)
        self.assertEqual(plan[0]['values'],[['']]);self.assertEqual(plan[1]['values'][0][0],3)
