# =============================================================
# DROPNODE MX — database.py  v2.1
# + Estadísticas históricas completas
# + Tracking de engagement para prueba social real
# =============================================================

from supabase import create_client, Client
from datetime import datetime, timedelta
from config import SUPABASE_URL, SUPABASE_KEY, DIAS_HISTORIAL
import logging

logger = logging.getLogger(__name__)
_client: Client = None

def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ─────────────────────────────────────────────
#  PRODUCTOS
# ─────────────────────────────────────────────

def upsert_producto(url, tienda, nombre, categoria, sku) -> str:
    db = get_client()
    try:
        result = db.table("productos").upsert(
            {"url": url, "tienda": tienda, "nombre": nombre,
             "categoria": categoria, "sku": sku, "activo": True},
            on_conflict="sku,tienda"
        ).execute()
        if result.data:
            return result.data[0]["id"]
    except Exception:
        pass
    try:
        existing = db.table("productos").select("id") \
            .eq("sku", sku).eq("tienda", tienda).execute()
        if existing.data:
            return existing.data[0]["id"]
    except Exception as e:
        logger.error(f"[DB] upsert_producto: {e}")
    return None


# ─────────────────────────────────────────────
#  HISTORIAL DE PRECIOS
# ─────────────────────────────────────────────

def guardar_precio(producto_id, precio, precio_original,
                   stock, disponible=True):
    if not producto_id:
        return
    try:
        get_client().table("historial_precios").insert({
            "producto_id":     producto_id,
            "precio":          precio,
            "precio_original": precio_original,
            "stock":           stock,
            "disponible":      disponible,
            "timestamp":       datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"[DB] guardar_precio: {e}")


def get_stats_historicas(producto_id: str) -> dict:
    """
    Retorna estadísticas completas del historial de precios:
    - precio_minimo: el más bajo en 90 días
    - precio_maximo: el más alto en 90 días
    - precio_promedio: promedio de 90 días
    - dias_en_minimo: cuántos días lleva en el precio mínimo histórico
    - dias_desde_ultimo_cambio: días desde que cambió el precio
    - veces_en_oferta: cuántas veces bajó >15% en 90 días
    """
    db   = get_client()
    hace = (datetime.utcnow() - timedelta(days=DIAS_HISTORIAL)).isoformat()

    try:
        result = db.table("historial_precios") \
            .select("precio, timestamp") \
            .eq("producto_id", producto_id) \
            .gte("timestamp", hace) \
            .eq("disponible", True) \
            .order("timestamp", desc=False) \
            .execute()

        registros = result.data or []
        if not registros:
            return {}

        precios = [float(r["precio"]) for r in registros]
        min_p   = min(precios)
        max_p   = max(precios)
        avg_p   = sum(precios) / len(precios)

        # Días desde el primer registro en historial
        primer_ts = datetime.fromisoformat(
            registros[0]["timestamp"].replace("Z", ""))
        dias_historial = (datetime.utcnow() - primer_ts).days + 1

        # Días en el precio mínimo (cuántos registros tienen ese precio)
        dias_en_minimo = sum(1 for p in precios if abs(p - min_p) < min_p * 0.02)

        # Veces que bajó más del 15%
        veces_oferta = 0
        for i in range(1, len(precios)):
            if precios[i] < precios[i-1] * 0.85:
                veces_oferta += 1

        # Días desde el último cambio de precio
        ultimo_precio = precios[-1]
        dias_sin_cambio = 0
        for r in reversed(registros):
            if abs(float(r["precio"]) - ultimo_precio) > ultimo_precio * 0.01:
                break
            dias_sin_cambio += 1

        return {
            "precio_minimo":          min_p,
            "precio_maximo":          max_p,
            "precio_promedio":        avg_p,
            "dias_historial":         dias_historial,
            "dias_en_precio_actual":  dias_sin_cambio,
            "veces_en_oferta":        veces_oferta,
            "total_registros":        len(registros),
        }

    except Exception as e:
        logger.error(f"[DB] get_stats_historicas: {e}")
        return {}


def get_minimo_historico(producto_id: str) -> float | None:
    stats = get_stats_historicas(producto_id)
    return stats.get("precio_minimo")


def detectar_inflacion_previa(producto_id: str) -> bool:
    db   = get_client()
    ahora = datetime.utcnow()

    def precio_hace_n(n):
        desde = (ahora - timedelta(days=n+3)).isoformat()
        hasta = (ahora - timedelta(days=n-3)).isoformat()
        try:
            r = db.table("historial_precios").select("precio") \
                .eq("producto_id", producto_id) \
                .gte("timestamp", desde).lte("timestamp", hasta) \
                .order("timestamp", desc=True).limit(1).execute()
            return float(r.data[0]["precio"]) if r.data else None
        except Exception:
            return None

    p45 = precio_hace_n(45)
    p15 = precio_hace_n(15)
    if p45 and p15 and p15 > p45 * 1.20:
        return True
    return False


# ─────────────────────────────────────────────
#  ALERTAS Y ENGAGEMENT (prueba social real)
# ─────────────────────────────────────────────

def guardar_alerta(producto_id, heat_score, canal,
                   precio_alerta, descuento_real, msg_id=None):
    if not producto_id:
        return
    try:
        get_client().table("alertas_enviadas").insert({
            "producto_id":     producto_id,
            "heat_score":      heat_score,
            "canal":           canal,
            "precio_alerta":   precio_alerta,
            "descuento_real":  descuento_real,
            "telegram_msg_id": msg_id,
            "clicks":          0,
            "timestamp":       datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"[DB] guardar_alerta: {e}")


def alerta_ya_enviada_hoy(producto_id: str) -> bool:
    if not producto_id:
        return False
    try:
        desde = datetime.utcnow().replace(
            hour=0, minute=0, second=0).isoformat()
        r = get_client().table("alertas_enviadas").select("id") \
            .eq("producto_id", producto_id) \
            .gte("timestamp", desde).execute()
        return len(r.data) > 0
    except Exception:
        return False


def get_engagement_producto(producto_id: str) -> dict:
    """
    Retorna métricas de engagement reales del producto:
    - total_alertas: cuántas veces se ha alertado
    - total_clicks: clicks acumulados en el link
    - ultima_alerta: cuándo fue la última alerta
    - canales: en qué canales se ha publicado
    """
    try:
        r = get_client().table("alertas_enviadas") \
            .select("canal, clicks, timestamp") \
            .eq("producto_id", producto_id) \
            .execute()
        data = r.data or []
        if not data:
            return {}

        total_clicks   = sum(a.get("clicks", 0) for a in data)
        ultima_alerta  = max(a["timestamp"] for a in data)
        canales        = list(set(a["canal"] for a in data))

        return {
            "total_alertas": len(data),
            "total_clicks":  total_clicks,
            "ultima_alerta": ultima_alerta,
            "canales":       canales,
        }
    except Exception:
        return {}


def incrementar_clicks(producto_id: str):
    """Incrementa el contador de clicks cuando alguien toca el link."""
    try:
        desde = datetime.utcnow().replace(
            hour=0, minute=0, second=0).isoformat()
        r = get_client().table("alertas_enviadas").select("id, clicks") \
            .eq("producto_id", producto_id) \
            .gte("timestamp", desde) \
            .order("timestamp", desc=True).limit(1).execute()
        if r.data:
            alerta_id    = r.data[0]["id"]
            clicks_actual = r.data[0]["clicks"] or 0
            get_client().table("alertas_enviadas") \
                .update({"clicks": clicks_actual + 1}) \
                .eq("id", alerta_id).execute()
    except Exception:
        pass


def get_metricas_autolearning() -> list:
    try:
        desde = (datetime.utcnow() - timedelta(days=7)).isoformat()
        r = get_client().table("alertas_enviadas") \
            .select("heat_score, canal, descuento_real, clicks, timestamp") \
            .gte("timestamp", desde).execute()
        return r.data or []
    except Exception:
        return []
