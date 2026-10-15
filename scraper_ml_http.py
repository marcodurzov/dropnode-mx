# =============================================================
# DROPNODE MX — scraper_ml_http.py  (v1.0)
# Ofertas de Mercado Libre por HTTP simple (sin navegador).
# Idea tomada de un scraper público (Joharjbe/mercadolibre-mx-scraper):
#   /ofertas se sirve ya renderizado en el servidor (.poly-card), así que basta
#   con pedir el HTML como un navegador normal: User-Agent de escritorio, pasar
#   primero por la portada para recibir cookies y hacer pocas peticiones lentas.
#   Si ML manda a /account-verification, /login o /challenges, se PARA.
# Importes: se leen del aria-label ('886 pesos mexicanos'), sin ambigüedad de comas/puntos.
# Con PROXY_URL: si directo da muro, reintenta por el proxy (HTML ligero = pocos MB).
# Las cookies se guardan entre corridas (.cache/ml_cookies.json; el workflow las cachea).
# =============================================================
import os, re, json, time, random, logging
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE = "https://www.mercadolibre.com.mx/ofertas"
HOME = "https://www.mercadolibre.com.mx/"
COOKIES_PATH = os.environ.get("ML_COOKIES_PATH", ".cache/ml_cookies.json")
WALL = ("account-verification", "/login", "challenges")
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache", "Pragma": "no-cache", "Upgrade-Insecure-Requests": "1",
}
# categorías de /ofertas (rotan por corrida)
CATEGORIAS = ["MLM1051", "MLM1648", "MLM1002", "MLM1144", "MLM1574", "MLM1000", "MLM1276", "MLM1430", "MLM1246", "MLM1182"]


# ─────────────────────────────────────────────
# Parseo de tarjetas
# ─────────────────────────────────────────────
def _dinero(node):
    """Importe desde aria-label ('886 pesos mexicanos' -> 886.0; '260 pesos con 58 centavos' -> 260.58)."""
    if node is None:
        return None
    label = node.get("aria-label") or ""
    m = re.search(r"(\d[\d.,]*)\s*pesos", label)
    if m:
        ent = m.group(1).replace(".", "").replace(",", "")
        if ent.isdigit():
            v = float(ent)
            c = re.search(r"con\s+(\d+)\s*centavos", label)
            return v + int(c.group(1)) / 100 if c else v
    fr = node.select_one(".andes-money-amount__fraction")
    if fr is None:
        return None
    raw = fr.get_text(strip=True).replace(".", "").replace(",", "")
    if not raw.isdigit():
        return None
    v = float(raw)
    ce = node.select_one(".andes-money-amount__cents")
    if ce is not None and ce.get_text(strip=True).isdigit():
        t = ce.get_text(strip=True)
        v += float(t) / (10 ** len(t))
    return v


def _txt(card, sel):
    n = card.select_one(sel)
    return n.get_text(" ", strip=True) if n else ""


