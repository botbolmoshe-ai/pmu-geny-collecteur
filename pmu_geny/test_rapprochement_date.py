"""Test isolé PMU–Geny pour une date future, sans prédiction ni écriture de production."""
import argparse
import json
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from pmu_geny.auto_v18 import BASE, get_json, programme_diagnostic
from pmu_geny.rapprochement_v20_6 import index_programme, rapprocher

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-11-12")
    parser.add_argument("--output", default="resultats/test_rapprochement_2026-11-12.json")
    args = parser.parse_args()
    datetime.strptime(args.date, "%Y-%m-%d")
    url = BASE + datetime.strptime(args.date, "%Y-%m-%d").strftime("%d%m%Y")
    pmu = get_json(url)
    courses, diagnostic = programme_diagnostic(pmu, args.date)
    courses = [c for c in courses if 8 <= datetime.fromisoformat(c["depart"]).hour < 19]
    with tempfile.TemporaryDirectory(prefix="pmu-geny-test-") as tmp:
        root = Path(tmp)
        geny = index_programme(root, args.date, root / "etat_persistant.json", ttl_heures=0)
    results = []
    for course in courses:
        decision = rapprocher(course, geny.get("courses", [])) if geny.get("statut") == "OK" else {"statut": "INDEX_GENY_INDISPONIBLE"}
        results.append({"pmu": course["code"], "hippodrome": course["hippodrome"], "nom": course["nom"],
                        "depart": course["depart"], "geny_id": decision.get("geny_id"),
                        "statut": decision["statut"], "methode": decision.get("methode"),
                        "preuves": decision.get("preuves", {})})
    counts = Counter(x["statut"] for x in results)
    report = {"date": args.date, "perimetre": "France trot 08:00-19:00 Europe/Paris",
              "pmu_courses": len(courses), "geny_index_statut": geny.get("statut"),
              "geny_index_courses": len(geny.get("courses", [])),
              "geny_codes_rc_documentes": geny.get("codes_rc_documentes", 0),
              "statuts": dict(counts), "diagnostic_pmu": diagnostic, "associations": results}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("BILAN_RAPPROCHEMENT " + json.dumps({k: report[k] for k in ("date", "pmu_courses", "geny_index_statut", "geny_index_courses", "statuts")}, ensure_ascii=False), flush=True)
    for item in results:
        print("ASSOCIATION " + json.dumps(item, ensure_ascii=False), flush=True)
    if not courses or geny.get("statut") != "OK":
        raise SystemExit("TEST_NON_CONCLUANT: programme PMU vide ou index Geny indisponible")

if __name__ == "__main__":
    main()
