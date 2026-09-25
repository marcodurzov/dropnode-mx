# =============================================================
# DROPNODE MX — scraper_tiendas.py
# Costco · Sam's Club · Sears · Palacio de Hierro · Petco
# Inditex (Zara · Pull&Bear · Bershka · Lefties)
# Samsung MX · LG MX · Sony MX (outlet directo)
# Sin Playwright — requests + BeautifulSoup
# Compatible con GitHub Actions bot.yml
# =============================================================

import requests
import time
import random
import logging
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]


def _headers(referer=""):
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept-Language": "es-MX,es;q=0.9",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer":         referer or "https://www.google.com.mx/",
        "Cache-Control":   "no-cache",
    }


def _headers_json(referer=""):
    h = _headers(referer)
    h["Accept"] = "application/json, text/plain, */*"
    return h


def _esperar(a=4, b=9):
    time.sleep(random.uniform(a, b))


def _precio(texto: str) -> float:
    if not texto:
        return 0.0
    t = re.sub(r"[^\d.]", "", texto.replace(",", ""))
    try:
        return float(t)
    except Exception:
        return 0.0


def _item(tienda, nombre, precio_actual, precio_orig,
          asin_sku, url, thumbnail, cat_n, cat_e,
          envio_gratis=False):
    if precio_actual <= 0 or not nombre:
        return None
    descuento = 0.0
    if precio_orig > precio_actual:
        descuento = (precio_orig - precio_actual) / precio_orig
    if descuento < 0.12:
        return None
    return {
        "tienda":         tienda,
        "nombre":         nombre[:80],
        "precio_actual":  precio_actual,
        "precio_original": precio_orig,
        "descuento":      descuento,
        "sku":            str(asin_sku),
        "url":            url,
        "thumbnail":      thumbnail,
        "categoria":      {"nombre": cat_n, "emoji": cat_e},
        "envio_gratis":   envio_gratis,
    }


# ─────────────────────────────────────────────
# COSTCO MX
# ─────────────────────────────────────────────

COSTCO_URLS = [
    ("https://www.costco.com.mx/ofertas-especiales", "Ofertas Especiales"),
    ("https://www.costco.com.mx/electronica",        "Electrónica"),
    ("https://www.costco.com.mx/hogar",              "Hogar"),
    ("https://www.costco.com.mx/ropa",               "Ropa"),
    ("https://www.costco.com.mx/bebes-y-ninos",      "Bebés y Niños"),
    ("https://www.costco.com.mx/mascotas",           "Mascotas"),
]

COSTCO_CAT_MAP = {
    "electronica": ("Electrónica",   "🔌"),
    "hogar":       ("Hogar",         "🏠"),
    "ropa":        ("Moda",          "👗"),
    "ninos":       ("Bebés y Niños", "👶"),
    "mascotas":    ("Mascotas",      "🐾"),
    "ofertas":     ("Ofertas",       "🛒"),
}


def _costco_cat(url):
    for k, v in COSTCO_CAT_MAP.items():
        if k in url:
            return v
    return ("General", "🛒")


