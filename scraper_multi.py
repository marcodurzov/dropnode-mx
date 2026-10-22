# =============================================================
# DROPNODE MX — scraper_multi.py  (v1.0)
# Motor de scraping para tiendas SIN API conocida.
# Por cada tienda: descarga páginas de ofertas (y las descubre desde la
# home) y extrae productos con 4 estrategias, en este orden:
#   1) JSON-LD (schema.org Product / ItemList)
#   2) JSON embebido (__NEXT_DATA__, __STATE__, etc.) buscando nombre+precio+precio tachado
#   3) API VTEX (/api/catalog_system/pub/products/search)
#   4) Heurística HTML (precio tachado + precio actual dentro de una tarjeta)
# Soporta proxy (PROXY_URL) y detecta páginas de bloqueo para reportarlas.
# NOTA: escrito sin acceso a los sitios; diagnostico.py dice cuál estrategia
# funciona en cada tienda desde GitHub Actions.
# =============================================================
import re, json, time, random, logging, hashlib, os
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

UA = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]
BLOQUEO = ["access denied", "captcha", "px-captcha", "just a moment", "cf-chl", "robot check",
           "are you a human", "request unsuccessful", "unusual traffic", "akamai", "errors.edgesuite",
           "enable javascript and cookies", "pardon our interruption"]
MIN_DESC = 0.15
MIN_PRECIO = 150            # debajo de esto no vale la pena una alerta (y suele ser precio por unidad)
MAX_DESC = 0.85             # arriba de esto casi siempre es dato roto
MAX_DESC_HTML = 0.75        # la heurística HTML se equivoca más: tope más estricto

# clave: (nombre visible, emoji, base, [urls de ofertas/home], vtex?)
TIENDAS = {
    "liverpool": ("Liverpool", "🏬", "https://www.liverpool.com.mx",
                  ["/tienda/home", "/tienda/ofertas-y-promociones", "/tienda/liquidacion"], False),
    "palacio":   ("Palacio de Hierro", "💎", "https://www.elpalaciodehierro.com",
                  ["/", "/outlet", "/ofertas"], True),
    "costco":    ("Costco", "🏪", "https://www.costco.com.mx",
                  ["/", "/ofertas-especiales"], False),
    "sams":      ("Sam's Club", "🏬", "https://www.sams.com.mx",
                  ["/", "/ofertas"], False),
    "heb":       ("HEB", "🛒", "https://www.heb.com.mx",
                  ["/", "/ofertas"], True),
    "sears":     ("Sears", "🏬", "https://www.sears.com.mx",
                  ["/", "/ofertas"], False),
    "elektra":   ("Elektra", "⚡", "https://www.elektra.mx",
                  ["/", "/ofertas"], True),
    "bodega":    ("Bodega Aurrerá", "🛒", "https://www.bodegaaurrera.com.mx",
                  ["/inicio", "/ofertas"], False),
    "amazon":    ("Amazon", "📦", "https://www.amazon.com.mx",
                  ["/gp/goldbox", "/deals"], False),
    "walmart":   ("Walmart", "🛒", "https://www.walmart.com.mx",
                  ["/", "/content/ofertas"], False),
    "coppel":    ("Coppel", "🏪", "https://www.coppel.com",
                  ["/", "/ofertas"], False),
    "bestbuy":   ("Best Buy", "🛍️", "https://www.bestbuy.com.mx",
                  ["/", "/c/ofertas"], False),
    "officedepot": ("Office Depot", "🖇️", "https://www.officedepot.com.mx",
                  ["/", "/ofertas"], False),
    "homedepot": ("The Home Depot", "🔨", "https://www.homedepot.com.mx",
                  ["/", "/ofertas"], False),
    "cyberpuerta": ("Cyberpuerta", "💻", "https://www.cyberpuerta.mx",
                  ["/", "/Ofertas/"], False),
    "suburbia":  ("Suburbia", "👗", "https://www.suburbia.com.mx",
                  ["/", "/ofertas"], True),
    "sanborns":  ("Sanborns", "🏬", "https://www.sanborns.com.mx",
                  ["/", "/ofertas"], False),
    "claroshop": ("Claro Shop", "🛒", "https://www.claroshop.com",
                  ["/", "/ofertas"], False),
}
PALABRAS_OFERTA = ["oferta", "sale", "rebaja", "outlet", "promo", "descuento", "liquida", "hot-sale",
                   "buen-fin", "remate", "deals", "goldbox", "especial"]


# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────
def _precio(t):
    if t is None:
        return 0.0
    if isinstance(t, (int, float)):
        return float(t)
    s = str(t)
    m = re.search(r"\d[\d,]*\.?\d*", s.replace("\xa0", " "))
    if not m:
        return 0.0
    try:
        return float(m.group(0).replace(",", ""))
    except Exception:
        return 0.0


def _sesion():
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(UA),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.6",
        "Accept-Encoding": "gzip, deflate",            # sin 'br': requests no lo decodifica
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def _intento(s, url, referer, proxies=None):
    """(html, status, nota) de UN intento."""
    try:
        h = {"Referer": referer} if referer else {}
        r = s.get(url, headers=h, timeout=25, allow_redirects=True, proxies=proxies)
        txt = r.text or ""
        low = txt[:6000].lower()
        if r.status_code in (403, 429, 503) or any(b in low for b in BLOQUEO) and len(txt) < 60000:
            return txt, r.status_code, "BLOQUEADA"
        if r.status_code != 200:
            return txt, r.status_code, f"HTTP {r.status_code}"
        if len(txt) < 1500:
            return txt, r.status_code, "VACIA"
        return txt, r.status_code, ""
    except Exception as e:
        return "", 0, f"ERROR {str(e)[:80]}"


PROXY_PAGINAS_DIA = 16        # tope de páginas de tiendas que pueden pasar por el navegador+proxy cada día


def _proxy_permitido():
    """True si todavía hay cupo diario de páginas por proxy (candado en Supabase)."""
    if os.environ.get("PROXY_SIN_TOPE") == "1":
        return True
    try:
        import estado as E
        import horarios as H
        for i in range(PROXY_PAGINAS_DIA):
            if E.reclamar_evento(f"pxy:{H.fecha_mx()}:{i}", fallback=False):
                return True
    except Exception:
        pass
    return False


