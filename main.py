"""EDT (.ics) -> Discord (webhook, cards) + surveillance des trains ligne N + site web."""
import asyncio
import datetime as dt
import json
import logging
import time

import aiohttp
from aiohttp import web as aioweb

import cards as K
import config as C
import db
import ics_sync
import trains
import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")

session: aiohttp.ClientSession | None = None
state: dict = {"plan": None, "live": {}, "hero": None, "hero_ts": 0}


def now():
    return dt.datetime.now(C.TZ)


def courses(day):
    return db.get("edt", {}).get(day.isoformat(), [])


def onsite(day):
    """Cours sur place uniquement (les cours en ligne ne demandent pas de trajet)."""
    return [c for c in courses(day) if not c.get("virtual")]


# ---------- Discord ----------
async def send(embeds: list, content: str | None = None) -> bool:
    """Envoie des cards sur Discord via le webhook (10 cards max par message)."""
    url = C.get("DISCORD_WEBHOOK_URL")
    if "DISCORD_WEBHOOK_URL" in C.missing():
        log.info("Webhook Discord non configuré, message ignoré")
        return False
    if content is None:  # texte court affiché dans la notification du téléphone
        content = next((e["_notif"] for e in embeds if e.get("_notif")), None) or \
            next((e["_notif_edt"] for e in embeds if e.get("_notif_edt")), None)
    batches = [embeds[i:i + 10] for i in range(0, len(embeds), 10)] or [[]]
    for i, batch in enumerate(batches):
        files, clean = [], []
        for j, emb in enumerate(batch):  # images (frise du trajet) envoyées en pièce jointe
            emb = dict(emb)
            png = emb.pop("_png", None)
            emb.pop("_notif", None)
            emb.pop("_notif_edt", None)
            if png:
                name = f"trajet{j}.png"
                emb["image"] = {"url": f"attachment://{name}"}
                files.append((name, png))
            clean.append(emb)
        payload = {"username": "EDT & Trains", "embeds": clean}
        if content and i == 0:
            payload["content"] = content
        for _ in range(2):
            if files:
                body = aiohttp.FormData()
                body.add_field("payload_json", json.dumps(payload), content_type="application/json")
                for n_, (name, png) in enumerate(files):
                    body.add_field(f"files[{n_}]", png, filename=name, content_type="image/png")
                kw = {"data": body}
            else:
                kw = {"json": payload}
            try:
                async with session.post(url, timeout=aiohttp.ClientTimeout(total=20), **kw) as r:
                    if r.status == 429:
                        await asyncio.sleep((await r.json()).get("retry_after", 2))
                        continue
                    if r.status >= 300:
                        log.warning("Webhook Discord %s : %s", r.status, await r.text())
                        return False
                    break
            except Exception as e:
                log.warning("Webhook Discord : %s", e)
                return False
    return True


async def ha_notify(payload: dict):
    url = C.get("HA_WEBHOOK_URL")
    if not url:
        return
    try:
        await session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10))
    except Exception as e:
        log.warning("Webhook HA : %s", e)


# ---------- plans ----------
def next_school_day() -> dt.date:
    today = now().date()
    cs = onsite(today)
    if cs and now().strftime("%H:%M") < cs[0]["start"]:
        return today
    for i in range(1, 8):  # prochain jour avec cours sur place (saute le week-end)
        d = today + dt.timedelta(days=i)
        if onsite(d):
            return d
    return today + dt.timedelta(days=1)


async def get_plan(day: dt.date):
    cs = onsite(day)
    if not cs:
        return None
    p = state["plan"]
    if p and p["day"] == day.isoformat() and p["first"] == cs[0]["start"]:
        return p
    aller = await trains.plan_aller(session, day, cs[0]["start"])
    state["plan"] = {"day": day.isoformat(), "first": cs[0]["start"], "aller": aller}
    return state["plan"]


