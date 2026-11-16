"""Horaires temps réel ligne N via l'API PRIM (Calculateur IDFM / Navitia)."""
import datetime as dt
import logging
from dataclasses import dataclass

import aiohttp

import db
import config as C
from config import TZ

log = logging.getLogger("trains")
BASE = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"


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
    line_id: str = ""

    @property
    def delay(self) -> int:
        return int((self.dep - self.base_dep).total_seconds() // 60)

    @property
    def key(self) -> str:
        return f"{self.origin}|{self.mission}|{self.base_dep:%Y%m%d%H%M}"


async def _get(session, path, params):
    async with session.get(BASE + path, params=params, headers={"apikey": C.get("PRIM_API_KEY")},
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
            line_id=next((l["id"] for l in di.get("links", []) if l.get("type") == "line"), ""),
        )
        if t.key not in seen:
            seen.add(t.key)
            trips.append(t)
    return sorted(trips, key=lambda t: t.dep)


def target_arrival(day: dt.date, first_start: str) -> dt.datetime:
    h, m = map(int, first_start.split(":"))
    return dt.datetime.combine(day, dt.time(h, m), TZ) - dt.timedelta(minutes=C.get("WALK_SCHOOL") + C.get("MARGIN"))


def _hm(d):
    return d.strftime("%H:%M")


async def plan_aller(session, day: dt.date, first_start: str) -> list[dict]:
    """Pour chaque gare : train conseillé + 1 avant + 1 après. Gare préférée en premier."""
    target = target_arrival(day, first_start)
    h, m = map(int, first_start.split(":"))
    course = dt.datetime.combine(day, dt.time(h, m), TZ)
    latest_ok = course - dt.timedelta(minutes=C.get("WALK_SCHOOL"))  # limite absolue (sans marge)
    dest = await resolve(session, C.dest())
    res = []
    for o in C.origins():
        oid = await resolve(session, o)
        trips = await journeys(session, oid, dest, target, arrival=True, origin_name=o["name"], count=4)
        ok = [t for t in trips if t.arr <= target]
        main = max(ok, key=lambda t: t.dep) if ok else None
        # train habituel (ex. 07:16) : prioritaire s'il arrive avant le début des cours
        usual = o.get("usual")
        if usual:
            uh, um = map(int, usual.split(":"))
            u_when = dt.datetime.combine(day, dt.time(uh, um), TZ)
            cand = await journeys(session, oid, dest, u_when - dt.timedelta(minutes=1), arrival=False,
                                  origin_name=o["name"], count=2)
            cand = [t for t in cand if _hm(t.base_dep) == usual]
            if cand and cand[0].arr <= latest_ok and cand[0].arr >= target - dt.timedelta(minutes=45):
                main = cand[0]
                trips = sorted({t.key: t for t in trips + cand}.values(), key=lambda t: t.dep)
        if main is None and trips:
            main = trips[-1]
        if main is None:
            res.append({"origin": o, "trip": None, "target": target, "leave": None, "list": []})
            continue
        before = [t for t in trips if t.dep < main.dep][-1:]
        after = await journeys(session, oid, dest, main.base_dep + dt.timedelta(minutes=1), arrival=False,
                               origin_name=o["name"], count=3)
        after = [t for t in after if t.dep > main.dep and t.key != main.key][:1]
        res.append({"origin": o, "trip": main, "target": target, "latest_ok": latest_ok,
                    "leave": main.dep - dt.timedelta(minutes=o["access"]), "list": before + [main] + after})
    pref = C.get("PREFERRED_ORIGIN")
    res.sort(key=lambda r: r["origin"]["name"] != pref)
    return res


SHORT = {"Transilien": "Train", "Métro": "Métro", "RER": "RER", "Bus": "Bus", "Tramway": "Tram", "Train": "Train"}


async def routes(session, origin_cfg: dict, when: dt.datetime, arrival=True, forbid=(), count=4) -> list[dict]:
    """Itinéraires avec correspondances (RER C, bus...) en évitant les lignes interdites (ex. le N)."""
    oid = await resolve(session, origin_cfg)
    dest = await resolve(session, C.dest())
    params = [("from", oid), ("to", dest), ("datetime", _fmt(when)),
              ("datetime_represents", "arrival" if arrival else "departure"),
              ("max_nb_transfers", 3), ("count", count), ("data_freshness", "realtime")]
    params += [("forbidden_uris[]", f) for f in forbid if f]
    data = await _get(session, "/journeys", params)
    out, seen = [], set()
    for j in data.get("journeys", []):
        pt = [s for s in j.get("sections", []) if s.get("type") == "public_transport"]
        if not pt:
            continue
        legs = []
        for s in pt:
            di = s.get("display_informations", {})
            mode = di.get("commercial_mode") or di.get("physical_mode") or ""
            legs.append(f"{SHORT.get(mode, mode)} {di.get('code') or di.get('label') or ''}".strip())
        r = {"origin": origin_cfg["name"], "dep": _nv(j["departure_date_time"]),
             "arr": _nv(j["arrival_date_time"]), "legs": legs, "transfers": j.get("nb_transfers", len(pt) - 1)}
        k = (r["dep"], r["arr"], tuple(legs))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return sorted(out, key=lambda r: r["dep"])


async def backup_routes(session, origin_cfg: dict, target: dt.datetime, n_line_id: str = "") -> list[dict]:
    """Itinéraires de secours sans le N, arrivant avant l'heure cible."""
    try:
        rs = await routes(session, origin_cfg, target, arrival=True, forbid=[n_line_id])
    except Exception as e:
        log.warning("Itinéraires alternatifs : %s", e)
        return []
    if not n_line_id:  # on n'a pas pu exclure le N : on retire au moins les trajets directs en N
        rs = [r for r in rs if not (len(r["legs"]) == 1 and r["legs"][0].endswith(" N"))]
    return rs[-2:]


async def plan_retour(session, day: dt.date, last_end: str, count=3) -> list[dict]:
    h, m = map(int, last_end.split(":"))
    when = max(dt.datetime.combine(day, dt.time(h, m), TZ) + dt.timedelta(minutes=C.get("WALK_SCHOOL")),
               dt.datetime.now(TZ))
    dest = await resolve(session, C.dest())
    res = []
    for o in C.origins():
        oid = await resolve(session, o)
        trips = await journeys(session, dest, oid, when, arrival=False, origin_name=o["name"], count=count)
        res.append({"origin": o, "trips": trips[:count]})
    res.sort(key=lambda r: r["origin"]["name"] != C.get("PREFERRED_ORIGIN"))
    return res


async def check(session, planned: Trip, origin_cfg: dict):
    """Retourne (trip_temps_reel | None, supprimé: bool)."""
    oid = await resolve(session, origin_cfg)
    dest = await resolve(session, C.dest())
    rt = await journeys(session, oid, dest, planned.base_dep - dt.timedelta(minutes=1),
                        arrival=False, origin_name=planned.origin, count=6)
    for t in rt:
        if t.base_dep == planned.base_dep and (not planned.mission or t.mission == planned.mission):
            return t, False
    return None, True


async def alternatives(session, origin_cfg: dict, target: dt.datetime, after: dt.datetime) -> list[Trip]:
    oid = await resolve(session, origin_cfg)
    dest = await resolve(session, C.dest())
    trips = await journeys(session, oid, dest, after, arrival=False, origin_name=origin_cfg["name"], count=4)
    return trips[:3]
