from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pmu_geny.priorite_cycle_v20_9 import choisir_cycle

NOW = datetime(2026, 11, 11, 10, 0, tzinfo=ZoneInfo("Europe/Paris"))

def course(minutes=180):
    return [{"code": "R2C3", "depart": (NOW + timedelta(minutes=minutes)).isoformat()}]

def test_absence_manifeste_impose_complet():
    cycle, diag = choisir_cycle(course(), {"courses": {}}, NOW, "leger")
    assert cycle == "complet"
    assert diag["a_preparer"][0]["motif"] == "MANIFESTE_ABSENT"

def test_manifeste_et_prevision_exploitable_autorisent_leger():
    state = {"courses": {"R2C3": {"identifiant_geny": "GENY-123",
                                   "statut_prevision": "HORS_FENETRE_H1"}}}
    cycle, diag = choisir_cycle(course(), state, NOW, "leger")
    assert cycle == "leger"
    assert diag["statut"] == "PREPARATION_VALIDEE"

def test_apres_h1_non_fige_est_degrade_sans_relance():
    state = {"courses": {"R2C3": {"identifiant_geny": "GENY-123",
                                   "statut_prevision": "HORS_FENETRE_H1"}}}
    cycle, diag = choisir_cycle(course(45), state, NOW, "leger")
    assert cycle == "complet"
    assert diag["manquantes"][0]["motif"] == "TOP3_NON_FIGE"

def test_donnees_insuffisantes_imposent_complet():
    state = {"courses": {"R2C3": {"identifiant_geny": "GENY-123",
                                   "statut_prevision": "DONNEES_INSUFFISANTES"}}}
    assert choisir_cycle(course(), state, NOW, "leger")[0] == "complet"

def test_cycle_complet_explicitement_demande():
    assert choisir_cycle(course(), {"courses": {}}, NOW, "complet")[0] == "complet"

def test_blocage_geny_ne_relance_pas_sans_fin():
    state = {"courses": {"R2C3": {"motif_attente_geny": "COOLDOWN_GENY"}}}
    cycle, diag = choisir_cycle(course(), state, NOW, "leger")
    assert cycle == "leger"
    assert diag["statut"] == "PREPARATION_DEGRADEE"
    assert len(diag["bloquees"]) == 1

def test_aucune_course_proche_ne_signifie_pas_preparation_validee():
    cycle, diag = choisir_cycle([], {"courses": {}}, NOW, "leger")
    assert cycle == "leger"
    assert diag["statut"] == "AUCUNE_COURSE_PROCHE_A_CONTROLER"
