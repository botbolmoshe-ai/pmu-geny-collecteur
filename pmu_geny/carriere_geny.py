"""Preuve explicite de carrière vide avant le premier départ, sans course inventée."""
import re
from datetime import datetime,timezone
from dashboard.trot_analytics.dates import PARIS

from .ferrures_geny import documents,normaliser


def confirmer_inedit(document,html,ident):
    if (document.get('performances')!=[] or document.get('nombre_extrait')!=0
            or document.get('nombre_annonce_geny') not in (None,0)):return False
    try:stamp=datetime.fromisoformat(document['extrait_utc'])
    except (KeyError,TypeError,ValueError):return False
    if stamp.tzinfo is None:return False
    source=re.search(r'/course/(\d+)',str(document.get('source_url','')))
    if not source:return False
    evidence=[];conflict=False
    def walk(value):
        nonlocal conflict
        if isinstance(value,dict):
            horse=value.get('cheval')
            if isinstance(horse,dict) and str(horse.get('id'))==str(ident) and 'nbPerformances' in value:
                music=value.get('musique') or {};participation=value.get('participation')
                course=participation.get('course') if isinstance(participation,dict) else None
                if not isinstance(course,dict):course={}
                if (type(value.get('nbPerformances')) is not int or value['nbPerformances']!=0
                        or value.get('performances')!=[] or not isinstance(music,dict)
                        or normaliser(music.get('resume'))!='INEDIT'):
                    conflict=True
                elif str(course.get('id'))==source[1]:
                    try:departure=datetime.fromisoformat(course['dateHeureCourse'])
                    except (KeyError,TypeError,ValueError):departure=None
                    if departure:
                        # L'interface a été capturée avec le fuseau Europe/Paris.
                        if departure.tzinfo is None:departure=departure.replace(tzinfo=PARIS)
                        if stamp<departure:evidence.append(departure.astimezone(timezone.utc).isoformat())
            for item in value.values():walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    for data in documents(html):walk(data)
    if conflict or len(set(evidence))!=1:return False
    document.update(nombre_annonce_geny=0,nombre_concordant=True,champs_detail_valides=True,
                    complet=True,manquants=0,historique_situation='INEDIT_AVANT_DEPART',
                    preuve_carriere_vide={'source':'GENY_DONNEES_STRUCTUREES','identifiant_cheval':str(ident),
                        'nbPerformances':0,'musique':'Inédit','depart_utc':evidence[0]})
    return True
