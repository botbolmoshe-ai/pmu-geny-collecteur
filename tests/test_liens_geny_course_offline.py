import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile
import unittest
from pmu_geny import liens_geny_course as liens
from pmu_geny import historiques_incrementaux as inc


class LiensTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name);self.out=self.cache/'diagnostic';self.out.mkdir()
        self.now=datetime(2026,11,17,9,tzinfo=timezone.utc)
        self.engagement='2026-11-17_R3C1';self.url='https://www.geny.com/course/1698831/partants-pronostics'
        self.horse={'engagement':self.engagement,'numero':'1','nom':'Opera Wood','course_url':self.url}

    def rows(self):
        return [{'index':i,'cells':[str(i),'','Opera Wood' if i==1 else 'Open Oam','X'],
            'html':f'<tr><td>{i}</td><td></td><td><a href="/cheval/{2895698+i}">{name}</a></td><td>X</td></tr>'}
            for i,name in [(1,'Opera Wood'),(2,'Open Oam')]]

    def extraire(self,rows=None,html=''):
        return liens.extraire(self.rows() if rows is None else rows,html,self.engagement,self.url,self.now.isoformat())

    def memoriser(self,proof):
        inc.ecrire(self.out/'liens_course.json',proof)
        liens.memoriser(self.cache,self.horse,self.out)

    def test_un_tableau_deja_charge_resout_deux_chevaux_sans_ouvrir_leurs_fiches(self):
        proof=self.extraire();self.assertEqual(len(proof['chevaux']),2)
        self.memoriser(proof)
        link=liens.pour_cheval(self.cache,self.engagement,'2','OPEN OAM',self.now,self.url)
        self.assertEqual(link['id'],'2895700')
        self.assertNotIn('historique_complet_au_utc',link)

    def test_sans_href_retour_possible_aux_donnees_structurees_de_la_meme_course(self):
        rows=self.rows()
        for row in rows:row['html']=''
        data={'cheval':{'id':2895699,'nom':'Opera Wood'},'course':{'id':1698831}}
        html='<script>self.__next_f.push('+json.dumps([1,'1:'+json.dumps(data)+'\n'])+')</script>'
        proof=self.extraire(rows,html)
        self.assertEqual(proof['chevaux']['1']['id'],'2895699')
        self.assertEqual(self.extraire(rows)['chevaux'],{})
        foreign=html.replace('1698831','1698832')
        self.assertEqual(self.extraire(rows,foreign)['chevaux'],{})

    def test_nom_numero_course_et_fraicheur_obligatoires_pour_reutiliser(self):
        self.memoriser(self.extraire())
        for num,name,date,url in [
            ('1','Autre',self.now,self.url),('2','Opera Wood',self.now,self.url),
            ('1','Opera Wood',self.now+timedelta(hours=25),self.url),
            ('1','Opera Wood',self.now-timedelta(seconds=1),self.url),
            ('1','Opera Wood',self.now,self.url.replace('1698831','1698832'))]:
            with self.subTest(num=num,name=name,date=date,url=url):
                self.assertIsNone(liens.pour_cheval(self.cache,self.engagement,num,name,date,url))

    def test_noms_ambigus_et_liens_externes_ne_sont_pas_memorises(self):
        rows=self.rows();rows[1]['cells'][2]='Opera Wood'
        self.assertNotIn('1',self.extraire(rows)['chevaux'])
        rows=self.rows();rows[0]['html']=rows[0]['html'].replace('/cheval/2895699','https://example.org/cheval/2895699')
        self.assertNotIn('1',self.extraire(rows)['chevaux'])
        proof=self.extraire();proof['http']=403;self.memoriser(proof)
        self.assertFalse((self.cache/'sources_geny/liens'/f'{self.engagement}.json').exists())

    def test_alimentation_reutilise_lien_sans_promouvoir_identite_ni_carriere(self):
        self.memoriser(self.extraire())
        inc.ecrire(self.cache/'orchestration/correspondances_geny.json',{self.engagement:'GENY-1698831'})
        inc.ecrire(self.cache/'partants_actuels'/f'{self.engagement}.json',{'chevaux':{
            '2':{'nom':'Open Oam','statut_np':'PARTANT'}}})
        state=inc.alimenter(self.cache,self.now)
        h=state['chevaux'][self.engagement+'_2']
        self.assertEqual(h['geny']['id'],'2895700')
        self.assertNotIn('id',h)
        self.assertEqual(h['motif_actualisation'],'HISTORIQUE_ABSENT_OU_NON_DATE')
        self.assertNotIn('historique_complet_au_utc',h)


if __name__=='__main__':unittest.main()
