# =============================================================
# DROPNODE MX — scraper_ml.py
# Scraper de Mercado Libre usando su API oficial
# Anti-bloqueo integrado en cada capa
# =============================================================

import requests
import time
import random
import logging
from datetime import datetime
from config import (
    CATEGORIAS_ML, MAX_ITEMS_POR_CATEGORIA,
    DELAY_MIN, DELAY_MAX
)
from database import (
    upsert_producto, guardar_precio,
    get_minimo_historico, get_ultimo_precio,
    detectar_inflacion_previa, alerta_ya_enviada_hoy
)
from heat_score import calcular_heat_score

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  ANTI-BLOQUEO: Headers realistas
#  Rotamos entre varios User-Agents reales
# ─────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]

def get_headers() -> dict:
    """Genera headers realistas con User-Agent aleatorio."""
    return {
        "User-Agent":       random.choice(USER_AGENTS),
        "Accept":           "application/json, text/plain, */*",
        "Accept-Language":  "es-MX,es;q=0.9,en;q=0.8",
        "Accept-Encoding":  "gzip, deflate, br",
        "Connection":       "keep-alive",
        "Referer":          "https://www.mercadolibre.com.mx/",
        "Origin":           "https://www.mercadolibre.com.mx",
    }

def esperar():
    """Delay aleatorio anti-bloqueo entre peticiones."""
    segundos = random.uniform(DELAY_MIN, DELAY_MAX)
    logger.debug(f"[DELAY] Esperando {segundos:.1f}s...")
    time.sleep(segundos)

def llamar_api(url: str, params: dict = None,
               reintentos: int = 3) -> dict | None:
    """
    Llama a la API con reintentos y backoff exponencial.
    Si falla 3 veces, retorna None en lugar de crashear.
    """
    for intento in range(reintentos):
        try:
            esperar()
            resp = requests.get(
                url,
                params=params,
                headers=get_headers(),
                timeout=15
            )

            if resp.status_code == 200:
                return resp.json()

            elif resp.status_code == 429:
                # Rate limit — esperamos más tiempo
                espera = (2 ** intento) * 10
                logger.warning(f"[RATE LIMIT] Esperando {espera}s...")
                time.sleep(espera)

            elif resp.status_code == 404:
                return None  # Item no existe, no reintentar

            else:
                logger.warning(f"[HTTP {resp.status_code}] {url}")
                time.sleep(5)

        except requests.exceptions.Timeout:
            logger.warning(f"[TIMEOUT] Intento {intento+1}/{reintentos}")
            time.sleep(5)
        except requests.exceptions.ConnectionError:
            logger.warning(f"[CONNECTION ERROR] Intento {intento+1}/{reintentos}")
            time.sleep(10)
        except Exception as e:
            logger.error(f"[ERROR] {e}")
            time.sleep(5)

    logger.error(f"[FAIL] Agotados reintentos para: {url}")
    return None


# ─────────────────────────────────────────────
#  BÚSQUEDA DE ITEMS EN ML
# ─────────────────────────────────────────────

def buscar_items_categoria(categoria_id: str,
                            offset: int = 0) -> list:
    """
    Busca items en una categoría, ordenados por mayor descuento.
    ML no tiene parámetro 'sort by discount', así que buscamos
    los más nuevos y con mayor diferencia precio/precio_original.
    """
    url = "https://api.mercadolibre.com/sites/MLM/search"
    params = {
        "category": categoria_id,
        "sort":     "relevance",
        "offset":   offset,
        "limit":    50,
        "condition": "new",
    }

    data = llamar_api(url, params)
    if not data:
        return []

    return data.get("results", [])


def get_detalle_item(item_id: str) -> dict | None:
    """
    Obtiene precio actual, stock y detalles completos de un item.
    """
    url = f"https://api.mercadolibre.com/items/{item_id}"
    return llamar_api(url)


# ─────────────────────────────────────────────
#  PROCESAMIENTO PRINCIPAL
# ─────────────────────────────────────────────

