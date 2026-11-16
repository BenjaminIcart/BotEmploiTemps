"""Petit site web : EDT de la semaine, état des trains, boutons d'action."""
import datetime as dt
import html

from aiohttp import web

import db
from config import TZ, WEB_TOKEN

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
CSS = """body{font-family:system-ui;background:#111;color:#eee;max-width:900px;margin:auto;padding:1rem}
h1{font-size:1.4rem}.day{background:#1c1c1e;border-radius:12px;padding:.8rem 1rem;margin:.6rem 0}
.day.today{outline:2px solid #0a84ff}.c{display:flex;gap:.8rem;padding:.2rem 0}.t{color:#8e8e93;width:7.5rem}
table{width:100%;border-collapse:collapse}td,th{padding:.3rem;border-bottom:1px solid #333;text-align:left}
.ok{color:#30d158}.late{color:#ff9f0a}.ko{color:#ff453a}.card{background:#1c1c1e;border-radius:12px;padding:1rem;margin:.6rem 0}
button{background:#0a84ff;color:#fff;border:0;border-radius:8px;padding:.5rem .9rem;margin:.2rem;font-size:1rem;cursor:pointer}
pre{white-space:pre-wrap;background:#1c1c1e;border-radius:12px;padding:1rem}"""


def make_app(state: dict, actions: dict) -> web.Application:
    @web.middleware
    async def auth(request, handler):
        if WEB_TOKEN and request.query.get("token") != WEB_TOKEN:
            raise web.HTTPUnauthorized()
        return await handler(request)

    def page(body: str, request) -> web.Response:
        tok = f"?token={request.query['token']}" if "token" in request.query else ""
        nav = (f"<p><a href='/{tok}'><button>🏠 Accueil</button></a>"
               f"<a href='/train{tok}'><button>🚆 Train conseillé</button></a>"
               f"<a href='/retour{tok}'><button>🏠 Retour</button></a>"
               f"<a href='/sync{tok}'><button>🔄 Sync EDT</button></a></p>")
        return web.Response(text=f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                                 f"<title>EDT & trains</title><style>{CSS}</style><h1>🚆 EDT & trains</h1>{nav}{body}",
                            content_type="text/html")

    async def index(request):
        e = html.escape
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

    def text_action(name):
        async def handler(request):
            try:
                txt = await actions[name]()
            except Exception as ex:
                return page(f"<div class=card>❌ Erreur : {html.escape(str(ex))}</div>", request)
            if request.query.get("discord") == "1":
                await actions["send"](txt)
            tok = f"token={request.query['token']}&" if "token" in request.query else ""
            return page(f"<pre>{html.escape(txt)}</pre>"
                        f"<a href='?{tok}discord=1'><button>📨 Envoyer sur Discord</button></a>", request)
        return handler

    async def sync(request):
        try:
            n = await actions["sync"]()
        except Exception as ex:
            return page(f"<div class=card>❌ Erreur : {html.escape(str(ex))}</div>", request)
        return page(f"<div class=card>✅ EDT mis à jour ({n} jour(s) modifié(s))</div>", request)

    async def api(_):
        return web.json_response({"edt": db.get("edt", {}), "status": state.get("status_text")})

    app = web.Application(middlewares=[auth])
    app.router.add_get("/", index)
    app.router.add_get("/train", text_action("train"))
    app.router.add_get("/retour", text_action("retour"))
    app.router.add_get("/sync", sync)
    app.router.add_get("/api", api)
    return app
