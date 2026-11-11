import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pmu_geny.planification_v20_2 import selectionner_courses

T=ZoneInfo('Europe/Paris')
NOW=datetime(2026,11,10,18,0,tzinfo=T)

def race(code, departure):
    return {'code':code,'depart':departure.isoformat(),'date':departure.date().isoformat()}

class PlanningTests(unittest.TestCase):
    def test_day_before_as_soon_as_programme_available(self):
        c=[race('R1C1',NOW+timedelta(hours=14))]
        self.assertEqual(len(selectionner_courses(c,NOW.replace(hour=17),'2026-11-11',[],True,{})),1)
        self.assertEqual(len(selectionner_courses(c,NOW,'2026-11-11',[],True,{})),1)
        self.assertEqual(selectionner_courses(c,NOW,'2026-11-11',[],False,{}),[])
    def test_priority_and_no_future_on_light(self):
        c=[race('R1C1',NOW+timedelta(hours=5)),race('R1C2',NOW+timedelta(minutes=45)),race('R1C3',NOW+timedelta(hours=1,minutes=50))]
        self.assertEqual([x['code'] for x in selectionner_courses(c,NOW,'2026-11-10',[],True,{})],['R1C2','R1C3','R1C1'])
        self.assertEqual([x['code'] for x in selectionner_courses(c,NOW,'2026-11-10',[],False,{})],['R1C2'])
    def test_finished_only_in_4h_and_not_tomorrow(self):
        c=[race('R1C1',NOW-timedelta(minutes=10)),race('R1C2',NOW-timedelta(hours=5))]
        self.assertEqual([x['code'] for x in selectionner_courses(c,NOW,'2026-11-10',[],True,{})],['R1C1'])
        self.assertEqual(selectionner_courses(c,NOW,'2026-11-11',[],True,{}),[])
    def test_archived_excluded(self):
        c=[race('R1C1',NOW-timedelta(minutes=10))]
        self.assertEqual(selectionner_courses(c,NOW,'2026-11-10',[],True,{'courses':{'R1C1':{'etat':'TERMINE_ARCHIVE'}}}),[])
    def test_cap(self):
        c=[race(f'R1C{i}',NOW+timedelta(minutes=i*10)) for i in range(1,15)]
        self.assertEqual(len(selectionner_courses(c,NOW,'2026-11-10',[],True,{},max_courses=5)),5)

if __name__=='__main__':unittest.main()
