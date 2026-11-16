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


# ---------- cards ----------
def edt_card(day, courses, title_prefix=""):
    if not courses:
        return card(f"{title_prefix}📅 {jour(day)}", "grey", "Pas cours 🎉")
    return card(f"{title_prefix}📅 {jour(day)}", "blue", "\n".join(map(course_line, courses)),
                footer=f"{len(courses)} cours · début {courses[0]['start']} · fin {courses[-1]['end']}")


def aller_card(aller, first_start):
    if not aller:
        return card("🚆 Aller", "red", "Aucun train direct trouvé 🤔")
    fields = []
    for i, r in enumerate(aller):
        o, t = r["origin"], r["trip"]
        star = " ⭐" if i == 0 else ""
        fields.append((f"{o['emoji']} {o['name']}{star}",
                       f"Pars à **{hm(r['leave'])}**\nTrain {trip_str(t)}\n`{t.mission}`", True))
    return card(f"🚆 Aller · cours à {first_start}", "purple", fields=fields,
                footer=f"Arrivée Montparnasse avant {hm(aller[0]['target'])} · ⭐ = te laisse dormir le plus")


def retour_card(retour, subtitle=""):
    fields = [(f"{r['origin']['emoji']} → {r['origin']['name']}",
               "\n".join(trip_str(t) for t in r["trips"]) or "—", True) for r in retour]
    return card(f"🏠 Retour{subtitle}", "teal", fields=fields)


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


def status_card(kind, origin, planned, rt, leave, target, alts, back=False):
    head = f"{origin['emoji']} **{origin['name']}** · train `{planned.mission}`"
    alt_txt = "\n".join(trip_str(a) for a in alts) if alts else None
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
            f.append(("Autres trains", alt_txt, False))
        return card(f"⏱️ Retard +{rt.delay} min", "orange", head, f)
    f = [("Train prévu", f"~~{hm(planned.base_dep)}~~", True)]
    if alt_txt:
        f.append(("Autres trains", alt_txt, False))
    return card("🚫 Train supprimé", "red", head, f)
