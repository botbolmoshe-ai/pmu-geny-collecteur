"""Identifiants propres à chaque fournisseur et correspondances vérifiées.

Un numéro Zone-Turf n'est jamais un numéro Geny par convention. Les liens
inter-sources sont explicites, sourcés et révisables dans le registre JSON.
"""
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from .liaison_chevaux_v22 import nom_geny_concordant, nom_normalise

REGISTRE = Path(__file__).with_name('identites_chevaux_verifiees.json')


def source_identifiant(ident, url):
    parsed = urlparse(str(url or ''))
    if parsed.scheme != 'https':
        return ''
    if parsed.hostname in ('geny.com', 'www.geny.com'):
        match = re.match(r'/cheval/(\d+)(?:\D|$)', parsed.path)
        return 'geny' if match and match[1] == str(ident) else ''
    if parsed.hostname in ('zone-turf.fr', 'www.zone-turf.fr'):
        match = re.fullmatch(r'/cheval/[^/]+-(\d+)/(?:resume-de-carriere/?)?', parsed.path)
        return 'zone_turf' if match and match[1] == str(ident) else ''
    return ''


@lru_cache(maxsize=1)
def correspondances():
    entries = json.loads(REGISTRE.read_text(encoding='utf-8'))['correspondances']
    seen = set()
    for item in entries:
        stamp = datetime.fromisoformat(item['verification_utc'])
        ids = item['identifiants']
        if (not item.get('nom') or stamp.tzinfo is None or stamp > datetime.now(timezone.utc)
                or not re.fullmatch(r'\d{4,15}', ids['geny'])
                or source_identifiant(ids['geny'], item['url_geny']) != 'geny'
                or not re.fullmatch(r'https://www\.geny\.com/course/\d+/partants-pronostics', item['course_url'])
                or not re.fullmatch(r'\d{4}-\d{2}-\d{2}_R\d+C\d+', item['engagement'])
                or not str(item.get('numero', '')).isdigit()
                or len(item.get('performances_rapprochees', [])) < 2):
            raise ValueError('CORRESPONDANCE_IDENTITE_NON_PROUVEE')
        if re.search(r'/course/(\d+)', item['url_geny'])[1] != re.search(r'/course/(\d+)', item['course_url'])[1]:
            raise ValueError('COURSE_IDENTITE_NON_CONCORDANTE')
        for source, ident in ids.items():
            if source != 'geny' and source_identifiant(ident, item['urls_sources'].get(source)) != source:
                raise ValueError('SOURCE_IDENTIFIANT_NON_CONCORDANTE')
            if (source, ident) in seen:
                raise ValueError('CORRESPONDANCE_IDENTITE_AMBIGUE')
            seen.add((source, ident))
    return entries


@lru_cache(maxsize=1)
def courses_verifiees():
    return json.loads(REGISTRE.read_text(encoding='utf-8')).get('courses_verifiees', [])


def course_verifiee(engagement):
    from .echeances_production import instant

    now = datetime.now(timezone.utc)
    matches = {course[1] for proof in courses_verifiees()
               if proof.get('engagement') == engagement and proof.get('http') == 200
               and (stamp := instant(proof.get('capture_utc'))) and stamp <= now
               and (course := re.fullmatch(r'https://www\.geny\.com/course/(\d+)(?:-[^/]+)?/partants-pronostics',
                                           proof.get('source_url', '')))
               and course[1] == str(proof.get('course_geny_id'))}
    return 'GENY-' + matches.pop() if len(matches) == 1 else ''


