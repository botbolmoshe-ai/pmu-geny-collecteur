"""File durable par cheval : collecte, checkpoint distant, Sheets, suivant.

La complétude décrit une capture datée, jamais une carrière définitivement finie.
Les mises à jour n'écrivent aucun fichier de pronostic, résultat ou entraînement.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .cadence_geny import CadenceGeny, INTERVALLE_REPRISE, REFUS, TIMEOUT_COLLECTE
from .controle_historique import classifier
from .echeances_production import creneau_nocturne as nuit_collecte
from .liaison_chevaux_v22 import nom_geny_concordant, nom_normalise

UTC = timezone.utc
QUEUE = Path('collecte_incrementale/etat.json')


def lire(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {} if default is None else default
    # Un état corrompu doit arrêter le job, jamais réinitialiser la file.


def ecrire(path, doc):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def instant(value):
    try:
        date = datetime.fromisoformat(value)
        return date.astimezone(UTC) if date.tzinfo else None
    except (ValueError, TypeError):
        return None


def capture_valide(cache, ident):
    doc = lire(cache/'historiques'/ident/'historique_geny.json')
    return doc if doc and classifier(doc)[0] == 'COMPLET' else None


def actualisation_requise(horse, now, ttl_heures=24):
    complete = instant(horse.get('historique_complet_au_utc'))
    if not complete or complete > now:
        return 'HISTORIQUE_ABSENT_OU_NON_DATE'
    race = instant(horse.get('derniere_course_officielle_utc'))
    if race and horse.get('derniere_performance_date', '') < race.date().isoformat():
        return 'PUBLICATION_GENY_EN_ATTENTE'
    if race and race > complete:
        return 'NOUVELLE_COURSE_OFFICIELLE'
    if horse.get('ferrures_manquantes',0):
        return 'FERRURES_HISTORIQUES_A_COMPLETER'
    if horse.get('verification_periodique', True) and now - complete >= timedelta(hours=ttl_heures):
        return 'VERIFICATION_PERIODIQUE'
    return ''


def priorite_engagement(horse,now,*,manquant):
    engagement=str(horse.get('engagement_prioritaire') or horse.get('engagement',''))
    day=engagement[:10] if re.fullmatch(r'\d{4}-\d{2}-\d{2}_R\d+C\d+',engagement) else ''
    future=bool(day and day>=now.astimezone(ZoneInfo('Europe/Paris')).date().isoformat())
    if nuit_collecte(now):
        # Apres 21 h, J+1 passe avant les courses du jour deja disputees.
        tomorrow=(now.astimezone(ZoneInfo('Europe/Paris')).date()+timedelta(days=1)).isoformat()
        if manquant and day==tomorrow:return 0
        if manquant and future:return 1
        if manquant and day:return 2
        if future:return 3
        return 4
    return 0 if future else 1


def course_geny_connue(cache,engagement):
    """Rapprocher un engagement à partir des seules preuves déjà sauvegardées."""
    cache=Path(cache)
    match=re.fullmatch(r'(\d{4}-\d{2}-\d{2})_R(\d+)C(\d+)',engagement)
    if not match:return ''
    day=match[1];code='R'+match[2]+'C'+match[3]
    course=lire(cache/'orchestration'/f'{day}.json').get('courses',{}).get(code,{})
    cid=lire(cache/'orchestration/correspondances_geny.json').get(engagement) or course.get('identifiant_geny') or ''
    mapping=course.get('rapprochement_geny',{})
    if not cid and mapping.get('statut')=='CORRESPONDANCE_CONFIRMEE' and mapping.get('geny_id'):
        cid='GENY-'+str(mapping['geny_id'])
    if not cid:
        index=lire(cache/'sources_geny'/f'index_{day}.json')
        if index.get('statut')=='OK':
            from .rapprochement_v20_6 import rapprocher
            decision=rapprocher({**course,'date':day,'num_reunion':int(match[2]),
                                 'num_course':int(match[3])},index.get('courses',[]))
            if decision.get('statut')=='CORRESPONDANCE_CONFIRMEE':
                cid='GENY-'+str(decision['geny_id'])
    return cid if re.fullmatch(r'GENY-\d+',str(cid)) else ''


def alimenter(cache, now, *, sauvegarder=True, engagements=None, associations=None):
    """PMU est la liste de référence ; les manifests ne servent qu'à l'identité Geny."""
    cache = Path(cache)
    state = lire(cache/QUEUE, {'version': 1, 'chevaux': {}})
    if state.get('version') != 1 or not isinstance(state.get('chevaux'), dict):
        raise ValueError('FILE_INCREMENTALE_INCOMPATIBLE')
    from collections import Counter
    from .identites_chevaux import IndexGeny, TentativesGeny, source_identifiant
    index = IndexGeny(cache)
    tentatives = TentativesGeny(cache, now)
    for path in sorted((cache/'partants_actuels').glob('????-??-??_R*C*.json')):
        code = path.stem
        day = datetime.fromisoformat(code[:10]).date()
        # Reprise du passé récent + engagements du jour et du lendemain.
        today = now.astimezone(ZoneInfo('Europe/Paris')).date()
        if engagements is not None:
            if code not in engagements:
                continue
        elif not today-timedelta(days=7) <= day <= today+timedelta(days=1):
            continue
        participants = lire(path).get('chevaux', {})
        counts = Counter(nom_normalise(h.get('nom')) for h in participants.values())
        date, rncn = code.split('_')
        course = lire(cache/'orchestration'/f'{date}.json').get('courses', {}).get(rncn, {})
        cid = course_geny_connue(cache,code)
        manifest = lire(cache/'manifestes'/f'{cid}.json') if cid else {}
        blocks = manifest.get('courses') or []
        by_number = {str(h['numero']): h for h in blocks[0].get('partants', [])} if len(blocks) == 1 else {}
        official = lire(cache/'arrivees'/f'{code}.json')
        departure = instant(course.get('depart'))
        for number, participant in participants.items():
            name = participant.get('nom', '')
            if not name or participant.get('statut_np') == 'NON_PARTANT':
                continue
            context_key = code+'_'+str(number)
            mapped = by_number.get(str(number), {})
            if nom_normalise(mapped.get('nom')) != nom_normalise(name):
                mapped = {}
            count = counts[nom_normalise(name)]
            age = str(participant.get('age_ans', ''))
            year = day.year - int(age) if age.isdigit() else None
            pmu_id = participant.get('id_pmu')
            link, method = index.resoudre(name, cid, number, nom_repris=count > 1, annee=year, id_pmu=pmu_id)
            ident = link.get('id', '')
            if not ident and method != 'NOM_AMBIGU' and count == 1:
                # Les anciens manifestes de la course peuvent manquer d'URL.
                ident = str(mapped.get('id') or '')
            key = ident or context_key
            if associations is not None:
                associations[context_key] = key
            horse = state['chevaux'].setdefault(key, {'nom': name, 'sync': 'SANS_MODIFICATION'})
            if ident and context_key in state['chevaux'] and key != context_key:
                old = state['chevaux'].pop(context_key)
                for field in ('prochain_essai_utc', 'prochaine_sync_utc'):
                    if field == 'prochain_essai_utc' and old.get('recherche_identite_geny') and link:
                        continue
                    deadline = instant(old.get(field))
                    current = instant(horse.get(field))
                    if deadline and (current is None or deadline > current):
                        horse[field] = old[field]
            horse.update(nom=name, numero=number, engagement=code, vu_utc=now.isoformat())
            if pmu_id:
                horse['id_pmu'] = pmu_id
            horse['verification_periodique'] = not bool(official.get('arrivee'))
            if re.fullmatch(r'GENY-\d+', str(cid)):
                horse['course_url'] = 'https://www.geny.com/course/'+cid[5:]+'/partants-pronostics'
            if not horse.get('geny') and horse.get('course_url'):
                from .liens_geny_course import pour_cheval
                link=pour_cheval(cache,code,number,name,now,horse['course_url'])
                if link:horse['geny']=link
            if ident:
                horse['id'] = ident
                doc = capture_valide(cache, ident)
                # Date de la capture source, jamais date de migration ou mtime du fichier.
                if doc:
                    horse['historique_complet_au_utc'] = doc.get('extrait_utc')
                    horse['derniere_performance_date'] = max((r.get('date', '') for r in doc['performances']), default='')
                    horse['nombre_performances'] = len(doc['performances'])
                    from .ferrures_geny import manquantes
                    horse['ferrures_manquantes']=manquantes(doc)
                    horse['collecte'] = 'COMPLET'
                else:
                    horse.pop('historique_complet_au_utc', None)
                    horse['collecte'] = 'A_REPRENDRE'
                if link:
                    horse['geny'] = link
                elif source_identifiant(ident, mapped.get('url_geny')) == 'geny':
                    horse['geny'] = {'id': ident, 'nom': name, 'url_geny': mapped['url_geny']}
                elif doc and doc.get('source_url'):
                    horse['geny'] = {'id': ident, 'nom': name, 'url_geny': doc['source_url']}
            if official.get('arrivee') and departure:
                previous = instant(horse.get('derniere_course_officielle_utc'))
                if not previous or departure > previous:
                    horse['derniere_course_officielle_utc'] = departure.isoformat()
            horse['rapprochement_geny'] = method
            horse['annee_naissance_pmu'] = year
            horse['recherche_geny_par_nom'] = bool(not horse.get('id') and not horse.get('geny'))
            if horse['recherche_geny_par_nom']:
                tentative = tentatives.retrouver(code, number, name, pmu_id)
                retry = instant(tentative.get('reprise_utc'))
                if retry and retry > (instant(horse.get('prochain_essai_utc')) or now):
                    horse['prochain_essai_utc'] = retry.isoformat()
            elif ident and link:
                horse.pop('recherche_identite_geny', None)
            horse['motif_actualisation'] = actualisation_requise(horse, now)
            if horse.get('collecte') == 'EN_COURS':
                horse['collecte'] = 'A_REPRENDRE'
    if sauvegarder:ecrire(cache/QUEUE, state)
    return state


def materialiser_manifestes(cache, state):
    """Reconstruire hors réseau les manifests une fois toutes les identités établies.

    Les non-partants déjà connus sont conservés ; aucun identifiant n'est inventé.
    Un manifeste incomplet n'est jamais publié.
    """
    correspondences = lire(cache/'orchestration/correspondances_geny.json')
    journal = lire(cache/'etat_persistant.json', {'chevaux': {}}).get('chevaux', {})
    known = {}
    for ident, meta in journal.items():
        known.setdefault(nom_normalise(meta.get('nom')), []).append(str(ident))
    for engagement, cid in correspondences.items():
        if not re.fullmatch(r'GENY-\d+', str(cid)):
            continue
        target = cache/'manifestes'/f'{cid}.json'
        if target.exists():
            continue
        participants = lire(cache/'partants_actuels'/f'{engagement}.json').get('chevaux', {})
        horses = []
        for number, participant in participants.items():
            name = participant.get('nom', '')
            ids = known.get(nom_normalise(name), [])
            if len(ids) != 1:
                break
            ident = ids[0]
            doc = capture_valide(cache, ident)
            if not doc or not doc.get('source_url'):
                break
            horses.append({'id': ident, 'nom': name, 'numero': int(number),
                           'url_geny': doc['source_url']})
        if participants and len(horses) == len(participants):
            ecrire(target, {'courses': [{'course_id': cid,
                'source_course_geny': 'https://www.geny.com/course/'+cid[5:]+'/partants-pronostics',
                'nombre_partants_attendu': len(horses), 'partants': horses}]})


def prochaine_tache(state, now, attempts):
    # Les synchronisations échouées sont prioritaires et ne recollectent pas Geny.
    for key, h in state['chevaux'].items():
        if h.get('sync') == 'A_FAIRE' and attempts.get(('SYNC', key), 0) < 1:
            retry = instant(h.get('prochaine_sync_utc'))
            if not retry or now >= retry:
                return key, 'SYNC'
    cooldown = instant(state.get('prochain_acces_geny_utc'))
    if cooldown and now < cooldown:
        return None, 'COOLDOWN'
    candidates = []
    for key, h in state['chevaux'].items():
        if not h.get('motif_actualisation') or h.get('sync') == 'A_FAIRE':
            continue
        if state.get('politique_collecte')=='PROCHAINS_DEPARTS_SEULEMENT':
            depart=instant(h.get('depart_a_venir_utc'))
            if not depart or depart<=now or not h.get('preparation_pmu_ok'):continue
        # Uniquement chevaux revus dans les entrées de ce passage, pas toute la carrière.
        if h.get('vu_utc') != state.get('passage_utc'):
            continue
        retry = instant(h.get('prochain_essai_utc'))
        if attempts.get(('COLLECTE', key), 0) >= 1 or retry and now < retry:
            continue
        if not (h.get('geny') or h.get('course_url') or h.get('recherche_geny_par_nom')):
            h['collecte'] = 'LIEN_GENY_A_RESOUDRE'
            continue
        # La nuit, combler les carrières absentes avant les actualisations.
        priority=priorite_engagement(h,now,manquant=h.get('motif_actualisation')=='HISTORIQUE_ABSENT_OU_NON_DATE')
        enrichment=h.get('motif_actualisation')=='FERRURES_HISTORIQUES_A_COMPLETER'
        missing=h.get('motif_actualisation')=='HISTORIQUE_ABSENT_OU_NON_DATE'
        order=((h.get('premier_depart_reunion_utc') or h['depart_a_venir_utc'],
                enrichment, not missing, h['depart_a_venir_utc'], key) if state.get('politique_collecte')=='PROCHAINS_DEPARTS_SEULEMENT'
               else (enrichment,priority,h['engagement'],key))
        candidates.append((order,key))
    if candidates:
        return min(candidates)[1], 'COLLECTE'
    return None, 'TERMINE'


def executer_enfant(horse, out, *, profil=None):
    out.mkdir(parents=True, exist_ok=True)
    task = out/'tache.json'
    ecrire(task, horse)
    command = [sys.executable, '-m', 'pmu_geny.historique_individuel',
               '--tache', str(task), '--sortie', str(out)]
    if profil:
        command += ['--profil', profil]
    subprocess.run(command, check=True, timeout=TIMEOUT_COLLECTE)
    return lire(out/'resultat.json')


def memoriser_resolution(horse, report, out, *, cache=None):
    """Une résolution de lien n'est jamais une validation de carrière."""
    if cache is not None:
        from .liens_geny_course import memoriser
        memoriser(cache,horse,out)
    from .identites_chevaux import preuve_resolution_valide, source_identifiant
    proof=lire(out/'resolution_geny.json')
    geny=report.get('geny') or proof.get('geny') or {}
    ident=str(geny.get('id',''))
    if (source_identifiant(ident,geny.get('url_geny'))!='geny'
            or not re.fullmatch(r'\d{4,15}',ident)
            or not nom_geny_concordant(horse.get('nom'), geny)
            or horse.get('id') and str(horse['id'])!=ident):return
    if not report.get('geny') and (proof.get('engagement')!=horse.get('engagement')
            or proof.get('numero')!=str(horse.get('numero',''))):return
    horse['geny']=geny
    if (cache is not None and preuve_resolution_valide(proof) and proof.get('geny') == geny
            and proof.get('engagement') == horse.get('engagement')
            and proof.get('numero') == str(horse.get('numero', ''))):
        identity_key = nom_normalise(geny['nom'])
        if proof.get('id_pmu'):
            identity_key += ':' + str(proof['id_pmu'])
        digest = hashlib.sha256(identity_key.encode()).hexdigest()[:16]
        path = cache/'sources_geny/identites'/f'{ident}-{digest}.json'
        stored = lire(path)
        if not stored or len(geny.get('homonymes', [])) > len(stored['geny'].get('homonymes', [])):
            ecrire(path, proof)
        horse.update(id=ident, preuve_identite=proof['preuve'])
        if geny.get('homonymes'):
            horse['rapprochement_geny'] = 'NOM_AMBIGU'


