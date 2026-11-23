"""Sources réelles de ferrure, absence/ferre, identités et réparation sans perte."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from pmu_geny import ferrures_geny as fg
from pmu_geny import historiques_incrementaux as inc
from pmu_geny import rattrapage_historiques as back
from pmu_geny.partants_actuels_v21 import extraire_partants,enregistrer,ferrure_historique_explicite
from pmu_geny.sync_google_sheets import plan_sheet
from pmu_geny.reparer_ferrures import reparer,reparer_partants
from pmu_geny.moteur_sheets import SynchroniseurSheets
from test_v26_incremental_offline import doc
from test_v26_chaine_offline import SheetsSession


def participation(code='FF',*,ident='123456',date='2026-01-01',rank=3,chrono="1'15''0",pid=1):
    return {'id':pid,'deferre':code,'cheval':{'id':int(ident),'nom':'Test'},'rang':rank,
            'redKm':chrono,'recul':0,'hippodrome':{'nom':'Vincennes'},
            'course':{'id':pid,'dateHeureCourse':date+'T14:00:00','distance':2700,'specialite':'ATTELE'}}


def html(records=(),*,dom='',ident='123456'):
    payload='1:'+json.dumps({'performances':list(records)},ensure_ascii=False)+'\n'
    return '<script type="application/ld+json">'+json.dumps({'identifier':ident})+'</script>'+\
        '<script>self.__next_f.push('+json.dumps([1,payload])+')</script>'+dom


def perf(date='2026-01-01',rank='3',chrono="1'15''0"):
    return {'date':date,'hippodrome':'Vincennes','discipline':'Attelé','distance_m':'2700',
            'classement':rank,'chrono':chrono,'texte_source':'preuve stable '+date}


def pmu(name='Test',**extra):
    return {'participants':[{'numPmu':1,'nom':name,'idCheval':'TEST-PERE-MERE',
            'allure':'TROT','statut':'PARTANT','driver':'Driver source',**extra}]}


class FerruresTests(unittest.TestCase):
    def test_texte_petite_piste_et_nom_driver_ne_sont_pas_des_ferrures(self):
        for text in ['30/09/25 | Vincennes | Attelé | 2 850 | PP | G | - | Dur | Driver',
                     '19/07/26 | Laon | Attelé | 2 650 | G | Auto | Mlle C. Da Costa']:
            self.assertEqual(ferrure_historique_explicite(text),'')
        self.assertEqual(ferrure_historique_explicite('PP'),'PP')
        self.assertEqual(ferrure_historique_explicite('Ferrure : DA'),'DA')
        self.assertEqual(ferrure_historique_explicite('Vincennes 2100 D4 1e'),'D4')

    def test_nettoyage_limite_aux_anciens_faux_codes_dont_le_texte_est_identique(self):
        text='30/09/25 | Vincennes | Attelé | 2 850 | PP | G | - | Dur | Driver'
        headers=['cle_performance','ferrure','source_url']
        old={'cle_performance':'p','ferrure':'PP','source_url':text}
        incoming={'p':{'cle_performance':'p','ferrure':'','source_url':text}}
        _,changes,adds=plan_sheet(headers,[old],incoming,'Historique chevaux')
        self.assertEqual(changes,[(2,2,'')]);self.assertEqual(adds,[])
        _,changes,_=plan_sheet(headers,[{**old,'source_url':'preuve différente'}],incoming,'Historique chevaux')
        self.assertNotIn((2,2,''),changes)
        incoming['p']['ferrure']='D4'
        _,changes,_=plan_sheet(headers,[old],incoming,'Historique chevaux')
        self.assertIn((2,2,'D4'),changes);self.assertNotIn((2,2,''),changes)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.cache=Path(self.tmp.name);self.now=datetime.now(timezone.utc)

    def test_pmu_trot_sans_declaration_est_ferre_avec_provenance(self):
        result=extraire_partants(pmu())[1]
        self.assertEqual(result['ferrure'],'F')
        self.assertEqual(result['provenance_champs']['ferrure']['convention'],'TROT_SANS_DECLARATION_DEFERRAGE')
        self.assertEqual(extraire_partants(pmu(deferre='DEFERRE_ANTERIEURS_POSTERIEURS'))[1]['ferrure'],'D4')

    def test_absence_generique_galop_et_code_inconnu_ne_deviennent_pas_ferre(self):
        for raw in [{'participants':[{'numPmu':1,'nom':'Test'}]},pmu(allure='GALOP'),pmu(deferre='CODE_INCONNU')]:
            self.assertNotEqual(extraire_partants(raw)[1].get('ferrure'),'F')

    def test_enregistrement_pmu_conserve_url_et_heure_de_la_source(self):
        enregistrer(self.cache,{'date':'2026-11-15','code':'R4C1'},pmu())
        record=inc.lire(self.cache/'partants_actuels/2026-11-15_R4C1.json')
        proof=record['chevaux']['1']['provenance_champs']['ferrure']
        self.assertEqual(proof['capture_utc'],record['capture_utc'])
        self.assertTrue(proof['url'].endswith('/15112026/R4/C1/participants'))

    def test_codes_geny_distincts_des_codes_pmu_et_libelles_accessibles(self):
        self.assertEqual(fg.CODES['DP'],'DA/PP');self.assertEqual(fg.CODES['PP'],'P4')
        for label,expected in [('Ferré des 4','F'),('Déferré des 4','D4'),
            ('Déferré des quatre pieds','D4'),('Plaqué ant. / Déferré post.','DP/PA'),
            ('Déferré ant. / Plaqué post.','DA/PP'),('D - dur','')]:
            self.assertEqual(fg.libelle_ferrure(label),expected)

    def test_structure_source_enrichit_la_bonne_performance_sans_changer_son_texte(self):
        record=perf();document={'performances':[record]};before=copy.deepcopy(record)
        result=fg.enrichir(document,html([participation('DP')]),'123456','https://www.geny.com/cheval/123456',self.now.isoformat())
        self.assertEqual(result['ferrures_ajoutees'],1);self.assertEqual(record['ferrure'],'DA/PP')
        self.assertEqual({k:record[k] for k in before},before)
        self.assertEqual(record['ferrure_source']['identifiant_cheval'],'123456')

    def test_pictogramme_dom_charge_apres_bloc_initial_est_lu(self):
        row='<div>'+''.join('<span>'+x+'</span>' for x in ['02/01/26','Vincennes','Attelé','2700',
            'G','-','Dur','Crse F','12000 €','Driver'])+\
            '<div aria-label="Ferré des 4"><svg></svg></div><span>1\'15\'\'0</span><span>3</span><span>e</span></div>'
        dom='<section><h2>CARRIÈRE</h2><span>Trier par</span>'+row+'</section>'
        document={'performances':[perf(),perf('2026-01-02')]}
        result=fg.enrichir(document,html([participation('DD')],dom=dom),'123456','source')
        self.assertEqual([r.get('ferrure') for r in document['performances']],['D4','F'])
        self.assertEqual(result['ferrures_manquantes'],0)

    def test_identite_ou_date_differente_et_valeur_absente_ne_sont_pas_inventees(self):
        for record in [participation(ident='999999'),participation(date='2026-02-01'),participation(None),participation(rank=None)]:
            document={'performances':[perf()]}
            result=fg.enrichir(document,html([record]),'123456','source')
            self.assertFalse(document['performances'][0].get('ferrure'))
            self.assertEqual(result['ferrures_manquantes'],1)

    def test_deux_courses_meme_jour_sont_departagees_par_rang_et_chrono(self):
        records=[participation('DD',rank=1,chrono="1'14''0",pid=1),participation('FF',rank=2,pid=2)]
        document={'performances':[perf(rank='2')]}
        fg.enrichir(document,html(records),'123456','source')
        self.assertEqual(document['performances'][0]['ferrure'],'F')
        ambiguous={'performances':[perf(rank='8',chrono='')]}
        result=fg.enrichir(ambiguous,html(records),'123456','source')
        self.assertEqual(result['ferrures_ajoutees'],0);self.assertEqual(result['conflits'],1)

    def test_ferrure_refusee_si_une_autre_course_a_le_meme_code(self):
        rows = [participation('FF', pid=1), participation('FF', pid=2)]
        capture = self.now.isoformat()
        for row, expected_conflicts in ((perf(), 1), (perf(rank='4'), 0)):
            with self.subTest(rank=row['classement']):
                result = fg.enrichir({'performances': [row]}, html(rows), '123456', 'source', capture)
                self.assertNotIn('ferrure', row)
                self.assertEqual(result['conflits'], expected_conflicts)

    def seed_capture(self,*,ferrure=None):
        row=perf()
        if ferrure:row['ferrure']=ferrure
        data=doc(self.now-timedelta(days=1),[row])
        inc.ecrire(self.cache/'historiques/123456/historique_geny.json',data)
        inc.ecrire(self.cache/'etat_persistant.json',{'version':1,'chevaux':{'123456':{'nom':'Test'}}})
        return data

    def report(self,*,ferrure=None):
        row=perf()
        if ferrure:
            row.update(ferrure=ferrure, ferrure_qualification='SOURCEE')
        target=self.cache/'capture';inc.ecrire(target/'historique_geny.json',doc(self.now,[row]))
        return {'complet':True,'identite_verifiee':True,'geny':{'id':'123456','nom':'Test',
            'url_geny':'https://www.geny.com/cheval/123456-test/course/1698061'},'dossier':str(target)}

    def test_ajout_de_ferrure_ne_provoque_pas_une_fausse_regression(self):
        old=self.seed_capture();horse={'id':'123456','nom':'Test'}
        inc.accepter(self.cache,horse,self.report(ferrure='D4'))
        saved=inc.capture_valide(self.cache,'123456')
        self.assertEqual(saved['performances'][0]['ferrure'],'D4')
        self.assertEqual(saved['nombre_extrait'],old['nombre_extrait'])
        self.assertEqual(horse['ferrures_manquantes'],0)

    def test_ferrure_connue_est_conservee_et_une_contradiction_bloque(self):
        self.seed_capture(ferrure='F')
        inc.accepter(self.cache,{'id':'123456','nom':'Test'},self.report())
        self.assertEqual(inc.capture_valide(self.cache,'123456')['performances'][0]['ferrure'],'F')
        with self.assertRaisesRegex(ValueError,'REGRESSION_FERRURE'):
            inc.accepter(self.cache,{'id':'123456','nom':'Test'},self.report(ferrure='D4'))

    def test_reparation_archive_reproductible_et_date_de_capture_intacte(self):
        original=self.seed_capture();folder=self.cache/'diagnostics/GENY-1698061/123456';folder.mkdir(parents=True)
        (folder/'diagnostic_geny.html').write_text(html([participation('FF')]))
        inc.ecrire(folder/'historique_geny.json',original)
        frozen=self.cache/'pronostics/fige.json';inc.ecrire(frozen,{'preuve':'figee'});before=frozen.read_bytes()
        first=reparer(self.cache);second=reparer(self.cache)
        self.assertEqual(first['ferrures_ajoutees'],1);self.assertEqual(second['ferrures_ajoutees'],0)
        saved=inc.lire(self.cache/'historiques/123456/historique_geny.json')
        self.assertEqual(saved['extrait_utc'],original['extrait_utc'])
        self.assertEqual(frozen.read_bytes(),before)

    def test_reparation_pmu_ne_modifie_que_le_champ_ferrure_de_la_bonne_identite(self):
        path=self.cache/'partants_actuels/2026-11-15_R4C1.json'
        original={'source':'PMU_API_PARTICIPANTS','capture_utc':'2026-11-14T12:00:00+00:00',
                  'chevaux':{'1':{'nom':'Test','driver_jockey':'Driver original'}}}
        inc.ecrire(path,original)
        result=reparer_partants(self.cache,fetch=lambda url:pmu())
        saved=inc.lire(path)
        self.assertEqual(result['ferrures_courantes_ajoutees'],1)
        self.assertEqual(saved['chevaux']['1']['ferrure'],'F')
        self.assertEqual(saved['chevaux']['1']['driver_jockey'],'Driver original')
        self.assertEqual(saved['capture_utc'],original['capture_utc'])
        inc.ecrire(path,original)
        self.assertEqual(reparer_partants(self.cache,fetch=lambda url:pmu(name='Autre'))['ferrures_courantes_ajoutees'],0)

    def test_archive_de_depart_persistante_sans_nouvelle_ferrure(self):
        original = self.seed_capture(ferrure='F')
        folder = self.cache / 'diagnostics/GENY-1698061/123456'
        folder.mkdir(parents=True)
        record = participation()
        record.pop('deferre')
        record['course'].update(depart='ELASTIQUE', dateHeureCourse='2026-01-01T14:00:00+01:00')
        (folder / 'diagnostic_geny.html').write_text(html([record]))
        inc.ecrire(folder / 'historique_geny.json', original)

        repaired = reparer(self.cache)
        self.assertEqual((repaired['departs_ajoutes'], repaired['ferrures_ajoutees']), (1, 0))
        saved = inc.capture_valide(self.cache, '123456')
        proof = saved['performances'][0]['depart_trot']
        self.assertEqual(proof['mode'], 'Volté')
        self.assertEqual(proof['capture_utc'], original['extrait_utc'])
        self.assertEqual(saved['extrait_utc'], original['extrait_utc'])
        self.assertEqual(reparer(self.cache)['departs_ajoutes'], 0)
        self.assertEqual(len(list((self.cache / 'historiques_versions/123456').glob('*.json'))), 1)

        inc.accepter(self.cache, {'id': '123456', 'nom': 'Test'}, self.report())
        self.assertEqual(inc.capture_valide(self.cache, '123456')['performances'][0]['depart_trot'], proof)

    def test_carriere_complete_sans_ferrures_reste_a_completer(self):
        original=self.seed_capture()
        inc.ecrire(self.cache/back.INVENTAIRE,{'capture_utc':self.now.isoformat(),'chevaux':[],
                    'ids_couverts':['123456'],'lignes_historique':1})
        state=back.preparer(self.cache,self.now);state['sync_kpi']='OK';back.bilan(state)
        self.assertEqual(state['bilan']['cibles_completees'],1)
        self.assertEqual(state['bilan']['historiques_ferrures_a_completer'],1)
        self.assertEqual(state['statut'],'PARTIEL_REPRENABLE')
        self.assertEqual(back.prochaine_tache(state,self.now,{}),('123456','COLLECTE'))

    def test_reparation_pmu_respecte_un_refus_429_sans_poursuite(self):
        for code in ('R4C1','R4C2'):
            inc.ecrire(self.cache/'partants_actuels'/f'2026-11-15_{code}.json',
                {'source':'PMU_API_PARTICIPANTS','chevaux':{'1':{'nom':'Test'}}})
        calls=[]
        def denied(url):calls.append(url);raise HTTPError(url,429,'rate limit',None,None)
        result=reparer_partants(self.cache,fetch=denied)
        self.assertEqual(len(calls),1);self.assertEqual(result['erreurs_sources'][0]['http'],429)

    def test_ecriture_ferrure_sur_cle_existante_sans_ajout_ni_effet_sur_previsions(self):
        session=SheetsSession();session.tables['Historique chevaux']=[
            ['cle_performance','identifiant_cheval','cheval','classement','ferrure'],['p','123456','Test','3','']]
        before=copy.deepcopy(session.tables['Courses & Prévisions'])
        source={'Historique chevaux':{'p':{'cle_performance':'p','identifiant_cheval':'123456','cheval':'Test','classement':'3','ferrure':'F'}},
                'Courses & Prévisions':{},'Résultats & Analyse':{}}
        with patch.dict(os.environ,{'PMU_SHEETS_LOCK_DIR':str(self.cache),'PMU_SHEETS_CONTROLES':str(self.cache/'controle.jsonl'),'GITHUB_STEP_SUMMARY':''}), \
             patch('pmu_geny.sync_google_sheets.source_rows',return_value=source),patch('builtins.print'):
            engine=SynchroniseurSheets(self.cache,'fake',session=session);horse={'geny':{'id':'123456'},'nom':'Test'}
            first=engine.synchroniser_cheval(horse,include_courses=False,include_kpi=False)
            second=engine.synchroniser_cheval(horse,include_courses=False,include_kpi=False)
        self.assertEqual(first['Historique chevaux']['lignes_ajoutees'],0)
        self.assertEqual(first['Historique chevaux']['cellules_actualisees'],1)
        self.assertEqual(second['Historique chevaux']['cellules_actualisees'],0)
        self.assertEqual(session.tables['Courses & Prévisions'],before)


if __name__=='__main__':unittest.main()
