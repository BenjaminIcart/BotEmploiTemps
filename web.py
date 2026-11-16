"""Site web : tableau de bord, cards (même rendu que Discord) et page de configuration."""
import datetime as dt
import hashlib
import html
import re

from aiohttp import web

import config as C
import db
from cards import JOURS
from config import TZ

e = html.escape

CSS = """
:root{--bg:#0b0b0f;--card:#16161c;--card2:#1e1e26;--line:#2a2a35;--txt:#f2f2f7;--mute:#8e8e9a;
--blue:#0a84ff;--green:#30d158;--orange:#ff9f0a;--red:#ff453a;--purple:#bf5af2;--teal:#40c8e0}
*{box-sizing:border-box}html{color-scheme:dark}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,system-ui,sans-serif;background:var(--bg);color:var(--txt)}
a{color:inherit;text-decoration:none}
header{position:sticky;top:0;z-index:5;backdrop-filter:blur(14px);background:#0b0b0fcc;border-bottom:1px solid var(--line)}
.bar{max-width:1100px;margin:auto;display:flex;align-items:center;gap:.4rem;padding:.7rem 1rem;flex-wrap:wrap}
.logo{font-weight:800;font-size:1.1rem;margin-right:auto;letter-spacing:-.02em}
.nav a{padding:.45rem .8rem;border-radius:999px;color:var(--mute);font-weight:600;font-size:.92rem}
.nav a.on,.nav a:hover{background:var(--card2);color:var(--txt)}
main{max-width:1100px;margin:auto;padding:1.2rem 1rem 3rem}
h2{font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;color:var(--mute);margin:2rem 0 .7rem}
.box{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:1.1rem}
.warn{border-color:var(--orange);background:#ff9f0a14}
.btn{display:inline-flex;align-items:center;gap:.4rem;background:var(--blue);color:#fff;border:0;border-radius:12px;
padding:.6rem 1rem;font-weight:600;font-size:.95rem;cursor:pointer}
.btn.ghost{background:var(--card2);color:var(--txt);border:1px solid var(--line)}
.hero-head{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:.5rem}
.hero-head .d{font-size:1.5rem;font-weight:800;letter-spacing:-.02em}.hero-head .s{color:var(--mute)}
.opts{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:.8rem;margin-top:1rem}
.opt{background:var(--card2);border:1px solid var(--line);border-radius:16px;padding:1rem;position:relative}
.opt.best{border-color:var(--purple)}.opt .o{color:var(--mute);font-weight:600}
.opt .big{font-size:2.6rem;font-weight:800;letter-spacing:-.03em;line-height:1.1;margin:.2rem 0}
.opt .tr{color:var(--mute);font-size:.95rem}.tag{position:absolute;top:.8rem;right:.8rem}
.badge{display:inline-block;padding:.2rem .6rem;border-radius:999px;font-size:.8rem;font-weight:700}
.b-ok{background:#30d15822;color:var(--green)}.b-late{background:#ff9f0a22;color:var(--orange)}
.b-cancel{background:#ff453a22;color:var(--red)}.b-best{background:#bf5af222;color:var(--purple)}
.week{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(210px,1fr);gap:.7rem;overflow-x:auto;padding-bottom:.4rem}
.day{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:.8rem}
.day.today{border-color:var(--blue);box-shadow:0 0 0 1px var(--blue) inset}
.day .t{font-weight:700;margin-bottom:.5rem;display:flex;justify-content:space-between}
.day .t span{color:var(--mute);font-weight:500;font-size:.85rem}
.cr{border-left:4px solid var(--c);background:var(--card2);border-radius:8px;padding:.45rem .6rem;margin:.35rem 0}
.cr b{display:block;font-size:.93rem}.cr small{color:var(--mute)}.free{color:var(--mute);padding:.6rem 0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:.7rem}
.stat .v{font-size:1.9rem;font-weight:800}.stat .l{color:var(--mute);font-size:.88rem}
table{width:100%;border-collapse:collapse;font-size:.93rem}td,th{padding:.6rem .4rem;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--mute);font-weight:600}
.emb{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--c);border-radius:12px;padding:1rem 1.1rem;margin:.7rem 0}
.emb .et{font-weight:800;font-size:1.05rem;margin-bottom:.4rem}.emb .ed{line-height:1.6}
.emb .ef{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.7rem;margin-top:.7rem}
.emb .ef .full{grid-column:1/-1}.emb .fn{font-weight:700;font-size:.9rem;margin-bottom:.15rem}
.emb .fv{line-height:1.55}.emb .eft{color:var(--mute);font-size:.8rem;margin-top:.7rem}
code{background:#ffffff14;padding:.05rem .35rem;border-radius:5px;font-size:.88em}
.form .sec{margin-bottom:1rem}.form label{display:block;font-weight:600;margin:.9rem 0 .35rem}
.form small{color:var(--mute);display:block;margin-top:.3rem;font-size:.82rem}
.form input{width:100%;padding:.7rem .8rem;border-radius:10px;border:1px solid var(--line);background:var(--card2);color:var(--txt);font-size:1rem}
.form input:focus{outline:2px solid var(--blue);border-color:transparent}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:0 1rem}
.toast{background:#30d15818;border:1px solid var(--green);border-radius:12px;padding:.8rem 1rem;margin-bottom:1rem}
.row{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:1rem}
.sk{color:var(--mute)}
.tls{margin-top:.8rem;border-top:1px solid var(--line);padding-top:.6rem}
.tl{display:flex;gap:.5rem;padding:.25rem .4rem;border-radius:8px;color:var(--mute);font-variant-numeric:tabular-nums}
.tl span{width:1rem;text-align:center}.tl.main{background:#bf5af21f;color:var(--txt)}
.tl em{color:var(--orange);font-style:normal;font-weight:700}.tl i{color:var(--red);font-style:normal;font-size:.85em}
select{width:100%;padding:.7rem .8rem;border-radius:10px;border:1px solid var(--line);background:var(--card2);color:var(--txt);font-size:1rem}
.nav{display:flex;gap:.1rem}.nav a{white-space:nowrap}
@media(max-width:640px){.bar{gap:.5rem}.logo{flex:1 0 100%}.nav{flex:1;overflow-x:auto;scrollbar-width:none}
.nav a{padding:.4rem .65rem;font-size:.88rem}.opt .big{font-size:2.2rem}main{padding-top:.8rem}}
"""

