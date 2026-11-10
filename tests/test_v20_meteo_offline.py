import tempfile,unittest,json
from pathlib import Path
from datetime import datetime,timedelta,timezone
from pmu_geny.contexte_meteo_v20 import collecter_meteo
from pmu_geny.ml_v19 import _valid_context,features,FEATURES

class TestContexteMeteo(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
  self.now=datetime(2026,11,15,14,20,tzinfo=timezone.utc)
  self.course={'date':'2026-11-15','code':'R2C1','depart':'2026-11-15T16:30:00+01:00','nombre_declares':12,'hippodrome':'Vincennes'}
  self.resolve=lambda *args:{'latitude':48.84,'longitude':2.43,'precision':'ville_voisine_pas_piste'}
  self.request=lambda url:{'hourly':{'time':['2026-11-15T15:00','2026-11-15T16:00'],
       'precipitation':[0.1,2.3],'wind_speed_10m':[8,21],
       'temperature_2m':[10,13.2],'relative_humidity_2m':[71,83]}}
 def test_weather_ingested_before_depart(self):
  self.assertEqual(collecter_meteo(self.root,self.course,self.now,self.request,self.resolve),'METEO_CAPTUREE_4')
  context=_valid_context(self.root,self.course,self.now+timedelta(minutes=1))
  self.assertEqual(context[('*','meteo_pluie_mm')],2.3)
  self.assertEqual(context[('*','meteo_vent_kmh')],21.)
  self.assertEqual(context[('*','meteo_temperature_c')],13.2)
  self.assertEqual(context[('*','meteo_humidite_pct')],83.)
  self.assertTrue(all('cote' not in f for f in FEATURES))
 def test_no_postdeparture_weather(self):
  status=collecter_meteo(self.root,self.course,self.now+timedelta(hours=3),self.request,self.resolve)
  self.assertEqual(status,'APRES_DEPART');self.assertFalse((self.root/'contextes').exists())
 def test_missing_values_not_faked(self):
  blank=lambda url:{'hourly':{'time':['2026-11-15T16:00'],'precipitation':[None]}}
  with self.assertRaises(ValueError):collecter_meteo(self.root,self.course,self.now,blank,self.resolve)
  self.assertFalse((self.root/'contextes'/'2026-11-15_R2C1.json').exists())
 def test_no_network_call_when_recent(self):
  collecter_meteo(self.root,self.course,self.now,self.request,self.resolve)
  def fail(*args):raise AssertionError('unexpected request')
  self.assertEqual(collecter_meteo(self.root,self.course,self.now+timedelta(minutes=15),fail,fail),'METEO_RECENTE')
if __name__=='__main__':unittest.main()
