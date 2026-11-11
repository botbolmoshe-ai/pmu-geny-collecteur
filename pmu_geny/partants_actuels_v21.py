"""Metadonnees des partants: lecture prudente de champs explicites PMU, sans deviner."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from .auto_v18 import _list, _num, save

FIELDS = {
    "driver_jockey": ("driver", "jockey", "nomDriver", "nomJockey", "driverJockey"),
    "entraineur": ("entraineur", "trainer", "nomEntraineur"),
    "proprietaire": ("proprietaire", "owner", "nomProprietaire"),
    "ferrure": ("ferrure", "codeFerrure", "typeFerrure"),
}

def _label(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for k in ("nomComplet", "nom", "libelle", "libelleCourt", "nomPersonne", "code"):
            v = value.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return ""

def extraire_partants(raw):
    resultat = {}
    for item in _list(raw, "participants", "partants"):
        if not isinstance(item,dict):
            continue
        n=_num(item, "numPmu", "num", "numero", "numeroPmu")
        if n is None or n in resultat:
            continue
        fields={}
        for label,aliases in FIELDS.items():
            for alias in aliases:
                val=_label(item.get(alias))
                if val:
                    fields[label]=val
                    break
        resultat[n]=fields
    return resultat

def enregistrer(cache:Path, course:dict, raw):
    resultat=extraire_partants(raw)
    if not resultat:
        return "PARTANTS_NON_VERIFIES"
    doc={"date":course["date"], "course":course["code"],
         "source":"PMU_API_PARTICIPANTS",
         "capture_utc":datetime.now(timezone.utc).isoformat(),
         "chevaux":{str(n):values for n,values in resultat.items()}}
    save(Path(cache)/"partants_actuels"/f'{course["date"]}_{course["code"]}.json',doc)
    return "PARTANTS_ACTUELS_ENREGISTRES"