def procesar_item(item_raw: dict, categoria: dict) -> dict | None:
    """
    Procesa un item crudo de ML:
    1. Extrae datos relevantes
    2. Guarda en historial
    3. Calcula si es una alerta válida
    4. Retorna dict de alerta o None si no aplica
    """
    item_id       = item_raw.get("id")
    nombre        = item_raw.get("title", "Producto sin nombre")
    precio_actual = item_raw.get("price", 0)
    precio_orig   = item_raw.get("original_price") or precio_actual
    permalink     = item_raw.get("permalink", "")
    stock_raw     = item_raw.get("available_quantity", 0)
    thumbnail     = item_raw.get("thumbnail", "")

    if not precio_actual or precio_actual <= 0:
        return None

    # ── Guardar en base de datos ──────────────────────
    producto_id = upsert_producto(
        url=permalink,
        tienda="mercadolibre",
        nombre=nombre,
        categoria=categoria["nombre"],
        sku=item_id
    )

    # Obtener detalles completos para stock real
    detalle = get_detalle_item(item_id)
    if detalle:
        stock_raw    = detalle.get("available_quantity", stock_raw)
        precio_actual = detalle.get("price", precio_actual)
        precio_orig   = detalle.get("original_price") or precio_orig

    guardar_precio(
        producto_id=producto_id,
        precio=precio_actual,
        precio_original=precio_orig,
        stock=stock_raw,
        disponible=(stock_raw > 0)
    )

    # ── Verificaciones previas ────────────────────────

    # No enviar si ya mandamos alerta hoy
    if alerta_ya_enviada_hoy(producto_id):
        return None

    # No enviar si no hay stock
    if stock_raw <= 0:
        return None

    # ── Calcular descuento vs mínimo histórico real ───
    minimo_historico = get_minimo_historico(producto_id)

    if minimo_historico is None:
        # Primera vez que vemos este producto, solo guardamos
        # No enviamos alerta todavía — necesitamos historial
        logger.info(f"[NUEVO] {nombre[:50]} — acumulando historial")
        return None

    # Si el precio actual es mayor o igual al mínimo histórico,
    # no es una oferta real
    if precio_actual >= minimo_historico:
        return None

    descuento_real = (minimo_historico - precio_actual) / minimo_historico

    # ── Filtro anti-inflación ─────────────────────────
    if detectar_inflacion_previa(producto_id):
        logger.info(f"[INFLACIÓN DETECTADA] {nombre[:50]} — descartada")
        return None

    # ── Calcular Heat Score ───────────────────────────
    score = calcular_heat_score(
        descuento_real=descuento_real,
        stock=stock_raw,
        categoria=categoria["nombre"],
        precio_actual=precio_actual,
        precio_original=precio_orig
    )

    logger.info(
        f"[ITEM] {nombre[:45]} | "
        f"${precio_actual:,.0f} (−{descuento_real*100:.0f}%) | "
        f"Score: {score}/10"
    )

    return {
        "producto_id":    producto_id,
        "item_id":        item_id,
        "nombre":         nombre,
        "precio_actual":  precio_actual,
        "precio_original":precio_orig,
        "precio_minimo":  minimo_historico,
        "descuento_real": descuento_real,
        "stock":          stock_raw,
        "categoria":      categoria,
        "permalink":      permalink,
        "thumbnail":      thumbnail,
        "heat_score":     score,
    }


# ─────────────────────────────────────────────
#  CICLO COMPLETO DE SCRAPING
# ─────────────────────────────────────────────

def ejecutar_ciclo() -> list:
    """
    Ejecuta un ciclo completo de monitoreo:
    - Revisa todas las categorías configuradas
    - Retorna lista de alertas ordenadas por heat_score
    """
    logger.info("=" * 50)
    logger.info(f"[CICLO] Iniciando — {datetime.now().strftime('%H:%M:%S')}")

    alertas = []

    for categoria in CATEGORIAS_ML:
        logger.info(f"[CAT] {categoria['emoji']} {categoria['nombre']}")
        items_procesados = 0

        # Paginamos hasta MAX_ITEMS_POR_CATEGORIA
        for offset in range(0, MAX_ITEMS_POR_CATEGORIA, 50):
            items_raw = buscar_items_categoria(categoria["id"], offset)

            if not items_raw:
                break

            for item_raw in items_raw:
                resultado = procesar_item(item_raw, categoria)
                if resultado and resultado["heat_score"] >= 5:
                    alertas.append(resultado)
                items_procesados += 1

                if items_procesados >= MAX_ITEMS_POR_CATEGORIA:
                    break

            if items_procesados >= MAX_ITEMS_POR_CATEGORIA:
                break

        logger.info(
            f"[CAT] {categoria['nombre']}: "
            f"{items_procesados} items revisados"
        )

    # Ordenar por heat_score descendente
    alertas.sort(key=lambda x: x["heat_score"], reverse=True)

    logger.info(f"[CICLO] Terminado — {len(alertas)} alertas generadas")
    logger.info("=" * 50)

    return alertas
