"""Récupère le .ics, le transforme en {jour: [cours]} et détecte les changements."""
import datetime as dt
import logging

import aiohttp
import icalendar
import recurring_ical_events

import db
from config import ICS_URL, TZ

log = logging.getLogger("ics")


def _to_local(v):
    if v.tzinfo is None:
        v = v.replace(tzinfo=TZ)
    return v.astimezone(TZ)


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
        edt.setdefault(s.date().isoformat(), []).append({
            "start": s.strftime("%H:%M"), "end": e.strftime("%H:%M"),
            "summary": summary, "location": str(ev.get("LOCATION", "")).strip(),
        })
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
    async with session.get(ICS_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
        if r.status == 304:
            return None
        r.raise_for_status()
        text = await r.text()
        db.put("ics_meta", {"etag": r.headers.get("ETag"), "lm": r.headers.get("Last-Modified")})
    new = parse(text)
    old = db.get("edt")
    db.put("edt", new)
    if old is None:
        log.info("Premier import : %d jours de cours", len(new))
        return {}, {}, new
    return diff(old, new), old, new
