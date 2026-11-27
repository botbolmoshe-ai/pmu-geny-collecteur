from datetime import datetime,timedelta,timezone
import unittest
from pmu_geny.historique_kpi import HEADERS,SOURCE_HEADERS,planifier,TAB,enregistrer
from pmu_geny.moteur_sheets import SynchroniseurSheets
from test_v26_chaine_offline import SheetsSession,Response


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,17,12,tzinfo=timezone.utc)
        self.source=[SOURCE_HEADERS,['Historique','Couverture',0,'Définition',100],['ML','Moyenne','','Sans données','']]

    def materialiser(self,updates):
        return [u['values'][0] for u in updates]

    def test_libelle_paris_conserve_la_cle_historique(self):
        label = 'Collecte · Acquisition UTC'
        previous = [SOURCE_HEADERS, ['Collecte', label, 46353.5, 'Définition', '']]
        current = [SOURCE_HEADERS, ['Collecte', 'Collecte · Acquisition (Paris)', 46353.5, 'Définition', '']]
        saved = self.materialiser(planifier(previous, [], self.now)[0])
        updates, last = planifier(current, saved, self.now + timedelta(minutes=1))
        self.assertEqual(last, 2)
        self.assertEqual(updates[0]['values'][0][0], saved[1][0])
        self.assertEqual(updates[0]['values'][0][4], current[1][1])

    def test_zero_vide_et_total_conserves_sans_inventer_jour_passe(self):
        updates,last=planifier(self.source,[],self.now)
        rows=self.materialiser(updates)
        self.assertEqual(rows[0],HEADERS);self.assertEqual(last,3)
        self.assertEqual(rows[1][1],'2026-11-17');self.assertEqual(rows[1][5],0);self.assertEqual(rows[1][7],100)
        self.assertEqual(rows[2][5],'')
        self.assertEqual(planifier(self.source,rows,self.now)[0],[])

    def test_un_releve_par_jour_actualise_sans_doublon_puis_jour_precedent_gele(self):
        rows=self.materialiser(planifier(self.source,[],self.now)[0])
        self.source[1][2]=50
        updates,last=planifier(self.source,rows,self.now+timedelta(hours=1))
        self.assertEqual(last,3);self.assertTrue(updates[0]['range'].endswith('A2:H2'))
        next_day=self.now+timedelta(days=1)
        updates,last=planifier(self.source,rows,next_day)
        self.assertEqual(last,5);self.assertTrue(updates[0]['range'].endswith('A4:H4'))

    def test_ancienne_echeance_reste_dans_son_releve_et_ne_reapparait_pas(self):
        import json

        old_label = 'Échéances · H2 ouvertes'
        current_label = 'Échéances · H-2 ouvertes'
        old_day = self.now.date().isoformat()
        old = [json.dumps([old_day, old_label]), old_day, self.now.isoformat(),
               'ML', old_label, 5, 'Ancien jalon', 5]
        source = [SOURCE_HEADERS, old[3:], ['ML', current_label, 2, 'Jalon actuel', 2]]
        for observed in (self.now + timedelta(hours=1), self.now + timedelta(days=1)):
            updates, _ = planifier(source, [HEADERS, old], observed)
            self.assertEqual([row[4] for row in self.materialiser(updates)], [current_label])

    def test_date_observation_paris_et_non_date_utc(self):
        now=datetime(2026,11,17,23,30,tzinfo=timezone.utc)
        rows=self.materialiser(planifier(self.source,[],now)[0])
        self.assertEqual(rows[1][1],'2026-11-18')

    def test_doublons_et_rejeu_anterieur_refuses(self):
        rows=self.materialiser(planifier(self.source,[],self.now)[0])
        with self.assertRaises(ValueError):planifier(self.source,rows+[rows[1]],self.now)
        with self.assertRaises(ValueError):planifier(self.source,rows,self.now-timedelta(minutes=1))

    def test_creation_et_reprise_reelle_sous_moteur_unique(self):
        class Session(SheetsSession):
            def post(self,url,**kwargs):
                if url.endswith(':batchUpdate') and 'requests' in kwargs['json']:
                    self.writes.append((url,kwargs['json']))
                    for req in kwargs['json']['requests']:
                        if 'addSheet' in req:self.tables[req['addSheet']['properties']['title']]=[[]]
                    return Response({})
                return super().post(url,**kwargs)
        session=Session();session.tables['Data Quality & KPI']=self.source
        engine=SynchroniseurSheets('/tmp','test',session=session)
        enregistrer(engine,engine.metadata(),self.now)
        self.assertEqual(len(session.tables[TAB]),3)
        enregistrer(engine,engine.metadata(),self.now+timedelta(minutes=1))
        self.assertEqual(len(session.tables[TAB]),3)
        self.assertEqual(session.tables[TAB][1][5],0)
