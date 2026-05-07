# DropNode MX — scraper_liverpool.py
# Liverpool MX — API oficial de Shopping
import requests, time, random, logging, json

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "es-MX,es;q=0.9",
    "Origin": "https://www.liverpool.com.mx",
    "Referer": "https://www.liverpool.com.mx/",
}

BUSQUEDAS = [
    {"q": "laptop",             "emoji": "💻", "cat": "Computacion"},
    {"q": "television 4k",      "emoji": "📺", "cat": "Televisores"},
    {"q": "celular smartphone",  "emoji": "📱", "cat": "Celulares"},
    {"q": "iphone",             "emoji": "📱", "cat": "Celulares"},
    {"q": "samsung galaxy",     "emoji": "📱", "cat": "Celulares"},
    {"q": "audifonos",          "emoji": "🎧", "cat": "Audio"},
    {"q": "consola videojuegos", "emoji": "🎮", "cat": "Videojuegos"},
    {"q": "tablet ipad",        "emoji": "📱", "cat": "Tablets"},
]

def buscar(query: str) -> list:
    try:
        time.sleep(random.uniform(3, 6))
        # API oficial de Liverpool Shopping
        r = requests.get(
            "https://shoppingapi.liverpool.com.mx/api/2.0/page",
            params={
                "pathName": "/search",
                "query": query,
                "type": "search",
                "customerPreference": "liverpool",
                "page": "0",
                "rows": "48",
                "sort": "discounts",  # Ordenar por mayor descuento
            },
            headers=HEADERS, timeout=20
        )
        if r.status_code == 200:
            data = r.json()
            # Navegar estructura de respuesta de Liverpool
            records = (data.get("data", {})
                          .get("results", {})
                          .get("Product", {})
                          .get("records", []))
            if records:
                return records
            # Estructura alternativa
            records = (data.get("data", {})
                          .get("records", []))
            return records or []
        logger.warning(f"[LIVERPOOL] HTTP {r.status_code} para '{query}'")
        return []
    except Exception as e:
        logger.error(f"[LIVERPOOL] {e}")
        return []

def parsear(record: dict, cat: dict) -> dict | None:
    try:
        attrs = record.get("attributes", {})
        nombre = str(attrs.get("product.displayName", [""])[0] or
                     attrs.get("product.name", [""])[0])[:80]
        precio_str = (attrs.get("sku.activePrice", ["0"])[0] or
                      attrs.get("sku.listPrice", ["0"])[0])
        precio = float(str(precio_str).replace(",",""))
        precio_orig_str = (attrs.get("sku.listPrice", ["0"])[0] or
                           attrs.get("sku.compareAtPrice", ["0"])[0])
        precio_orig = float(str(precio_orig_str).replace(",",""))
        sku = str(attrs.get("sku.repositoryId", [""])[0] or
                  record.get("id", ""))
        url_base = str(attrs.get("product.canonicalUrl", [""])[0] or "")
        if url_base and not url_base.startswith("http"):
            url_base = "https://www.liverpool.com.mx" + url_base
        img = str(attrs.get("sku.primarySmallImageUrl", [""])[0] or "")
        if not nombre or precio <= 0 or not url_base:
            return None
        descuento = 0.0
        if precio_orig > precio:
            descuento = (precio_orig - precio) / precio_orig
        if descuento < 0.10:
            return None
        return {
            "tienda": "liverpool",
            "nombre": nombre,
            "precio_actual": precio,
            "precio_original": precio_orig,
            "descuento": descuento,
            "sku": sku,
            "url": url_base,
            "thumbnail": img,
            "categoria": {"nombre": cat["cat"], "emoji": cat["emoji"]},
        }
    except Exception:
        return None

def ejecutar_ciclo_liverpool() -> list:
    logger.info("[LIVERPOOL] Iniciando ciclo...")
    resultados = []
    for cat in BUSQUEDAS[:4]:  # 4 busquedas por ciclo
        records = buscar(cat["q"])
        for rec in records:
            r = parsear(rec, cat)
            if r:
                resultados.append(r)
    # Deduplicar por SKU
    seen = set()
    unicos = []
    for r in resultados:
        if r["sku"] not in seen:
            seen.add(r["sku"])
            unicos.append(r)
    logger.info(f"[LIVERPOOL] {len(unicos)} productos con descuento")
    return unicos