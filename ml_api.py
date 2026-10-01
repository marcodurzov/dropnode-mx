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
    """Lista de resultados de búsqueda (o [])."""
    params = {"q": query, "condition": "new", "limit": limit, "sort": "relevance"}
    if extra:
        params.update(extra)
    try:
        time.sleep(random.uniform(1, 3))
        r = get("https://api.mercadolibre.com/sites/MLM/search", params=params)
        return r.json().get("results", []) if r.status_code == 200 else []
    except Exception as e:
        logger.warning(f"[ML API] buscar '{query}': {e}")
        return []
