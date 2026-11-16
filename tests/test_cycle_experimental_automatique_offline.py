import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from pmu_geny.cycle_ml_experimental import executer

class ExperimentalTests(unittest.TestCase):
    def test_demarre_sous_le_seuil_de_production_et_ne_promeut_pas(self):
        rows=[{'depart':f'2026-11-{d:02}T12:00:00+00:00',
               'capture_utc':f'2026-11-{d:02}T11:00:00+00:00',
               'verifie_utc':f'2026-11-{d:02}T13:00:00+00:00','y':n%2}
               for d in (12,13,14) for n in (1,2,3,4)]
        report={'statut':'EXPERIMENTAL_NON_CALIBRE_NON_DEPLOYE','modele_choisi_avant_test':'test',
                'test_ml':{'courses':1,'moyenne':1},'decoupage':{}}
        with tempfile.TemporaryDirectory() as folder, \
             patch('pmu_geny.cycle_ml_experimental.dataset',return_value=(rows,3)), \
             patch('pmu_geny.experience_ml.run',return_value=report) as fit:
            r=executer(folder,datetime.now(timezone.utc),'empreinte')
            self.assertEqual(r['statut'],report['statut']);self.assertFalse(r['promotion_production'])
            self.assertFalse((Path(folder)/'ml/modele.joblib').exists())
            self.assertEqual(executer(folder,datetime.now(timezone.utc),'empreinte')['execution'],'DONNEES_INCHANGEES')
            self.assertEqual(fit.call_count,1)
            for row in rows:row['verifie_utc']='2099-01-01T00:00:00+00:00'
            self.assertEqual(executer(folder,datetime.now(timezone.utc),'nouvelle')['statut'],'ATTENTE_DONNEES_TEMPORELLES')
            self.assertEqual(fit.call_count,1)
