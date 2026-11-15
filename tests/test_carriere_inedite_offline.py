import copy
import json
import unittest
from datetime import datetime,timedelta,timezone

from pmu_geny.carriere_geny import confirmer_inedit
from pmu_geny.controle_historique import classifier


def html(data):
    chunk='1:'+json.dumps(data)+'\n'
    return '<script>self.__next_f.push('+json.dumps([1,chunk])+')</script>'


class IneditTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.document={'nombre_annonce_geny':None,'nombre_extrait':0,'performances':[],
            'source_url':'https://www.geny.com/cheval/123456-test/course/1697677',
            'extrait_utc':self.now.isoformat()}
        self.data={'cheval':{'id':123456},'nbPerformances':0,'performances':[],
            'musique':{'resume':'Inédit'},'qualifications':[{'dateQualification':'2026-01-01'}],
            'participation':{'course':{'id':1697677,'dateHeureCourse':(self.now+timedelta(hours=1)).isoformat()}}}

    def test_zero_explicitement_prouve_avant_depart_sans_inventer_une_course(self):
        stamp=self.document['extrait_utc']
        self.assertTrue(confirmer_inedit(self.document,html(self.data),'123456'))
        self.assertEqual(classifier(self.document),('COMPLET',[]))
        self.assertEqual(self.document['performances'],[])
        self.assertEqual(self.document['nombre_annonce_geny'],0)
        self.assertEqual(self.document['extrait_utc'],stamp)
        self.assertEqual(self.document['historique_situation'],'INEDIT_AVANT_DEPART')

    def test_absence_de_champ_filtre_identite_ou_course_differente_ne_prouvent_pas_zero(self):
        cases=[]
        for field,value in [('nbPerformances',None),('nbPerformances',False),
                            ('performances',None),('musique',{'resume':'1a'}),
                            ('cheval',{'id':999999}),('participation',None)]:
            data=copy.deepcopy(self.data);data[field]=value;cases.append(data)
        other=copy.deepcopy(self.data);other['participation']['course']['id']=9999999;cases.append(other)
        for data in cases:
            with self.subTest(data=data):
                doc=copy.deepcopy(self.document)
                self.assertFalse(confirmer_inedit(doc,html(data),'123456'))
                self.assertIsNone(doc['nombre_annonce_geny'])

    def test_compteurs_contradictoires_et_capture_apres_depart_restent_incomplets(self):
        contradiction=copy.deepcopy(self.data);contradiction['nbPerformances']=2
        self.assertFalse(confirmer_inedit(self.document,html([self.data,contradiction]),'123456'))
        self.data['participation']['course']['dateHeureCourse']=(self.now-timedelta(minutes=1)).isoformat()
        self.assertFalse(confirmer_inedit(self.document,html(self.data),'123456'))