def accepter(cache, horse, report, *, origine='COLLECTE_INCREMENTALE_PRODUCTION'):
    """Ne jamais remplacer un historique complet par un partiel ou une régression."""
    if not report.get('complet') or not report.get('identite_verifiee'):
        raise ValueError('HISTORIQUE_NON_VALIDE')
    ident = str(report['geny']['id'])
    if not re.fullmatch(r'\d{4,15}', ident) or horse.get('id') and ident != horse['id']:
        raise ValueError('IDENTIFIANT_NON_CONCORDANT')
    source = Path(report['dossier'])
    doc = lire(source/'historique_geny.json')
    if classifier(doc)[0] != 'COMPLET' or not instant(doc.get('extrait_utc')):
        raise ValueError('CONTENU_OU_DATE_NON_VALIDE')
    if instant(doc['extrait_utc']) > datetime.now(UTC):
        raise ValueError('CAPTURE_DANS_LE_FUTUR')
    doc.update(statut='COMPLET', complet=True, champs_detail_valides=True)
    previous = capture_valide(cache, ident)
    if previous:
        # Les mêmes dates peuvent contenir plusieurs courses : comparer les lignes complètes.
        from .structure_geny import FIELDS

        def indexed(d):
            result={}
            for row in d['performances']:
                clean={k:v for k,v in row.items() if k not in ('ferrure','ferrure_source','ferrure_qualification','depart_trot', *FIELDS)}
                clean['texte_source']=re.sub(r'\s*\|\s*\d{1,2}:\d{2}\s*\|\s*/\s*\|\s*\d{1,2}:\d{2}\s*$',
                                             '',str(clean.get('texte_source','')))
                result.setdefault(json.dumps(clean, sort_keys=True, ensure_ascii=False),[]).append(row)
            return result
        before,after=indexed(previous),indexed(doc)
        if not set(before).issubset(after):
            raise ValueError('REGRESSION_HISTORIQUE_A_CONTROLER')
        for key,rows in before.items():
            for old in rows:
                ferrure=old.get('ferrure')
                for new in after[key]:
                    if old.get('depart_trot') and not new.get('depart_trot'):
                        new['depart_trot'] = old['depart_trot']
                    if not ferrure:continue
                    if ((new.get('ferrure') and new['ferrure']!=ferrure)
                            or (new.get('ferrure_qualification') == 'CONFLIT'
                                and old.get('ferrure_qualification') != 'CONFLIT')):
                        raise ValueError('REGRESSION_FERRURE_A_CONTROLER')
                    if not new.get('ferrure'):
                        new['ferrure']=ferrure
                        for champ in ('ferrure_source', 'ferrure_qualification'):
                            if old.get(champ):
                                new[champ] = old[champ]
        oldtime = instant(previous.get('extrait_utc'))
        if oldtime and instant(doc['extrait_utc']) < oldtime:
            raise ValueError('CAPTURE_PLUS_ANCIENNE')
        archive = cache/'historiques_versions'/ident/(hashlib.sha256(json.dumps(previous, sort_keys=True).encode()).hexdigest()+'.json')
        ecrire(archive, previous)
    destination = cache/'historiques'/ident
    from .ferrures_geny import couverture
    couverture(doc)
    ecrire(destination/'historique_geny.json', doc)
    # Regénérer le CSV depuis le JSON validé pour éviter un fichier désynchronisé.
    columns = ['date', 'hippodrome', 'discipline', 'distance_m', 'classement', 'chrono', 'texte_source','ferrure']
    with (destination/'historique_geny.csv').open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter=';', extrasaction='ignore')
        writer.writeheader()
        writer.writerows(doc['performances'])
    stamp = doc['extrait_utc']
    horse.update(id=ident, geny=report['geny'], collecte='COMPLET', sync='A_FAIRE',
                 historique_complet_au_utc=stamp, derniere_verification_utc=stamp,
                 prochaine_verification_utc=(instant(stamp)+timedelta(hours=24)).isoformat(),
                 nombre_performances=len(doc['performances']), motif_actualisation='', erreur='')
    # Une collecte validée annule le délai d'échec précédent. Une nouvelle
    # lacune de ferrure ou publication peut ensuite poser son propre délai.
    horse.pop('prochain_essai_utc',None)
    horse['ferrures_manquantes']=doc['ferrures_manquantes']
    if doc['ferrures_manquantes']:
        horse['motif_actualisation']='FERRURES_HISTORIQUES_A_COMPLETER'
        horse['prochain_essai_utc']=(datetime.now(UTC)+timedelta(hours=6)).isoformat()
    horse['derniere_performance_date'] = max((r.get('date', '') for r in doc['performances']), default='')
    journal = lire(cache/'etat_persistant.json', {'version': 1, 'chevaux': {}})
    journal.setdefault('chevaux', {})[ident] = {**journal.get('chevaux', {}).get(ident, {}),
        'id': ident, 'nom': report['geny'].get('nom') or horse['nom'], 'statut': 'COMPLET', 'motifs': [],
        'nombre_extrait': doc['nombre_extrait'], 'nombre_annonce_geny': doc['nombre_annonce_geny'],
        'maj_utc': stamp, 'historique_complet_au_utc': stamp,
        'prochaine_verification_utc': horse['prochaine_verification_utc'],
        'origine': origine}
    ecrire(cache/'etat_persistant.json', journal)


