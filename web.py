"""Site web (mobile d'abord) : accueil avec le prochain départ, emploi du temps, trajet, réglages."""
import base64
import colorsys
import datetime as dt
import hashlib
import html
import re

from aiohttp import web

import config as C
import db
import monitor
import notifs
import push
from cards import JOURS
from config import TZ

e = html.escape

CSS = """
:root{--bg:#0b0c0e;--card:#1c1d21;--row:#26272c;--line:#34363d;--txt:#f3f4f6;--mute:#969ba6;--dim:#6b707a;
--blue:#0a84ff;--green:#30d158;--orange:#ff9f0a;--red:#ff453a;--purple:#bf5af2;--teal:#40c8e0;--n:#00a88f;--m6:#6eca97;
--safe:env(safe-area-inset-bottom,0px);--safe-top:env(safe-area-inset-top,0px)}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}html{color-scheme:dark}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Inter,system-ui,sans-serif;
background:var(--bg);color:var(--txt);font-size:16px;line-height:1.4}
a{color:inherit;text-decoration:none}
main{max-width:760px;margin:auto;padding:12px 16px calc(96px + var(--safe))}
.top{display:flex;align-items:center;gap:10px;max-width:760px;margin:auto;padding:calc(16px + var(--safe-top)) 16px 0}
.top h1{font-size:28px;margin:0;letter-spacing:-.03em;flex:1}
.ibtn{width:42px;height:42px;border-radius:14px;background:var(--card);display:grid;place-items:center}
.ibtn svg{width:20px;height:20px}
nav.tabs{position:fixed;left:0;right:0;bottom:0;z-index:10;background:#131417ee;backdrop-filter:blur(18px);
-webkit-backdrop-filter:blur(18px);border-top:1px solid var(--line);display:flex;padding:6px 6px calc(6px + var(--safe))}
nav.tabs a{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;padding:6px 0;color:var(--dim);font-size:11px;font-weight:600}
nav.tabs a svg{width:24px;height:24px}nav.tabs a.on{color:var(--blue)}
@media(min-width:900px){nav.tabs{top:var(--safe-top);bottom:auto;left:50%;right:auto;transform:translateX(-50%);margin-top:12px;
border:1px solid var(--line);border-radius:16px;padding:4px;gap:2px}
nav.tabs a{flex-direction:row;padding:8px 14px;font-size:14px;border-radius:12px;gap:8px}nav.tabs a svg{width:18px;height:18px}
nav.tabs a.on{background:var(--row);color:var(--txt)}.top{padding-top:calc(76px + var(--safe-top))}main{padding-bottom:40px}}
.lbl{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);margin:24px 4px 10px}
.card{background:var(--card);border-radius:22px;padding:18px;position:relative;overflow:hidden}
.card.acc::before{content:"";position:absolute;inset:0 0 auto 0;height:4px;background:var(--a,var(--blue))}
.k{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--a,var(--blue))}
.big{font-size:68px;font-weight:800;letter-spacing:-.045em;line-height:1;margin:10px 0 6px;font-variant-numeric:tabular-nums}
.sub{color:var(--mute)}.sub b{color:var(--txt)}
.chip{display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:999px;font-size:13px;font-weight:700;background:var(--row);white-space:nowrap}
.c-ok{color:var(--green);background:#30d15824}.c-late{color:var(--orange);background:#ff9f0a24}
.c-cancel{color:var(--red);background:#ff453a24}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.sp{justify-content:space-between}
.steps{margin-top:20px}
.st{display:grid;grid-template-columns:58px 22px 1fr;align-items:start;min-height:56px}
.st .t{font-weight:800;font-size:18px;font-variant-numeric:tabular-nums}
.st .t.o{color:var(--orange)}.st .t.r{color:var(--red)}
.st .d{position:relative;align-self:stretch}
.st .d::before{content:"";position:absolute;left:50%;top:4px;width:14px;height:14px;margin-left:-7px;border-radius:50%;
border:3px solid var(--txt);background:var(--card);z-index:1;box-sizing:border-box}
.st .d::after{content:"";position:absolute;left:50%;top:20px;bottom:0;width:4px;margin-left:-2px;border-radius:2px;background:var(--lc,var(--line))}
.st.dash .d::after{background:repeating-linear-gradient(var(--dim) 0 5px,transparent 5px 10px)}
.st:last-child .d::after{display:none}.st:last-child .d::before,.st:first-child .d::before{background:var(--txt)}
.st.warn .d::before{border-color:var(--red);background:var(--red)}
.st .n{padding:0 0 16px 8px}.st .n b{display:block;font-size:16px}
.leg{display:inline-block;margin-top:6px;padding:3px 9px;border-radius:8px;font-size:12px;font-weight:700;background:var(--row);color:var(--txt)}
.leg.N{background:var(--n);color:#03251f}.leg.m6{background:var(--m6);color:#08301d}.leg span{font-weight:500;opacity:.8;margin-left:5px}
details.alt{background:var(--card);border-radius:18px;margin-top:10px}
details.alt summary{list-style:none;padding:14px 16px;display:flex;align-items:center;gap:10px;cursor:pointer}
details.alt summary::-webkit-details-marker{display:none}details.alt .in{padding:0 16px 6px}
.alt .tm{font-weight:800;font-size:24px;font-variant-numeric:tabular-nums}.chev{margin-left:auto;color:var(--dim);font-size:26px;transition:.2s}
details[open] .chev{transform:rotate(90deg)}
.ret{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.ret h4{margin:0 0 8px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--mute)}
.tr{background:var(--row);border-radius:14px;padding:10px 12px;margin-bottom:8px;display:flex;align-items:baseline;gap:6px;font-variant-numeric:tabular-nums}
.tr b{font-size:19px}.tr small{color:var(--mute)}.tr.first{background:#40c8e01f;box-shadow:inset 0 0 0 1px #40c8e055}
.tr em{margin-left:auto;font-style:normal;color:var(--orange);font-weight:700;font-size:13px}
.days{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;margin:4px -16px 0;padding:2px 16px 6px}
.days::-webkit-scrollbar{display:none}
.day{flex:0 0 auto;width:58px;padding:10px 0;border-radius:16px;background:var(--card);text-align:center;cursor:pointer}
.day small{display:block;color:var(--mute);font-size:11px;font-weight:700;text-transform:uppercase}
.day b{font-size:21px}.day i{display:block;width:6px;height:6px;border-radius:3px;margin:5px auto 0;background:transparent}
.day.has i{background:var(--blue)}.day.on{background:var(--blue)}.day.on small{color:#ffffffcc}.day.on i{background:#fff}
.dpanel{display:none}.dpanel.on{display:block}
.dsum{color:var(--mute);margin:0 4px 10px;display:flex;justify-content:space-between;font-size:14px}
.crs{display:grid;grid-template-columns:54px 6px 1fr auto;gap:12px;align-items:center;background:var(--card);
border-radius:18px;padding:13px 14px;margin-bottom:8px}
.crs .ct b{display:block;font-size:18px;font-variant-numeric:tabular-nums}.crs .ct small{color:var(--mute);font-variant-numeric:tabular-nums}
.crs .bar{height:40px;border-radius:3px;background:var(--c)}
.crs .bar.dash{background:repeating-linear-gradient(var(--c) 0 6px,transparent 6px 11px)}
.crs .cn{min-width:0}.crs .cn b{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;font-size:16px;overflow:hidden;line-height:1.25}
.crs .cn small{color:var(--mute);display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.crs .cc{display:flex;flex-direction:column;gap:5px;align-items:flex-end}
.crs.now{box-shadow:inset 0 0 0 2px var(--green)}.crs.past{opacity:.45}
.tag{font-size:11px;font-weight:700;padding:4px 8px;border-radius:8px;background:var(--row);white-space:nowrap}
.tag.on{color:var(--teal);background:#40c8e024}.tag.now{color:var(--green);background:#30d15824}
.pause{display:flex;align-items:center;gap:10px;color:var(--dim);font-size:13px;font-weight:600;margin:2px 0 10px 80px}
.pause::after{content:"";flex:1;height:1px;background:var(--line)}
.free{text-align:center;color:var(--mute);padding:48px 0;font-size:18px}
.stats{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.stat{background:var(--card);border-radius:18px;padding:14px 16px}.stat b{font-size:28px;display:block;letter-spacing:-.02em}.stat small{color:var(--mute)}
@media(min-width:600px){.stats{grid-template-columns:repeat(4,1fr)}}
.hist{background:var(--card);border-radius:18px;padding:2px 16px}
.hrow{display:flex;align-items:center;gap:10px;padding:12px 0;border-bottom:1px solid var(--line)}.hrow:last-child{border:0}
.hrow span:first-child{color:var(--mute);font-size:14px;width:48px}.hrow b{flex:1;font-weight:600}
.btn{display:flex;align-items:center;justify-content:center;gap:8px;background:var(--blue);color:#fff;border:0;border-radius:16px;
padding:15px 16px;font-weight:700;font-size:16px;cursor:pointer;width:100%;font-family:inherit}
.btn.g{background:var(--card);color:var(--txt)}.btns{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}
.warn{background:#ff9f0a1c;color:#ffd08a;border-radius:16px;padding:12px 14px;margin-bottom:12px}
.ok{background:#30d1581c;color:#9ff0b4;border-radius:16px;padding:12px 14px;margin-bottom:12px}
.sk{color:var(--mute);padding:6px 0}
.shimmer{height:14px;border-radius:7px;background:linear-gradient(90deg,var(--row),var(--line),var(--row));background-size:200% 100%;animation:sh 1.2s infinite}
@keyframes sh{to{background-position:-200% 0}}
img.full{width:100%;display:block;border-radius:18px;margin-bottom:12px}
code{background:#ffffff14;padding:1px 6px;border-radius:6px;font-size:.9em}
.form label{display:block;font-weight:600;margin:14px 2px 6px;font-size:15px}.form label:first-child{margin-top:0}
.form small{color:var(--mute);display:block;margin:6px 2px 0;font-size:13px}
.form input,.form select{width:100%;padding:13px 14px;border-radius:12px;border:1px solid var(--line);background:var(--row);color:var(--txt);font-size:16px;font-family:inherit}
.form input:focus,.form select:focus{outline:2px solid var(--blue);border-color:transparent}
.ico{width:46px;height:46px;border-radius:50%;display:grid;place-items:center;flex:0 0 auto;background:var(--a);
color:#111;font-weight:900;font-size:22px;box-shadow:0 0 0 6px color-mix(in srgb,var(--a) 25%,transparent)}
.hd{display:flex;gap:14px;align-items:center}.hd h2{margin:2px 0 0;font-size:24px;letter-spacing:-.02em;line-height:1.15}
.h2{font-size:26px;font-weight:800;letter-spacing:-.02em;margin:4px 0 2px;line-height:1.15}
.bk{background:var(--row);border-radius:14px;padding:11px 13px;margin-top:8px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.bk b{font-variant-numeric:tabular-nums;margin-right:4px}.bk .chip{background:var(--line);font-size:12px;padding:4px 9px}
.chg{display:flex;gap:10px;align-items:center;background:var(--row);border-radius:14px;padding:11px 12px;margin-top:8px}
.chg b{flex:1;min-width:0}.chg small{display:block;color:var(--mute);font-weight:400}
.c-add{color:var(--green);background:#30d15824}.c-mod{color:var(--orange);background:#ff9f0a24}
.block{margin-bottom:14px}
.mon{display:block;background:var(--card);border-radius:18px;padding:14px 16px;margin-bottom:8px}
.mon .mt{display:flex;align-items:center;gap:12px}.mon .mt b{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mon small{color:var(--mute)}.mon .mr{text-align:right;font-variant-numeric:tabular-nums;font-size:14px;color:var(--mute);white-space:nowrap}
.mon .mr b{color:var(--txt);display:block;font-size:16px}
.dot{width:12px;height:12px;border-radius:50%;flex:0 0 auto;background:var(--dim)}
.dot.up{background:var(--green);box-shadow:0 0 0 4px #30d15833}.dot.down{background:var(--red);box-shadow:0 0 0 4px #ff453a40;animation:pulse 1.4s infinite}
.dot.pend{background:var(--orange)}.dot.paused{background:transparent;border:2px solid var(--dim)}
@keyframes pulse{50%{box-shadow:0 0 0 7px #ff453a10}}
.beats{display:flex;gap:3px;margin-top:12px;height:22px;align-items:stretch}
.beats i{flex:1;border-radius:3px;background:var(--line)}.beats i.u{background:var(--green)}.beats i.d{background:var(--red)}
.chart{width:100%;height:150px;display:block;margin-top:8px}
.grid4{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}@media(min-width:600px){.grid4{grid-template-columns:repeat(4,1fr)}}
.inc{display:flex;gap:10px;align-items:center;padding:11px 0;border-bottom:1px solid var(--line)}.inc:last-child{border:0}
.inc b{flex:1;font-weight:600}.inc small{color:var(--mute);display:block;font-weight:400}
.form textarea{width:100%;min-height:120px;padding:13px 14px;border-radius:12px;border:1px solid var(--line);background:var(--row);color:var(--txt);font-size:15px;font-family:inherit}
.form .ck{display:flex;align-items:center;gap:10px;margin-top:16px;font-weight:600}.form .ck input{width:22px;height:22px}
.btn.red{background:#ff453a22;color:var(--red)}
.fab{position:fixed;right:18px;bottom:calc(84px + var(--safe));z-index:9;width:56px;height:56px;border-radius:18px;background:var(--blue);
color:#fff;display:grid;place-items:center;font-size:30px;font-weight:300;box-shadow:0 8px 24px #0a84ff55}
@media(min-width:900px){.fab{bottom:28px}}
.emb{background:var(--card);border-radius:18px;padding:16px;margin-bottom:12px;border-left:4px solid var(--c)}
.emb .et{font-weight:800;margin-bottom:6px}.emb .ef{display:grid;gap:10px;margin-top:10px}.emb .fn{font-weight:700;font-size:14px}
"""

