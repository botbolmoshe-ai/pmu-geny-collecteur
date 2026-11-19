"""Dates affichées et conversion des valeurs numériques de Google Sheets."""
from datetime import date, datetime, timedelta, timezone
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
        try:
            return (date.fromisoformat(str(value)) - EPOCH.date()).days
        except ValueError:
            return value
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
    try:
        return date.fromisoformat(str(value)).strftime("%d/%m/%Y")
    except ValueError:
        return value


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
