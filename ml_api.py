# =============================================================
# DROPNODE MX — ml_api.py  (v1.0)
# Acceso a la API pública de Mercado Libre CON token de aplicación
# (si defines ML_APP_ID y ML_SECRET). Sin token, ML suele responder
# 403 a IPs de datacenter como las de GitHub Actions.
# Devuelve objetos requests.Response, así el código viejo no cambia.
# =============================================================
import os, time, logging, random
import requests

logger = logging.getLogger(__name__)
_token = {"v": None, "exp": 0}

UA = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"]


def token():
    app, sec = os.environ.get("ML_APP_ID", "").strip(), os.environ.get("ML_SECRET", "").strip()
    if not app or not sec:
        return None
    if _token["v"] and time.time() < _token["exp"] - 120:
        return _token["v"]
    try:
        r = requests.post("https://api.mercadolibre.com/oauth/token",
                          data={"grant_type": "client_credentials", "client_id": app, "client_secret": sec},
                          headers={"Accept": "application/json",
                                   "Content-Type": "application/x-www-form-urlencoded"}, timeout=15)
        if r.status_code == 200:
            d = r.json()
            _token["v"], _token["exp"] = d["access_token"], time.time() + int(d.get("expires_in", 21000))
            return _token["v"]
        logger.warning(f"[ML TOKEN] HTTP {r.status_code}")
    except Exception as e:
        logger.warning(f"[ML TOKEN] {e}")
    return None


def get(url, params=None, headers=None, timeout=15):
    h = {"User-Agent": random.choice(UA), "Accept": "application/json", "Accept-Language": "es-MX,es;q=0.9"}
    if headers:
        h.update(headers)
    t = token()
    if t:
        h["Authorization"] = f"Bearer {t}"
    r = requests.get(url, params=params, headers=h, timeout=timeout)
    if r.status_code in (401, 403) and t:
        _token["v"] = None          # token vencido: reintenta una vez
        t = token()
        if t:
            h["Authorization"] = f"Bearer {t}"
            r = requests.get(url, params=params, headers=h, timeout=timeout)
    if r.status_code != 200:
        logger.warning(f"[ML API] HTTP {r.status_code} {url.split('?')[0][-50:]}")
    return r


def buscar(query, limit=30, extra=None):
    """Lista de resultados de búsqueda (o []).
    /sites/MLM/search responde 403 desde GitHub incluso con token; entonces se usa la ruta
    de catálogo (products/search -> producto ganador -> /items), que devuelve dicts compatibles
    (id, title, price, original_price, permalink, thumbnail, shipping)."""
    params = {"q": query, "condition": "new", "limit": limit, "sort": "relevance"}
    if extra:
        params.update(extra)
    try:
        time.sleep(random.uniform(1, 3))
        r = get("https://api.mercadolibre.com/sites/MLM/search", params=params)
        if r.status_code == 200:
            return r.json().get("results", [])
    except Exception as e:
        logger.warning(f"[ML API] buscar '{query}': {e}")
    return catalogo_buscar(query, max_productos=min(10, max(3, limit // 4)))


# ─────────────────────────────────────────────
# Ruta de catálogo (responde 200 con token de aplicación)
#   highlights/products-search -> id de producto -> buy_box_winner.item_id -> /items?ids=...
# ─────────────────────────────────────────────
API = "https://api.mercadolibre.com"


def _json(r):
    try:
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def items_por_ids(ids):
    """Multiget de /items (de 20 en 20). Devuelve los 'body' con code 200."""
    out = []
    ids = [i for i in dict.fromkeys(ids) if i]
    for i in range(0, len(ids), 20):
        try:
            time.sleep(random.uniform(0.3, 0.8))
            data = _json(get(f"{API}/items", params={"ids": ",".join(ids[i:i + 20])}))
            for e in data or []:
                if isinstance(e, dict) and e.get("code") == 200 and isinstance(e.get("body"), dict):
                    out.append(e["body"])
        except Exception as ex:
            logger.warning(f"[ML API] items multiget: {ex}")
    return out


_PRODUCTOS_403 = {"v": False}


def item_id_de_producto(pid):
    """ID del item ganador (buy box) de un producto de catálogo.
    (Con la app actual /products/{id} responde 403: tras el primer 403 ya no se insiste.)"""
    if _PRODUCTOS_403["v"]:
        return None
    try:
        time.sleep(random.uniform(0.2, 0.5))
        r = get(f"{API}/products/{pid}")
        if r.status_code == 403:
            _PRODUCTOS_403["v"] = True
            return None
        d = _json(r) or {}
        bb = d.get("buy_box_winner") or {}
        return bb.get("item_id")
    except Exception:
        return None


def highlights_ids(cat_id):
    """(ids_de_items, ids_de_productos) de los más vendidos de una categoría."""
    d = _json(get(f"{API}/highlights/MLM/category/{cat_id}")) or {}
    items, prods = [], []
    for x in d.get("content") or []:
        t = str(x.get("type", "")).upper()
        if t == "ITEM":
            items.append(x.get("id"))
        elif t in ("PRODUCT", "USER_PRODUCT"):
            prods.append(x.get("id"))
    return items, prods


def highlights_items(cat_id, max_productos=12):
    """Items completos (con precio y precio original) de los más vendidos de una categoría."""
    items, prods = highlights_ids(cat_id)
    for p in prods[:max_productos]:
        iid = item_id_de_producto(p)
        if iid:
            items.append(iid)
    return items_por_ids(items)


def catalogo_buscar(query, max_productos=8):
    """Equivalente a una búsqueda: products/search -> items ganadores."""
    try:
        time.sleep(random.uniform(0.5, 1.5))
        d = _json(get(f"{API}/products/search", params={"status": "active", "site_id": "MLM",
                                                          "q": query, "limit": max_productos})) or {}
        ids = []
        for p in (d.get("results") or [])[:max_productos]:
            iid = item_id_de_producto(p.get("id"))
            if iid:
                ids.append(iid)
        return items_por_ids(ids)
    except Exception as e:
        logger.warning(f"[ML API] catalogo_buscar '{query}': {e}")
        return []
