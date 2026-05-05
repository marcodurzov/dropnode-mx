# =============================================================
# DROPNODE MX — scraper_liverpool.py
# Liverpool Mexico — API interna publica
# =============================================================

import requests, time, random, logging
logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0 Safari/537.36",
]

CATEGORIAS_LIVERPOOL = [
    {"id": "D0060201",  "nombre": "Celulares",      "emoji": "📱"},
    {"id": "D006020201","nombre": "Laptops",         "emoji": "💻"},
    {"id": "D0060206",  "nombre": "Televisores",     "emoji": "📺"},
    {"id": "D0060207",  "nombre": "Audio",           "emoji": "🎧"},
    {"id": "D0060208",  "nombre": "Videojuegos",     "emoji": "🎮"},
    {"id": "D0030101",  "nombre": "Electrodomesticos","emoji": "🏠"},
]

def get_headers():
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json",
        "Accept-Language": "es-MX,es;q=0.9",
        "Origin":          "https://www.liverpool.com.mx",
        "Referer":         "https://www.liverpool.com.mx/",
    }

def esperar():
    time.sleep(random.uniform(5, 11))

def buscar_liverpool(categoria_id: str, pagina: int = 1) -> list:
    url = "https://shoppingapi.liverpool.com.mx/search/category"
    params = {
        "categoryId":    categoria_id,
        "currentPage":   pagina,
        "pageSize":      24,
        "sortBy":        "discount-desc",  # Ordenar por mayor descuento
        "country":       "MX",
    }
    try:
        esperar()
        resp = requests.get(url, params=params, headers=get_headers(), timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[LIVERPOOL] HTTP {resp.status_code}")
            return []
        data  = resp.json()
        prods = data.get("products", []) or data.get("results", [])
        return prods
    except Exception as e:
        logger.error(f"[LIVERPOOL] Error: {e}")
        return []

def parsear_item_liverpool(item: dict, categoria: dict) -> dict | None:
    try:
        nombre        = item.get("name", item.get("title", ""))[:80]
        precio_actual = float(item.get("price", {}).get("value", 0) or
                              item.get("currentPrice", 0) or 0)
        precio_orig   = float(item.get("price", {}).get("originalValue", 0) or
                              item.get("originalPrice", 0) or precio_actual)
        sku           = str(item.get("code", item.get("id", "")))
        thumbnail     = item.get("images", [{}])[0].get("url", "") if item.get("images") else ""
        url_prod      = f"https://www.liverpool.com.mx/tienda/pdp/{sku}"

        if not nombre or precio_actual <= 0:
            return None

        descuento = 0.0
        if precio_orig > precio_actual:
            descuento = (precio_orig - precio_actual) / precio_orig

        if descuento < 0.15:
            return None

        return {
            "tienda":          "liverpool",
            "nombre":          nombre,
            "precio_actual":   precio_actual,
            "precio_original": precio_orig,
            "descuento":       descuento,
            "sku":             sku,
            "url":             url_prod,
            "thumbnail":       thumbnail,
            "categoria":       categoria,
        }
    except Exception:
        return None

def ejecutar_ciclo_liverpool() -> list:
    logger.info("[LIVERPOOL] Iniciando ciclo...")
    resultados = []
    for cat in CATEGORIAS_LIVERPOOL[:3]:
        items = buscar_liverpool(cat["id"])
        for item in items:
            r = parsear_item_liverpool(item, cat)
            if r:
                resultados.append(r)
    logger.info(f"[LIVERPOOL] {len(resultados)} productos encontrados")
    return resultados