def school_target(r) -> dt.datetime:
    return r["course"] - dt.timedelta(minutes=C.get("MARGIN"))


def n_line_id(aller) -> str:
    return next((t.line_id for r in aller for t in r.get("list", []) if t.line_id), "")


async def get_backups(aller) -> list:
    out = []
    for r in aller:
        out += await trains.backup_routes(session, r["origin"], school_target(r), n_line_id(aller))
    return out


async def plan_cards(day: dt.date, prefix="", web=False) -> list:
    out = [K.edt_card(day, courses(day), prefix)]
    cs = onsite(day)
    if cs:
        aller = await trains.plan_aller(session, day, cs[0]["start"])
        retour = await trains.plan_retour(session, day, cs[-1]["end"], pref=C.preferred_origin(cs[0]["start"]))
        problem = not aller or not aller[0]["trip"]
        backups = await get_backups(aller) if (problem or web) else []
        ac = K.aller_card(aller, cs[0]["start"], backups if problem else None,
                          C.get("SCHOOL_NAME"), C.metro_stop()["name"])
        if prefix and ac.get("_notif"):
            ac["_notif"] = prefix.strip(" ·") + " : " + ac["_notif"]
        out.append(ac)
        for r2 in aller[1:]:
            out.append(K.alt_card(r2, C.get("SCHOOL_NAME"), C.metro_stop()["name"]))
        if web and not problem:
            out.append(K.backups_card(backups, "🔀 Si le N ne passe pas"))
        out.append(K.retour_card(retour, f" · fin à {cs[-1]['end']}", cs[-1]["end"]))
    return out


async def retour_cards(end: str | None = None) -> list:
    cs = onsite(now().date())
    pref = C.preferred_origin(cs[0]["start"]) if cs else None
    res = await trains.plan_retour(session, now().date(), end or now().strftime("%H:%M"), pref=pref)
    return [K.retour_card(res, f" · fin à {end}" if end else "", end)]


async def hero() -> dict:
    """Données du prochain trajet pour le site (cache 2 min)."""
    if state["hero"] and time.time() - state["hero_ts"] < 120:
        return state["hero"]
    day = next_school_day()
    cs = onsite(day)
    data = {"day": K.jour(day), "today": day == now().date(), "first": cs[0] if cs else None, "options": []}
    if cs and "PRIM_API_KEY" not in C.missing():
        aller = await trains.plan_aller(session, day, cs[0]["start"])
        state["hero_png"] = []
        for i, r in enumerate(aller):
            if not r["trip"]:
                continue
            try:
                import render
                png = render.aller_png(r, C.get("SCHOOL_NAME"), C.metro_stop()["name"], alt=i > 0)
                if png:
                    state["hero_png"].append(png)
            except Exception as e:
                log.warning("Frise : %s", e)
        for i, r in enumerate(aller):
            t = r["trip"]
            if not t:
                data["options"].append({"origin": r["origin"]["name"], "emoji": r["origin"]["emoji"],
                                        "best": i == 0, "none": True})
                continue
            live = state["live"].get(t.key, {})
            limit = r.get("latest_ok", r["target"])
            data["options"].append({
                "origin": r["origin"]["name"], "emoji": r["origin"]["emoji"], "best": i == 0,
                "leave": K.hm(r["leave"]), "dep": K.hm(t.dep), "base_dep": K.hm(t.base_dep),
                "arr": K.hm(t.arr), "mission": t.mission, "delay": live.get("delay", t.delay),
                "status": live.get("kind", "late" if t.delay >= C.get("DELAY_ALERT") else "ok"),
                "trains": [{"dep": K.hm(x.dep), "arr": K.hm(x.arr), "delay": x.delay, "main": x.key == t.key,
                            "late": x.arr > limit} for x in r["list"]],
            })
            ch = r.get("chain")
            if ch:
                data["options"][-1]["chain"] = {
                    "metro": ({"dep": K.hm(ch["metro"]["dep"]), "arr": K.hm(ch["metro"]["arr"]),
                               "line": ch["metro"]["line"]} if ch["metro"] else None),
                    "school_arr": K.hm(ch["school_arr"]), "school": C.get("SCHOOL_NAME"),
                    "stop": C.metro_stop()["name"], "late": ch["school_arr"] > r["course"]}
            try:
                import render
                data["options"][-1]["route"] = render.route_data(r, C.get("SCHOOL_NAME"), C.metro_stop()["name"])
            except Exception as e:
                log.warning("Route : %s", e)
    # retour du jour (si cours sur place aujourd'hui et pas encore fini depuis longtemps)
    today_cs = onsite(now().date())
    if today_cs and "PRIM_API_KEY" not in C.missing():
        end = today_cs[-1]["end"]
        end_dt = dt.datetime.combine(now().date(), dt.time(*map(int, end.split(":"))), C.TZ)
        if now() <= end_dt + dt.timedelta(minutes=90):
            try:
                ret = await trains.plan_retour(session, now().date(), end,
                                               pref=C.preferred_origin(today_cs[0]["start"]))
                data["retour"] = {"end": end, "cols": [
                    {"name": r["origin"]["name"],
                     "trips": [{"dep": K.hm(t.dep), "arr": K.hm(t.arr), "delay": t.delay} for t in r["trips"]]}
                    for r in ret]}
            except Exception as e:
                log.warning("Retour : %s", e)
    state["hero"], state["hero_ts"] = data, time.time()
    return data


