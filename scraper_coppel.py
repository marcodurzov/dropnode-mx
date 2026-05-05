# =============================================================
# DROPNODE MX — scraper_coppel.py
# Coppel Mexico — API publica
# =============================================================

import requests, time, random, logging
logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
]

BUSQUEDAS_COPPEL = [
    {"query": "celular",        "emoji": "📱"},
    {"query": "laptop",         "emoji": "💻"},
    {"query": "television",     "emoji": "📺"},
    {"query": "videojuego",     "emoji": "🎮"},
    {"query": "electrodomestico","emoji": "🏠"},
    {"query": "audifonos",      "emoji": "🎧"},
]

def get_headers():
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "es-MX,es;q=0.9",
        "Origin":          "https://www.coppel.com",
        "Referer":         "https://www.coppel.com/",
    }

def esperar():
    time.sleep(random.uniform(5, 10))

def buscar_coppel(query: str) -> list:
    url = "https://www.coppel.com/api/2.0/page"
    params = {
        "pageName":    "/search",
        "Ntt":         query,
        "No":          0,
        "Nrpp":        24,
        "sortBy":      "discountPercentage|1",
    }
    try:
        esperar()
        resp = requests.get(url, params=params, headers=get_headers(), timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[COPPEL] HTTP {resp.status_code}")
            return []
        data = resp.json()
        return (data.get("resultList", {})
                    .get("contents", [{}])[0]
                    .get("mainContent", [{}])[0]
                    .get("contents", [{}])[0]
                    .get("records", []))
    except Exception as e:
        logger.error(f"[COPPEL] Error: {e}")
        return []

def parsear_item_coppel(item: dict, cat: dict) -> dict | None:
    try:
        attrs         = item.get("attributes", {})
        nombre        = attrs.get("product.displayName", [""])[0][:80]
        precio_actual = float(attrs.get("sku.salePrice", [0])[0] or 0)
        precio_orig   = float(attrs.get("sku.listPrice", [precio_actual])[0] or precio_actual)
        sku           = attrs.get("product.repositoryId", [""])[0]
        thumbnail     = attrs.get("product.smallImage", [""])[0]
        url_prod      = f"https://www.coppel.com/{sku}"

        if not nombre or precio_actual <= 0:
            return None

        descuento = 0.0
        if precio_orig > precio_actual:
            descuento = (precio_orig - precio_actual) / precio_orig

        if descuento < 0.15:
            return None

        return {
            "tienda":          "coppel",
            "nombre":          nombre,
            "precio_actual":   precio_actual,
            "precio_original": precio_orig,
            "descuento":       descuento,
            "sku":             sku,
            "url":             url_prod,
            "thumbnail":       thumbnail,
            "categoria":       {"nombre": cat["query"].capitalize(), "emoji": cat["emoji"]},
        }
    except Exception:
        return None

def ejecutar_ciclo_coppel() -> list:
    logger.info("[COPPEL] Iniciando ciclo...")
    resultados = []
    for cat in BUSQUEDAS_COPPEL[:3]:
        items = buscar_coppel(cat["query"])
        for item in items:
            r = parsear_item_coppel(item, cat)
            if r:
                resultados.append(r)
    logger.info(f"[COPPEL] {len(resultados)} productos encontrados")
    return resultados
