"""Configuration : valeurs de la page /config (stockées en base) > .env > défaut."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TZ = ZoneInfo("Europe/Paris")
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data.db"))
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))

# (clé, libellé, type, défaut, aide) — une clé commençant par "__" = titre de section
FIELDS = [
    ("__Emploi du temps & Discord", "", "", "", ""),
    ("ICS_URL", "Lien .ics de l'emploi du temps", "secret", "", "webcal:// accepté"),
    ("DISCORD_WEBHOOK_URL", "URL du webhook Discord", "secret", "",
     "Salon › Modifier › Intégrations › Webhooks › Nouveau webhook › Copier l'URL"),
    ("PRIM_API_KEY", "Clé API PRIM (IDFM)", "secret", "",
     "prim.iledefrance-mobilites.fr › abonnement « Calculateur IDFM – Accès générique (v2) »"),
    ("__Trajet", "", "", "", ""),
    ("EARLY_BEFORE", "Cours tôt : 1er cours avant", "time", "09:00", "ex. 09:00 → un cours à 8h ou 8h30 = Trappes"),
    ("EARLY_ORIGIN", "Gare si cours tôt", "choice:Trappes|Coignières", "Trappes", ""),
    ("LATE_ORIGIN", "Gare si cours plus tard", "choice:Coignières|Trappes", "Coignières", ""),
    ("LATE_AHEAD", "Trains d'avance si cours plus tard", "int", "1", "0 = le dernier train qui passe"),
    ("USUAL_TRAPPES", "Train habituel à Trappes", "time", "07:16", "pris en priorité s'il arrive à temps (vide = auto)"),
    ("USUAL_COIGNIERES", "Train habituel à Coignières", "time", "", "vide = auto"),
    ("ACCESS_COIGNIERES", "Maison → quai Coignières (min)", "int", "18", "à pied + marge"),
    ("ACCESS_TRAPPES", "Maison → quai Trappes (min)", "int", "22", "voiture + parking"),
    ("MARGIN", "Marge avant le cours (min)", "int", "5", "le train habituel peut entamer cette marge"),
    ("__Arrivée à l'école", "", "", "", ""),
    ("SCHOOL_NAME", "Nom de l'école", "text", "ECE Paris", ""),
    ("SCHOOL_ADDRESS", "Adresse de l'école", "text", "10 rue Sextius Michel, 75015 Paris",
     "utilisée pour les itinéraires de secours"),
    ("METRO_STOP", "Station d'arrivée (métro 6)", "text", "Bir-Hakeim", "nom ou ID stop_area:…"),
    ("TRANSFER_MONTPARNASSE", "Correspondance train → métro 6 (min)", "int", "6", "marche dans la gare Montparnasse"),
    ("METRO_EST", "Métro jusqu'à la station, attente comprise (min)", "int", "12", "sert à choisir le bon train"),
    ("WALK_END", "Station → école à pied (min)", "int", "6", ""),
    ("__Notifications", "", "", "", ""),
    ("DELAY_ALERT", "Alerte à partir de (min de retard)", "int", "3", ""),
    ("CHECK_BEFORE", "Surveiller X min avant de partir", "int", "45", ""),
    ("RECAP_HOUR", "Heure du récap du lendemain", "time", "20:00", ""),
    ("VIRTUAL_NOTIFY", "Rappel cours en ligne (min avant)", "int", "5", "pour penser à se mettre présent"),
    ("ICS_REFRESH_MIN", "Actualisation de l'EDT (min)", "int", "15", ""),
    ("HA_WEBHOOK_URL", "Webhook Home Assistant (optionnel)", "text", "",
     "ex : http://IP_HA:8123/api/webhook/train_retard"),
    ("__Avancé", "", "", "", ""),
    ("WEB_TOKEN", "Mot de passe du site (optionnel)", "secret", "", "accès ensuite via ?token=…"),
    ("STOP_COIGNIERES", "ID gare Coignières", "text", "", "vide = détection auto"),
    ("STOP_TRAPPES", "ID gare Trappes", "text", "", "vide = détection auto"),
    ("STOP_MONTPARNASSE", "ID gare Montparnasse", "text", "", "vide = détection auto"),
]
_DEFAULTS = {k: d for k, _, t, d, _ in FIELDS if t}
_TYPES = {k: t for k, _, t, _, _ in FIELDS if t}
REQUIRED = ("ICS_URL", "DISCORD_WEBHOOK_URL", "PRIM_API_KEY")


def get(key: str):
    import db  # import tardif (db importe config)
    saved = db.get("settings", {})
    if key in saved and (saved[key] or _TYPES.get(key) in ("time", "text")):
        v = saved[key]  # une valeur vidée volontairement reste vide
    else:
        v = os.getenv(key) or _DEFAULTS.get(key, "")
    v = str(v).strip().strip('"\'')
    if key == "ICS_URL" and v.startswith("webcal://"):
        v = "https://" + v[len("webcal://"):]
    if _TYPES.get(key) == "int":
        try:
            return int(v)
        except ValueError:
            return int(_DEFAULTS[key])
    return v


def save(values: dict):
    import db
    saved = db.get("settings", {})
    for k, v in values.items():
        if k in _TYPES:
            saved[k] = str(v).strip()
    db.put("settings", saved)


def missing() -> list[str]:
    out = []
    for k in REQUIRED:
        v = get(k)
        if not v or "..." in v or (k != "PRIM_API_KEY" and not v.startswith("http")):
            out.append(k)
    return out


def origins():
    return [
        {"name": "Coignières", "query": "Coignières", "id": get("STOP_COIGNIERES"),
         "access": get("ACCESS_COIGNIERES"), "emoji": "🚶", "usual": get("USUAL_COIGNIERES")},
        {"name": "Trappes", "query": "Trappes", "id": get("STOP_TRAPPES"),
         "access": get("ACCESS_TRAPPES"), "emoji": "🚗", "usual": get("USUAL_TRAPPES")},
    ]


def dest():
    return {"name": "Montparnasse", "query": "Paris Montparnasse", "id": get("STOP_MONTPARNASSE")}


def preferred_origin(first_start: str) -> str:
    return get("EARLY_ORIGIN") if is_early(first_start) else get("LATE_ORIGIN")


def is_early(first_start: str) -> bool:
    return first_start < (get("EARLY_BEFORE") or "09:00")


def school_delay() -> int:
    """Minutes entre l'arrivée du train à Montparnasse et l'arrivée à l'école."""
    return get("TRANSFER_MONTPARNASSE") + get("METRO_EST") + get("WALK_END")


def metro_stop():
    q = get("METRO_STOP") or "Bir-Hakeim"
    return {"name": q, "query": q, "id": q if q.startswith("stop_area") else ""}


def school():
    return {"name": get("SCHOOL_NAME") or "École", "query": get("SCHOOL_ADDRESS")}