def qualifier_observation(record):
    """Conserver la provenance ; appliquer seulement une liaison déjà vérifiée."""
    record = dict(record)
    ident = str(record.get('id', ''))
    source = source_identifiant(ident, record.get('source_url'))
    if not source:
        # Certaines anciennes lignes portent déjà l'URL Geny exacte mais
        # encore le numéro Zone-Turf dans la colonne ID.
        for proof in correspondances():
            if (nom_normalise(proof['nom'])==nom_normalise(record.get('nom'))
                    and source_identifiant(proof['identifiants']['geny'],record.get('source_url'))=='geny'):
                source=next((s for s,i in proof['identifiants'].items() if s!='geny' and i==ident),'')
                if source:break
    if not source:
        return record
    record['source_identifiant'] = source
    record['identifiants_sources'] = {source: ident}
    if source == 'geny':
        return record
    matches = [x for x in correspondances() if x['identifiants'].get(source) == ident
               and nom_normalise(x['nom']) == nom_normalise(record.get('nom'))]
    if len(matches) == 1:
        proof = matches[0]
        record.update(id=proof['identifiants']['geny'], url_geny=proof['url_geny'],
                      identifiants_sources=proof['identifiants'], reconciliation_identite=proof)
    else:
        # Un nouveau lien nécessite une vérification explicite ; aucun candidat
        # /cheval/ID n'est construit sur le serveur d'un autre fournisseur.
        record.update(id='', identifiant_externe_non_reconcilie=True)
    return record


def canoniser_ligne(row):
    observation = qualifier_observation({'id': str(row.get('identifiant_cheval', '')),
        'nom': row.get('cheval', ''), 'source_url': row.get('source_url', '')})
    if observation.get('reconciliation_identite'):
        return {**row, 'identifiant_cheval': observation['id']}
    return row


def cle_inter_sources(row):
    """Même performance attestée : seule la notation des secondes est normalisée."""
    from .controle_sync_sheets import cle_sportive
    row = dict(canoniser_ligne(row))
    row['chrono'] = str(row.get('chrono', '')).replace('"', "''")
    return cle_sportive(row)


