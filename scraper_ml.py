# =============================================================
# DROPNODE MX — scraper_ml.py  v2.0
# Fix critico: autenticacion OAuth2 con Client Credentials
# Resuelve el error 403 permanentemente
# =============================================================

import requests
import time
import random
import logging
from datetime import datetime, timedelta
from config import (
    CATEGORIAS_ML, MAX_ITEMS_POR_CATEGORIA,
    DELAY_MIN, DELAY_MAX, MODO_FRIO, UMBRAL_FRIO,
    UMBRAL_DESCUENTO_FREE
)
from database import (
    upsert_producto, guardar_precio,
    get_minimo_historico, detectar_inflacion_previa,
    alerta_ya_enviada_hoy
)
from heat_score import calcular_heat_score

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CREDENCIALES ML
# ─────────────────────────────────────────────
ML_APP_ID      = "8981005082557994"
ML_SECRET      = "uPi0xSGRxpAPWUGDOLdoT04g6PNg4Yd2"
ML_TOKEN_URL   = "https://api.mercadolibre.com/oauth/token"

# Token en memoria — se renueva automaticamente cada 6 horas
_token_data = {"access_token": None, "expires_at": None}


def obtener_token() -> str:
    """
    Obtiene o renueva el Access Token de ML usando Client Credentials.
    El token dura 6 horas — se renueva automaticamente.
    """
    ahora = datetime.utcnow()

    # Reusar token si todavia es valido
    if (_token_data["access_token"] and
            _token_data["expires_at"] and
            ahora < _token_data["expires_at"]):
        return _token_data["access_token"]

    logger.info("[ML AUTH] Obteniendo nuevo Access Token...")

    try:
        resp = requests.post(
            ML_TOKEN_URL,
            data={
                "grant_type":    "client_credentials",
                "client_id":     ML_APP_ID,
                "client_secret": ML_SECRET,
            },
            timeout=15
        )

        if resp.status_code == 200:
            data = resp.json()
            _token_data["access_token"] = data["access_token"]
            # Expirar 5 minutos antes para evitar tokens caducados
            _token_data["expires_at"] = (
                ahora + timedelta(seconds=data.get("expires_in", 21600) - 300)
            )
            logger.info("[ML AUTH] Token obtenido correctamente")
            return _token_data["access_token"]
        else:
            logger.error(f"[ML AUTH] Error {resp.status_code}: {resp.text}")
            return None

    except Exception as e:
        logger.error(f"[ML AUTH] Exception: {e}")
        return None


# ─────────────────────────────────────────────
#  ANTI-BLOQUEO
# ─────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/122.0.0.0",
]