ICONS = {
    "home": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>',
    "cal": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="4.5" width="18" height="16.5" rx="3"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/></svg>',
    "train": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="3" width="14" height="14" rx="4"/><path d="M5 11h14M9 21l1.5-4M15 21l-1.5-4"/></svg>',
    "pulse": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg>',
    "gear": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/></svg>',
    "sync": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/></svg>',
}

HOME_JS = r"""
<script>
const q=location.search;
const S={ok:['c-ok',"À l'heure"],late:['c-late','Retard'],cancel:['c-cancel','Supprimé']};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function steps(r){
  if(!r) return '';
  let h='<div class=steps>';
  r.stops.forEach((s,i)=>{
    const L=r.legs[i];
    const cls=L?(L.kind==='N'?'N':(L.kind==='6'?'m6':'')):'';
    const lc=L?(L.kind==='N'?'var(--n)':(L.kind==='6'?'var(--m6)':'')):'';
    const dash=L&&(L.kind==='walk'||L.kind==='car');
    const tc=s.warn?'r':(s.delay?'o':'');
    h+=`<div class="st ${dash?'dash':''} ${s.warn?'warn':''}" style="--lc:${lc}"><div class="t ${tc}">${esc(s.time)}</div><div class=d></div>
    <div class=n><b>${esc(s.name)}${s.delay?` <span class="chip c-late">+${s.delay}</span>`:''}</b>
    ${L?`<span class="leg ${cls}">${esc(L.label)}${L.detail?`<span>${esc(L.detail)}</span>`:''}</span>`:''}</div></div>`;
  });
  return h+'</div>';
}
fetch('/api/hero'+q).then(r=>r.json()).then(h=>{
  const el=document.getElementById('hero');
  if(h.error){el.innerHTML=`<div class=card><div class=sk>⚠️ ${esc(h.error)}</div></div>`;return}
  const when=h.today?"Aujourd'hui":esc(h.day);
  if(!h.first){el.innerHTML=`<div class=card><div class=k>Prochain départ</div><div class=sk style="margin-top:8px">Pas de cours sur place à venir 🎉</div></div>`;return}
  const o=h.options.find(x=>!x.none);
  if(!o){el.innerHTML=`<div class=card><div class=k>${when}</div><div class=sk>Aucun train trouvé — clé PRIM configurée ?</div></div>`;return}
  const st=S[o.status]||S.ok, late=o.chain&&o.chain.late;
  const acc=o.status==='cancel'?'var(--red)':(late||o.status==='late'?'var(--orange)':'var(--purple)');
  let s=`<div class="card acc" style="--a:${acc}"><div class="row sp"><div class=k>${when} · 1er cours ${esc(h.first.start)}</div>
    <span class="chip ${st[0]}">${st[1]}${o.delay>0?' +'+o.delay+' min':''}</span></div>
    <div class=big>${esc(o.leave)}</div>
    <div class=sub>Départ de chez toi · <b>${esc(o.origin)}</b> · train <b>${esc(o.dep)}</b>${o.chain?` · ${esc(o.chain.school)} <b>${esc(o.chain.school_arr)}</b>`:''}</div>
    ${late?'<div class="warn" style="margin:12px 0 0">Tu arriveras après le début du cours</div>':''}
    ${steps(o.route)}`;
  const others=(o.trains||[]).filter(t=>!t.main);
  if(others.length) s+=`<div class=row><span class=sub style="font-size:14px">Autres trains</span>`+
    others.map(t=>`<span class="chip ${t.late?'c-cancel':''}">${t.dep}${t.delay>0?' +'+t.delay:''}${t.late?' · trop tard':''}</span>`).join('')+`</div>`;
  s+='</div>';
  h.options.filter(x=>x!==o&&!x.none).forEach(a=>{
    s+=`<details class=alt><summary><div><div class=k style="--a:var(--mute)">Autre option · ${esc(a.origin)}</div>
      <div><span class=tm>${esc(a.leave)}</span> <span class=sub>· train ${esc(a.dep)}${a.chain?' · '+esc(a.chain.school)+' '+esc(a.chain.school_arr):''}</span></div></div>
      <span class=chev>›</span></summary><div class=in>${steps(a.route)}</div></details>`;
  });
  if(h.retour){
    s+=`<div class=lbl>Retour · fin à ${esc(h.retour.end)}</div><div class=card><div class=ret>`+
      h.retour.cols.map((c,i)=>`<div><h4>Vers ${esc(c.name)}</h4>`+
        (c.trips.length?c.trips.map((t,j)=>`<div class="tr ${i===0&&j===0?'first':''}"><b>${t.dep}</b><small>→ ${t.arr}</small>${t.delay>0?`<em>+${t.delay}</em>`:''}</div>`).join(''):'<div class=sk>Aucun train</div>')+
      `</div>`).join('')+`</div></div>`;
  }
  el.innerHTML=s;
}).catch(()=>{document.getElementById('hero').innerHTML='<div class=card><div class=sk>Erreur de chargement</div></div>'});
</script>"""