class IndexGeny:
    """Index des preuves d'identité, commun aux collecteurs et aux lecteurs."""

    def __init__(self, cache, *, observations=None):
        from collections import defaultdict
        from .ml_v19 import load

        self.noms = defaultdict(dict)
        self.contextes = defaultdict(set)
        self.annees = defaultdict(set)
        self.pmu = defaultdict(set)
        self.annees_par_id = defaultdict(set)
        self.noms_par_id = defaultdict(set)
        self.cache = Path(cache)
        journal = (load(self.cache/'etat_persistant.json', {}) or {}).get('chevaux', {})
        for proof in correspondances():
            self.ajouter(proof['nom'], proof['identifiants']['geny'], proof['url_geny'], 'REGISTRE_VERIFIE')
        if observations is None:
            snapshot = load(self.cache/'rattrapage_historiques/inventaire_sheets.json', {}) or {}
            observations = snapshot.get('chevaux', [])
        for record in observations:
            record = qualifier_observation(record)
            self.ajouter(record.get('nom'), record.get('id'),
                         record.get('url_geny') or record.get('source_url'), 'SHEETS_SOURCE_GENY')
        for folder in ('historiques', 'historiques_partiels'):
            for path in (self.cache/folder).glob('*/historique_geny.json'):
                doc = load(path, {}) or {}
                ident = path.parent.name
                if str(doc.get('identifiant_cheval', ident)) != ident:
                    continue
                if folder == 'historiques_partiels' and doc.get('identite_verifiee') is not True:
                    continue
                meta = journal.get(ident, {})
                url = doc.get('source_url')
                name = doc.get('nom') or meta.get('nom')
                if not url and meta.get('statut') in ('COMPLET', 'PARTIEL') and isinstance(doc.get('performances'), list):
                    # Anciennes captures du collecteur Geny, rangées par ID.
                    url = 'https://www.geny.com/cheval/'+ident
                self.ajouter(name, ident, url, 'CAPTURE_GENY')
        for path in sorted((self.cache/'manifestes').glob('GENY-*.json')):
            for block in (load(path, {}) or {}).get('courses', []):
                if block.get('course_id') != path.stem:
                    continue
                for horse in block.get('partants', []):
                    ident = str(horse.get('id', ''))
                    self.ajouter(horse.get('nom'), ident, horse.get('url_geny'),
                                 'MANIFESTE_GENY', path.stem, horse.get('numero'))
        from .historiques_incrementaux import instant
        proofs = [(path.stem, load(path, {}) or {})
                  for path in (self.cache/'sources_geny/liens').glob('*.json')]
        proofs.extend((proof['engagement'], proof) for proof in courses_verifiees())
        for engagement, proof in proofs:
            stamp = instant(proof.get('capture_utc'))
            source = urlparse(proof.get('source_url') or '')
            match = re.match(r'/course/(\d+)(?:\D|$)', source.path)
            if (proof.get('engagement') != engagement or proof.get('http') != 200 or not stamp
                    or stamp > datetime.now(timezone.utc) or source.scheme != 'https'
                    or source.hostname not in ('geny.com', 'www.geny.com')
                    or not match or match[1] != str(proof.get('course_geny_id'))):
                continue
            for number, horse in proof.get('chevaux', {}).items():
                self.ajouter(horse.get('nom'), horse.get('id'), horse.get('url_geny'),
                             'LIENS_COURSE_GENY', 'GENY-'+match[1], number, fiche=horse)
        for folder in sorted((self.cache/'diagnostics/decouverte').glob('*')):
            pages = set()
            for attempt in load(folder/'tentatives.json', []) or []:
                source = urlparse(attempt.get('url') or '')
                match = re.match(r'/course/(\d+)(?:\D|$)', source.path)
                if (attempt.get('http') == 200 and match and source.scheme == 'https'
                        and source.hostname in ('geny.com', 'www.geny.com')):
                    pages.add(match[1])
            if not pages:
                continue
            rows = load(folder/'lignes_tableau.json', []) or []
            numbers = defaultdict(set)
            for row in rows:
                cells = row.get('cells', [])
                if len(cells) > 2 and str(cells[0]).isdigit():
                    numbers[nom_normalise(cells[2])].add(str(cells[0]))
            for path in sorted(folder.glob('clic_*.json')):
                click = load(path, {}) or {}
                url = click.get('url') or ''
                match = re.fullmatch(r'/cheval/(\d+)(?:-[^/]+)?/course/(\d+)/?', urlparse(url).path)
                name = click.get('nom')
                found = numbers[nom_normalise(name)]
                if (match and match[2] in pages and len(found) == 1
                        and click.get('mode') in ('nouvel_onglet', 'meme_onglet')):
                    self.ajouter(name, match[1], url, 'ARCHIVE_CLIC_GENY', 'GENY-'+match[2], next(iter(found)))
        for path in sorted((self.cache/'sources_geny/identites').glob('*.json')):
            proof = load(path, {}) or {}
            if preuve_resolution_valide(proof):
                horse = proof['geny']
                self.ajouter(horse['nom'], horse['id'], horse['url_geny'], proof['preuve'], fiche=horse)
                if proof.get('id_pmu'):
                    self.pmu[str(proof['id_pmu'])].add(str(horse['id']))
                year = proof.get('annee_naissance_pmu') or horse.get('annee_naissance_pmu')
                if year:
                    key = nom_normalise(proof['nom_attendu'])
                    self.annees[(key, int(year))].add(str(horse['id']))
                    self.annees_par_id[(key, str(horse['id']))].add(int(year))
                for candidate in horse.get('homonymes', []):
                    if nom_normalise(candidate.get('nom')) == nom_normalise(horse['nom']):
                        self.ajouter(candidate.get('nom'), candidate.get('id'), candidate.get('url_geny'),
                                     'RECHERCHE_GENY_NOM_AMBIGU')

    def ajouter(self, nom, ident, url, preuve, course=None, numero=None, *, fiche=None):
        key = nom_normalise(nom)
        ident = str(ident or '')
        if not key or not re.fullmatch(r'\d{1,15}', ident) or source_identifiant(ident, url) != 'geny':
            return
        self.noms_par_id[ident].add(key)
        self.noms[key].setdefault(ident, {
            'id': ident, 'nom': nom, 'url_geny': url.replace('https://geny.com/', 'https://www.geny.com/'),
            'preuve': preuve})
        keys = {key}
        if fiche and nom_geny_concordant(fiche.get('nom_pmu'), fiche):
            alias = nom_normalise(fiche['nom_pmu'])
            self.noms[alias][ident] = {**self.noms[key][ident], 'nom': nom,
                                      'nationalite_geny': fiche.get('nationalite_geny'), 'nom_pmu': fiche['nom_pmu']}
            keys.add(alias)
        if course and numero is not None:
            for name in keys:
                self.contextes[(name, course, str(numero))].add(ident)

    def resoudre(self, nom, course=None, numero=None, *, nom_repris=False, annee=None, id_pmu=None):
        key = nom_normalise(nom)
        candidates = self.noms.get(key, {})
        context = self.contextes.get((key, course, str(numero)), set())
        pmu_ids = self.pmu.get(str(id_pmu), set())
        annee_ids = self.annees.get((key, annee), set())
        if pmu_ids:
            confirmed = pmu_ids.intersection(candidates)
            if context:
                confirmed &= context
            if annee_ids:
                confirmed &= annee_ids
            if len(confirmed) == 1 and len(pmu_ids) == 1:
                return candidates[next(iter(confirmed))], 'ID_PMU_VERIFIE'
            return {}, 'NOM_AMBIGU'
        if len(candidates) > 1 or nom_repris:
            confirmed = context & annee_ids if context and annee_ids else context or annee_ids
            if len(confirmed) == 1:
                ident = next(iter(confirmed))
                if len(self.noms_par_id[ident]) == 1:
                    return candidates[ident], 'NOM_AMBIGU_ID_CONFIRME'
        elif len(candidates) == 1:
            ident = next(iter(candidates))
            known_years = self.annees_par_id.get((key, ident), set())
            if len(self.noms_par_id[ident]) == 1 and (not annee or not known_years or annee in known_years):
                return candidates[ident], ('NOM_EXACT_ET_ID_GENY_CONFIRME' if context
                                           else 'NOM_EXACT_UNIQUE')
        return {}, 'NOM_AMBIGU' if candidates or nom_repris else 'NON_ASSOCIE'


