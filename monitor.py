"""Surveillance de services (remplace Uptime Kuma) : HTTP(S), mot-clé, port TCP, ping.

- vérification à intervalle réglable par service
- « hors ligne » seulement après N échecs consécutifs (évite les fausses alertes)
- notification quand ça tombe / revient (avec la durée de la panne)
- alerte d'expiration du certificat SSL
- historique des temps de réponse, % de disponibilité 24 h / 7 j / 30 j, incidents
"""
import asyncio
import datetime as dt
import logging
import socket
import ssl
import time
from urllib.parse import urlparse

import aiohttp

import db

log = logging.getLogger("monitor")
con = db.con
con.executescript("""
CREATE TABLE IF NOT EXISTS monitors (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT DEFAULT 'http', target TEXT,
  interval INTEGER DEFAULT 60, timeout INTEGER DEFAULT 10, keyword TEXT DEFAULT '', accepted TEXT DEFAULT '200-399',
  retries INTEGER DEFAULT 2, paused INTEGER DEFAULT 0, notify INTEGER DEFAULT 1, ssl_days INTEGER DEFAULT 14,
  created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS checks (monitor_id INTEGER, ts REAL, ok INTEGER, ms INTEGER, msg TEXT);
CREATE INDEX IF NOT EXISTS checks_idx ON checks (monitor_id, ts);
CREATE TABLE IF NOT EXISTS incidents (id INTEGER PRIMARY KEY AUTOINCREMENT, monitor_id INTEGER,
  start REAL, end REAL, reason TEXT);
""")
con.commit()
# colonnes ajoutées après coup (authentification)
_cols = {r[1] for r in con.execute("PRAGMA table_info(monitors)")}
for col, ddl in (("auth_type", "TEXT DEFAULT 'none'"), ("auth_user", "TEXT DEFAULT ''"), ("auth_pass", "TEXT DEFAULT ''"),
                 ("headers", "TEXT DEFAULT ''"), ("ignore_tls", "INTEGER DEFAULT 0")):
    if col not in _cols:
        con.execute(f"ALTER TABLE monitors ADD COLUMN {col} {ddl}")
con.commit()

AUTH_TYPES = {"none": "Aucune", "basic": "Identifiant + mot de passe (Basic)", "bearer": "Jeton (Bearer)",
              "header": "En-têtes personnalisés"}
TYPES = {"http": "HTTP(S)", "keyword": "HTTP + mot-clé", "tcp": "Port TCP", "ping": "Ping"}
FIELDS = ["name", "type", "target", "interval", "timeout", "keyword", "accepted", "retries", "notify", "ssl_days",
          "auth_type", "auth_user", "auth_pass", "headers", "ignore_tls"]
_COLS = ["id", "name", "type", "target", "interval", "timeout", "keyword", "accepted", "retries", "paused",
         "notify", "ssl_days", "created", "auth_type", "auth_user", "auth_pass", "headers", "ignore_tls"]
_SEL = ",".join(_COLS)

# état en mémoire : {id: {"status": "up"/"down"/"pending", "fails": n, "last": ts, "ms":…, "msg":…, "cert_days":…}}
STATE: dict[int, dict] = {}
_notify = None  # fonction async(kind, monitor, info) branchée par main.py


# ---------- base ----------
def _row(r) -> dict:
    return dict(zip(_COLS, r))


def all_monitors() -> list[dict]:
    return [_row(r) for r in con.execute(f"SELECT {_SEL} FROM monitors ORDER BY name COLLATE NOCASE")]


def get(mid: int) -> dict | None:
    r = con.execute(f"SELECT {_SEL} FROM monitors WHERE id=?", (mid,)).fetchone()
    return _row(r) if r else None


