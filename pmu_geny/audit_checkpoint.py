"""Audit en lecture seule du checkpoint de rattrapage PMU TROT.

Usage: python -m pmu_geny.audit_checkpoint chemin/vers/bilan.json
Aucune requête réseau, aucune écriture, aucun recalcul de pronostic.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def age_horodatage(valeur, maintenant):
    try:
        horodatage = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    if horodatage.tzinfo is None:
        return None
    return (maintenant - horodatage).total_seconds() / 3600


def analyser(bilan, maintenant=None, seuil_heures=6):
    maintenant = maintenant or datetime.now(timezone.utc)
    compteurs = bilan.get("bilan") or {}
    alertes = []
    def entier(cle):
        valeur = compteurs.get(cle)
        if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur < 0:
            alertes.append(f"COMPTEUR_INVALIDE:{cle}")
            return None
        return valeur

    total = entier("cibles_inventoriees")
    faites = entier("cibles_completees")
    restantes = entier("cibles_restantes")
    ferrures = entier("historiques_ferrures_a_completer")
    attente = entier("synchronisations_en_attente")
    if None not in (total, faites, restantes) and faites + restantes != total:
        alertes.append("INCOHERENCE_INVENTAIRE")
    lot = bilan.get("lot_96", {})
    if "lot_96" in bilan:
        if not isinstance(lot, dict):
            raise ValueError("lot_96 doit être un objet JSON")
        if type(lot.get("cibles")) is not int or lot["cibles"] != 96:
            alertes.append("DENOMINATEUR_LOT_96_MODIFIE")
        if not all(type(lot.get(k)) is int and 0 <= lot[k] <= 96 for k in ("completes", "restantes", "publiees")):
            alertes.append("LOT_96_COMPTEURS_INVALIDES")
        elif lot["publiees"] + lot["restantes"] != 96 or lot["publiees"] > lot["completes"]:
            alertes.append("LOT_96_INCOHERENT")
    statut = bilan.get("statut")
    termine = (statut == "TERMINE")
    conditions = (None not in (total, faites, restantes, ferrures, attente)
                  and total > 0 and faites == total and restantes == 0
                  and ferrures == 0 and attente == 0 and bilan.get("sync_kpi") == "OK")
    if termine and not conditions:
        alertes.append("FIN_GLOBALE_NON_PROUVEE")
    age_heures = age_horodatage(bilan.get("maj_utc"), maintenant)
    if age_heures is None:
        alertes.append("HORODATAGE_INVALIDE")
    elif age_heures < -0.1:
        alertes.append("HORODATAGE_FUTUR")
    elif age_heures > seuil_heures:
        alertes.append("BILAN_ANCIEN")

    acquisition = bilan.get("derniere_acquisition_validee_utc")
    age_acquisition = age_horodatage(acquisition, maintenant)
    if statut == "PARTIEL_REPRENABLE" and "derniere_acquisition_validee_utc" in bilan:
        if acquisition is None:
            alertes.append("AUCUNE_ACQUISITION_VALIDEE")
        elif age_acquisition is None:
            alertes.append("HORODATAGE_ACQUISITION_INVALIDE")
        elif age_acquisition < -0.1:
            alertes.append("HORODATAGE_ACQUISITION_FUTUR")
        elif age_acquisition > seuil_heures:
            alertes.append("ACQUISITION_ANCIENNE")

    return {
        "inventaire_id": bilan.get("inventaire_id"),
        "revision_inventaire": bilan.get("revision_inventaire"),
        "statut": statut,
        "fin_globale_prouvee_par_compteurs": termine and conditions and not alertes,
        "age_heures": round(age_heures, 2) if age_heures is not None else None,
        "derniere_acquisition_validee_utc": acquisition,
        "age_acquisition_heures": round(age_acquisition, 2) if age_acquisition is not None else None,
        "cibles": {"total": total, "completees": faites, "restantes": restantes},
        "lot_96": lot,
        "ferrures_restantes": ferrures,
        "synchronisations_en_attente": attente,
        "alertes": alertes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--seuil-heures", type=float, default=6)
    args = parser.parse_args()
    if args.seuil_heures <= 0:
        parser.error("--seuil-heures doit etre strictement positif")
    try:
        bilan = json.loads(args.checkpoint.read_text(encoding="utf-8"))
        if not isinstance(bilan, dict) or not isinstance(bilan.get("bilan", {}), dict):
            raise ValueError("le checkpoint et son bilan doivent être des objets JSON")
        resultat = analyser(bilan, seuil_heures=args.seuil_heures)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"CHECKPOINT_ILLISIBLE: {exc}\n")
    print(json.dumps(resultat, ensure_ascii=False, indent=2))
    return 1 if resultat["alertes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
