"""EDT (.ics) -> Discord (webhook, cards) + surveillance des trains ligne N + site web."""
import asyncio
import datetime as dt
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


# ---------- Discord ----------
async def send(embeds: list, content: str | None = None) -> bool:
    """Envoie des cards sur Discord via le webhook (10 cards max par message)."""
    url = C.get("DISCORD_WEBHOOK_URL")
    if "DISCORD_WEBHOOK_URL" in C.missing():
        log.info("Webhook Discord non configuré, message ignoré")
        return False
    batches = [embeds[i:i + 10] for i in range(0, len(embeds), 10)] or [[]]
    for i, batch in enumerate(batches):
        payload = {"username": "EDT & Trains", "embeds": batch}
        if content and i == 0:
            payload["content"] = content
        for _ in range(2):
            try:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as r:
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
    cs = courses(today)
    if cs and now().strftime("%H:%M") < cs[0]["start"]:
        return today
    for i in range(1, 8):  # prochain jour avec cours (saute le week-end)
        d = today + dt.timedelta(days=i)
        if courses(d):
            return d
    return today + dt.timedelta(days=1)


async def get_plan(day: dt.date):
    cs = courses(day)
    if not cs:
        return None
    p = state["plan"]
    if p and p["day"] == day.isoformat() and p["first"] == cs[0]["start"]:
        return p
    aller = await trains.plan_aller(session, day, cs[0]["start"])
    state["plan"] = {"day": day.isoformat(), "first": cs[0]["start"], "aller": aller}
    return state["plan"]


def n_line_id(aller) -> str:
    return next((t.line_id for r in aller for t in r.get("list", []) if t.line_id), "")


async def get_backups(aller) -> list:
    out = []
    for r in aller:
        out += await trains.backup_routes(session, r["origin"], r["target"], n_line_id(aller))
    return out


async def plan_cards(day: dt.date, prefix="", web=False) -> list:
    cs = courses(day)
    out = [K.edt_card(day, cs, prefix)]
    if cs:
        aller = await trains.plan_aller(session, day, cs[0]["start"])
        retour = await trains.plan_retour(session, day, cs[-1]["end"])
        problem = not aller or not aller[0]["trip"]
        backups = await get_backups(aller) if (problem or web) else []
        out.append(K.aller_card(aller, cs[0]["start"], backups if problem else None))
        if web and not problem:
            out.append(K.backups_card(backups, "🔀 Si le N ne passe pas"))
        out.append(K.retour_card(retour, f" · fin à {cs[-1]['end']}"))
    return out


async def retour_cards() -> list:
    res = await trains.plan_retour(session, now().date(), now().strftime("%H:%M"))
    return [K.retour_card(res, " · prochains trains")]


async def hero() -> dict:
    """Données du prochain trajet pour le site (cache 2 min)."""
    if state["hero"] and time.time() - state["hero_ts"] < 120:
        return state["hero"]
    day = next_school_day()
    cs = courses(day)
    data = {"day": K.jour(day), "today": day == now().date(), "first": cs[0] if cs else None, "options": []}
    if cs and "PRIM_API_KEY" not in C.missing():
        for i, r in enumerate(await trains.plan_aller(session, day, cs[0]["start"])):
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
            await send(await plan_cards(day, "🔁 Nouveau trajet · "))
    return len(changes)


async def recap_check():
    t = now()
    k = f"recap|{t.date()}"
    if t.strftime("%H:%M") >= C.get("RECAP_HOUR") and not db.get(k):
        db.put(k, True)
        tomorrow = t.date() + dt.timedelta(days=1)
        if courses(tomorrow):
            await send(await plan_cards(tomorrow, "🌙 Demain · "))


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
                backups = await trains.backup_routes(session, o, r["target"], t.line_id)
        await send([K.status_card(kind, o, t, rt, r["leave"], r["target"], alts, back=bool(last), backups=backups)])

    # Retour : 10 min avant la fin des cours (1 fois par jour)
    last_end = courses(t_now.date())[-1]["end"]
    end = dt.datetime.combine(t_now.date(), dt.time(*map(int, last_end.split(":"))), C.TZ)
    k = f"retour|{plan['day']}"
    if end - dt.timedelta(minutes=10) <= t_now <= end and not db.get(k):
        db.put(k, True)
        await send(await retour_cards())


async def every(seconds, fn, name: str):
    while True:
        try:
            await fn()
        except Exception as e:
            log.warning("Erreur dans %s : %s", name, e)
        await asyncio.sleep(seconds() if callable(seconds) else seconds)


# ---------- actions du site ----------
async def test_discord() -> list:
    c = K.card("👋 Test réussi", "green", "Le webhook fonctionne, les notifications arriveront ici.")
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
        every(180, monitor, "monitor"),
    )


if __name__ == "__main__":
    asyncio.run(main())
