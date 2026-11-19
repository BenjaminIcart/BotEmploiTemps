"""Notifications Web Push (appli ajoutée à l'écran d'accueil, iOS 16.4+ / Android)."""
import asyncio
import base64
import json
import logging

import db

log = logging.getLogger("push")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def keys() -> dict:
    """Clés VAPID générées au premier lancement et gardées en base."""
    k = db.get("vapid")
    if k:
        return k
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid
    v = Vapid()
    v.generate_keys()
    priv = v.private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()).decode()
    pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    k = {"private": priv, "public": _b64(pub)}
    db.put("vapid", k)
    return k


def subs() -> list:
    return db.get("push_subs", [])


def add_sub(sub: dict, label: str = ""):
    lst = [s for s in subs() if s["endpoint"] != sub.get("endpoint")]
    lst.append({"endpoint": sub["endpoint"], "keys": sub.get("keys", {}), "label": label[:80]})
    db.put("push_subs", lst)


def remove_sub(endpoint: str):
    db.put("push_subs", [s for s in subs() if s["endpoint"] != endpoint])


_vapid = None


def _vapid_obj(pem: str):
    global _vapid
    if _vapid is None:
        from py_vapid import Vapid
        _vapid = Vapid.from_pem(pem.encode())
    return _vapid


def _send_one(sub: dict, payload: str, vapid_private: str):
    from pywebpush import WebPushException, webpush
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]}, data=payload,
                vapid_private_key=_vapid_obj(vapid_private), vapid_claims={"sub": "mailto:edt-trains@example.com"},
                ttl=3600, timeout=10)
        return True
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        if code in (404, 410):  # abonnement expiré (appli supprimée, permission retirée…)
            remove_sub(sub["endpoint"])
            log.info("Abonnement push supprimé (%s)", code)
        else:
            log.warning("Push : %s", e)
    except Exception as e:
        log.warning("Push : %s", e)
    return False


async def send(title: str, body: str, url: str = "/", tag: str | None = None) -> int:
    """Envoie la notification à tous les appareils abonnés. Renvoie le nombre d'envois réussis."""
    lst = subs()
    if not lst:
        return 0
    try:
        priv = keys()["private"]
    except Exception as e:
        log.warning("Clés VAPID : %s", e)
        return 0
    payload = json.dumps({"title": title, "body": body, "url": url, "tag": tag or title})
    res = await asyncio.gather(*(asyncio.to_thread(_send_one, s, payload, priv) for s in lst))
    return sum(1 for r in res if r)


SW_JS = """
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data.json(); } catch (_) { d = {title: 'EDT & Trains', body: e.data ? e.data.text() : ''}; }
  e.waitUntil(self.registration.showNotification(d.title || 'EDT & Trains', {
    body: d.body || '', icon: '/icon-512.png', badge: '/icon-180.png', tag: d.tag, renotify: true,
    data: {url: d.url || '/'}
  }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then(list => {
    for (const c of list) { if ('focus' in c) { c.navigate(url); return c.focus(); } }
    return clients.openWindow(url);
  }));
});
"""


def icon_png(size: int) -> bytes:
    """Icône de l'appli (PNG) : dégradé bleu → indigo, avant de train blanc. iOS arrondit lui-même les coins."""
    import io

    from PIL import Image, ImageDraw
    s = size * 4
    u = s / 100
    # dégradé diagonal
    grad = Image.new("RGB", (s, s))
    top, bot = (24, 150, 255), (88, 86, 214)
    gd = ImageDraw.Draw(grad)
    for i in range(s * 2):
        t = i / (s * 2)
        col = tuple(int(top[k] + (bot[k] - top[k]) * t) for k in range(3))
        gd.line([(i, 0), (0, i)], fill=col, width=2)
    img = grad
    d = ImageDraw.Draw(img, "RGBA")
    # halo léger
    d.ellipse([10 * u, -30 * u, 110 * u, 55 * u], fill=(255, 255, 255, 28))
    # rails
    d.polygon([(30 * u, 92 * u), (40 * u, 74 * u), (44 * u, 74 * u), (36 * u, 92 * u)], fill=(255, 255, 255, 150))
    d.polygon([(70 * u, 92 * u), (60 * u, 74 * u), (56 * u, 74 * u), (64 * u, 92 * u)], fill=(255, 255, 255, 150))
    # caisse du train
    d.rounded_rectangle([25 * u, 16 * u, 75 * u, 76 * u], 15 * u, fill=(255, 255, 255, 255))
    # pare-brise
    d.rounded_rectangle([32 * u, 24 * u, 68 * u, 46 * u], 7 * u, fill=(28, 44, 92, 255))
    d.polygon([(36 * u, 44 * u), (52 * u, 26 * u), (58 * u, 26 * u), (42 * u, 44 * u)], fill=(255, 255, 255, 40))
    # bandeau
    d.rounded_rectangle([44 * u, 19 * u, 56 * u, 21.5 * u], 1.2 * u, fill=(88, 86, 214, 255))
    # phares
    for cx in (36, 64):
        d.ellipse([(cx - 4.5) * u, 56 * u, (cx + 4.5) * u, 65 * u], fill=(255, 196, 46, 255))
    d.rounded_rectangle([45 * u, 59 * u, 55 * u, 62 * u], 1.5 * u, fill=(200, 205, 220, 255))
    img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