EDT_JS = """
<script>
document.querySelectorAll('.day').forEach(d=>d.onclick=()=>{
  document.querySelectorAll('.day,.dpanel').forEach(x=>x.classList.remove('on'));
  d.classList.add('on');document.getElementById('p'+d.dataset.d).classList.add('on');
  d.scrollIntoView({inline:'center',behavior:'smooth',block:'nearest'});
});
const on=document.querySelector('.day.on');on&&on.scrollIntoView({inline:'center',block:'nearest'});
</script>"""


def _color(name: str) -> str:
    h = int(hashlib.md5(name.lower().encode()).hexdigest(), 16) % 360
    r, g, b = colorsys.hls_to_rgb(h / 360, 0.62, 0.65)
    return f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"


def _min(hm):
    h, m = map(int, hm.split(":"))
    return h * 60 + m


def course_rows(courses, day=None):
    """Liste des cours (même style que l'image Discord), avec pauses et cours en cours."""
    now = dt.datetime.now(TZ)
    is_today = day == now.date()
    nowm = now.hour * 60 + now.minute
    out, prev = [], None
    for c in courses:
        virt = c.get("virtual")
        if prev and not virt:
            gap = _min(c["start"]) - _min(prev)
            if gap >= 30:
                hh, mm = divmod(gap, 60)
                out.append(f"<div class=pause>Pause · {f'{hh} h {mm:02d}' if hh else f'{mm} min'}</div>")
        st = ""
        if is_today:
            if _min(c["start"]) <= nowm < _min(c["end"]):
                st = "now"
            elif nowm >= _min(c["end"]):
                st = "past"
        tags = []
        if st == "now":
            tags.append("<span class='tag now'>EN COURS</span>")
        if c.get("type"):
            tags.append(f"<span class=tag>{e(c['type'])}</span>")
        if virt:
            tags.append("<span class='tag on'>EN LIGNE</span>")
        meta = "Cours à distance" if virt else (c.get("location") or "")
        out.append(f"<div class='crs {st}'><div class=ct><b>{c['start']}</b><small>{c['end']}</small></div>"
                   f"<i class='bar{' dash' if virt else ''}' style='--c:{_color(c['summary'])}'></i>"
                   f"<div class=cn><b>{e(c['summary'])}</b><small>{e(meta)}</small></div>"
                   f"<div class=cc>{''.join(tags)}</div></div>")
        if not virt:
            prev = c["end"]
    return "".join(out)


def steps_html(r) -> str:
    """Frise verticale (même rendu que l'accueil)."""
    if not r:
        return ""
    out = ["<div class=steps>"]
    for i, s in enumerate(r["stops"]):
        L = r["legs"][i] if i < len(r["legs"]) else None
        kind = (L or {}).get("kind")
        cls = "N" if kind == "N" else ("m6" if kind == "6" else "")
        lc = "var(--n)" if kind == "N" else ("var(--m6)" if kind == "6" else "")
        dash = kind in ("walk", "car")
        tc = "r" if s.get("warn") else ("o" if s.get("delay") else "")
        leg = (f"<span class='leg {cls}'>{e(L['label'])}" + (f"<span>{e(L['detail'])}</span>" if L.get("detail") else "")
               + "</span>") if L else ""
        delay = f" <span class='chip c-late'>+{s['delay']}</span>" if s.get("delay") else ""
        out.append(f"<div class='st {'dash' if dash else ''} {'warn' if s.get('warn') else ''}' style='--lc:{lc}'>"
                   f"<div class='t {tc}'>{e(s['time'])}</div><div class=d></div>"
                   f"<div class=n><b>{e(s['name'])}{delay}</b>{leg}</div></div>")
    out.append("</div>")
    return "".join(out)


def _pills(items, label):
    if not items:
        return ""
    return (f"<div class=row><span class=sub style='font-size:14px'>{label}</span>"
            + "".join(f"<span class='chip {'c-cancel' if w else ''}'>{e(t)}</span>" for t, w in items) + "</div>")


def _backups(items):
    if not items:
        return ""
    return ("<div class=lbl style='margin:16px 0 4px'>Sans le N</div>"
            + "".join(f"<div class=bk><b>{e(b['dep'])} → {e(b['arr'])}</b>"
                      + "".join(f"<span class=chip>{e(x)}</span>" for x in b["legs"]) + "</div>" for b in items))


