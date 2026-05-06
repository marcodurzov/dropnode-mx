# =============================================================
# DROPNODE MX — scraper_walmart.py  v2.1
# Walmart Mexico — endpoint corregido
# =============================================================

import requests, time, random, logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
]

BUSQUEDAS = [
    {"q": "celular smartphone",   "emoji": "📱", "cat": "Celulares"},
    {"q": "laptop computadora",   "emoji": "💻", "cat": "Computacion"},
    {"q": "smart tv television",  "emoji": "📺", "cat": "Televisores"},
    {"q": "audifonos bluetooth",  "emoji": "🎧", "cat": "Audio"},
    {"q": "videojuegos consola",  "emoji": "🎮", "cat": "Videojuegos"},
    {"q": "tablet",               "emoji": "📱", "cat": "Tablets"},
]

def get_headers():
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "es-MX,es;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer":         "https://www.walmart.com.mx/",
        "Origin":          "https://www.walmart.com.mx",
    }

def esperar():
    time.sleep(random.uniform(5, 11))

def buscar_walmart(query: str) -> list:
    """Busca en Walmart MX usando su endpoint de búsqueda."""
    url    = "https://www.walmart.com.mx/api/2/page"
    params = {
        "pathName": "/search",
        "query":    query,
        "page":     "1",
        "pageSize": "20",
    }
    try:
        esperar()
        resp = requests.get(url, params=params,
                           headers=get_headers(), timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            # Navegar la estructura JSON de Walmart
            content = (data.get("data", {})
                          .get("content", {})
                          .get("gsp", {})
                          .get("results", []))
            if content:
                return content

            # Estructura alternativa
            items = (data.get("data", {})
                        .get("content", {})
                        .get("searchContent", {})
                        .get("paginationV2", {})
                        .get("resp", [{}])[0]
                        .get("items", []))
            return items

        logger.warning(f"[WALMART] HTTP {resp.status_code}")
        return []
    except Exception as e:
        logger.error(f"[WALMART] Error: {e}")
        return []

def buscar_walmart_alternativo(query: str) -> list:
    """Método alternativo: scraping del HTML de Walmart."""
    url    = f"https://www.walmart.com.mx/search?q={urllib.parse.quote(query)}"
    try:
        esperar()
        resp = requests.get(url, headers={
            **get_headers(),
            "Accept": "text/html,application/xhtml+xml",
        }, timeout=20)
        if resp.status_code != 200:
            return []

        import json, re
        # Buscar JSON de productos en el HTML
        pattern = r'"items"\s*:\s*(\[.*?\])'
        match   = re.search(pattern, resp.text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        return []
    except Exception:
        return []

def parsear_item(item: dict, cat: dict) -> dict | None:
    """Extrae datos relevantes del item de Walmart."""
    try:
        # Intentar diferentes estructuras del JSON de Walmart
        nombre = (item.get("name") or
                  item.get("title") or
                  item.get("displayName") or "")[:80]

        precio_actual = float(
            item.get("price") or
            item.get("salePrice") or
            item.get("currentPrice") or 0)

        precio_orig = float(
            item.get("wasPrice") or
            item.get("originalPrice") or
            item.get("listPrice") or
            precio_actual)

        sku      = str(item.get("usItemId") or item.get("id") or
                      item.get("productId") or "")
        imagen   = (item.get("imageUrl") or
                   item.get("image", {}).get("url") or "")
        url_prod = (item.get("canonicalUrl") or
                   f"https://www.walmart.com.mx/ip/{sku}")
        if not url_prod.startswith("http"):
            url_prod = f"https://www.walmart.com.mx{url_prod}"

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
            "url":             url_prod,
            "thumbnail":       imagen,
            "categoria":       {"nombre": cat["cat"], "emoji": cat["emoji"]},
        }
    except Exception:
        return None

def ejecutar_ciclo_walmart() -> list:
    import urllib.parse
    logger.info("[WALMART] Iniciando ciclo...")
    resultados = []
    for cat in BUSQUEDAS[:4]:
        items = buscar_walmart(cat["q"])
        if not items:
            items = buscar_walmart_alternativo(cat["q"])
        for item in items:
            r = parsear_item(item, cat)
            if r:
                resultados.append(r)
    logger.info(f"[WALMART] {len(resultados)} productos con descuento")
    return resultados
