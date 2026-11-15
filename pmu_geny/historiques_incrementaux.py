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

from .controle_historique import classifier
from .liaison_chevaux_v22 import nom_normalise

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


def nuit_collecte(now):
    hour=now.astimezone(ZoneInfo('Europe/Paris')).hour
    return hour>=21 or hour<7


def priorite_engagement(horse,now,*,manquant):
    engagement=str(horse.get('engagement_prioritaire') or horse.get('engagement',''))
    day=engagement[:10] if re.fullmatch(r'\d{4}-\d{2}-\d{2}_R\d+C\d+',engagement) else ''
    future=bool(day and day>=now.astimezone(ZoneInfo('Europe/Paris')).date().isoformat())
    if nuit_collecte(now):
        if manquant and future:return 0
        if manquant and day:return 1
        if future:return 2
        return 3
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


def alimenter(cache, now):
    """PMU est la liste de référence ; les manifests ne servent qu'à l'identité Geny."""
    cache = Path(cache)
    state = lire(cache/QUEUE, {'version': 1, 'chevaux': {}})
    if state.get('version') != 1 or not isinstance(state.get('chevaux'), dict):
        raise ValueError('FILE_INCREMENTALE_INCOMPATIBLE')
    journal = lire(cache/'etat_persistant.json', {'version': 1, 'chevaux': {}})
    known = {}
    for ident, meta in journal.get('chevaux', {}).items():
        name = nom_normalise(meta.get('nom'))
        if name:
            known.setdefault(name, []).append(str(ident))
    for path in sorted((cache/'partants_actuels').glob('????-??-??_R*C*.json')):
        code = path.stem
        day = datetime.fromisoformat(code[:10]).date()
        # Reprise du passé récent + engagements du jour et du lendemain.
        today = now.astimezone(ZoneInfo('Europe/Paris')).date()
        if not today-timedelta(days=7) <= day <= today+timedelta(days=1):
            continue
        participants = lire(path).get('chevaux', {})
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
            ids = known.get(nom_normalise(name), [])
            ident = str(mapped.get('id') or (ids[0] if len(ids) == 1 else ''))
            key = ident or context_key
            horse = state['chevaux'].setdefault(key, {'nom': name, 'sync': 'SANS_MODIFICATION'})
            if ident and context_key in state['chevaux'] and key != context_key:
                del state['chevaux'][context_key]
            horse.update(nom=name, numero=number, engagement=code, vu_utc=now.isoformat())
            horse['verification_periodique'] = not bool(official.get('arrivee'))
            if re.fullmatch(r'GENY-\d+', str(cid)):
                horse['course_url'] = 'https://www.geny.com/course/'+cid[5:]+'/partants-pronostics'
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
                if mapped.get('url_geny'):
                    horse['geny'] = {'id': ident, 'nom': name, 'url_geny': mapped['url_geny']}
                elif doc and doc.get('source_url'):
                    horse['geny'] = {'id': ident, 'nom': name, 'url_geny': doc['source_url']}
            if official.get('arrivee') and departure:
                previous = instant(horse.get('derniere_course_officielle_utc'))
                if not previous or departure > previous:
                    horse['derniere_course_officielle_utc'] = departure.isoformat()
            horse['motif_actualisation'] = actualisation_requise(horse, now)
            if horse.get('collecte') == 'EN_COURS':
                horse['collecte'] = 'A_REPRENDRE'
    ecrire(cache/QUEUE, state)
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
        # Uniquement chevaux revus dans les entrées de ce passage, pas toute la carrière.
        if h.get('vu_utc') != state.get('passage_utc'):
            continue
        retry = instant(h.get('prochain_essai_utc'))
        if attempts.get(('COLLECTE', key), 0) >= 1 or retry and now < retry:
            continue
        if not h.get('geny') and not h.get('course_url'):
            h['collecte'] = 'LIEN_GENY_A_RESOUDRE'
            continue
        # La nuit, combler les carrières absentes avant les actualisations.
        priority=priorite_engagement(h,now,manquant=h.get('motif_actualisation')=='HISTORIQUE_ABSENT_OU_NON_DATE')
        enrichment=h.get('motif_actualisation')=='FERRURES_HISTORIQUES_A_COMPLETER'
        candidates.append(((enrichment,priority,h['engagement'],key),key))
    if candidates:
        return min(candidates)[1], 'COLLECTE'
    return None, 'TERMINE'