def _limpia(href):
    if not href:
        return ""
    p = urlsplit(href)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def parsear_html(html):
    """HTML de /ofertas -> lista de dicts en el formato que usa github_scraper_ml.procesar()."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for card in soup.select(".poly-card"):
        try:
            a = card.select_one("a.poly-component__title")
            if a is None:
                continue
            titulo = a.get_text(" ", strip=True)
            href = a.get("href") or ""
            url = _limpia(href)
            m = re.search(r"MLM-?\d+", url) or re.search(r"MLM-?\d+", href)
            item_id = m.group(0).replace("-", "") if m else ""
            precio = _dinero(card.select_one(".poly-price__current .andes-money-amount"))
            anterior = _dinero(card.select_one("s.andes-money-amount--previous"))
            pct = None
            pill = card.select_one(".poly-price__label .polylabel-pill")
            if pill:
                d = re.search(r"(\d+)\s*%", pill.get_text(strip=True))
                if d:
                    pct = int(d.group(1))
            if precio and (not anterior or anterior <= precio) and pct and 5 <= pct <= 90:
                anterior = round(precio / (1 - pct / 100))
            if not (titulo and url and item_id and precio and precio > 10):
                continue
            etiqueta = _txt(card, ".poly-component__poly-label").lower()
            cuenta = _txt(card, ".poly-component__countdown") + _txt(card, ".poly-component__highlight-countdown")
            flash = bool(cuenta or "relampago" in etiqueta or "relámpago" in etiqueta)
            envio = "gratis" in _txt(card, ".poly-component__shipping-v2").lower()
            cupon_txt = _txt(card, ".poly-component__coupons")
            monto = 0.0
            if cupon_txt:
                mm = re.search(r"\$\s?([\d.,]+)", cupon_txt)
                pp = re.search(r"(\d+)\s*%", cupon_txt)
                if mm:
                    try:
                        monto = float(mm.group(1).replace(",", ""))
                    except ValueError:
                        monto = 0.0
                elif pp:
                    monto = round(precio * int(pp.group(1)) / 100)
            img = card.select_one(".poly-component__picture")
            thumb = ""
            if img is not None:
                thumb = img.get("src") or img.get("data-src") or ""
                if thumb.startswith("data:"):
                    thumb = img.get("data-src") or ""
            out.append({
                "id": item_id, "title": titulo[:100], "price": precio,
                "original_price": anterior if anterior and anterior > precio and anterior < precio * 8 else 0,
                "permalink": url, "thumbnail": thumb, "available_quantity": None,
                "tiene_cupon": bool(cupon_txt), "cupon_monto": monto,
                "precio_con_cupon": precio - monto if monto else precio,
                "es_flash": flash, "envio_gratis": envio,
            })
        except Exception as e:
            logger.debug(f"[ML HTTP] tarjeta: {e}")
    return out


# ─────────────────────────────────────────────
# Descarga
# ─────────────────────────────────────────────
def _cargar_cookies(s):
    try:
        with open(COOKIES_PATH, encoding="utf-8") as f:
            for c in json.load(f):
                s.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))
    except Exception:
        pass


def _guardar_cookies(s):
    try:
        os.makedirs(os.path.dirname(COOKIES_PATH) or ".", exist_ok=True)
        with open(COOKIES_PATH, "w", encoding="utf-8") as f:
            json.dump([{"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
                       for c in s.cookies], f)
    except Exception:
        pass


def _sesion(proxy=None):
    s = requests.Session()
    s.headers.update(HEADERS)
    if proxy:
        s.proxies.update({"http": proxy, "https": proxy})
    _cargar_cookies(s)
    try:
        s.get(HOME, timeout=30)                       # la portada da las cookies que espera un navegador
    except requests.RequestException:
        pass
    return s


def _pagina(s, url, intentos=2):
    """HTML o None. None también si ML mandó a un muro (hay que parar, no insistir)."""
    for i in range(intentos):
        try:
            r = s.get(url, timeout=30, allow_redirects=True)
        except requests.RequestException as e:
            logger.warning(f"[ML HTTP] red: {str(e)[:80]}")
            time.sleep(2 * (i + 1))
            continue
        if any(w in r.url for w in WALL):
            logger.warning(f"[ML HTTP] muro de verificación: {r.url[:100]}")
            return None
        if r.status_code == 200 and len(r.text) > 10_000:
            return r.text
        logger.warning(f"[ML HTTP] HTTP {r.status_code} ({len(r.text)} bytes) {url[:70]}")
        time.sleep(3 * (i + 1))
    return None


def obtener_raw(max_paginas=4, categorias=None, usar_proxy=True, solo_proxy=False):
    """(lista_raw, info). Directo primero; si hay muro y existe PROXY_URL, reintenta por proxy."""
    info = {"paginas": 0, "muro": False, "proxy": False}
    urls = [BASE if p == 1 else f"{BASE}?page={p}" for p in range(1, max_paginas + 1)]
    for c in (categorias or []):
        urls.append(f"{BASE}?category={c}")
    proxy = os.environ.get("PROXY_URL", "").strip() if usar_proxy else ""

    modos = ([proxy] if solo_proxy else [None, proxy]) if proxy else [None]
    for modo in modos:
        s = _sesion(modo)
        vistos, res = set(), []
        for u in urls:
            html = _pagina(s, u)
            if html is None:
                info["muro"] = True
                break
            tarjetas = parsear_html(html)
            info["paginas"] += 1
            for t in tarjetas:
                if t["id"] not in vistos:
                    vistos.add(t["id"]); res.append(t)
            if not tarjetas:
                break
            time.sleep(random.uniform(1.5, 3.0))
        _guardar_cookies(s)
        if res:
            info["proxy"] = bool(modo)
            info["muro"] = False
            return res, info
    return [], info


# ─────────────────────────────────────────────
# Formato estándar para main.py
# ─────────────────────────────────────────────
def a_item(raw):
    try:
        precio, orig = float(raw["price"]), float(raw.get("original_price") or 0)
        if precio <= 0 or orig <= precio:
            return None
        desc = (orig - precio) / orig
        if desc < 0.15 or desc > 0.9:
            return None
        return {"tienda": "mercadolibre", "nombre": raw["title"][:90], "precio_actual": precio,
                "precio_original": orig, "descuento": desc, "sku": raw["id"], "url": raw["permalink"],
                "thumbnail": raw.get("thumbnail", ""), "categoria": {"nombre": "Mercado Libre", "emoji": "🛒"},
                "envio_gratis": bool(raw.get("envio_gratis")), "es_flash": bool(raw.get("es_flash"))}
    except Exception:
        return None


def ejecutar_ciclo_ml_http():
    a = time.localtime()
    base = (a.tm_yday * 4 + a.tm_hour) % len(CATEGORIAS)
    cats = [CATEGORIAS[base], CATEGORIAS[(base + 4) % len(CATEGORIAS)]]
    raws, info = obtener_raw(max_paginas=3, categorias=cats)
    items = [x for x in (a_item(r) for r in raws) if x]
    items.sort(key=lambda x: x["descuento"], reverse=True)
    logger.info(f"[ML HTTP] páginas={info['paginas']} tarjetas={len(raws)} con descuento={len(items)} "
                f"muro={info['muro']} proxy={info['proxy']}")
    return items[:20]
