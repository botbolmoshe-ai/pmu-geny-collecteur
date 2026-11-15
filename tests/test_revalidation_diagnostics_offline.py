import copy
import json
import tempfile
import unittest
import zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch,Mock

from pmu_geny import historiques_incrementaux as inc
from pmu_geny import rattrapage_historiques as back
from pmu_geny.collecte_geny_v4 import parse_career
from pmu_geny.controle_historique import classifier
from pmu_geny.revalider_diagnostics import revalider,revalider_artifacts


class RevalidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name);self.now=datetime.now(timezone.utc)
        inc.ecrire(self.cache/'etat_persistant.json',{'chevaux':{'123456':{'nom':'Test'}}})
        inc.ecrire(self.cache/back.INVENTAIRE,{'capture_utc':self.now.isoformat(),'chevaux':[],
                                            'ids_couverts':[],'lignes_historique':0})
        inc.ecrire(self.cache/back.QUEUE,back.preparer(self.cache,self.now))
        self.row='11/11/26\nLa Capelle\nAttelé\n2 000\nG\n-\nDur\nCrse F\n12 500 €\nB. Rouer\n1\'23\'\'7\n25.4\n6\ne'
        self.body='Test\nCARRIÈRE\nsur 1 courses\n'+self.row+'\n03/06\n2026\nGrosbois\nAttelé\n2 000m\nQualification\n1\'19"8'
        self.geny={'id':'123456','nom':'Test','url_geny':'https://www.geny.com/cheval/123456-test/course/1697677'}
        self.document={**parse_career(self.body,[]),'source_url':self.geny['url_geny'],
                       'extrait_utc':(self.now-timedelta(hours=1)).isoformat()}
        self.document['performances'][0].update(classement='',ferrure='F')
        self.document['complet']=False

    def archive(self,*,identity=True,document=None,geny=None):
        archive=self.cache/'test.zip';folder='resultats/incremental/123456/12345678'
        report={'complet':False,'identite_verifiee':identity,'geny':geny or self.geny,
                'statut':'DONNEES_INCOMPLETES'}
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr(folder+'/resultat.json',json.dumps(report))
            z.writestr(folder+'/123456/historique_geny.json',json.dumps(document or self.document))
            z.writestr(folder+'/123456/diagnostic_texte_geny.txt',self.body)
        return archive

    def test_qualification_apres_derniere_course_ne_masque_pas_son_classement(self):
        parsed=parse_career(self.body,[])
        self.assertEqual(classifier(parsed),('COMPLET',[]))
        self.assertEqual(parsed['nombre_extrait'],1)
        self.assertEqual(parsed['blocs_qualification_exclus'],1)
        row=parsed['performances'][0]
        self.assertEqual(row['classement'],'6')
        self.assertNotIn('Grosbois',row['texte_source'])
        self.assertEqual(parse_career('CARRIÈRE\nsur 1 courses\n'+self.row.replace('\n6\ne',''),[])['performances'][0]['classement'],'')

    def test_rejeu_local_garde_date_ferrure_et_publie_sans_recollecte(self):
        frozen=self.cache/'ml/instantanes/fige.json';inc.ecrire(frozen,{'preuve':'figee'})
        archive=self.archive()
        with patch('requests.get',side_effect=AssertionError('Aucune requête de source')):
            first=revalider(self.cache,archive);second=revalider(self.cache,archive)
        self.assertEqual(first['captures_revalidees'],1);self.assertEqual(second['captures_revalidees'],0)
        saved=inc.capture_valide(self.cache,'123456')
        self.assertEqual(saved['extrait_utc'],self.document['extrait_utc'])
        self.assertEqual(saved['performances'][0]['ferrure'],'F')
        self.assertEqual(saved['performances'][0]['classement'],'6')
        self.assertTrue(saved['revalidation_archive']['sha256'])
        collect=Mock(side_effect=AssertionError('Aucune recollecte'));sync=Mock(return_value={})
        with patch.object(inc.time,'sleep'):
            state=inc.run(self.cache,mode='rattrapage',collect=collect,sync=sync)
        collect.assert_not_called();sync.assert_called_once()
        self.assertEqual(state['chevaux']['123456']['sync'],'OK')
        self.assertEqual(inc.lire(frozen),{'preuve':'figee'})

    def test_identite_date_et_total_incertains_ne_sont_pas_promus(self):
        future=copy.deepcopy(self.document);future['extrait_utc']=(self.now+timedelta(days=1)).isoformat()
        count=copy.deepcopy(self.document);count['nombre_annonce_geny']=2
        for kwargs in ({'identity':False},{'geny':{**self.geny,'id':'999999'}},
                       {'document':future},{'document':count}):
            with self.subTest(kwargs=kwargs):
                report=revalider(self.cache,self.archive(**kwargs))
                self.assertEqual(report['captures_revalidees'],0)
                self.assertFalse((self.cache/'historiques/123456/historique_geny.json').exists())

    def test_identifiants_artefacts_invalides_ne_declenchent_aucun_telechargement(self):
        with patch('requests.get') as request:
            for value in ('abc','1/2','1;2','1,2,3,4,5,6'):
                with self.assertRaisesRegex(ValueError,'ARTEFACTS_INVALIDES'):
                    revalider_artifacts(self.cache,value)
            request.assert_not_called()