def clean(form: dict) -> dict:
    t = form.get("type", "http")
    t = t if t in TYPES else "http"
    target = str(form.get("target", "")).strip()
    if t in ("http", "keyword") and target and not target.startswith(("http://", "https://")):
        target = "https://" + target
    name = str(form.get("name", "")).strip() or (urlparse(target).hostname or target)[:60]

    def num(k, d, lo, hi):
        try:
            return max(lo, min(hi, int(form.get(k, d))))
        except (TypeError, ValueError):
            return d
    return {"name": name[:80], "type": t, "target": target[:500], "interval": num("interval", 60, 20, 86400),
            "timeout": num("timeout", 10, 2, 60), "keyword": str(form.get("keyword", ""))[:200],
            "accepted": str(form.get("accepted", "200-399")).strip() or "200-399",
            "retries": num("retries", 2, 1, 10), "notify": 1 if form.get("notify", "1") in ("1", "on", 1, True) else 0,
            "ssl_days": num("ssl_days", 14, 0, 90),
            "auth_type": form.get("auth_type") if form.get("auth_type") in AUTH_TYPES else "none",
            "auth_user": str(form.get("auth_user", "")).strip()[:200],
            "auth_pass": str(form.get("auth_pass", ""))[:2000],
            "headers": str(form.get("headers", "")).strip()[:4000],
            "ignore_tls": 1 if form.get("ignore_tls") in ("1", "on", 1, True) else 0}


def add(form: dict) -> int:
    d = clean(form)
    cur = con.execute(f"INSERT INTO monitors ({','.join(FIELDS)}) VALUES ({','.join('?' * len(FIELDS))})",
                      [d[k] for k in FIELDS])
    con.commit()
    return cur.lastrowid


def update(mid: int, form: dict):
    d = clean(form)
    old = get(mid) or {}
    if not d["auth_pass"] and d["auth_type"] == old.get("auth_type"):
        d["auth_pass"] = old.get("auth_pass", "")  # champ vide = mot de passe / jeton inchangé
    con.execute(f"UPDATE monitors SET {','.join(k + '=?' for k in FIELDS)} WHERE id=?", [d[k] for k in FIELDS] + [mid])
    con.commit()
    STATE.pop(mid, None)


def delete(mid: int):
    for t in ("monitors WHERE id", "checks WHERE monitor_id", "incidents WHERE monitor_id"):
        con.execute(f"DELETE FROM {t}=?", (mid,))
    con.commit()
    STATE.pop(mid, None)


def set_paused(mid: int, paused: bool):
    con.execute("UPDATE monitors SET paused=? WHERE id=?", (int(paused), mid))
    con.commit()
    if paused:
        STATE.pop(mid, None)


# ---------- statistiques ----------
def uptime(mid: int, hours: int) -> float | None:
    r = con.execute("SELECT COUNT(*), SUM(ok) FROM checks WHERE monitor_id=? AND ts>=?",
                    (mid, time.time() - hours * 3600)).fetchone()
    return round(100 * (r[1] or 0) / r[0], 2) if r[0] else None


def recent(mid: int, n: int = 50) -> list[tuple]:
    """Derniers contrôles (du plus ancien au plus récent) : (ts, ok, ms, msg)."""
    rows = con.execute("SELECT ts, ok, ms, msg FROM checks WHERE monitor_id=? ORDER BY ts DESC LIMIT ?", (mid, n)).fetchall()
    return rows[::-1]


def avg_ms(mid: int, hours: int = 24) -> int | None:
    r = con.execute("SELECT AVG(ms) FROM checks WHERE monitor_id=? AND ok=1 AND ts>=?",
                    (mid, time.time() - hours * 3600)).fetchone()
    return int(r[0]) if r[0] else None


def incidents(mid: int | None = None, n: int = 20) -> list[dict]:
    q = "SELECT i.id, i.monitor_id, i.start, i.end, i.reason, m.name FROM incidents i LEFT JOIN monitors m ON m.id=i.monitor_id"
    args: tuple = ()
    if mid is not None:
        q += " WHERE i.monitor_id=?"
        args = (mid,)
    q += " ORDER BY i.start DESC LIMIT ?"
    return [dict(zip(["id", "monitor_id", "start", "end", "reason", "name"], r))
            for r in con.execute(q, args + (n,))]


def summary() -> dict:
    ms = [m for m in all_monitors() if not m["paused"]]
    st = [STATE.get(m["id"], {}).get("status", "pending") for m in ms]
    return {"total": len(ms), "up": st.count("up"), "down": st.count("down"), "pending": st.count("pending"),
            "down_names": [m["name"] for m, s in zip(ms, st) if s == "down"]}


