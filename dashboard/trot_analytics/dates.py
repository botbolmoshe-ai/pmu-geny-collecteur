"""Dates affichées et conversion des valeurs numériques de Google Sheets."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
EPOCH = datetime(1899, 12, 30)
DATE_PATTERN = "dd/mm/yyyy"
DATETIME_PATTERN = DATE_PATTERN + " hh:mm"

DATE_FIELDS = {"date_course", "date_course_historique", "Date", "Date du relevé"}
PARIS_FIELDS = {"heure_depart_paris", "Départ (Paris)"}
UTC_FIELDS = {"Relevé UTC"}


def date_kind(field):
    if field in DATE_FIELDS:
        return "DATE"
    if field in PARIS_FIELDS or field in UTC_FIELDS or field.endswith(("_utc", " UTC")):
        return "DATE_TIME"
    return None


def instant_iso(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp if stamp.tzinfo is not None else None
    except (OverflowError, ValueError):
        return None


def vers_nombre(field, value):
    kind = date_kind(field)
    if kind == "DATE":
        parsed = lire_date(value)
        return (parsed - EPOCH.date()).days if parsed else value
    stamp = instant_iso(value) if kind == "DATE_TIME" else None
    if stamp is None:
        return value
    zone = PARIS if field in PARIS_FIELDS else timezone.utc
    wall = stamp.astimezone(zone).replace(tzinfo=None)
    delta = wall - EPOCH
    return delta.days + (delta.seconds * 1_000_000 + delta.microseconds) / 86_400_000_000


def depuis_nombre(field, value):
    kind = date_kind(field)
    if kind is None or type(value) not in (int, float):
        return value
    try:
        wall = EPOCH + timedelta(days=value)
    except (OverflowError, ValueError):
        return value
    if kind == "DATE":
        return wall.date().isoformat()
    zone = PARIS if field in PARIS_FIELDS else timezone.utc
    stamp = wall.replace(tzinfo=zone)
    if zone == PARIS and stamp.utcoffset() != stamp.replace(fold=1).utcoffset():
        # Une ancienne série locale dans l'heure sautée ou répétée ne prouve aucun instant.
        return value
    return stamp.isoformat()


def vers_cellule_operationnelle(field, value):
    if date_kind(field) != "DATE_TIME":
        return vers_nombre(field, value)
    stamp = instant_iso(value)
    if stamp is None:
        return ""
    zone = PARIS if field in PARIS_FIELDS else timezone.utc
    return stamp.astimezone(zone).isoformat()


def afficher_date(value):
    parsed = lire_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else value


def afficher_instant(value, zone=PARIS):
    stamp = instant_iso(value)
    return stamp.astimezone(zone).strftime("%d/%m/%Y %H:%M") if stamp else ""


def meme_date_sheets(field, left, right):
    if date_kind(field) == "DATE_TIME":
        a = instant_iso(depuis_nombre(field, left))
        b = instant_iso(depuis_nombre(field, right))
        if a and b:
            # Le nombre de jours peut perdre quelques microsecondes côté Sheets.
            return abs(a - b) <= timedelta(microseconds=10)
        return left == right
    return vers_nombre(field, left) == vers_nombre(field, right)


TIME_PATTERN = "hh:mm"
DISPLAY_PREFIX = "Paris · "


def lire_date(value):
    if not isinstance(value, str):
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def lire_instant_consultation(value, zone):
    stamp = instant_iso(value)
    if stamp or not isinstance(value, str):
        return stamp
    for pattern in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            local = datetime.strptime(value, pattern).replace(tzinfo=zone)
        except ValueError:
            continue
        if local.utcoffset() == local.replace(fold=1).utcoffset():
            return local
    return None


def nombre_paris(value, *, utc=True):
    stamp = lire_instant_consultation(value, timezone.utc if utc else PARIS)
    if stamp is None:
        return value
    delta = stamp.astimezone(PARIS).replace(tzinfo=None) - EPOCH
    return delta / timedelta(days=1)


def afficher_source(value):
    """Projeter uniquement les segments datés de la provenance publiée."""
    import re

    if not isinstance(value, str) or not value.startswith(("https://", "http://")):
        return value
    # L’URL initiale est conservée intégralement, même si son chemin contient une date.
    url, separator, provenance = value.partition(" ")
    if not separator:
        return value
    instant = re.compile(r"(?<![\w/])\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
                         r"(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})(?![\w/])")
    def afficher_segment(match):
        display = afficher_instant(match[0])
        return display + " (Paris)" if display else match[0]

    provenance = instant.sub(afficher_segment, provenance)
    provenance = re.sub(r"(publié le )(\d{4}-\d{2}-\d{2})(?![\dT])",
                        lambda match: match[1] + afficher_date(match[2]), provenance)
    return url + separator + provenance


def indicateur_horodate(label):
    return isinstance(label, str) and label.endswith(" UTC")


def afficher_valeur_kpi(label, value):
    if indicateur_horodate(label) and type(value) in (int, float) and 20000 < value < 80000:
        return (EPOCH + timedelta(days=value)).strftime("%d/%m/%Y %H:%M")
    return afficher_instant(value) or value
