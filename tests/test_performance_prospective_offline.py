import hashlib
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from pmu_geny.echeances_production import sauver,lire
from pmu_geny.performance_prospective import mesurer
from pmu_geny.partants_actuels_v21 import qualifier_ferrure


class ProspectiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name);self.now=datetime(2026,11,17,18,tzinfo=timezone.utc)
        self.depart=self.now-timedelta(hours=1);self.key='2026-11-17_R3C1'
        versions={}
        for mode,numbers in [('direct',(1,4,5)),('ml',(1,2,3))]:
            path=self.cache/'pronostics'/f'{self.key}_{mode}.json'
            doc={'date':'2026-11-17','course':'R3C1','depart':self.depart.isoformat(),
                 'calcul_utc':(self.depart-timedelta(minutes=10)).isoformat(),'top3':[{'numero':n} for n in numbers]}
            sauver(path,doc)
            versions[mode]={'fichier':str(path.relative_to(self.cache)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                            'calcul_utc':doc['calcul_utc'],'publication_utc':(self.depart-timedelta(minutes=9)).isoformat()}
        self.certificate={'depart':self.depart.isoformat(),'versions':versions}
        sauver(self.cache/'publications'/f'{self.key}.json',self.certificate)
        sauver(self.cache/'arrivees'/f'{self.key}.json',{'source':'PMU_API_PARTICIPANTS',
            'verifie_utc':self.now.isoformat(),'arrivee':[{'numero':n,'rang':n} for n in (1,2,3)]})

    def test_score_apparie_publie_pas_score_entrainement(self):
        r=mesurer(self.cache,self.now)
        self.assertEqual(r['courses'],1);self.assertEqual(r['moyenne_ml'],3)
        self.assertEqual(r['moyenne_direct'],1);self.assertEqual(r['ecart_ml_direct'],2)

    def test_hash_corrompu_et_publication_apres_depart_exclus(self):
        self.certificate['versions']['ml']['publication_utc']=self.now.isoformat()
        sauver(self.cache/'publications'/f'{self.key}.json',self.certificate)
        self.assertEqual(mesurer(self.cache,self.now)['courses'],0)
        self.certificate['versions']['ml']['publication_utc']=(self.depart-timedelta(minutes=9)).isoformat()
        self.certificate['versions']['ml']['sha256']='invalide'
        sauver(self.cache/'publications'/f'{self.key}.json',self.certificate)
        self.assertEqual(mesurer(self.cache,self.now)['courses'],0)

    def test_version_archivee_retrouvee_sans_utiliser_nouveau_calcul_non_publie(self):
        path=self.cache/self.certificate['versions']['ml']['fichier']
        original=lire(path);sauver(self.cache/'pronostics/versions'/f'{self.key}_ml_ancien.json',original)
        sauver(path,{**original,'top3':[{'numero':n} for n in (6,7,8)]})
        self.assertEqual(mesurer(self.cache,self.now)['moyenne_ml'],3)

    def test_ferrure_inconnue_reste_vide_et_convention_est_distincte(self):
        p=qualifier_ferrure({'ferrure':'INCONNU_X'})
        self.assertEqual(p['ferrure'],'');self.assertEqual(p['ferrure_brute'],'INCONNU_X')
        self.assertEqual(qualifier_ferrure(p)['ferrure_qualification'],'CODE_INCONNU')
        p=qualifier_ferrure({'ferrure':'F','provenance_champs':{'ferrure':{'convention':'PMU'}}})
        self.assertEqual(p['ferrure_qualification'],'CONVENTION_PMU')


if __name__=='__main__':unittest.main()
