"""Images des notifications (PNG) : un seul style moderne pour tout.

Chaque fonction publique renvoie des octets PNG. Rendu x2 puis réduit pour un texte net.
"""
import colorsys
import hashlib
import io
import os

from PIL import Image, ImageDraw, ImageFont

S = 2            # suréchantillonnage
W = 1000         # largeur finale
PAD = 40         # marge intérieure

BG = (17, 18, 20)
CARD = (32, 34, 38)
ROW = (42, 44, 50)
LINE = (58, 61, 68)
TXT = (243, 244, 246)
MUTE = (150, 156, 166)
DIM = (100, 105, 115)

ACCENT = {"blue": (10, 132, 255), "green": (48, 209, 88), "orange": (255, 159, 10), "red": (255, 69, 58),
          "purple": (191, 90, 242), "teal": (64, 200, 224), "grey": (120, 124, 132)}
LINE_COL = {"N": (0, 168, 143), "6": (110, 202, 151), "walk": (120, 124, 132), "car": (120, 124, 132)}

_FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF"]
_cache = {}


def font(size, bold=False):
    key = (size, bold)
    if key in _cache:
        return _cache[key]
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    f = None
    for d in _FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            f = ImageFont.truetype(p, size * S)
            break
    if f is None:
        try:
            f = ImageFont.load_default(size=size * S)
        except TypeError:
            f = ImageFont.load_default()
    _cache[key] = f
    return f


def subject_color(name: str):
    h = int(hashlib.md5(name.lower().encode()).hexdigest(), 16) % 360
    r, g, b = colorsys.hls_to_rgb(h / 360, 0.62, 0.65)
    return int(r * 255), int(g * 255), int(b * 255)


def mix(c, k):
    """Assombrit une couleur vers le fond de carte (k = opacité de la couleur)."""
    return tuple(int(CARD[i] + (c[i] - CARD[i]) * k) for i in range(3))


class Canvas:
    """Toile haute ; png(y) recadre au contenu puis ajoute coins arrondis et liseré coloré."""
    MAXH = 2400

    def __init__(self, height=None, accent="blue"):
        self.img = Image.new("RGB", (W * S, self.MAXH * S), CARD)
        self.d = ImageDraw.Draw(self.img)
        self.accent = ACCENT.get(accent, accent)
        self.y = 0

    # primitives (coordonnées en px finaux)
    def rect(self, x0, y0, x1, y1, r, fill, outline=None, width=0):
        self.d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S], r * S, fill=fill,
                                 outline=outline, width=width * S)

    def text(self, x, y, s, size=20, bold=False, fill=TXT, anchor="la"):
        self.d.text((x * S, y * S), s, font=font(size, bold), fill=fill, anchor=anchor)

    def tw(self, s, size=20, bold=False):
        return self.d.textlength(s, font=font(size, bold)) / S

    def fit(self, s, max_w, size=20, bold=False):
        if self.tw(s, size, bold) <= max_w:
            return s
        while s and self.tw(s + "…", size, bold) > max_w:
            s = s[:-1]
        return s.rstrip() + "…"

    def chip(self, x, y, s, fg, bg, size=15, anchor="l"):
        w = self.tw(s, size, True) + 22
        h = size + 14
        x0 = x - w if anchor == "r" else (x - w / 2 if anchor == "m" else x)
        self.rect(x0, y, x0 + w, y + h, h / 2, bg)
        self.text(x0 + w / 2, y + h / 2, s, size, True, fg, "mm")
        return w

    def circle(self, x, y, r, fill=None, outline=None, width=0):
        self.d.ellipse([(x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S], fill=fill,
                       outline=outline, width=width * S)

    def line(self, x0, y0, x1, y1, fill, width=2):
        self.d.line([(x0 * S, y0 * S), (x1 * S, y1 * S)], fill=fill, width=width * S)

    def header(self, label, title, subtitle=None, chip=None, sub_color=MUTE):
        """Petit libellé, gros titre, sous-titre et pastille d'état à droite. Renvoie le y suivant."""
        self.text(PAD, 42, label.upper(), 14, True, self.accent)
        self.text(PAD, 64, title, 32, True)
        y = 112
        if subtitle:
            self.text(PAD, y, subtitle, 18, False, sub_color)
            y += 34
        if chip:
            txt, col = chip
            self.chip(W - PAD, 44, txt, col, mix(col, 0.22), 16, "r")
        return y + 6

    def png(self, bottom=None):
        h = int((bottom or self.y) + 30)
        content = self.img.crop((0, 0, W * S, h * S))
        out = Image.new("RGB", (W * S, h * S), BG)
        mask = Image.new("L", out.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, W * S - 1, h * S - 1], 22 * S, fill=255)
        top = Image.new("RGB", out.size, self.accent)  # liseré : la couleur dépasse de 5 px en haut
        out.paste(top, (0, 0), mask)
        inner = Image.new("L", out.size, 0)
        ImageDraw.Draw(inner).rounded_rectangle([0, 5 * S, W * S - 1, h * S - 1], 22 * S, fill=255)
        out.paste(content, (0, 0), inner)
        out = out.resize((W, h), Image.LANCZOS)
        buf = io.BytesIO()
        out.save(buf, "PNG", optimize=True)
        return buf.getvalue()


