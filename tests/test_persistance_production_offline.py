from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pmu_geny import persistance_production as persistance


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
        persistance.restaurer(self.cache, self.root)

    def git(self,*args):
        return subprocess.check_output(['git',*args],cwd=self.root,text=True).strip()

    def test_sauvegarde_jalons_sans_effacer_donnees_existantes_ni_modifier_code(self):
        (self.cache/'jalons').mkdir();(self.cache/'jalons/preuve.json').write_text('{"publication":true}')
        (self.cache/'garde.json').unlink()
        self.assertEqual(persistance.publier(self.cache,self.root),'SAUVEGARDE')
        self.git('fetch','-q','origin','pmu-data')
        self.assertEqual(self.git('show','origin/pmu-data:jalons/preuve.json'),'{"publication":true}')
        self.assertEqual(self.git('show','origin/pmu-data:garde.json'),'preuve existante')
        self.assertEqual(self.git('rev-parse','HEAD'),self.head)
        self.assertEqual(persistance.publier(self.cache,self.root),'DEJA_SAUVEGARDE')

    def test_une_avancee_distante_pendant_le_push_est_reprise_sans_force_push(self):
        (self.cache/'nouveau.json').write_text('{}')
        original = persistance.git
        pushes = []

        def concurrent(root, *args, **kwargs):
            if args[0] == 'push':
                pushes.append(args)
                if len(pushes) == 1:
                    (self.root/'garde.json').write_text('écriture concurrente')
                    self.git('commit', '-qam', 'autre ecrivain')
                    self.git('push', '-q', 'origin', 'HEAD:pmu-data')
            return original(root, *args, **kwargs)

        with patch.object(persistance, 'git', side_effect=concurrent):
            self.assertEqual(persistance.publier(self.cache, self.root), 'SAUVEGARDE')
        self.assertEqual(len(pushes), 2)
        self.assertTrue(all(len(args) == 3 for args in pushes))
        self.git('fetch','-q','origin','pmu-data')
        self.assertEqual(self.git('show','origin/pmu-data:garde.json'),'écriture concurrente')
        self.assertEqual(self.git('show','origin/pmu-data:nouveau.json'),'{}')
        (self.cache/'autre.json').write_text('{}')
        self.assertEqual(persistance.publier(self.cache, self.root), 'SAUVEGARDE')
        self.git('fetch', '-q', 'origin', 'pmu-data')
        self.assertEqual(self.git('show','origin/pmu-data:garde.json'),'écriture concurrente')

    def test_deux_ecritures_du_meme_fichier_sont_signalees(self):
        (self.cache/'garde.json').write_text('modification locale')
        autre = self.cache.with_name('autre-cache')
        persistance.restaurer(autre, self.root)
        (autre/'garde.json').write_text('modification distante')
        persistance.publier(autre, self.root)
        with self.assertRaisesRegex(persistance.ConflitPersistance, 'garde.json'):
            persistance.publier(self.cache, self.root)
        self.git('fetch', '-q', 'origin', 'pmu-data')
        self.assertEqual(self.git('show','origin/pmu-data:garde.json'),'modification distante')


if __name__=='__main__':unittest.main()
