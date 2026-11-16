"""Construction des cards (embeds Discord). Le site web réutilise les mêmes cards."""
import datetime as dt

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
COL = {"blue": 0x0A84FF, "green": 0x30D158, "orange": 0xFF9F0A, "red": 0xFF453A,
       "purple": 0xBF5AF2, "grey": 0x636366, "teal": 0x40C8E0}


def hm(d):
    return d.strftime("%H:%M")


def jour(d):
    return f"{JOURS[d.weekday()]} {d:%d/%m}"


def ts(d, f="t"):
    """Horodatage Discord (affiché dans le fuseau de chacun). f=t heure, R relatif."""
    return f"<t:{int(d.timestamp())}:{f}>"


def card(title, color, desc=None, fields=None, footer=None):
    e = {"title": title[:256], "color": COL.get(color, color)}
    if desc:
        e["description"] = desc[:4000]
    if fields:
        e["fields"] = [{"name": n[:256], "value": (v or "—")[:1024], "inline": i} for n, v, i in fields][:25]
    if footer:
        e["footer"] = {"text": footer[:2048]}
    e["timestamp"] = dt.datetime.now(dt.timezone.utc).isoformat()
    return e


def course_line(c):
    return f"`{c['start']} – {c['end']}` **{c['summary']}**" + (f" · {c['location']}" if c["location"] else "")


def trip_str(t):
    if t.delay > 0:
        return f"~~{hm(t.base_dep)}~~ **{hm(t.dep)}** (+{t.delay}) → {hm(t.arr)}"
    return f"**{hm(t.dep)}** → {hm(t.arr)}"


def route_str(r):
    return f"**{hm(r['dep'])}** → {hm(r['arr'])} · " + " ➜ ".join(r["legs"])


# ---------- cards ----------
def edt_card(day, courses, title_prefix=""):
    if not courses:
        return card(f"{title_prefix}📅 {jour(day)}", "grey", "Pas cours 🎉")
    fields = [(f"🕗 {c['start']} → {c['end']}", f"**{c['summary']}**" + (f"\n📍 {c['location']}" if c["location"] else ""), True)
              for c in courses]
    return card(f"{title_prefix}📅 {jour(day)}", "blue", fields=fields,
                footer=f"{len(courses)} cours · de {courses[0]['start']} à {courses[-1]['end']}")


def trains_list(r):
    """3 trains max : avant / conseillé / après."""
    lines = []
    for t in r["list"]:
        main = t.key == r["trip"].key
        late = t.arr > r.get("latest_ok", r["target"])
        delay = f" (+{t.delay})" if t.delay > 0 else ""
        txt = f"{hm(t.dep)}{delay} → {hm(t.arr)}"
        if main:
            lines.append(f"▶️ **{txt}** `{t.mission}`")
        else:
            lines.append(f"▫️ {txt}" + (" ⚠️ trop tard" if late else ""))
    return "\n".join(lines)


def aller_card(aller, first_start, backups=None):
    fields = []
    for i, r in enumerate(aller):
        o = r["origin"]
        name = f"{o['emoji']} {o['name']}" + (" ⭐" if i == 0 else "")
        if not r["trip"]:
            fields.append((name, "❌ Aucun train N trouvé", True))
            continue
        fields.append((name, f"🏠 Pars à **{hm(r['leave'])}**\n" + trains_list(r), True))
    if backups:
        fields.append(("🔀 Itinéraires sans le N", "\n".join(route_str(b) for b in backups), False))
    color = "purple" if all(r["trip"] for r in aller) and aller else "orange"
    tgt = aller[0]["target"] if aller else None
    return card(f"🚆 Aller · 1er cours à {first_start}", color, fields=fields or [("—", "Aucun train trouvé 🤔", False)],
                footer=(f"▶️ train conseillé · ▫️ avant / après · arrivée idéale avant {hm(tgt)}" if tgt else None))


def retour_card(retour, subtitle=""):
    fields = [(f"{r['origin']['emoji']} → {r['origin']['name']}",
               "\n".join(trip_str(t) for t in r["trips"]) or "—", True) for r in retour]
    return card(f"🏠 Retour{subtitle}", "teal", fields=fields)


def backups_card(backups, title="🔀 Autres itinéraires (sans le N)"):
    if not backups:
        return card(title, "grey", "Aucun itinéraire alternatif trouvé")
    by = {}
    for b in backups:
        by.setdefault(b["origin"], []).append(route_str(b))
    return card(title, "grey", fields=[(f"Depuis {o}", "\n".join(v), False) for o, v in by.items()])


def changes_card(changes):
    fields = []
    for d, chs in changes.items():
        lines = []
        for kind, a, b in chs:
            if kind == "add":
                lines.append(f"🆕 {course_line(b)}")
            elif kind == "del":
                lines.append(f"❌ ~~{a['start']} – {a['end']} {a['summary']}~~ annulé")
            else:
                lines.append(f"🔄 **{a['summary']}** {a['start']}–{a['end']} {a['location']} → "
                             f"**{b['start']}–{b['end']} {b['location']}**")
        fields.append((jour(dt.date.fromisoformat(d)), "\n".join(lines), False))
    return card("⚠️ Emploi du temps modifié", "orange", fields=fields)


def status_card(kind, origin, planned, rt, leave, target, alts, back=False, backups=None):
    head = f"{origin['emoji']} **{origin['name']}** · train `{planned.mission}`"
    alt_txt = "\n".join(trip_str(a) for a in alts) if alts else None
    bk = ("🔀 Sans le N", "\n".join(route_str(b) for b in backups), False) if backups else None
    if kind == "ok":
        title = "✅ Revenu à l'heure" if back else "✅ Train à l'heure"
        t = rt or planned
        return card(title, "green", head, [("Départ", f"**{hm(t.dep)}**", True),
                                           ("Arrivée", hm(t.arr), True),
                                           ("Pars de chez toi", f"**{hm(leave)}** ({ts(leave, 'R')})", True)])
    if kind == "late":
        ok = rt.arr <= target
        f = [("Départ", f"~~{hm(rt.base_dep)}~~ **{hm(rt.dep)}**", True), ("Arrivée", hm(rt.arr), True),
             ("En cours à l'heure ?", "✅ Ça passe" if ok else "⚠️ Risque de retard", True)]
        if alt_txt:
            f.append(("Autres trains N", alt_txt, False))
        if bk:
            f.append(bk)
        return card(f"⏱️ Retard +{rt.delay} min", "orange", head, f)
    f = [("Train prévu", f"~~{hm(planned.base_dep)}~~", True)]
    if alt_txt:
        f.append(("Autres trains N", alt_txt, False))
    if bk:
        f.append(bk)
    return card("🚫 Train supprimé", "red", head, f)
