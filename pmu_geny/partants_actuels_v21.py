"""Metadonnees des partants: lecture prudente de champs explicites PMU, sans deviner."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import re
from .auto_v18 import _list, _num, save

FIELDS = {
    "driver_jockey": ("driver", "jockey", "nomDriver", "nomJockey", "driverJockey"),
    "entraineur": ("entraineur", "trainer", "nomEntraineur"),
    "proprietaire": ("proprietaire", "owner", "nomProprietaire"),
    "ferrure": ("ferrure", "codeFerrure", "typeFerrure", "ferrureCheval"),
    "sexe": ("sexe", "sexeCheval", "sexeParticipant"),
    "age_ans": ("age", "ageCheval", "ageParticipant"),
    "gains_euros": ("gainsCarriere", "gainsParticipant", "gains", "gainCarriere",
                     "montantGains", "gainTotal", "gainsCheval"),
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

def age_valide(value):
    if isinstance(value,bool):return None
    raw=str(value or '').strip()
    if re.fullmatch(r'\d{1,2}',raw):
        age=int(raw)
        return age if 2<=age<=25 else None
    return None

def gains_valides(value):
    if isinstance(value,dict):
        for key in ('montant','valeur','gains','total','montantGains'):
            if key in value:return gains_valides(value[key])
        return None
    if isinstance(value,bool) or value is None:return None
    text=str(value).replace('\u00a0','').replace(' ','').replace('€','').strip()
    if not re.fullmatch(r'\d+(?:[.,]\d{1,2})?',text):return None
    amount=float(text.replace(',','.'))
    return round(amount,2) if 0<=amount<100_000_000 else None

def sexe_normalise(value):
    if isinstance(value,dict):
        value=value.get('libelle') or value.get('code') or value.get('nom') or ''
    key=str(value or '').strip().upper()
    return {
        'M':'Mâle','MALE':'Mâle','MÂLE':'Mâle','MALES':'Mâle','MÂLES':'Mâle','ENTIER':'Mâle','ENTIERS':'Mâle',
        'F':'Femelle','FEMELLE':'Femelle','FEMELLES':'Femelle','JUMENT':'Femelle','POULICHE':'Femelle',
        'H':'Hongre','HONGRE':'Hongre','HONGRES':'Hongre'
    }.get(key,'')

def ferrure_historique_explicite(value):
    """Codes explicites seulement, jamais un tiret ou 'D' isolé dans Geny."""
    match=re.search(r'(?<![A-Za-z0-9])(?:DP/PA|DA/PP|D4|P4|DP|DA|PA|PP)(?![A-Za-z0-9])',
                    str(value or ''),re.I)
    return match.group(0).upper() if match else ''

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
        for alias in FIELDS["age_ans"]:
            age=age_valide(item.get(alias))
            if age is not None:fields['age_ans']=age;break
        for alias in FIELDS["gains_euros"]:
            gains=gains_valides(item.get(alias))
            if gains is not None:fields['gains_euros']=gains;break
        for alias in FIELDS["sexe"]:
            sexe=sexe_normalise(item.get(alias))
            if sexe:fields['sexe']=sexe;break
        if fields.get('sexe'):
            fields['sexe']=sexe_normalise(fields['sexe']) or fields['sexe']
        for nom_key in ("nomCheval","nom","nomParticipant"):
            nom=_label(item.get(nom_key))
            if nom:
                fields["nom"]=nom
                break
        if item.get("nonPartant") is True or str(item.get("statut","")).upper() in ("NP","NON_PARTANT"):
            fields["statut_np"]="NON_PARTANT"
        elif item.get("nonPartant") is False or str(item.get("statut","")).upper()=="PARTANT":
            fields["statut_np"]="PARTANT"
        else:
            fields["statut_np"]="NP_NON_VERIFIE"
        resultat[n]=fields
    return resultat

def enregistrer(cache:Path, course:dict, raw):
    resultat=extraire_partants(raw)
    if not resultat:
        return "PARTANTS_NON_VERIFIES"
    samples=_list(raw,"participants","partants")
    observed=sorted(str(k) for k in samples[0].keys()) if samples and isinstance(samples[0],dict) else []
    doc={"date":course["date"], "course":course["code"],
         "champs_participant_pmu_observes":observed,
         # Champs publics diagnostiques des trois premiers partants, sans
         # déduction de la structure PMU.
         "diagnostic_profils_pmu":[
             {"nom":str(item.get("nom",""))[:80],
              "deferre":item.get("deferre"),
              "gainsParticipant":item.get("gainsParticipant")}
             for item in samples[:3] if isinstance(item,dict)],
         "source":"PMU_API_PARTICIPANTS",
         "capture_utc":datetime.now(timezone.utc).isoformat(),
         "chevaux":{str(n):values for n,values in resultat.items()}}
    save(Path(cache)/"partants_actuels"/f'{course["date"]}_{course["code"]}.json',doc)
    return "PARTANTS_ACTUELS_ENREGISTRES"
