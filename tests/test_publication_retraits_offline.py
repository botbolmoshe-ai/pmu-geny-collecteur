"""Non-régression : une sélection invalidée efface les cellules obsolètes."""
import unittest
import tempfile
from pathlib import Path
from pmu_geny.ml_v19 import save
from pmu_geny.sync_google_sheets import source_rows
from pmu_geny.sync_google_sheets import plan_sheet

class PublicationTests(unittest.TestCase):
    def test_source_transmet_les_vides_d_une_prevision_invalidee(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);day='2026-11-17';code='R3C1'
            save(root/'sources_pmu'/f'programme_{day}.json',{'programme':[{
                'date':day,'code':code,'depart':day+'T14:12:00+01:00','hippodrome':'VINCENNES'}]})
            save(root/'partants_actuels'/f'{day}_{code}.json',{'chevaux':{'1':{
                'nom':'Retiré','statut_np':'NON_PARTANT'}}})
            save(root/'pronostics'/f'{day}_{code}_direct.json',{
                'statut':'DONNEES_INSUFFISANTES','classement_complet':[],'top3':[]})
            rows=source_rows(root)['Courses & Prévisions'];row=next(iter(rows.values()))
            for field in ('top3_direct_rang','top3_direct_top3','top3_direct_score'):
                self.assertIn(field,row);self.assertEqual(row[field],'')

    def test_rangs_selection_et_score_effaces_sur_retrait(self):
        before={'course_key':'course','numero':'1','top3_direct_top3':'OUI',
                'top3_direct_rang':1,'top3_direct_score':3.5}
        after={**before,'top3_direct_top3':'','top3_direct_rang':'','top3_direct_score':''}
        headers,changes,append=plan_sheet(list(before),[before],{'one':after},'Courses & Prévisions')
        self.assertFalse(append)
        self.assertEqual({headers[col-1]:value for _,col,value in changes},
                         {'top3_direct_top3':'','top3_direct_rang':'','top3_direct_score':''})
