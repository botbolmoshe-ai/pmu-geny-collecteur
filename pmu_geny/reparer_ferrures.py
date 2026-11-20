"""Réparer depuis les archives locales, sans accès Geny ni modification des pronostics."""
import argparse
import copy
import csv
import hashlib
import json
import re
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.request import Request,urlopen

from .ferrures_geny import enrichir
from .historiques_incrementaux import lire,ecrire,instant


def reparer_partants(cache,fetch=None):
    from .partants_actuels_v21 import extraire_partants
    from .liaison_chevaux_v22 import nom_normalise
    def public(url):
        with urlopen(Request(url,headers={'User-Agent':'PMU-Trot-Research/1.0'}),timeout=20) as response:
            return json.load(response)
    fetch=fetch or public;now=datetime.now(timezone.utc)
    report={'courses_relues':0,'ferrures_courantes_ajoutees':0,'erreurs_sources':[]}
    for path in sorted((Path(cache)/'partants_actuels').glob('????-??-??_R*C*.json')):
        doc=lire(path)
        if doc.get('source')!='PMU_API_PARTICIPANTS' or not any(not h.get('ferrure') for h in doc.get('chevaux',{}).values()):continue
        last=instant(doc.get('dernier_controle_reparation_ferrures_utc'))
        if last and now-last<timedelta(hours=6):continue
        match=re.fullmatch(r'(\d{4})-(\d{2})-(\d{2})_R(\d+)C(\d+)',path.stem)
        if not match:continue
        year,month,day,r,c=match.groups()
        url=f'https://online.turfinfo.api.pmu.fr/rest/client/1/programme/{day}{month}{year}/R{r}/C{c}/participants'
        doc['dernier_controle_reparation_ferrures_utc']=now.isoformat()
        try:profiles=extraire_partants(fetch(url));report['courses_relues']+=1
        except Exception as exc:
            code=getattr(exc,'code',None)
            report['erreurs_sources'].append({'course':path.stem,'http':code,'erreur':type(exc).__name__})
            ecrire(path,doc)
            if code in (403,429):break
            continue
        for number,horse in doc.get('chevaux',{}).items():
            profile=profiles.get(int(number),{})
            if (horse.get('ferrure') or not profile.get('ferrure') or
                    nom_normalise(horse.get('nom'))!=nom_normalise(profile.get('nom'))):continue
            horse['ferrure']=profile['ferrure']
            proof=profile.get('provenance_champs',{}).get('ferrure',{'source':'PMU_API_PARTICIPANTS'})
            horse.setdefault('provenance_champs',{})['ferrure']={**proof,'url':url,'capture_utc':now.isoformat()}
            report['ferrures_courantes_ajoutees']+=1
        ecrire(path,doc)
    return report


def reparer(cache, *, partants=False, fetch=None, stop_requested=None, apres_archive=''):
    cache=Path(cache);report={'archives_lues':0,'historiques_enrichis':0,'ferrures_ajoutees':0,'departs_ajoutes':0,'conflits':0,
            'ferrures_ajoutees_par_id':{},'reprise_apres_archive':''}
    last = apres_archive
    for html in sorted((cache/'diagnostics').rglob('diagnostic_geny.html')):
        relative = html.relative_to(cache).as_posix()
        if relative <= apres_archive:
            continue
        if stop_requested and stop_requested():
            report['reprise_apres_archive'] = last
            break
        last = relative
        ident=html.parent.name
        if not re.fullmatch(r'\d{4,15}',ident):continue
        target=cache/'historiques'/ident/'historique_geny.json'
        previous=lire(target)
        if not previous or not isinstance(previous.get('performances'),list):continue
        evidence=lire(html.parent/'historique_geny.json')
        url=evidence.get('source_url') or previous.get('source_url','')
        if not re.search(r'/cheval/'+re.escape(ident)+r'(?:\D|$)',url):continue
        capture = instant(evidence.get('extrait_utc'))
        if not capture or capture > datetime.now(timezone.utc):
            continue
        doc=copy.deepcopy(previous)
        result=enrichir(doc,html.read_text(encoding='utf-8'),ident,url,evidence.get('extrait_utc'))
        report['archives_lues']+=1;report['conflits']+=result['conflits']
        if not (result['ferrures_ajoutees'] or result['departs_ajoutes']):continue
        # La date de capture de carrière reste celle d'origine ; ne jamais la
        # remplacer par la date de réparation ou par le mtime d'un fichier.
        archive=cache/'historiques_versions'/ident/(hashlib.sha256(json.dumps(previous,sort_keys=True).encode()).hexdigest()+'.json')
        ecrire(archive,previous);ecrire(target,doc)
        columns=['date','hippodrome','discipline','distance_m','classement','chrono','texte_source','ferrure']
        with target.with_suffix('.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns,delimiter=';',extrasaction='ignore')
            writer.writeheader();writer.writerows(doc['performances'])
        report['historiques_enrichis']+=1;report['ferrures_ajoutees']+=result['ferrures_ajoutees']
        report['departs_ajoutes']+=result['departs_ajoutes']
        if result['ferrures_ajoutees']:
            added = report['ferrures_ajoutees_par_id']
            added[ident] = added.get(ident, 0) + result['ferrures_ajoutees']
    if partants:report.update(reparer_partants(cache,fetch))
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cache',default='cache_pmu');parser.add_argument('--partants',action='store_true');args=parser.parse_args()
    report=reparer(Path(args.cache),partants=args.partants)
    out=Path('resultats/ferrures');out.mkdir(parents=True,exist_ok=True)
    (out/'reparation_archives.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('REPARATION_FERRURES '+json.dumps(report),flush=True)


if __name__=='__main__':main()