HERO_JS = """
<script>
const q=location.search;
const B={ok:['b-ok',"À l'heure"],late:['b-late','Retard'],cancel:['b-cancel','Supprimé']};
fetch('/api/hero'+q).then(r=>r.json()).then(h=>{
  const el=document.getElementById('hero');
  if(h.error){el.innerHTML=`<div class=sk>⚠️ ${h.error}</div>`;return}
  let s=`<div class=hero-head><div class=d>${h.today?"Aujourd'hui":h.day}</div>`+
        (h.first?`<div class=s>1er cours <b>${h.first.start}</b> · ${h.first.summary}</div>`:'')+`</div>`;
  if(!h.first){el.innerHTML=s+'<p class=sk>Pas de cours à venir 🎉</p>';return}
  if(!h.options.length){el.innerHTML=s+'<p class=sk>Aucun train trouvé (clé PRIM configurée ?)</p>';return}
  s+='<div class=opts>'+h.options.map(o=>{
    if(o.none) return `<div class="opt"><div class=o>${o.emoji} ${o.origin}</div><div class=big style="color:var(--red)">—</div><div class=tr>Aucun train N trouvé</div></div>`;
    const b=B[o.status]||B.ok, dl=o.delay>0?` +${o.delay} min`:'';
    const list=(o.trains||[]).map(t=>`<div class="tl ${t.main?'main':''}"><span>${t.main?'▶':'·'}</span>`+
      `<b>${t.dep}</b>${t.delay>0?` <em>+${t.delay}</em>`:''} → ${t.arr}${t.late&&!t.main?' <i>trop tard</i>':''}</div>`).join('');
    return `<div class="opt ${o.best?'best':''}">${o.best?'<span class="tag badge b-best">⭐ Principal</span>':''}
      <div class=o>${o.emoji} ${o.origin}</div><div class=big>${o.leave}</div>
      <div class=tr>Départ de chez toi · <span class="badge ${b[0]}">${b[1]}${dl}</span></div>
      <div class=tls>${list}</div></div>`
  }).join('')+'</div>';
  el.innerHTML=s;
}).catch(()=>{document.getElementById('hero').innerHTML='<div class=sk>Erreur de chargement</div>'});
</script>"""


def _color(name: str) -> str:
    h = int(hashlib.md5(name.lower().encode()).hexdigest(), 16) % 360
    return f"hsl({h} 70% 60%)"


