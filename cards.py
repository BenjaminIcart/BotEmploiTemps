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


def with_image(c, make, summary=None):
    """Ajoute l'image (PNG) à la card ; si elle est générée, le texte détaillé est retiré."""
    try:
        png = make()
    except Exception as e:  # Pillow absent ou erreur : on garde la version texte
        import logging
        logging.getLogger("cards").warning("Image : %s", e)
        png = None
    if png:
        c["_png"] = png
        c.pop("fields", None)
        c.pop("footer", None)
        if summary is not None:
            c["description"] = summary
        else:
            c.pop("description", None)
    return c


def _render():
    import render
    return render


# ---------- cards ----------
def course_row(c):
    meta = " · ".join(x for x in (c.get("type"), "*en ligne*" if c.get("virtual") else c.get("location")) if x)
    return f"`{c['start']}–{c['end']}`  **{c['summary']}**" + (f"  ·  {meta}" if meta else "")


def edt_card(day, courses, title_prefix=""):
    if not courses:
        return with_image(card(f"{title_prefix}{jour(day)}", "grey", "Pas cours"),
                          lambda: _render().edt_png(f"{title_prefix}{jour(day)}", "", []))
    onsite = [c for c in courses if not c.get("virtual")]
    online = len(courses) - len(onsite)
    foot = []
    if onsite:
        foot.append(f"Sur place {onsite[0]['start']} → {onsite[-1]['end']}")
    if online:
        foot.append(f"{online} en ligne")
    c = card(f"{title_prefix}{jour(day)}", "blue", "\n".join(map(course_row, courses)), footer=" · ".join(foot))
    c["_notif_edt"] = f"📅 {jour(day)} : {len(courses)} cours, 1er à {courses[0]['start']}"
    return with_image(c, lambda: _render().edt_png(f"{title_prefix}{jour(day)}", " · ".join(foot), courses))


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


def aller_card(aller, first_start, backups=None, school_name="École", stop_name="Bir-Hakeim"):
    if not aller or not aller[0]["trip"]:
        f = [("Sans le N", "\n".join(route_str(b) for b in backups), False)] if backups else None
        c = card("Aller · aucun train N trouvé", "orange", f"1er cours sur place à {first_start}", f)
        c["_notif"] = f"⚠️ Aucun train N trouvé pour ton cours de {first_start}"
        return c
    r, t = aller[0], aller[0]["trip"]
    o, ch = r["origin"], r.get("chain")
    dep = f"**{hm(t.dep)}**" + (f" (+{t.delay})" if t.delay > 0 else "")
    lines = [f"{dep} {o['name']} → Montparnasse {hm(t.arr)}"]
    late = False
    if ch:
        if ch["metro"]:
            lines.append(f"**{hm(ch['metro']['dep'])}** Métro {ch['metro']['line']} → {stop_name} {hm(ch['metro']['arr'])}")
        late = ch["school_arr"] > r["course"]
        lines.append(f"**{hm(ch['school_arr'])}** {school_name} · cours à {hm(r['course'])}")
    if late:
        lines.append("⚠️ Arrivée après le début du cours")
    others = [x for x in r["list"] if x.key != t.key]
    limit = r.get("latest_ok", r["target"])
    fields = []
    if others:
        fields.append(("Autres trains", " · ".join(
            hm(x.dep) + (" (trop tard)" if x.arr > limit else "") for x in others), True))
    if backups:
        fields.append(("Sans le N", "\n".join(route_str(b) for b in backups), False))
    c = card(f"Départ {hm(r['leave'])} · {o['name']}", "orange" if late or backups else "purple",
             "\n".join(lines), fields)
    pills = [(hm(x.dep) + (f" +{x.delay}" if x.delay > 0 else "") + (" · trop tard" if x.arr > limit else ""),
              x.arr > limit) for x in others]
    c["_notif"] = (f"🚆 Pars à {hm(r['leave'])} · train {hm(t.dep)} {o['name']}"
                   + (f" (+{t.delay})" if t.delay > 0 else "")
                   + (f" · {school_name} {hm(ch['school_arr'])}" if ch else "")
                   + (" ⚠️ en retard" if late else ""))
    return with_image(c, lambda: _render().aller_png(r, school_name, stop_name, pills, backups=backups or ()),
                      lines[0] + ("\n⚠️ Arrivée après le début du cours" if late else ""))


def alt_card(r, school_name="École", stop_name="Bir-Hakeim"):
    """Autre gare (Coignières si Trappes conseillé, et inversement), avec sa propre frise."""
    t = r.get("trip")
    if not t:
        return card(f"Autre option · {r['origin']['name']}", "grey", "Aucun train N trouvé")
    ch = r.get("chain")
    desc = f"Pars à **{hm(r['leave'])}** · train **{hm(t.dep)}**" + (f" (+{t.delay})" if t.delay > 0 else "")
    if ch:
        desc += f" · {school_name} à {hm(ch['school_arr'])}" + (" ⚠️" if ch["school_arr"] > r["course"] else "")
    c = card(f"Autre option · {r['origin']['name']}", "grey", desc)
    return with_image(c, lambda: _render().aller_png(r, school_name, stop_name, alt=True), desc)


