# =============================================================
# DROPNODE MX — scraper_walmart.py
# Scraper de Walmart Mexico usando su API publica
# Sin afiliado por ahora — genera contenido de valor
# =============================================================

import requests
import time
import random
import logging

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
]

CATEGORIAS_WALMART = [
    {"query": "celulares smartphones",  "emoji": "📱"},
    {"query": "laptops computadoras",   "emoji": "💻"},
    {"query": "televisores smart tv",   "emoji": "📺"},
    {"query": "videojuegos consolas",   "emoji": "🎮"},
    {"query": "electrodomesticos",      "emoji": "🏠"},
    {"query": "audifonos bocinas",      "emoji": "🎧"},
]

def get_headers():
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json",
        "Accept-Language": "es-MX,es;q=0.9",
        "Referer":         "https://www.walmart.com.mx/",
    }

def esperar():
    time.sleep(random.uniform(5, 12))

def buscar_walmart(query: str, limit: int = 20) -> list:
    """
    Busca productos en Walmart MX con descuento.
    Usa el endpoint de busqueda publica de Walmart.
    """
    url = "https://www.walmart.com.mx/api/2/page"
    params = {
        "pathName": f"/search",
        "query":    query,
        "page":     1,
        "ps":       limit,
    }

    try:
        esperar()
        resp = requests.get(url, params=params,
                           headers=get_headers(), timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[WALMART] HTTP {resp.status_code} para '{query}'")
            return []

        data = resp.json()
        items_raw = (data.get("data", {})
                        .get("content", {})
                        .get("gsp", {})
                        .get("results", []))
        return items_raw

    except Exception as e:
        logger.error(f"[WALMART] Error en '{query}': {e}")
        return []


def parsear_item_walmart(item: dict) -> dict | None:
    """Extrae los datos relevantes de un item de Walmart."""
    try:
        product = item.get("product", {})
        offers  = item.get("offers", [{}])
        offer   = offers[0] if offers else {}

        nombre        = product.get("productName", "")
        precio_actual = float(offer.get("currentPrice", 0))
        precio_orig   = float(offer.get("wasPrice", 0) or precio_actual)
        sku           = product.get("productId", "")
        imagen        = product.get("imageUrl", "")
        url_producto  = f"https://www.walmart.com.mx/ip/{sku}"

        if not nombre or precio_actual <= 0:
            return None

        descuento = 0.0
        if precio_orig > precio_actual:
            descuento = (precio_orig - precio_actual) / precio_orig

        return {
            "tienda":         "walmart",
            "nombre":         nombre[:80],
            "precio_actual":  precio_actual,
            "precio_original":precio_orig,
            "descuento":      descuento,
            "sku":            sku,
            "url":            url_producto,
            "thumbnail":      imagen,
        }

    except Exception:
        return None


def ejecutar_ciclo_walmart() -> list:
    """
    Ejecuta scraping de Walmart para todas las categorias.
    Retorna lista de productos con descuento >= 15%.
    """
    logger.info("[WALMART] Iniciando ciclo...")
    resultados = []

    for cat in CATEGORIAS_WALMART:
        items_raw = buscar_walmart(cat["query"])
        for item_raw in items_raw:
            item = parsear_item_walmart(item_raw)
            if item and item["descuento"] >= 0.15:
                item["categoria"] = {"nombre": cat["query"].split()[0].capitalize(),
                                     "emoji":  cat["emoji"]}
                resultados.append(item)

    logger.info(f"[WALMART] {len(resultados)} productos con descuento encontrados")
    return resultados
