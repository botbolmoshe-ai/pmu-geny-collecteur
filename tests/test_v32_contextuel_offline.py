"""V32: tests sans reseau de la contextualisation du TOP3 direct."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pmu_geny.formes_contextuelles_v32 import (
    _musique_pmu, _historique_contextuel, noter_partant,
)
from pmu_geny.top3_independants_v22 import calculer

NOW = datetime(2026, 11, 15, 9, tzinfo=timezone.utc)
COURSE = {"date": "2026-11-15", "code": "R1C2",
          "depart": "2026-11-15T14:00:00+01:00",
          "nombre_declares": 4, "distance_m": 2700,
          "discipline": "TROT_ATTELE", "hippodrome": "HIPPODROME DE PARIS-VINCENNES"}


def hist(races, statut="COMPLET"):
    return {"statut": statut, "performances": races}


def perf(date="2026-10-25", rang="1", distance="2700", hippodrome="Vincennes",
         discipline="Attelé", ferrure="D4"):
    return {"date": date, "classement": rang, "distance_m": distance,
            "hippodrome": hippodrome, "discipline": discipline, "ferrure": ferrure}


class ScoresV32(unittest.TestCase):
    def test_musique_pas_de_confusion_monte_attele(self):
        score, count = _musique_pmu({"musique": "1m 3a 2a 4m"}, "a")
        self.assertEqual(count, 2)
        self.assertLess(score, 4)
        self.assertEqual(_musique_pmu({"musique": "1m2m"}, "a"), (None, 0))
        self.assertEqual(_musique_pmu({"musique": "Da Ta Aa"}, "a")[1], 3)

    def test_course_identique_plus_comparable_qu_une_victoire_lointaine(self):
        proche = _historique_contextuel(hist([
            perf(rang="2"), perf("2026-10-20", rang="2")]), COURSE, {"ferrure": "D4"})
        loin = _historique_contextuel(hist([
            perf(rang="1", distance="1600", hippodrome="Caen", ferrure="P4"),
            perf("2026-10-20", rang="1", distance="1600", hippodrome="Caen", ferrure="P4"),
        ]), COURSE, {"ferrure": "D4"})
        self.assertGreater(proche["poids_total"], loin["poids_total"])
        self.assertGreater(proche["score"], loin["score"])
        self.assertEqual(proche["ferrures_comparees"], 2)
        self.assertEqual(proche["courses_distance_proche"], 2)

    def test_allocation_inferieure_reduit_comparabilite(self):
        from pmu_geny.formes_contextuelles_v32 import _facteur_niveau
        cible={**COURSE, "allocation_eur": 120000}
        basse={"texte_source": "12/10/26 | Caen | Attelé | 2 700 | Crse D | 20 000 €"}
        proche={"texte_source": "12/10/26 | Vincennes | Attelé | 2 700 | 120 000 €"}
        self.assertEqual(_facteur_niveau(cible,basse),(0.70,True))
        self.assertEqual(_facteur_niveau(cible,proche),(1.0,True))
        self.assertEqual(_facteur_niveau(cible,{"texte_source":""}),(1.0,False))

    def test_disqualifications_et_pas_de_reconstruction_des_ferrures(self):
        données = hist([perf(rang="Dai", ferrure=""),
                        perf("2026-10-20", rang="2", ferrure="")])
        score = _historique_contextuel(données, COURSE, {"ferrure": "D4"})
        self.assertEqual(score["ferrures_comparees"], 0)
        self.assertEqual(score["performances_valides"], 2)
        self.assertLess(score["score"], 2.5)

    def test_pas_de_fuite_temporelle_ni_de_melange_monte(self):
        données = hist([
            perf("2026-11-16", rang="1"),
            perf("2026-11-15", rang="1"),
            perf("2026-10-15", rang="1", discipline="Monté"),
            perf("2026-10-10", rang="3"),
        ])
        item = _historique_contextuel(données, COURSE, {})
        self.assertEqual(item["performances_valides"], 1)

    def test_historique_absent_musique_pmu_secours(self):
        item = noter_partant({"musique": "1a2a"}, COURSE, {}, {"ferrure": "D4"})
        self.assertEqual(item["source_forme"], "PMU_MUSIQUE_SEULE")
        self.assertEqual(item["historique_exploitable"], 0)
        self.assertIsNotNone(item["score"])

    def test_historique_geny_sans_musique_pmu(self):
        lien = {"cheval_id": "42", "methode": "NOM_EXACT_UNIQUE",
                "historique": hist([perf("2026-11-01", "2"), perf("2026-10-10", "3")])}
        item = noter_partant({}, COURSE, lien, {"ferrure": "D4"})
        self.assertEqual(item["source_forme"], "GENY_CONTEXTUEL_SEUL")
        self.assertEqual(item["historique_exploitable"], 2)

    def test_homonyme_ambigu_interdit_historique(self):
        lien = {"cheval_id": "", "methode": "NOM_AMBIGU", "historique": hist([perf()])}
        self.assertEqual(noter_partant({}, COURSE, lien, {})["score"], None)

    def test_historique_donnees_incoherentes_rejete(self):
        lien = {"cheval_id": "42", "methode": "NOM_EXACT_UNIQUE",
                "historique": hist([perf()], "DONNEES_INCOHERENTES")}
        self.assertEqual(noter_partant({"musique":"3a"}, COURSE, lien, {})["source_forme"],
                         "PMU_MUSIQUE_SEULE")


class IntegrationV32(unittest.TestCase):
    def test_pmu_geny_palimpseste_scores_sources_et_np(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            def write(path, doc):
                p = cache / path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(doc), encoding="utf-8")
            write("etat_persistant.json", {"chevaux": {"42": {"nom": "Étoile d Or", "statut": "COMPLET"}}})
            write("historiques/42/historique_geny.json",
                  hist([perf("2026-11-01", "1"), perf("2026-10-15", "2"), perf("2026-09-25", "3")]))
            chevaux = [
                {"numPmu": 1, "nomCheval": "Etoile d Or", "musique": "3a4a5a",
                 "nonPartant": False, "deferre": "DEFERRE_ANTERIEURS_POSTERIEURS"},
                {"numPmu": 2, "nomCheval": "Second", "musique": "1a2a3a", "nonPartant": False},
                {"numPmu": 3, "nomCheval": "Trois", "musique": "Da5a", "nonPartant": False},
                {"numPmu": 4, "nomCheval": "Sans forme", "nonPartant": False},
            ]
            status = calculer(cache, COURSE, {"participants": chevaux}, NOW)
            self.assertEqual(status["direct"], "CALCULE_PARTIEL")
            doc = json.loads((cache/"pronostics/2026-11-15_R1C2_direct.json").read_text())
            self.assertEqual(len(doc["top3"]), 3)
            self.assertEqual(doc["partants_eligibles"], 4)
            self.assertEqual(doc["couverture_sources"]["sans_score"], 1)
            self.assertEqual(doc["couverture_sources"]["geny_historique"], 1)
            first = next(h for h in doc["classement_complet"] if h["numero"] == 1)
            self.assertEqual(first["source_forme"], "PMU+GENY_CONTEXTUEL")
            self.assertEqual(first["identifiant_historique"], "42")
            self.assertEqual(first["ferrures_historiques_comparees"], 3)
            self.assertEqual(doc["version_moteur"], "direct-v32-contextuel")
            # Les cotes n'ont pas de donnee: aucune imputation depuis le direct.
            self.assertEqual(status["cotes"], "DONNEES_INSUFFISANTES")
            # Une nouvelle execution apres depart ne reecrit aucun instantane.
            avant = (cache/"pronostics/2026-11-15_R1C2_direct.json").read_text()
            self.assertEqual(calculer(cache, COURSE, {"participants": chevaux},
                                     datetime(2026, 11, 15, 14, tzinfo=timezone.utc))["direct"],
                             "APRES_DEPART")
            self.assertEqual((cache/"pronostics/2026-11-15_R1C2_direct.json").read_text(), avant)

    def test_ferrure_tierce_utilisee_seulement_avec_preuve_et_heure(self):
        def run_with(capture, name="Etoile", url="https://www.equidia.fr/course-test", source="equidia"):
            with tempfile.TemporaryDirectory() as tmp:
                cache = Path(tmp)
                def write(rel, doc):
                    path = cache/rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(doc), encoding="utf-8")
                write("etat_persistant.json", {"chevaux": {"42": {"nom": "Etoile", "statut": "COMPLET"}}})
                write("historiques/42/historique_geny.json",
                      hist([perf("2026-11-01", "2"), perf("2026-10-15", "1")]))
                write("partants_actuels/2026-11-15_R1C2.json", {
                    "date": "2026-11-15", "course": "R1C2",
                    "capture_utc": "2026-11-15T07:00:00+00:00",
                    "chevaux": {"1": {"nom": name, "ferrure": "D4", "provenance_champs": {
                        "ferrure": {"source": source, "url": url,
                                    "capture_utc": capture}}}}
                })
                partants=[{"numPmu":i, "nomCheval":("Etoile" if i==1 else "Cheval "+str(i)),
                           "musique":"2a3a", "nonPartant":False}
                          for i in range(1,5)]
                calculer(cache, COURSE, {"participants":partants}, NOW)
                doc=json.loads((cache/"pronostics/2026-11-15_R1C2_direct.json").read_text())
                h=next(x for x in doc["classement_complet"] if x["numero"]==1)
                return h["ferrures_historiques_comparees"], h["source_ferrure_courante"]

        self.assertEqual(run_with("2026-11-15T08:00:00+00:00"), (2,"SOURCEE_EQUIDIA"))
        self.assertEqual(run_with("2026-11-15T13:20:00+00:00"), (0,"NON_DOCUMENTEE"))
        self.assertEqual(run_with("2026-11-15T08:00:00+00:00",name="Autre"), (0,"NON_DOCUMENTEE"))
        self.assertEqual(run_with("2026-11-15T08:00:00+00:00",url=""), (0,"NON_DOCUMENTEE"))
        self.assertEqual(run_with("2026-11-15T08:00:00+00:00",source="zeturf"), (0,"NON_DOCUMENTEE"))

    def test_non_partant_exclu_et_pas_de_score_invente(self):
        with tempfile.TemporaryDirectory() as tmp:
            participants = [
                {"numPmu": i, "nomCheval": f"Cheval {i}",
                 "musique": "1a2a", "nonPartant": i == 1}
                for i in range(1, 5)]
            res = calculer(tmp, COURSE, {"participants": participants}, NOW)
            self.assertEqual(res["direct"], "CALCULE_COMPLET")
            path = Path(tmp) / "pronostics/2026-11-15_R1C2_direct.json"
            self.assertNotIn(1, [x["numero"] for x in json.loads(path.read_text())["top3"]])


if __name__ == "__main__":
    unittest.main()
