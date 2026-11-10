"""Cas référencés: programme Geny du 11/11/2026 et cas artificiels hostiles."""
import unittest
from pmu_geny.rapprochement_v20_6 import rapprocher, index_from_anchors

DATE = '2026-11-11'

class TestProgrammeJourFerie(unittest.TestCase):
    def candidate(self, course_id, lieu, titre, r=None, c=None):
        slug = f'{DATE}-{lieu}-prix-{titre}'
        return {'href': f'https://www.geny.com/course/{course_id}-{slug}/partants-pronostics',
                'r': r, 'c': c, 'text': 'Partants / Pronos'}

    def test_la_capelle_reunion_renumerotee(self):
        # Identifiant et titre Geny observés dans le programme du 11 novembre.
        # Un numéro de réunion PMU différent ne doit pas masquer l'identité.
        anchors=[self.candidate('1697677','la-capelle','alain-le-guen',10,1),
                 self.candidate('1697679','la-capelle','claude-mathieu',10,2)]
        cours={'date':DATE,'hippodrome':'HIPPODROME DE LA CAPELLE',
               'nom':'Prix Alain le Guen','num_reunion':11,'num_course':1}
        decision=rapprocher(cours,index_from_anchors(anchors,DATE))
        self.assertEqual(decision['statut'],'CORRESPONDANCE_CONFIRMEE')
        self.assertEqual(decision['geny_id'],'1697677')
        self.assertEqual(decision['methode'],'NOM_FORT_RC_DIFFERENT')
        self.assertTrue(decision['preuves']['code_rc_different'])

    def test_la_capelle_exact_code(self):
        data=index_from_anchors([self.candidate('1697679','la-capelle','claude-mathieu',10,2)],DATE)
        decision=rapprocher({'date':DATE,'hippodrome':'La Capelle','nom':'Prix Claude Mathieu',
                            'num_reunion':10,'num_course':2},data)
        self.assertEqual(decision['geny_id'],'1697679')
        self.assertEqual(decision['methode'],'DATE_HIPPODROME_RC')

    def test_lyon_nom_et_hippodrome_sans_code(self):
        data=index_from_anchors([self.candidate('99901','lyon-la-soie','bellino-ii')],DATE)
        d=rapprocher({'date':DATE,'hippodrome':'HIPPODROME DE LYON LA SOIE',
                      'nom':'Prix Bellino II', 'num_reunion':4,'num_course':5},data)
        self.assertEqual(d['statut'],'CORRESPONDANCE_CONFIRMEE')

    def test_nom_proche_different_refuse_avec_code_contradictoire(self):
        data=index_from_anchors([self.candidate('11111','la-capelle','alain-le-grand',10,1)],DATE)
        d=rapprocher({'date':DATE,'hippodrome':'La Capelle','nom':'Prix Alain le Guen',
                      'num_reunion':11,'num_course':1},data)
        self.assertNotEqual(d['statut'],'CORRESPONDANCE_CONFIRMEE')

    def test_deux_noms_identiques_refuses(self):
        data=index_from_anchors([self.candidate('11111','la-capelle','alain-le-guen',10,1),
                                 self.candidate('22222','la-capelle','alain-le-guen',10,8)],DATE)
        d=rapprocher({'date':DATE,'hippodrome':'La Capelle','nom':'Prix Alain le Guen',
                      'num_reunion':11,'num_course':1},data)
        self.assertEqual(d['statut'],'CORRESPONDANCE_AMBIGUE')

    def test_mauvaise_date_et_piste_refusees(self):
        data=index_from_anchors([self.candidate('1697677','la-capelle','alain-le-guen',10,1)],DATE)
        for champ,valeur in [('date','2026-11-10'),('hippodrome','Graignes')]:
            c={'date':DATE,'hippodrome':'La Capelle','nom':'Prix Alain le Guen',
               'num_reunion':11,'num_course':1}
            c[champ]=valeur
            self.assertNotEqual(rapprocher(c,data)['statut'],'CORRESPONDANCE_CONFIRMEE')

if __name__=='__main__': unittest.main()