def render_data(d: dict) -> str:
    """Affichage natif (HTML) d'une card : notifications, pages Trajet / Retour."""
    t = d.get("type")
    if t == "edt":
        day = dt.date.fromisoformat(d["day"]) if d.get("day") else None
        body = course_rows(d["courses"], day) if d["courses"] else "<div class=free>Pas cours</div>"
        return (f"<div class=block><div class=lbl style='margin-top:4px'>{e(d['title'])}"
                + (f" · {e(d['subtitle'])}" if d.get("subtitle") else "") + f"</div>{body}</div>")
    if t == "aller":
        acc = "var(--mute)" if d.get("alt") else ("var(--orange)" if d.get("late") else "var(--purple)")
        if d.get("alt"):
            return (f"<details class='alt block'><summary><div><div class=k style='--a:var(--mute)'>Autre option · "
                    f"{e(d.get('origin', ''))}</div><div><span class=tm>{e(d.get('leave', ''))}</span> "
                    f"<span class=sub>· {e(d.get('sub', ''))}</span></div></div><span class=chev>›</span></summary>"
                    f"<div class=in>{steps_html(d.get('route'))}</div></details>")
        chip = "<span class='chip c-cancel'>En retard</span>" if d.get("late") else "<span class='chip' style='color:var(--purple);background:#bf5af224'>Conseillé</span>"
        big = f"<div class=big>{e(d['leave'])}</div>" if d.get("leave") else f"<div class=h2>{e(d['title'])}</div>"
        origin = f"Départ de chez toi · <b>{e(d.get('origin', ''))}</b><br>" if d.get("leave") else ""
        return (f"<div class='card acc block' style='--a:{acc}'><div class='row sp'><div class=k>Trajet du matin</div>{chip}</div>"
                f"{big}<div class=sub>{origin}{e(d.get('sub', ''))}</div>{steps_html(d.get('route'))}"
                f"{_pills(d.get('others'), 'Autres trains')}{_backups(d.get('backups'))}</div>")
    if t == "status":
        k = d["kind"]
        acc, ico, lab = {"ok": ("var(--green)", "✓", "Train à l'heure"), "late": ("var(--orange)", "!", "Retard"),
                         "cancel": ("var(--red)", "✕", "Train supprimé")}[k]
        return (f"<div class='card acc block' style='--a:{acc}'><div class=hd><div class=ico>{ico}</div>"
                f"<div><div class=k>{lab}</div><h2>{e(d['title'])}</h2></div></div>"
                f"<div class=sub style='margin-top:10px'>{e(d['sub'])}</div>{steps_html(d.get('route'))}"
                f"{_pills(d.get('others'), 'Autres trains N')}{_backups(d.get('backups'))}</div>")
    if t == "retour":
        cols = "".join(
            f"<div><h4>Vers {e(c['name'])}</h4>"
            + ("".join(f"<div class='tr {'first' if i == 0 and j == 0 else ''}'><b>{x['dep']}</b><small>→ {x['arr']}</small>"
                       + (f"<em>+{x['delay']}</em>" if x.get("delay") and x["delay"] > 0 else "") + "</div>"
                       for j, x in enumerate(c["trips"])) or "<div class=sk>Aucun train</div>") + "</div>"
            for i, c in enumerate(d["cols"]))
        return (f"<div class='card acc block' style='--a:var(--teal)'><div class=k>Retour</div><div class=h2>{e(d['title'])}</div>"
                f"<div class=sub style='margin-bottom:14px'>{e(d['subtitle'])}</div><div class=ret>{cols}</div></div>")
    if t == "changes":
        tags = {"add": ("c-add", "Nouveau"), "del": ("c-cancel", "Annulé"), "mod": ("c-mod", "Déplacé")}
        g = "".join(f"<div class=lbl style='margin:14px 0 2px'>{e(x['day'])}</div>"
                    + "".join(f"<div class=chg><span class='chip {tags[i['kind']][0]}'>{tags[i['kind']][1]}</span>"
                              f"<b>{e(i['name'])}<small>{e(i['detail'])}</small></b></div>" for i in x["items"])
                    for x in d["groups"])
        return (f"<div class='card acc block' style='--a:var(--orange)'><div class=k>Emploi du temps modifié</div>"
                f"<div class=h2>{d['n']} changement{'s' if d['n'] > 1 else ''}</div>{g}</div>")
    if t == "virtual":
        c = d["course"]
        return (f"<div class='card acc block' style='--a:var(--teal)'><div class='row sp'><div class=k>Cours en ligne</div>"
                f"<span class='chip' style='color:var(--teal);background:#40c8e024'>En ligne</span></div>"
                f"<div class=big style='font-size:44px'>{e(c['start'])} – {e(c['end'])}</div>"
                f"<div class=h2 style='font-size:21px'>{e(c['summary'])}</div>"
                f"<div class=sub>{e(c.get('type') or '')} · ouvre l'app de l'école pour te mettre présent</div></div>")
    if t == "monitor":
        acc, ico, lab = {"down": ("var(--red)", "✕", "Service hors ligne"), "up": ("var(--green)", "✓", "Service de retour"),
                         "ssl": ("var(--orange)", "!", "Certificat bientôt expiré")}[d["kind"]]
        return (f"<div class='card acc block' style='--a:{acc}'><div class=hd><div class=ico>{ico}</div>"
                f"<div><div class=k>{lab}</div><h2>{e(d['name'])}</h2></div></div>"
                f"<div class=sub style='margin-top:8px;word-break:break-all'>{e(d['target'])}</div>"
                f"<div class=bk style='margin-top:12px'><b>{e(d['line'])}</b></div>"
                f"<div class=row style='margin-top:10px'>{''.join(f'<span class=chip>{e(x)}</span>' for x in d['chips'])}</div>"
                f"<a class='btn g' style='margin-top:14px' href='/services/{d['id']}'>Voir le service</a></div>")
    if t == "simple":
        return (f"<div class='card acc block' style='--a:var(--green)'><div class=hd><div class=ico>✓</div>"
                f"<div><div class=k>{e(d.get('label', ''))}</div><h2>{e(d['title'])}</h2></div></div>"
                f"<div class=sub style='margin-top:10px'>{e(d.get('sub', ''))}</div></div>")
    if t == "text":
        return render_card(d["card"])
    return ""


def show(c: dict) -> str:
    """Card → HTML natif si possible, sinon image ou texte."""
    return render_data(c["_data"]) if c.get("_data") else render_card(c)


def md(text: str) -> str:
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
    """Card : image si disponible, sinon version texte."""
    if c.get("_png"):
        return (f"<img class=full alt='{e(c.get('title', ''))}' "
                f"src='data:image/png;base64,{base64.b64encode(c['_png']).decode()}'>")
    col = f"#{c.get('color', 0x636366):06x}"
    out = [f"<div class=emb style='--c:{col}'><div class=et>{md(c.get('title'))}</div>"]
    if c.get("description"):
        out.append(f"<div>{md(c['description'])}</div>")
    if c.get("fields"):
        out.append("<div class=ef>" + "".join(f"<div><div class=fn>{md(f['name'])}</div><div>{md(f['value'])}</div></div>"
                                             for f in c["fields"]) + "</div>")
    out.append("</div>")
    return "".join(out)


# ---------- surveillance (services) ----------
def urlparse_host(target: str) -> str:
    from urllib.parse import urlparse
    return urlparse(target).hostname or target if "://" in target else target


def _ago(ts):
    if not ts:
        return "jamais"
    s = int(dt.datetime.now().timestamp() - ts)
    return f"il y a {s} s" if s < 90 else (f"il y a {s // 60} min" if s < 5400 else f"il y a {s // 3600} h")


def beats_html(rows, n=40):
    rows = rows[-n:]
    pad = "".join("<i></i>" for _ in range(n - len(rows)))
    return ("<div class=beats>" + pad + "".join(
        f"<i class='{'u' if ok else 'd'}' title='{e(dt.datetime.fromtimestamp(ts, TZ).strftime('%H:%M'))} · "
        f"{e(msg or '')}{f' · {ms} ms' if ok else ''}'></i>" for ts, ok, ms, msg in rows) + "</div>")


def chart_svg(rows):
    """Courbe des temps de réponse (SVG, sans librairie)."""
    pts = [(ts, ms, ok) for ts, ok, ms, _ in rows]
    if len(pts) < 2:
        return "<div class=sk>Pas encore assez de mesures</div>"
    W_, H_, P = 600, 150, 6
    t0, t1 = pts[0][0], pts[-1][0]
    okms = [ms for _, ms, ok in pts if ok] or [1]
    top = max(max(okms) * 1.15, 40)
    X = lambda t: P + (W_ - 2 * P) * (t - t0) / max(1, t1 - t0)
    Y = lambda v: H_ - 22 - (H_ - 34) * min(v, top) / top
    line = " ".join(f"{X(t):.1f},{Y(ms):.1f}" for t, ms, ok in pts if ok)
    first_x = next((X(t) for t, _, ok in pts if ok), P)
    last_x = next((X(t) for t, _, ok in reversed(pts) if ok), W_ - P)
    fails = "".join(f"<rect x='{X(t) - 1.5:.1f}' y='{H_ - 18}' width='3' height='12' rx='1.5' fill='#ff453a'/>"
                    for t, _, ok in pts if not ok)
    lab = lambda t: dt.datetime.fromtimestamp(t, TZ).strftime("%H:%M")
    return (f"<svg class=chart viewBox='0 0 {W_} {H_}' preserveAspectRatio='none'>"
            "<defs><linearGradient id=g x1=0 y1=0 x2=0 y2=1><stop offset=0 stop-color='#0a84ff' stop-opacity='.35'/>"
            "<stop offset=1 stop-color='#0a84ff' stop-opacity='0'/></linearGradient></defs>"
            + (f"<polygon fill='url(#g)' points='{first_x:.1f},{H_ - 22} {line} {last_x:.1f},{H_ - 22}'/>"
               f"<polyline fill=none stroke='#0a84ff' stroke-width='2.5' stroke-linejoin=round points='{line}' "
               f"vector-effect=non-scaling-stroke/>" if line else "")
            + fails + "</svg>"
            f"<div class='row sp sub' style='font-size:12px'><span>{lab(t0)}</span>"
            f"<span>max {max(okms)} ms</span><span>{lab(t1)}</span></div>")