def executer_enfant(horse, out):
    out.mkdir(parents=True, exist_ok=True)
    task = out/'tache.json'
    ecrire(task, horse)
    subprocess.run([sys.executable, '-m', 'pmu_geny.historique_individuel',
                    '--tache', str(task), '--sortie', str(out)], check=True, timeout=240)
    return lire(out/'resultat.json')


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
        def indexed(d):
            result={}
            for row in d['performances']:
                clean={k:v for k,v in row.items() if k not in ('ferrure','ferrure_source')}
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
                if not ferrure:continue
                for new in after[key]:
                    if new.get('ferrure') and new['ferrure']!=ferrure:
                        raise ValueError('REGRESSION_FERRURE_A_CONTROLER')
                    if not new.get('ferrure'):
                        new['ferrure']=ferrure
                        if old.get('ferrure_source'):new['ferrure_source']=old['ferrure_source']
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
    horse['ferrures_manquantes']=doc['ferrures_manquantes']
    if doc['ferrures_manquantes']:
        horse['motif_actualisation']='FERRURES_HISTORIQUES_A_COMPLETER'
        horse['prochain_essai_utc']=(datetime.now(UTC)+timedelta(hours=6)).isoformat()
    horse['derniere_performance_date'] = max((r.get('date', '') for r in doc['performances']), default='')
    journal = lire(cache/'etat_persistant.json', {'version': 1, 'chevaux': {}})
    journal.setdefault('chevaux', {})[ident] = {**journal.get('chevaux', {}).get(ident, {}),
        'id': ident, 'nom': horse['nom'], 'statut': 'COMPLET', 'motifs': [],
        'nombre_extrait': doc['nombre_extrait'], 'nombre_annonce_geny': doc['nombre_annonce_geny'],
        'maj_utc': stamp, 'historique_complet_au_utc': stamp,
        'prochaine_verification_utc': horse['prochaine_verification_utc'],
        'origine': origine}
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
            for name in ('historiques', 'historiques_versions', 'manifestes'):
                if (cache/name).exists():
                    shutil.copytree(cache/name, target/name, dirs_exist_ok=True)
            shutil.copy2(cache/'etat_persistant.json', target/'etat_persistant.json')
            git('add', str(queue.parent), 'historiques', 'etat_persistant.json', cwd=target)
            if (target/'manifestes').exists():
                git('add', 'manifestes', cwd=target)
            if (target/'historiques_versions').exists():
                git('add', 'historiques_versions', cwd=target)
            changed = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=target).returncode
            if changed:
                git('commit', '-m', 'PMU : checkpoint collecte incrementale', cwd=target)
                # Pas de force push : un conflit arrête le passage avant le cheval suivant.
                git('push', 'origin', 'HEAD:refs/heads/pmu-data', cwd=target)
        finally:
            git('worktree', 'remove', '--force', str(target))