def preuve_resolution_valide(proof):
    from .historiques_incrementaux import instant
    horse = proof.get('geny') or {}
    ident = str(horse.get('id', ''))
    stamp = instant(proof.get('resolution_utc'))
    return (proof.get('preuve') in ('RECHERCHE_GENY_NOM_EXACT', 'FICHE_GENY_VERIFIEE', 'COURSE_GENY_VERIFIEE')
            and stamp and stamp <= datetime.now(timezone.utc)
            and re.fullmatch(r'\d{4,15}', ident)
            and source_identifiant(ident, horse.get('url_geny')) == 'geny'
            and bool(nom_normalise(horse.get('nom')))
            and nom_geny_concordant(proof.get('nom_attendu'), horse))


def statut_tentative(motif):
    from dashboard.trot_analytics.correspondance_geny import AMBIGUE, BLOQUEE, NON_TROUVEE

    if motif == 'RECHERCHE_GENY_SANS_NOM_EXACT':
        return NON_TROUVEE
    if motif in ('RECHERCHE_GENY_NOM_AMBIGU', 'NOM_NUMERO_OU_IDENTIFIANT_NON_CONCORDANT',
                 'CONFLIT_PREUVE_ARCHIVEE', 'NOM_FICHE_GENY_NON_CONCORDANT'):
        return AMBIGUE
    return BLOQUEE


