import unittest
from unittest.mock import patch
from urllib.parse import unquote
from pmu_geny.sync_google_sheets import lire_feuille_complete, plan_sheet


class Response:
    headers={}
    def __init__(self,code,values):self.status_code=code;self.values=values
    def json(self):return self.values if isinstance(self.values,dict) else {'values':self.values}


class PaginationTests(unittest.TestCase):
    def test_cle_apres_5000_ne_se_reinsere_pas(self):
        class Session:
            def get(self,url,**kwargs):
                values=[]
                for name in kwargs['params']['ranges']:
                    r=name.split('!')[1]
                    if r=='A1:C2000':rows=[['cle_performance','cheval','classement']]
                    elif r=='A2001:C4000':rows=[]
                    elif r=='A4001:C6000':rows=[[]]*1000+[['id|date|piste','TEST','3']]
                    else:raise AssertionError(r)
                    values.append({'range':name,'values':rows})
                return Response(200,{'valueRanges':values})
        values=lire_feuille_complete(Session(),'https://unused','Historique chevaux',
                                     {'gridProperties':{'rowCount':6000,'columnCount':3}})
        self.assertEqual(values[5000],['id|date|piste','TEST','3'])
        existing=[dict(zip(values[0],row)) for row in values[1:]]
        _,updates,appends=plan_sheet(values[0],existing,{'x':{'cle_performance':'id|date|piste','cheval':'TEST','classement':'3'}},'Historique chevaux')
        self.assertEqual(updates,[]);self.assertEqual(appends,[])

    def test_groupe_les_pages_et_conserve_les_trous_entre_appels(self):
        class Session:
            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                ranges = kwargs['params']['ranges']
                self.calls.append(ranges)
                values = []
                for name in ranges:
                    cell = name.split('!')[1]
                    rows = {'A1:J2000': [['cle_performance']],
                            'A20001:J22000': [['carriere']]}.get(cell, [])
                    values.append({'range': name, 'values': rows})
                return Response(200, {'valueRanges': values})

        session = Session()
        values = lire_feuille_complete(session, 'base', 'Historique chevaux',
                                      {'gridProperties': {'rowCount': 22000, 'columnCount': 10}})
        self.assertEqual([len(ranges) for ranges in session.calls], [10, 1])
        self.assertEqual(values[19999], [])
        self.assertEqual(values[20000], ['carriere'])

    def test_page_incomplete_arrete_lecture(self):
        class Session:
            def get(self,url,**kwargs):return Response(403,[])
        with self.assertRaisesRegex(RuntimeError,'Lecture incomplete'):
            lire_feuille_complete(Session(),'unused','Historique chevaux',{'gridProperties':{'rowCount':6000,'columnCount':19}})

    def test_429_retente_sans_prendre_une_page_vide_pour_un_succes(self):
        class Session:
            n=0
            def get(self,url,**kwargs):
                self.n+=1
                return Response(429,[]) if self.n==1 else Response(200,{'valueRanges':[
                    {'range':kwargs['params']['ranges'][0],'values':[['header'],['valeur']]}]})
        session=Session()
        with patch('time.sleep'):
            result=lire_feuille_complete(session,'unused','Historique chevaux',{'gridProperties':{'rowCount':2,'columnCount':1}})
        self.assertEqual(result,[['header'],['valeur']]);self.assertEqual(session.n,2)

    def test_dimensions_absentes_refusees(self):
        with self.assertRaises(ValueError):lire_feuille_complete(None,'unused','Historique chevaux',{})

    def test_variantes_meme_cle_conservees_sans_ecrasement_ni_reinsertion(self):
        headers=['cle_performance','cheval','classement','source_url']
        existing=[{'cle_performance':'id|date|piste','cheval':'TEST','classement':'3','source_url':'preuve A'},
                  {'cle_performance':'id|date|piste','cheval':'TEST','classement':'4','source_url':'preuve B'}]
        incoming={'x':{'cle_performance':'id|date|piste','cheval':'TEST','classement':'3','source_url':'preuve A'}}
        _,updates,appends=plan_sheet(headers,existing,incoming,'Historique chevaux')
        self.assertEqual(updates,[]);self.assertEqual(appends,[])


if __name__=='__main__':unittest.main()