def monitor_form(m: dict | None, action: str) -> str:
    m = m or {"name": "", "type": "http", "target": "", "interval": 60, "timeout": 10, "keyword": "",
              "accepted": "200-399", "retries": 2, "notify": 1, "ssl_days": 14}
    opts = "".join(f"<option value={k}{' selected' if m['type'] == k else ''}>{v}</option>"
                   for k, v in monitor.TYPES.items())
    return f"""<form class=form method=post action="{action}"><div class=card>
<label>Type</label><select name=type id=mtype>{opts}</select>
<label>Adresse</label><input name=target required value="{e(m['target'])}" placeholder="https://exemple.fr · 192.168.1.10:8123 · 1.1.1.1">
<small id=thint>URL du site (https:// ajouté si besoin)</small>
<label>Nom</label><input name=name value="{e(m['name'])}" placeholder="vide = nom du domaine">
<div id=kw><label>Mot-clé attendu dans la page</label><input name=keyword value="{e(m['keyword'])}" placeholder="ex. Home Assistant"></div>
<div id=codes><label>Codes HTTP acceptés</label><input name=accepted value="{e(m['accepted'])}"><small>ex. 200-399 ou 200,401</small></div>
</div><div class=lbl>Vérification</div><div class=card><div class=grid4 style="gap:0 12px">
<div><label>Toutes les (s)</label><input type=number inputmode=numeric name=interval min=20 value="{m['interval']}"></div>
<div><label>Délai max (s)</label><input type=number inputmode=numeric name=timeout min=2 value="{m['timeout']}"></div>
<div><label>Échecs avant alerte</label><input type=number inputmode=numeric name=retries min=1 value="{m['retries']}"></div>
<div><label>Alerte SSL (jours)</label><input type=number inputmode=numeric name=ssl_days min=0 value="{m['ssl_days']}"></div>
</div><label class=ck><input type=checkbox name=notify value=1{' checked' if m['notify'] else ''}> Notifications (Discord / téléphone)</label>
</div><div style="margin-top:14px"><button class=btn>Enregistrer</button></div></form>
<script>
const ty=document.getElementById('mtype'),kw=document.getElementById('kw'),co=document.getElementById('codes'),th=document.getElementById('thint');
function upd(){{const v=ty.value;kw.style.display=v==='keyword'?'':'none';co.style.display=(v==='http'||v==='keyword')?'':'none';
th.textContent={{http:"URL du site (https:// ajouté si besoin)",keyword:"URL de la page à vérifier",tcp:"hôte:port, ex. 192.168.1.10:8123",ping:"IP ou nom d'hôte"}}[v]}}
ty.onchange=upd;upd();
</script>"""