def md(text: str) -> str:
    """Mini rendu du markdown Discord (gras, barré, code, horodatages)."""
    t = e(text or "")

    def stamp(m):
        d = dt.datetime.fromtimestamp(int(m.group(1)), TZ)
        if m.group(2) == "R":
            mins = int((d - dt.datetime.now(TZ)).total_seconds() // 60)
            return f"dans {mins} min" if mins >= 0 else f"il y a {-mins} min"
        return d.strftime("%H:%M")

    t = re.sub(r"&lt;t:(\d+):([tR])&gt;", stamp, t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"~~(.+?)~~", r"<s>\1</s>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t.replace("\n", "<br>")


def render_card(c: dict) -> str:
    col = f"#{c.get('color', 0x636366):06x}"
    out = [f"<div class=emb style='--c:{col}'><div class=et>{md(c.get('title'))}</div>"]
    if c.get("description"):
        out.append(f"<div class=ed>{md(c['description'])}</div>")
    if c.get("fields"):
        out.append("<div class=ef>")
        for f in c["fields"]:
            out.append(f"<div class='{'' if f.get('inline') else 'full'}'><div class=fn>{md(f['name'])}</div>"
                       f"<div class=fv>{md(f['value'])}</div></div>")
        out.append("</div>")
    if c.get("footer"):
        out.append(f"<div class=eft>{md(c['footer']['text'])}</div>")
    out.append("</div>")
    return "".join(out)


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

    def page(body: str, request, active="/") -> web.Response:
        t = tok(request)
        links = [("/", "Accueil"), ("/train", "Trajet"), ("/retour", "Retour"), ("/config", "⚙️ Config")]
        nav = "".join(f"<a class='{'on' if p == active else ''}' href='{p}{t}'>{n}</a>" for p, n in links)
        miss = C.missing()
        warn = ""
        if miss and active != "/config":
            warn = (f"<div class='box warn' style='margin-bottom:1rem'>⚠️ Configuration incomplète "
                    f"(<code>{', '.join(miss)}</code>) — <a href='/config{t}'><u>compléter</u></a></div>")
        return web.Response(
            text=f"<!doctype html><html lang=fr><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                 f"<title>EDT & Trains</title><link rel=icon href='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 "
                 f"viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🚆</text></svg>'><style>{CSS}</style>"
                 f"<header><div class=bar><div class=logo>🚆 EDT & Trains</div><nav class=nav>{nav}</nav>"
                 f"<a class='btn ghost' href='/sync{t}' title='Actualiser l&#39;emploi du temps'>🔄</a></div></header>"
                 f"<main>{warn}{body}</main></html>",
            content_type="text/html")

    def err(ex, request, active="/"):
        return page(f"<div class='box warn'>❌ {e(str(ex))}</div>", request, active)

    # ---------- tableau de bord ----------
    async def index(request):
        edt = db.get("edt", {})
        today = dt.datetime.now(TZ).date()
        t = tok(request)
        out = ["<h2 style='margin-top:.4rem'>Prochain trajet</h2>",
               "<div class=box id=hero><div class=sk>Chargement des horaires…</div></div>",
               f"<div class=row><a class=btn href='/train?discord=1{tok(request, False)}'>📨 Envoyer le trajet sur Discord</a>"
               f"<a class='btn ghost' href='/retour{t}'>🏠 Trains retour</a></div>",
               "<h2>Cette semaine</h2><div class=week>"]
        for i in range(7):
            d = today + dt.timedelta(days=i)
            cs = edt.get(d.isoformat(), [])
            if not cs and d.weekday() >= 5:
                continue
            label = "Aujourd'hui" if i == 0 else ("Demain" if i == 1 else JOURS[d.weekday()])
            out.append(f"<div class='day{' today' if i == 0 else ''}'><div class=t>{label}<span>{d:%d/%m}</span></div>")
            if not cs:
                out.append("<div class=free>Pas cours 🎉</div>")
            for c in cs:
                out.append(f"<div class=cr style='--c:{_color(c['summary'])}'><b>{e(c['summary'])}</b>"
                           f"<small>{c['start']} – {c['end']}{' · ' + e(c['location']) if c['location'] else ''}</small></div>")
            out.append("</div>")
        out.append("</div>")

        rows = db.last_delays(50)
        if rows:
            n = len(rows)
            ok = sum(1 for r in rows if not r[5] and r[4] < C.get("DELAY_ALERT"))
            canc = sum(1 for r in rows if r[5])
            lates = [r[4] for r in rows if not r[5] and r[4] > 0]
            avg = round(sum(lates) / len(lates)) if lates else 0
            out.append("<h2>Statistiques</h2><div class=stats>"
                       f"<div class='box stat'><div class=v style='color:var(--green)'>{round(100 * ok / n)}%</div><div class=l>trains à l'heure</div></div>"
                       f"<div class='box stat'><div class=v style='color:var(--orange)'>{avg} min</div><div class=l>retard moyen</div></div>"
                       f"<div class='box stat'><div class=v style='color:var(--red)'>{canc}</div><div class=l>suppressions</div></div>"
                       f"<div class='box stat'><div class=v>{n}</div><div class=l>trains suivis</div></div></div>")
            out.append("<h2>Historique</h2><div class=box><table><tr><th>Jour</th><th>Gare</th><th>Train</th><th>État</th></tr>")
            for day, origin, mission, base_dep, delay, cancelled in rows[:20]:
                b = ("b-cancel", "Supprimé") if cancelled else (("b-late", f"+{delay} min") if delay > 0 else ("b-ok", "À l'heure"))
                out.append(f"<tr><td>{day[8:10]}/{day[5:7]}</td><td>{e(origin)}</td><td>{base_dep[11:16]} <code>{e(mission)}</code></td>"
                           f"<td><span class='badge {b[0]}'>{b[1]}</span></td></tr>")
            out.append("</table></div>")
        out.append(HERO_JS)
        return page("".join(out), request, "/")

    async def api_hero(_):
        try:
            return web.json_response(await actions["hero"]())
        except Exception as ex:
            return web.json_response({"error": str(ex)})

    # ---------- pages de cards ----------
    def cards_action(name, title, active):
        async def handler(request):
            try:
                cs = await actions[name]()
                sent = ""
                if request.query.get("discord") == "1":
                    sent = ("<div class=toast>✅ Envoyé sur Discord</div>" if await actions["send"](cs)
                            else "<div class='box warn'>❌ Envoi Discord impossible (webhook ?)</div>")
            except Exception as ex:
                return err(ex, request, active)
            body = (f"{sent}<h2 style='margin-top:.4rem'>{title}</h2>" + "".join(map(render_card, cs)) +
                    f"<div class=row><a class=btn href='?discord=1{tok(request, False)}'>📨 Envoyer sur Discord</a></div>")
            return page(body, request, active)
        return handler

    async def sync(request):
        try:
            n = await actions["sync"]()
        except Exception as ex:
            return err(ex, request)
        nb = sum(len(v) for v in db.get("edt", {}).values())
        return page(f"<div class=toast>✅ Emploi du temps récupéré : {nb} cours sur 30 jours · {n} jour(s) modifié(s)</div>"
                    f"<a class=btn href='/{tok(request)}'>← Tableau de bord</a>", request)

    # ---------- config ----------
    async def config_view(request):
        saved = db.get("settings", {})
        t = tok(request)
        out = ["<div class=toast>✅ Configuration enregistrée et appliquée</div>" if request.query.get("saved") else "",
               f"<form class=form method=post action='/config{t}'>"]
        open_sec = False
        for key, label, typ, default, hint in C.FIELDS:
            if key.startswith("__"):
                if open_sec:
                    out.append("</div></div>")
                out.append(f"<h2>{e(key[2:])}</h2><div class='box sec'><div class=grid2>")
                open_sec = True
                continue
            cur = str(saved.get(key, ""))
            if typ == "secret":
                ph = ("•••••••• enregistré — vide = inchangé" if C.get(key)
                      else "à remplir" if key in C.REQUIRED else "optionnel")
                inp = f"<input type=password name={key} placeholder='{e(ph)}' autocomplete=off>"
            elif typ == "int":
                inp = f"<input type=number min=0 name={key} value='{e(cur or str(C.get(key)))}'>"
            elif typ.startswith("choice:"):
                val = cur or C.get(key)
                inp = f"<select name={key}>" + "".join(
                    f"<option{' selected' if o == val else ''}>{e(o)}</option>" for o in typ[7:].split("|")) + "</select>"
            elif typ == "time":
                inp = f"<input type=time name={key} value='{e(C.get(key))}'>"
            else:
                inp = f"<input type=text name={key} value='{e(cur)}' placeholder='{e(default or 'optionnel')}'>"
            wide = " style='grid-column:1/-1'" if typ == "secret" or key.endswith("URL") else ""
            out.append(f"<div{wide}><label>{e(label)}</label>{inp}" + (f"<small>{e(hint)}</small>" if hint else "") + "</div>")
        if open_sec:
            out.append("</div></div>")
        out.append("<div class=row><button class=btn type=submit>💾 Enregistrer</button></div></form>")
        out.append(f"<h2>Tests</h2><div class=row><a class='btn ghost' href='/config/test/discord{t}'>📨 Webhook Discord</a>"
                   f"<a class='btn ghost' href='/config/test/prim{t}'>🚆 API PRIM</a>"
                   f"<a class='btn ghost' href='/sync{t}'>📅 Lien .ics</a></div>")
        return page("".join(out), request, "/config")

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
            cs = await actions[f"test_{name}"]()
        except Exception as ex:
            return err(ex, request, "/config")
        return page("".join(map(render_card, cs)) + f"<a class='btn ghost' href='/config{tok(request)}'>← Config</a>",
                    request, "/config")

    async def api(_):
        return web.json_response({"edt": db.get("edt", {})})

    app = web.Application(middlewares=[auth])
    app.router.add_get("/", index)
    app.router.add_get("/api/hero", api_hero)
    app.router.add_get("/train", cards_action("train", "Prochain trajet", "/train"))
    app.router.add_get("/retour", cards_action("retour", "Trains retour", "/retour"))
    app.router.add_get("/sync", sync)
    app.router.add_get("/config", config_view)
    app.router.add_post("/config", config_post)
    app.router.add_get("/config/test/{what}", test)
    app.router.add_get("/api", api)
    return app
