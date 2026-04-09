# =============================================================
# DROPNODE MX — database.py
# Todas las operaciones con Supabase
# =============================================================

from supabase import create_client, Client
from datetime import datetime, timedelta
from config import SUPABASE_URL, SUPABASE_KEY, DIAS_HISTORIAL
import logging

logger = logging.getLogger(__name__)

# Conexión única reutilizable
_client: Client = None

def get_client() -> Client:
    """Retorna el cliente de Supabase (singleton)."""
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


# ─────────────────────────────────────────────
#  PRODUCTOS
# ─────────────────────────────────────────────

def upsert_producto(url: str, tienda: str, nombre: str,
                    categoria: str, sku: str) -> str:
    """
    Inserta o actualiza un producto. Retorna su UUID.
    """
    db = get_client()
    data = {
        "url":       url,
        "tienda":    tienda,
        "nombre":    nombre,
        "categoria": categoria,
        "sku":       sku,
        "activo":    True,
    }
    # upsert basado en SKU único por tienda
    result = db.table("productos").upsert(
        data, on_conflict="sku,tienda"
    ).execute()

    if result.data:
        return result.data[0]["id"]

    # Si ya existe, buscarlo
    existing = db.table("productos").select("id") \
        .eq("sku", sku).eq("tienda", tienda).single().execute()
    return existing.data["id"]


def get_productos_activos() -> list:
    """Retorna todos los productos que estamos monitoreando."""
    db = get_client()
    result = db.table("productos").select("*").eq("activo", True).execute()
    return result.data or []


# ─────────────────────────────────────────────
#  HISTORIAL DE PRECIOS
# ─────────────────────────────────────────────

def guardar_precio(producto_id: str, precio: float,
                   precio_original: float, stock: int,
                   disponible: bool = True):
    """Guarda un registro de precio capturado ahora."""
    db = get_client()
    db.table("historial_precios").insert({
        "producto_id":      producto_id,
        "precio":           precio,
        "precio_original":  precio_original,
        "stock":            stock,
        "disponible":       disponible,
        "timestamp":        datetime.utcnow().isoformat(),
    }).execute()


def get_minimo_historico(producto_id: str) -> float | None:
    """
    Retorna el precio mínimo REAL de los últimos 90 días.
    Este es el valor clave para detectar caídas genuinas
    (ignora el precio tachado que puede estar inflado).
    """
    db = get_client()
    desde = (datetime.utcnow() - timedelta(days=DIAS_HISTORIAL)).isoformat()

    result = db.table("historial_precios") \
        .select("precio") \
        .eq("producto_id", producto_id) \
        .gte("timestamp", desde) \
        .eq("disponible", True) \
        .order("precio", desc=False) \
        .limit(1) \
        .execute()

    if result.data:
        return float(result.data[0]["precio"])
    return None


def get_ultimo_precio(producto_id: str) -> dict | None:
    """Retorna el registro de precio más reciente del producto."""
    db = get_client()
    result = db.table("historial_precios") \
        .select("*") \
        .eq("producto_id", producto_id) \
        .order("timestamp", desc=True) \
        .limit(1) \
        .execute()

    return result.data[0] if result.data else None


def detectar_inflacion_previa(producto_id: str) -> bool:
    """
    Detecta si el precio fue inflado artificialmente antes de
    la 'oferta'. Si hace 15 días era 20%+ más caro que hace 45 días,
    es probable que sea una oferta falsa.
    """
    db = get_client()

    def precio_hace_n_dias(n: int) -> float | None:
        desde = (datetime.utcnow() - timedelta(days=n+3)).isoformat()
        hasta = (datetime.utcnow() - timedelta(days=n-3)).isoformat()
        result = db.table("historial_precios") \
            .select("precio") \
            .eq("producto_id", producto_id) \
            .gte("timestamp", desde) \
            .lte("timestamp", hasta) \
            .order("timestamp", desc=True) \
            .limit(1) \
            .execute()
        return float(result.data[0]["precio"]) if result.data else None

    precio_45 = precio_hace_n_dias(45)
    precio_15 = precio_hace_n_dias(15)

    if precio_45 and precio_15:
        # Si el precio subió más de 20% en ese período → sospechoso
        if precio_15 > precio_45 * 1.20:
            logger.info(f"[INFLACIÓN] Producto {producto_id}: "
                        f"${precio_45:.0f} → ${precio_15:.0f} (+{((precio_15/precio_45)-1)*100:.0f}%)")
            return True

    return False


# ─────────────────────────────────────────────
#  ALERTAS ENVIADAS
# ─────────────────────────────────────────────

def guardar_alerta(producto_id: str, heat_score: int,
                   canal: str, precio_alerta: float,
                   descuento_real: float, msg_id: int = None):
    """Registra cada alerta enviada para el auto-learning."""
    db = get_client()
    db.table("alertas_enviadas").insert({
        "producto_id":    producto_id,
        "heat_score":     heat_score,
        "canal":          canal,
        "precio_alerta":  precio_alerta,
        "descuento_real": descuento_real,
        "telegram_msg_id": msg_id,
        "clicks":         0,
        "timestamp":      datetime.utcnow().isoformat(),
    }).execute()


def alerta_ya_enviada_hoy(producto_id: str) -> bool:
    """Evita mandar la misma alerta dos veces en el mismo día."""
    db = get_client()
    desde = datetime.utcnow().replace(
        hour=0, minute=0, second=0
    ).isoformat()

    result = db.table("alertas_enviadas") \
        .select("id") \
        .eq("producto_id", producto_id) \
        .gte("timestamp", desde) \
        .execute()

    return len(result.data) > 0


def get_metricas_autolearning() -> dict:
    """
    Retorna métricas agregadas para el auto-learning:
    - Qué heat scores convierten mejor
    - Qué horas generan más actividad
    - Qué categorías rinden más
    """
    db = get_client()
    desde = (datetime.utcnow() - timedelta(days=7)).isoformat()

    alertas = db.table("alertas_enviadas") \
        .select("heat_score, canal, descuento_real, clicks, timestamp") \
        .gte("timestamp", desde) \
        .execute()

    return alertas.data or []
