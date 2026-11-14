import unittest
from unittest.mock import patch
from urllib.parse import unquote
from pmu_geny.sync_google_sheets import lire_feuille_complete, plan_sheet


class Response:
    headers={}
    def __init__(self,code,values):self.status_code=code;self.values=values
    def json(self):return {'values':self.values}


class PaginationTests(unittest.TestCase):
    def test_cle_apres_5000_ne_se_reinsere_pas(self):
        class Session:
            def get(self,url,**kwargs):
                r=unquote(url).split('!')[1]
                if r=='A1:C2000':return Response(200,[['cle_performance','cheval','classement']])
                if r=='A2001:C4000':return Response(200,[])
                if r=='A4001:C6000':return Response(200,[[]]*1000+[['id|date|piste','TEST','3']])
                raise AssertionError(r)
        values=lire_feuille_complete(Session(),'https://unused','Historique chevaux',
                                     {'gridProperties':{'rowCount':6000,'columnCount':3}})
        self.assertEqual(values[5000],['id|date|piste','TEST','3'])
        existing=[dict(zip(values[0],row)) for row in values[1:]]
        _,updates,appends=plan_sheet(values[0],existing,{'x':{'cle_performance':'id|date|piste','cheval':'TEST','classement':'3'}},'Historique chevaux')
        self.assertEqual(updates,[]);self.assertEqual(appends,[])

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
                return Response(429,[]) if self.n==1 else Response(200,[['header'],['valeur']])
        session=Session()
        with patch('time.sleep'):
            result=lire_feuille_complete(session,'unused','Historique chevaux',{'gridProperties':{'rowCount':2,'columnCount':1}})
        self.assertEqual(result,[['header'],['valeur']]);self.assertEqual(session.n,2)

    def test_dimensions_absentes_refusees(self):
        with self.assertRaises(ValueError):lire_feuille_complete(None,'unused','Historique chevaux',{})


if __name__=='__main__':unittest.main()
