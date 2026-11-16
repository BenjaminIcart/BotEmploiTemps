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
    ("ACCESS_COIGNIERES", "Maison → quai Coignières (min)", "int", "18", "à pied + marge"),
    ("ACCESS_TRAPPES", "Maison → quai Trappes (min)", "int", "22", "voiture + parking"),
    ("WALK_SCHOOL", "Montparnasse → lycée (min)", "int", "15", ""),
    ("MARGIN", "Marge avant le cours (min)", "int", "5", ""),
    ("__Notifications", "", "", "", ""),
    ("DELAY_ALERT", "Alerte à partir de (min de retard)", "int", "3", ""),
    ("CHECK_BEFORE", "Surveiller X min avant de partir", "int", "45", ""),
    ("RECAP_HOUR", "Heure du récap du lendemain", "time", "20:00", ""),
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
    v = db.get("settings", {}).get(key) or os.getenv(key) or _DEFAULTS.get(key, "")
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
         "access": get("ACCESS_COIGNIERES"), "emoji": "🚶"},
        {"name": "Trappes", "query": "Trappes", "id": get("STOP_TRAPPES"),
         "access": get("ACCESS_TRAPPES"), "emoji": "🚗"},
    ]


def dest():
    return {"name": "Montparnasse", "query": "Paris Montparnasse", "id": get("STOP_MONTPARNASSE")}