MANIFEST = {"name": "EDT & Trains", "short_name": "EDT", "id": "/", "start_url": "/", "scope": "/",
            "display": "standalone", "background_color": "#0b0c0e", "theme_color": "#0b0c0e",
            "icons": [{"src": "/icon-180.png", "sizes": "180x180", "type": "image/png"},
                      {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}
PUBLIC = ("/manifest.json", "/icon.svg", "/icon-180.png", "/icon-512.png", "/sw.js")

PUSH_JS = r"""
<script>
(function(){
const q=location.search, st=document.getElementById('pstat'), btn=document.getElementById('pbtn');
const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone;
const ios=/iphone|ipad|ipod/i.test(navigator.userAgent);
const b64=s=>{s=s.replace(/-/g,'+').replace(/_/g,'/');const r=atob(s+'='.repeat((4-s.length%4)%4));return Uint8Array.from([...r].map(c=>c.charCodeAt(0)))};
const post=(u,d)=>fetch(u+q,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
async function refresh(){
  if(!window.isSecureContext){st.textContent="Les notifications demandent une adresse en HTTPS (ex. https://edt-xxx.duckdns.org).";btn.style.display='none';return}
  if(!('serviceWorker' in navigator)||!('PushManager' in window)){
    st.textContent=ios&&!standalone?"Sur iPhone : Safari → Partager → « Sur l'écran d'accueil », puis ouvre l'appli depuis l'icône et reviens ici.":"Ce navigateur ne gère pas les notifications push.";
    btn.style.display='none';return}
  const reg=await navigator.serviceWorker.register('/sw.js');
  const sub=await reg.pushManager.getSubscription();
  btn.style.display='';
  if(sub){st.textContent='Activées sur cet appareil ✓';btn.textContent='Désactiver sur cet appareil';btn.className='btn g';btn.dataset.on=1}
  else{st.textContent=Notification.permission==='denied'?"Bloquées : autorise-les dans les réglages du téléphone.":"Désactivées sur cet appareil";
       btn.textContent='Activer les notifications';btn.className='btn';btn.dataset.on=''}
}
btn.onclick=async()=>{
  try{
    const reg=await navigator.serviceWorker.ready;
    if(btn.dataset.on){const s=await reg.pushManager.getSubscription();if(s){await post('/api/push/unsubscribe',{endpoint:s.endpoint});await s.unsubscribe()}return refresh()}
    if(await Notification.requestPermission()!=='granted')return refresh();
    const k=await (await fetch('/api/push/key'+q)).json();
    const s=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64(k.key)});
    await post('/api/push/subscribe',{sub:s.toJSON(),label:(ios?'iPhone':'Appareil')+' · '+new Date().toLocaleDateString('fr-FR')});
  }catch(err){st.textContent='Erreur : '+err.message}
  refresh();
};
refresh();
})();
</script>"""
ICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><linearGradient id="g" x1="0" y1="0" '
            'x2="1" y2="1"><stop offset="0" stop-color="#1896ff"/><stop offset="1" stop-color="#5856d6"/></linearGradient></defs>'
            '<rect width="100" height="100" rx="24" fill="url(#g)"/><path d="M30 92l10-18h4l-8 18zM70 92l-10-18h-4l8 18z" '
            'fill="#fff" fill-opacity=".6"/><rect x="25" y="16" width="50" height="60" rx="15" fill="#fff"/>'
            '<rect x="32" y="24" width="36" height="22" rx="7" fill="#1c2c5c"/><circle cx="36" cy="60.5" r="4.5" fill="#ffc42e"/>'
            '<circle cx="64" cy="60.5" r="4.5" fill="#ffc42e"/></svg>')


def make_app(state: dict, actions: dict) -> web.Application:
    def tok(request, first=True):
        t = request.query.get("token")
        return (("?" if first else "&") + f"token={e(t)}") if t else ""

    @web.middleware
    async def auth(request, handler):
        need = C.get("WEB_TOKEN")
        if not need or request.path in PUBLIC:
            return await handler(request)
        if request.query.get("token") == need:  # 1re visite avec ?token= : on le retient dans un cookie
            resp = await handler(request)
            resp.set_cookie("edt_token", need, max_age=400 * 86400, httponly=True, samesite="Lax",
                            secure=request.headers.get("X-Forwarded-Proto") == "https" or request.secure)
            return resp
        if request.cookies.get("edt_token") == need:
            return await handler(request)
        return web.Response(status=401, text="🔒 Ouvre une fois l'adresse avec ?token=TON_MOT_DE_PASSE")

    def page(body: str, request, active="/", title="EDT & Trains") -> web.Response:
        t = tok(request)
        tabs = [("/", "Accueil", "home"), ("/edt", "Cours", "cal"), ("/train", "Trajet", "train"),
                ("/services", "Services", "pulse"), ("/config", "Réglages", "gear")]
        nav = "".join(f"<a class='{'on' if p == active else ''}' href='{p}{t}'>{ICONS[i]}<span>{n}</span></a>"
                      for p, n, i in tabs)
        miss = C.missing()
        warn = ""
        if miss and active != "/config":
            warn = (f"<div class=warn>Configuration incomplète (<code>{', '.join(miss)}</code>) — "
                    f"<a href='/config{t}'><u>compléter</u></a></div>")
        return web.Response(
            text="<!doctype html><html lang=fr><head><meta charset=utf-8>"
                 "<meta name=viewport content='width=device-width,initial-scale=1,viewport-fit=cover'>"
                 "<meta name=theme-color content='#0b0c0e'><meta name=apple-mobile-web-app-capable content=yes>"
                 "<meta name=apple-mobile-web-app-status-bar-style content=black-translucent>"
                 "<link rel=manifest href='/manifest.json'><link rel=icon href='/icon.svg'>"
                 f"<link rel=apple-touch-icon href='/icon-180.png'><title>{e(title)}</title><style>{CSS}</style></head><body>"
                 f"<div class=top><h1>{e(title)}</h1>"
                 f"<a class=ibtn href='/sync{t}' title='Actualiser'>{ICONS['sync']}</a></div>"
                 f"<main>{warn}{body}</main><nav class=tabs>{nav}</nav></body></html>",
            content_type="text/html")

    def err(ex, request, active="/"):
        return page(f"<div class=warn>❌ {e(str(ex))}</div>", request, active)

    # ---------- accueil ----------
    async def index(request):
        edt = db.get("edt", {})
        now = dt.datetime.now(TZ)
        today = now.date()
        out = ["<div class=lbl style='margin-top:8px'>Prochain départ</div>",
               "<div id=hero><div class=card><div class=shimmer style='width:40%'></div>"
               "<div class=shimmer style='width:60%;height:58px;margin:16px 0'></div><div class=shimmer></div></div></div>"]
        ms = monitor.summary()
        if ms["total"]:
            t_ = tok(request)
            if ms["down"]:
                out.append(f"<a class='mon' href='/services{t_}' style='margin-top:12px;box-shadow:inset 0 0 0 2px var(--red)'>"
                           f"<div class=mt><span class='dot down'></span><b>{ms['down']} service(s) hors ligne</b>"
                           f"<span class=sub>{e(', '.join(ms['down_names'][:2]))}</span><span class=chev>›</span></div></a>")
            else:
                out.append(f"<a class='mon' href='/services{t_}' style='margin-top:12px'><div class=mt><span class='dot up'></span>"
                           f"<b>Services : tout est en ligne</b><span class=sub>{ms['up']}/{ms['total']}</span>"
                           f"<span class=chev>›</span></div></a>")
        show = None  # cours du jour (ou du prochain jour de cours)
        for i in range(8):
            d = today + dt.timedelta(days=i)
            cs = edt.get(d.isoformat(), [])
            if cs and (i > 0 or now.strftime("%H:%M") < cs[-1]["end"]):
                show = (d, cs)
                break
        if show:
            d, cs = show
            label = ("Aujourd'hui" if d == today else "Demain" if d == today + dt.timedelta(days=1)
                     else f"{JOURS[d.weekday()]} {d:%d/%m}")
            out.append(f"<div class=lbl>Cours · {label}</div>{course_rows(cs, d)}")
        rows = db.last_delays(50)
        if rows:
            n = len(rows)
            ok = sum(1 for r in rows if not r[5] and r[4] < C.get("DELAY_ALERT"))
            canc = sum(1 for r in rows if r[5])
            lates = [r[4] for r in rows if not r[5] and r[4] > 0]
            avg = round(sum(lates) / len(lates)) if lates else 0
            out.append("<div class=lbl>Ponctualité</div><div class=stats>"
                       f"<div class=stat><b style='color:var(--green)'>{round(100 * ok / n)}%</b><small>à l'heure</small></div>"
                       f"<div class=stat><b style='color:var(--orange)'>{avg} min</b><small>retard moyen</small></div>"
                       f"<div class=stat><b style='color:var(--red)'>{canc}</b><small>suppressions</small></div>"
                       f"<div class=stat><b>{n}</b><small>trains suivis</small></div></div>")
            out.append("<div class=lbl>Historique</div><div class=hist>")
            for day, origin, mission, base_dep, delay, cancelled in rows[:10]:
                cl, tx = (("c-cancel", "Supprimé") if cancelled else
                          ("c-late", f"+{delay} min") if delay > 0 else ("c-ok", "À l'heure"))
                out.append(f"<div class=hrow><span>{day[8:10]}/{day[5:7]}</span><b>{base_dep[11:16]} · {e(origin)}</b>"
                           f"<span class='chip {cl}'>{tx}</span></div>")
            out.append("</div>")
        t = tok(request)
        out.append(f"<div class=btns><a class=btn href='/train?discord=1{tok(request, False)}'>Envoyer sur Discord</a>"
                   f"<a class='btn g' href='/retour{t}'>Trains retour</a></div>")
        out.append(HOME_JS)
        return page("".join(out), request, "/", "Accueil")

    # ---------- emploi du temps ----------
    async def edt_page(request):
        edt = db.get("edt", {})
        now = dt.datetime.now(TZ)
        today = now.date()
        days = [today + dt.timedelta(days=i) for i in range(21)]
        days = [d for d in days if d.weekday() < 5 or edt.get(d.isoformat())]
        sel = next((d for d in days if edt.get(d.isoformat()) and
                    (d > today or now.strftime("%H:%M") < edt[d.isoformat()][-1]["end"])), today)
        chips, panels = [], []
        for d in days:
            cs = edt.get(d.isoformat(), [])
            k = d.isoformat()
            lab = "Auj." if d == today else JOURS[d.weekday()][:3]
            chips.append(f"<div class='day{' has' if cs else ''}{' on' if d == sel else ''}' data-d='{k}'>"
                         f"<small>{lab}</small><b>{d.day}</b><i></i></div>")
            if cs:
                ons = [c for c in cs if not c.get("virtual")]
                summ = (f"<span>{len(cs)} cours</span><span>"
                        + (f"Sur place {ons[0]['start']} → {ons[-1]['end']}" if ons else "Tout en ligne") + "</span>")
                body = f"<div class=dsum>{summ}</div>" + course_rows(cs, d)
            else:
                body = "<div class=free>Pas cours 🎉</div>"
            panels.append(f"<div class='dpanel{' on' if d == sel else ''}' id='p{k}'>"
                          f"<div class=lbl>{JOURS[d.weekday()]} {d.day:02d}/{d.month:02d}</div>{body}</div>")
        return page(f"<div class=days>{''.join(chips)}</div>{''.join(panels)}{EDT_JS}", request, "/edt",
                    "Emploi du temps")

    # ---------- cards (images) ----------
    def cards_action(name, title, active):
        async def handler(request):
            try:
                cs = await actions[name]()
                sent = ""
                if request.query.get("discord") == "1":
                    to_send = await actions[name + "_discord"]() if name + "_discord" in actions else cs
                    sent = ("<div class=ok>Envoyé sur Discord ✓</div>" if await actions["send"](to_send)
                            else "<div class=warn>Envoi Discord impossible (webhook ?)</div>")
            except Exception as ex:
                return err(ex, request, active)
            body = (sent + "".join(map(show, cs)) +
                    f"<a class=btn href='?discord=1{tok(request, False)}'>Envoyer sur Discord</a>")
            return page(body, request, active, title)
        return handler

    async def trajet_png(request):
        pngs = state.get("hero_png") or []
        i = int(request.query.get("i", "0") or 0)
        if i >= len(pngs):
            raise web.HTTPNotFound()
        return web.Response(body=pngs[i], content_type="image/png", headers={"Cache-Control": "no-store"})

    async def api_hero(_):
        try:
            h = dict(await actions["hero"]())
            h["png"] = len(state.get("hero_png") or [])
            return web.json_response(h)
        except Exception as ex:
            return web.json_response({"error": str(ex)})

    async def sync(request):
        try:
            n = await actions["sync"]()
        except Exception as ex:
            return err(ex, request)
        nb = sum(len(v) for v in db.get("edt", {}).values())
        return page(f"<div class=ok>Emploi du temps récupéré : {nb} cours sur 30 jours · {n} jour(s) modifié(s)</div>"
                    f"<a class=btn href='/edt{tok(request)}'>Voir l'emploi du temps</a>", request, "/", "Actualisé")

    # ---------- réglages ----------
    async def config_view(request):
        saved = db.get("settings", {})
        t = tok(request)
        n_dev = len(push.subs())
        out = ["<div class=ok>Réglages enregistrés et appliqués ✓</div>" if request.query.get("saved") else "",
               "<div class=lbl style='margin-top:8px'>Notifications sur ce téléphone</div><div class=card>"
               "<div id=pstat class=sub>Vérification…</div>"
               "<button id=pbtn class=btn type=button style='margin-top:12px;display:none'>Activer les notifications</button>"
               f"<div class=sub style='font-size:13px;margin-top:10px'>{n_dev} appareil(s) abonné(s)"
               + (f" · <a href='/config/test/push{t}'><u>envoyer un test</u></a>" if n_dev else "")
               + f" · <a href='/n{t}'><u>historique</u></a></div></div>",
               PUSH_JS,
               f"<form class=form method=post action='/config{t}'>"]
        open_sec = False
        for key, label, typ, default, hint in C.FIELDS:
            if key.startswith("__"):
                if open_sec:
                    out.append("</div>")
                out.append(f"<div class=lbl>{e(key[2:])}</div><div class=card>")
                open_sec = True
                continue
            cur = str(saved.get(key, ""))
            if typ == "secret":
                ph = ("•••••••• enregistré — vide = inchangé" if C.get(key)
                      else "à remplir" if key in C.REQUIRED else "optionnel")
                inp = f"<input type=password name={key} placeholder='{e(ph)}' autocomplete=off>"
            elif typ == "int":
                inp = f"<input type=number inputmode=numeric min=0 name={key} value='{e(cur or str(C.get(key)))}'>"
            elif typ.startswith("choice:"):
                val = cur or C.get(key)
                inp = f"<select name={key}>" + "".join(
                    f"<option{' selected' if o == val else ''}>{e(o)}</option>" for o in typ[7:].split("|")) + "</select>"
            elif typ == "time":
                inp = f"<input type=time name={key} value='{e(C.get(key))}'>"
            else:
                inp = f"<input type=text name={key} value='{e(cur)}' placeholder='{e(default or 'optionnel')}'>"
            out.append(f"<label>{e(label)}</label>{inp}" + (f"<small>{e(hint)}</small>" if hint else ""))
        if open_sec:
            out.append("</div>")
        out.append("<div style='margin-top:16px'><button class=btn type=submit>Enregistrer</button></div></form>")
        out.append(f"<div class=lbl>Tests</div><div class=btns><a class='btn g' href='/config/test/discord{t}'>Webhook Discord</a>"
                   f"<a class='btn g' href='/config/test/prim{t}'>API PRIM</a></div>"
                   f"<div class=btns><a class='btn g' href='/sync{t}'>Lien .ics</a>"
                   f"<a class='btn g' href='/retour{t}'>Trains retour</a></div>")
        return page("".join(out), request, "/config", "Réglages")

    async def config_post(request):
        form = await request.post()
        values = {}
        for key, _, typ, _, _ in C.FIELDS:
            if key.startswith("__") or key not in form:
                continue
            v = str(form[key]).strip()
            if typ == "secret" and not v:
                continue
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
        return page("".join(map(show, cs)) +
                    f"<a class='btn g' href='/config{tok(request)}'>Retour aux réglages</a>", request, "/config", "Test")

    # ---------- notifications (ouvertes depuis le téléphone) ----------
    async def notif_page(request):
        n = notifs.get(request.match_info["nid"])
        if not n:
            return page("<div class=warn>Notification expirée.</div>", request, "/", "Notification")
        t = tok(request)
        when = n["ts"][11:16] + " · " + n["ts"][8:10] + "/" + n["ts"][5:7]
        out = [f"<div class=sub style='margin:0 4px 14px'>{e(n['body'])}<br><small style='color:var(--dim)'>Reçue à {when}</small></div>"]
        out += [render_data(bl) for bl in n.get("blocks", [])]
        out.append(f"<div class=btns><a class=btn href='/{t}'>Accueil</a><a class='btn g' href='/n{t}'>Toutes les notifs</a></div>")
        return page("".join(out), request, "/", n["title"])

    async def notif_list(request):
        t = tok(request)
        lst = notifs.latest(30)
        if not lst:
            return page("<div class=free>Aucune notification pour l'instant</div>", request, "/", "Notifications")
        rows = "".join(f"<a class=hrow href='/n/{n['id']}{t}'><span>{n['ts'][11:16]}</span>"
                       f"<b>{e(n['title'])}<br><small class=sub style='font-weight:400'>{e(n['body'])}</small></b>"
                       f"<span class=chev>›</span></a>" for n in lst)
        return page(f"<div class=hist>{rows}</div>", request, "/", "Notifications")

    # ---------- services (surveillance) ----------
    def mstate(m):
        if m["paused"]:
            return "paused", "En pause"
        info = monitor.STATE.get(m["id"], {})
        s = info.get("status", "pending")
        if s == "pending" and info.get("fails"):
            return "pend", "Échec, nouvel essai…"
        return s, {"up": "En ligne", "down": "Hors ligne", "pending": "En attente"}[s]

    async def services(request):
        t = tok(request)
        ms = monitor.all_monitors()
        s = monitor.summary()
        if not ms:
            head = ("<div class='card acc' style='--a:var(--blue)'><div class=k>Surveillance</div>"
                    "<div class=h2>Aucun service</div><div class=sub>Ajoute tes sites, ton Home Assistant, ton Proxmox… "
                    "pour être prévenu dès qu'ils ne répondent plus.</div></div>")
        elif s["down"]:
            head = (f"<div class='card acc' style='--a:var(--red)'><div class=k>Surveillance</div>"
                    f"<div class=h2>{s['down']} service{'s' if s['down'] > 1 else ''} hors ligne</div>"
                    f"<div class=sub>{e(', '.join(s['down_names']))}</div></div>")
        else:
            head = (f"<div class='card acc' style='--a:var(--green)'><div class=k>Surveillance</div>"
                    f"<div class=h2>Tout est en ligne</div><div class=sub>{s['up']}/{s['total']} services"
                    + (f" · {s['pending']} en attente" if s["pending"] else "") + "</div></div>")
        rows = []
        for m in ms:
            st, label = mstate(m)
            info = monitor.STATE.get(m["id"], {})
            up = monitor.uptime(m["id"], 24)
            host = urlparse_host(m["target"])
            right = (f"<b>{info['ms']} ms</b>" if info.get("ok") else f"<b style='color:var(--red)'>{label}</b>"
                     if st == "down" else f"<b>{label}</b>") + (f"{up:g} %" if up is not None else "")
            rows.append(f"<a class=mon href='/services/{m['id']}{t}'><div class=mt><span class='dot {st}'></span>"
                        f"<div style='flex:1;min-width:0'><b style='display:block'>{e(m['name'])}</b>"
                        f"<small>{e(monitor.TYPES[m['type']])} · {e(host)}</small></div><div class=mr>{right}</div></div>"
                        f"{beats_html(monitor.recent(m['id'], 40))}</a>")
        body = head + (f"<div class=lbl>Services</div>{''.join(rows)}" if rows else "")
        inc = [i for i in monitor.incidents(None, 8)]
        if inc:
            body += "<div class=lbl>Derniers incidents</div><div class=hist>" + "".join(
                f"<div class=inc><span class='dot {'down' if not i['end'] else ''}'></span><b>{e(i['name'] or '?')}"
                f"<small>{e(i['reason'] or '')}</small></b><span class=sub style='font-size:13px;text-align:right'>"
                f"{dt.datetime.fromtimestamp(i['start'], TZ).strftime('%d/%m %H:%M')}<br>"
                f"{'en cours' if not i['end'] else monitor.fmt_duration(i['end'] - i['start'])}</span></div>" for i in inc) + "</div>"
        body += (f"<div class=lbl>Ajout rapide</div><form class=form method=post action='/services/bulk{t}'><div class=card>"
                 "<textarea name=urls placeholder='Une adresse par ligne\nhttps://gravicore.ibenji.fr\n192.168.1.20:8006'></textarea>"
                 "<small>Les adresses avec « :port » sans http sont ajoutées en port TCP, les autres en HTTP(S).</small>"
                 "<div style='margin-top:12px'><button class='btn g'>Ajouter la liste</button></div></div></form>")
        body += f"<a class=fab href='/services/new{t}' aria-label='Ajouter'>+</a>"
        return page(body, request, "/services", "Services")

    async def service_new(request):
        if request.method == "POST":
            mid = monitor.add(dict(await request.post()))
            m = monitor.get(mid)
            if "monitor_check" in actions:
                await actions["monitor_check"](m)
            raise web.HTTPFound(f"/services/{mid}{tok(request)}")
        return page(monitor_form(None, f"/services/new{tok(request)}"), request, "/services", "Nouveau service")

    async def service_bulk(request):
        form = await request.post()
        n = 0
        for line in str(form.get("urls", "")).splitlines():
            line = line.strip()
            if not line:
                continue
            is_tcp = not line.startswith("http") and re.search(r":\d+$", line)
            monitor.add({"target": line, "type": "tcp" if is_tcp else "http"})
            n += 1
        raise web.HTTPFound(f"/services{tok(request)}")

    async def service_view(request):
        mid = int(request.match_info["mid"])
        m = monitor.get(mid)
        if not m:
            raise web.HTTPFound(f"/services{tok(request)}")
        t = tok(request)
        st, label = mstate(m)
        info = monitor.STATE.get(mid, {})
        acc = {"up": "var(--green)", "down": "var(--red)", "paused": "var(--dim)"}.get(st, "var(--blue)")
        chip = {"up": "c-ok", "down": "c-cancel"}.get(st, "")
        link = (f"<a href='{e(m['target'])}' target=_blank style='word-break:break-all'><u>{e(m['target'])}</u></a>"
                if m["type"] in ("http", "keyword") else e(m["target"]))
        cert = info.get("cert_days")
        head = (f"<div class='card acc' style='--a:{acc}'><div class='row sp'><div class=k>{e(monitor.TYPES[m['type']])}</div>"
                f"<span class='chip {chip}'>{label}</span></div><div class=h2>{e(m['name'])}</div>"
                f"<div class=sub>{link}</div>"
                f"<div class=bk style='margin-top:12px'><span class='dot {st}'></span><b>{e(info.get('msg') or 'Pas encore vérifié')}</b>"
                f"<span class=sub style='margin-left:auto;font-size:13px'>{_ago(info.get('last'))}</span></div>"
                + (f"<div class=row style='margin-top:10px'><span class='chip {'c-late' if cert <= m['ssl_days'] else ''}'>"
                   f"Certificat : {cert} j</span></div>" if cert is not None else "") + "</div>")
        stats = "".join(f"<div class=stat><b>{'—' if v is None else f'{v:g} %'}</b><small>dispo {lab}</small></div>"
                        for lab, v in (("24 h", monitor.uptime(mid, 24)), ("7 j", monitor.uptime(mid, 168)),
                                       ("30 j", monitor.uptime(mid, 720))))
        avg = monitor.avg_ms(mid)
        stats += f"<div class=stat><b>{'—' if avg is None else f'{avg} ms'}</b><small>réponse moy. 24 h</small></div>"
        rows24 = [r for r in monitor.recent(mid, 2000) if r[0] >= dt.datetime.now().timestamp() - 86400]
        body = (head + f"<div class=lbl>Disponibilité</div><div class=grid4>{stats}</div>"
                f"<div class=lbl>Temps de réponse · 24 h</div><div class=card>{chart_svg(rows24[-300:])}"
                f"{beats_html(monitor.recent(mid, 50), 50)}</div>")
        inc = monitor.incidents(mid, 10)
        if inc:
            body += "<div class=lbl>Incidents</div><div class=hist>" + "".join(
                f"<div class=inc><span class='dot {'down' if not i['end'] else ''}'></span><b>{e(i['reason'] or '')}"
                f"<small>{dt.datetime.fromtimestamp(i['start'], TZ).strftime('%d/%m à %H:%M')}</small></b>"
                f"<span class=chip>{'en cours' if not i['end'] else monitor.fmt_duration(i['end'] - i['start'])}</span></div>"
                for i in inc) + "</div>"
        body += (f"<div class=btns><form method=post action='/services/{mid}/check{t}'><button class=btn>Vérifier</button></form>"
                 f"<form method=post action='/services/{mid}/pause{t}'><button class='btn g'>"
                 f"{'Reprendre' if m['paused'] else 'Mettre en pause'}</button></form></div>"
                 f"<details class=alt style='margin-top:12px'><summary><b>Modifier</b><span class=chev>›</span></summary>"
                 f"<div class=in>{monitor_form(m, f'/services/{mid}/edit{t}')}</div></details>"
                 f"<form method=post action='/services/{mid}/delete{t}' onsubmit=\"return confirm('Supprimer ce service et son historique ?')\">"
                 f"<button class='btn red' style='margin-top:12px'>Supprimer</button></form>")
        return page(body, request, "/services", m["name"])

    async def service_action(request):
        mid = int(request.match_info["mid"])
        act = request.match_info["act"]
        m = monitor.get(mid)
        if not m:
            raise web.HTTPFound(f"/services{tok(request)}")
        if act == "delete":
            monitor.delete(mid)
            raise web.HTTPFound(f"/services{tok(request)}")
        if act == "pause":
            monitor.set_paused(mid, not m["paused"])
        elif act == "edit":
            monitor.update(mid, dict(await request.post()))
            m = monitor.get(mid)
            if not m["paused"] and "monitor_check" in actions:
                await actions["monitor_check"](m)
        elif act == "check" and "monitor_check" in actions:
            await actions["monitor_check"](m)
        raise web.HTTPFound(f"/services/{mid}{tok(request)}")

    async def manifest(_):
        return web.json_response(MANIFEST, content_type="application/manifest+json")

    async def sw(_):
        return web.Response(text=push.SW_JS, content_type="application/javascript",
                            headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})

    def png_icon(size):
        async def h(_):
            return web.Response(body=push.icon_png(size), content_type="image/png",
                                headers={"Cache-Control": "public, max-age=86400"})
        return h

    async def push_key(_):
        return web.json_response({"key": push.keys()["public"]})

    async def push_sub(request):
        d = await request.json()
        sub = d.get("sub") or {}
        if not sub.get("endpoint"):
            raise web.HTTPBadRequest()
        push.add_sub(sub, d.get("label", ""))
        return web.json_response({"ok": True, "count": len(push.subs())})

    async def push_unsub(request):
        d = await request.json()
        push.remove_sub(d.get("endpoint", ""))
        return web.json_response({"ok": True})

    async def icon(_):
        return web.Response(text=ICON_SVG, content_type="image/svg+xml")

    async def api(_):
        return web.json_response({"edt": db.get("edt", {})})

    app = web.Application(middlewares=[auth])
    app.router.add_get("/", index)
    app.router.add_get("/edt", edt_page)
    app.router.add_get("/api/hero", api_hero)
    app.router.add_get("/trajet.png", trajet_png)
    app.router.add_get("/train", cards_action("train", "Trajet", "/train"))
    app.router.add_get("/retour", cards_action("retour", "Trains retour", "/train"))
    app.router.add_get("/sync", sync)
    app.router.add_get("/config", config_view)
    app.router.add_post("/config", config_post)
    app.router.add_get("/config/test/{what}", test)
    app.router.add_get("/n", notif_list)
    app.router.add_get("/n/{nid}", notif_page)
    app.router.add_get("/services", services)
    app.router.add_route("*", "/services/new", service_new)
    app.router.add_post("/services/bulk", service_bulk)
    app.router.add_get("/services/{mid:\\d+}", service_view)
    app.router.add_post("/services/{mid:\\d+}/{act}", service_action)
    app.router.add_get("/manifest.json", manifest)
    app.router.add_get("/sw.js", sw)
    app.router.add_get("/icon-180.png", png_icon(180))
    app.router.add_get("/icon-512.png", png_icon(512))
    app.router.add_get("/api/push/key", push_key)
    app.router.add_post("/api/push/subscribe", push_sub)
    app.router.add_post("/api/push/unsubscribe", push_unsub)
    app.router.add_get("/icon.svg", icon)
    app.router.add_get("/api", api)
    return app
