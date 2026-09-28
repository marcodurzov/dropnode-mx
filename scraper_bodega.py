# =============================================================
# DROPNODE MX — scraper_bodega.py
# Bodega Aurrerá MX (Walmart subsidiary)
# Usa API interna de Walmart MX adaptada
# =============================================================
import requests, time, random, logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_UA = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]

def _h(ref="https://www.bodegaaurrera.com.mx/"):
    return {"User-Agent": random.choice(_UA),
            "Accept": "application/json,text/html,*/*",
            "Accept-Language": "es-MX,es;q=0.9", "Referer": ref}

def _p(v):
    try: return float(str(v).replace(",","").replace("$","").strip())
    except: return 0.0

def _it(nombre, precio, precio_o, sku, url, thumb, cat_n, cat_e):
    if precio <= 0 or not nombre or not url: return None
    d = (precio_o - precio) / precio_o if precio_o > precio else 0.0
    if d < 0.12: return None
    return {"tienda":"bodega","nombre":nombre[:80],"precio_actual":precio,
            "precio_original":precio_o,"descuento":d,"sku":str(sku),"url":url,
            "thumbnail":thumb or "","categoria":{"nombre":cat_n,"emoji":cat_e},
            "envio_gratis":False}

def _infer_cat(nombre):
    n = nombre.lower()
    if any(w in n for w in ["celular","smartphone","iphone","samsung"]): return "Celulares","📱"
    if any(w in n for w in ["televisor","pantalla","smart tv"]): return "Televisores","📺"
    if any(w in n for w in ["laptop","tablet","computadora"]): return "Cómputo","💻"
    if any(w in n for w in ["lavadora","refri","estufa","microondas"]): return "Hogar","🏠"
    if any(w in n for w in ["juguete","muñeca","lego"]): return "Juguetes","🧸"
    if any(w in n for w in ["ropa","pantalon","playera","zapato"]): return "Moda","👗"
    if any(w in n for w in ["alimento","comida","leche","cereal"]): return "Alimentos","🍎"
    return "General","🛒"

# ── API de Bodega Aurrerá (misma base que Walmart MX) ──
def _api_bodega(dept_id=None, limit=20):
    """
    Bodega Aurrerá comparte infraestructura con Walmart MX.
    Su API devuelve JSON con productos y precios.
    """
    urls = [
        "https://www.bodegaaurrera.com.mx/api/products/v2/search?query=*&sort=discount&order=desc&limit=50",
        "https://www.bodegaaurrera.com.mx/api/products/search?q=oferta&sortBy=bestDiscount&numItems=40",
        "https://www.bodegaaurrera.com.mx/graphql",
    ]
    for url in urls[:2]:
        try:
            time.sleep(random.uniform(4,8))
            r = requests.get(url, headers=_h(), timeout=20)
            if r.status_code == 200:
                data = r.json()
                items = (data.get("items") or data.get("products") or
                         data.get("searchResult",{}).get("itemStacks",[{}])[0].get("items",[]))
                if items:
                    return items
        except: pass
    return []

def _parsear_api(items):
    res = []
    for item in items:
        try:
            nombre = (item.get("name") or item.get("title") or
                      item.get("displayName",""))
            precio = _p(item.get("price") or item.get("salePrice") or
                        item.get("priceInfo",{}).get("currentPrice",0))
            p_orig = _p(item.get("wasPrice") or item.get("listPrice") or
                        item.get("priceInfo",{}).get("wasPrice",0))
            thumb  = (item.get("imageInfo",{}).get("thumbnailUrl") or
                      item.get("image") or item.get("thumbnail",""))
            link   = item.get("canonicalUrl") or item.get("productUrl") or ""
            if link and not link.startswith("http"):
                link = "https://www.bodegaaurrera.com.mx" + link
            sku    = str(item.get("id") or item.get("productId") or nombre[:15])
            cat_n, cat_e = _infer_cat(nombre)
            it = _it(nombre, precio, p_orig, sku, link, thumb, cat_n, cat_e)
            if it: res.append(it)
        except: continue
    return res

def _html_bodega():
    """Fallback HTML cuando la API no responde."""
    urls = [
        "https://www.bodegaaurrera.com.mx/oferta",
        "https://www.bodegaaurrera.com.mx/ofertas-especiales",
    ]
    res = []
    for url in urls[:1]:
        try:
            time.sleep(random.uniform(5,9))
            r = requests.get(url, headers=_h(), timeout=20)
            if r.status_code != 200: continue
            soup = BeautifulSoup(r.text, "html.parser")
            # Walmart / Bodega usan estructura de Grid con data attributes
            cards = (soup.select("[data-testid='list-view']") or
                     soup.select("[class*='Grid-module']") or
                     soup.select("[class*='product-tile']") or
                     soup.select("article"))
            for card in cards[:20]:
                try:
                    ne = card.select_one("[class*='product-title'],[itemprop='name'],h3,h4")
                    pe = card.select_one("[class*='price-characteristic'],[class*='sale'],[class*='current']")
                    oe = card.select_one("[class*='strike'],[class*='was'],[class*='original']")
                    le = card.select_one("a[href]")
                    ie = card.select_one("img")
                    if not ne or not pe: continue
                    nombre = ne.get_text(strip=True)
                    precio = _p(pe.get_text()); p_orig = _p(oe.get_text()) if oe else 0
                    link   = le["href"] if le else ""
                    if link and not link.startswith("http"):
                        link = "https://www.bodegaaurrera.com.mx" + link
                    thumb  = ie.get("src","") if ie else ""
                    cat_n, cat_e = _infer_cat(nombre)
                    it = _it(nombre, precio, p_orig, nombre[:15], link, thumb, cat_n, cat_e)
                    if it: res.append(it)
                except: continue
        except Exception as e:
            logger.error(f"[BODEGA HTML] {e}")
    return res

def ejecutar_ciclo_bodega():
    logger.info("[BODEGA] Iniciando...")
    res  = []; seen = set()

    # 1. Intentar API JSON primero
    items_api = _api_bodega()
    if items_api:
        for it in _parsear_api(items_api):
            if it["sku"] not in seen: seen.add(it["sku"]); res.append(it)

    # 2. Fallback a HTML si API no dio resultados
    if not res:
        logger.info("[BODEGA] Fallback a HTML")
        for it in _html_bodega():
            if it["sku"] not in seen: seen.add(it["sku"]); res.append(it)

    res.sort(key=lambda x: x["descuento"], reverse=True)
    logger.info(f"[BODEGA] {len(res)} productos")
    return res[:15]
