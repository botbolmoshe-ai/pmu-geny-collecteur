"""Planification J-1 / jour J, avec arrêt strict des prédictions au départ."""
from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PARIS=ZoneInfo('Europe/Paris')

def selectionner_courses(courses, now, date, selection, complet, etat, max_courses=12):
    """Liste des courses pertinentes par priorité, sans travailler sur des archives.

    Un cycle léger ne vérifie que les départs à <= 90 minutes et les arrivées
    récentes. Un cycle complet prépare progressivement les départs futurs, y
    compris demain après 18 h. Jamais de collecte ni prédiction après l'heure
    programmée du départ; les arrivées récentes restent traitables.
    """
    if now.tzinfo is None: raise ValueError('Heure locale requise')
    today=now.astimezone(PARIS).date()
    day=datetime.fromisoformat(date).date()
    if day<today or day>today+timedelta(days=1):return []
    if day>today and now.astimezone(PARIS).hour<18:return []
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
            if day!=today or remaining < -240:continue
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
        selected.append((priority,c))
    selected.sort(key=lambda x:x[0])
    return [c for _,c in selected[:max_courses]]
