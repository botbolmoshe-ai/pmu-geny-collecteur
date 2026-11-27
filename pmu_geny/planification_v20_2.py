"""Planification J-1 / jour J, avec arrêt strict des prédictions au départ."""
from __future__ import annotations
from datetime import datetime, timedelta
from dashboard.trot_analytics.dates import PARIS


def decision_autorisee(now, date, depart):
    if now.tzinfo is None or depart.tzinfo is None:
        raise ValueError('Horodatages avec fuseau requis')
    local=now.astimezone(PARIS)
    # Dès le début du jour J, préparer une sélection préliminaire si les données
    # suffisent. Attendre 07 h bloquait aussi la collecte d'historiques la nuit.
    return (date==local.date().isoformat() and
            depart.astimezone(PARIS).date().isoformat()==date and now<depart)

def selectionner_courses(courses, now, date, selection, complet, etat, max_courses=12):
    """Liste des courses pertinentes par priorité, sans travailler sur des archives.

    Preparation J+1 des que le programme est disponible. Collecte incrementalement
    et ne predit jamais apres le depart. Les arrivees recentes restent traitables.
    """
    if now.tzinfo is None: raise ValueError('Heure locale requise')
    today=now.astimezone(PARIS).date()
    day=datetime.fromisoformat(date).date()
    if day<today-timedelta(days=1) or day>today+timedelta(days=1):return []
    previous=etat.get('courses',{})
    selected=[]
    for c in courses:
        if selection and c['code'] not in selection:continue
        try: departure=datetime.fromisoformat(c['depart'])
        except (ValueError,TypeError,KeyError):continue
        if departure.tzinfo is None:continue
        remaining=(departure-now).total_seconds()/60
        record=previous.get(c['code'],{})
        if remaining<=0:
            # Une fenêtre post-course courte, uniquement pour récupérer des
            # arrivées et audits manquants, jamais pour prédire.
            if remaining < -2160:continue
            if record.get('etat')=='TERMINE_ARCHIVE':continue
            priority=(4, abs(remaining))
        elif day>today:
            if not complet:continue
            priority=(3,remaining)
        elif remaining <= 120:
            priority=(0,remaining)
        elif remaining <= 360:
            if not complet:continue
            priority=(1,remaining)
        else:
            if not complet:continue
            priority=(2,remaining)
        if not complet and remaining>90:continue
        # Le temps jusqu'au départ reste prioritaire; P1 précède P2 à urgence égale.
        rang_metier=0 if c.get('priorite_metier')=='P1' else 1
        selected.append(((priority[0],priority[1],rang_metier),c))
    selected.sort(key=lambda x:x[0])
    return [c for _,c in selected[:max_courses]]
