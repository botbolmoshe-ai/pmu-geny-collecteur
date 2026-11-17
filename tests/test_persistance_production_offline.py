from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pmu_geny.persistance_production import publier


class PersistanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);self.root=base/'code';self.root.mkdir()
        self.remote=base/'remote.git';self.cache=base/'cache';self.cache.mkdir()
        subprocess.run(['git','init','-q','--bare',str(self.remote)],check=True)
        self.git('init','-q');self.git('config','user.name','Test');self.git('config','user.email','test@example.invalid')
        (self.root/'garde.json').write_text('preuve existante')
        self.git('add','.');self.git('commit','-qm','initial')
        self.git('remote','add','origin',str(self.remote));self.git('push','-q','origin','HEAD:pmu-data')
        self.head=self.git('rev-parse','HEAD')

    def git(self,*args):
        return subprocess.check_output(['git',*args],cwd=self.root,text=True).strip()

    def test_sauvegarde_jalons_sans_effacer_donnees_existantes_ni_modifier_code(self):
        (self.cache/'jalons').mkdir();(self.cache/'jalons/preuve.json').write_text('{"publication":true}')
        self.assertEqual(publier(self.cache,self.root),'SAUVEGARDE')
        self.git('fetch','-q','origin','pmu-data')
        self.assertEqual(self.git('show','origin/pmu-data:jalons/preuve.json'),'{"publication":true}')
        self.assertEqual(self.git('show','origin/pmu-data:garde.json'),'preuve existante')
        self.assertEqual(self.git('rev-parse','HEAD'),self.head)
        self.assertEqual(publier(self.cache,self.root),'DEJA_SAUVEGARDE')

    def test_conflit_distant_arrete_la_sauvegarde_sans_force_push(self):
        (self.cache/'nouveau.json').write_text('{}')
        original=subprocess.check_output
        def concurrent(cmd,*args,**kwargs):
            if cmd[:3]==['git','push','origin']:
                original(['git','commit','--allow-empty','-qm','autre ecrivain'],cwd=self.root)
                original(['git','push','-q','origin','HEAD:pmu-data'],cwd=self.root)
            return original(cmd,*args,**kwargs)
        with patch('pmu_geny.persistance_production.subprocess.check_output',side_effect=concurrent):
            with self.assertRaises(subprocess.CalledProcessError):publier(self.cache,self.root)
        self.git('fetch','-q','origin','pmu-data')
        self.assertEqual(self.git('log','-1','--format=%s','origin/pmu-data'),'autre ecrivain')


if __name__=='__main__':unittest.main()
