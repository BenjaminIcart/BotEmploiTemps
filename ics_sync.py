"""Récupère le .ics, le transforme en {jour: [cours]} et détecte les changements."""
import datetime as dt
import logging

import aiohttp
import icalendar
import recurring_ical_events

import db
import config as C
from config import TZ

log = logging.getLogger("ics")


def _to_local(v):
    if v.tzinfo is None:
        v = v.replace(tzinfo=TZ)
    return v.astimezone(TZ)


import re

TYPE_RE = re.compile(r"^[A-Z][A-Z0-9\-]{1,20}$")
PROF_RE = re.compile(r"^(M\.|Mme|Mlle|Mr|Dr|Pr)\s", re.I)
GROUP_RE = re.compile(r"(\bGr\s?\d|\[ING|\bING\d|\bIng\d)", re.I)
VIRTUAL_RE = re.compile(r"(e-?learning|distanciel|session live|lien communiqu|teams|zoom)", re.I)
TYPE_LABEL = {"CRS": "Cours", "CM": "CM", "TD": "TD", "TP": "TP", "CONFERENCE": "Conférence",
              "EXAM": "Examen", "DS": "DS", "PROJET": "Projet", "SOUTIEN": "Soutien"}


def clean_course(summary: str, location: str) -> dict:
    """'Mécanique - Mme X - [ING1 RENFO] - Ing1 Gr17 - CRS' -> nom, type, salle, en ligne ?"""
    parts = [p.strip() for p in summary.split(" - ") if p.strip()]
    ctype = ""
    if len(parts) > 1 and TYPE_RE.match(parts[-1]):
        ctype = parts.pop()
    keep = [p for p in parts if not PROF_RE.match(p) and not GROUP_RE.search(p)]
    virtual = bool(re.search(r"(^|-)CV$", ctype)) or bool(VIRTUAL_RE.search(summary + " " + location))
    if keep and VIRTUAL_RE.search(keep[0]) and len(keep) > 1:
        keep = keep[1:]  # "Session live obligatoire..." -> on garde le vrai titre
    name = keep[0] if keep else (parts[0] if parts else summary)
    name = re.sub(r"\s+", " ", name)[:60]
    codes = [c for c in ctype.split("-") if c and c != "CV"]
    if codes[:1] == ["CRS"] and len(codes) > 1:
        codes = codes[1:]  # CRS-CM -> CM, CRS-TD -> TD
    label = " / ".join(TYPE_LABEL.get(c, c.capitalize()) for c in codes)
    loc = location.strip(" -")
    if virtual or "ELEARNING" in loc.upper():
        virtual, loc = True, "En ligne"
    else:
        loc = re.sub(r"^Salle\s+", "", loc, flags=re.I)
        loc = re.sub(r"\s*-\s*(EIFFEL\s*\d+|E\d+)$", lambda m: " · " + m.group(1).replace("E", "Eiffel ", 1)
                     if m.group(1).upper().startswith("E") and not m.group(1).upper().startswith("EIFFEL")
                     else " · " + m.group(1).title(), loc)
    return {"summary": name, "type": label, "location": loc, "virtual": virtual}


def parse(text: str, days_back=1, days_fwd=30) -> dict:
    cal = icalendar.Calendar.from_ical(text)
    start = dt.datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=days_back)
    end = start + dt.timedelta(days=days_back + days_fwd)
    edt = {}
    for ev in recurring_ical_events.of(cal).between(start, end):
        if not isinstance(ev.get("DTSTART").dt, dt.datetime):
            continue  # événements "journée entière" ignorés
        summary = str(ev.get("SUMMARY", "")).strip()
        if str(ev.get("STATUS", "")).upper() == "CANCELLED" or summary.lower().startswith(("annul", "cancel")):
            continue  # cours annulé -> on le retire (le diff le signalera)
        s = _to_local(ev["DTSTART"].dt)
        e = _to_local(ev["DTEND"].dt) if ev.get("DTEND") else s + dt.timedelta(hours=1)
        info = clean_course(summary, str(ev.get("LOCATION", "")))
        edt.setdefault(s.date().isoformat(), []).append({"start": s.strftime("%H:%M"), "end": e.strftime("%H:%M"), **info})
    for d in edt:
        edt[d].sort(key=lambda c: c["start"])
    return edt


def _diff_day(old, new):
    old, new, changes = list(old), list(new), []
    for c in list(new):                       # identiques -> on ignore
        if c in old:
            old.remove(c); new.remove(c)
    for c in list(new):                       # même matière, autre heure/salle -> modifié
        m = next((o for o in old if o["summary"] == c["summary"]), None)
        if m:
            old.remove(m); new.remove(c); changes.append(("mod", m, c))
    changes += [("del", o, None) for o in old] + [("add", None, c) for c in new]
    return changes


def diff(old: dict, new: dict, horizon_days=14) -> dict:
    today = dt.datetime.now(TZ).date()
    out = {}
    for d in sorted(set(old) | set(new)):
        if not today <= dt.date.fromisoformat(d) <= today + dt.timedelta(days=horizon_days):
            continue
        ch = _diff_day(old.get(d, []), new.get(d, []))
        if ch:
            out[d] = ch
    return out


async def sync(session: aiohttp.ClientSession, force=False):
    """Retourne (changements, ancien_edt, nouvel_edt) ou None si rien n'a changé."""
    meta = db.get("ics_meta", {}) if not force else {}
    headers = {}
    if meta.get("etag"):
        headers["If-None-Match"] = meta["etag"]
    if meta.get("lm"):
        headers["If-Modified-Since"] = meta["lm"]
    url = C.get("ICS_URL")
    if "ICS_URL" in C.missing():
        raise RuntimeError("Lien .ics non configuré (page /config)")
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
        if r.status == 304:
            return None
        r.raise_for_status()
        text = await r.text()
        db.put("ics_meta", {"etag": r.headers.get("ETag"), "lm": r.headers.get("Last-Modified")})
    new = parse(text)
    old = db.get("edt")
    if db.get("edt_ver") != 2:  # nouveau format : pas de faux "changements"
        old = None
        db.put("edt_ver", 2)
    db.put("edt", new)
    if old is None:
        log.info("Premier import : %d jours de cours", len(new))
        return {}, {}, new
    return diff(old, new), old, new
