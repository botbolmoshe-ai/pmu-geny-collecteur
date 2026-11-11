"""Contexte météo pré-départ sourcé (Open-Meteo) pour le moteur V19.

Aucune donnée inférée en cas d'erreur d'accès/géocodage. Les valeurs sont
sauvegardées avec l'horodatage de capture, jamais reconstituées après le départ.
L'état officiel du terrain n'est PAS déduit des précipitations.
"""
from __future__ import annotations
import json, math, re, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FORECAST = 'https://api.open-meteo.com/v1/forecast'
GEOCODE = 'https://geocoding-api.open-meteo.com/v1/search'
# Localisations de piste vérifiées, sans géocodage externe ambigu.
# Sources: office de tourisme Vincennes (48.820896,2.452039);
# Recensement des équipements sportifs, piste de trot Amiens (49.89498,2.27037).
KNOWN_TRACKS = {
    'hippodromedeparisvincennes':(48.820896,2.452039,'Vincennes, Paris'),
    'hippodromedevincennes':(48.820896,2.452039,'Vincennes, Paris'),
    'vincennes':(48.820896,2.452039,'Vincennes, Paris'),
    'hippodromedamiens':(49.89498,2.27037,'Amiens'),
    'hippodromedu petitsaintjean':(49.89498,2.27037,'Amiens'),
    'amiens':(49.89498,2.27037,'Amiens'),
}
WEATHER_FIELDS = {
    'precipitation': 'meteo_pluie_mm',
    'wind_speed_10m': 'meteo_vent_kmh',
    'temperature_2m': 'meteo_temperature_c',
    'relative_humidity_2m': 'meteo_humidite_pct',
}


def _get_json(url, timeout=15):
    if not (url.startswith(FORECAST+'?') or url.startswith(GEOCODE+'?')):
        raise ValueError('URL météo non autorisée')
    request=Request(url,headers={'Accept':'application/json','User-Agent':'pmu-geny-data-research/1.0'})
    with urlopen(request,timeout=timeout) as response:
        if response.status!=200:raise RuntimeError(f'METEO_HTTP_{response.status}')
        data=response.read(1_000_001)
        if len(data)>1_000_000:raise ValueError('Réponse météo trop volumineuse')
        parsed=json.loads(data)
        if not isinstance(parsed,dict):raise ValueError('JSON météo invalide')
        return parsed


def _norm(s):
    s=unicodedata.normalize('NFKD',str(s).casefold())
    return re.sub(r'[^a-z0-9]','', ''.join(x for x in s if not unicodedata.combining(x)))


def _resolve_location(cache:Path, hippodrome:str):
    """Géocodage d'une ville FR, jamais un résultat approximatif ambigu."""
    name=hippodrome.strip()
    key=_norm(name)
    if key in KNOWN_TRACKS:
        lat,lon,local=KNOWN_TRACKS[key]
        return {'latitude':lat,'longitude':lon,'localite':local,
                'source':'COORDONNEES_PISTE_REFERENCEES','precision':'piste_hippodrome'}
    path=cache/'contextes'/'geocodage_v20.json'
    data=_load(path,{}) or {}
    if key in data:
        return data[key]
    url=GEOCODE+'?'+urlencode({'name':name,'count':10,'language':'fr','countryCode':'FR','format':'json'})
    doc=_get_json(url)
    matches=[x for x in doc.get('results',[]) if isinstance(x,dict)
             and str(x.get('country_code','')).upper()=='FR'
             and _norm(x.get('name',''))==key
             and isinstance(x.get('latitude'),(float,int))
             and isinstance(x.get('longitude'),(float,int))]
    # Plusieurs villes de même nom -> pas de localisation inventée.
    if len(matches)!=1:
        raise ValueError(f'Géocodage hippodrome non univoque : {name} ({len(matches)} correspondances)')
    result={'latitude':float(matches[0]['latitude']),'longitude':float(matches[0]['longitude']),
            'localite':matches[0]['name'],'source':url, 'precision':'ville_voisine_pas_piste'}
    data[key]=result
    _save(path,data)
    return result


def _load(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default


def _save(path,doc):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)


def collecter_meteo(cache,course,now=None,request_json=None,resolve_location=None):
    """Retourne un statut explicite; injecte des observations numériques horodatées.

    request_json / resolve_location injectables exclusivement pour tests hors réseau.
    """
    cache=Path(cache)
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None: raise ValueError('Horodatage sans fuseau')
    depart=datetime.fromisoformat(course['depart'])
    if depart.tzinfo is None:raise ValueError('Départ sans fuseau')
    if now>=depart:return 'APRES_DEPART'
    path=cache/'contextes'/f"{course['date']}_{course['code']}.json"
    existing=_load(path,{}) or {}
    previous=[x for x in existing.get('observations',[]) if x.get('champ') in WEATHER_FIELDS.values()]
    if previous:
        try:
            last=max(datetime.fromisoformat(x['collecte_utc']) for x in previous)
            if now-last<timedelta(minutes=45):return 'METEO_RECENTE'
        except (KeyError,ValueError,TypeError):pass
    locate=resolve_location or _resolve_location
    site=locate(cache,course['hippodrome'])
    requester=request_json or _get_json
    url=FORECAST+'?'+urlencode({'latitude':site['latitude'],'longitude':site['longitude'],
        'hourly':','.join(WEATHER_FIELDS),'timezone':'Europe/Paris',
        'start_date':depart.date().isoformat(),'end_date':depart.date().isoformat()})
    doc=requester(url)
    hourly=doc.get('hourly',{})
    if not isinstance(hourly,dict) or not isinstance(hourly.get('time'),list):
        raise ValueError('Séries horaires météo absentes')
    # Arrondir à l'heure de départ antérieure; pas de météo de l'heure suivante.
    local=depart.astimezone(depart.tzinfo).replace(minute=0,second=0,microsecond=0)
    target=local.strftime('%Y-%m-%dT%H:00')
    try:i=hourly['time'].index(target)
    except ValueError:raise ValueError(f'Heure météo du départ introuvable : {target}') from None
    captured=now.astimezone(timezone.utc).isoformat()
    rows=[]
    for source_field,feature in WEATHER_FIELDS.items():
        series=hourly.get(source_field)
        if not isinstance(series,list) or i>=len(series):continue
        value=series[i]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):continue
        if source_field=='precipitation' and value<0:continue
        if source_field in ('wind_speed_10m','relative_humidity_2m') and value<0:continue
        rows.append({'champ':feature,'valeur':round(float(value),3),'collecte_utc':captured,
                    'source_url':url,'source':'Open-Meteo Forecast','heure_prevision_locale':target,
                    'type_donnee':'prevision_avant_depart','precision_geographique':'ville_pas_hippodrome'})
    if not rows:raise ValueError('Aucune mesure météo exploitable')
    old=[x for x in existing.get('observations',[]) if x.get('champ') not in WEATHER_FIELDS.values()]
    existing.update({'course':course['code'],'date':course['date'],'hippodrome':course['hippodrome'],
                     'meteo_source':'Open-Meteo Forecast','meteo_collecte_utc':captured,
                     'meteo_statut':'PREVISION_CAPTUREE','meteo_precision_geographique':site.get('precision','ville'),
                     'observations':old+rows})
    _save(path,existing)
    return f'METEO_CAPTUREE_{len(rows)}'