def memoriser_tentative(horse, report, stamp, *, acces, refus=None):
    """Journaliser une tentative d'identité dans la file durable existante."""
    if horse.get('geny') and source_identifiant(horse['geny'].get('id'), horse['geny'].get('url_geny')) == 'geny':
        return
    motif = report.get('statut')
    if not (acces or refus or motif in ('RECHERCHE_GENY_SANS_NOM_EXACT', 'RECHERCHE_GENY_NOM_AMBIGU',
                                        'RECHERCHE_GENY_NON_AUTORISEE')):
        return
    motif = motif or ('ACCES_GENY_' + refus if refus else 'EXECUTION_GENY_INTERROMPUE')
    horse['recherche_identite_geny'] = {
        'statut': statut_tentative(motif), 'motif': motif,
        'utc': stamp, 'reprise_utc': horse.get('prochain_essai_utc'),
    }


class TentativesGeny:
    """Relecture des preuves des deux files par contexte ou identifiant PMU."""

    def __init__(self, cache, now):
        from .echeances_production import instant, lire

        self.contextes = {}
        self.pmu = {}
        for path in ('collecte_incrementale/etat.json', 'rattrapage_historiques/etat.json'):
            for horse in lire(Path(cache) / path).get('chevaux', {}).values():
                name = nom_normalise(horse.get('nom'))
                record = horse.get('recherche_identite_geny')
                if not record:
                    old = horse.get('dernier_echec_collecte') or {}
                    motif = old.get('statut')
                    if motif not in ('RECHERCHE_GENY_NOM_AMBIGU', 'RECHERCHE_GENY_SANS_NOM_EXACT',
                                      'RECHERCHE_GENY_INDISPONIBLE', 'RECHERCHE_GENY_NON_INTERPRETABLE',
                                      'NOM_FICHE_GENY_NON_CONCORDANT'):
                        continue
                    record = {'statut': statut_tentative(motif), 'motif': motif, 'utc': old.get('utc'),
                              'reprise_utc': horse.get('prochain_essai_utc')}
                stamp = instant(record.get('utc'))
                if not name or not stamp or stamp > now:
                    continue
                context = (horse.get('engagement'), str(horse.get('numero') or ''), name)
                if all(context):
                    self._ajouter(self.contextes, context, stamp, record)
                if horse.get('id_pmu'):
                    self._ajouter(self.pmu, (str(horse['id_pmu']), name), stamp, record)

    @staticmethod
    def _ajouter(index, key, stamp, record):
        previous = index.get(key)
        if previous is None or stamp > previous[0]:
            index[key] = (stamp, record)

    def retrouver(self, engagement, numero, nom, id_pmu):
        name = nom_normalise(nom)
        records = tuple(item for item in (
            self.contextes.get((engagement, str(numero), name)),
            self.pmu.get((str(id_pmu), name)),
        ) if item)
        return max(records, key=lambda item: item[0])[1] if records else {}



def champs_correspondance_geny(tentative, pmu_id, geny_id, methode):
    from dashboard.trot_analytics.correspondance_geny import AMBIGUE, CHAMP, CONFIRMEE, NON_EFFECTUEE, NON_TROUVEE

    if geny_id:
        statut, motif = CONFIRMEE, ''
    elif tentative and (methode != 'NOM_AMBIGU' or tentative['statut'] != NON_TROUVEE):
        statut, motif = tentative['statut'], tentative.get('motif', '')
    elif methode == 'NOM_AMBIGU':
        statut, motif = AMBIGUE, methode
    else:
        statut, motif = NON_EFFECTUEE, ''
    details = [motif] if motif else []
    if tentative and statut == tentative.get('statut'):
        details.extend(f'{label} {tentative[key]}' for label, key in (
            ('Contrôle UTC', 'utc'), ('Reprise UTC', 'reprise_utc')) if tentative.get(key))
    return {CHAMP: statut, '_note_correspondance_geny': '\n'.join(details),
            '_id_pmu_correspondance': pmu_id, '_id_geny_correspondance': geny_id}