# ---------- tâches ----------
async def do_ics_sync(force=False) -> int:
    if not force and "ICS_URL" in C.missing():
        return 0
    res = await ics_sync.sync(session, force=force)
    if not res:
        return 0
    changes, old, new = res
    if not changes:
        return 0
    state["hero"] = None
    await send([K.changes_card(changes)])
    for day in (now().date(), now().date() + dt.timedelta(days=1)):
        k = day.isoformat()
        f_old = (old.get(k) or [{}])[0].get("start")
        f_new = (new.get(k) or [{}])[0].get("start")
        if k in changes and f_old != f_new:
            state["plan"] = None
            await send(await plan_cards(day, "Nouveau trajet · "))
    return len(changes)


async def recap_check():
    t = now()
    k = f"recap|{t.date()}"
    if t.strftime("%H:%M") >= C.get("RECAP_HOUR") and not db.get(k):
        db.put(k, True)
        tomorrow = t.date() + dt.timedelta(days=1)
        if courses(tomorrow):
            await send(await plan_cards(tomorrow, "Demain · "))


async def monitor():
    if "PRIM_API_KEY" in C.missing():
        return
    t_now = now()
    plan = await get_plan(t_now.date())
    if not plan:
        return
    for r in plan["aller"]:
        t, o = r["trip"], r["origin"]
        if not t:
            continue
        if not (r["leave"] - dt.timedelta(minutes=C.get("CHECK_BEFORE")) <= t_now <= t.base_dep + dt.timedelta(minutes=60)):
            continue
        rt, cancelled = await trains.check(session, t, o)
        if rt and t_now > rt.dep:
            continue  # train parti
        delay = rt.delay if rt else 0
        kind = "cancel" if cancelled else ("late" if delay >= C.get("DELAY_ALERT") else "ok")
        state["live"][t.key] = {"kind": kind, "delay": delay}
        k = f"notif|{t.key}"
        last = db.get(k)
        if last and last["kind"] == kind and abs(last["delay"] - delay) < 3:
            continue
        db.put(k, {"kind": kind, "delay": delay})
        state["hero"] = None
        db.log_delay(plan["day"], o["name"], t.mission, t.base_dep.isoformat(), delay, cancelled)
        await ha_notify({"origin": o["name"], "status": kind, "delay": delay, "train": K.hm(t.base_dep)})
        alts, backups = [], []
        if kind != "ok":
            alts = await trains.alternatives(session, o, r["target"], t_now + dt.timedelta(minutes=o["access"]))
            alts = [a for a in alts if a.key != t.key][:2]
            if kind == "cancel" or rt.arr > r["target"]:
                backups = await trains.backup_routes(session, o, school_target(r), t.line_id)
        eta, route_r = None, None
        if rt:
            ch = await trains.chain(session, rt.arr)
            eta = f"**{K.hm(ch['school_arr'])}**" + (" ⚠️" if ch["school_arr"] > r["course"] else " ✅")
            route_r = dict(r, trip=rt, chain=ch)
        await send([K.status_card(kind, o, t, rt, r["leave"], r.get("latest_ok", r["target"]), alts,
                                  back=bool(last), backups=backups, school_eta=eta, route_r=route_r,
                                  school_name=C.get("SCHOOL_NAME"), stop_name=C.metro_stop()["name"])])

    # Retour : à la fin du dernier cours SUR PLACE (1 fois par jour)
    last_end = onsite(t_now.date())[-1]["end"]
    end = dt.datetime.combine(t_now.date(), dt.time(*map(int, last_end.split(":"))), C.TZ)
    k = f"retour|{plan['day']}"
    if end - dt.timedelta(minutes=2) <= t_now <= end + dt.timedelta(minutes=20) and not db.get(k):
        db.put(k, True)
        await send(await retour_cards(last_end))


