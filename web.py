"""Site web : EDT de la semaine, état des trains, actions et page de configuration."""
import datetime as dt
import html

from aiohttp import web

import config as C
import db
from config import TZ

e = html.escape
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
CSS = """body{font-family:system-ui;background:#111;color:#eee;max-width:900px;margin:auto;padding:1rem}
a{color:#0a84ff}h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:1.4rem}
.day{background:#1c1c1e;border-radius:12px;padding:.8rem 1rem;margin:.6rem 0}
.day.today{outline:2px solid #0a84ff}.c{display:flex;gap:.8rem;padding:.2rem 0}.t{color:#8e8e93;width:7.5rem}
table{width:100%;border-collapse:collapse}td,th{padding:.3rem;border-bottom:1px solid #333;text-align:left}
.ok{color:#30d158}.late{color:#ff9f0a}.ko{color:#ff453a}
.card{background:#1c1c1e;border-radius:12px;padding:1rem;margin:.6rem 0}.warn{outline:2px solid #ff9f0a}
button{background:#0a84ff;color:#fff;border:0;border-radius:8px;padding:.5rem .9rem;margin:.2rem;font-size:1rem;cursor:pointer}
button.alt{background:#3a3a3c}pre{white-space:pre-wrap;background:#1c1c1e;border-radius:12px;padding:1rem}
label{display:block;margin-top:.8rem;font-weight:600}small{color:#8e8e93;display:block;margin-top:.2rem}
input{width:100%;box-sizing:border-box;padding:.55rem;border-radius:8px;border:1px solid #3a3a3c;background:#2c2c2e;color:#eee;font-size:1rem}"""


