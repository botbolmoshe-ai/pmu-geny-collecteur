"""TOP3 direct avec contexte PMU/Geny verifie; TOP3 cotes independant.
Jamais de cotes dans la methode directe, ni de donnees apres depart.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path
from .ml_v19 import load, save
from .auto_v18 import _list, _num
from .cotes_v19 import calculer_cotes, collecter
from .departs_trot import POIDS_FORME_MEME_DEPART
from .profils_partants import PRIORITE, VERSION_PROFILS, evaluer_profils

VERSION_MOTEUR = 'direct-v32-contextuel'

def _musique(value):
    if isinstance(value,dict):
        value=value.get('musique') or value.get('libelle') or ''
    if not isinstance(value,str):return []
    # Les performances PMU sont souvent collees. Une annee n'est pas une place.
    value=re.sub(r'\(\s*\d{2}(?:\d{2})?\s*\)', ' ', value)
    pattern=r'\d{1,2}[am]|[datr][am]'
    tokens=re.findall(pattern,value,flags=re.I)
    if tokens:
        residue=re.sub(pattern,'',value,flags=re.I)
    else:
        # Compatibilite des archives sans indication d'allure: 1-2-3, D 4 5.
        pattern=r'\d{1,2}|[datr]'
        tokens=re.findall(pattern,value,flags=re.I)
        residue=re.sub(pattern,'',value,flags=re.I)
    if re.sub(r'[\s,;/|.\-]+','',residue):return []
    return tokens[:5]

def _form_score(participant):
    value=next((participant[k] for k in ('musique','musiqueCheval','derniereMusique')
                if participant.get(k)),None)
    series=_musique(value)
    if not series:return None
    points={1:5.0,2:3.5,3:2.5,4:1.5,5:1.0}
    ranks=[int(re.match(r'\d+',t).group()) if t[0].isdigit() else 0 for t in series]
    return round(sum(points.get(r,0.0)*(1-0.12*i) for i,r in enumerate(ranks)),3)

def calculer(cache, course, raw, now=None, clock=None, *, inclure_cotes=True):
    """Compatibilité des appels existants, avec publication du marché séparée."""
    now = now or datetime.now(timezone.utc)
    output = {}
    if inclure_cotes:
        collecter(cache, course, raw, now)
        output['cotes'] = calculer_cotes(cache, course, now, clock)
    output['direct'] = _calculer_direct(cache, course, raw, now, clock)
    return output


def _calculer_direct(cache, course, raw, now, clock):
    depart=datetime.fromisoformat(course['depart'])
    if now.tzinfo is None or depart.tzinfo is None:raise ValueError('Fuseau obligatoire')
    if now>=depart:return 'APRES_DEPART'
    participants=_list(raw,'participants','partants')
    if not participants:return 'PARTANTS_ABSENTS'
    from .formes_contextuelles_v32 import forme_meme_depart, noter_partant
    from .liaison_chevaux_v22 import etablir
    from .partants_actuels_v21 import extraire_partants
    from .signaux_geny import candidat_classement, signaux as signaux_historiques
    profils=extraire_partants(raw)
    # Les critères courants proviennent exclusivement du relevé PMU fourni.
    identites=[{'numero':numero,'nom':profil['nom']}
               for numero,profil in profils.items() if profil.get('nom')]
    # Un nom exact unique ou un identifiant Geny confirme est obligatoire.
    liens=etablir(cache,course,identites)
    base=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}"
    expected=course.get('nombre_declares')
    old = load(Path(str(base)+'_direct.json'), {}) or {}
    known_np = set()
    try:
        if datetime.fromisoformat(old['calcul_utc']) <= now and old.get('depart') == course['depart']:
            known_np.update(int(n) for n in old.get('non_partants_confirmes', []))
    except (KeyError, TypeError, ValueError):
        pass
    all_numbers=set()
    eligible=[];direct=[]
    signaux = {}
    historiques = {}
    for item in participants:
        if not isinstance(item,dict):continue
        n=_num(item,'numPmu','num','numero','numeroPmu')
        if n is None or n in all_numbers:
            return 'PARTANTS_INCOHERENTS'
        all_numbers.add(n)
        if item.get('nonPartant') is True or str(item.get('statut','')).upper() in ('NP','NON_PARTANT'):
            known_np.add(n)
            continue
        if item.get('nonPartant') is False or str(item.get('statut','')).upper()=='PARTANT':
            known_np.discard(n)  # Nouvelle confirmation explicite PMU.
        if n in known_np:continue
        eligible.append(n)
        profil = profils.get(n, {})
        label = profil.get('nom', '')
        lien = liens.get(str(n), {})
        info=noter_partant(item,course,lien,profil)
        if label:
            signaux[str(n)] = evaluer_profils(course, lien, profil, now)
        if info['score'] is not None and label:
            historiques[n] = signaux_historiques(course, profil, lien, now)
            direct.append({'numero':n,'nom':label,'score_direct':info['score'],
                           'source_forme':info['source_forme'],
                           'qualite_score':info['qualite'],
                           'musique_exploitable':info['musique_exploitable'],
                           'historique_exploitable':info['historique_exploitable'],
                           'distance_proche':info.get('distance_proche',0),
                           'comparabilite_moyenne':info.get('comparabilite_moyenne'),
                           'ferrures_historiques_comparees':info.get('ferrures_historiques_comparees',0),
                           'source_ferrure_courante':profils.get(n,{}).get('source_ferrure','PMU' if profils.get(n,{}).get('ferrure') else 'NON_DOCUMENTEE'),
                           'identifiant_historique':info.get('identifiant_historique')})
            forme_depart = forme_meme_depart(lien.get('historique') or {}, course, profil, now)
            if forme_depart:
                direct[-1].update(forme_geny_meme_depart=forme_depart['score'],
                                  sorties_geny_meme_depart=forme_depart['performances_valides'])
    ranking = direct
    observed_at = now.isoformat()
    reuse_previous = False
    old_ranking = [h for h in old.get('classement_complet', []) if int(h['numero']) not in known_np]
    old_usable = False
    try:
        old_usable = (datetime.fromisoformat(old['calcul_utc']) <= now
                      and old.get('depart') == course['depart'] and old.get('version_moteur') == VERSION_MOTEUR)
    except (KeyError, ValueError, TypeError):
        pass
    complete_list = expected is not None and len(all_numbers) == int(expected)
    if old_usable and len(old_ranking) > len(ranking) and not (complete_list and len(eligible) < 3):
        if known_np == set(old.get('non_partants_confirmes', [])):
            return 'ANCIEN_RELEVE_PLUS_COMPLET'
        ranking = old_ranking
        reuse_previous = True
        observed_at = old.get('donnees_observees_utc', old['calcul_utc'])
        signaux = {n: signal for n, signal in old.get('profils_partants', {}).items() if int(n) not in known_np}
    ranking.sort(key=lambda h: (-h['score_direct'], -PRIORITE.get(
        signaux.get(str(h['numero']), {}).get('statut'), 0), h['numero']))
    sufficient = len(ranking) >= 3 and not (complete_list and len(eligible) < 3)
    doc = {'date':course['date'],'course':course['code'],'depart':course['depart'],
           'mode':'DIRECT','donnees_observees_utc':observed_at,
           'version_moteur':VERSION_MOTEUR,'non_partants_confirmes':sorted(known_np),
           'statut':('COMPLET' if complete_list and len(ranking)==len(eligible) else 'PARTIEL') if sufficient else 'DONNEES_INSUFFISANTES',
           'observations':len(ranking),'partants_eligibles':len(eligible),
           'classement_complet':ranking if sufficient else [],'top3':ranking[:3] if sufficient else [],
           'note':'Direct heuristique: musique PMU et historiques Geny anterieurs'
                  ' ponderes par discipline, distance, hippodrome, ferrure documentee'
                  ' et anciennete. Scores non calibres; facteurs manquants explicites.'}
    if not reuse_previous or old.get('version_profils'):
        doc['version_profils'] = old['version_profils'] if reuse_previous else VERSION_PROFILS
        doc['profils_partants'] = signaux
    # Calcul expérimental conservé avec la même observation que le direct.
    # La forme du même mode est lissée dans le moteur contextuel.
    if sufficient and any('forme_geny_meme_depart' in horse for horse in ranking):
        def score_experimental(horse):
            base_score = horse['score_direct']
            shape = horse.get('forme_geny_meme_depart', base_score)
            return base_score + POIDS_FORME_MEME_DEPART * (shape - base_score)

        candidate = sorted(ranking, key=lambda horse: (
            -score_experimental(horse),
            -PRIORITE.get(signaux.get(str(horse['numero']), {}).get('statut'), 0),
            horse['numero'],
        ))
        doc['candidat_depart'] = {
            'poids': POIDS_FORME_MEME_DEPART,
            'top3': [horse['numero'] for horse in candidate[:3]],
            'partants_avec_forme_meme_depart': sum('forme_geny_meme_depart' in horse for horse in ranking),
        }
    if sufficient and complete_list and len(ranking) == len(eligible) and not reuse_previous:
        candidat = candidat_classement([(h['numero'], h['score_direct']) for h in ranking], historiques)
        if candidat:
            doc['candidat_geny'] = candidat
    doc['couverture_sources'] = {
        'pmu_musique':sum(h.get('musique_exploitable',0)>0 for h in ranking),
        'geny_historique':sum(h.get('historique_exploitable',0)>0 for h in ranking),
        'pmu_seul':sum(h.get('source_forme')=='PMU_MUSIQUE_SEULE' for h in ranking),
        'sans_score':max(0,len(eligible)-len(ranking)),
        'effectif_declare_confirme':complete_list,
    }
    if not sufficient and not old and not known_np and not any(signal['statut'] for signal in signaux.values()):
        return 'DONNEES_INSUFFISANTES'
    captured = clock() if clock else now
    if captured >= depart:
        return 'APRES_DEPART'
    doc['calcul_utc'] = captured.isoformat()
    if not reuse_previous:
        for signal in signaux.values():
            signal['calcul_utc'] = doc['calcul_utc']
    doc['premier_calcul_utc'] = old.get('premier_calcul_utc', doc['calcul_utc'])
    if old:
        version = datetime.fromisoformat(old['calcul_utc']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        archive = Path(cache)/'pronostics'/'versions'/f"{course['date']}_{course['code']}_direct_{version}.json"
        if not archive.exists():
            save(archive, old)
    save(Path(str(base)+'_direct.json'), doc)
    return 'CALCULE_'+doc['statut'] if sufficient else 'DONNEES_INSUFFISANTES'