async def virtual_check():
    """Rappel avant chaque cours en ligne (pour se mettre présent)."""
    t_now = now()
    before = C.get("VIRTUAL_NOTIFY")
    for c in courses(t_now.date()):
        if not c.get("virtual"):
            continue
        start = dt.datetime.combine(t_now.date(), dt.time(*map(int, c["start"].split(":"))), C.TZ)
        k = f"virtual|{t_now.date()}|{c['start']}|{c['summary']}"
        if start - dt.timedelta(minutes=before) <= t_now <= start + dt.timedelta(minutes=10) and not db.get(k):
            db.put(k, True)
            await send([K.virtual_card(c)])


async def every(seconds, fn, name: str):
    while True:
        try:
            await fn()
        except Exception as e:
            log.warning("Erreur dans %s : %s", name, e)
        await asyncio.sleep(seconds() if callable(seconds) else seconds)


# ---------- actions du site ----------
async def test_discord() -> list:
    c = K.test_card()
    if not await send([c]):
        raise RuntimeError("Échec de l'envoi : vérifie l'URL du webhook (voir les logs)")
    return [c]


async def test_prim() -> list:
    fields = []
    for p in C.origins() + [C.dest()]:
        fields.append((p["name"], f"`{await trains.resolve(session, p)}`", True))
    return [K.card("🚆 API PRIM OK", "green", "Gares détectées :", fields)]


def on_config_saved():
    db.put("stops", {})
    state.update(plan=None, hero=None)


async def main():
    global session
    session = aiohttp.ClientSession()
    actions = {
        "sync": lambda: do_ics_sync(force=True),
        "train": lambda: plan_cards(next_school_day(), web=True),
        "train_discord": lambda: plan_cards(next_school_day()),
        "retour": retour_cards,
        "hero": hero,
        "send": send,
        "test_discord": test_discord,
        "test_prim": test_prim,
        "config_saved": on_config_saved,
    }
    runner = aioweb.AppRunner(web.make_app(state, actions))
    await runner.setup()
    await aioweb.TCPSite(runner, "0.0.0.0", C.WEB_PORT).start()
    log.info("Site web : http://0.0.0.0:%d", C.WEB_PORT)
    await asyncio.gather(
        every(lambda: C.get("ICS_REFRESH_MIN") * 60, do_ics_sync, "ics"),
        every(60, recap_check, "recap"),
        every(60, virtual_check, "virtual"),
        every(180, monitor, "monitor"),
    )


if __name__ == "__main__":
    asyncio.run(main())
