# =============================================================
# DROPNODE MX — scraper_walmart.py  v2.2
# Fix: import urllib + endpoint corregido
# =============================================================

import requests, time, random, logging, urllib.parse, json, re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
]

BUSQUEDAS = [
    {"q": "celular smartphone",  "emoji": "📱", "cat": "Celulares"},
    {"q": "laptop computadora",  "emoji": "💻", "cat": "Computacion"},
    {"q": "smart tv television", "emoji": "📺", "cat": "Televisores"},
    {"q": "audifonos bluetooth", "emoji": "🎧", "cat": "Audio"},
    {"q": "videojuegos consola", "emoji": "🎮", "cat": "Videojuegos"},
    {"q": "tablet",              "emoji": "📱", "cat": "Tablets"},
]

def get_headers(html=False):
    h = {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept-Language": "es-MX,es;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer":         "https://www.walmart.com.mx/",
        "Origin":          "https://www.walmart.com.mx",
    }
    if html:
        h["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    else:
        h["Accept"] = "application/json, text/plain, */*"
    return h

def esperar():
    time.sleep(random.uniform(5, 11))

def buscar_walmart_api(query: str) -> list:
    """Método 1: API JSON de Walmart MX."""
    url = "https://www.walmart.com.mx/api/2/page"
    params = {"pathName": "/search", "query": query, "page": "1", "pageSize": "20"}
    try:
        esperar()
        resp = requests.get(url, params=params, headers=get_headers(), timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            results = (data.get("data", {})
                          .get("content", {})
                          .get("gsp", {})
                          .get("results", []))
            if results:
                return results
        logger.warning(f"[WALMART] API HTTP {resp.status_code}")
        return []
    except Exception as e:
        logger.error(f"[WALMART] API error: {e}")
        return []

def buscar_walmart_html(query: str) -> list:
    """Método 2: Scraping HTML de Walmart MX."""
    url = f"https://www.walmart.com.mx/search?q={urllib.parse.quote(query)}"
    try:
        esperar()
        resp = requests.get(url, headers=get_headers(html=True), timeout=20)
        if resp.status_code != 200:
            return []
        # Buscar JSON embebido en el HTML
        match = re.search(r'"items"\s*:\s*(\[.*?\])', resp.text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass
        # Buscar en script tags
        soup   = BeautifulSoup(resp.text, "lxml")
        scripts = soup.find_all("script", type="application/json")
        for sc in scripts:
            try:
                d = json.loads(sc.string or "")
                if isinstance(d, list) and len(d) > 0:
                    return d
            except Exception:
                continue
        return []
    except Exception as e:
        logger.error(f"[WALMART] HTML error: {e}")
        return []

def parsear_item(item: dict, cat: dict) -> dict | None:
    try:
        nombre = (item.get("name") or item.get("title") or
                  item.get("displayName") or "")[:80]

        precio_actual = float(
            item.get("price") or item.get("salePrice") or
            item.get("currentPrice") or 0)

        precio_orig = float(
            item.get("wasPrice") or item.get("originalPrice") or
            item.get("listPrice") or precio_actual)

        sku     = str(item.get("usItemId") or item.get("id") or
                      item.get("productId") or "")
        imagen  = (item.get("imageUrl") or
                  item.get("image", {}).get("url") if isinstance(item.get("image"), dict) else "")
        url_p   = item.get("canonicalUrl") or f"/ip/{sku}"
        if not url_p.startswith("http"):
            url_p = f"https://www.walmart.com.mx{url_p}"

        if not nombre or precio_actual <= 0:
            return None

        descuento = 0.0
        if precio_orig > precio_actual:
            descuento = (precio_orig - precio_actual) / precio_orig

        if descuento < 0.15:
            return None

        return {
            "tienda":          "walmart",
            "nombre":          nombre,
            "precio_actual":   precio_actual,
            "precio_original": precio_orig,
            "descuento":       descuento,
            "sku":             sku,
            "url":             url_p,
            "thumbnail":       imagen or "",
            "categoria":       {"nombre": cat["cat"], "emoji": cat["emoji"]},
        }
    except Exception:
        return None

def ejecutar_ciclo_walmart() -> list:
    logger.info("[WALMART] Iniciando ciclo...")
    resultados = []
    for cat in BUSQUEDAS[:4]:
        items = buscar_walmart_api(cat["q"])
        if not items:
            items = buscar_walmart_html(cat["q"])
        for item in items:
            r = parsear_item(item, cat)
            if r:
                resultados.append(r)
    logger.info(f"[WALMART] {len(resultados)} productos con descuento")
    return resultados
