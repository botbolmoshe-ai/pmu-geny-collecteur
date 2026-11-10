import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pmu_geny.selection_metier_v20_4 import niveau, normaliser_hippodrome
from pmu_geny.auto_v18 import programme_diagnostic
from pmu_geny.planification_v20_2 import selectionner_courses

P=ZoneInfo('Europe/Paris')

class CorrectionsV205(unittest.TestCase):
    def course(self,n,heure=15,allocation=33000):
        return {'numOrdre':n,'heureDepart':int(datetime(2026,11,10,heure,30,tzinfo=P).timestamp()*1000),
                'nombreDeclaresPartants':14,'specialite':'TROT_ATTELE','allocation':allocation,'libelle':f'Prix {n}'}
    def test_vincennes_pmu_p1_sans_allocation_elevee(self):
        for hip in ('Vincennes','PARIS-VINCENNES','HIPPODROME DE PARIS-VINCENNES','Hippodrome de Vincennes'):
            with self.subTest(hip=hip):
                tier,raison,meta=niveau(self.course(1),{},hip,14)
                self.assertEqual((tier,raison),('P1','VINCENNES'))
                self.assertEqual(meta['hippodrome_normalise'],'vincennes')
    def test_reims_p2_normalise(self):
        tier,raison,meta=niveau(self.course(1,allocation=21000),{},'HIPPODROME DE REIMS',12)
        self.assertEqual((tier,raison),('P2','HIPPODROME_MAJEUR_P2'))
        self.assertEqual(meta['hippodrome_normalise'],'reims')
    def test_lyon_sites_distincts(self):
        self.assertEqual(normaliser_hippodrome('Hippodrome de Lyon-Parilly'),'lyon parilly')
        self.assertEqual(normaliser_hippodrome('Hippodrome de Lyon-La Soie'),'lyon la soie')
    def test_non_trot_exclu_memes_si_vincennes(self):
        c=self.course(1);c['specialite']='PLAT'
        self.assertIsNone(niveau(c,{},'HIPPODROME DE PARIS-VINCENNES',14)[0])
    def test_diagnostic_course_pmu_reclassee(self):
        r={'numOfficiel':2,'pays':'FRA','hippodrome':{'libelleLong':'HIPPODROME DE PARIS-VINCENNES'},
           'courses':[self.course(i,allocation=33000) for i in range(1,9)]}
        result,diag=programme_diagnostic({'reunions':[r]},'2026-11-10')
        self.assertEqual((len(result),diag['courses_p1'],diag['courses_p2']),(8,8,0))
    def test_course_terminee_non_preparee(self):
        now=datetime(2026,11,10,18,46,tzinfo=P)
        entries=[{'code':'R2C1','depart':datetime(2026,11,10,13,30,tzinfo=P).isoformat(),'priorite_metier':'P1'}]
        self.assertEqual(selectionner_courses(entries,now,'2026-11-10',[],True,{}),[])
    def test_preparation_demain_apres_18(self):
        now=datetime(2026,11,10,19,0,tzinfo=P)
        c={'code':'R1C1','depart':datetime(2026,11,11,14,30,tzinfo=P).isoformat(),'priorite_metier':'P1'}
        self.assertEqual(len(selectionner_courses([c],now,'2026-11-11',[],True,{})),1)
        self.assertEqual(selectionner_courses([c],now,'2026-11-11',[],False,{}),[])

if __name__=='__main__':unittest.main()
