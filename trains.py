"""Horaires temps réel ligne N via l'API PRIM (Calculateur IDFM / Navitia)."""
import datetime as dt
import logging
from dataclasses import dataclass

import aiohttp

import db
from config import DEST, MARGIN, ORIGINS, PRIM_API_KEY, TZ, WALK_SCHOOL

log = logging.getLogger("trains")
BASE = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
HEADERS = {"apikey": PRIM_API_KEY}


def _nv(t: str) -> dt.datetime:
    return dt.datetime.strptime(t, "%Y%m%dT%H%M%S").replace(tzinfo=TZ)


def _fmt(d: dt.datetime) -> str:
    return d.astimezone(TZ).strftime("%Y%m%dT%H%M%S")


@dataclass
class Trip:
    origin: str
    line: str
    mission: str
    direction: str
    base_dep: dt.datetime
    dep: dt.datetime
    base_arr: dt.datetime
    arr: dt.datetime

    @property
    def delay(self) -> int:
        return int((self.dep - self.base_dep).total_seconds() // 60)

    @property
    def key(self) -> str:
        return f"{self.origin}|{self.mission}|{self.base_dep:%Y%m%d%H%M}"


async def _get(session, path, params):
    async with session.get(BASE + path, params=params, headers=HEADERS,
                           timeout=aiohttp.ClientTimeout(total=20)) as r:
        if r.status == 404:  # Navitia renvoie 404 quand aucun trajet
            return {}
        r.raise_for_status()
        return await r.json()


async def resolve(session, place: dict) -> str:
    if place.get("id"):
        return place["id"]
    cache = db.get("stops", {})
    if place["query"] in cache:
        return cache[place["query"]]
    data = await _get(session, "/places", {"q": place["query"], "type[]": "stop_area", "count": 5})
    places = data.get("places", [])
    if not places:
        raise RuntimeError(f"Gare introuvable : {place['query']}")
    sid = places[0]["id"]
    log.info("Gare '%s' -> %s (%s)", place["query"], sid, places[0].get("name"))
    cache[place["query"]] = sid
    db.put("stops", cache)
    return sid


async def journeys(session, frm, to, when, arrival, origin_name, count=4) -> list[Trip]:
    params = {
        "from": frm, "to": to, "datetime": _fmt(when),
        "datetime_represents": "arrival" if arrival else "departure",
        "max_nb_transfers": 0, "count": count, "data_freshness": "realtime",
    }
    data = await _get(session, "/journeys", params)
    trips, seen = [], set()
    for j in data.get("journeys", []):
        pt = [s for s in j.get("sections", []) if s.get("type") == "public_transport"]
        if len(pt) != 1:
            continue
        s, di = pt[0], pt[0].get("display_informations", {})
        t = Trip(
            origin=origin_name,
            line=di.get("code") or di.get("label") or "?",
            mission=di.get("headsign") or di.get("trip_short_name") or "",
            direction=di.get("direction", ""),
            base_dep=_nv(s.get("base_departure_date_time", s["departure_date_time"])),
            dep=_nv(s["departure_date_time"]),
            base_arr=_nv(s.get("base_arrival_date_time", s["arrival_date_time"])),
            arr=_nv(s["arrival_date_time"]),
        )
        if t.key not in seen:
            seen.add(t.key)
            trips.append(t)
    return sorted(trips, key=lambda t: t.dep)


def target_arrival(day: dt.date, first_start: str) -> dt.datetime:
    h, m = map(int, first_start.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), TZ) - dt.timedelta(minutes=WALK_SCHOOL + MARGIN)


async def plan_aller(session, day: dt.date, first_start: str) -> list[dict]:
    """Pour chaque gare : le train le plus tard qui arrive à l'heure + l'heure de départ de chez toi."""
    target = target_arrival(day, first_start)
    dest = await resolve(session, DEST)
    res = []
    for o in ORIGINS:
        oid = await resolve(session, o)
        trips = await journeys(session, oid, dest, target, arrival=True, origin_name=o["name"], count=3)
        ok = [t for t in trips if t.arr <= target] or trips
        if not ok:
            continue
        best = max(ok, key=lambda t: t.dep)
        res.append({"origin": o, "trip": best, "target": target,
                    "leave": best.dep - dt.timedelta(minutes=o["access"]), "alts": ok})
    res.sort(key=lambda r: r["leave"], reverse=True)  # celui qui te laisse dormir le plus en premier
    return res


async def plan_retour(session, day: dt.date, last_end: str, count=3) -> list[dict]:
    h, m = map(int, last_end.split(":"))
    when = max(dt.datetime.combine(day, dt.time(h, m), TZ) + dt.timedelta(minutes=WALK_SCHOOL),
               dt.datetime.now(TZ))
    dest = await resolve(session, DEST)
    res = []
    for o in ORIGINS:
        oid = await resolve(session, o)
        trips = await journeys(session, dest, oid, when, arrival=False, origin_name=o["name"], count=count)
        res.append({"origin": o, "trips": trips[:count]})
    return res


async def check(session, planned: Trip, origin_cfg: dict):
    """Retourne (trip_temps_reel | None, supprimé: bool)."""
    oid = await resolve(session, origin_cfg)
    dest = await resolve(session, DEST)
    rt = await journeys(session, oid, dest, planned.base_dep - dt.timedelta(minutes=1),
                        arrival=False, origin_name=planned.origin, count=6)
    for t in rt:
        if t.base_dep == planned.base_dep and (not planned.mission or t.mission == planned.mission):
            return t, False
    return None, True


async def alternatives(session, origin_cfg: dict, target: dt.datetime, after: dt.datetime) -> list[Trip]:
    oid = await resolve(session, origin_cfg)
    dest = await resolve(session, DEST)
    trips = await journeys(session, oid, dest, after, arrival=False, origin_name=origin_cfg["name"], count=4)
    return trips[:3]
