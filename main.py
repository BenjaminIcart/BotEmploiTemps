"""EDT (.ics) -> Discord (webhook) + surveillance des trains ligne N + petit site web."""
import asyncio
import datetime as dt
import logging

import aiohttp
from aiohttp import web as aioweb

import config as C
import db
import ics_sync
import trains
import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
session: aiohttp.ClientSession | None = None
state: dict = {"plan": None, "status_text": ""}


# ---------- helpers ----------
def now():
    return dt.datetime.now(C.TZ)


def hm(d):
    return d.strftime("%H:%M")


def jour(d):
    return f"{JOURS[d.weekday()]} {d:%d/%m}"


def courses(day):
    return db.get("edt", {}).get(day.isoformat(), [])


def fmt_course(c):
    return f"`{c['start']}-{c['end']}` {c['summary']}" + (f" · {c['location']}" if c["location"] else "")


def fmt_edt(day):
    cs = courses(day)
    return f"📅 **{jour(day)}**\n" + ("\n".join(map(fmt_course, cs)) if cs else "Pas cours 🎉")


def fmt_trip(t: trains.Trip):
    if t.delay > 0:
        return f"~~{hm(t.base_dep)}~~ **{hm(t.dep)}** (+{t.delay} min) → {hm(t.arr)} `{t.mission}`"
    return f"**{hm(t.dep)}** → {hm(t.arr)} `{t.mission}`"


