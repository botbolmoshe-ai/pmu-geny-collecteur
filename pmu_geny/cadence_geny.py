"""Cadence durable des deux files historiques, sous leur verrou de production."""
from datetime import timedelta, timezone
from email.utils import parsedate_to_datetime

from .echeances_production import instant, lire, sauver

INTERVALLE_NORMAL = 30
INTERVALLE_REPRISE = 60
VALIDATIONS_REPRISE = 10
TIMEOUT_COLLECTE = 240
MARGE_CHECKPOINT = 60
REFUS = {'ACCES_REFUSE_403': '403', 'ACCES_LIMITE_429': '429'}


def reprise_serveur(value, now):
    if not value:
        return None
    try:
        if value.strip().isdigit():
            return now + timedelta(seconds=int(value))
        deadline = parsedate_to_datetime(value)
        return deadline.replace(tzinfo=deadline.tzinfo or timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


class CadenceGeny:
    def __init__(self, cache):
        self.journal = cache / 'etat_persistant.json'
        journal = lire(self.journal)
        self.etat = journal.get('cadence_historiques', {})
        incident = (journal.get('dernier_blocage_geny') or {}).get('utc')
        if incident and incident != self.etat.get('dernier_incident_utc'):
            self.etat.update(reprise=True, validations_consecutives=0, dernier_incident_utc=incident)

    @property
    def intervalle(self):
        return INTERVALLE_REPRISE if self.etat.get('reprise') else INTERVALLE_NORMAL

    def delai(self, now):
        dates = (instant(self.etat.get(cle)) for cle in ('prochain_cheval_utc', 'reservation_expire_utc'))
        return max(0, (max((date for date in dates if date), default=now) - now).total_seconds())

    def _sauver(self):
        journal = lire(self.journal)
        journal.setdefault('version', 1)
        journal.setdefault('chevaux', {})
        journal['cadence_historiques'] = self.etat
        sauver(self.journal, journal)

    def reserver(self, now):
        # Si le processus s'interrompt, le prochain runner respecte aussi
        # la fin la plus tardive possible du sous-processus précédent.
        self.etat['reservation_expire_utc'] = (
            now + timedelta(seconds=TIMEOUT_COLLECTE + self.intervalle + MARGE_CHECKPOINT)).isoformat()
        self._sauver()

    def terminer(self, now, *, valide=None, refus=False):
        self.etat.pop('reservation_expire_utc', None)
        if refus:
            incidents = self.etat.get('incidents_sans_validation', 0) + 1
            self.etat.update(reprise=True, validations_consecutives=0,
                             dernier_incident_utc=now.isoformat(), incidents_sans_validation=incidents)
        elif self.etat.get('reprise') and valide is not None:
            validations = self.etat.get('validations_consecutives', 0) + 1 if valide else 0
            self.etat.update(reprise=validations < VALIDATIONS_REPRISE, validations_consecutives=validations)
        if valide:
            self.etat['incidents_sans_validation'] = 0
        self.etat['prochain_cheval_utc'] = (now + timedelta(seconds=self.intervalle)).isoformat()
        self._sauver()
