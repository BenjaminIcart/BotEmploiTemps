import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

TZ = ZoneInfo("Europe/Paris")

# --- Secrets ---
ICS_URL = os.environ["ICS_URL"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
PRIM_API_KEY = os.environ["PRIM_API_KEY"]
HA_WEBHOOK_URL = os.getenv("HA_WEBHOOK_URL", "")  # optionnel
WEB_TOKEN = os.getenv("WEB_TOKEN", "")  # optionnel : ?token=xxx pour accéder au site

# --- Trajet ---
# access = minutes entre chez toi et le quai (trajet + marge)
ORIGINS = [
    {"name": "Coignières", "query": "Coignières", "id": os.getenv("STOP_COIGNIERES", ""),
     "access": int(os.getenv("ACCESS_COIGNIERES", "18")), "emoji": "🚶"},
    {"name": "Trappes", "query": "Trappes", "id": os.getenv("STOP_TRAPPES", ""),
     "access": int(os.getenv("ACCESS_TRAPPES", "22")), "emoji": "🚗"},
]
DEST = {"name": "Montparnasse", "query": "Paris Montparnasse", "id": os.getenv("STOP_MONTPARNASSE", "")}

WALK_SCHOOL = int(os.getenv("WALK_SCHOOL", "15"))   # gare -> lycée
MARGIN = int(os.getenv("MARGIN", "5"))              # marge avant le début du cours
DELAY_ALERT = int(os.getenv("DELAY_ALERT", "3"))    # retard (min) à partir duquel on alerte
CHECK_BEFORE = int(os.getenv("CHECK_BEFORE", "45")) # surveillance à partir de X min avant le départ de chez toi
ICS_REFRESH_MIN = int(os.getenv("ICS_REFRESH_MIN", "15"))
RECAP_HOUR = os.getenv("RECAP_HOUR", "20:00")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data.db"))