# ---------- icônes dessinées (pas d'emoji dans Pillow) ----------
def icon_status(c: Canvas, x, y, kind, r=26):
    col = {"ok": ACCENT["green"], "late": ACCENT["orange"], "cancel": ACCENT["red"]}.get(kind, ACCENT["grey"])
    c.circle(x, y, r, fill=mix(col, 0.25))
    c.circle(x, y, r - 6, fill=col)
    w = 4
    if kind == "ok":
        c.line(x - 9, y + 1, x - 3, y + 8, CARD, w)
        c.line(x - 3, y + 8, x + 10, y - 7, CARD, w)
    elif kind == "cancel":
        c.line(x - 8, y - 8, x + 8, y + 8, CARD, w)
        c.line(x + 8, y - 8, x - 8, y + 8, CARD, w)
    else:
        c.line(x, y - 10, x, y + 3, CARD, w)
        c.circle(x, y + 9, 2.5, fill=CARD)


# ---------- frise du trajet ----------
ROUTE_H = 190


def draw_route(c: Canvas, y, stops, legs):
    """Frise horizontale : arrêts (heure + nom) reliés par des segments colorés."""
    n = len(stops)
    x0, x1, ly = 80, W - 80, y + 58
    xs = [x0 + i * (x1 - x0) / (n - 1) for i in range(n)]
    for i, leg in enumerate(legs):
        a, b = xs[i] + 15, xs[i + 1] - 15
        col = LINE_COL.get(leg["kind"], ACCENT["grey"])
        soft = leg["kind"] in ("walk", "car")
        if soft:
            x = a
            while x < b:
                c.line(x, ly, min(x + 7, b), ly, col, 5)
                x += 14
        else:
            c.rect(a, ly - 5, b, ly + 5, 5, col)
        mid = (a + b) / 2
        lw = c.tw(leg["label"], 15, True) + 24
        c.rect(mid - lw / 2, ly - 47, mid + lw / 2, ly - 19, 14, ROW if soft else col)
        c.text(mid, ly - 33, leg["label"], 15, True, TXT if soft else (18, 18, 18), "mm")
        if leg.get("detail"):
            c.text(mid, ly + 24, leg["detail"], 14, False, MUTE, "mm")
    for i, st in enumerate(stops):
        x = xs[i]
        col = ACCENT["red"] if st.get("warn") else (ACCENT["orange"] if st.get("delay") else TXT)
        c.circle(x, ly, 14, fill=CARD, outline=col, width=5)
        if i in (0, n - 1):
            c.circle(x, ly, 6, fill=col)
        t = st["time"] + (f" +{st['delay']}" if st.get("delay") else "")
        c.text(x, ly + 62, t, 26, True, col, "mm")
        c.text(x, ly + 94, st["name"], 16, False, MUTE, "mm")
    return y + ROUTE_H


def route_data(r: dict, school_name: str, stop_name: str):
    """Arrêts + segments à partir d'un résultat de trains.plan_aller (ou équivalent)."""
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
    return {"stops": stops, "legs": legs, "late": late,
            "school_arr": hm(ch["school_arr"]) if ch else None, "course": hm(r["course"])}


def _pills_row(c: Canvas, y, label, items):
    """Ligne « Autres trains : [06:50] [07:31 trop tard] »."""
    c.text(PAD, y + 7, label, 15, True, MUTE)
    x = PAD + c.tw(label, 15, True) + 16
    for txt, warn in items:
        x += c.chip(x, y, txt, ACCENT["red"] if warn else TXT, mix(ACCENT["red"], .2) if warn else ROW, 15) + 8
    return y + 44


def _routes_rows(c: Canvas, y, title, routes):
    """Itinéraires sans le N : heure, flèche, lignes."""
    c.text(PAD, y, title, 15, True, MUTE)
    y += 30
    hm = lambda x: x.strftime("%H:%M")
    for r in routes:
        c.rect(PAD, y, W - PAD, y + 46, 12, ROW)
        c.text(PAD + 18, y + 23, f"{hm(r['dep'])} → {hm(r['arr'])}", 19, True, TXT, "lm")
        x = PAD + 200
        for leg in r["legs"]:
            x += c.chip(x, y + 9, leg, TXT, LINE, 14) + 8
        y += 54
    return y


