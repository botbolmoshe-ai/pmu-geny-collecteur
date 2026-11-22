"""Regression: a stale evaluation label cannot hide verified pre-start Direct scores."""
from datetime import datetime, timezone
from dashboard.trot_analytics.logic import result_matching
from dashboard.trot_analytics.performance import performance_rows


def test_prestart_direct_result_with_stale_status_is_visible():
    row = {
        "Clé course (technique)": "2026-11-21|GRAIGNES|R10C7",
        "Date": "2026-11-21",
        "Hippodrome": "GRAIGNES",
        "Départ (Paris)": "2026-11-21T16:18:00+01:00",
        "TOP3 direct · Heure calcul UTC": "2026-11-21T08:15:34+00:00",
        "TOP3 direct · Chevaux": "8,3,12",
        "TOP3 direct · Chevaux à l’arrivée (0–3)": "3",
        "TOP3 direct · Matching (%)": "100",
        "Arrivée · N° officiels": "12,8,3",
        "Arrivée · Vérifiée UTC": "2026-11-21T16:14:53+00:00",
        "Évaluation · État": "ARRIVEE_SANS_TOP3_PUBLIE",
    }
    now = datetime(2026, 11, 22, tzinfo=timezone.utc)
    assert result_matching(row, "direct", now) == 100
    assert result_matching(row, "ml", now) is None
    rows = performance_rows([row], now)
    assert len(rows) == 1 and rows[0]["direct"] == 100
    assert rows[0]["ml"] is None


def test_poststart_prediction_is_never_accepted():
    row = {
        "Départ (Paris)": "2026-11-21T16:18:00+01:00",
        "TOP3 direct · Heure calcul UTC": "2026-11-21T16:00:00+00:00",
        "TOP3 direct · Chevaux": "8,3,12",
        "TOP3 direct · Chevaux à l’arrivée (0–3)": "3",
        "TOP3 direct · Matching (%)": "100",
        "Arrivée · N° officiels": "12,8,3",
        "Arrivée · Vérifiée UTC": "2026-11-21T16:14:53+00:00",
        "Évaluation · État": "EVALUE",
    }
    assert result_matching(row, "direct", datetime(2026, 11, 22, tzinfo=timezone.utc)) is None
