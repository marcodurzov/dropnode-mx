# =============================================================
# DROPNODE MX — scraper_otros.py
# AliExpress, SHEIN, Temu — scraping basico
# Sin afiliado activo — contenido de valor para el canal
# =============================================================

import requests, time, random, logging
logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
]

def get_headers(referer=""):
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json",
        "Accept-Language": "es-MX,es;q=0.9",
        "Referer":         referer,
    }

def esperar(minimo=6, maximo=13):
    time.sleep(random.uniform(minimo, maximo))


# ─────────────────────────────────────────────
#  ALIEXPRESS
# ─────────────────────────────────────────────

BUSQUEDAS_ALIEXPRESS = [
    {"query": "smartphone",    "emoji": "📱"},
    {"query": "laptop",        "emoji": "💻"},
    {"query": "smartwatch",    "emoji": "⌚"},
    {"query": "audifonos",     "emoji": "🎧"},
    {"query": "tablet",        "emoji": "📱"},
]

def buscar_aliexpress(query: str) -> list:
    url = "https://www.aliexpress.com/glosearch/api/product"
    params = {
        "keywords":  query,
        "sortType":  "forsale_price_asc",
        "page":      1,
        "pageSize":  20,
        "countryCode": "MX",
        "currency":  "MXN",
    }
    try:
        esperar()
        resp = requests.get(url, params=params,
                           headers=get_headers("https://www.aliexpress.com/"),
                           timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[ALIEXPRESS] HTTP {resp.status_code}")
            return []
        data  = resp.json()
        items = data.get("result", {}).get("resultList", [])
        return items
    except Exception as e:
        logger.error(f"[ALIEXPRESS] Error: {e}")
        return []

def parsear_aliexpress(item: dict, cat: dict) -> dict | None:
    try:
        info          = item.get("item", {})
        nombre        = info.get("title", "")[:80]
        precio_actual = float(info.get("salePrice", {}).get("value", 0) or 0)
        precio_orig   = float(info.get("originalPrice", {}).get("value", 0) or precio_actual)
        item_id       = str(info.get("itemId", ""))
        thumbnail     = info.get("imageUrl", "")
        url_prod      = f"https://www.aliexpress.com/item/{item_id}.html"

        if not nombre or precio_actual <= 0:
            return None

        descuento = 0.0
        if precio_orig > precio_actual:
            descuento = (precio_orig - precio_actual) / precio_orig

        if descuento < 0.20:
            return None

        return {
            "tienda":          "aliexpress",
            "nombre":          nombre,
            "precio_actual":   precio_actual,
            "precio_original": precio_orig,
            "descuento":       descuento,
            "sku":             item_id,
            "url":             url_prod,
            "thumbnail":       thumbnail,
            "categoria":       cat,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
#  SHEIN
# ─────────────────────────────────────────────

CATEGORIAS_SHEIN = [
    {"cat_id": "2030",  "nombre": "Mujer",     "emoji": "👗"},
    {"cat_id": "1980",  "nombre": "Hombre",    "emoji": "👔"},
    {"cat_id": "2207",  "nombre": "Accesorios","emoji": "👜"},
]

def buscar_shein(cat_id: str) -> list:
    url = "https://us.shein.com/api/productList/get"
    params = {
        "cat_id":    cat_id,
        "limit":     20,
        "page":      1,
        "sort":      "9",       # Ordenar por descuento
        "currency":  "MXN",
        "country":   "MX",
        "lang":      "es",
    }
    try:
        esperar()
        resp = requests.get(url, params=params,
                           headers=get_headers("https://us.shein.com/"),
                           timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[SHEIN] HTTP {resp.status_code}")
            return []
        data = resp.json()
        return data.get("info", {}).get("products", [])
    except Exception as e:
        logger.error(f"[SHEIN] Error: {e}")
        return []

def parsear_shein(item: dict, cat: dict) -> dict | None:
    try:
        nombre        = item.get("goods_name", "")[:80]
        precio_actual = float(item.get("salePrice", {}).get("amount", 0) or 0)
        precio_orig   = float(item.get("retailPrice", {}).get("amount", 0) or precio_actual)
        goods_id      = str(item.get("goods_id", ""))
        goods_sn      = item.get("goods_sn", "")
        thumbnail     = item.get("goods_img", "")
        url_prod      = f"https://us.shein.com/{goods_sn}-p-{goods_id}.html"

        if not nombre or precio_actual <= 0:
            return None

        descuento = 0.0
        if precio_orig > precio_actual:
            descuento = (precio_orig - precio_actual) / precio_orig

        if descuento < 0.30:
            return None

        return {
            "tienda":          "shein",
            "nombre":          nombre,
            "precio_actual":   precio_actual,
            "precio_original": precio_orig,
            "descuento":       descuento,
            "sku":             goods_id,
            "url":             url_prod,
            "thumbnail":       thumbnail,
            "categoria":       cat,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
#  CICLOS PRINCIPALES
# ─────────────────────────────────────────────

def ejecutar_ciclo_aliexpress() -> list:
    logger.info("[ALIEXPRESS] Iniciando ciclo...")
    resultados = []
    for cat in BUSQUEDAS_ALIEXPRESS[:3]:
        items = buscar_aliexpress(cat["query"])
        for item in items:
            r = parsear_aliexpress(item, {"nombre": cat["query"].capitalize(),
                                          "emoji": cat["emoji"]})
            if r:
                resultados.append(r)
    logger.info(f"[ALIEXPRESS] {len(resultados)} productos encontrados")
    return resultados


def ejecutar_ciclo_shein() -> list:
    logger.info("[SHEIN] Iniciando ciclo...")
    resultados = []
    for cat in CATEGORIAS_SHEIN[:2]:
        items = buscar_shein(cat["cat_id"])
        for item in items:
            r = parsear_shein(item, {"nombre": cat["nombre"], "emoji": cat["emoji"]})
            if r:
                resultados.append(r)
    logger.info(f"[SHEIN] {len(resultados)} productos encontrados")
    return resultados