def get_headers() -> dict:
    token = obtener_token()
    headers = {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json",
        "Accept-Language": "es-MX,es;q=0.9",
        "Connection":      "keep-alive",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def esperar():
    s = random.uniform(DELAY_MIN, DELAY_MAX)
    time.sleep(s)

def llamar_api(url, params=None, reintentos=3):
    for intento in range(reintentos):
        try:
            esperar()
            resp = requests.get(
                url, params=params,
                headers=get_headers(), timeout=15
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401:
                # Token expirado — forzar renovacion
                logger.warning("[ML AUTH] Token expirado, renovando...")
                _token_data["access_token"] = None
                _token_data["expires_at"]   = None
                continue
            elif resp.status_code == 429:
                espera = (2 ** intento) * 12
                logger.warning(f"[RATE LIMIT] {espera}s")
                time.sleep(espera)
            elif resp.status_code == 403:
                logger.warning(f"[403] Acceso denegado — reintentando con token renovado")
                _token_data["access_token"] = None
                time.sleep(10)
            elif resp.status_code == 404:
                return None
            else:
                logger.warning(f"[HTTP {resp.status_code}]")
                time.sleep(5)
        except requests.exceptions.Timeout:
            logger.warning(f"[TIMEOUT] intento {intento+1}")
            time.sleep(5)
        except requests.exceptions.ConnectionError:
            logger.warning(f"[CONN ERROR] intento {intento+1}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"[ERROR] {e}")
            time.sleep(5)
    logger.error(f"[FAIL] {url}")
    return None


# ─────────────────────────────────────────────
#  BUSQUEDA DE PRODUCTOS
# ─────────────────────────────────────────────

def buscar_items_categoria(categoria_id, offset=0):
    url    = "https://api.mercadolibre.com/sites/MLM/search"
    params = {
        "category": categoria_id,
        "sort":     "relevance",
        "offset":   offset,
        "limit":    50,
        "condition": "new",
    }
    data = llamar_api(url, params)
    return data.get("results", []) if data else []

def get_detalle_item(item_id):
    return llamar_api(f"https://api.mercadolibre.com/items/{item_id}")

def calcular_descuento_frio(precio_actual, precio_original):
    if not precio_original or precio_original <= precio_actual:
        return 0.0
    return (precio_original - precio_actual) / precio_original


# ─────────────────────────────────────────────
#  PROCESAMIENTO DE CADA PRODUCTO
# ─────────────────────────────────────────────

def procesar_item(item_raw, categoria):
    item_id       = item_raw.get("id")
    nombre        = item_raw.get("title", "Producto")
    precio_actual = item_raw.get("price", 0)
    precio_orig   = item_raw.get("original_price") or precio_actual
    permalink     = item_raw.get("permalink", "")
    stock_raw     = item_raw.get("available_quantity", 0)
    thumbnail     = item_raw.get("thumbnail", "")

    if not precio_actual or precio_actual <= 0:
        return None

    producto_id = upsert_producto(
        url=permalink, tienda="mercadolibre",
        nombre=nombre, categoria=categoria["nombre"], sku=item_id
    )

    detalle = get_detalle_item(item_id)
    if detalle:
        stock_raw     = detalle.get("available_quantity", stock_raw)
        precio_actual = detalle.get("price", precio_actual)
        precio_orig   = detalle.get("original_price") or precio_orig
        thumbnail     = detalle.get("thumbnail", thumbnail)

    guardar_precio(
        producto_id=producto_id, precio=precio_actual,
        precio_original=precio_orig, stock=stock_raw,
        disponible=(stock_raw > 0)
    )

    if alerta_ya_enviada_hoy(producto_id):
        return None
    if stock_raw <= 0:
        return None

    # Calcular descuento segun modo
    if MODO_FRIO:
        descuento_real    = calcular_descuento_frio(precio_actual, precio_orig)
        precio_referencia = precio_orig
        if descuento_real < UMBRAL_FRIO:
            return None
    else:
        minimo = get_minimo_historico(producto_id)
        if minimo is None:
            return None
        if precio_actual >= minimo:
            return None
        descuento_real    = (minimo - precio_actual) / minimo
        precio_referencia = minimo
        if descuento_real < UMBRAL_DESCUENTO_FREE:
            return None
        if detectar_inflacion_previa(producto_id):
            return None

    score = calcular_heat_score(
        descuento_real=descuento_real,
        stock=stock_raw,
        categoria=categoria["nombre"],
        precio_actual=precio_actual,
        precio_original=precio_orig
    )

    logger.info(
        f"[ALERTA] {nombre[:40]} | "
        f"${precio_actual:,.0f} (-{descuento_real*100:.0f}%) | "
        f"Score:{score}"
    )

    return {
        "producto_id":     producto_id,
        "item_id":         item_id,
        "nombre":          nombre,
        "precio_actual":   precio_actual,
        "precio_original": precio_orig,
        "precio_minimo":   precio_referencia,
        "descuento_real":  descuento_real,
        "stock":           stock_raw,
        "categoria":       categoria,
        "permalink":       permalink,
        "thumbnail":       thumbnail,
        "heat_score":      score,
        "modo_frio":       MODO_FRIO,
    }


# ─────────────────────────────────────────────
#  CICLO COMPLETO
# ─────────────────────────────────────────────

def ejecutar_ciclo():
    logger.info(
        f"[CICLO] Iniciando — {datetime.now().strftime('%H:%M:%S')} | "
        f"Modo: {'FRIO' if MODO_FRIO else 'NORMAL'}"
    )

    # Verificar token antes de empezar
    token = obtener_token()
    if not token:
        logger.error("[CICLO] Sin token ML — abortando ciclo")
        return []

    alertas = []

    for categoria in CATEGORIAS_ML:
        logger.info(f"[CAT] {categoria['emoji']} {categoria['nombre']}")
        procesados = 0

        for offset in range(0, MAX_ITEMS_POR_CATEGORIA, 50):
            items = buscar_items_categoria(categoria["id"], offset)
            if not items:
                break
            for item in items:
                r = procesar_item(item, categoria)
                if r and r["heat_score"] >= 4:
                    alertas.append(r)
                procesados += 1
                if procesados >= MAX_ITEMS_POR_CATEGORIA:
                    break
            if procesados >= MAX_ITEMS_POR_CATEGORIA:
                break

        logger.info(f"[CAT] {categoria['nombre']}: {procesados} revisados")

    alertas.sort(key=lambda x: x["heat_score"], reverse=True)
    logger.info(f"[CICLO] Terminado — {len(alertas)} alertas")
    return alertas
