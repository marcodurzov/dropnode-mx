# =============================================================
# DROPNODE MX — scraper_elektra.py
# Elektra MX — VTEX API + búsqueda directa
# =============================================================
import requests, time, random, logging, re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_UA = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]

def _h(ref="https://www.elektra.mx/"):
    return {"User-Agent": random.choice(_UA), "Accept-Language": "es-MX,es;q=0.9",
            "Accept": "application/json,text/html,*/*", "Referer": ref}

def _p(v):
    try: return float(str(v).replace(",","").replace("$","").strip())
    except: return 0.0

def _it(nombre, precio, precio_o, sku, url, thumb, cat_n, cat_e, envio=False):
    if precio <= 0 or not nombre or not url: return None
    d = (precio_o - precio) / precio_o if precio_o > precio else 0.0
    if d < 0.12: return None
    return {"tienda":"elektra","nombre":nombre[:80],"precio_actual":precio,
            "precio_original":precio_o,"descuento":d,"sku":str(sku),"url":url,
            "thumbnail":thumb or "","categoria":{"nombre":cat_n,"emoji":cat_e},
            "envio_gratis":envio}

def _vtex(fq="", order="OrderByBestDiscountDESC", limit=24):
    try:
        time.sleep(random.uniform(5,9))
        r = requests.get("https://www.elektra.mx/api/catalog_system/pub/products/search",
            params={"O":order,"_from":0,"_to":limit-1,"fq":fq} if fq
            else {"O":order,"_from":0,"_to":limit-1},
            headers=_h(), timeout=20)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        logger.error(f"[ELEKTRA VTEX] {e}"); return []

def _parsear_vtex(prods, cat_n, cat_e):
    res = []
    for p in prods:
        try:
            nombre = p.get("productName","")
            link   = p.get("link","")
            if not link.startswith("http"): link = "https://www.elektra.mx" + link
            items  = p.get("items",[{}]); imgs = items[0].get("images",[{}]) if items else [{}]
            thumb  = imgs[0].get("imageUrl","") if imgs else ""
            sellers= items[0].get("sellers",[{}]) if items else [{}]
            offer  = sellers[0].get("commertialOffer",{}) if sellers else {}
            precio = _p(offer.get("Price",0)); p_orig = _p(offer.get("ListPrice",0))
            stock  = int(offer.get("AvailableQuantity",0)); sku = p.get("productId","")
            if stock <= 0: continue
            it = _it(nombre, precio, p_orig, sku, link, thumb, cat_n, cat_e)
            if it: res.append(it)
        except: continue
    return res

def _infer_cat(nombre):
    n = nombre.lower()
    if any(w in n for w in ["iphone","celular","samsung","motorola","xiaomi"]): return "Celulares","📱"
    if any(w in n for w in ["televisor","smart tv","pantalla","oled","qled"]): return "Televisores","📺"
    if any(w in n for w in ["laptop","computadora","tablet","ipad"]): return "Cómputo","💻"
    if any(w in n for w in ["audifonos","bocina","speaker","airpods"]): return "Audio","🎧"
    if any(w in n for w in ["lavadora","refrigerador","estufa","secadora"]): return "Hogar","🏠"
    return "Electrónica","🔌"

def _busqueda_elektra(query, cat_n, cat_e):
    """Búsqueda directa en Elektra — complementa VTEX cuando no hay categoría."""
    try:
        time.sleep(random.uniform(5,9))
        r = requests.get(
            f"https://www.elektra.mx/{query}?_q={query}&map=ft&order=OrderByBestDiscountDESC",
            headers=_h(), timeout=20)
        if r.status_code != 200: return []
        # Intentar parsear como VTEX JSON si devuelve JSON
        try:
            data = r.json()
            if isinstance(data, list): return _parsear_vtex(data, cat_n, cat_e)
        except: pass
        # Fallback HTML
        soup = BeautifulSoup(r.text, "html.parser")
        res  = []
        for card in soup.select("[class*='product-summary'],[class*='ProductCard'],[class*='vtex-product']")[:15]:
            try:
                ne = card.select_one("[class*='name'],[class*='title'],h3,h4")
                pe = card.select_one("[class*='sellingPrice'],[class*='sale'],[class*='Selling']")
                oe = card.select_one("[class*='listPrice'],[class*='List'],[class*='original']")
                le = card.select_one("a[href]"); ie = card.select_one("img")
                if not ne or not pe: continue
                nombre = ne.get_text(strip=True); precio = _p(pe.get_text())
                p_orig = _p(oe.get_text()) if oe else 0
                link   = le["href"] if le else ""
                if link and not link.startswith("http"): link = "https://www.elektra.mx" + link
                thumb  = ie.get("src","") if ie else ""
                it = _it(nombre, precio, p_orig, nombre[:15], link, thumb, cat_n, cat_e)
                if it: res.append(it)
            except: continue
        return res
    except Exception as e:
        logger.error(f"[ELEKTRA SEARCH] {query}: {e}"); return []

def ejecutar_ciclo_elektra():
    logger.info("[ELEKTRA] Iniciando...")
    res  = []; seen = set()

    def _add(items):
        for it in items:
            if it["sku"] not in seen: seen.add(it["sku"]); res.append(it)

    # 1. VTEX API — mejores descuentos generales
    prods = _vtex()
    for p in prods:
        nombre = p.get("productName","")
        cat_n, cat_e = _infer_cat(nombre)
        _add(_parsear_vtex([p], cat_n, cat_e))

    # 2. Búsquedas específicas por categoría caliente
    queries = [("iphones","Celulares","📱"),("laptops","Cómputo","💻"),
               ("televisores","Televisores","📺")]
    for q, cn, ce in queries[:2]:
        if len(res) < 5:  # Solo si VTEX no dio suficientes
            _add(_busqueda_elektra(q, cn, ce))

    res.sort(key=lambda x: x["descuento"], reverse=True)
    logger.info(f"[ELEKTRA] {len(res)} productos")
    return res[:15]
