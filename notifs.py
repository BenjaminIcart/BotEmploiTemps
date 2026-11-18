"""Historique des notifications : appuyer sur une notif du téléphone ouvre ses images."""
import datetime as dt
import secrets
from pathlib import Path

import db
from config import BASE_DIR, TZ

DIR = BASE_DIR / "notifs"
KEEP = 40


def save(embeds: list, title: str, body: str) -> str:
    """Enregistre les cards (images sur disque) et renvoie l'identifiant de la notification."""
    DIR.mkdir(exist_ok=True)
    nid = dt.datetime.now(TZ).strftime("%Y%m%d%H%M%S") + secrets.token_hex(3)
    cards = []
    # la card qui a déclenché la notif (trajet, retard…) en premier
    embeds = sorted(embeds, key=lambda e: not e.get("_notif"))
    for i, e in enumerate(embeds):
        if e.get("_png"):
            name = f"{nid}_{i}.png"
            (DIR / name).write_bytes(e["_png"])
            cards.append({"png": name, "title": e.get("title", "")})
        else:
            cards.append({"card": {k: v for k, v in e.items() if not k.startswith("_")}})
    lst = db.get("notifs", [])
    lst.insert(0, {"id": nid, "ts": dt.datetime.now(TZ).isoformat(timespec="minutes"),
                   "title": title, "body": body, "cards": cards})
    for old in lst[KEEP:]:  # ménage
        for c in old["cards"]:
            if c.get("png"):
                (DIR / c["png"]).unlink(missing_ok=True)
    db.put("notifs", lst[:KEEP])
    return nid


def get(nid: str) -> dict | None:
    return next((n for n in db.get("notifs", []) if n["id"] == nid), None)


def latest(n: int = 20) -> list:
    return db.get("notifs", [])[:n]


def png_path(name: str) -> Path | None:
    p = DIR / Path(name).name
    return p if p.exists() and p.suffix == ".png" else None
