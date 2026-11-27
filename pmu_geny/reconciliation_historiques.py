"""Rapprocher les preuves Geny et le registre courant, sans modifier les archives."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
import re

from dashboard.trot_analytics.correspondance_geny import AMBIGUE, CHAMP, CONFIRMEE
from dashboard.trot_analytics.dates import meme_date_sheets
from .controle_historique import classifier
from .controle_sync_sheets import cle_sportive
from .historiques_incrementaux import course_geny_connue, instant, lire
from .identites_chevaux import (IndexGeny, TentativesGeny, canoniser_ligne,
                                champs_correspondance_geny, qualifier_observation,
                                source_identifiant)
from .liaison_chevaux_v22 import nom_normalise

CHAMPS_HISTORIQUE = frozenset({
    'historique_statut', 'historique_nb_courses_datees', 'historique_maj_utc',
})
COURSE_KEY = re.compile(r'(\d{4}-\d{2}-\d{2})\|[^|]+\|(R\d+C\d+)')


class ReconciliationHistoriques:
    def __init__(self, cache, historique_publie, *, now=None):
        self.cache = cache
        self.now = now or datetime.now(timezone.utc)
        self.index = IndexGeny(cache)
        self.tentatives = TentativesGeny(cache, self.now)
        self.course = lru_cache(maxsize=None)(self.course)
        self.historique = lru_cache(maxsize=None)(self.historique)
        self.journal = lire(cache/'etat_persistant.json').get('chevaux', {})
        self.publications = defaultdict(set)
        for original in historique_publie:
            row = canoniser_ligne(original)
            ident = str(row.get('identifiant_cheval') or '')
            nom = row.get('cheval')
            url = row.get('url_source_geny') or row.get('source_url')
            if ident != str(original.get('identifiant_cheval') or ''):
                url = qualifier_observation({'id': original.get('identifiant_cheval'),
                    'nom': nom, 'source_url': original.get('source_url')}).get('url_geny')
            self.index.ajouter(nom, ident, url, 'SHEETS_SOURCE_GENY')
            key = cle_sportive(row)
            if key and row.get('cle_performance'):
                self.publications[ident].add((nom_normalise(nom), key))

    def course(self, engagement):
        return (course_geny_connue(self.cache, engagement),
                lire(self.cache/'partants_actuels'/f'{engagement}.json').get('chevaux', {}))

    def historique(self, ident):
        doc = lire(self.cache/'historiques'/ident/'historique_geny.json')
        partial = lire(self.cache/'historiques_partiels'/ident/'historique_geny.json')
        journal = self.journal.get(ident, {})
        nom = doc.get('nom') or journal.get('nom') or partial.get('nom')
        if nom and nom_normalise(nom) not in self.index.noms_par_id[ident]:
            return ('GENY_IDENTIFIE_CARRIERE_MANQUANTE', 0, '',
                    'Nom de la capture en conflit avec l’identité Geny.')
        keys = {key for name, key in self.publications.get(ident, ())
                if name in self.index.noms_par_id[ident]}
        stamp = instant(doc.get('extrait_utc'))
        total = doc.get('nombre_annonce_geny')
        valide = (doc.get('statut') == 'COMPLET' and stamp and stamp <= self.now
                  and type(total) is int and total >= 0
                  and str(doc.get('identifiant_cheval', ident)) == ident
                  and source_identifiant(ident, doc.get('source_url')) == 'geny'
                  and classifier(doc)[0] == 'COMPLET')
        if valide:
            attendues = {cle_sportive({'identifiant_cheval': ident,
                'date_course_historique': perf['date'], **perf}) for perf in doc['performances']}
            if len(attendues) != total:
                return ('HISTO_PARTIEL_GENY', len(keys), stamp.isoformat(),
                        f'{len(attendues)}/{total} signatures sportives distinctes dans la capture Geny. '
                        'Vérifier les variantes source avant toute nouvelle publication.')
            manquantes = attendues - keys
            if not manquantes:
                return ('HISTO_OK_NOM_ID', len(keys), stamp.isoformat(),
                        f'Capture Geny validée et relue dans Sheets ({total}/{total}).')
            return ('HISTO_PUBLICATION_EN_ATTENTE', len(keys), stamp.isoformat(),
                    f'Capture Geny validée le {stamp.isoformat()}. '
                    f'{len(attendues & keys)}/{total} performances de la capture relues dans Sheets. Reprendre la publication.')
        partielle = (partial.get('identite_verifiee') is True
                     and str(partial.get('identifiant_cheval', ident)) == ident
                     and source_identifiant(ident, partial.get('source_url')) == 'geny'
                     and (partielle_utc := instant(partial.get('extrait_utc')))
                     and partielle_utc <= self.now and bool(partial.get('performances')))
        if keys or partielle:
            return ('HISTO_PARTIEL_GENY', len(keys), partielle_utc.isoformat() if partielle else '',
                    'Vérifier le total source et les champs obligatoires de la carrière.')
        return ('GENY_IDENTIFIE_CARRIERE_MANQUANTE', 0, '',
                'Identité confirmée. Collecter la carrière via la file existante.')

    def diagnostiquer(self, row, *, nom_repris=False):
        key, number = row.get('course_key', ''), str(row.get('numero') or '')
        name = row.get('cheval', '')
        match = COURSE_KEY.fullmatch(key)
        if not match or not number or not nom_normalise(name):
            return {}
        date, code = match.groups()
        engagement = f'{date}_{code}'
        cid, participants = self.course(engagement)
        pmu = participants.get(number, {})
        if nom_normalise(pmu.get('nom')) != nom_normalise(name):
            pmu = {}
        pmu_id = pmu.get('id_pmu') or row.get('_id_pmu_correspondance')
        age = str(pmu.get('age_ans') or row.get('age_ans') or '')
        year = int(date[:4]) - int(age) if age.isdigit() else None
        link, method = self.index.resoudre(name, cid, number, nom_repris=nom_repris,
                                           annee=year, id_pmu=pmu_id)
        ident = link.get('id')
        tentative = self.tentatives.retrouver(engagement, number, name, pmu_id)
        result = champs_correspondance_geny(tentative, pmu_id, ident, method)
        if ident:
            statut, count, stamp, action = self.historique(ident)
            if statut == 'HISTO_OK_NOM_ID' and method == 'NOM_EXACT_UNIQUE':
                statut = 'HISTO_OK_NOM'
            reason = f"Geny {ident} · {method} · {link['preuve']}\n{link['url_geny']}"
        else:
            statut = 'HISTO_AMBIGU' if result[CHAMP] == AMBIGUE else 'HISTO_NON_COLLECTE'
            count, stamp = 0, ''
            reason = result['_note_correspondance_geny']
            action = ('Contrôler les candidats et le contexte PMU avant la collecte.'
                      if result[CHAMP] == AMBIGUE else
                      'Reprendre la résolution dans la file existante à partir des preuves de course disponibles.')
        result.update(course_key=key, numero=number, historique_statut=statut,
                      historique_nb_courses_datees=count, historique_maj_utc=stamp,
                      _note_correspondance_geny='\n'.join(filter(None, (reason, action))))
        return result

    def participations(self, existing, incoming):
        def cle(row):
            return f"{row.get('course_key')}|{row.get('numero')}"
        observed = Counter(cle(row) for row in existing if row.get('cheval'))
        before = {cle(row): row for row in existing if row.get('cheval')}
        rows = dict(before)
        for key, row in incoming.items():
            if row.get('cheval'):
                rows[key] = {**rows.get(key, {}), **row}
        names = Counter((r.get('course_key'), nom_normalise(r.get('cheval'))) for r in rows.values())
        diagnostics = {}
        anomalies = Counter()
        for key, row in rows.items():
            if observed[key] > 1:
                anomalies['cle_participation_ambigue'] += 1
                continue
            repeated = names[row.get('course_key'), nom_normalise(row.get('cheval'))] > 1
            if result := self.diagnostiquer(row, nom_repris=repeated):
                diagnostics[key] = result
        for key, result in diagnostics.items():
            if observed[key] != 1:
                continue
            compter_ecart(anomalies, before[key], result)
        return diagnostics, anomalies


    def stock_entry(self, horse):
        from .rattrapage_historiques import contexte_verifiable, engagement_canonique

        name = horse.get('nom', '')
        engagement = engagement_canonique(horse.get('engagement'))
        number = str(horse.get('numero') or '')
        ident = str(horse.get('id') or '')
        diagnostic = {}
        if contexte_verifiable(horse):
            day, code = engagement.split('_')
            diagnostic = self.diagnostiquer({'course_key': f'{day}|Stock|{code}',
                'numero': number, 'cheval': name, '_id_pmu_correspondance': horse.get('id_pmu')})
        geny = horse.get('geny') or {}
        ident = ident or str(geny.get('id') or '')
        if (not diagnostic.get('_id_geny_correspondance') and not horse.get('conflit_identite')
                and diagnostic.get(CHAMP) != AMBIGUE and source_identifiant(ident, geny.get('url_geny')) == 'geny'
                and ident in self.index.noms[nom_normalise(name)]):
            status, count, stamp, action = self.historique(ident)
            diagnostic = {CHAMP: CONFIRMEE, 'historique_statut': status,
                          'historique_nb_courses_datees': count, 'historique_maj_utc': stamp,
                          '_id_geny_correspondance': ident, '_note_correspondance_geny': action}
        if diagnostic:
            return diagnostic
        tentative = self.tentatives.retrouver(engagement, number, name, horse.get('id_pmu'))
        return champs_correspondance_geny(tentative, horse.get('id_pmu'), None,
                                           'NOM_AMBIGU' if horse.get('conflit_identite') else None)

    def stock(self):
        from .rattrapage_historiques import engagement_canonique

        targets = lire(self.cache/'rattrapage_historiques/etat.json').get('chevaux', {})
        return {key: {'nom': horse.get('nom', ''), 'engagement': engagement_canonique(horse.get('engagement')),
                      'numero': str(horse.get('numero') or ''),
                      'cible_equivalente_a': horse.get('cible_equivalente_a'), **self.stock_entry(horse)}
                for key, horse in targets.items()}


def compter_ecart(counts, ancien, courant):
    if ancien.get(CHAMP) != courant[CHAMP]:
        counts['correspondance'] += 1
    if ancien.get('historique_statut') != courant['historique_statut']:
        counts['statut_historique'] += 1
    if str(ancien.get('historique_nb_courses_datees') or '0') != str(courant['historique_nb_courses_datees']):
        counts['nombre_performances'] += 1
    if not meme_date_sheets('historique_maj_utc', ancien.get('historique_maj_utc') or '',
                            courant['historique_maj_utc']):
        counts['date_capture'] += 1
    if (courant[CHAMP] == CONFIRMEE and courant['historique_nb_courses_datees'] > 0
            and ancien.get('historique_statut') == 'HISTO_NON_COLLECTE'):
        counts['historique_publie_affiche_absent'] += 1