async def send(text: str):
    """Envoie sur Discord via webhook (découpe à 2000 caractères)."""
    url = C.get("DISCORD_WEBHOOK_URL")
    if "DISCORD_WEBHOOK_URL" in C.missing():
        log.info("Webhook Discord non configuré, message ignoré")
        return False
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) > 1900:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    for c in chunks:
        try:
            async with session.post(url, json={"content": c, "username": "EDT & Trains"},
                                    timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 429:  # rate limit
                    await asyncio.sleep((await r.json()).get("retry_after", 2))
                    await session.post(url, json={"content": c})
                elif r.status >= 300:
                    log.warning("Webhook Discord %s : %s", r.status, await r.text())
                    return False
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


async def msg_plan(day: dt.date, title="") -> str:
    cs = courses(day)
    if not cs:
        return f"{title}{fmt_edt(day)}"
    aller = await trains.plan_aller(session, day, cs[0]["start"])
    retour = await trains.plan_retour(session, day, cs[-1]["end"])
    out = [title + fmt_edt(day), "", f"🚆 **Aller** (cours à {cs[0]['start']})"]
    for r in aller:
        o = r["origin"]
        out.append(f"{o['emoji']} {o['name']} — pars à **{hm(r['leave'])}** · train {fmt_trip(r['trip'])}")
    if not aller:
        out.append("Aucun train direct trouvé 🤔")
    out.append(f"\n🏠 **Retour** (fin à {cs[-1]['end']})")
    for r in retour:
        out.append(f"{r['origin']['name']} : " + (", ".join(f"{hm(t.dep)}→{hm(t.arr)}" for t in r["trips"]) or "—"))
    return "\n".join(out)


async def msg_retour() -> str:
    res = await trains.plan_retour(session, now().date(), now().strftime("%H:%M"))
    lines = [f"{r['origin']['name']} : " + (" · ".join(fmt_trip(t) for t in r["trips"]) or "—") for r in res]
    return "🏠 **Trains retour**\n" + "\n".join(lines)


def next_school_day() -> dt.date:
    today = now().date()
    cs = courses(today)
    return today if cs and now().strftime("%H:%M") < cs[0]["start"] else today + dt.timedelta(days=1)


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
    icons = {"add": "🆕", "del": "❌", "mod": "🔄"}
    lines = ["⚠️ **Changement d'emploi du temps**"]
    for d, chs in changes.items():
        lines.append(f"**{jour(dt.date.fromisoformat(d))}**")
        for kind, a, b in chs:
            if kind == "add":
                lines.append(f"{icons[kind]} {fmt_course(b)}")
            elif kind == "del":
                lines.append(f"{icons[kind]} ~~{fmt_course(a)}~~ (annulé)")
            else:
                lines.append(f"{icons[kind]} {a['summary']} : {a['start']}-{a['end']} {a['location']} → "
                             f"**{b['start']}-{b['end']} {b['location']}**")
    await send("\n".join(lines))
    for day in (now().date(), now().date() + dt.timedelta(days=1)):
        k = day.isoformat()
        f_old = (old.get(k) or [{}])[0].get("start")
        f_new = (new.get(k) or [{}])[0].get("start")
        if k in changes and f_old != f_new:
            state["plan"] = None
            await send(await msg_plan(day, "🔁 **Nouveau trajet conseillé**\n"))
    return len(changes)


async def recap_check():
    t = now()
    k = f"recap|{t.date()}"
    if t.strftime("%H:%M") >= C.get("RECAP_HOUR") and not db.get(k):
        db.put(k, True)
        tomorrow = t.date() + dt.timedelta(days=1)
        if courses(tomorrow):
            await send(await msg_plan(tomorrow, "🌙 **Demain**\n"))


async def monitor():
    if "PRIM_API_KEY" in C.missing():
        return
    t_now = now()
    plan = await get_plan(t_now.date())
    if not plan:
        return
    status_txt = []
    for r in plan["aller"]:
        t, o = r["trip"], r["origin"]
        if not (r["leave"] - dt.timedelta(minutes=C.get("CHECK_BEFORE")) <= t_now <= t.base_dep + dt.timedelta(minutes=60)):
            continue
        rt, cancelled = await trains.check(session, t, o)
        if rt and t_now > rt.dep:
            continue  # train parti
        delay = rt.delay if rt else 0
        kind = "cancel" if cancelled else ("late" if delay >= C.get("DELAY_ALERT") else "ok")
        status_txt.append(f"{o['name']} {hm(t.base_dep)} : " +
                          ("SUPPRIMÉ" if cancelled else f"+{delay} min" if delay else "à l'heure"))
        k = f"notif|{t.key}"
        last = db.get(k)
        if last and last["kind"] == kind and abs(last["delay"] - delay) < 3:
            continue
        db.put(k, {"kind": kind, "delay": delay})
        db.log_delay(plan["day"], o["name"], t.mission, t.base_dep.isoformat(), delay, cancelled)
        await ha_notify({"origin": o["name"], "status": kind, "delay": delay, "train": hm(t.base_dep)})
        head = f"{o['emoji']} **{o['name']} {hm(t.base_dep)}** `{t.mission}`"
        if kind == "ok":
            await send(f"✅ {head} à l'heure — pars à **{hm(r['leave'])}**" if not last
                       else f"✅ {head} est revenu à l'heure")
            continue
        if kind == "late":
            msg = f"⏱️ {head} : **+{delay} min** → départ {hm(rt.dep)}, arrivée {hm(rt.arr)}"
            msg += "\n⚠️ Tu risques d'être en retard en cours" if rt.arr > r["target"] else "\nÇa passe encore 👍"
        else:
            msg = f"🚫 {head} **SUPPRIMÉ**"
        alts = await trains.alternatives(session, o, r["target"], t_now + dt.timedelta(minutes=o["access"]))
        alts = [a for a in alts if a.key != t.key]
        if alts:
            msg += "\nAutres trains : " + " · ".join(fmt_trip(a) for a in alts)
        await send(msg)
    if status_txt:
        state["status_text"] = " | ".join(status_txt)

    # Retour : 10 min avant la fin des cours (1 fois par jour)
    last_end = courses(t_now.date())[-1]["end"]
    end = dt.datetime.combine(t_now.date(), dt.time(*map(int, last_end.split(":"))), C.TZ)
    k = f"retour|{plan['day']}"
    if end - dt.timedelta(minutes=10) <= t_now <= end and not db.get(k):
        db.put(k, True)
        await send(await msg_retour())


async def every(seconds, fn, name: str):
    while True:
        try:
            await fn()
        except Exception as e:
            log.warning("Erreur dans %s : %s", name, e)
        await asyncio.sleep(seconds() if callable(seconds) else seconds)


async def test_discord() -> str:
    ok = await send("👋 Test : le webhook fonctionne !")
    return "✅ Message envoyé sur Discord" if ok else "❌ Échec (vérifie l'URL du webhook, voir les logs)"


async def test_prim() -> str:
    lines = []
    for p in C.origins() + [C.dest()]:
        sid = await trains.resolve(session, p)
        lines.append(f"✅ {p['name']} → {sid}")
    return "\n".join(lines)


def on_config_saved():
    db.put("stops", {})
    state["plan"] = None


# ---------- démarrage ----------
async def main():
    global session
    session = aiohttp.ClientSession()
    actions = {
        "sync": lambda: do_ics_sync(force=True),
        "train": lambda: msg_plan(next_school_day()),
        "retour": msg_retour,
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