def run(cache, *, max_minutes=15, max_chevaux=1000, publier=False,
        collect=executer_enfant, checkpoint=None, sync=None, mode='production', stop_requested=None):
    cache = Path(cache)
    now = datetime.now(UTC)
    reprise=None
    if mode=='rattrapage':
        from . import rattrapage_historiques as reprise
    elif mode!='production':
        raise ValueError('MODE_COLLECTE_INCONNU')
    queue=reprise.QUEUE if reprise else QUEUE
    state = reprise.preparer(cache,now) if reprise else alimenter(cache, now)
    state['passage_utc'] = now.isoformat()
    state['priorite_collecte']='PARTANTS_SANS_HISTORIQUE_NUIT' if nuit_collecte(now) else 'ENGAGEMENTS_JOUR'
    state.pop('motif_fin_passage',None)
    journal = lire(cache/'etat_persistant.json', {'version': 1, 'chevaux': {}})
    blocked = instant((journal.get('dernier_blocage_geny') or {}).get('utc'))
    if blocked and now < blocked+timedelta(minutes=30):
        state['prochain_acces_geny_utc'] = (blocked+timedelta(minutes=30)).isoformat()
    attempts, count = {}, 0
    sheets_engine=None
    deadline = time.monotonic()+max_minutes*60
    def save():
        state['maj_utc'] = datetime.now(UTC).isoformat()
        if reprise:reprise.bilan(state)
        else:materialiser_manifestes(cache, state)
        ecrire(cache/queue, state)
        if reprise:ecrire(cache/queue.parent/'bilan.json',reprise.rapport(state))
        if checkpoint:
            checkpoint(cache)
        elif publier:
            if reprise:checkpoint_distant(cache,queue=queue)
            else:checkpoint_distant(cache)
    save()
    while time.monotonic() < deadline:
        reason=stop_requested() if stop_requested else None
        if reason:
            state['motif_fin_passage']=str(reason)
            break
        choisir=reprise.prochaine_tache if reprise else prochaine_tache
        key, action = choisir(state, datetime.now(UTC), attempts)
        if key is None:
            break
        if action == 'COLLECTE' and count >= max_chevaux:
            break
        horse = state['chevaux'][key]
        attempts[(action, key)] = attempts.get((action, key), 0)+1
        if action == 'COLLECTE':
            horse['collecte'] = 'EN_COURS'
            save()  # Reprise sûre, même si le sous-processus est tué.
            out = Path('resultats/incremental')/key/str(time.time_ns())
            report = {}
            try:
                report = collect(horse, out)
                if report.get('statut') in ('ACCES_REFUSE_403', 'ACCES_LIMITE_429'):
                    raise PermissionError(report['statut'])
                if reprise:accepter(cache,horse,report,origine='RATTRAPAGE_GLOBAL')
                else:accepter(cache, horse, report)
                ident = horse['id']
                if not reprise and key != ident:
                    state['chevaux'][ident] = horse
                    del state['chevaux'][key]
                    key = ident
                # Date de vérification != couverture : Geny peut publier la nouvelle course plus tard.
                race = instant(horse.get('derniere_course_officielle_utc')) if not reprise else None
                if race and horse.get('derniere_performance_date', '') < race.date().isoformat():
                    doc = capture_valide(cache, ident)
                    horse['derniere_performance_date'] = max((r.get('date', '') for r in doc['performances']), default='')
                    if horse['derniere_performance_date'] < race.date().isoformat():
                        horse['motif_actualisation'] = 'PUBLICATION_GENY_EN_ATTENTE'
                        horse['prochain_essai_utc'] = (datetime.now(UTC)+timedelta(hours=6)).isoformat()
            except Exception as exc:
                horse.update(collecte='A_REPRENDRE', erreur=f'{type(exc).__name__}: {exc}',
                             prochain_essai_utc=(datetime.now(UTC)+timedelta(hours=6)).isoformat())
                if isinstance(exc, PermissionError):
                    stamp = datetime.now(UTC)
                    state['prochain_acces_geny_utc'] = (stamp+timedelta(minutes=30)).isoformat()
                    journal = lire(cache/'etat_persistant.json', {'version': 1, 'chevaux': {}})
                    journal['dernier_blocage_geny'] = {'utc': stamp.isoformat(), 'code': '403' if '403' in str(exc) else '429'}
                    ecrire(cache/'etat_persistant.json', journal)
                elif report.get('statut') in ('ERREUR', 'ERREUR_NAVIGATION', 'ACCES_INDISPONIBLE') and horse.get('course_url'):
                    horse.pop('geny', None)  # Résoudre à nouveau une URL périmée au prochain essai.
            count += 1
            save()  # Publier les données AVANT toute écriture Sheets.
            if horse.get('sync') != 'A_FAIRE':
                if instant(state.get('prochain_acces_geny_utc')) and datetime.now(UTC) < instant(state['prochain_acces_geny_utc']):
                    continue
                time.sleep(30)
                continue
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
            horse.update(sync='OK', sync_utc=datetime.now(UTC).isoformat(), erreur='')
            if reprise:reprise.valider_sync(state,horse)
        except Exception as exc:
            horse.update(sync='A_FAIRE', erreur=f'{type(exc).__name__}: {exc}',
                         prochaine_sync_utc=(datetime.now(UTC)+timedelta(minutes=10)).isoformat())
            from .controle_sync_sheets import BlocageSynchronisation
            from .moteur_sheets import SynchronisationOccupee
            if isinstance(exc,(BlocageSynchronisation,SynchronisationOccupee)):
                save()
                if sheets_engine:sheets_engine.fermer()
                raise  # Incident visible en échec Actions ; ne pas continuer silencieusement.
        save()
        if action == 'COLLECTE':
            time.sleep(30)
    state['bilan'] = {'chevaux_suivis': len(state['chevaux']), 'tentatives_collecte': count,
                      'synchronisations_en_attente': sum(h.get('sync') == 'A_FAIRE' for h in state['chevaux'].values()),
                      'actualisations_en_attente': sum(bool(h.get('motif_actualisation')) for h in state['chevaux'].values())}
    state['statut'] = ('PARTIEL_REPRENABLE' if state['bilan']['actualisations_en_attente'] or
                       state['bilan']['synchronisations_en_attente'] else 'A_JOUR')
    if publier and sync is None and (sheets_engine is not None or state.get('sync_kpi')=='A_REPRENDRE'):
        from .moteur_sheets import SynchroniseurSheets
        if sheets_engine is None:sheets_engine=SynchroniseurSheets(cache,os.environ['GOOGLE_SHEETS_ID'])
        try:
            state['sync_kpi_details']=sheets_engine.synchroniser_kpi()
            state['sync_kpi']='OK'
        except Exception:
            state['sync_kpi']='A_REPRENDRE';save()
            raise
        finally:sheets_engine.fermer()
    save()
    return state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', default='cache_pmu')
    parser.add_argument('--max-minutes', type=int, default=15)
    parser.add_argument('--max-chevaux', type=int, default=1000)
    parser.add_argument('--publier', action='store_true')
    args = parser.parse_args()
    if args.max_minutes < 1 or args.max_chevaux < 1:
        parser.error('Bornes positives requises')
    if not args.publier:
        state = alimenter(Path(args.cache), datetime.now(UTC))
        print(json.dumps({'mode': 'INVENTAIRE_SANS_RESEAU', 'chevaux': len(state['chevaux'])}))
        return
    if not all(os.environ.get(k) for k in ('GOOGLE_SHEETS_ID', 'GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON')):
        raise SystemExit('Secrets Sheets absents : aucune collecte lancée')
    state = run(Path(args.cache), max_minutes=args.max_minutes, max_chevaux=args.max_chevaux, publier=True)
    print('BILAN_INCREMENTAL '+json.dumps(state['bilan']))


if __name__ == '__main__':
    main()
