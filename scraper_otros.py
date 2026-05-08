# =============================================================
# DROPNODE MX — scraper_otros.py v2.0
# AliExpress, SHEIN + Marcas electrónicas por ML API
# Samsung, Sony, LG, Lenovo, Dell, HP, Asus, Xiaomi, Ghia
# Estrategia: buscar productos de marca en ML con descuento real
# Sin Playwright — solo requests (compatible con Railway)
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
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json",
        "Accept-Language": "es-MX,es;q=0.9",
        "Referer": referer,
    }


def esperar(minimo=4, maximo=9):
    time.sleep(random.uniform(minimo, maximo))


# ─────────────────────────────────────────────
# ALIEXPRESS
# ─────────────────────────────────────────────

BUSQUEDAS_ALIEXPRESS = [
    {"query": "smartphone", "emoji": "📱"},
    {"query": "laptop",     "emoji": "💻"},
    {"query": "smartwatch", "emoji": "⌚"},
    {"query": "audifonos",  "emoji": "🎧"},
    {"query": "tablet",     "emoji": "📱"},
]


def buscar_aliexpress(query: str) -> list:
    url = "https://www.aliexpress.com/glosearch/api/product"
    params = {
        "keywords": query, "sortType": "forsale_price_asc",
        "page": 1, "pageSize": 20,
        "countryCode": "MX", "currency": "MXN",
    }
    try:
        esperar()
        resp = requests.get(url, params=params,
                            headers=get_headers("https://www.aliexpress.com/"),
                            timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("result", {}).get("resultList", [])
    except Exception as e:
        logger.error(f"[ALIEXPRESS] {e}")
        return []


def parsear_aliexpress(item: dict, cat: dict) -> dict | None:
    try:
        info = item.get("item", {})
        nombre = info.get("title", "")[:80]
        precio_actual = float(info.get("salePrice", {}).get("value", 0) or 0)
        precio_orig = float(info.get("originalPrice", {}).get("value", 0) or precio_actual)
        item_id = str(info.get("itemId", ""))
        thumbnail = info.get("imageUrl", "")
        url_prod = f"https://www.aliexpress.com/item/{item_id}.html"
        if not nombre or precio_actual <= 0:
            return None
        descuento = 0.0
        if precio_orig > precio_actual:
            descuento = (precio_orig - precio_actual) / precio_orig
        if descuento < 0.20:
            return None
        return {
            "tienda": "aliexpress", "nombre": nombre,
            "precio_actual": precio_actual, "precio_original": precio_orig,
            "descuento": descuento, "sku": item_id, "url": url_prod,
            "thumbnail": thumbnail, "categoria": cat,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
# SHEIN
# ─────────────────────────────────────────────

CATEGORIAS_SHEIN = [
    {"cat_id": "2030", "nombre": "Mujer",      "emoji": "👗"},
    {"cat_id": "1980", "nombre": "Hombre",     "emoji": "👔"},
    {"cat_id": "2207", "nombre": "Accesorios", "emoji": "👜"},
]


def buscar_shein(cat_id: str) -> list:
    url = "https://us.shein.com/api/productList/get"
    params = {
        "cat_id": cat_id, "limit": 20, "page": 1,
        "sort": "9", "currency": "MXN", "country": "MX", "lang": "es",
    }
    try:
        esperar()
        resp = requests.get(url, params=params,
                            headers=get_headers("https://us.shein.com/"),
                            timeout=15)
        if resp.status_code != 200:
            return []
        return resp.json().get("info", {}).get("products", [])
    except Exception as e:
        logger.error(f"[SHEIN] {e}")
        return []


def parsear_shein(item: dict, cat: dict) -> dict | None:
    try:
        nombre = item.get("goods_name", "")[:80]
        precio_actual = float(item.get("salePrice", {}).get("amount", 0) or 0)
        precio_orig = float(item.get("retailPrice", {}).get("amount", 0) or precio_actual)
        goods_id = str(item.get("goods_id", ""))
        goods_sn = item.get("goods_sn", "")
        thumbnail = item.get("goods_img", "")
        url_prod = f"https://us.shein.com/{goods_sn}-p-{goods_id}.html"
        if not nombre or precio_actual <= 0:
            return None
        descuento = 0.0
        if precio_orig > precio_actual:
            descuento = (precio_orig - precio_actual) / precio_orig
        if descuento < 0.30:
            return None
        return {
            "tienda": "shein", "nombre": nombre,
            "precio_actual": precio_actual, "precio_original": precio_orig,
            "descuento": descuento, "sku": goods_id, "url": url_prod,
            "thumbnail": thumbnail, "categoria": cat,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
# MARCAS ELECTRÓNICAS VÍA ML API
# Busca productos de marca específica en ML con descuento real.
# Ventajas: sin JS, sin Playwright, links de afiliado ya disponibles,
# historial de precios ya rastreado por el sistema.
# ─────────────────────────────────────────────

ML_SEARCH_API = "https://api.mercadolibre.com/sites/MLM/search"

# Marcas con sus queries optimizadas para encontrar ofertas reales
# seller_id = ID de la tienda oficial en ML (cuando aplique)
MARCAS_ELECTRONICAS = [
    {
        "marca": "Samsung",
        "queries": ["Samsung Galaxy", "Samsung televisor", "Samsung laptop"],
        "emoji": "📱",
        "categoria": "Electrónica",
        "descuento_min": 0.20,   # Samsung raramente hace >40%, 20% ya es bueno
    },
    {
        "marca": "Sony",
        "queries": ["Sony PlayStation", "Sony televisor 4K", "Sony audifonos WH"],
        "emoji": "🎮",
        "categoria": "Electrónica",
        "descuento_min": 0.20,
    },
    {
        "marca": "LG",
        "queries": ["LG televisor OLED", "LG monitor", "LG laptop gram"],
        "emoji": "📺",
        "categoria": "Electrónica",
        "descuento_min": 0.20,
    },
    {
        "marca": "Lenovo",
        "queries": ["Lenovo laptop IdeaPad", "Lenovo ThinkPad outlet", "Lenovo tablet"],
        "emoji": "💻",
        "categoria": "Laptops",
        "descuento_min": 0.25,
    },
    {
        "marca": "Dell",
        "queries": ["Dell laptop inspiron", "Dell monitor", "Dell outlet reacondicionado"],
        "emoji": "💻",
        "categoria": "Laptops",
        "descuento_min": 0.25,
    },
    {
        "marca": "HP",
        "queries": ["HP laptop pavilion", "HP impresora", "HP monitor"],
        "emoji": "💻",
        "categoria": "Laptops",
        "descuento_min": 0.25,
    },
    {
        "marca": "Asus",
        "queries": ["Asus laptop vivobook", "Asus monitor gaming", "Asus router"],
        "emoji": "💻",
        "categoria": "Laptops",
        "descuento_min": 0.25,
    },
    {
        "marca": "Xiaomi",
        "queries": ["Xiaomi celular", "Xiaomi redmi", "Xiaomi smart tv"],
        "emoji": "📱",
        "categoria": "Celulares",
        "descuento_min": 0.20,
    },
    {
        "marca": "Ghia",
        "queries": ["Ghia laptop", "Ghia tablet", "Ghia computadora"],
        "emoji": "💻",
        "categoria": "Laptops",
        "descuento_min": 0.25,
    },
    {
        "marca": "Hisense",
        "queries": ["Hisense televisor", "Hisense refrigerador"],
        "emoji": "📺",
        "categoria": "Electrónica",
        "descuento_min": 0.25,
    },
    {
        "marca": "TCL",
        "queries": ["TCL televisor", "TCL smart tv"],
        "emoji": "📺",
        "categoria": "Electrónica",
        "descuento_min": 0.25,
    },
]


def buscar_marca_en_ml(query: str, descuento_min: float = 0.20) -> list:
    """
    Busca en ML productos de una marca con descuento real.
    Usa la API pública de ML — sin auth, sin rate limit agresivo.
    Filtra por precio_original vs precio_actual para confirmar descuento real.
    """
    try:
        esperar(3, 7)
        resp = requests.get(ML_SEARCH_API, params={
            "q": query,
            "condition": "new",
            "sort": "relevance",
            "limit": 20,
            "site_id": "MLM",
        }, headers=get_headers("https://www.mercadolibre.com.mx/"),
           timeout=15)

        if resp.status_code != 200:
            logger.warning(f"[ML MARCA] HTTP {resp.status_code} para '{query}'")
            return []

        items = resp.json().get("results", [])
        resultados = []

        for item in items:
            try:
                precio = float(item.get("price", 0))
                precio_orig = float(item.get("original_price") or 0)
                nombre = item.get("title", "")[:80]
                link = item.get("permalink", "")
                thumbnail = item.get("thumbnail", "")
                item_id = str(item.get("id", ""))
                stock = item.get("available_quantity", 10) or 10

                if not nombre or precio <= 0 or not link:
                    continue

                # Solo incluir si hay precio_original real (descuento confirmado por ML)
                if precio_orig <= precio:
                    continue

                descuento = (precio_orig - precio) / precio_orig
                if descuento < descuento_min:
                    continue

                # Excluir reacondicionados genéricos (ya los captura github_scraper_ml)
                nombre_lower = nombre.lower()
                if any(x in nombre_lower for x in ["reacondicionado generico", "sin caja"]):
                    continue

                resultados.append({
                    "nombre": nombre,
                    "precio_actual": precio,
                    "precio_original": precio_orig,
                    "descuento": descuento,
                    "sku": item_id,
                    "url": link,
                    "thumbnail": thumbnail.replace("I.jpg", "O.jpg"),  # imagen más grande
                    "stock": stock,
                })

            except Exception:
                continue

        return resultados

    except Exception as e:
        logger.error(f"[ML MARCA] Error '{query}': {e}")
        return []


def ejecutar_ciclo_marcas(marcas_indices: list = None) -> list:
    """
    Ejecuta el ciclo de scrapers de marcas.
    marcas_indices: lista de índices a ejecutar (para rotación).
                    Si None, elige 2 marcas al azar.
    Retorna lista de items en el mismo formato que scraper_otros.
    """
    logger.info("[MARCAS] Iniciando ciclo...")
    resultados = []

    # Por defecto, rotar 2 marcas por ciclo para no saturar la API de ML
    if marcas_indices is None:
        marcas_indices = random.sample(range(len(MARCAS_ELECTRONICAS)), min(2, len(MARCAS_ELECTRONICAS)))

    for idx in marcas_indices:
        marca_cfg = MARCAS_ELECTRONICAS[idx]
        marca = marca_cfg["marca"]
        emoji = marca_cfg["emoji"]
        categoria = marca_cfg["categoria"]
        descuento_min = marca_cfg["descuento_min"]

        # Rotar queries — 1 por ciclo para no golpear demasiado la API
        query = random.choice(marca_cfg["queries"])

        logger.info(f"[MARCAS] Buscando: {query}")
        items = buscar_marca_en_ml(query, descuento_min)

        for item in items[:3]:  # max 3 por marca
            resultados.append({
                "tienda": marca.lower(),
                "nombre": item["nombre"],
                "precio_actual": item["precio_actual"],
                "precio_original": item["precio_original"],
                "descuento": item["descuento"],
                "sku": item["sku"],
                "url": item["url"],
                "thumbnail": item.get("thumbnail", ""),
                "categoria": {"nombre": categoria, "emoji": emoji},
            })

    logger.info(f"[MARCAS] {len(resultados)} productos encontrados")
    return resultados


# ─────────────────────────────────────────────
# TIKTOK SHOP
# Por ahora: busca en ML los productos trending de TikTok Shop
# (búsqueda por keywords que se viralizan en TikTok MX)
# La integración directa con TikTok Shop requiere Playwright
# y está planeada para GitHub Actions en la siguiente versión.
# ─────────────────────────────────────────────

KEYWORDS_TIKTOK_TRENDING = [
    "mini proyector portatil",
    "cargador magnetico magsafe",
    "luz led gaming rgb",
    "audifonos inalambricos bluetooth",
    "reloj inteligente deportivo",
    "camara seguridad wifi",
    "bocina portatil bluetooth",
    "base carga inalambrica",
]


def ejecutar_ciclo_tiktok_trending() -> list:
    """
    Busca en ML los productos que están trending en TikTok Shop MX.
    Captura el efecto TikTok en ML sin necesitar scraper de TikTok directamente.
    """
    logger.info("[TIKTOK TREND] Iniciando ciclo...")
    resultados = []

    keywords = random.sample(KEYWORDS_TIKTOK_TRENDING, 2)
    for kw in keywords:
        items = buscar_marca_en_ml(kw, descuento_min=0.15)
        for item in items[:2]:
            resultados.append({
                "tienda": "tiktok_trend",
                "nombre": item["nombre"],
                "precio_actual": item["precio_actual"],
                "precio_original": item["precio_original"],
                "descuento": item["descuento"],
                "sku": item["sku"],
                "url": item["url"],
                "thumbnail": item.get("thumbnail", ""),
                "categoria": {"nombre": "Trending TikTok", "emoji": "🎵"},
            })

    logger.info(f"[TIKTOK TREND] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# CICLOS PRINCIPALES (existentes)
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