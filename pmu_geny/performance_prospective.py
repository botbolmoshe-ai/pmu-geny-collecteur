"""Mesurer uniquement les versions publiées avant départ et les arrivées vérifiées."""
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from .echeances_production import lire, sauver, instant


def retrouver(cache,key,kind,proof):
    path=cache/proof.get('fichier','')
    if cache.resolve() not in path.resolve().parents:return None
    # Le dernier calcul peut avoir changé avant un échec Sheets. Rechercher la
    # version effectivement publiée, sans lui substituer un nouveau classement.
    candidates=[path,*sorted((cache/'pronostics/versions').glob(f'{key}_{kind}_*.json'))]
    for p in candidates:
        if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==proof.get('sha256'):
            return lire(p)
    return None


def mesurer(cache,now=None):
    cache=Path(cache);now=now or datetime.now(timezone.utc)
    results=[];rejected=[];depart_candidate={};depart_baseline={}
    for p in sorted((cache/'publications').glob('*.json')):
        certificate=lire(p);key=p.stem;depart=instant(certificate.get('depart'))
        arrival=lire(cache/'arrivees'/f'{key}.json');checked=instant(arrival.get('verifie_utc'))
        if not depart or not checked or not depart<checked<=now:
            continue
        if arrival.get('source')!='PMU_API_PARTICIPANTS':
            rejected.append({'course':key,'motif':'SOURCE_ARRIVEE_NON_VERIFIEE'});continue
        try:
            podium=[int(h['numero']) for h in arrival['arrivee'] if h['rang'] in (1,2,3)]
            if (len(podium)!=3 or len(set(podium))!=3
                    or {h['rang'] for h in arrival['arrivee'] if h['rang'] in (1,2,3)}!={1,2,3}):raise ValueError()
            scores={};versions={};alternate=None
            for kind in ('direct','ml'):
                proof=certificate['versions'][kind]
                published=instant(proof.get('publication_utc'))
                created=instant(proof.get('calcul_utc'))
                doc=retrouver(cache,key,kind,proof)
                if not doc or not published or not created or not created<=published<depart:
                    raise ValueError('PREUVE_PUBLICATION_INVALIDE')
                if doc.get('calcul_utc')!=proof['calcul_utc']:raise ValueError('VERSION_INCOHERENTE')
                if doc.get('date','')+'_'+doc.get('course','')!=key or instant(doc.get('depart'))!=depart:
                    raise ValueError('COURSE_INCOHERENTE')
                if kind=='ml' and doc.get('experimental'):
                    fitted=instant(doc.get('entrainement_utc'))
                    label=instant(doc.get('dernier_label_entrainement_utc'))
                    if not fitted or not label or not label<=fitted<=created:raise ValueError('FUITE_TEMPORELLE')
                numbers=[int(h['numero']) for h in doc['top3']]
                if len(numbers)!=3 or len(set(numbers))!=3:raise ValueError('TOP3_INVALIDE')
                scores[kind]=len(set(numbers)&set(podium))
                if kind == 'direct':
                    candidate = doc.get('candidat_depart', {})
                    proposed = candidate.get('top3', [])
                    eligible = {h.get('numero') for h in doc.get('classement_complet', [])}
                    if len(proposed) == len(set(proposed)) == 3 and set(proposed) <= eligible:
                        alternate = len(set(proposed) & set(podium))
                versions[kind]=proof['sha256']
            if alternate is not None:
                depart_candidate[key] = alternate
                depart_baseline[key] = scores['direct']
            results.append({'course':key,'depart':depart.isoformat(),'arrivee_verifiee_utc':checked.isoformat(),
                'scores':scores,'versions':versions,'empreinte_modele':certificate['versions']['ml'].get('empreinte_modele')})
        except (KeyError,ValueError,TypeError) as exc:
            rejected.append({'course':key,'motif':str(exc) or 'ARRIVEE_INVALIDE'})
    n=len(results)
    report={'nature':'PREVISIONS_PUBLIEES_AVANT_DEPART','controle_utc':now.isoformat(),'courses':n,
            'moyenne_ml':sum(r['scores']['ml'] for r in results)/n if n else None,
            'moyenne_direct':sum(r['scores']['direct'] for r in results)/n if n else None,
            'ecart_ml_direct':sum(r['scores']['ml']-r['scores']['direct'] for r in results)/n if n else None,
            'exact_3_sur_3_ml':sum(r['scores']['ml']==3 for r in results),
            'au_moins_2_sur_3_ml':sum(r['scores']['ml']>=2 for r in results),
            'resultats':results,'rejets':rejected,
            'regle_ajustement':'Reentrainement sur nouveaux labels admissibles ; choix sur validation temporelle, jamais sur le test ni promotion sur ces seuls scores.'}
    report['candidat_depart'] = {'courses': len(depart_candidate), 'statut': 'DONNEES_INSUFFISANTES'}
    if depart_candidate:
        from .experience_ml import paired_interval
        report['candidat_depart'].update(
            statut='EXPERIMENTAL', comparaison=paired_interval(depart_candidate, depart_baseline),
            scores_candidat_par_course=depart_candidate, scores_direct_par_course=depart_baseline,
        )
    sauver(cache/'ml/performance_prospective.json',report)
    return report