def fmt_duration(sec: float) -> str:
    sec = int(sec)
    if sec < 90:
        return f"{sec} s"
    m = sec // 60
    if m < 90:
        return f"{m} min"
    h, m = divmod(m, 60)
    if h < 48:
        return f"{h} h {m:02d}"
    return f"{h // 24} j {h % 24} h"


# ---------- contrôles ----------
def _accepted(code: int, spec: str) -> bool:
    for part in spec.replace(" ", "").split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit() and int(a) <= code <= int(b):
                return True
        elif part.isdigit() and int(part) == code:
            return True
    return False


async def _check_http(session, m) -> tuple[bool, int, str, int | None]:
    t0 = time.perf_counter()
    cert_days = None
    headers = {"User-Agent": "EDT-Trains-Monitor/1.0"}
    auth = None
    at = m.get("auth_type") or "none"
    if at == "basic" and m.get("auth_user"):
        auth = aiohttp.BasicAuth(m["auth_user"], m.get("auth_pass") or "")
    elif at == "bearer" and m.get("auth_pass"):
        headers["Authorization"] = f"Bearer {m['auth_pass'].strip()}"
    if at == "header" or m.get("headers"):
        for line in (m.get("headers") or "").splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip():
                    headers[k.strip()] = v.strip()
    async with session.get(m["target"], timeout=aiohttp.ClientTimeout(total=m["timeout"]), allow_redirects=True,
                           headers=headers, auth=auth, ssl=False if m.get("ignore_tls") else None) as r:
        try:  # date d'expiration du certificat
            sslobj = r.connection.transport.get_extra_info("ssl_object") if r.connection else None
            cert = sslobj.getpeercert() if sslobj else None
            if cert and cert.get("notAfter"):
                exp = ssl.cert_time_to_seconds(cert["notAfter"])
                cert_days = int((exp - time.time()) // 86400)
        except Exception:
            pass
        body = await r.text(errors="ignore") if m["type"] == "keyword" else None
        ms = int((time.perf_counter() - t0) * 1000)
        if not _accepted(r.status, m["accepted"]):
            hint = " · identifiants refusés" if r.status in (401, 403) and at != "none" else (
                " · authentification requise" if r.status == 401 else "")
            return False, ms, f"HTTP {r.status}{hint}", cert_days
        if m["type"] == "keyword" and m["keyword"] and m["keyword"].lower() not in (body or "").lower():
            return False, ms, f"Mot-clé « {m['keyword']} » absent", cert_days
        return True, ms, f"HTTP {r.status}", cert_days


async def _check_tcp(m) -> tuple[bool, int, str, None]:
    host, _, port = m["target"].rpartition(":")
    host = host.strip("[]") or m["target"]
    t0 = time.perf_counter()
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(host, int(port)), m["timeout"])
        w.close()
        return True, int((time.perf_counter() - t0) * 1000), f"Port {port} ouvert", None
    except (ValueError, OSError, asyncio.TimeoutError) as e:
        return False, int((time.perf_counter() - t0) * 1000), f"Port fermé ({type(e).__name__})", None


