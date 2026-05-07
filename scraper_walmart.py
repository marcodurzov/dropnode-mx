# DropNode MX — scraper_walmart.py
# Walmart MX — parse de __NEXT_DATA__ embebido en HTML
import requests, time, random, logging, json, re

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
]

BUSQUEDAS = [
    {"q": "laptop",              "emoji": "💻", "cat": "Computacion"},
    {"q": "television smart tv", "emoji": "📺", "cat": "Televisores"},
    {"q": "celular desbloqueado","emoji": "📱", "cat": "Celulares"},
    {"q": "audifonos bluetooth", "emoji": "🎧", "cat": "Audio"},
    {"q": "videojuegos",         "emoji": "🎮", "cat": "Videojuegos"},
    {"q": "tablet",              "emoji": "📱", "cat": "Tablets"},
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }

def buscar_walmart(query: str) -> list:
    try:
        time.sleep(random.uniform(4, 8))
        url = f"https://www.walmart.com.mx/search?q={requests.utils.quote(query)}"
        r = requests.get(url, headers=get_headers(), timeout=25)
        if r.status_code != 200:
            logger.warning(f"[WALMART] HTTP {r.status_code} para '{query}'")
            return []
        # Extraer __NEXT_DATA__ del HTML (Next.js embebe todos los productos aqui)
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', r.text, re.DOTALL)
        if not match:
            logger.warning(f"[WALMART] Sin __NEXT_DATA__ para '{query}'")
            return []
        data = json.loads(match.group(1))
        # Navegar la estructura de Next.js de Walmart MX
        props = data.get("props", {}).get("pageProps", {})
        # Buscar items en diferentes rutas posibles
        items = (props.get("initialData", {})
                     .get("searchContent", {})
                     .get("paginationV2", {})
                     .get("resp", [{}])[0]
                     .get("itemStacks", [{}])[0]
                     .get("items", []))
        if not items:
            # Ruta alternativa
            items = (props.get("dehydratedState", {})
                        .get("queries", [{}])[0]
                        .get("state", {})
                        .get("data", {})
                        .get("items", []))
        if not items:
            # Busqueda generica en el JSON
            text = match.group(1)
            all_items = re.findall(r'"usItemId":"(\d+)".*?"price":(\d+\.?\d*)', text)
            logger.info(f"[WALMART] '{query}': {len(all_items)} items via regex")
        return items
    except Exception as e:
        logger.error(f"[WALMART] {e}")
        return []

def parsear(item: dict, cat: dict) -> dict | None:
    try:
        nombre = str(item.get("name") or item.get("title") or item.get("displayName") or "")[:80]
        precio = float(item.get("price") or item.get("salePrice") or item.get("priceInfo", {}).get("currentPrice", {}).get("price", 0) or 0)
        precio_orig = float(item.get("wasPrice") or item.get("listPrice") or item.get("priceInfo", {}).get("wasPrice", {}).get("price", precio) or precio)
        sku = str(item.get("usItemId") or item.get("itemId") or item.get("id") or "")
        url_p = str(item.get("canonicalUrl") or item.get("productPageUrl") or "")
        if url_p and not url_p.startswith("http"):
            url_p = "https://www.walmart.com.mx" + url_p
        img = str(item.get("imageInfo", {}).get("thumbnailUrl") or item.get("image") or item.get("imageUrl") or "")
        if not nombre or precio <= 0 or not url_p:
            return None
        descuento = 0.0
        if precio_orig > precio:
            descuento = (precio_orig - precio) / precio_orig
        if descuento < 0.10:
            return None
        return {
            "tienda": "walmart",
            "nombre": nombre,
            "precio_actual": precio,
            "precio_original": precio_orig,
            "descuento": descuento,
            "sku": sku,
            "url": url_p,
            "thumbnail": img,
            "categoria": {"nombre": cat["cat"], "emoji": cat["emoji"]},
        }
    except Exception:
        return None

def ejecutar_ciclo_walmart() -> list:
    logger.info("[WALMART] Iniciando ciclo...")
    resultados = []
    for cat in BUSQUEDAS[:3]:
        items = buscar_walmart(cat["q"])
        for item in items:
            r = parsear(item, cat)
            if r:
                resultados.append(r)
    seen = set()
    unicos = [r for r in resultados if r["sku"] not in seen and not seen.add(r["sku"])]
    logger.info(f"[WALMART] {len(unicos)} productos con descuento")
    return unicos