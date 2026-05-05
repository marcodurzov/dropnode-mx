# =============================================================
# DROPNODE MX — scraper_amazon.py
# Amazon Mexico — scraping con requests + afiliado activo
# =============================================================

import requests, time, random, logging
logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]

BUSQUEDAS_AMAZON = [
    "celular smartphone oferta",
    "laptop computadora oferta",
    "smart tv television oferta",
    "audifonos bluetooth oferta",
    "tablet ipad oferta",
    "videojuegos consolas oferta",
    "electrodomesticos oferta",
]

def get_headers():
    return {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept-Language": "es-MX,es;q=0.9",
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection":      "keep-alive",
    }

def esperar():
    time.sleep(random.uniform(6, 14))

def buscar_amazon(query: str) -> list:
    """Busca productos en Amazon MX y extrae precios con descuento."""
    from bs4 import BeautifulSoup

    url = "https://www.amazon.com.mx/s"
    params = {
        "k":           query,
        "rh":          "p_n_specials_match:21191023011",  # Filtro de ofertas
        "s":           "price-asc-rank",
        "ref":         "sr_st_price-asc-rank",
    }

    try:
        esperar()
        resp = requests.get(url, params=params, headers=get_headers(), timeout=15)
        if resp.status_code != 200:
            logger.warning(f"[AMAZON] HTTP {resp.status_code} para '{query}'")
            return []

        soup     = BeautifulSoup(resp.text, "html.parser")
        items    = soup.select("div[data-component-type='s-search-result']")
        results  = []

        for item in items[:10]:
            try:
                nombre_el  = item.select_one("h2 a span")
                precio_el  = item.select_one("span.a-price-whole")
                antes_el   = item.select_one("span.a-text-price span.a-offscreen")
                asin_el    = item.get("data-asin", "")
                img_el     = item.select_one("img.s-image")

                if not nombre_el or not precio_el:
                    continue

                nombre        = nombre_el.text.strip()
                precio_str    = precio_el.text.replace(",", "").replace("$", "").strip()
                precio_actual = float(precio_str) if precio_str else 0

                precio_orig = precio_actual
                if antes_el:
                    antes_str = antes_el.text.replace(",", "").replace("$", "").strip()
                    precio_orig = float(antes_str) if antes_str else precio_actual

                if precio_actual <= 0:
                    continue

                descuento = 0.0
                if precio_orig > precio_actual:
                    descuento = (precio_orig - precio_actual) / precio_orig

                if descuento < 0.15:
                    continue

                thumbnail = img_el.get("src", "") if img_el else ""
                url_prod  = f"https://www.amazon.com.mx/dp/{asin_el}"

                results.append({
                    "tienda":          "amazon",
                    "nombre":          nombre[:80],
                    "precio_actual":   precio_actual,
                    "precio_original": precio_orig,
                    "descuento":       descuento,
                    "sku":             asin_el,
                    "url":             url_prod,
                    "thumbnail":       thumbnail,
                    "categoria":       {"nombre": query.split()[0].capitalize(), "emoji": "🛒"},
                })

            except Exception:
                continue

        return results

    except Exception as e:
        logger.error(f"[AMAZON] Error: {e}")
        return []


def ejecutar_ciclo_amazon() -> list:
    logger.info("[AMAZON] Iniciando ciclo...")
    resultados = []
    for query in BUSQUEDAS_AMAZON[:4]:  # Max 4 busquedas por ciclo
        items = buscar_amazon(query)
        resultados.extend(items)
    logger.info(f"[AMAZON] {len(resultados)} productos encontrados")
    return resultados
