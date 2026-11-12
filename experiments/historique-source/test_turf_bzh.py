"""Sonde non destructive pour API Turf.bzh: recherche cheval et dossier course.
Aucune cle n'est affichee ni stockee. Sans cle, rapporter le statut HTTP seulement.
"""
import json,os,urllib.request,urllib.error
BASE="https://www.turf.bzh/api/v1/"
KEY=os.environ.get("TURF_BZH_API_KEY","")
URLS={"recherche_cheval":BASE+"chevaux?recherche=LOMBOK%20JIEL", "dossier_course":BASE+"courses/2026-11-12/R1C1/dossier?historique=3"}
def probe(label,url):
 headers={"Accept":"application/json","User-Agent":"PMU-Historique-Validation/1.0"}
 if KEY:headers["Authorization"]="Bearer "+KEY
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=15) as resp:
   body=resp.read(1000000);status=resp.status
 except urllib.error.HTTPError as e:status=e.code;body=e.read(1000)
 except Exception as e:return {"test":label,"statut":"ERREUR_RESEAU","type_erreur":type(e).__name__}
 result={"test":label,"http":status,"json_valide":False,"historique_verifie":False}
 try:
  data=json.loads(body);result["json_valide"]=True
  if isinstance(data,dict):
   result["cles_racine"]=list(data.keys())[:15]
   if status==200:
    # Ne jamais assimiler un dossier ou un message d'erreur a un historique date.
    result["structure_disponible"]=True
 except (ValueError,UnicodeError):pass
 return result
print(json.dumps({"source":"turf.bzh","cle_configuree":bool(KEY),"sondes":[probe(k,v) for k,v in URLS.items()],"note":"Validation de structure uniquement; historiques non valides tant que dates et classements ne sont pas extraits."},ensure_ascii=False))
