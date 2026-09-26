# =============================================================
# DROPNODE MX — scraper_api.py
# Scrapers basados en APIs JSON — sin JS, sin Playwright
# VTEX (Palacio de Hierro · Petco · Sears)
# ML API (Oferta del Día · Oferta Imperdible · Más vendidos)
# Sam's Club JSON
# =============================================================

import requests
import time
import random
import logging
import re

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]


def _h(referer=""):
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json, text/plain, */*",
        "Accept-Language": "es-MX,es;q=0.9",
        "Referer":         referer or "https://www.google.com.mx/",
    }


def _esperar():
    time.sleep(random.uniform(4, 8))


def _precio(valor) -> float:
    if not valor:
        return 0.0
    try:
        return float(str(valor).replace(",", "").strip())
    except Exception:
        return 0.0


def _item(tienda, nombre, precio, precio_o, sku, url, thumb, cat_n, cat_e,
          envio=False, es_flash=False):
    if precio <= 0 or not nombre or not url:
        return None
    desc = 0.0
    if precio_o > precio:
        desc = (precio_o - precio) / precio_o
    if desc < 0.12:
        return None
    return {
        "tienda":         tienda,
        "nombre":         nombre[:80],
        "precio_actual":  precio,
        "precio_original": precio_o,
        "descuento":      desc,
        "sku":            str(sku),
        "url":            url,
        "thumbnail":      thumb or "",
        "categoria":      {"nombre": cat_n, "emoji": cat_e},
        "envio_gratis":   envio,
        "es_flash":       es_flash,
    }


# ─────────────────────────────────────────────
# VTEX — API universal para tiendas que usan VTEX
# Palacio de Hierro, Petco, Sears usan este framework
# La API pública retorna JSON sin necesidad de JS
# ─────────────────────────────────────────────

def _vtex_search(base_url: str, fq: str = "", order: str = "OrderByBestDiscountDESC",
                 limit: int = 24) -> list:
    """
    Llama al endpoint de búsqueda VTEX estándar.
    Retorna lista de productos en JSON o [] si falla.
    """
    url = f"{base_url.rstrip('/')}/api/catalog_system/pub/products/search"
    params = {
        "O":     order,
        "_from": 0,
        "_to":   limit - 1,
    }
    if fq:
        params["fq"] = fq

    try:
        _esperar()
        resp = requests.get(url, params=params, headers=_h(base_url), timeout=20)
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"[VTEX] {base_url} → HTTP {resp.status_code}")
        return []
    except Exception as e:
        logger.error(f"[VTEX] {base_url}: {e}")
        return []


def _vtex_parsear(prods: list, tienda: str, cat_n: str, cat_e: str,
                  base_url: str) -> list:
    resultados = []
    for prod in prods:
        try:
            nombre = prod.get("productName", "")
            link   = prod.get("link", "")
            if not link.startswith("http"):
                link = base_url.rstrip("/") + link

            # Imágenes
            imgs   = prod.get("items", [{}])[0].get("images", [{}])
            thumb  = imgs[0].get("imageUrl", "") if imgs else ""

            # Precios desde sellers
            sellers = (prod.get("items", [{}])[0]
                       .get("sellers", [{}]))
            offer   = (sellers[0].get("commertialOffer", {}) if sellers else {})
            precio  = _precio(offer.get("Price", 0))
            precio_o = _precio(offer.get("ListPrice", 0))
            stock   = int(offer.get("AvailableQuantity", 0))
            sku     = prod.get("productId", nombre[:15])

            if stock <= 0:
                continue

            item = _item(tienda, nombre, precio, precio_o, sku,
                         link, thumb, cat_n, cat_e)
            if item:
                resultados.append(item)
        except Exception:
            continue
    return resultados


def scrape_palacio_vtex() -> list:
    """Palacio de Hierro — VTEX API. Outlet + Sale + Ofertas."""
    logger.info("[PALACIO] VTEX API...")
    resultados = []
    base = "https://www.palaciodehierro.com.mx"

    # Outlet y sale sections via VTEX facets
    queries = [
        ("specificationFilter_26:Outlet", "Outlet",  "💎"),
        ("specificationFilter_26:Sale",   "Sale",    "💎"),
        ("",                              "Ofertas", "💎"),
    ]

    for fq, cat_n, cat_e in queries[:2]:
        prods = _vtex_search(base, fq=fq, limit=20)
        resultados.extend(_vtex_parsear(prods, "palacio", cat_n, cat_e, base))

    logger.info(f"[PALACIO] {len(resultados)} productos")
    return resultados


def scrape_petco_vtex() -> list:
    """Petco MX — VTEX API."""
    logger.info("[PETCO] VTEX API...")
    base  = "https://www.petco.com.mx"
    prods = _vtex_search(base, limit=24)
    res   = _vtex_parsear(prods, "petco", "Mascotas", "🐾", base)
    logger.info(f"[PETCO] {len(res)} productos")
    return res


def scrape_sears_vtex() -> list:
    """Sears MX — intenta VTEX API, fallback a búsqueda directa."""
    logger.info("[SEARS] API...")
    resultados = []
    base = "https://www.sears.com.mx"

    # Sears puede usar VTEX o su propio sistema
    prods = _vtex_search(base, limit=24)
    if prods:
        resultados = _vtex_parsear(prods, "sears", "Hogar", "🏬", base)
    else:
        # Fallback: JSON de OpenCart que usa Sears
        try:
            _esperar()
            resp = requests.get(
                f"{base}/index.php?route=product/special&sort=pd.price&order=ASC",
                headers={**_h(base), "Accept": "text/html,application/xhtml+xml"},
                timeout=20
            )
            # Sin JS: poco probable que retorne datos útiles
            # Se deja como placeholder para futura mejora
        except Exception:
            pass

    logger.info(f"[SEARS] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# MERCADO LIBRE — API pública de deals
# Oferta del Día, Oferta Imperdible, Más vendidos en oferta
# Sin auth, sin límite para uso básico
# ─────────────────────────────────────────────

ML_API = "https://api.mercadolibre.com"

# Categorías principales de ML México con sus IDs
ML_CATEGORIAS = [
    ("MLM1055", "Electrónica",    "🔌"),
    ("MLM1648", "Computación",    "💻"),
    ("MLM1051", "Celulares",      "📱"),
    ("MLM1000", "Electrónica",    "🔌"),
    ("MLM1276", "Juguetes",       "🧸"),
    ("MLM1246", "Bebés",          "👶"),
    ("MLM1500", "Mascotas",       "🐾"),
    ("MLM1430", "Deportes",       "⚽"),
    ("MLM1574", "Hogar",          "🏠"),
    ("MLM1182", "Moda",           "👗"),
]


def _ml_parsear(items: list, tienda: str = "mercadolibre",
                cat_n: str = "ML", cat_e: str = "🛒",
                es_flash: bool = False) -> list:
    resultados = []
    for item in items:
        try:
            nombre   = item.get("title", "")
            precio   = _precio(item.get("price", 0))
            precio_o = _precio(item.get("original_price") or 0)
            link     = item.get("permalink", "")
            thumb    = item.get("thumbnail", "").replace("I.jpg", "O.jpg")
            sku      = str(item.get("id", ""))
            envio    = bool(item.get("shipping", {}).get("free_shipping", False))

            # Inferir categoría si está disponible
            cat_id = item.get("category_id", "")
            for c_id, c_n, c_e in ML_CATEGORIAS:
                if c_id == cat_id:
                    cat_n, cat_e = c_n, c_e
                    break

            prod = _item(tienda, nombre, precio, precio_o, sku,
                         link, thumb, cat_n, cat_e, envio, es_flash)
            if prod:
                resultados.append(prod)
        except Exception:
            continue
    return resultados


def scrape_ml_oferta_del_dia() -> list:
    """
    ML Oferta del Día — badge oficial de ML.
    Usa la API pública de deals de ML sin autenticación.
    Son los productos con el mayor descuento verificado por ML.
    Ideales para publicar como 'Deal del Día' en community.
    """
    logger.info("[ML DEAL DÍA] API...")
    resultados = []

    # Endpoint de ML para deals con mayor descuento
    endpoints = [
        # Búsqueda ordenada por mayor descuento, nuevos
        {
            "url":    f"{ML_API}/sites/MLM/search",
            "params": {
                "sort":       "best_discount",
                "condition":  "new",
                "limit":      50,
                "offset":     0,
            }
        },
        # Deals con deals activos
        {
            "url":    f"{ML_API}/sites/MLM/search",
            "params": {
                "sort":         "best_discount",
                "condition":    "new",
                "has_pictures": "Y",
                "limit":        30,
                "offset":       0,
                "shipping_cost": "free",  # Con envío gratis
            }
        },
    ]

    seen = set()
    for ep in endpoints:
        try:
            _esperar()
            resp = requests.get(ep["url"], params=ep["params"],
                                headers=_h("https://www.mercadolibre.com.mx/"),
                                timeout=15)
            if resp.status_code != 200:
                continue

            items = resp.json().get("results", [])
            for item in items:
                sku = str(item.get("id", ""))
                if sku in seen:
                    continue
                seen.add(sku)

                # Solo incluir si tiene badge de deal oficial en ML
                # o descuento real de 20%+
                precio   = _precio(item.get("price", 0))
                precio_o = _precio(item.get("original_price") or 0)
                if precio_o > 0:
                    desc = (precio_o - precio) / precio_o
                    if desc >= 0.20:
                        # Marcar como flash si tiene deal badge
                        atribs = item.get("attributes", [])
                        deal_badge = any(
                            a.get("id") in ("DEAL_TYPE", "DEAL_ID")
                            for a in atribs
                        )
                        prod = _item(
                            "mercadolibre", item.get("title", ""),
                            precio, precio_o, sku,
                            item.get("permalink", ""),
                            item.get("thumbnail", "").replace("I.jpg", "O.jpg"),
                            "Oferta del Día", "⚡",
                            bool(item.get("shipping", {}).get("free_shipping")),
                            es_flash=deal_badge,
                        )
                        if prod:
                            resultados.append(prod)

        except Exception as e:
            logger.error(f"[ML DEAL DÍA] {e}")

    # Ordenar por mayor descuento
    resultados.sort(key=lambda x: x["descuento"], reverse=True)
    logger.info(f"[ML DEAL DÍA] {len(resultados)} productos")
    return resultados[:20]  # Top 20 para no saturar


def scrape_ml_por_categoria(cat_id: str, cat_n: str, cat_e: str,
                             limit: int = 20) -> list:
    """
    ML búsqueda por categoría ordenada por mejor descuento.
    Complementa el scraper Playwright del canal ML.
    """
    try:
        _esperar()
        resp = requests.get(
            f"{ML_API}/sites/MLM/search",
            params={
                "category": cat_id,
                "sort":     "best_discount",
                "condition": "new",
                "limit":    limit,
            },
            headers=_h("https://www.mercadolibre.com.mx/"),
            timeout=15
        )
        if resp.status_code != 200:
            return []
        items = resp.json().get("results", [])
        return _ml_parsear(items, "mercadolibre", cat_n, cat_e)
    except Exception as e:
        logger.error(f"[ML CAT {cat_id}] {e}")
        return []


def scrape_ml_mas_vendidos_oferta() -> list:
    """
    Los más vendidos de ML que además tienen descuento.
    Combinación de volumen de ventas + precio reducido = oportunidad.
    """
    logger.info("[ML VENDIDOS] Iniciando...")
    resultados = []
    seen = set()

    # Rotar entre 3 categorías por run
    cats = random.sample(ML_CATEGORIAS[:6], 3)

    for cat_id, cat_n, cat_e in cats:
        try:
            _esperar()
            resp = requests.get(
                f"{ML_API}/sites/MLM/search",
                params={
                    "category": cat_id,
                    "sort":     "best_seller",
                    "condition": "new",
                    "limit":    20,
                },
                headers=_h("https://www.mercadolibre.com.mx/"),
                timeout=15
            )
            if resp.status_code != 200:
                continue

            items = resp.json().get("results", [])
            for item in items:
                sku = str(item.get("id", ""))
                if sku in seen:
                    continue
                seen.add(sku)
                precio   = _precio(item.get("price", 0))
                precio_o = _precio(item.get("original_price") or 0)
                # Solo los que tienen descuento real
                if precio_o > precio:
                    prod = _item(
                        "mercadolibre", item.get("title", ""),
                        precio, precio_o, sku,
                        item.get("permalink", ""),
                        item.get("thumbnail", "").replace("I.jpg", "O.jpg"),
                        cat_n, cat_e,
                        bool(item.get("shipping", {}).get("free_shipping")),
                    )
                    if prod:
                        resultados.append(prod)

        except Exception as e:
            logger.error(f"[ML VENDIDOS {cat_id}] {e}")

    resultados.sort(key=lambda x: x["descuento"], reverse=True)
    logger.info(f"[ML VENDIDOS] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# SAM'S CLUB — API JSON
# ─────────────────────────────────────────────

def scrape_sams_api() -> list:
    """
    Sam's Club MX — endpoint JSON de productos en oferta.
    Sam's expone su catálogo vía una API REST básica.
    """
    logger.info("[SAMS] API JSON...")
    resultados = []

    endpoints = [
        "https://www.samsclub.com.mx/sams/products/searchProducts.jsp"
        "?rootCategory=rootCategory&site=SMXS&searchTerm=*"
        "&sortKey=discountPercentage&sortOrder=desc&start=0&numItems=24"
        "&showOutOfStock=false&type=filter",
    ]

    for url in endpoints:
        try:
            _esperar()
            resp = requests.get(url, headers=_h("https://www.samsclub.com.mx/"),
                                timeout=20)
            if resp.status_code != 200:
                continue

            data  = resp.json()
            prods = (data.get("payload", {}).get("records", []) or
                     data.get("products", []) or
                     data.get("results", []))

            for prod in prods[:20]:
                try:
                    nombre   = (prod.get("displayName") or prod.get("name", ""))
                    precio   = _precio(prod.get("listPrice") or prod.get("price", 0))
                    precio_o = _precio(prod.get("wasPrice") or prod.get("originalPrice", 0))
                    link     = prod.get("productUrl") or prod.get("url", "")
                    if link and not link.startswith("http"):
                        link = "https://www.samsclub.com.mx" + link
                    thumb = (prod.get("imageUrl") or
                             prod.get("primaryImage", {}).get("url", ""))
                    sku   = str(prod.get("productId") or prod.get("id", ""))

                    item = _item("sams", nombre, precio, precio_o, sku,
                                 link, thumb, "Sam's Club", "🏬", envio=True)
                    if item:
                        resultados.append(item)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"[SAMS API] {e}")

    logger.info(f"[SAMS] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# CICLOS EXPORTADOS
# ─────────────────────────────────────────────

def ejecutar_ciclo_palacio_api() -> list:
    return scrape_palacio_vtex()


def ejecutar_ciclo_petco_api() -> list:
    return scrape_petco_vtex()


def ejecutar_ciclo_sears_api() -> list:
    return scrape_sears_vtex()


def ejecutar_ciclo_sams_api() -> list:
    return scrape_sams_api()


def ejecutar_ciclo_ml_deals() -> list:
    """ML Oferta del Día + Más vendidos con descuento."""
    deals    = scrape_ml_oferta_del_dia()
    vendidos = scrape_ml_mas_vendidos_oferta()
    # Combinar y deduplicar
    seen = set()
    res  = []
    for item in deals + vendidos:
        if item["sku"] not in seen:
            seen.add(item["sku"])
            res.append(item)
    res.sort(key=lambda x: x["descuento"], reverse=True)
    return res


def get_deal_del_dia() -> dict | None:
    """
    Retorna EL mejor deal del día de ML para publicar en community.
    Criterio: mayor descuento real + tiene precio original confirmado.
    """
    deals = scrape_ml_oferta_del_dia()
    if not deals:
        return None
    # El primero ya es el de mayor descuento
    return deals[0]