# ---------- images publiques ----------
def aller_png(r, school_name, stop_name, others=(), alt=False, backups=()):
    rd = route_data(r, school_name, stop_name)
    if not rd:
        return None
    o = r["origin"]
    h = 160 + ROUTE_H + (50 if others else 0) + (40 + 54 * len(backups) if backups else 0) + 20
    c = Canvas(h, "grey" if alt else ("orange" if rd["late"] else "purple"))
    sub = f"Arrivée {school_name} à {rd['school_arr']} · cours à {rd['course']}" if rd["school_arr"] else None
    chip = ("EN RETARD", ACCENT["red"]) if rd["late"] else (None if alt else ("CONSEILLÉ", ACCENT["purple"]))
    y = c.header("Autre option" if alt else "Trajet du matin",
                 f"Départ {r['leave'].strftime('%H:%M')} · {o['name']}", sub, chip,
                 ACCENT["orange"] if rd["late"] else MUTE)
    y = draw_route(c, y - 6, rd["stops"], rd["legs"])
    if others:
        y = _pills_row(c, y, "Autres trains", others)
    if backups:
        y = _routes_rows(c, y + 4, "SANS LE N", backups)
    return c.png(y - 10)


def edt_png(title, subtitle, courses):
    """Emploi du temps de la journée sous forme de liste visuelle."""
    rows = []
    prev_end = None
    for cr in courses:
        if prev_end and not cr.get("virtual"):
            gap = _minutes(cr["start"]) - _minutes(prev_end)
            if gap >= 30:
                rows.append(("gap", gap))
        rows.append(("course", cr))
        if not cr.get("virtual"):
            prev_end = cr["end"]
    h = 150 + sum(36 if k == "gap" else 84 for k, _ in rows) + 24
    if not courses:
        h = 220
    c = Canvas(h, "blue" if courses else "grey")
    y = c.header("Emploi du temps", title, subtitle)
    if not courses:
        c.text(PAD, y + 10, "Pas cours", 24, True, MUTE)
        return c.png(y + 40)
    for kind, v in rows:
        if kind == "gap":
            hh, mm = divmod(v, 60)
            label = f"Pause · {hh} h {mm:02d}" if hh else f"Pause · {mm} min"
            c.line(PAD + 130, y + 18, W - PAD, y + 18, LINE, 1)
            c.rect(PAD + 130, y + 6, PAD + 140 + c.tw(label, 14, True) + 12, y + 30, 12, CARD)
            c.text(PAD + 140, y + 18, label, 14, True, DIM, "lm")
            y += 36
            continue
        cr = v
        virt = cr.get("virtual")
        col = subject_color(cr["summary"])
        c.rect(PAD, y, W - PAD, y + 74, 14, ROW)
        c.text(PAD + 20, y + 14, cr["start"], 24, True, TXT)
        c.text(PAD + 20, y + 46, cr["end"], 16, False, MUTE)
        bx = PAD + 112
        if virt:
            for yy in range(int(y + 12), int(y + 62), 10):
                c.rect(bx, yy, bx + 6, yy + 6, 3, col)
        else:
            c.rect(bx, y + 12, bx + 6, y + 62, 3, col)
        chips_w = 0
        tags = [(cr.get("type"), TXT, LINE)] if cr.get("type") else []
        if virt:
            tags.append(("EN LIGNE", ACCENT["teal"], mix(ACCENT["teal"], .25)))
        x = W - PAD - 16
        for t, fg, bg in reversed(tags):
            w = c.chip(x, y + 23, t, fg, bg, 14, "r")
            x -= w + 8
            chips_w += w + 8
        tx = bx + 26
        max_w = W - PAD - 16 - chips_w - tx - 10
        c.text(tx, y + 13, c.fit(cr["summary"], max_w, 22, True), 22, True)
        meta = "Cours à distance" if virt else (cr.get("location") or "")
        c.text(tx, y + 45, c.fit(meta, max_w, 16), 16, False, MUTE)
        y += 84
    return c.png(y - 10)


