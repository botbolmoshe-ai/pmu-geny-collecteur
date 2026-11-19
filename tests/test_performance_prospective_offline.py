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

    def test_depart_apparie_au_direct_sans_publication_ml(self):
        proof = self.certificate['versions']['direct']
        path = self.cache / proof['fichier']
        doc = lire(path)
        doc['classement_complet'] = [{'numero': n} for n in (1, 2, 3, 4, 5)]
        doc['candidat_depart'] = {'poids': 0.10, 'top3': [1, 2, 3], 'partants_avec_forme_meme_depart': 2}
        sauver(path, doc)
        proof['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        proof['lecture_sheets_utc'] = proof['publication_utc']
        (self.cache / 'publications' / f'{self.key}.json').unlink()
        sauver(self.cache / 'publications' / 'direct' / f'{self.key}.json',
               {'depart': self.depart.isoformat(), 'versions': {'direct': proof}})

        report = mesurer(self.cache, self.now)
        self.assertEqual(report['courses'], 0)
        variant = report['candidat_depart']
        self.assertEqual((variant['courses'], variant['direct_evaluable']), (1, 1))
        self.assertEqual((variant['moyenne'], variant['moyenne_direct']), (3, 1))
        self.assertIsNone(variant['comparaison'])

        proof.pop('lecture_sheets_utc')
        sauver(self.cache / 'publications' / 'direct' / f'{self.key}.json',
               {'depart': self.depart.isoformat(), 'versions': {'direct': proof}})
        self.assertEqual(mesurer(self.cache, self.now)['candidat_depart']['courses'], 0)

    def test_ferrure_inconnue_reste_vide_et_convention_est_distincte(self):
        p=qualifier_ferrure({'ferrure':'INCONNU_X'})
        self.assertEqual(p['ferrure'],'');self.assertEqual(p['ferrure_brute'],'INCONNU_X')
        self.assertEqual(qualifier_ferrure(p)['ferrure_qualification'],'CODE_INCONNU')
        p=qualifier_ferrure({'ferrure':'F','provenance_champs':{'ferrure':{'convention':'PMU'}}})
        self.assertEqual(p['ferrure_qualification'],'CONVENTION_PMU')


    def test_report_de_depart_ne_melange_pas_les_horaires_des_attestations(self):
        new_departure = self.depart + timedelta(minutes=30)
        readback = new_departure - timedelta(minutes=5)
        doc = lire(self.cache / self.certificate['versions']['direct']['fichier'])
        doc.update(
            depart=new_departure.isoformat(),
            calcul_utc=(readback - timedelta(minutes=1)).isoformat(),
            classement_complet=[{'numero': n} for n in (1, 2, 3, 4, 5)],
            candidat_depart={'poids': 0.10, 'top3': [1, 2, 3], 'partants_avec_forme_meme_depart': 2},
        )
        path = self.cache / 'pronostics' / 'versions' / f'{self.key}_direct_report.json'
        sauver(path, doc)
        direct_proof = {
            'fichier': str(path.relative_to(self.cache)),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'calcul_utc': doc['calcul_utc'],
            'lecture_sheets_utc': readback.isoformat(),
            'publication_utc': readback.isoformat(),
        }
        sauver(self.cache / 'publications' / 'direct' / f'{self.key}.json', {
            'depart': new_departure.isoformat(), 'versions': {'direct': direct_proof},
        })

        report = mesurer(self.cache, self.now)
        self.assertEqual(report['courses'], 1)
        self.assertEqual(report['resultats'][0]['depart'], self.depart.isoformat())
        self.assertEqual(report['candidat_depart']['courses'], 1)
        self.assertEqual(report['candidat_depart']['moyenne'], 3)

        arrival = self.cache / 'arrivees' / f'{self.key}.json'
        sauver(arrival, {**lire(arrival), 'verifie_utc': new_departure.isoformat()})
        self.assertEqual(mesurer(self.cache, self.now)['candidat_depart']['courses'], 0)


if __name__=='__main__':unittest.main()