def _fetch_navegador_proxy(url):
    """(html, status, nota) abriendo la página con Chromium POR EL PROXY (sin imágenes/CSS)."""
    if os.environ.get("RENDER_JS", "1") != "1":
        return "", 0, "sin navegador"
    try:
        import navegador as NAV
        proxy = NAV.proxy_cfg()
        if not proxy:
            return "", 0, "sin proxy"
        if not _proxy_permitido():
            return "", 0, "tope diario de proxy"
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            b, page = NAV.lanzar(pw, proxy=proxy)
            page.goto(url, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(4000)
            html_ = page.content()
            b.close()
        low = html_[:6000].lower()
        if len(html_) < 1500 or (any(x in low for x in BLOQUEO) and len(html_) < 60000):
            return html_, 200, "BLOQUEADA"
        return html_, 200, ""
    except Exception as e:
        return "", 0, f"ERROR {str(e)[:80]}"


def descargar(url, sesion=None, referer=None, espera=(2, 5)):
    """(html, status, nota). nota: '', 'BLOQUEADA', 'VACIA' o el error.
    Primero directo (gratis); si lo bloquean y hay PROXY_URL, reintenta por el proxy
    (así el plan de GB del proxy solo se gasta en las tiendas que lo necesitan)."""
    s = sesion or _sesion()
    time.sleep(random.uniform(*espera))
    txt, st, nota = _intento(s, url, referer)
    if nota in ("BLOQUEADA",) or nota.startswith("ERROR"):
        p = os.environ.get("PROXY_URL", "").strip()
        if p:
            time.sleep(random.uniform(1, 3))
            txt2, st2, nota2 = _intento(s, url, referer, proxies={"http": p, "https": p})
            if not nota2:
                return txt2, st2, ""
            txt3, st3, nota3 = _fetch_navegador_proxy(url)      # último recurso: navegador por proxy
            if not nota3:
                return txt3, st3, ""
            return txt2, st2, nota2 + " [proxy]"
    return txt, st, nota


def _abs(base, href):
    if not href:
        return ""
    if href.startswith("//"):
        return "https:" + href
    return urljoin(base + "/", href)


# ─────────────────────────────────────────────
# Estrategia 1: JSON-LD
# ─────────────────────────────────────────────
def _walk_ld(o, out):
    if isinstance(o, list):
        for x in o:
            _walk_ld(x, out)
    elif isinstance(o, dict):
        t = o.get("@type")
        tipos = t if isinstance(t, list) else [t]
        if "Product" in tipos:
            out.append(o)
        for k in ("itemListElement", "item", "@graph", "mainEntity", "hasVariant"):
            if k in o:
                _walk_ld(o[k], out)


def extraer_jsonld(soup, base):
    res = []
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(sc.string or sc.get_text() or "null")
        except Exception:
            continue
        prods = []
        _walk_ld(data, prods)
        for p in prods:
            offers = p.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            precio = _precio(offers.get("price") or offers.get("lowPrice"))
            orig = 0.0
            specs = offers.get("priceSpecification")
            for sp in (specs if isinstance(specs, list) else [specs] if specs else []):
                if isinstance(sp, dict) and "list" in str(sp.get("priceType", "")).lower():
                    orig = max(orig, _precio(sp.get("price")))
            orig = max(orig, _precio(offers.get("highPrice")))
            img = p.get("image")
            img = img[0] if isinstance(img, list) and img else (img if isinstance(img, str) else "")
            res.append({"nombre": p.get("name", ""), "precio": precio, "orig": orig,
                        "url": _abs(base, p.get("url") or offers.get("url") or p.get("@id") or offers.get("@id") or ""), "thumb": img or ""})
    return res


# ─────────────────────────────────────────────
# Estrategia 2: JSON embebido
# ─────────────────────────────────────────────
_K_NOMBRE = ("productName", "productDisplayName", "displayName", "name", "title")
_K_PRECIO = ("salePrice", "sellingPrice", "currentPrice", "finalPrice", "promoPrice", "minimumPromoPrice", "price", "activePrice", "Price")
_K_ORIG = ("wasPrice", "listPrice", "ListPrice", "originalPrice", "regularPrice", "priceBeforeDiscount",
           "oldPrice", "compareAtPrice", "previousPrice", "basePrice", "strikePrice", "highPrice", "maximumListPrice")
_K_URL = ("canonicalUrl", "productUrl", "url", "link", "linkText", "permalink", "href", "slug")
_K_IMG = ("thumbnailUrl", "imageUrl", "image", "img", "thumbnail", "primaryImage")


def _val(d, keys):
    for k in keys:
        if k in d and d[k] not in (None, "", {}, []):
            v = d[k]
            if isinstance(v, dict):                      # {"price": 123} / {"value": 123}
                for kk in ("price", "value", "amount", "currentPrice", "min"):
                    if kk in v:
                        return v[kk]
                continue
            if isinstance(v, list) and v:
                v = v[0]
                if isinstance(v, dict):
                    v = v.get("url") or v.get("imageUrl") or v.get("src") or ""
            return v
    return None


def _walk_json(o, out, prof=0):
    if prof > 14:
        return
    if isinstance(o, dict):
        nombre = _val(o, _K_NOMBRE)
        precio = _precio(_val(o, _K_PRECIO))
        orig = _precio(_val(o, _K_ORIG))
        if isinstance(nombre, str) and len(nombre) > 4 and precio > 0 and orig > precio:
            out.append({"nombre": nombre, "precio": precio, "orig": orig,
                        "url": str(_val(o, _K_URL) or ""), "thumb": str(_val(o, _K_IMG) or "")})
        for v in o.values():
            if isinstance(v, (dict, list)):
                _walk_json(v, out, prof + 1)
    elif isinstance(o, list):
        for v in o[:400]:
            if isinstance(v, (dict, list)):
                _walk_json(v, out, prof + 1)


def extraer_json_embebido(soup, base):
    res = []
    for sc in soup.find_all("script"):
        txt = sc.string or sc.get_text() or ""
        if len(txt) < 200:
            continue
        blobs = []
        if sc.get("type") == "application/json" or sc.get("id") == "__NEXT_DATA__":
            blobs.append(txt)
        else:
            for m in re.finditer(r"=\s*(\{.{200,}\})\s*;?\s*$", txt, re.S):
                blobs.append(m.group(1))
        for b in blobs:
            try:
                _walk_json(json.loads(b), res)
            except Exception:
                continue
    for r in res:
        r["url"] = _abs(base, r["url"]) if r["url"] and not r["url"].startswith("http") else r["url"]
        if r["url"] and not r["url"].startswith("http"):
            r["url"] = ""
    return res


# ─────────────────────────────────────────────
# Estrategia 3: VTEX
# ─────────────────────────────────────────────
def extraer_vtex(base, sesion, paginas=2):
    """API VTEX ordenada por mayor descuento. `paginas` x 50 productos."""
    data = []
    for i in range(paginas):
        try:
            time.sleep(random.uniform(2, 4))
            r = sesion.get(f"{base}/api/catalog_system/pub/products/search",
                           params={"O": "OrderByBestDiscountDESC", "_from": i * 50, "_to": i * 50 + 49}, timeout=20)
            if r.status_code not in (200, 206):
                if not data:
                    return [], f"HTTP {r.status_code}"
                break
            parte = r.json()
            if not isinstance(parte, list):
                if not data:
                    return [], "no-lista"
                break
            data += parte
            if len(parte) < 50:
                break
        except Exception as e:
            if not data:
                return [], f"ERROR {str(e)[:60]}"
            break
    res = []
    for p in data:
        try:
            it = (p.get("items") or [{}])[0]
            oferta = ((it.get("sellers") or [{}])[0]).get("commertialOffer", {})
            if int(oferta.get("AvailableQuantity", 0) or 0) <= 0:
                continue
            img = ((it.get("images") or [{}])[0]).get("imageUrl", "")
            res.append({"nombre": p.get("productName", ""), "precio": _precio(oferta.get("Price")),
                        "orig": max(_precio(oferta.get("ListPrice")), _precio(oferta.get("PriceWithoutDiscount"))),
                        "url": _abs(base, p.get("link", "")),
                        "thumb": img})
        except Exception:
            continue
    return res, ""


# ─────────────────────────────────────────────
# Estrategia 4: heurística HTML
# ─────────────────────────────────────────────
_SEL_VIEJO = ("s, del, strike, [class*='old'], [class*='before'], [class*='was'], [class*='list-price'], "
              "[class*='listPrice'], [class*='original'], [class*='tachado'], [class*='strike']")


def extraer_html(soup, base):
    res, vistos = [], set()
    for viejo in soup.select(_SEL_VIEJO):
        orig = _precio(viejo.get_text(" ", strip=True))
        if orig <= 0 or "$" not in viejo.get_text() and orig < 50:
            continue
        nodo = viejo
        for _ in range(6):                               # subir hasta la tarjeta
            nodo = nodo.parent
            if nodo is None or nodo.name in ("body", "html"):
                nodo = None
                break
            if nodo.find("a", href=True) and nodo.find("img"):
                break
        if nodo is None:
            continue
        precios = []
        for el in nodo.find_all(string=re.compile(r"\$\s*\d")):
            if viejo in el.parents:
                continue
            v = _precio(el)
            if 0 < v < orig:
                precios.append(v)
        if not precios:
            continue
        pcts = [int(x) for x in re.findall(r"(\d{1,2})\s*%", nodo.get_text(" ", strip=True)) if 5 <= int(x) <= 90]
        if pcts:      # el precio correcto es el que coincide con el % de descuento que muestra la tarjeta
            precio = min(precios, key=lambda p: min(abs((orig - p) / orig * 100 - q) for q in pcts))
        else:
            precio = max(precios)
        a = nodo.find("a", href=True)
        img = nodo.find("img")
        nombre = ""
        for t in nodo.find_all(["h1", "h2", "h3", "h4", "h5"]):
            nombre = t.get_text(" ", strip=True)
            if len(nombre) > 4:
                break
        if len(nombre) <= 4 and img:
            nombre = img.get("alt", "")
        if len(nombre) <= 4 and a:
            nombre = a.get("title") or a.get_text(" ", strip=True)
        url = _abs(base, a["href"]) if a else ""
        clave = (nombre[:30], precio)
        if len(nombre) > 4 and url and clave not in vistos:
            vistos.add(clave)
            thumb = (img.get("src") or img.get("data-src") or "") if img else ""
            res.append({"nombre": nombre, "precio": precio, "orig": orig, "url": url, "thumb": thumb, "pcts": pcts})
    return res


# ─────────────────────────────────────────────
# Parser dedicado de Liverpool: tarjetas de catálogo (selectores tomados de un repo público)
#   li.m-product__card · h3.a-card-brand · h3.card-title · p.a-card-price · p.a-card-discount
# ─────────────────────────────────────────────
def extraer_liverpool(soup, base):
    res = []
    for card in soup.select("li.m-product__card"):
        try:
            a = card.select_one("a[href]")
            marca = card.select_one("h3.a-card-brand")
            titulo = card.select_one("h3.card-title, .a-card-description")
            pr = card.select_one("p.a-card-price, .a-card-price")
            ds = card.select_one("p.a-card-discount, .a-card-discount")
            if not (a and pr and ds):
                continue
            precio = _precio(pr.get_text(" ", strip=True))
            m = re.search(r"(\d{1,2})\s*%", ds.get_text(" ", strip=True))
            if precio <= 0 or not m:
                continue
            pct = int(m.group(1))
            if not 5 <= pct <= 90:
                continue
            nombre = " ".join(x.get_text(" ", strip=True) for x in (marca, titulo) if x)
            img = card.select_one("img")
            res.append({"nombre": nombre, "precio": precio, "orig": round(precio / (1 - pct / 100)),
                        "url": _abs(base, a["href"]),
                        "thumb": (img.get("src") or img.get("data-src") or "") if img else "", "pcts": [pct]})
        except Exception:
            continue
    return res


# ─────────────────────────────────────────────
# Orquestación por tienda
# ─────────────────────────────────────────────
def _descubrir(soup, base, n=3):
    cand, vistos = [], set()
    host = urlparse(base).netloc.replace("www.", "")
    for a in soup.find_all("a", href=True):
        h = a["href"]
        u = _abs(base, h)
        if host not in urlparse(u).netloc or u in vistos or "#" in h and len(h) < 3:
            continue
        low = (h + " " + a.get_text(" ", strip=True)).lower()
        if any(p in low for p in PALABRAS_OFERTA) and len(u) < 160:
            vistos.add(u)
            cand.append(u)
    return cand[:n]


def _categoria(nombre):
    n = nombre.lower()
    reglas = [(("celular", "iphone", "smartphone", "galaxy", "redmi", "moto g"), ("Celulares", "📱")),
              (("televisor", "smart tv", "pantalla", "oled", "qled", " tv"), ("Televisores", "📺")),
              (("laptop", "notebook", "macbook", "tablet", "ipad", "computadora"), ("Computación", "💻")),
              (("audifono", "audífono", "bocina", "airpods", "speaker"), ("Audio", "🎧")),
              (("lavadora", "refrigerador", "estufa", "microondas", "licuadora", "freidora", "aspiradora"), ("Electrodomésticos", "🏠")),
              (("consola", "playstation", "xbox", "nintendo"), ("Videojuegos", "🎮")),
              (("perfume", "fragancia", "maquillaje", "crema"), ("Belleza", "💄")),
              (("tenis", "zapato", "playera", "pantal", "vestido", "chamarra", "camisa"), ("Moda", "👗")),
              (("juguete", "lego", "muñeca", "muneca"), ("Juguetes", "🧸")),
              (("colchon", "colchón", "sofa", "sofá", "mueble", "silla", "mesa"), ("Hogar", "🛋️"))]
    for claves, cat in reglas:
        if any(c in n for c in claves):
            return cat
    return ("Ofertas", "🛍️")


def _limpiar_nombre(n):
    n = re.sub(r"\s+", " ", str(n or "")).strip()
    n = re.sub(r"\s*\$\s?[\d.,]+(\s*(MXN|mxn))?", " ", n)            # "…Urban Escape $943.11" -> sin precio
    return re.sub(r"\s+", " ", n).strip(" -–|·")


def _a_item(clave, r, estrategia="", razones=None):
    nombre_t, emoji_t, base, _, _ = TIENDAS[clave]

    def no(motivo):
        if razones is not None:
            razones[motivo] = razones.get(motivo, 0) + 1
        return None

    nombre = _limpiar_nombre(r.get("nombre", ""))
    precio, orig = float(r.get("precio") or 0), float(r.get("orig") or 0)
    url = r.get("url") or ""
    if not nombre or len(nombre) < 5:
        return no("sin_nombre")
    if not url.startswith("http"):
        return no("sin_url")
    if precio < MIN_PRECIO:
        return no("precio_bajo")
    if orig <= precio:
        return no("sin_precio_tachado")
    if orig == int(orig) and 2020 <= orig <= 2030:      # "Hot Sale 2026" no es un precio
        return no("precio_anterior_parece_anio")
    desc = (orig - precio) / orig
    tope = MAX_DESC_HTML if estrategia == "html" else MAX_DESC
    if estrategia == "html":                        # la heurística HTML exige evidencia: un % visible que cuadre con los precios
        pcts = r.get("pcts") or []
        if not pcts:
            return no("sin_porcentaje_visible")
        if not any(abs(q - desc * 100) <= 4 for q in pcts):
            return no("porcentaje_no_coincide")
    if desc < MIN_DESC:
        return no("descuento_menor_15")
    if desc > tope:
        return no("descuento_sospechoso")
    ratio = orig / precio
    if estrategia == "html" and any(abs(ratio - n) / n < 0.012 for n in (4, 6, 9, 10, 12, 18, 24)):
        return no("parece_mensualidad")             # "4 pagos de $X", meses sin intereses, precio por unidad…
    cat_n, cat_e = _categoria(nombre)
    return {"tienda": clave, "nombre": nombre[:90], "precio_actual": precio, "precio_original": orig,
            "descuento": desc, "sku": hashlib.md5(url.split("?")[0].encode()).hexdigest()[:14],
            "url": url, "thumbnail": r.get("thumb") or "", "categoria": {"nombre": cat_n, "emoji": cat_e},
            "envio_gratis": False}


def _renderizar(url, espera_ms=4000):
    """HTML ya ejecutado con JavaScript (Playwright). '' si no se puede."""
    if os.environ.get("RENDER_JS", "1") != "1":
        return ""
    try:
        from playwright.sync_api import sync_playwright
        import navegador as NAV
        with sync_playwright() as pw:
            b, page = NAV.lanzar(pw)
            page.goto(url, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(espera_ms)
            page.evaluate("window.scrollBy(0, 2500)")
            page.wait_for_timeout(1500)
            html_ = page.content()
            b.close()
            return html_
    except Exception as e:
        logger.warning(f"[RENDER] {url[:60]}: {str(e)[:80]}")
        return ""


def _estrategias(paginas, base, detalle, clave):
    """Corre las 3 estrategias sobre las páginas; devuelve lista de (estrategia, crudo)."""
    crudos = []
    estrategias = [("jsonld", extraer_jsonld), ("json_embebido", extraer_json_embebido), ("html", extraer_html)]
    if clave == "liverpool":
        estrategias.insert(0, ("liverpool", extraer_liverpool))
    for estrategia, fn in estrategias:
        total = 0
        for u, soup in paginas:
            try:
                got = fn(soup, base)
            except Exception as e:
                logger.debug(f"[MULTI {clave}] {estrategia}: {e}")
                got = []
            total += len(got)
            crudos += [(estrategia, g) for g in got]
        detalle["estrategias"][estrategia] = detalle["estrategias"].get(estrategia, 0) + total
    return crudos


def scrapear_tienda(clave, diag=None, max_paginas=4, muestras_dir=None):
    """Devuelve items estándar. Si `diag` (dict) se pasa, se llena con detalle."""
    if clave not in TIENDAS:
        return []
    nombre_t, _, base, rutas, vtex = TIENDAS[clave]
    s = _sesion()
    crudos, paginas, descubiertas = [], [], []
    detalle = {"paginas": [], "estrategias": {}}

    urls = [_abs(base, r) for r in rutas]
    for i, u in enumerate(urls):
        if len(paginas) >= max_paginas:
            break
        html_, st, nota = descargar(u, s, referer=base)
        detalle["paginas"].append({"url": u, "status": st, "bytes": len(html_), "nota": nota})
        if nota or not html_:
            continue
        soup = BeautifulSoup(html_, "html.parser")
        paginas.append((u, soup))
        if muestras_dir and len(paginas) == 1:
            _guardar_muestra(muestras_dir, f"{clave}_crudo.html", html_)
        if i == 0:
            descubiertas = [d for d in _descubrir(soup, base) if d not in urls]
    for u in descubiertas:
        if len(paginas) >= max_paginas:
            break
        html_, st, nota = descargar(u, s, referer=base)
        detalle["paginas"].append({"url": u, "status": st, "bytes": len(html_), "nota": nota})
        if not nota and html_:
            paginas.append((u, BeautifulSoup(html_, "html.parser")))

    crudos = _estrategias(paginas, base, detalle, clave)
    if vtex or not crudos:
        got, nota = extraer_vtex(base, s)
        detalle["estrategias"]["vtex"] = len(got) if not nota else nota
        crudos += [("vtex", g) for g in got]

    razones = {}

    def _filtrar(lista):
        out, vistos = [], set()
        for est, r in lista:
            it = _a_item(clave, r, est, razones)
            if it and it["sku"] not in vistos:
                vistos.add(it["sku"])
                out.append(it)
        return out

    items = _filtrar(crudos)

    # Si la página carga pero no sale ningún producto válido del HTML crudo: renderizar con JavaScript
    if not items and paginas:
        rend = []
        for u, _ in paginas[:2]:
            h2 = _renderizar(u)
            if h2:
                rend.append((u, BeautifulSoup(h2, "html.parser")))
                if muestras_dir and len(rend) == 1:
                    _guardar_muestra(muestras_dir, f"{clave}_renderizado.html", h2)
        detalle["renderizadas"] = len(rend)
        d2 = {"estrategias": {}}
        crudos2 = _estrategias(rend, base, d2, clave)
        detalle["estrategias_render"] = d2["estrategias"]
        crudos += crudos2
        items = _filtrar(crudos2)

    items.sort(key=lambda x: x["descuento"], reverse=True)
    detalle["items"] = len(items)
    detalle["candidatos_crudos"] = len(crudos)
    detalle["descartes"] = razones
    if diag is not None:
        diag.update(detalle)
        diag["muestra"] = [(i["nombre"][:40], i["precio_actual"], i["precio_original"]) for i in items[:2]]
    logger.info(f"[MULTI {clave}] páginas={len(paginas)} items={len(items)} {detalle['estrategias']} descartes={razones}")
    return items[:15]


def _guardar_muestra(carpeta, nombre, contenido, tope=900_000):
    try:
        os.makedirs(carpeta, exist_ok=True)
        with open(os.path.join(carpeta, nombre), "w", encoding="utf-8") as f:
            f.write(contenido[:tope])
    except Exception:
        pass


def ejecutar_ciclo_multi(clave):
    try:
        return scrapear_tienda(clave)
    except Exception as e:
        logger.error(f"[MULTI {clave}] {e}")
        return []


def ejecutar_ciclo_heb():
    return ejecutar_ciclo_multi("heb")