def retour_png(title, subtitle, columns):
    """columns = [(nom gare, [(dep, arr, delay)]), ...] : la 1re colonne est la gare du matin."""
    n_rows = max((len(t) for _, t in columns), default=0)
    h = 160 + 40 + n_rows * 62 + 20
    c = Canvas(h, "teal")
    y = c.header("Retour", title, subtitle)
    ncol = max(1, len(columns))
    gap = 20
    cw = (W - 2 * PAD - gap * (ncol - 1)) / ncol
    y_end = y + 40
    for i, (name, trips) in enumerate(columns):
        x = PAD + i * (cw + gap)
        c.text(x, y, f"Vers {name}".upper(), 14, True, ACCENT["teal"] if i == 0 else MUTE)
        yy = y + 32
        if not trips:
            c.text(x, yy + 10, "Aucun train", 18, False, MUTE)
        for j, (dep, arr, delay) in enumerate(trips):
            first = j == 0
            c.rect(x, yy, x + cw, yy + 52, 14, mix(ACCENT["teal"], .18) if (first and i == 0) else ROW)
            c.text(x + 18, yy + 26, dep, 24, True, TXT, "lm")
            c.text(x + 18 + c.tw(dep, 24, True) + 12, yy + 26, f"→ {arr}", 18, False, MUTE, "lm")
            if delay and delay > 0:
                c.chip(x + cw - 12, yy + 11, f"+{delay} min", ACCENT["orange"], mix(ACCENT["orange"], .22), 14, "r")
            elif first and i == 0:
                c.chip(x + cw - 12, yy + 11, "PROCHAIN", ACCENT["teal"], mix(ACCENT["teal"], .25), 13, "r")
            yy += 62
        y_end = max(y_end, yy)
    return c.png(y_end - 10)


def status_png(kind, title, subtitle, route=None, others=(), backups=()):
    """Alerte du matin : état du train + frise + alternatives."""
    accent = {"ok": "green", "late": "orange", "cancel": "red"}[kind]
    h = 160 + (ROUTE_H if route else 0) + (50 if others else 0) + (40 + 54 * len(backups) if backups else 0) + 20
    c = Canvas(h, accent)
    label = {"ok": "Train à l'heure", "late": "Retard", "cancel": "Train supprimé"}[kind]
    c.text(PAD + 66, 42, label.upper(), 14, True, c.accent)
    c.text(PAD + 66, 64, title, 32, True)
    icon_status(c, PAD + 26, 76, kind)
    y = 112
    if subtitle:
        c.text(PAD + 66, y, subtitle, 18, False, MUTE)
        y += 34
    y += 6
    if route:
        y = draw_route(c, y - 6, route["stops"], route["legs"])
    if others:
        y = _pills_row(c, y, "Autres trains N", others)
    if backups:
        y = _routes_rows(c, y + 4, "SANS LE N", backups)
    return c.png(y - 10)


def changes_png(groups):
    """groups = [(jour, [(kind, nom, détail)])] avec kind ∈ add / del / mod."""
    n = sum(len(g) for _, g in groups)
    h = 150 + sum(40 + 62 * len(g) for _, g in groups) + 10
    c = Canvas(h, "orange")
    y = c.header("Emploi du temps modifié", f"{n} changement{'s' if n > 1 else ''}")
    tags = {"add": ("NOUVEAU", ACCENT["green"]), "del": ("ANNULÉ", ACCENT["red"]), "mod": ("DÉPLACÉ", ACCENT["orange"])}
    for day, items in groups:
        c.text(PAD, y, day.upper(), 14, True, MUTE)
        y += 30
        for kind, name, detail in items:
            t, col = tags[kind]
            c.rect(PAD, y, W - PAD, y + 54, 14, ROW)
            w = c.chip(PAD + 14, y + 12, t, col, mix(col, .22), 13)
            tx = PAD + 14 + w + 16
            c.text(tx, y + 27, c.fit(name, 330, 19, True), 19, True, TXT, "lm")
            c.text(W - PAD - 18, y + 27, c.fit(detail, 420, 16), 16, False, MUTE, "rm")
            y += 62
        y += 10
    return c.png(y - 20)


def virtual_png(course):
    c = Canvas(270, "teal")
    y = c.header("Cours en ligne", f"{course['start']} – {course['end']}", None,
                 ("EN LIGNE", ACCENT["teal"]))
    c.rect(PAD, y, W - PAD, y + 82, 16, ROW)
    c.rect(PAD + 18, y + 16, PAD + 24, y + 66, 3, subject_color(course["summary"]))
    c.text(PAD + 42, y + 14, c.fit(course["summary"], W - 2 * PAD - 220, 24, True), 24, True)
    c.text(PAD + 42, y + 48, "Ouvre l'app pour te mettre présent", 17, False, MUTE)
    if course.get("type"):
        c.chip(W - PAD - 18, y + 26, course["type"], TXT, LINE, 15, "r")
    return c.png(y + 82)


def simple_png(label, title, subtitle, accent="green", kind="ok"):
    c = Canvas(170, accent)
    c.text(PAD + 66, 42, label.upper(), 14, True, c.accent)
    c.text(PAD + 66, 64, title, 30, True)
    c.text(PAD + 66, 110, subtitle, 18, False, MUTE)
    icon_status(c, PAD + 26, 80, kind)
    return c.png(130)


def _minutes(hm: str) -> int:
    h, m = map(int, hm.split(":"))
    return h * 60 + m
