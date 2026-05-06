# =============================================================
# DROPNODE MX — scraper_ml.py  v2.1
# Dos modos de publicacion:
#   1. ALERTA: producto con descuento real >= umbral
#   2. DESTACADO DEL DIA: mejores precios del ciclo sin importar %
# =============================================================

import requests, time, random, logging
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

# Credenciales ML OAuth2
ML_APP_ID    = "8981005082557994"
ML_SECRET    = "uPi0xSGRxpAPWUGDOLdoT04g6PNg4Yd2"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
_token_data  = {"access_token": None, "expires_at": None}


def obtener_token() -> str:
    ahora = datetime.utcnow()
    if (_token_data["access_token"] and _token_data["expires_at"]
            and ahora < _token_data["expires_at"]):
        return _token_data["access_token"]

    logger.info("[ML AUTH] Obteniendo token...")
    try:
        resp = requests.post(ML_TOKEN_URL, data={
            "grant_type":    "client_credentials",
            "client_id":     ML_APP_ID,
            "client_secret": ML_SECRET,
        }, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            _token_data["access_token"] = data["access_token"]
            _token_data["expires_at"]   = ahora + timedelta(
                seconds=data.get("expires_in", 21600) - 300)
            logger.info("[ML AUTH] Token OK")
            return _token_data["access_token"]
        else:
            logger.error(f"[ML AUTH] Error {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"[ML AUTH] {e}")
        return None


USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
]

def get_headers():
    token = obtener_token()
    h = {
        "User-Agent":      random.choice(USER_AGENTS),
        "Accept":          "application/json",
        "Accept-Language": "es-MX,es;q=0.9",
    }
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

def esperar():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

def llamar_api(url, params=None, reintentos=3):
    for intento in range(reintentos):
        try:
            esperar()
            resp = requests.get(url, params=params,
                                headers=get_headers(), timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in (401, 403):
                _token_data["access_token"] = None
                logger.warning(f"[ML] {resp.status_code} — renovando token")
                time.sleep(5)
            elif resp.status_code == 429:
                time.sleep((2 ** intento) * 12)
            else:
                logger.warning(f"[HTTP {resp.status_code}]")
                time.sleep(5)
        except Exception as e:
            logger.error(f"[ML] {e}")
            time.sleep(5)
    return None


def buscar_items(categoria_id, offset=0):
    data = llamar_api("https://api.mercadolibre.com/sites/MLM/search", {
        "category": categoria_id,
        "sort":     "relevance",
        "offset":   offset,
        "limit":    50,
        "condition": "new",
    })
    return data.get("results", []) if data else []


def get_detalle(item_id):
    return llamar_api(f"https://api.mercadolibre.com/items/{item_id}")


def ejecutar_ciclo():
    """
    Retorna dos listas:
      alertas    — productos con descuento real verificado
      destacados — mejores precios del ciclo (sin filtro de descuento)
    """
    if not obtener_token():
        logger.error("[CICLO ML] Sin token — abortando")
        return [], []

    alertas    = []
    destacados = []   # Top productos por categoria sin filtro de %

    logger.info(f"[CICLO ML] {datetime.now().strftime('%H:%M')} | "
                f"Modo: {'FRIO' if MODO_FRIO else 'NORMAL'}")

    for categoria in CATEGORIAS_ML:
        logger.info(f"[CAT] {categoria['emoji']} {categoria['nombre']}")
        procesados       = 0
        mejor_de_cat     = None   # El mejor producto de esta categoria
        mejor_score_cat  = -1

        for offset in range(0, MAX_ITEMS_POR_CATEGORIA, 50):
            items = buscar_items(categoria["id"], offset)
            if not items:
                break

            for item_raw in items:
                resultado = procesar_item(item_raw, categoria)
                procesados += 1

                if resultado is None:
                    continue

                # Actualizar mejor de la categoria (para destacados)
                if resultado["heat_score"] > mejor_score_cat:
                    mejor_score_cat = resultado["heat_score"]
                    mejor_de_cat    = resultado

                # Si tiene descuento real, va a alertas
                if resultado.get("tiene_descuento"):
                    alertas.append(resultado)

                if procesados >= MAX_ITEMS_POR_CATEGORIA:
                    break

            if procesados >= MAX_ITEMS_POR_CATEGORIA:
                break

        # Agregar el mejor de la categoria a destacados
        if mejor_de_cat and mejor_de_cat not in alertas:
            destacados.append(mejor_de_cat)

        logger.info(f"[CAT] {categoria['nombre']}: {procesados} revisados")

    alertas.sort(key=lambda x: x["heat_score"], reverse=True)
    destacados.sort(key=lambda x: x["heat_score"], reverse=True)

    logger.info(f"[CICLO ML] Fin — {len(alertas)} alertas | "
                f"{len(destacados)} destacados")

    return alertas, destacados


def procesar_item(item_raw, categoria):
    """
    Procesa un item. Retorna dict con:
      - tiene_descuento: True si pasó el umbral
      - heat_score calculado
    """
    item_id       = item_raw.get("id")
    nombre        = item_raw.get("title", "Producto")
    precio_actual = item_raw.get("price", 0)
    precio_orig   = item_raw.get("original_price") or 0
    permalink     = item_raw.get("permalink", "")
    stock_raw     = item_raw.get("available_quantity", 0)
    thumbnail     = item_raw.get("thumbnail", "")

    if not precio_actual or precio_actual <= 0:
        return None

    # Guardar en Supabase
    producto_id = upsert_producto(
        url=permalink, tienda="mercadolibre",
        nombre=nombre, categoria=categoria["nombre"], sku=item_id
    )

    # Obtener detalle completo
    detalle = get_detalle(item_id)
    if detalle:
        stock_raw     = detalle.get("available_quantity", stock_raw)
        precio_actual = detalle.get("price", precio_actual)
        precio_orig   = detalle.get("original_price") or precio_orig
        thumbnail     = detalle.get("thumbnail", thumbnail)

    guardar_precio(
        producto_id=producto_id, precio=precio_actual,
        precio_original=precio_orig or precio_actual,
        stock=stock_raw, disponible=(stock_raw > 0)
    )

    if stock_raw <= 0:
        return None
    if alerta_ya_enviada_hoy(producto_id):
        return None

    # Calcular descuento
    tiene_descuento = False
    descuento_real  = 0.0
    precio_ref      = precio_actual

    if MODO_FRIO and precio_orig and precio_orig > precio_actual:
        descuento_real = (precio_orig - precio_actual) / precio_orig
        precio_ref     = precio_orig
        if descuento_real >= UMBRAL_FRIO:
            tiene_descuento = True
    elif not MODO_FRIO:
        minimo = get_minimo_historico(producto_id)
        if minimo and precio_actual < minimo:
            descuento_real = (minimo - precio_actual) / minimo
            precio_ref     = minimo
            if descuento_real >= UMBRAL_DESCUENTO_FREE:
                if not detectar_inflacion_previa(producto_id):
                    tiene_descuento = True

    score = calcular_heat_score(
        descuento_real=descuento_real,
        stock=stock_raw,
        categoria=categoria["nombre"],
        precio_actual=precio_actual,
        precio_original=precio_orig or precio_actual,
    )

    if tiene_descuento:
        logger.info(f"[ALERTA] {nombre[:40]} | "
                    f"${precio_actual:,.0f} (-{descuento_real*100:.0f}%) | "
                    f"Score:{score}")

    return {
        "producto_id":     producto_id,
        "item_id":         item_id,
        "nombre":          nombre,
        "precio_actual":   precio_actual,
        "precio_original": precio_orig or precio_actual,
        "precio_minimo":   precio_ref,
        "descuento_real":  descuento_real,
        "tiene_descuento": tiene_descuento,
        "stock":           stock_raw,
        "categoria":       categoria,
        "permalink":       permalink,
        "thumbnail":       thumbnail,
        "heat_score":      score,
        "modo_frio":       MODO_FRIO,
    }