def retour_card(retour, subtitle="", end=None):
    fields = [(r["origin"]["name"], "\n".join(trip_str(t) for t in r["trips"]) or "—", True) for r in retour]
    c = card(f"Retour{subtitle}", "teal", "Trains N à Montparnasse que tu peux attraper (métro depuis l'école compris)", fields)
    cols = [(r["origin"]["name"], [(hm(t.dep), hm(t.arr), t.delay) for t in r["trips"]]) for r in retour]
    first = next((t for r in retour[:1] for t in r["trips"][:1]), None)
    summary = f"Prochain train : **{hm(first.dep)}** vers {retour[0]['origin']['name']}" if first else None
    if first:
        c["_notif"] = f"🏠 Prochain train {hm(first.dep)} → {retour[0]['origin']['name']} (arrivée {hm(first.arr)})"
    return with_image(c, lambda: _render().retour_png(f"Fin des cours à {end}" if end else "Trains retour",
                                                     "Depuis Montparnasse · métro depuis l'école compris", cols),
                      summary)


def virtual_card(c):
    e = card(f"Cours en ligne à {c['start']}", "teal",
             f"**{c['summary']}**" + (f" · {c['type']}" if c.get("type") else "") +
             f"\n{c['start']} – {c['end']}\n\nPense à ouvrir l'app pour te mettre présent.")
    e["_notif"] = f"💻 Cours en ligne à {c['start']} : {c['summary']} — mets-toi présent"
    return with_image(e, lambda: _render().virtual_png(c), f"**{c['summary']}** · pense à te mettre présent")


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
    c = card("⚠️ Emploi du temps modifié", "orange", fields=fields)
    groups = []
    for d, chs in changes.items():
        items = []
        for kind, a, b in chs:
            if kind == "add":
                items.append(("add", b["summary"], f"{b['start']}–{b['end']} · {b.get('location', '')}".strip(" ·")))
            elif kind == "del":
                items.append(("del", a["summary"], f"{a['start']}–{a['end']}"))
            else:
                det = f"{a['start']}–{a['end']} → {b['start']}–{b['end']}"
                if a.get("location") != b.get("location"):
                    det += f" · {b.get('location', '')}"
                items.append(("mod", a["summary"], det))
        groups.append((jour(dt.date.fromisoformat(d)), items))
    n = sum(len(g) for _, g in groups)
    word = {"add": "ajouté", "del": "annulé", "mod": "déplacé"}
    first = next(((d, it) for d, its in groups for it in its), None)
    if first:
        d, (kd, name, _) = first
        c["_notif"] = f"⚠️ EDT modifié : {name} {word[kd]} ({d})" + (f" +{n - 1} autre(s)" if n > 1 else "")
    return with_image(c, lambda: _render().changes_png(groups), f"{n} changement(s) dans ton emploi du temps")


def status_card(kind, origin, planned, rt, leave, target, alts, back=False, backups=None, school_eta=None,
                route_r=None, school_name="École", stop_name="Bir-Hakeim"):
    c = _status_text(kind, origin, planned, rt, leave, target, alts, back, backups, school_eta)
    t = rt or planned
    if kind == "ok":
        title = ("Revenu à l'heure · " if back else "") + f"{hm(t.dep)} {origin['name']}"
        sub = f"Pars de chez toi à {hm(leave)}"
    elif kind == "late":
        title = f"+{rt.delay} min · {hm(rt.dep)} {origin['name']}"
        sub = f"Prévu à {hm(rt.base_dep)} · " + ("ça passe pour le cours" if rt.arr <= target else "risque de retard en cours")
    else:
        title = f"{hm(planned.base_dep)} {origin['name']}"
        sub = "Prends un autre train ou un itinéraire sans le N"
    pills = [(hm(a.dep) + (f" +{a.delay}" if a.delay > 0 else ""), False) for a in alts]
    if kind == "ok":
        notif = f"✅ {hm(t.dep)} {origin['name']} à l'heure · pars à {hm(leave)}"
    elif kind == "late":
        notif = (f"⏱️ +{rt.delay} min : {hm(rt.dep)} au lieu de {hm(rt.base_dep)} · "
                 + ("ça passe" if rt.arr <= target else "risque de retard"))
    else:
        notif = f"🚫 {hm(planned.base_dep)} {origin['name']} supprimé" + (f" · prochain N {hm(alts[0].dep)}" if alts else "")

    def make():
        R = _render()
        route = R.route_data(route_r, school_name, stop_name) if (route_r and kind != "cancel") else None
        return R.status_png(kind, title, sub, route, pills, backups or ())

    c["_notif"] = notif
    return with_image(c, make, c.get("description"))


def _status_text(kind, origin, planned, rt, leave, target, alts, back=False, backups=None, school_eta=None):
    head = f"{origin['emoji']} **{origin['name']}** · train `{planned.mission}`"
    alt_txt = "\n".join(trip_str(a) for a in alts) if alts else None
    bk = ("🔀 Sans le N", "\n".join(route_str(b) for b in backups), False) if backups else None
    if kind == "ok":
        title = "✅ Revenu à l'heure" if back else "✅ Train à l'heure"
        t = rt or planned
        f = [("Départ", f"**{hm(t.dep)}**", True), ("Montparnasse", hm(t.arr), True),
             ("Pars de chez toi", f"**{hm(leave)}** ({ts(leave, 'R')})", True)]
        if school_eta:
            f.append(("🏫 Arrivée école", school_eta, True))
        return card(title, "green", head, f)
    if kind == "late":
        ok = rt.arr <= target
        f = [("Départ", f"~~{hm(rt.base_dep)}~~ **{hm(rt.dep)}**", True), ("Montparnasse", hm(rt.arr), True),
             ("En cours à l'heure ?", "✅ Ça passe" if ok else "⚠️ Risque de retard", True)]
        if school_eta:
            f.append(("🏫 Arrivée école", school_eta, True))
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


def test_card():
    c = card("👋 Test réussi", "green", "Le webhook fonctionne, les notifications arriveront ici.")
    return with_image(c, lambda: _render().simple_png("Connexion", "Webhook connecté",
                                                     "Les notifications arriveront dans ce salon"), "Webhook connecté")
