"""V31 : aucune reinsertion d'une performance identique par variation de source."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from pmu_geny.sync_google_sheets import source_rows,reconcilier_cles_historiques
from pmu_geny.controle_sync_sheets import (cle_sportive,inventaire,verifier_avant,
                                            BlocageSynchronisation)


class DedupHistoriqueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name)
        journal=self.cache/'etat_persistant.json'
        journal.write_text(json.dumps({'chevaux':{'123':{
            'nom':'CHEVAL TEST','statut':'COMPLET'}}}))
        self.export=self.cache/'exports'/'GENY-1698069'/'performances.csv'
        self.export.parent.mkdir(parents=True)

    def source(self,rows):
        with self.export.open('w',newline='',encoding='utf-8') as stream:
            fields=['cheval_id','nom','date','hippodrome','discipline',
                    'distance_m','classement','chrono','texte_source']
            writer=csv.DictWriter(stream,fieldnames=fields,delimiter=';')
            writer.writeheader()
            writer.writerows(rows)
        return source_rows(self.cache)['Historique chevaux']

    @staticmethod
    def perf(source,*,chrono="1'14''0",place='4'):
        return {'cheval_id':'123','nom':'CHEVAL TEST','date':'2026-11-12',
                'hippodrome':'Vincennes','discipline':'Attelé','distance_m':'2700',
                'classement':place,'chrono':chrono,'texte_source':source}

    def test_url_et_description_de_la_meme_course_ne_creent_qu_une_ligne(self):
        url='https://www.geny.com/cheval/123-test/course/1698069'
        desc="12/11/26 | Vincennes | Attelé | 2 700 | Crse D | 41 000 € | 1'14''0 | 4 | e"
        rows=self.source([self.perf(url),self.perf(desc)])
        self.assertEqual(len(rows),1)
        self.assertEqual(next(iter(rows.values()))['source_url'],desc)
        self.assertEqual(next(iter(rows)), '123|2026-11-12|VINCENNES')
        self.assertEqual(source_rows(self.cache)['Historique chevaux'],rows)

    def test_deux_courses_distinctes_meme_jour_sont_conservees(self):
        rows=self.source([self.perf('12/11/26 | course 1'),
                          self.perf('12/11/26 | course 2',chrono="1'15''0",place='8')])
        self.assertEqual(len(rows),2)
        self.assertEqual({r['classement'] for r in rows.values()},{'4','8'})
        self.assertEqual(len({r['cle_performance'] for r in rows.values()}),2)

    def test_persistance_et_export_fusionnes(self):
        url='https://www.geny.com/cheval/123-test/course/1698069'
        desc="12/11/26 | Vincennes | Attelé | 2 700 | G | Crse D | 41 000 € | 4 | e"
        self.source([self.perf(url)])
        doc={'statut':'COMPLET','performances':[self.perf(desc)]}
        hist=self.cache/'historiques'/'123'/'historique_geny.json'
        hist.parent.mkdir(parents=True)
        hist.write_text(json.dumps(doc))
        rows=source_rows(self.cache)['Historique chevaux']
        self.assertEqual(len(rows),1)
        self.assertEqual(next(iter(rows.values()))['source_url'],desc)

    def test_reconciliation_conserve_la_cle_anterieure(self):
        before={'identifiant_cheval':'123','date_course_historique':'2026-11-12',
                'hippodrome':'Vincennes','discipline':'Attelé','distance_m':'2700',
                'classement':'4','chrono':"1'14''0",'cle_performance':'ancienne'}
        item={**before,'cle_performance':'nouvelle','source_url':'texte enrichi'}
        restored=reconcilier_cles_historiques([before],{'x':item})
        self.assertEqual(list(restored),['ancienne'])
        self.assertEqual(restored['ancienne']['source_url'],'texte enrichi')

    def test_cles_différentes_meme_performance_bloquees_avant_ecriture(self):
        before={'identifiant_cheval':'123','date_course_historique':'2026-11-12',
                'hippodrome':'Vincennes','discipline':'Attelé','distance_m':'2700',
                'classement':'4','chrono':"1'14''0",'cle_performance':'ancienne'}
        item={**before,'cle_performance':'nouvelle','source_url':'texte enrichi'}
        headers=list(before)+['source_url']
        with self.assertRaises(BlocageSynchronisation):
            verifier_avant(headers,[before],{'x':item},
                           [list(item.get(h,'') for h in headers)],
                           observed_keys=inventaire(headers,[before])['keys'])


if __name__=='__main__':
    unittest.main()
