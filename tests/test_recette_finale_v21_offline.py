"""Vérifier l'import historique et le registre actif avec la même recette."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pmu_geny import recette_finale_v21


class RecetteFinaleV21Tests(unittest.TestCase):
    def test_registre_actif_accepte_les_ajouts_et_refuse_les_manques(self):
        cas = (
            (2, False, []),
            (3, False, ["PERFORMANCES_IMPORTEES:3/2"]),
            (3, True, []),
            (1, True, ["PERFORMANCES_IMPORTEES:1/2"]),
        )
        for nombre, evolutif, attendus in cas:
            with self.subTest(nombre=nombre, evolutif=evolutif), tempfile.TemporaryDirectory() as dossier:
                racine = Path(dossier)
                historique = racine / "historiques" / "123"
                historique.mkdir(parents=True)
                performances = [
                    {"date": f"2026-11-0{jour}", "hippodrome": "Vincennes", "discipline": "TROT_ATTELE",
                     "distance_m": 2700, "classement": 1}
                    for jour in range(1, nombre + 1)
                ]
                (historique / "historique_geny.json").write_text(json.dumps({
                    "nombre_annonce_geny": nombre, "nombre_extrait": nombre, "performances": performances,
                }))
                (historique / "historique_geny.csv").touch()
                (racine / "etat_persistant.json").write_text(json.dumps({
                    "version": 1, "chevaux": {"123": {"statut": "COMPLET", "nombre_extrait": nombre}},
                }))
                (racine / "manifestes").mkdir()
                (racine / "manifestes" / "GENY-123.json").touch()
                rapport = racine / "rapport.json"
                args = ["recette_finale_v21", "--source", str(racine), "--rapport", str(rapport)]
                if evolutif:
                    args.append("--registre-evolutif")
                with (
                    patch.object(sys, "argv", args),
                    patch.object(recette_finale_v21, "HORSES", {"123": "Cheval test"}),
                    patch.object(recette_finale_v21, "EXPECTED_PERFS", 2),
                    redirect_stdout(io.StringIO()),
                ):
                    if attendus:
                        with self.assertRaises(SystemExit) as arret:
                            recette_finale_v21.main()
                        self.assertEqual(arret.exception.code, 1)
                    else:
                        recette_finale_v21.main()
                self.assertEqual(json.loads(rapport.read_text())["problemes"], attendus)