def suspendre_geny(cache, state, stamp, code, reprise_serveur=None):
    from .echeances_production import pause_geny_active
    deadline = stamp + timedelta(minutes=30)
    current = pause_geny_active(cache, stamp)
    serveur = instant(reprise_serveur)
    reprise = max(deadline, current or deadline, serveur or deadline)
    state['prochain_acces_geny_utc'] = reprise.isoformat()
    journal = lire(cache/'etat_persistant.json', {'version': 1, 'chevaux': {}})
    journal['dernier_blocage_geny'] = {'utc': stamp.isoformat(), 'code': code}
    if serveur:
        journal['dernier_blocage_geny']['reprise_au_plus_tot_utc'] = reprise.isoformat()
    ecrire(cache/'etat_persistant.json', journal)


def checkpoint_distant(cache, *, queue=QUEUE):
    """Publier seulement les fichiers de collecte sous le verrou partagé des workflows."""
    root = Path(__file__).resolve().parents[1]
    def git(*args, cwd=root):
        return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()
    git('fetch', 'origin', 'pmu-data')
    with tempfile.TemporaryDirectory(prefix='pmu-checkpoint-') as tmp:
        target = Path(tmp)/'data'
        git('worktree', 'add', '--detach', str(target), 'origin/pmu-data')
        try:
            ecrire(target/queue, lire(cache/queue))
            if queue!=QUEUE:
                shutil.copytree(cache/queue.parent,target/queue.parent,dirs_exist_ok=True)
            recensements = QUEUE.parent/'recensements'
            if queue == QUEUE and (cache/recensements).is_dir():
                shutil.copytree(cache/recensements, target/recensements, dirs_exist_ok=True)
            for name in ('historiques', 'historiques_partiels', 'historiques_versions', 'manifestes','sources_geny/liens','sources_geny/identites'):
                if (cache/name).exists():
                    shutil.copytree(cache/name, target/name, dirs_exist_ok=True)
            shutil.copy2(cache/'etat_persistant.json', target/'etat_persistant.json')
            git('add', str(queue.parent), 'historiques', 'etat_persistant.json', cwd=target)
            if (target/'manifestes').exists():
                git('add', 'manifestes', cwd=target)
            if (target/'historiques_versions').exists():
                git('add', 'historiques_versions', cwd=target)
            if (target/'historiques_partiels').exists():
                git('add', 'historiques_partiels', cwd=target)
            for directory in ('sources_geny/liens', 'sources_geny/identites'):
                if (target/directory).exists():
                    git('add', directory, cwd=target)
            changed = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=target).returncode
            if changed:
                git('commit', '-m', 'PMU : checkpoint collecte incrementale', cwd=target)
                # Pas de force push : un conflit arrête le passage avant le cheval suivant.
                git('push', 'origin', 'HEAD:refs/heads/pmu-data', cwd=target)
        finally:
            git('worktree', 'remove', '--force', str(target))


