"""Rejouer les captures en échec sans consulter à nouveau la source hippique."""
import hashlib
import json
import os
import re
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path,PurePosixPath

from . import historiques_incrementaux as inc
from .collecte_geny_v4 import parse_career
from .controle_historique import classifier
from .ferrures_geny import enrichir,cle_performance
from .liaison_chevaux_v22 import nom_normalise
from .carriere_geny import confirmer_inedit


def revalider(cache,archive):
    from . import rattrapage_historiques as back
    cache=Path(cache);archive=Path(archive);now=datetime.now(inc.UTC)
    state=back.preparer(cache,now)
    report={'captures_revalidees':0,'performances_revalidees':0,'captures_ignorees':0}
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as zipped:
        def read(name):
            if zipped.getinfo(name).file_size>10*1024*1024:raise ValueError('DIAGNOSTIC_TROP_VOLUMINEUX')
            return zipped.read(name).decode('utf-8')
        for filename in zipped.namelist():
            if not re.fullmatch(r'resultats/incremental/[^/]+/\d+/resultat\.json',filename):continue
            previous=json.loads(read(filename));geny=previous.get('geny',{});ident=str(geny.get('id',''))
            horses=[h for h in state['chevaux'].values() if h.get('id')==ident and h.get('nom')
                    and not h.get('conflit_identite')
                    and nom_normalise(h.get('nom'))==nom_normalise(geny.get('nom'))]
            # Une résolution avait pu réussir avant l'échec de lecture, sans
            # que l'identifiant ait été accepté. Retrouver alors la cible par
            # son contexte archivé, pas par le seul nom.
            task_file=str(PurePosixPath(filename).parent/'tache.json')
            if not horses and task_file in zipped.namelist():
                task=json.loads(read(task_file));context=back.contexte_verifiable(task)
                race=re.search(r'/course/(\d+)',str(task.get('course_url','')))
                actual=re.search(r'/course/(\d+)',str(geny.get('url_geny','')))
                if (not task.get('id') and context and race and actual and race[1]==actual[1]
                        and back.url_course(task.get('course_url'))
                        and nom_normalise(task.get('nom'))==nom_normalise(geny.get('nom'))):
                    horses=[h for h in state['chevaux'].values() if not h.get('id')
                            and not h.get('conflit_identite') and back.contexte_verifiable(h)==context]
            if (previous.get('complet') or not previous.get('identite_verifiee') or not horses
                    or not re.fullmatch(r'\d{4,15}',ident) or not back.url_cheval(geny.get('url_geny'),ident)
                    or inc.capture_valide(cache,ident)):
                report['captures_ignorees']+=1;continue
            folder=PurePosixPath(filename).parent/ident
            required=[str(folder/x) for x in ('historique_geny.json','diagnostic_texte_geny.txt')]
            if not all(x in zipped.namelist() for x in required):report['captures_ignorees']+=1;continue
            old=json.loads(read(required[0]));text=read(required[1]);stamp=inc.instant(old.get('extrait_utc'))
            if (not stamp or stamp>now or not back.url_cheval(old.get('source_url'),ident)
                    or nom_normalise(geny['nom']) not in nom_normalise(text[:6000])):
                report['captures_ignorees']+=1;continue
            parsed=parse_career(text,[])
            parsed.update(source_url=old['source_url'],extrait_utc=old['extrait_utc'])
            html=str(folder/'diagnostic_geny.html')
            confirmed=confirmer_inedit(parsed,read(html),ident) if html in zipped.namelist() else False
            # Une absence prouvée avant un premier départ n'est pas la preuve
            # d'une carrière encore vide après ce départ.
            expired_zero=(confirmed and inc.instant(parsed['preuve_carriere_vide']['depart_utc'])<=now)
            same_total=(parsed['nombre_annonce_geny']==old.get('nombre_annonce_geny')
                        or confirmed and old.get('nombre_annonce_geny') is None)
            if classifier(parsed)[0]!='COMPLET' or not same_total or expired_zero:
                report['captures_ignorees']+=1;continue
            # Conserver les ferrures déjà observées, seulement si la performance
            # correspond sans ambiguïté ; la nouvelle lecture ne les invente pas.
            for row in parsed['performances']:
                matches=[x for x in old.get('performances',[]) if
                         cle_performance(x)==cle_performance(row) and x.get('chrono')==row.get('chrono')]
                if len(matches)==1:
                    for key in ('ferrure','ferrure_source'):
                        if matches[0].get(key):row[key]=matches[0][key]
            document={**old,**parsed}
            if html in zipped.namelist():enrichir(document,read(html),ident,old['source_url'],old['extrait_utc'])
            document['revalidation_archive']={'sha256':digest,'resultat':filename,'utc':now.isoformat()}
            with tempfile.TemporaryDirectory() as tmp:
                inc.ecrire(Path(tmp)/'historique_geny.json',document)
                inc.accepter(cache,horses[0],{**previous,'complet':True,'statut':'COMPLET','dossier':tmp},
                             origine='REVALIDATION_DIAGNOSTIC_ARCHIVE')
            report['captures_revalidees']+=1;report['performances_revalidees']+=len(parsed['performances'])
    state['derniere_revalidation']={'utc':now.isoformat(),'archive_sha256':digest,**report}
    back.bilan(state);inc.ecrire(cache/back.QUEUE,state)
    inc.ecrire(cache/back.QUEUE.parent/'bilan.json',back.rapport(state, cache=cache))
    return report


def revalider_artifacts(cache,identifiants):
    """Télécharger uniquement les artefacts du dépôt courant, avec son jeton Actions."""
    import requests
    if not re.fullmatch(r'\d+(?:,\d+){0,4}',identifiants):raise ValueError('ARTEFACTS_INVALIDES')
    repo=os.environ.get('GITHUB_REPOSITORY','');token=os.environ.get('GH_TOKEN','')
    if not re.fullmatch(r'[\w.-]+/[\w.-]+',repo) or not token:raise ValueError('CONTEXTE_GITHUB_REQUIS')
    for ident in identifiants.split(','):
        response=requests.get(f'https://api.github.com/repos/{repo}/actions/artifacts/{ident}/zip',
            headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json'},timeout=60)
        if response.status_code!=200:raise ValueError('ARTEFACT_INACCESSIBLE_HTTP_'+str(response.status_code))
        if len(response.content)>32*1024*1024:raise ValueError('ARTEFACT_TROP_VOLUMINEUX')
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'diagnostics.zip';archive.write_bytes(response.content)
            report=revalider(cache,archive)
        print('REVALIDATION_DIAGNOSTICS '+json.dumps({'artefact':ident,**report}),flush=True)
