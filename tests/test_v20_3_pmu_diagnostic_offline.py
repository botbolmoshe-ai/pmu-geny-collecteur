import unittest
from datetime import datetime
from pmu_geny.auto_v18 import programme_diagnostic

class DiagnosticPMUTest(unittest.TestCase):
    def setUp(self):
        self.date='2026-11-10'
        self.depart=int(datetime.fromisoformat('2026-11-10T15:30:00+01:00').timestamp()*1000)
        self.course={'numOrdre':8,'heureDepart':self.depart,'nombreDeclaresPartants':18,'libelle':'Prix de Beauvais','specialite':'TROT_ATTELE'}
    def test_country_in_reunion(self):
        data={'programme':{'reunions':[{'numOfficiel':2,'pays':'FRA','hippodrome':{'libelleLong':'Vincennes'},'courses':[self.course]}]}}
        courses,diag=programme_diagnostic(data,self.date)
        self.assertEqual([c['code'] for c in courses],['R2C8'])
        self.assertEqual(diag['courses_retenues'],1)
    def test_country_in_hippodrome(self):
        data={'programme':{'reunions':[{'numOfficiel':2,'hippodrome':{'codePays':'FR','libelleLong':'Vincennes'},'courses':[self.course]}]}}
        courses,diag=programme_diagnostic(data,self.date)
        self.assertEqual(len(courses),1)
    def test_unknown_not_assumed_france(self):
        data={'programme':{'reunions':[{'numOfficiel':2,'hippodrome':{'libelleLong':'Vincennes'},'courses':[self.course]}]}}
        courses,diag=programme_diagnostic(data,self.date)
        self.assertEqual(courses,[])
        self.assertEqual(diag['reunions_pays_inconnu'],1)
        self.assertEqual(diag['courses_recues'],1)
    def test_invalid_partants_reported(self):
        data={'reunions':[{'numOfficiel':2,'pays':'FRA','courses':[{**self.course,'nombreDeclaresPartants':None}]}]}
        courses,diag=programme_diagnostic(data,self.date)
        self.assertEqual(courses,[])
        self.assertEqual(diag['exclusions']['partants_absents_ou_invalides'],1)

if __name__=='__main__':unittest.main()