def run(cache, *, max_minutes=15, max_chevaux=None, publier=False,
        collect=None, checkpoint=None, sync=None, mode='production', stop_requested=None,
        prochains_depart=False, creneau_reserve=None, nocturne=False, perimetre=None, archive_recensement=None,
        cadence_geny=None):
    cache = Path(cache)
    now = datetime.now(UTC)
    reprise=None
    if mode=='rattrapage':
        from . import rattrapage_historiques as reprise
    elif mode!='production':
        raise ValueError('MODE_COLLECTE_INCONNU')
    queue=reprise.QUEUE if reprise else QUEUE
    associations = {}
    rejeu = {}
    if perimetre:
        from . import recensement_historiques as recensement
        chemin_suivi, suivi = recensement.ouvrir(cache, *perimetre)
        engagements = {f"{suivi['date_courses']}_{course}" for course in suivi['courses']}
        state = alimenter(cache, now, engagements=engagements, associations=associations)
        for contexte, ligne in suivi['chevaux'].items():
            ident = ligne.get('id_geny')
            cheval = state['chevaux'].get(ident)
            if cheval and nom_normalise(cheval.get('nom')) == nom_normalise(ligne['nom']):
                associations[contexte] = ident
        if archive_recensement:
            rejeu = recensement.captures_a_rejouer(archive_recensement, chemin_suivi, suivi, state, associations)
    else:
        state = reprise.preparer(cache,now) if reprise else alimenter(cache, now)
    if prochains_depart and not reprise:
        from .preparation_prochaines import appliquer
        appliquer(cache,state,now,nocturne=nocturne)
    elif not reprise:state.pop('politique_collecte',None)
    state['passage_utc'] = now.isoformat()
    state['priorite_collecte'] = ('STOCK_NOCTURNE' if reprise else 'DEPARTS_DU_JOUR_NOCTURNE') if nocturne else (
        'PARTANTS_SANS_HISTORIQUE_NUIT' if nuit_collecte(now) else 'ENGAGEMENTS_JOUR')
    state.pop('motif_fin_passage',None)
    state.pop('creneau_reserve', None)
    from .echeances_production import pause_geny_active
    states = {'back' if reprise else 'prod': state}
    pause = pause_geny_active(cache, now, **states)
    if pause:
        state['prochain_acces_geny_utc'] = pause.isoformat()
    else:
        state.pop('prochain_acces_geny_utc', None)
    attempts, count, accepted, partials = {}, 0, 0, 0
    sheets_engine=None
    captures_completes = set()
    sync_confirmees = set()
    ajouts_sheets_confirmes = 0
    refus_geny = {'403': 0, '429': 0}
    refus_http = {'403': 0, '429': 0}
    from collections import Counter
    requetes_par_ressource = Counter()
    hits_cache_http = 0
    requetes_geny, attente_geny, duree_geny = 0, 0.0, 0.0
    if cadence_geny is None:
        cadence_geny = collect is None
    profil = None
    executor_reel = collect is None
    if executor_reel:
        collect = executer_enfant
        from .historique_individuel import RECHERCHE_NON_AUTORISEE, recherche_bloquee_avant_navigation
    cadence = CadenceGeny(cache) if cadence_geny else None
    deadline = None if max_minutes is None else time.monotonic()+max_minutes*60
    def save(*, distant=True):
        state['maj_utc'] = datetime.now(UTC).isoformat()
        heures = max(1, (instant(state['maj_utc']) - now).total_seconds()) / 3600
        state['collecte_cycle'] = {
            'debut_utc': state['passage_utc'], 'controle_utc': state['maj_utc'], 'source': 'Geny',
            'carrieres_completes_distinctes': len(captures_completes),
            'chevaux_confirmes_sheets': len(sync_confirmees),
            'performances_ajoutees_et_confirmees_sheets': ajouts_sheets_confirmes,
            'requetes_http_geny': requetes_geny, 'requetes_geny_par_ressource': dict(requetes_par_ressource),
            'ressources_geny_servies_du_cache_http': hits_cache_http,
            'attente_inter_chevaux_secondes': round(attente_geny, 2),
            'intervalle_inter_chevaux_secondes': cadence.intervalle if cadence else None,
            'duree_acces_geny_secondes': round(duree_geny, 2),
            'refus_sans_validation': cadence.etat.get('incidents_sans_validation', 0) if cadence else 0,
            'carrieres_validees_par_heure_cycle': round(len(captures_completes) / heures, 2),
            'carrieres_publiees_par_heure_cycle': round(len(sync_confirmees) / heures, 2),
            'refus_geny': refus_geny, 'reponses_http_refusees_geny': refus_http, 'prochain_acces_geny_utc': state.get('prochain_acces_geny_utc'),
        }
        state.setdefault('bilan',{}).update(tentatives_collecte=count,
            captures_validees=accepted,captures_partielles=partials,collectes_rejetees=count-accepted-partials)
        if reprise:
            previous = {field: state['bilan'].get(field) for field in (
                'contextes_distincts_sans_identifiant', 'noms_distincts_sans_identifiant',
                'identifiants_sans_carriere_complete')}
            current = reprise.bilan(state)
            if any(current[field] != value for field, value in previous.items()):
                state['sync_kpi'] = 'A_REPRENDRE'
        else:materialiser_manifestes(cache, state)
        ecrire(cache/queue, state)
        if perimetre:
            suivi['controle_utc'] = state['maj_utc']
            suivi['bilan'] = recensement.bilan(suivi)
            suivi['motif_fin_passage'] = state.get('motif_fin_passage')
            suivi['prochain_acces_geny_utc'] = state.get('prochain_acces_geny_utc')
            ecrire(cache/chemin_suivi, suivi)
        if reprise:ecrire(cache/queue.parent/'bilan.json',reprise.rapport(state, cache=cache))
        if not distant:
            return
        if checkpoint:
            checkpoint(cache)
        elif publier:
            if reprise:checkpoint_distant(cache,queue=queue)
            else:checkpoint_distant(cache)
    save()
    syncs = set()
    while deadline is None or time.monotonic() < deadline:
        reason=stop_requested() if stop_requested else None
        if reason:
            state['motif_fin_passage']=str(reason)
            break
        choisir=reprise.prochaine_tache if reprise else prochaine_tache
        capture_archivee = None
        if rejeu:
            key = next(iter(rejeu))
            capture_archivee = rejeu.pop(key)
            action = 'COLLECTE'
        elif archive_recensement:
            state['motif_fin_passage'] = 'REVALIDATION_ARCHIVES_TERMINEE'
            break
        elif perimetre:
            pause = pause_geny_active(cache, datetime.now(UTC))
            key, action = recensement.tache(suivi, state, associations, pause, syncs)
            if pause:
                state['prochain_acces_geny_utc'] = pause.isoformat()
        else:
            key, action = choisir(state, datetime.now(UTC), attempts)
        if key is None:
            state['motif_fin_passage']=action
            break
        if action == 'COLLECTE' and max_chevaux is not None and count >= max_chevaux:
            state['motif_fin_passage']='MAX_CHEVAUX_ATTEINT'
            break
        horse = state['chevaux'][key]
        recherche_bloquee = (action == 'COLLECTE' and executor_reel and not capture_archivee
                             and recherche_bloquee_avant_navigation(horse))
        if action == 'COLLECTE' and cadence and not capture_archivee and not recherche_bloquee:
            delai = cadence.delai(datetime.now(UTC))
            if delai:
                if delai > INTERVALLE_REPRISE or (deadline is not None and time.monotonic() + delai >= deadline):
                    state['motif_fin_passage'] = 'CADENCE_GENY_DIFFEREE'
                    break
                debut_attente = time.monotonic()
                time.sleep(min(delai, 10))
                attente_geny += time.monotonic() - debut_attente
                continue
        attempts[(action, key)] = attempts.get((action, key), 0)+1
        if action == 'COLLECTE':
            statut_initial = 'ECHEC_COLLECTE' if capture_archivee else 'A_EXAMINER'
            lignes = recensement.lignes_associees(suivi, associations, key, statut_initial) if perimetre else ()
            debut_tentative = datetime.now(UTC).isoformat()
            if not horse.get('geny') and horse.get('course_url'):
                from .liens_geny_course import pour_cheval
                link = pour_cheval(cache, horse.get('engagement'), horse.get('numero'),
                                   horse['nom'], datetime.now(UTC), horse['course_url'])
                if link and (not horse.get('id') or str(horse['id']) == link['id']):
                    horse['geny'] = {**link, 'preuve': 'COURSE_GENY_VERIFIEE'}
            if reprise:
                stamp = datetime.now(UTC).isoformat()
                state.update(collecte_tentee_utc=stamp, sync_kpi='A_REPRENDRE')
                if creneau_reserve and creneau_reserve():
                    state.update(dernier_creneau_reserve_utc=stamp, creneau_reserve=True)
            if reprise:
                attempts[reprise.cle_travail_geny(horse)] = 1
            requete_reelle = not capture_archivee and not recherche_bloquee
            if cadence and requete_reelle:
                cadence.reserver(datetime.now(UTC))
                save()  # Réserver avant de lancer le processus réseau.
            horse['collecte'] = 'EN_COURS'
            # Le checkpoint précédent permet de reprendre une capture interrompue.
            save(distant=bool(reprise) and not cadence)
            # Une clé de contexte peut contenir « : », interdit dans un artefact Actions.
            out = Path('resultats/incremental') / key.replace(':', '_') / str(time.time_ns())
            report, mesure = {}, {}
            refus, valide, fin_requete = None, False, None
            debut_requete = time.monotonic()
            try:
                try:
                    if recherche_bloquee:
                        report = {'statut': RECHERCHE_NON_AUTORISEE}
                    elif capture_archivee:
                        report = capture_archivee
                    elif executor_reel:
                        if profil is None:
                            profil = tempfile.TemporaryDirectory(prefix='pmu-geny-session-')
                        report = collect(horse, out, profil=profil.name)
                    else:
                        report = collect(horse, out)
                finally:
                    fin_requete = datetime.now(UTC)
                    if requete_reelle:
                        duree_geny += time.monotonic() - debut_requete
                        mesure = lire(out / 'http_geny.json')
                        cache_http = mesure.get('cache_http_par_ressource', {})
                        hits = sum(cache_http.values())
                        hits_cache_http += hits
                        requetes_geny += max(0, mesure.get('requetes', 0) - hits)
                        requetes_par_ressource.update(mesure.get('par_ressource', {}))
                        requetes_par_ressource.subtract(cache_http)
                        for code, nombre in mesure.get('reponses_refusees', {}).items():
                            refus_http[code] += nombre
                    refus = (mesure.get('refus') if requete_reelle else None) or REFUS.get(report.get('statut'))
                if refus and report.get('statut') not in REFUS:
                    report['statut'] = next(statut for statut, code in REFUS.items() if code == refus)
                if refus:
                    raise PermissionError(report['statut'])
                memoriser_resolution(horse,report,out,cache=cache)
                if reprise and horse.get('preuve_identite'):
                    reprise.propager_identite(state,horse)
                if report.get('complet'):
                    if reprise:
                        last = reprise.derniere_acquisition_validee(cache, state)
                        accepter(cache,horse,report,origine='RATTRAPAGE_GLOBAL')
                        stamp = horse['historique_complet_au_utc']
                        state['derniere_acquisition_validee_utc'] = max(
                            (value for value in (last, stamp) if value), key=instant)
                    else:accepter(cache, horse, report)
                    accepted+=1
                    captures_completes.add(str(horse['id']))
                    valide = True
                else:
                    from .historiques_partiels import conserver
                    if not conserver(cache,horse,report):raise ValueError('HISTORIQUE_NON_VALIDE')
                    partials+=1
                ident = horse['id']
                if not reprise and key != ident:
                    state['chevaux'][ident] = horse
                    del state['chevaux'][key]
                    if perimetre:
                        for contexte, assoc in associations.items():
                            if assoc == key:
                                associations[contexte] = ident
                    key = ident
                    attempts[('COLLECTE',key)]=1
                # Date de vérification != couverture : Geny peut publier la nouvelle course plus tard.
                race = instant(horse.get('derniere_course_officielle_utc')) if not reprise else None
                if report.get('complet') and race and horse.get('derniere_performance_date', '') < race.date().isoformat():
                    doc = capture_valide(cache, ident)
                    horse['derniere_performance_date'] = max((r.get('date', '') for r in doc['performances']), default='')
                    if horse['derniere_performance_date'] < race.date().isoformat():
                        horse['motif_actualisation'] = 'PUBLICATION_GENY_EN_ATTENTE'
                        horse['prochain_essai_utc'] = (datetime.now(UTC)+timedelta(hours=6)).isoformat()
            except Exception as exc:
                if isinstance(exc, subprocess.TimeoutExpired) and profil:
                    profil.cleanup()
                    profil = None
                horse.update(collecte='A_REPRENDRE', erreur=f'{type(exc).__name__}: {exc}',
                             prochain_essai_utc=(datetime.now(UTC)+timedelta(hours=168 if
                                 report.get('statut') == 'RECHERCHE_GENY_NON_AUTORISEE' else 6)).isoformat())
                horse['dernier_echec_collecte']={'utc':datetime.now(UTC).isoformat(),
                    'statut':report.get('statut') or type(exc).__name__,
                    'motifs':report.get('motifs',[]),'erreur':str(exc),
                    'identite_verifiee':report.get('identite_verifiee'),
                    'diagnostic':str(out/'resultat.json')}
                if refus:
                    refus_geny[refus] += 1
                    suspendre_geny(cache, state, fin_requete, refus, mesure.get('reprise_au_plus_tot_utc') if requete_reelle else None)
                # Le sous-processus peut s'arrêter après la preuve et avant son bilan.
                if not report or refus:
                    memoriser_resolution(horse,report,out,cache=cache)
                    if reprise and horse.get('preuve_identite'):
                        reprise.propager_identite(state,horse)
            finally:
                if requete_reelle or recherche_bloquee:
                    state['sync_kpi'] = 'A_REPRENDRE'
                    from .identites_chevaux import memoriser_tentative
                    memoriser_tentative(horse, report, debut_tentative,
                                        acces=bool(mesure), refus=refus)
                if cadence and requete_reelle:
                    cadence.terminer(fin_requete, valide=valide, refus=bool(refus))
            if reprise:
                attempts[reprise.cle_travail_geny(horse)] = 1
            count += 1
            for ligne in lignes:
                if capture_archivee:
                    ligne['revalidation_utc'] = debut_tentative
                else:
                    ligne['tentative_utc'] = debut_tentative
                ligne['id_geny'] = horse.get('id')
                if refus or horse.get('collecte') == 'A_REPRENDRE':
                    echec = horse['dernier_echec_collecte']
                    ligne.update(statut='REFUS_GENY' if refus else 'ECHEC_COLLECTE',
                                 motif=echec['erreur'], statut_extraction=echec['statut'])
                elif horse.get('sync') == 'A_FAIRE':
                    ligne.update(statut='A_PUBLIER', capture=horse.get('collecte'))
                else:
                    ligne.update(statut='DEJA_PUBLIE', capture=horse.get('collecte'))
            save()  # Publier les données AVANT toute écriture Sheets.
            if horse.get('sync') != 'A_FAIRE':
                continue
        if perimetre:
            syncs.add(key)
        try:
            if sync:
                horse['sync_details'] = sync(horse)
            elif publier:
                from .moteur_sheets import SynchroniseurSheets
                if sheets_engine is None:
                    sheets_engine=SynchroniseurSheets(cache,os.environ['GOOGLE_SHEETS_ID'])
                state['sync_kpi']='A_REPRENDRE'
                if reprise:
                    horse['sync_details']=sheets_engine.synchroniser_cheval(
                        horse,include_kpi=False,include_courses=False)
                else:horse['sync_details']=sheets_engine.synchroniser_cheval(horse,include_kpi=False)
            else:
                raise RuntimeError('SYNCHRONISATION_NON_CONFIGUREE')
            historique = horse.get('sync_details', {}).get('Historique chevaux', {})
            if historique.get('controle', {}).get('statut') == 'VALIDE':
                sync_confirmees.add(str(horse.get('id') or key))
                ajouts_sheets_confirmes += historique.get('lignes_ajoutees', 0)
            horse.update(sync='OK', sync_utc=datetime.now(UTC).isoformat(), erreur='')
            if reprise and horse.get('collecte')=='COMPLET':reprise.valider_sync(state,horse)
            if perimetre:
                for ligne in recensement.lignes_associees(suivi, associations, key, 'A_PUBLIER'):
                    preuve = historique.get('controle', {}).get('statut') == 'VALIDE'
                    ligne.update(statut='PUBLIE' if preuve else 'PUBLICATION_NON_PROUVEE',
                                 publication_utc=horse['sync_utc'] if preuve else None,
                                 performances_ajoutees=historique.get('lignes_ajoutees', 0) if preuve else 0)
        except Exception as exc:
            horse.update(sync='A_FAIRE', erreur=f'{type(exc).__name__}: {exc}',
                         prochaine_sync_utc=(datetime.now(UTC)+timedelta(minutes=10)).isoformat())
            if perimetre:
                for ligne in recensement.lignes_associees(suivi, associations, key, 'A_PUBLIER'):
                    ligne.update(statut='PUBLICATION_A_REPRENDRE', motif=type(exc).__name__)
            from .controle_sync_sheets import BlocageSynchronisation
            from .moteur_sheets import SynchronisationOccupee
            if not perimetre and isinstance(exc,(BlocageSynchronisation,SynchronisationOccupee)):
                save()
                if sheets_engine:sheets_engine.fermer()
                raise  # Incident visible en échec Actions ; ne pas continuer silencieusement.
        save()
    state.setdefault('motif_fin_passage','BUDGET_TEMPS_ATTEINT')
    if prochains_depart and not reprise:
        from .preparation_prochaines import appliquer
        appliquer(cache,state,datetime.now(UTC),nocturne=nocturne)
    state['bilan'] = {'chevaux_suivis': len(state['chevaux']), 'tentatives_collecte': count,
                      'captures_validees':accepted,'captures_partielles':partials,
                      'collectes_rejetees':count-accepted-partials,
                      'synchronisations_en_attente': sum(h.get('sync') == 'A_FAIRE' for h in state['chevaux'].values()),
                      'actualisations_en_attente': sum(bool(h.get('motif_actualisation')) for h in state['chevaux'].values())}
    state['statut'] = ('PARTIEL_REPRENABLE' if state['bilan']['actualisations_en_attente'] or
                       state['bilan']['synchronisations_en_attente'] else 'A_JOUR')
    if reprise:
        state.update(controle_ordonnancement_utc=datetime.now(UTC).isoformat(),
                     motif_ordonnancement=state['motif_fin_passage'])
        reprise.preparer_noms_passes(cache, state, datetime.now(UTC))
        reprise.bilan(state)
        reprise.persister_etat(cache, state)
    if publier and sync is None and (sheets_engine is not None or state.get('sync_kpi')=='A_REPRENDRE'):
        from .moteur_sheets import SynchroniseurSheets
        if sheets_engine is None:sheets_engine=SynchroniseurSheets(cache,os.environ['GOOGLE_SHEETS_ID'])
        try:
            sheets_engine.synchroniser_correspondances()
            state['sync_kpi_details']=sheets_engine.synchroniser_kpi()
            state['sync_kpi']='OK'
            state['sync_kpi_utc']=datetime.now(UTC).isoformat()
        except Exception:
            state['sync_kpi']='A_REPRENDRE';save()
            raise
        finally:sheets_engine.fermer()
    save()
    return suivi if perimetre else state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', default='cache_pmu')
    parser.add_argument('--max-minutes', type=int, default=15)
    parser.add_argument('--max-chevaux', type=int)
    parser.add_argument('--publier', action='store_true')
    parser.add_argument('--nocturne', action='store_true')
    parser.add_argument('--local', action='store_true', help='Publications sans requête Geny')
    parser.add_argument('--date-courses')
    parser.add_argument('--hippodrome')
    parser.add_argument('--archive-recensement', type=Path)
    args = parser.parse_args()
    if args.archive_recensement and not args.date_courses:
        parser.error('--archive-recensement exige le périmètre du recensement')
    if bool(args.date_courses) != bool(args.hippodrome):
        parser.error('--date-courses et --hippodrome doivent être fournis ensemble')
    if args.max_minutes < 1 or (args.max_chevaux is not None and args.max_chevaux < 1):
        parser.error('Bornes positives requises')
    if args.date_courses and not args.publier:
        from .recensement_historiques import bilan, ouvrir
        _, suivi = ouvrir(Path(args.cache), args.date_courses, args.hippodrome)
        print(json.dumps(bilan(suivi), ensure_ascii=False))
        return
    if not args.publier:
        state = alimenter(Path(args.cache), datetime.now(UTC))
        print(json.dumps({'mode': 'INVENTAIRE_SANS_RESEAU', 'chevaux': len(state['chevaux'])}))
        return
    if not all(os.environ.get(k) for k in ('GOOGLE_SHEETS_ID', 'GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON')):
        raise SystemExit('Secrets Sheets absents : aucune collecte lancée')
    if args.date_courses:
        # Un recensement ne peut pas monopoliser le verrou de production.
        from .echeances_production import besoin_pmu

        sortie_actions = os.getenv('GITHUB_OUTPUT')
        cache = Path(args.cache)
        suivi = run(cache, max_minutes=7, publier=True,
                    stop_requested=lambda: besoin_pmu(cache, datetime.now(UTC)),
                    perimetre=(args.date_courses, args.hippodrome),
                    archive_recensement=args.archive_recensement)
        print('BILAN_RECENSEMENT ' + json.dumps(suivi['bilan'], ensure_ascii=False))
        motif = suivi['motif_fin_passage']
        reprise = None
        if motif == 'COOLDOWN':
            reprise = suivi.get('prochain_acces_geny_utc')
        elif motif in {'BUDGET_TEMPS_ATTEINT', 'ECHEANCE_PMU_PRIORITAIRE', 'CADENCE_GENY_DIFFEREE'}:
            reprise = (datetime.now(UTC) + timedelta(minutes=15)).isoformat()
        if sortie_actions and reprise:
            with open(sortie_actions, 'a') as output:
                output.write(f'reprise_utc={reprise}\n')
        return
    from .rattrapage_historiques import priorite_production
    from .echeances_production import besoin_pmu, motif_pause_collecte_nocturne
    cache = Path(args.cache)
    verifier_echeances = motif_pause_collecte_nocturne if args.nocturne else besoin_pmu
    state = run(cache, max_minutes=args.max_minutes, max_chevaux=0 if args.local else args.max_chevaux, publier=True,
                prochains_depart=True, nocturne=args.nocturne,
                stop_requested=lambda:(verifier_echeances(cache, datetime.now(UTC))
                    or (not nuit_collecte(datetime.now(UTC))
                        and priorite_production({'.github/workflows/pmu-v16.yml'}))))
    print('BILAN_INCREMENTAL '+json.dumps({**state['bilan'],
        'motif_fin_passage':state['motif_fin_passage'],
        'couverture_par_jour':state['preparation_prochaines_courses']['couverture_par_jour'],
        'collecte_cycle': state['collecte_cycle']}))


if __name__ == '__main__':
    main()
