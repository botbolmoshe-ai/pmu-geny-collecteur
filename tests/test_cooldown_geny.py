"""Regression: le cooldown doit accepter les journaux historiques sans fuseau."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pmu_geny.traitement_course import traiter


class CooldownGenyTests(unittest.TestCase):
    def test_ancien_horodatage_sans_fuseau_ne_declenche_pas_de_requete(self):
        with tempfile.TemporaryDirectory() as dossier:
            racine = Path(dossier)
            etat = racine / "etat_persistant.json"
            recent = (datetime.now(timezone.utc) - timedelta(minutes=2)).replace(tzinfo=None)
            etat.write_text(json.dumps({
                "version": 1, "chevaux": {},
                "dernier_blocage_geny": {"utc": recent.isoformat(), "code": "429"},
            }), encoding="utf-8")
            manifeste = {"courses": [{
                "course_id": "1234567", "nombre_partants_attendu": 1,
                "partants": [{"id": "123", "nom": "TEST", "url_geny": "https://www.geny.com/cheval/123"}],
            }]}
            with patch("pmu_geny.traitement_course.extraire_cheval", side_effect=AssertionError("Requete Geny interdite")) as extraction:
                bilan = traiter(manifeste, racine / "sortie", 1, etat_path=etat)
            extraction.assert_not_called()
            self.assertEqual(bilan["collecte_geny"], "DIFFEREE_COOLDOWN")
            self.assertEqual(bilan["courses"][0]["chevaux"][0]["statut"], "NON_TENTE_COOLDOWN")


if __name__ == "__main__":
    unittest.main()