async def _check_ping(m) -> tuple[bool, int, str, None]:
    t0 = time.perf_counter()
    proc = await asyncio.create_subprocess_exec("ping", "-c", "1", "-W", str(m["timeout"]), m["target"],
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await proc.communicate()
    ms = int((time.perf_counter() - t0) * 1000)
    txt = out.decode(errors="ignore")
    if proc.returncode == 0:
        try:
            ms = int(float(txt.split("time=")[1].split()[0]))
        except Exception:
            pass
        return True, ms, "Répond au ping", None
    if "permitted" in txt or "socket" in txt.lower():
        return False, ms, "Ping non autorisé dans le container (utilise TCP)", None
    return False, ms, "Pas de réponse au ping", None


async def check(session, m: dict) -> dict:
    """Vérifie un service, enregistre le résultat et déclenche les notifications."""
    try:
        if m["type"] in ("http", "keyword"):
            ok, ms, msg, cert = await _check_http(session, m)
        elif m["type"] == "tcp":
            ok, ms, msg, cert = await _check_tcp(m)
        else:
            ok, ms, msg, cert = await _check_ping(m)
    except asyncio.TimeoutError:
        ok, ms, msg, cert = False, m["timeout"] * 1000, f"Délai dépassé ({m['timeout']} s)", None
    except aiohttp.ClientSSLError as e:
        ok, ms, msg, cert = False, 0, "Certificat SSL invalide" + (" ou expiré" if "expired" in str(e) else ""), None
    except (aiohttp.ClientError, socket.gaierror, OSError) as e:
        ok, ms, msg, cert = False, 0, _friendly(e), None
    except Exception as e:
        ok, ms, msg, cert = False, 0, f"Erreur : {str(e)[:80]}", None
    now = time.time()
    con.execute("INSERT INTO checks VALUES (?,?,?,?,?)", (m["id"], now, int(ok), ms, msg))
    con.commit()

    st = STATE.setdefault(m["id"], {"status": "pending", "fails": 0})
    prev = st["status"]
    st.update(last=now, ms=ms, msg=msg, ok=ok)
    if cert is not None:
        st["cert_days"] = cert
    if ok:
        st["fails"] = 0
        if prev == "down":
            inc = con.execute("SELECT id, start FROM incidents WHERE monitor_id=? AND end IS NULL ORDER BY start DESC",
                              (m["id"],)).fetchone()
            dur = now - inc[1] if inc else 0
            if inc:
                con.execute("UPDATE incidents SET end=? WHERE id=?", (now, inc[0]))
                con.commit()
            st["status"] = "up"
            await _fire("up", m, {"msg": msg, "ms": ms, "duration": fmt_duration(dur)})
        else:
            st["status"] = "up"
    else:
        st["fails"] += 1
        if st["fails"] >= m["retries"] and prev != "down":
            st["status"] = "down"
            con.execute("INSERT INTO incidents (monitor_id, start, reason) VALUES (?,?,?)", (m["id"], now, msg))
            con.commit()
            await _fire("down", m, {"msg": msg, "fails": st["fails"]})
        elif prev == "pending" and st["fails"] < m["retries"]:
            st["status"] = "pending"
    # certificat bientôt expiré : 1 alerte par jour
    if cert is not None and m["ssl_days"] and cert <= m["ssl_days"]:
        k = f"sslwarn|{m['id']}|{dt.date.today()}"
        if not db.get(k):
            db.put(k, True)
            await _fire("ssl", m, {"days": cert})
    return st


def _friendly(e: Exception) -> str:
    """Message d'erreur lisible."""
    txt = str(e)
    name = type(e).__name__
    if "DNS" in name or isinstance(e, socket.gaierror) or "Name or service not known" in txt or "getaddrinfo" in txt:
        return "Nom de domaine introuvable"
    if "refused" in txt.lower() or "Connect call failed" in txt:
        return "Connexion refusée (service arrêté ?)"
    if "unreachable" in txt.lower() or "No route" in txt:
        return "Hôte injoignable"
    if "ServerDisconnected" in name:
        return "Le serveur a coupé la connexion"
    if "TooManyRedirects" in name:
        return "Trop de redirections"
    return f"Erreur réseau ({name})"


async def _fire(kind, m, info):
    if not m.get("notify") or _notify is None:
        return
    try:
        await _notify(kind, m, info)
    except Exception as e:
        log.warning("Notification monitor : %s", e)


def _restore():
    """Au démarrage : reprend l'état « hors ligne » des incidents encore ouverts."""
    for (mid,) in con.execute("SELECT DISTINCT monitor_id FROM incidents WHERE end IS NULL"):
        STATE[mid] = {"status": "down", "fails": 99}


async def loop(session):
    """Boucle principale : vérifie chaque service quand son intervalle est écoulé."""
    _restore()
    sem = asyncio.Semaphore(10)

    async def run(m):
        async with sem:
            await check(session, m)

    last_prune = 0
    while True:
        now = time.time()
        due = [m for m in all_monitors() if not m["paused"] and now - STATE.get(m["id"], {}).get("last", 0) >= m["interval"]]
        for m in due:
            STATE.setdefault(m["id"], {"status": "pending", "fails": 0})["last"] = now  # évite les doublons
            asyncio.create_task(run(m))
        if now - last_prune > 3600:  # on garde 30 jours d'historique
            con.execute("DELETE FROM checks WHERE ts < ?", (now - 30 * 86400,))
            con.commit()
            last_prune = now
        await asyncio.sleep(5)