def scrape_costco() -> list:
    logger.info("[COSTCO] Iniciando...")
    resultados = []
    seen = set()

    for url, seccion in COSTCO_URLS[:3]:  # 3 secciones por ciclo
        try:
            _esperar(5, 10)
            resp = requests.get(url, headers=_headers("https://www.costco.com.mx/"), timeout=20)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            # Productos en cards
            cards = (soup.select(".product-tile") or
                     soup.select("[class*='product-item']") or
                     soup.select("[class*='ProductCard']"))

            for card in cards[:20]:
                try:
                    nombre_el  = (card.select_one("[class*='product-name']")
                                  or card.select_one("h2") or card.select_one("h3"))
                    precio_el  = card.select_one("[class*='sale-price'],[class*='price-sales'],[class*='current-price']")
                    antes_el   = card.select_one("[class*='price-standard'],[class*='price-original'],[class*='was']")
                    link_el    = card.select_one("a[href]")
                    img_el     = card.select_one("img")

                    if not nombre_el or not precio_el:
                        continue

                    nombre    = nombre_el.get_text(strip=True)
                    precio    = _precio(precio_el.get_text())
                    precio_o  = _precio(antes_el.get_text()) if antes_el else 0
                    link      = "https://www.costco.com.mx" + link_el["href"] if link_el and link_el.get("href", "").startswith("/") else (link_el["href"] if link_el else "")
                    thumb     = img_el.get("src", "") if img_el else ""
                    sku       = re.search(r"/(\d{6,})", link or "")
                    sku_val   = sku.group(1) if sku else nombre[:20]

                    if sku_val in seen or not link:
                        continue
                    seen.add(sku_val)

                    cat_n, cat_e = _costco_cat(url)
                    item = _item("costco", nombre, precio, precio_o,
                                 sku_val, link, thumb, cat_n, cat_e, envio_gratis=True)
                    if item:
                        resultados.append(item)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"[COSTCO] {seccion}: {e}")

    logger.info(f"[COSTCO] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# SAM'S CLUB MX
# ─────────────────────────────────────────────

def scrape_sams() -> list:
    logger.info("[SAMS] Iniciando...")
    resultados = []
    seen = set()

    urls = [
        ("https://www.samsclub.com.mx/ofertas", "Ofertas"),
        ("https://www.samsclub.com.mx/electronicos", "Electrónica"),
        ("https://www.samsclub.com.mx/hogar", "Hogar"),
        ("https://www.samsclub.com.mx/ropa-y-accesorios", "Moda"),
        ("https://www.samsclub.com.mx/bebes-y-ninos", "Bebés"),
        ("https://www.samsclub.com.mx/mascotas", "Mascotas"),
    ]

    for url, seccion in urls[:3]:
        try:
            _esperar(5, 10)
            resp = requests.get(url, headers=_headers("https://www.samsclub.com.mx/"), timeout=20)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = (soup.select(".sc-product-card") or
                     soup.select("[class*='ProductCard']") or
                     soup.select("[class*='product-tile']"))

            for card in cards[:20]:
                try:
                    nombre_el = card.select_one("[class*='name'],[class*='title'],h2,h3")
                    precio_el = card.select_one("[class*='sale'],[class*='offer'],[class*='current']")
                    antes_el  = card.select_one("[class*='original'],[class*='was'],[class*='before']")
                    link_el   = card.select_one("a[href]")
                    img_el    = card.select_one("img")

                    if not nombre_el or not precio_el:
                        continue

                    nombre   = nombre_el.get_text(strip=True)
                    precio   = _precio(precio_el.get_text())
                    precio_o = _precio(antes_el.get_text()) if antes_el else 0
                    link     = link_el["href"] if link_el else ""
                    if link and link.startswith("/"):
                        link = "https://www.samsclub.com.mx" + link
                    thumb    = img_el.get("src", "") if img_el else ""
                    sku      = re.search(r"/(\d{6,})", link or "")
                    sku_val  = sku.group(1) if sku else nombre[:20]

                    if sku_val in seen or not link:
                        continue
                    seen.add(sku_val)

                    cat_map = {
                        "electro": ("Electrónica", "🔌"),
                        "hogar":   ("Hogar", "🏠"),
                        "ropa":    ("Moda", "👗"),
                        "beb":     ("Bebés", "👶"),
                        "mascot":  ("Mascotas", "🐾"),
                    }
                    cat_n, cat_e = ("Ofertas", "🛒")
                    for k, v in cat_map.items():
                        if k in url:
                            cat_n, cat_e = v
                            break

                    item = _item("sams", nombre, precio, precio_o,
                                 sku_val, link, thumb, cat_n, cat_e, envio_gratis=True)
                    if item:
                        resultados.append(item)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"[SAMS] {seccion}: {e}")

    logger.info(f"[SAMS] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# PETCO MX
# ─────────────────────────────────────────────

def scrape_petco() -> list:
    logger.info("[PETCO] Iniciando...")
    resultados = []

    urls = [
        "https://www.petco.com.mx/petco/category/offers/",
        "https://www.petco.com.mx/petco/category/descuentos/",
    ]

    for url in urls:
        try:
            _esperar(4, 8)
            resp = requests.get(url, headers=_headers("https://www.petco.com.mx/"), timeout=20)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = (soup.select(".vtex-product-summary") or
                     soup.select("[class*='ProductCard']") or
                     soup.select("[class*='product-summary']"))

            for card in cards[:15]:
                try:
                    nombre_el = card.select_one("[class*='name'],[class*='productBrand'],h3,h2")
                    precio_el = card.select_one("[class*='sellingPrice'],[class*='sale'],[class*='current']")
                    antes_el  = card.select_one("[class*='listPrice'],[class*='original']")
                    link_el   = card.select_one("a[href]")
                    img_el    = card.select_one("img")

                    if not nombre_el or not precio_el:
                        continue

                    nombre   = nombre_el.get_text(strip=True)
                    precio   = _precio(precio_el.get_text())
                    precio_o = _precio(antes_el.get_text()) if antes_el else 0
                    link     = link_el["href"] if link_el else ""
                    if link and link.startswith("/"):
                        link = "https://www.petco.com.mx" + link
                    thumb    = img_el.get("src", "") if img_el else ""

                    item = _item("petco", nombre, precio, precio_o,
                                 nombre[:20], link, thumb, "Mascotas", "🐾")
                    if item:
                        resultados.append(item)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"[PETCO] {e}")

    logger.info(f"[PETCO] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# SEARS MX
# ─────────────────────────────────────────────

def scrape_sears() -> list:
    logger.info("[SEARS] Iniciando...")
    resultados = []

    urls = [
        ("https://www.sears.com.mx/categoria/ofertas-y-liquidaciones/", "Ofertas", "🛒"),
        ("https://www.sears.com.mx/categoria/electronica-y-computo/",   "Electrónica", "🔌"),
        ("https://www.sears.com.mx/categoria/linea-blanca/",            "Hogar", "🏠"),
        ("https://www.sears.com.mx/categoria/juguetes/",                "Juguetes", "🧸"),
    ]

    for url, cat_n, cat_e in urls[:2]:
        try:
            _esperar(5, 10)
            resp = requests.get(url, headers=_headers("https://www.sears.com.mx/"), timeout=20)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            # Sears usa estructura de OpenCart / custom
            cards = (soup.select(".product-layout") or
                     soup.select("[class*='product-thumb']") or
                     soup.select("[class*='product-item']"))

            for card in cards[:15]:
                try:
                    nombre_el = card.select_one("[class*='name'],h4,h3,h2")
                    precio_el = card.select_one("[class*='price-new'],[class*='sale']")
                    antes_el  = card.select_one("[class*='price-old'],[class*='price-tax']")
                    link_el   = card.select_one("a[href]")
                    img_el    = card.select_one("img")

                    if not nombre_el or not precio_el:
                        continue

                    nombre   = nombre_el.get_text(strip=True)
                    precio   = _precio(precio_el.get_text())
                    precio_o = _precio(antes_el.get_text()) if antes_el else 0
                    link     = link_el["href"] if link_el else ""
                    thumb    = img_el.get("src", "") if img_el else ""

                    item = _item("sears", nombre, precio, precio_o,
                                 nombre[:20], link, thumb, cat_n, cat_e)
                    if item:
                        resultados.append(item)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"[SEARS] {cat_n}: {e}")

    logger.info(f"[SEARS] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# PALACIO DE HIERRO
# ─────────────────────────────────────────────

def scrape_palacio() -> list:
    logger.info("[PALACIO] Iniciando...")
    resultados = []

    # Palacio tiene una API de búsqueda VTEX
    urls = [
        ("https://www.palaciodehierro.com.mx/outlet?map=specificationFilter_26", "Outlet", "🏬"),
        ("https://www.palaciodehierro.com.mx/belleza/ofertas",                    "Belleza", "💄"),
        ("https://www.palaciodehierro.com.mx/moda-mujer/ofertas",                 "Moda Mujer", "👗"),
    ]

    for url, cat_n, cat_e in urls[:2]:
        try:
            _esperar(5, 10)
            resp = requests.get(url, headers=_headers("https://www.palaciodehierro.com.mx/"), timeout=20)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = (soup.select(".vtex-product-summary") or
                     soup.select("[class*='ProductSummary']") or
                     soup.select("[class*='product-summary']"))

            for card in cards[:15]:
                try:
                    nombre_el = card.select_one("[class*='name'],[class*='productBrand'],h3")
                    precio_el = card.select_one("[class*='sellingPrice'],[class*='sale']")
                    antes_el  = card.select_one("[class*='listPrice'],[class*='original']")
                    link_el   = card.select_one("a[href]")
                    img_el    = card.select_one("img")

                    if not nombre_el or not precio_el:
                        continue

                    nombre   = nombre_el.get_text(strip=True)
                    precio   = _precio(precio_el.get_text())
                    precio_o = _precio(antes_el.get_text()) if antes_el else 0
                    link     = link_el["href"] if link_el else ""
                    if link and link.startswith("/"):
                        link = "https://www.palaciodehierro.com.mx" + link
                    thumb    = img_el.get("src", "") if img_el else ""

                    item = _item("palacio", nombre, precio, precio_o,
                                 nombre[:20], link, thumb, cat_n, cat_e)
                    if item:
                        resultados.append(item)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"[PALACIO] {cat_n}: {e}")

    logger.info(f"[PALACIO] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# INDITEX (Zara, Pull&Bear, Bershka, Lefties)
# API unificada de Inditex para sección SALE
# ─────────────────────────────────────────────

INDITEX_BRANDS = [
    {
        "nombre":  "zara",
        "emoji":   "👗",
        "sale_url": "https://www.zara.com/mx/es/sale-mxp-1.html",
        "api":     "https://www.zara.com/mx/es/category/1953/products?ajax=true",
    },
    {
        "nombre":  "pullbear",
        "emoji":   "👕",
        "sale_url": "https://www.pullandbear.com/mx/es/sale",
        "api":     None,
    },
    {
        "nombre":  "bershka",
        "emoji":   "👕",
        "sale_url": "https://www.bershka.com/mx/es/sale",
        "api":     None,
    },
    {
        "nombre":  "lefties",
        "emoji":   "👕",
        "sale_url": "https://www.lefties.com/mx/es/sale",
        "api":     None,
    },
]


def _scrape_inditex_brand(brand: dict) -> list:
    resultados = []
    nombre_marca = brand["nombre"]
    emoji_marca  = brand["emoji"]
    url          = brand["sale_url"]

    try:
        _esperar(5, 10)
        resp = requests.get(
            url,
            headers=_headers(f"https://www.{nombre_marca}.com/mx/"),
            timeout=20
        )
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Inditex usa estructura común
        cards = (soup.select("[class*='product-grid-product']") or
                 soup.select("[class*='product-item']") or
                 soup.select("[class*='GridItem']"))

        for card in cards[:15]:
            try:
                nombre_el = (card.select_one("[class*='product-grid-product-info__name']")
                             or card.select_one("[class*='product-name']")
                             or card.select_one("h3,h4"))
                precio_el = (card.select_one("[class*='price--sale'],[class*='price__sale']")
                             or card.select_one("[class*='current-price']"))
                antes_el  = (card.select_one("[class*='price--original'],[class*='price__original']")
                             or card.select_one("[class*='price-old']"))
                link_el   = card.select_one("a[href]")
                img_el    = card.select_one("img")

                if not nombre_el or not precio_el:
                    continue

                nombre   = nombre_el.get_text(strip=True)
                precio   = _precio(precio_el.get_text())
                precio_o = _precio(antes_el.get_text()) if antes_el else 0
                link     = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    domain = f"https://www.{nombre_marca}.com"
                    if nombre_marca == "pullbear":
                        domain = "https://www.pullandbear.com"
                    link = domain + link
                thumb    = img_el.get("src", "") if img_el else ""

                item = _item(nombre_marca, nombre, precio, precio_o,
                             nombre[:20], link, thumb, "Moda", emoji_marca)
                if item:
                    resultados.append(item)
            except Exception:
                continue

    except Exception as e:
        logger.error(f"[INDITEX {nombre_marca}] {e}")

    return resultados


def scrape_inditex() -> list:
    """Scrapa las 4 marcas de Inditex en México — sección SALE."""
    logger.info("[INDITEX] Iniciando (Zara, Pull&Bear, Bershka, Lefties)...")
    resultados = []
    # Alternar marcas por run para no sobrecargar
    marcas = random.sample(INDITEX_BRANDS, 2)
    for brand in marcas:
        items = _scrape_inditex_brand(brand)
        resultados.extend(items)
        logger.info(f"[INDITEX {brand['nombre']}] {len(items)} productos")
    return resultados


# ─────────────────────────────────────────────
# SAMSUNG MX — Outlet directo
# ─────────────────────────────────────────────

def scrape_samsung_outlet() -> list:
    logger.info("[SAMSUNG] Outlet directo...")
    resultados = []

    urls = [
        "https://www.samsung.com/mx/offer/",
        "https://www.samsung.com/mx/smartphones/all-smartphones/?galaxy_s=on&discount=true",
        "https://www.samsung.com/mx/tvs/all-tvs/?discount=true",
    ]

    for url in urls[:2]:
        try:
            _esperar(5, 10)
            resp = requests.get(url, headers=_headers("https://www.samsung.com/mx/"), timeout=20)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = (soup.select("[class*='product-card']") or
                     soup.select("[class*='ProductCard']") or
                     soup.select("[class*='product-item']"))

            for card in cards[:10]:
                try:
                    nombre_el = card.select_one("[class*='product-name'],[class*='model-name'],h3,h4")
                    precio_el = card.select_one("[class*='sale-price'],[class*='price-sale'],[class*='discount-price']")
                    antes_el  = card.select_one("[class*='regular-price'],[class*='price-before']")
                    link_el   = card.select_one("a[href]")
                    img_el    = card.select_one("img")

                    if not nombre_el or not precio_el:
                        continue

                    nombre   = nombre_el.get_text(strip=True)
                    precio   = _precio(precio_el.get_text())
                    precio_o = _precio(antes_el.get_text()) if antes_el else 0
                    link     = link_el["href"] if link_el else ""
                    if link and link.startswith("/"):
                        link = "https://www.samsung.com" + link
                    thumb    = img_el.get("src", "") if img_el else ""

                    # Inferir categoría
                    cat_n = "Smartphones" if "smartphone" in url else "Televisores" if "tv" in url else "Electrónica"
                    cat_e = "📱" if "smartphone" in url else "📺" if "tv" in url else "🔌"

                    item = _item("samsung", nombre, precio, precio_o,
                                 nombre[:20], link, thumb, cat_n, cat_e)
                    if item:
                        resultados.append(item)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"[SAMSUNG] {e}")

    logger.info(f"[SAMSUNG] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# LG MX — Sección de promociones
# ─────────────────────────────────────────────

def scrape_lg() -> list:
    logger.info("[LG] Iniciando...")
    resultados = []

    urls = [
        ("https://www.lg.com/mx/promotions",              "Electrónica", "🔌"),
        ("https://www.lg.com/mx/tvs/all-tvs",             "Televisores", "📺"),
        ("https://www.lg.com/mx/refrigerators/all-fridges","Hogar",       "🏠"),
    ]

    for url, cat_n, cat_e in urls[:2]:
        try:
            _esperar(5, 10)
            resp = requests.get(url, headers=_headers("https://www.lg.com/mx/"), timeout=20)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            cards = (soup.select("[class*='product-list-item']") or
                     soup.select("[class*='MuiCard']") or
                     soup.select("[class*='product-item']"))

            for card in cards[:10]:
                try:
                    nombre_el = card.select_one("[class*='model-title'],[class*='product-title'],h3,h4")
                    precio_el = card.select_one("[class*='price-sale'],[class*='sale-price'],[class*='current']")
                    antes_el  = card.select_one("[class*='price-original'],[class*='before']")
                    link_el   = card.select_one("a[href]")
                    img_el    = card.select_one("img")

                    if not nombre_el or not precio_el:
                        continue

                    nombre   = nombre_el.get_text(strip=True)
                    precio   = _precio(precio_el.get_text())
                    precio_o = _precio(antes_el.get_text()) if antes_el else 0
                    link     = link_el["href"] if link_el else ""
                    if link and link.startswith("/"):
                        link = "https://www.lg.com" + link
                    thumb    = img_el.get("src", "") if img_el else ""

                    item = _item("lg", nombre, precio, precio_o,
                                 nombre[:20], link, thumb, cat_n, cat_e)
                    if item:
                        resultados.append(item)
                except Exception:
                    continue

        except Exception as e:
            logger.error(f"[LG] {cat_n}: {e}")

    logger.info(f"[LG] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# SONY MX — Outlet / Ofertas
# ─────────────────────────────────────────────

def scrape_sony() -> list:
    logger.info("[SONY] Iniciando...")
    resultados = []

    try:
        _esperar(5, 10)
        url  = "https://www.sony.com.mx/es/store/catalog/category/view/id/39"
        resp = requests.get(url, headers=_headers("https://www.sony.com.mx/"), timeout=20)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = (soup.select(".product-item") or
                 soup.select("[class*='product-tile']") or
                 soup.select("[class*='ProductCard']"))

        for card in cards[:10]:
            try:
                nombre_el = card.select_one("[class*='product-name'],h3,h4")
                precio_el = card.select_one("[class*='sale'],[class*='price-final']")
                antes_el  = card.select_one("[class*='old'],[class*='original'],[class*='regular']")
                link_el   = card.select_one("a[href]")
                img_el    = card.select_one("img")

                if not nombre_el or not precio_el:
                    continue

                nombre   = nombre_el.get_text(strip=True)
                precio   = _precio(precio_el.get_text())
                precio_o = _precio(antes_el.get_text()) if antes_el else 0
                link     = link_el["href"] if link_el else ""
                if link and link.startswith("/"):
                    link = "https://www.sony.com.mx" + link
                thumb    = img_el.get("src", "") if img_el else ""

                cat_n = "Audio" if any(w in nombre.lower() for w in ["wh","wf","speaker","bocina"]) else "Electrónica"
                cat_e = "🎧" if cat_n == "Audio" else "📺" if "tv" in nombre.lower() else "🔌"

                item = _item("sony", nombre, precio, precio_o,
                             nombre[:20], link, thumb, cat_n, cat_e)
                if item:
                    resultados.append(item)
            except Exception:
                continue

    except Exception as e:
        logger.error(f"[SONY] {e}")

    logger.info(f"[SONY] {len(resultados)} productos")
    return resultados


# ─────────────────────────────────────────────
# CICLOS EXPORTADOS
# ─────────────────────────────────────────────

def ejecutar_ciclo_costco() -> list:
    return scrape_costco()


def ejecutar_ciclo_sams() -> list:
    return scrape_sams()


def ejecutar_ciclo_petco() -> list:
    return scrape_petco()


def ejecutar_ciclo_sears() -> list:
    return scrape_sears()


def ejecutar_ciclo_palacio() -> list:
    return scrape_palacio()


def ejecutar_ciclo_inditex() -> list:
    return scrape_inditex()


def ejecutar_ciclo_marcas_directo() -> list:
    """Samsung + LG + Sony directo — rotar por run."""
    slot = random.choice(["samsung", "lg", "sony"])
    if slot == "samsung":
        return scrape_samsung_outlet()
    elif slot == "lg":
        return scrape_lg()
    else:
        return scrape_sony()