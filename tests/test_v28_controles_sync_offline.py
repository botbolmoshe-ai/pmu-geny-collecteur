import json
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from pmu_geny.controle_sync_sheets import BlocageSynchronisation,verifier_avant,verifier_apres,inventaire
from pmu_geny.sync_google_sheets import plan_sheet


class ControlesTests(unittest.TestCase):
    headers=['cle_performance','cheval','classement']
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.log=Path(self.tmp.name)/'controle.jsonl'
        self.env=patch.dict(os.environ,{'PMU_SHEETS_CONTROLES':str(self.log),'GITHUB_STEP_SUMMARY':str(Path(self.tmp.name)/'summary.md')})
        self.env.start();self.addCleanup(self.env.stop)
        self.console=patch('builtins.print');self.console.start();self.addCleanup(self.console.stop)

    def control(self,existing,incoming,appends=None,observed=None):
        if appends is None:_,_,appends=plan_sheet(self.headers,existing,incoming,'Historique chevaux')
        if observed is None:observed=inventaire(self.headers,existing)['keys']
        return verifier_avant(self.headers,existing,incoming,appends,observed_keys=observed)

    def test_rejouer_la_meme_source_ne_cree_aucune_ligne(self):
        source={'x':{'cle_performance':'1','cheval':'TEST','classement':'3'}}
        first=self.control([],source)
        verifier_apres(first,list(source.values()))
        second=self.control(list(source.values()),source)
        self.assertEqual(second['report']['ajouts_prevus'],0)
        verifier_apres(second,list(source.values()))

    def test_meme_cle_dans_deux_entrees_source_refusee(self):
        with self.assertRaisesRegex(BlocageSynchronisation,'SOURCE'):
            self.control([],{'a':{'cle_performance':'1'},'b':{'cle_performance':'1'}},appends=[])

    def test_proposition_de_reinsertion_refusee_avant_post(self):
        old=[{'cle_performance':'1','cheval':'TEST'}]
        with self.assertRaisesRegex(BlocageSynchronisation,'REINSERTION'):
            self.control(old,{'x':old[0]},appends=[['1','TEST','']])

    def test_lecture_tronquee_detectee_par_le_controle_independant(self):
        old=[{'cle_performance':'visible'}]
        with self.assertRaisesRegex(BlocageSynchronisation,'CONTROLE_INDEPENDANT'):
            self.control(old,{},observed=Counter({'visible':1,'apres_5000':1}))

    def test_doublons_de_valeurs_existants_bloquent_sans_supprimer(self):
        old=[{'cle_performance':'1','cheval':'TEST'}]*2
        with self.assertRaisesRegex(BlocageSynchronisation,'COPIES'):
            self.control(old,{})
        self.assertEqual(len(old),2)

    def test_variantes_existantes_de_meme_cle_sont_bloquees(self):
        old=[{'cle_performance':'1','cheval':'TEST','classement':'3'},
             {'cle_performance':'1','cheval':'TEST','classement':'4'}]
        with self.assertRaisesRegex(BlocageSynchronisation,'CLES_PERFORMANCE_DUPLIQUEES'):
            self.control(old,{'x':old[0]})

    def test_croissance_anormale_refusee(self):
        source={str(i):{'cle_performance':str(i)} for i in range(501)}
        with self.assertRaisesRegex(BlocageSynchronisation,'CROISSANCE_ANORMALE'):
            self.control([],source)

    def test_seuil_relatif_sur_un_historique_plus_grand(self):
        old=[{'cle_performance':str(i)} for i in range(6000)]
        source={str(i):{'cle_performance':str(i)} for i in range(6000,6601)}
        with self.assertRaisesRegex(BlocageSynchronisation,'CROISSANCE_ANORMALE'):
            self.control(old,source)

    def test_import_initial_explicite_et_trace(self):
        source={str(i):{'cle_performance':str(i)} for i in range(501)}
        with patch.dict(os.environ,{'PMU_SHEETS_IMPORT_INITIAL':'1'}):
            control=self.control([],source)
        self.assertTrue(control['report']['import_initial_explicite'])
        verifier_apres(control,list(source.values()))

    def test_ligne_inattendue_apres_post_detectee(self):
        source={'a':{'cle_performance':'1'}}
        control=self.control([],source)
        with self.assertRaisesRegex(BlocageSynchronisation,'MULTIPLICITES'):
            verifier_apres(control,[source['a'],source['a']])

    def test_ligne_perdue_apres_post_detectee(self):
        old=[{'cle_performance':'1'}]
        control=self.control(old,{})
        with self.assertRaisesRegex(BlocageSynchronisation,'MULTIPLICITES'):
            verifier_apres(control,[])

    def test_echec_produit_un_journal_et_un_resume_explicitement_bloques(self):
        with self.assertRaises(BlocageSynchronisation):self.control([{'cheval':'sans cle'}],{})
        report=json.loads(self.log.read_text().splitlines()[-1])
        self.assertEqual(report['statut'],'BLOQUE')
        self.assertIn('BLOQUE',(Path(self.tmp.name)/'summary.md').read_text())

    def test_source_complete_inattendue_vide_bloquee(self):
        with self.assertRaisesRegex(BlocageSynchronisation,'INATTENDUE_VIDE'):
            verifier_avant(self.headers,[{'cle_performance':'1'}],{},[],full_source=True,observed_keys=Counter({'1':1}))


if __name__=='__main__':unittest.main()
