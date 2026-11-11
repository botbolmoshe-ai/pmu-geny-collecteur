import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pmu_geny.auto_v18 import programme_diagnostic
from pmu_geny.selection_metier_v20_4 import niveau,discipline_course
from pmu_geny.planification_v20_2 import selectionner_courses

class SelectionTrotTest(unittest.TestCase):
    def setUp(self):
        self.date='2026-11-10'
        self.time=int(datetime(2026,11,10,15,30,tzinfo=ZoneInfo('Europe/Paris')).timestamp()*1000)
    def c(self,n,disc='TROT_ATTELE',nb=14,alloc=21000):
        return {'numOrdre':n,'heureDepart':self.time,'nombreDeclaresPartants':nb,'libelle':'Prix test',
                'specialite':disc,'allocation':alloc}
    def run_prog(self,reunions):
        return programme_diagnostic({'reunions':reunions},self.date)
    def r(self,rno,hip,courses,**kwargs):
        return {'numOfficiel':rno,'pays':'FRA','hippodrome':{'libelleLong':hip},'courses':courses,**kwargs}
    def test_trot_exclusive_et_priorites(self):
        courses,diag=self.run_prog([
            self.r(1,'Vincennes',[self.c(1),self.c(2,'PLAT')]),
            self.r(2,'Caen',[self.c(1,'TROT_MONTE'),self.c(2,'OBSTACLE')]),
            self.r(3,'Fontainebleau',[self.c(1)])])
        self.assertEqual([(c['code'],c['priorite_metier']) for c in courses],[('R1C1','P1'),('R2C1','P2')])
        self.assertEqual(diag['courses_p1'],1)
        self.assertEqual(diag['courses_p2'],1)
        self.assertEqual(diag['exclusions']['metier_hors_trot'],2)
        self.assertEqual(diag['exclusions']['metier_hippodrome_hors_selection'],1)
        self.assertEqual(len(diag['decisions_metier']),5)
    def test_absence_discipline_pas_deduction_depuis_nom(self):
        course=self.c(1);course.pop('specialite');course['libelle']='Grand Prix de Trot'
        output,diag=self.run_prog([self.r(1,'Vincennes',[course])])
        self.assertEqual(output,[])
        self.assertEqual(diag['exclusions']['metier_discipline_inconnue'],1)
    def test_specialite_unique_reunion(self):
        course=self.c(1);course.pop('specialite')
        output,_=self.run_prog([self.r(1,'Vincennes',[course],specialites=['TROT_ATTELE'])])
        self.assertEqual(len(output),1)
    def test_mix_reunion_non_suffisant(self):
        course=self.c(1);course.pop('specialite')
        output,_=self.run_prog([self.r(1,'Vincennes',[course],specialites=['TROT_ATTELE','PLAT'])])
        self.assertEqual(output,[])
    def test_depart_hors_plage(self):
        outside=self.c(1)
        outside['heureDepart']=int(datetime(2026,11,10,22,15,tzinfo=ZoneInfo('Europe/Paris')).timestamp()*1000)
        output,diag=self.run_prog([self.r(1,'Vincennes',[outside])])
        self.assertEqual(output,[])
        self.assertEqual(diag['exclusions']['depart_hors_plage_08_19'],1)
    def test_groupe_et_allocation(self):
        c=self.c(1,alloc=41000)
        tier,reason,_=niveau(c,{},'Fontainebleau',14)
        self.assertEqual((tier,reason),('P1','ALLOCATION_ELEVEE'))
        c['allocation']=9000;c['categorie']='Groupe III'
        self.assertEqual(niveau(c,{},'Fontainebleau',14)[0],'P1')
    def test_p2_seuil(self):
        self.assertIsNone(niveau(self.c(1,nb=7),{},'Caen',7)[0])
        self.assertIsNone(niveau(self.c(1,alloc=9000),{},'Caen',14)[0])
    def test_horaire_prioritaire_puis_p1(self):
        t=datetime(2026,11,10,14,0,tzinfo=ZoneInfo('Europe/Paris'))
        def horse(code,hours,tier):return {'code':code,'depart':(t+timedelta(hours=hours)).isoformat(),'priorite_metier':tier}
        courses=[horse('R1C1',1.5,'P2'),horse('R2C1',1.5,'P1'),horse('R3C1',0.5,'P2')]
        selected=selectionner_courses(courses,t,'2026-11-10',[],True,{})
        self.assertEqual([c['code'] for c in selected],['R3C1','R2C1','R1C1'])
if __name__=='__main__': unittest.main()
