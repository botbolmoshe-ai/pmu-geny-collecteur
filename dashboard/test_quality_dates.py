from datetime import date,datetime,timezone
import unittest
from quality_dates import cohort_metrics, daily_series, history_series, latest_history,VALUE,TOTAL


class QualityDatesTests(unittest.TestCase):
    def row(self,day,n=1,hist=0,np='PARTANT'):
        return {'Date':day,'Clé course (technique)':day+'|R1C1','N°':n,'Cheval':f'H{n}',
            'Non-partant (NP)':np,'Historique · Nb performances récupérées':hist,
            'Ferrure · Course du jour':'D4','Âge (ans)':5,'Sexe':'Hongre','Gains carrière (€)':0}

    def test_focus_date_et_intervalle_avec_denoms_et_np(self):
        rows=[self.row('2026-11-16',hist=3),self.row('2026-11-17',hist=0),self.row('2026-11-17',2,4,'NON_PARTANT')]
        one={m['Indicateur']:m for m in cohort_metrics(rows,date(2026,11,17),date(2026,11,17))}
        self.assertEqual(one['Partants avec historique disponible'][VALUE],0)
        self.assertEqual(one['Partants avec historique disponible'][TOTAL],1)
        self.assertEqual(one['Participations recensées'][VALUE],2)
        all_days=daily_series(rows,date(2026,11,16),date(2026,11,17))
        rates=[m[VALUE] for m in all_days if m['Indicateur']=='Taux de partants avec historique disponible']
        self.assertEqual(rates,[1,0])

    def test_aucune_donnee_ne_devient_un_taux_zero(self):
        m={m['Indicateur']:m for m in cohort_metrics([],date(2026,11,17),date(2026,11,17))}
        self.assertEqual(m['Taux de ferrure reconnue'][VALUE],'')
        with self.assertRaises(ValueError):cohort_metrics([],date(2026,11,18),date(2026,11,17))

    def test_releves_historiques_ne_reutilisent_pas_la_valeur_actuelle(self):
        records=[{'Date du relevé':'2026-11-16','Relevé UTC':'2026-11-16T12:00:00+00:00','Indicateur':'Taux',VALUE:0.2,TOTAL:10},
                 {'Date du relevé':'2026-11-17','Relevé UTC':'2026-11-17T12:00:00+00:00','Indicateur':'Taux',VALUE:0.8,TOTAL:20}]
        now=datetime(2026,11,18,tzinfo=timezone.utc)
        series=history_series(records,date(2026,11,16),date(2026,11,17),now)
        selected,day=latest_history(series)
        self.assertEqual(day,'2026-11-17');self.assertEqual(selected[0][VALUE],0.8)
        old=history_series(records,date(2026,11,16),date(2026,11,16),now)
        self.assertEqual(old[0][VALUE],0.2)
        self.assertEqual(history_series(records,date(2026,11,15),date(2026,11,15)),[])
        with self.assertRaises(ValueError):history_series(records+records,date(2026,11,16),date(2026,11,17),now)
        with self.assertRaises(ValueError):history_series(records,date(2026,11,16),date(2026,11,17),datetime(2026,11,15,tzinfo=timezone.utc))

    def test_date_future_de_course_admise_mais_date_invalide_ignoree(self):
        rows=[self.row('2026-11-18'),self.row('invalide')]
        self.assertEqual(len(daily_series(rows,date(2026,11,18),date(2026,11,18))),12)
