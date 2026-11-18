"""Historique des notifications : appuyer sur une notif du téléphone ouvre une page qui les affiche."""
import datetime as dt
import secrets

import db
from config import TZ

KEEP = 50


def save(embeds: list, title: str, body: str) -> str:
    """Garde uniquement les données des cards (pas d'images) et renvoie l'identifiant."""
    nid = dt.datetime.now(TZ).strftime("%Y%m%d%H%M%S") + secrets.token_hex(3)
    # la card déclencheuse en premier, puis l'autre option de trajet, puis le reste dans l'ordre
    main = next((e for e in embeds if e.get("_notif")), None)
    alts = [e for e in embeds if (e.get("_data") or {}).get("alt")]
    embeds = ([main] if main else []) + alts + [e for e in embeds if e is not main and e not in alts]
    blocks = []
    for e in embeds:
        if e.get("_data"):
            blocks.append(e["_data"])
        else:
            blocks.append({"type": "text", "card": {k: v for k, v in e.items() if not k.startswith("_")}})
    lst = db.get("notifs", [])
    lst.insert(0, {"id": nid, "ts": dt.datetime.now(TZ).isoformat(timespec="minutes"),
                   "title": title, "body": body, "blocks": blocks})
    db.put("notifs", lst[:KEEP])
    return nid


def get(nid: str) -> dict | None:
    return next((n for n in db.get("notifs", []) if n["id"] == nid), None)


def latest(n: int = 20) -> list:
    return db.get("notifs", [])[:n]
