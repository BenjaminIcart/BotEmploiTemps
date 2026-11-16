"""Frise graphique du trajet (PNG) : Maison → Gare → Montparnasse → Station → École."""
import io
import os

from PIL import Image, ImageDraw, ImageFont

BG, CARD, TXT, MUTE = (30, 31, 34), (43, 45, 49), (242, 243, 245), (148, 155, 164)
ORANGE, RED, GREEN = (255, 159, 10), (255, 69, 58), (48, 209, 88)
LINE_COLORS = {"N": (0, 168, 143), "6": (110, 202, 151), "walk": (120, 124, 132), "car": (120, 124, 132)}

_FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF"]


def _font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in _FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _hex(c):
    if isinstance(c, tuple):
        return c
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def render(data: dict) -> bytes:
    """data = {title, subtitle, late, stops:[{name,time,delay,warn}], legs:[{label,detail,kind}]}"""
    S = 2  # rendu x2 pour la netteté
    W, H = 1000, 300
    img = Image.new("RGB", (W * S, H * S), BG)
    d = ImageDraw.Draw(img)
    f_title, f_sub = _font(30 * S, True), _font(19 * S)
    f_time, f_name = _font(27 * S, True), _font(17 * S)
    f_leg, f_legd = _font(16 * S, True), _font(14 * S)

    d.rounded_rectangle([8 * S, 8 * S, (W - 8) * S, (H - 8) * S], 18 * S, fill=CARD)
    d.text((34 * S, 26 * S), data["title"], font=f_title, fill=TXT)
    d.text((34 * S, 68 * S), data["subtitle"], font=f_sub, fill=ORANGE if data.get("late") else MUTE)

    stops, legs = data["stops"], data["legs"]
    n = len(stops)
    x0, x1, y = 80, W - 80, 170
    xs = [x0 + i * (x1 - x0) / (n - 1) for i in range(n)]

    for i, leg in enumerate(legs):  # segments
        a, b = xs[i] + 14, xs[i + 1] - 14
        col = _hex(LINE_COLORS.get(leg["kind"], leg.get("color", (120, 124, 132))))
        if leg["kind"] in ("walk", "car"):
            step = 14
            x = a
            while x < b:
                d.line([(x * S, y * S), (min(x + 7, b) * S, y * S)], fill=col, width=5 * S)
                x += step
        else:
            d.rounded_rectangle([a * S, (y - 5) * S, b * S, (y + 5) * S], 5 * S, fill=col)
        mid = (a + b) / 2
        # pastille de ligne
        lw = d.textlength(leg["label"], font=f_leg) / S + 22
        d.rounded_rectangle([(mid - lw / 2) * S, (y - 48) * S, (mid + lw / 2) * S, (y - 20) * S], 14 * S,
                            fill=col if leg["kind"] not in ("walk", "car") else (64, 66, 72))
        d.text((mid * S, (y - 34) * S), leg["label"], font=f_leg, anchor="mm",
               fill=(20, 20, 20) if leg["kind"] not in ("walk", "car") else TXT)
        if leg.get("detail"):
            d.text((mid * S, (y + 22) * S), leg["detail"], font=f_legd, anchor="mm", fill=MUTE)

    for i, st in enumerate(stops):  # arrêts
        x = xs[i]
        ring = RED if st.get("warn") else (ORANGE if st.get("delay") else TXT)
        d.ellipse([(x - 13) * S, (y - 13) * S, (x + 13) * S, (y + 13) * S], fill=CARD, outline=ring, width=5 * S)
        if i in (0, n - 1):
            d.ellipse([(x - 6) * S, (y - 6) * S, (x + 6) * S, (y + 6) * S], fill=ring)
        col = RED if st.get("warn") else (ORANGE if st.get("delay") else TXT)
        t = st["time"] + (f" +{st['delay']}" if st.get("delay") else "")
        d.text((x * S, (y + 62) * S), t, font=f_time, anchor="mm", fill=col)
        d.text((x * S, (y + 94) * S), st["name"], font=f_name, anchor="mm", fill=MUTE)

    img = img.resize((W, H), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def from_plan(r: dict, school_name: str, stop_name: str) -> dict | None:
    """Construit les données de la frise à partir d'un résultat de trains.plan_aller (gare principale)."""
    t = r.get("trip")
    if not t:
        return None
    hm = lambda x: x.strftime("%H:%M")
    o, ch = r["origin"], r.get("chain") or {}
    car = o["name"] == "Trappes"
    stops = [{"name": "Maison", "time": hm(r["leave"])},
             {"name": o["name"], "time": hm(t.dep), "delay": t.delay if t.delay > 0 else 0},
             {"name": "Montparnasse", "time": hm(t.arr)}]
    legs = [{"label": "Voiture" if car else "À pied", "detail": f"{o['access']} min", "kind": "car" if car else "walk"},
            {"label": "Ligne N", "detail": f"{int((t.arr - t.dep).total_seconds() // 60)} min", "kind": "N"}]
    m = ch.get("metro")
    if m:
        stops.append({"name": stop_name, "time": hm(m["arr"])})
        legs.append({"label": f"Métro {m['line']}", "detail": f"départ {hm(m['dep'])}", "kind": "6"})
    else:
        stops.append({"name": stop_name, "time": "~"})
        legs.append({"label": "Métro 6", "detail": "estimé", "kind": "6"})
    late = bool(ch) and ch["school_arr"] > r["course"]
    stops.append({"name": school_name, "time": hm(ch["school_arr"]) if ch else "?", "warn": late})
    walk = int((ch["school_arr"] - m["arr"]).total_seconds() // 60) if (ch and m) else None
    legs.append({"label": "À pied", "detail": f"{walk} min" if walk is not None else "", "kind": "walk"})
    return {"title": f"Départ {hm(r['leave'])} · {o['name']}",
            "subtitle": (f"Arrivée {school_name} {hm(ch['school_arr'])} · cours à {hm(r['course'])}" if ch else "")
                        + (" — en retard !" if late else ""),
            "late": late, "stops": stops, "legs": legs}