def make_app(state: dict, actions: dict) -> web.Application:
    def tok(request, first=True):
        t = request.query.get("token")
        return (("?" if first else "&") + f"token={e(t)}") if t else ""

    @web.middleware
    async def auth(request, handler):
        need = C.get("WEB_TOKEN")
        if need and request.query.get("token") != need:
            return web.Response(status=401, text="🔒 Ajoute ?token=… à l'adresse")
        return await handler(request)

    def page(body: str, request) -> web.Response:
        t = tok(request)
        nav = (f"<p><a href='/{t}'><button>🏠 Accueil</button></a>"
               f"<a href='/train{t}'><button>🚆 Train conseillé</button></a>"
               f"<a href='/retour{t}'><button>🏠 Retour</button></a>"
               f"<a href='/sync{t}'><button>🔄 Sync EDT</button></a>"
               f"<a href='/config{t}'><button class=alt>⚙️ Config</button></a></p>")
        miss = C.missing()
        if miss and request.path != "/config":
            nav += (f"<div class='card warn'>⚠️ Configuration incomplète ({', '.join(miss)}) → "
                    f"<a href='/config{t}'>remplir la config</a></div>")
        return web.Response(text=f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                                 f"<title>EDT & trains</title><style>{CSS}</style><h1>🚆 EDT & trains</h1>{nav}{body}",
                            content_type="text/html")

    def err(ex, request):
        return page(f"<div class='card warn'>❌ Erreur : {e(str(ex))}</div>", request)

    # ---------- accueil ----------
    async def index(request):
        edt = db.get("edt", {})
        today = dt.datetime.now(TZ).date()
        out = []
        if state.get("status_text"):
            out.append(f"<div class=card>{e(state['status_text'])}</div>")
        for i in range(7):
            d = today + dt.timedelta(days=i)
            cs = edt.get(d.isoformat(), [])
            if not cs and d.weekday() >= 5:
                continue
            out.append(f"<div class='day{' today' if i == 0 else ''}'><b>{JOURS[d.weekday()]} {d:%d/%m}</b>")
            out += [f"<div class=c><span class=t>{c['start']}–{c['end']}</span><span>{e(c['summary'])}"
                    f"{' · ' + e(c['location']) if c['location'] else ''}</span></div>" for c in cs] or ["<div>Pas cours 🎉</div>"]
            out.append("</div>")
        rows = db.last_delays()
        if rows:
            out.append("<h2>Historique</h2><table><tr><th>Jour</th><th>Gare</th><th>Train</th><th>État</th></tr>")
            for day, origin, mission, base_dep, delay, cancelled in rows:
                cls, txt = ("ko", "Supprimé") if cancelled else (("late", f"+{delay} min") if delay > 0 else ("ok", "À l'heure"))
                out.append(f"<tr><td>{day}</td><td>{e(origin)}</td><td>{e(mission)} {base_dep[11:16]}</td>"
                           f"<td class={cls}>{txt}</td></tr>")
            out.append("</table>")
        return page("".join(out), request)

    # ---------- actions ----------
    def text_action(name):
        async def handler(request):
            try:
                txt = await actions[name]()
                if request.query.get("discord") == "1":
                    await actions["send"](txt)
            except Exception as ex:
                return err(ex, request)
            return page(f"<pre>{e(txt)}</pre><a href='?discord=1{tok(request, False)}'>"
                        f"<button>📨 Envoyer sur Discord</button></a>", request)
        return handler

    async def sync(request):
        try:
            n = await actions["sync"]()
        except Exception as ex:
            return err(ex, request)
        nb = sum(len(v) for v in db.get("edt", {}).values())
        return page(f"<div class=card>✅ EDT récupéré : {nb} cours sur 30 jours ({n} jour(s) modifié(s))</div>", request)

    # ---------- config ----------
    async def config_view(request):
        saved = db.get("settings", {})
        out = ["<div class=card>✅ Configuration enregistrée et appliquée</div>" if request.query.get("saved") else "",
               f"<form method=post action='/config{tok(request)}'>"]
        for key, label, typ, default, hint in C.FIELDS:
            if key.startswith("__"):
                out.append(f"<h2>{e(key[2:])}</h2>")
                continue
            cur = str(saved.get(key, ""))
            if typ == "secret":
                ph = "•••••••• enregistré — laisser vide pour garder" if C.get(key) else ""
                inp = f"<input type=password name={key} placeholder='{e(ph)}' autocomplete=off>"
            elif typ == "int":
                inp = f"<input type=number min=0 name={key} value='{e(cur or str(C.get(key)))}'>"
            elif typ == "time":
                inp = f"<input type=time name={key} value='{e(cur or C.get(key))}'>"
            else:
                inp = f"<input type=text name={key} value='{e(cur)}' placeholder='{e(default)}'>"
            out.append(f"<label>{e(label)}</label>{inp}" + (f"<small>{e(hint)}</small>" if hint else ""))
        out.append("<p><button type=submit>💾 Enregistrer</button></p></form>")
        t = tok(request)
        out.append(f"<h2>Tests</h2><a href='/config/test/discord{t}'><button class=alt>📨 Tester le webhook Discord</button></a>"
                   f"<a href='/config/test/prim{t}'><button class=alt>🚆 Tester l'API PRIM (gares)</button></a>"
                   f"<a href='/sync{t}'><button class=alt>📅 Tester le lien .ics</button></a>")
        return page("".join(out), request)

    async def config_post(request):
        form = await request.post()
        values = {}
        for key, _, typ, _, _ in C.FIELDS:
            if key.startswith("__") or key not in form:
                continue
            v = str(form[key]).strip()
            if typ == "secret" and not v:
                continue  # vide = on garde l'ancienne valeur
            values[key] = v
        C.save(values)
        actions["config_saved"]()
        new_tok = C.get("WEB_TOKEN")
        if new_tok and request.query.get("token") != new_tok:
            raise web.HTTPFound(f"/config?token={new_tok}&saved=1")
        raise web.HTTPFound(f"/config?saved=1{tok(request, False)}")

    async def test(request):
        name = request.match_info["what"]
        if f"test_{name}" not in actions:
            raise web.HTTPNotFound()
        try:
            txt = await actions[f"test_{name}"]()
        except Exception as ex:
            return err(ex, request)
        return page(f"<pre>{e(txt)}</pre><a href='/config{tok(request)}'><button class=alt>⬅️ Retour config</button></a>",
                    request)

    async def api(_):
        return web.json_response({"edt": db.get("edt", {}), "status": state.get("status_text")})

    app = web.Application(middlewares=[auth])
    app.router.add_get("/", index)
    app.router.add_get("/train", text_action("train"))
    app.router.add_get("/retour", text_action("retour"))
    app.router.add_get("/sync", sync)
    app.router.add_get("/config", config_view)
    app.router.add_post("/config", config_post)
    app.router.add_get("/config/test/{what}", test)
    app.router.add_get("/api", api)
    return app
