"""Inventaire hors ligne des chevaux du registre et des historiques Geny.

Entrées CSV exportées depuis les onglets Google Sheets; aucune requête réseau.
Ne modifie jamais les historiques, le cache ou Google Sheets.
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()

def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def audit(courses, historiques):
    horses = defaultdict(lambda: {"noms": set(), "ids": set(), "courses": 0})
    for row in courses:
        name = (row.get("Cheval") or "").strip()
        if not name:
            continue
        key = norm(name)
        h = horses[key]
        h["noms"].add(name)
        h["courses"] += 1
    history = defaultdict(list)
    sources = defaultdict(set)
    for row in historiques:
        name = row.get("cheval") or ""
        key = norm(name)
        if not key:
            continue
        history[key].append(row)
        if row.get("identifiant_cheval"):
            horses[key]["ids"].add(str(row["identifiant_cheval"]))
        sources[key].add("GENY" if "geny.com" in (row.get("source_url") or "").lower()
                         else "AUTRE_OU_INCONNUE")
    backlog = []
    for key, h in horses.items():
        rows = history[key]
        unique = {r.get("cle_performance") or
                  "|".join(str(r.get(k) or "") for k in
                           ("identifiant_cheval","date_course_historique","hippodrome","classement"))
                  for r in rows}
        geny = sum("geny.com" in (r.get("source_url") or "").lower() for r in rows)
        status = "ABSENT" if not rows else ("A_COMPLETER_GENY" if not geny else "A_VERIFIER_COMPLETUDE")
        backlog.append({"nom": sorted(h["noms"])[0], "identifiants_registre": sorted(h["ids"]),
                        "apparitions": h["courses"], "lignes_historique": len(rows),
                        "performances_uniques": len(unique), "lignes_geny": geny,
                        "statut": status, "sources": sorted(sources[key])})
    priority = {"ABSENT": 0, "A_COMPLETER_GENY": 1, "A_VERIFIER_COMPLETUDE": 2}
    backlog.sort(key=lambda x: (priority[x["statut"]], -x["apparitions"], x["nom"]))
    return {"chevaux_uniques": len(horses),
            "sans_historique": sum(x["statut"] == "ABSENT" for x in backlog),
            "sans_ligne_geny": sum(x["lignes_geny"] == 0 for x in backlog),
            "chevaux_avec_ligne_geny": sum(x["lignes_geny"] > 0 for x in backlog),
            "lignes_historique_existantes": sum(x["lignes_historique"] for x in backlog),
            "avertissement": "Les lignes Geny ne prouvent pas la completude de carriere; verification des manifests et du cache requise.",
            "file_rattrapage": backlog}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--courses-csv", type=Path, required=True)
    p.add_argument("--historiques-csv", type=Path, required=True)
    p.add_argument("--rapport", type=Path, required=True)
    args = p.parse_args()
    result = audit(read_rows(args.courses_csv), read_rows(args.historiques_csv))
    args.rapport.parent.mkdir(parents=True, exist_ok=True)
    args.rapport.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "file_rattrapage"}, ensure_ascii=False))

if __name__ == "__main__":
    main()
