"""Test ponctuel d'une fiche cheval publique, sans authentification ni contournement."""
import json,sys
from html.parser import HTMLParser
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
URL="https://www.zeturf.fr/fr/course-du-jour/2026-10-14/R1C1-reims-grand-national-du-trot/9/infos"
class Text(HTMLParser):
 def __init__(self): super().__init__();self.parts=[]
 def handle_data(self,d): self.parts.append(d)
def main():
 result={"source":"zeturf","type":"FICHE_CHEVAL","cheval":"JACOMO BELLO","url":URL,"performances_extraites":0,"extraction_historique_validee":False}
 try:
  with urlopen(Request(URL,headers={"User-Agent":"Mozilla/5.0 (compatible; HistoryResearch/1.0)"}),timeout=15) as r:
   body=r.read(300000).decode("utf-8","replace");p=Text();p.feed(body)
   txt=" ".join(" ".join(p.parts).split()).lower()
   result.update(http=r.status,octets=len(body),nom_present="jacomo bello" in txt,
    acces_historique_restreint="pour bénéficier des fonctionnalités zeturfpro" in txt or "vous devez être client zeturf" in txt,
    mots_cles_performances=txt.count("performance"))
 except HTTPError as e: result.update(http=e.code,erreur="HTTPError")
 except (URLError,TimeoutError,OSError) as e: result.update(erreur=type(e).__name__)
 print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":main()
