import unittest
from datetime import datetime, timezone
from pmu_geny.sync_google_sheets import matching_pct,plan_sheet,source_rows,conclusion_methodes
from tempfile import TemporaryDirectory
from pathlib import Path
from pmu_geny.ml_v19 import save

class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.depart='2026-11-12T14:00:00+01:00'
        self.now=datetime(2026,11,12,16,tzinfo=timezone.utc)
        self.arr={'verifie_utc':'2026-11-12T14:10:00+01:00','arrivee':[
            {'rang':i,'numero':i} for i in (1,2,3)]}
    def pred(self,nums):
        return {'calcul_utc':'2026-11-12T13:00:00+01:00','top3':[{'numero':n} for n in nums]}
    def test_four_scores(self):
        for nums,expected in [([4,5,6],0),([1,4,5],33.33),([2,1,5],66.67),([3,2,1],100)]:
            self.assertEqual(matching_pct(self.pred(nums),self.arr,self.depart,self.now),expected)
    def test_invalid_or_missing_proofs(self):
        for p in ({},self.pred([1,1,2]),{**self.pred([1,2,3]),'calcul_utc':self.depart},
                  {**self.pred([1,2,3]),'non_partants_confirmes':[1]}):
            self.assertEqual(matching_pct(p,self.arr,self.depart,self.now),'')
        self.assertEqual(matching_pct(self.pred([1,2,3]),{**self.arr,'verifie_utc':'2099-01-01T00:00:00+00:00'},self.depart,self.now),'')
    def test_invalid_podium_and_invalid_chronology(self):
        self.assertEqual(matching_pct(self.pred([1,2,31]),self.arr,self.depart,self.now),'')
        self.assertEqual(matching_pct(self.pred([1,2,3]),{**self.arr,'verifie_utc':self.depart},self.depart,self.now),'')
        self.assertEqual(matching_pct(self.pred([1,2,3]),{**self.arr,'arrivee':[{'rang':i,'numero':1} for i in (1,2,3)]},self.depart,self.now),'')
    def test_conclusions_ne_designent_pas_de_faux_gagnant(self):
        self.assertEqual(conclusion_methodes({'Direct':0,'ML':0}), 'Échec commun : aucun cheval retrouvé (0/3)')
        self.assertEqual(conclusion_methodes({'Direct':0,'ML':''}), 'Direct : 0/3 ; aucune autre méthode évaluable')
        self.assertTrue(conclusion_methodes({'Direct':33.33,'ML':33.33}).startswith('Égalité en tête'))
        self.assertTrue(conclusion_methodes({'Direct':66.67,'ML':33.33}).startswith('Meilleure méthode : Direct'))
        self.assertTrue(conclusion_methodes({'Direct':'','ML':''}).startswith('Aucune prévision'))

    def test_numeric_values_and_clear(self):
        before={'course_key':'x','matching_direct_pct':100,'matching_ml_pct':33.33}
        after={**before,'matching_direct_pct':0,'matching_ml_pct':''}
        headers,changes,append=plan_sheet(list(before),[before],{'x':after},'Résultats & Analyse')
        self.assertFalse(append)
        self.assertEqual({headers[c-1]:v for _,c,v in changes},{'matching_direct_pct':0,'matching_ml_pct':''})

    def test_rapprochement_sans_paire_conserve_le_direct_verifie(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            day, code = '2026-11-12', 'R3C1'
            save(root/'sources_pmu'/f'programme_{day}.json', {'programme': [{
                'date': day, 'code': code, 'depart': self.depart, 'hippodrome': 'VINCENNES'}]})
            save(root/'arrivees'/f'{day}_{code}.json', self.arr)
            direct = root/'pronostics'/f'{day}_{code}_direct.json'
            save(direct, self.pred([4, 5, 6]))
            save(root/'pronostics'/f'{day}_{code}_ml_latest.json', self.pred([1, 2, 3]))
            save(root/'rapprochements'/f'{day}_R3.json', {
                'date': day, 'reunion': f'{day}_R3', 'statut': 'COMPLET',
                'declenchement_utc': self.now.isoformat(),
                'courses': {code: {'statut': 'ARRIVEE_OFFICIELLE', 'scores': {}}},
            })
            report, = source_rows(root)['Résultats & Analyse'].values()
            self.assertEqual(report['statut_evaluation'], 'EVALUE_DIRECT')
            self.assertEqual(report['matching_direct_pct'], 0)
            self.assertEqual(report['matching_ml_pct'], '')
            self.assertEqual(report['gagnant_ml_verdict'], '')
            self.assertEqual(report['conclusion'], 'Direct : 0/3 ; aucune autre méthode évaluable')
            save(direct, {**self.pred([1, 2, 3]), 'calcul_utc': self.depart})
            report, = source_rows(root)['Résultats & Analyse'].values()
            self.assertEqual(report['statut_evaluation'], 'ARRIVEE_SANS_TOP3_PUBLIE')
            self.assertEqual(report['matching_direct_pct'], '')

    def test_source_publie_matching_distinct_sur_une_arrivee_verifiee(self):
        with TemporaryDirectory() as folder:
            root=Path(folder); day='2026-11-12'; code='R3C1'
            save(root/'sources_pmu'/f'programme_{day}.json',{'programme':[{
                'date':day,'code':code,'depart':self.depart,'hippodrome':'VINCENNES',
                'nom':'PRIX TEST (GR A)','allocation_eur':40000,
                'parametres_pmu':{'conditions':"PRIX TEST Course 1 Course D Départ à l'Autostart. Pour 4 et 5 ans.",
                                 'parcours':'GRANDE PISTE'}}]})
            save(root/'partants_actuels'/f'{day}_{code}.json',{'chevaux':{
                str(n):{'nom':f'CHEVAL {n}','age_ans':4,'statut_np':'PARTANT'} for n in range(1,7)}})
            save(root/'arrivees'/f'{day}_{code}.json',self.arr)
            save(root/'pronostics'/f'{day}_{code}_direct.json',self.pred([2,4,1]))
            ml = self.pred([4,5,6])
            ml['top3'][0]['nom'] = 'NOM ENTRAINEUR'
            frozen_file = root/'pronostics'/f'{day}_{code}_ml_latest.json'
            save(frozen_file, ml)
            frozen_before = frozen_file.read_bytes()
            save(root/'pronostics'/f'{day}_{code}_cotes.json', self.pred([1,2,3]))
            output=source_rows(root)
            item=next(iter(output['Résultats & Analyse'].values()))
            runners={row['numero']:row for row in output['Courses & Prévisions'].values()}
            runner=runners['1']
            self.assertEqual(runners['2']['gagnant_direct_selection'],'OUI')
            self.assertEqual(runners['2']['gagnant_ml_selection'],'')
            self.assertEqual(runners['4']['gagnant_ml_selection'],'OUI')
            self.assertEqual([item[f'gagnant_direct_{field}'] for field in ('numero','nom','rang','verdict')],
                             [2,'CHEVAL 2',2,'Non trouvé'])
            self.assertEqual([item[f'gagnant_ml_{field}'] for field in ('numero','nom','rang','verdict')],
                             [4,'CHEVAL 4','','Non trouvé'])
            self.assertEqual([runner[field] for field in (
                'course_nom_pmu','course_categorie_pmu','course_ages_admis',
                'course_allocation_eur','course_parcours','course_mode_depart','age_ans')],
                ['PRIX TEST (GR A)','Course D','4 et 5 ans',40000,'Grande piste','Autostart',4])
            self.assertEqual(item['top3_direct_noms'],'CHEVAL 2 · CHEVAL 4 · CHEVAL 1')
            self.assertEqual(item['top3_ml_noms'],'CHEVAL 4 · CHEVAL 5 · CHEVAL 6')
            self.assertEqual(item['arrivee_officielle_noms'],'CHEVAL 1 · CHEVAL 2 · CHEVAL 3')
            self.assertEqual(item['matching_direct_pct'],66.67)
            self.assertEqual(item['matching_ml_pct'],0)
            self.assertTrue(item['conclusion'].startswith('Meilleure méthode : Direct'))
            self.assertEqual(item['score_cotes'], 3)
            self.assertEqual(frozen_file.read_bytes(), frozen_before)
            save(root/'pronostics'/f'{day}_{code}_direct.json',self.pred([4,5,6]))
            item=next(iter(source_rows(root)['Résultats & Analyse'].values()))
            self.assertTrue(item['conclusion'].startswith('Échec commun'))
            save(root/'arrivees'/f'{day}_{code}.json',{
                **self.arr,'arrivee':self.arr['arrivee']+[{'numero':4,'rang':7}]})
            save(root/'pronostics'/f'{day}_{code}_direct.json',self.pred([1,2,3]))
            item=next(iter(source_rows(root)['Résultats & Analyse'].values()))
            self.assertEqual(item['gagnant_direct_verdict'],'Trouvé')
            self.assertEqual(item['gagnant_ml_rang'],7)
            save(root/'pronostics'/f'{day}_{code}_direct.json',{**self.pred([1,2,3]),'calcul_utc':self.depart})
            item=next(iter(source_rows(root)['Résultats & Analyse'].values()))
            self.assertEqual(item['conclusion'],'ML : 0/3 ; aucune autre méthode évaluable')
            self.assertEqual(item['gagnant_direct_verdict'],'')
            (root/'pronostics'/f'{day}_{code}_ml_latest.json').unlink()
            item=next(iter(source_rows(root)['Résultats & Analyse'].values()))
            self.assertEqual(item['matching_ml_pct'],'')
            self.assertEqual(item['gagnant_ml_numero'],'')
            self.assertNotIn('top3_ml_noms', item)
