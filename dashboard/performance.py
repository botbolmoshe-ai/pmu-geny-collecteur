"""Comparable performance of published, verified TOP3 results; read only."""
from collections import Counter, defaultdict
from datetime import date
from logic import number, result_matching

METHODS = ("direct", "ml")


def performance_rows(results, now):
    """One row per unambiguous course; require published matching for both methods."""
    keys = Counter(str(r.get("Clé course (technique)") or "").strip() for r in results)
    rows = []
    for r in results:
        key = str(r.get("Clé course (technique)") or "").strip()
        if not key or keys[key] != 1:
            continue
        try:
            day = date.fromisoformat(str(r.get("Date")))
        except (TypeError, ValueError):
            continue
        if r.get("Évaluation · État") != "EVALUE":
            continue
        scores = {}
        for method, label in (("direct", "TOP3 direct"), ("ml", "TOP3 ML")):
            published = number(r.get(label + " · Matching (%)"))
            score = result_matching(r, method, now)
            scores[method] = score if published is not None and score is not None and abs(published-score) <= 0.02 else None
        rows.append({"key":key,"date":day,"hippodrome":str(r.get("Hippodrome") or ""),**scores})
    return sorted(rows, key=lambda r:(r["date"],r["key"]))


def summarize(rows):
    paired = [r for r in rows if all(r[m] is not None for m in METHODS)]
    n = len(paired)
    # The only possible stored scores are 0, 33.33, 66.67 and 100.
    # Recover the exact integer counts, avoiding accumulated rounding error.
    hits = {m:sum(round(r[m]*3/100) for r in paired) for m in METHODS}
    return {"courses":n,"evaluated":len(rows),
            "direct_available":sum(r["direct"] is not None for r in rows),
            "ml_available":sum(r["ml"] is not None for r in rows),
            **{m:100*hits[m]/(3*n) if n else None for m in METHODS}}


def evolution(rows):
    days=defaultdict(list)
    for row in rows:
        days[row["date"]].append(row)
    cumulative=[]
    out=[]
    for day, group in sorted(days.items()):
        daily=summarize(group)
        if not daily["courses"]:
            continue
        cumulative.extend(group)
        total=summarize(cumulative)
        out.append({"Date":day,"Courses communes":daily["courses"],
            "TOP3 direct":daily["direct"],"TOP3 ML":daily["ml"],
            "Direct cumulé":total["direct"],"ML cumulé":total["ml"],
            "Courses cumulées":total["courses"]})
    return out
