# =============================================================
# DROPNODE MX — peticiones.py
# Gestiona peticiones de la comunidad:
#   - Guarda en Supabase lo que la gente pide
#   - Detecta cuando un scraper encuentra un match
#   - Dispara alerta VIP con tag "Pedido por la comunidad"
#   - Dispara FOMO en canal free sin revelar el producto
#
# SQL a ejecutar en Supabase ANTES de usar este módulo:
# ─────────────────────────────────────────────────────
# CREATE TABLE IF NOT EXISTS peticiones (
#     id          BIGSERIAL PRIMARY KEY,
#     texto       TEXT NOT NULL,
#     user_id     BIGINT,
#     username    TEXT,
#     semana      INT,
#     timestamp   TIMESTAMPTZ DEFAULT NOW(),
#     procesada   BOOLEAN DEFAULT FALSE,
#     encontrada  BOOLEAN DEFAULT FALSE,
#     producto    TEXT,
#     producto_url TEXT
# );
# ─────────────────────────────────────────────────────
# =============================================================

import os
import re
import logging
import requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# ── Configuración ──────────────────────────────────────────

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHANNEL_FREE_ID  = int(os.environ.get("CHANNEL_FREE_ID", "0"))
CHANNEL_VIP_ID   = int(os.environ.get("CHANNEL_VIP_ID", "0"))
LAUNCHPASS_LINK  = os.environ.get("LAUNCHPASS_LINK", "").strip()
SUPABASE_URL     = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY     = os.environ.get("SUPABASE_KEY", "").strip()

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TZ_MEXICO    = timezone(timedelta(hours=-6))

# ── Estado en memoria ──────────────────────────────────────
# Persiste mientras Railway no reinicia (suficiente para la ventana del lunes)

_ventana_abierta          = False   # True durante la ventana de peticiones del lunes
_primera_respuesta_acusada = False  # Para enviar el "gracias, seguimos leyendo" solo una vez
_peticiones_semana         = []     # Cache temporal de textos recibidos esta semana


def _db():
    """Retorna cliente Supabase o None si no está disponible."""
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


def _semana_actual() -> int:
    return datetime.now(TZ_MEXICO).isocalendar()[1]


def _hora_mx():
    return datetime.now(TZ_MEXICO)


# ── API pública del módulo ─────────────────────────────────

def abrir_ventana():
    """
    Llamar cuando se envía la pregunta del lunes.
    Activa la recepción de peticiones hasta las 14:00 MX.
    """
    global _ventana_abierta, _primera_respuesta_acusada, _peticiones_semana
    _ventana_abierta           = True
    _primera_respuesta_acusada = False
    _peticiones_semana         = []
    logger.info("[PETICIONES] Ventana abierta")


def cerrar_ventana():
    global _ventana_abierta
    _ventana_abierta = False
    logger.info("[PETICIONES] Ventana cerrada")


def ventana_activa() -> bool:
    """
    La ventana se cierra automáticamente a las 14:00 MX
    aunque no se llame cerrar_ventana() explícitamente.
    """
    if not _ventana_abierta:
        return False
    hora = _hora_mx()
    if hora.weekday() != 0 or hora.hour >= 14:
        cerrar_ventana()
        return False
    return True


def procesar_posible_peticion(message: dict) -> bool:
    """
    Analiza un mensaje del grupo y, si la ventana está activa
    y parece una petición real, lo guarda.
    Retorna True si fue guardado como petición.
    """
    global _primera_respuesta_acusada, _peticiones_semana

    if not ventana_activa():
        return False

    texto = message.get("text", "").strip()
    user  = message.get("from", {})

    # Ignorar bots, mensajes vacíos y mensajes muy cortos
    if user.get("is_bot") or not texto or len(texto) < 3:
        return False

    # Ignorar comandos y links
    if texto.startswith("/") or "http" in texto.lower():
        return False

    user_id  = user.get("id")
    username = user.get("username") or user.get("first_name", "")

    # Guardar en memoria
    _peticiones_semana.append(texto)

    # Guardar en Supabase (no bloqueante — falla silenciosamente)
    _guardar_en_db(texto, user_id, username)

    # Enviar "gracias, seguimos leyendo" solo en la PRIMERA respuesta
    if not _primera_respuesta_acusada:
        _primera_respuesta_acusada = True
        _enviar_acuse_inicial()

    return True


def enviar_resumen_peticiones():
    """
    Envía UN solo mensaje de agradecimiento con el conteo total.
    Llamar a las 14:00 MX del lunes.
    """
    n = _contar_peticiones_semana()
    if n == 0:
        return

    texto = (
        f"📝 <b>Recibimos {n} sugerencias esta semana.</b>\n\n"
        "Nuestro equipo ya las tiene en el radar.\n"
        "Los primeros resultados aparecen en el Canal VIP antes que aqui."
    )
    payload = {
        "chat_id":                  _get_group_id(),
        "text":                     texto,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }
    if LAUNCHPASS_LINK:
        payload["reply_markup"] = {
            "inline_keyboard": [[{
                "text": "📲 Ver resultados en Canal VIP",
                "url":  LAUNCHPASS_LINK
            }]]
        }
    _enviar(payload)
    cerrar_ventana()
    logger.info(f"[PETICIONES] Resumen enviado — {n} peticiones")


def verificar_match(nombre_producto: str, url_producto: str, precio: float) -> bool:
    """
    Compara el nombre del producto encontrado contra las peticiones
    pendientes de la semana. Si hay match, dispara las alertas y retorna True.
    Llamar desde los scrapers después de encontrar un item.
    """
    pendientes = _get_peticiones_pendientes()
    if not pendientes:
        return False

    nombre_lower = nombre_producto.lower()
    keywords_producto = set(_tokenizar(nombre_lower))

    for peticion in pendientes:
        keywords_peticion = set(_tokenizar(peticion["texto"].lower()))
        # Match si al menos 2 palabras relevantes coinciden
        comunes = keywords_producto & keywords_peticion
        if len(comunes) >= 2 or (len(keywords_peticion) == 1 and keywords_peticion & keywords_producto):
            logger.info(f"[PETICIONES] Match: '{peticion['texto']}' → '{nombre_producto[:50]}'")
            _disparar_alertas(peticion, nombre_producto, url_producto, precio)
            _marcar_encontrada(peticion["id"], nombre_producto, url_producto)
            return True

    return False


def get_peticiones_como_keywords() -> list:
    """
    Retorna lista de strings con las peticiones de la semana
    para que los scrapers las usen como queries adicionales.
    """
    pendientes = _get_peticiones_pendientes()
    return [p["texto"] for p in pendientes]


# ── Funciones internas ─────────────────────────────────────

def _get_group_id():
    """Lee GROUP_ID del entorno para evitar import circular."""
    try:
        return int(os.environ.get("GROUP_ID", "0"))
    except Exception:
        return 0


def _tokenizar(texto: str) -> list:
    """Extrae palabras relevantes de 4+ letras."""
    palabras_ignorar = {
        "para", "quiero", "busco", "algo", "como", "que", "una",
        "unos", "unas", "este", "esta", "buen", "buena", "precio",
        "barato", "barata", "oferta", "descuento", "tiene", "tiene",
        "favor", "algun", "alguna", "donde", "cual", "cuando"
    }
    return [w for w in re.findall(r'[a-záéíóúñ]{4,}', texto.lower())
            if w not in palabras_ignorar]


def _enviar_acuse_inicial():
    """
    UN solo mensaje cuando llega la primera petición del lunes.
    Informal, cálido, no spam.
    """
    _enviar({
        "chat_id":    _get_group_id(),
        "text":       "Gracias a todos los que están respondiendo 👀\nSeguimos leyendo hasta el mediodía.",
        "parse_mode": "HTML",
    })


def _guardar_en_db(texto: str, user_id: int, username: str):
    db = _db()
    if not db:
        return
    try:
        db.table("peticiones").insert({
            "texto":    texto[:200],
            "user_id":  user_id,
            "username": username,
            "semana":   _semana_actual(),
        }).execute()
    except Exception as e:
        logger.warning(f"[PETICIONES] DB insert: {e}")


def _contar_peticiones_semana() -> int:
    # Primero intenta DB, fallback a memoria
    db = _db()
    if db:
        try:
            r = db.table("peticiones").select("id", count="exact").eq(
                "semana", _semana_actual()
            ).execute()
            return r.count or len(_peticiones_semana)
        except Exception:
            pass
    return len(_peticiones_semana)


def _get_peticiones_pendientes() -> list:
    db = _db()
    if not db:
        # Fallback: convertir cache en memoria a formato dict
        return [{"id": None, "texto": t} for t in _peticiones_semana]
    try:
        r = db.table("peticiones").select("id, texto").eq(
            "semana", _semana_actual()
        ).eq("encontrada", False).eq("procesada", False).execute()
        return r.data or []
    except Exception:
        return [{"id": None, "texto": t} for t in _peticiones_semana]


def _marcar_encontrada(peticion_id, producto: str, url: str):
    if not peticion_id:
        return
    db = _db()
    if not db:
        return
    try:
        db.table("peticiones").update({
            "encontrada":   True,
            "procesada":    True,
            "producto":     producto[:200],
            "producto_url": url,
        }).eq("id", peticion_id).execute()
    except Exception as e:
        logger.warning(f"[PETICIONES] DB update: {e}")


def _disparar_alertas(peticion: dict, nombre: str, url: str, precio: float):
    """
    VIP: alerta completa con tag 'Pedido por la comunidad'.
    Free: FOMO sin revelar el producto.
    """
    # ── Alerta VIP ──
    msg_vip = (
        f"🎯 *Pedido por la comunidad — encontrado*\n\n"
        f"*{nombre[:65]}*\n\n"
        f"*${precio:,.0f} MXN*\n\n"
        f"[COMPRAR AHORA]({url})"
    )
    _enviar({
        "chat_id":                  CHANNEL_VIP_ID,
        "text":                     msg_vip,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": True,
    })

    # ── FOMO en free ──
    # Categoría genérica para no revelar el producto exacto
    categoria = _inferir_categoria(nombre)
    msg_free_texto = (
        f"🎯 <b>La comunidad lo pidió — nuestro equipo lo encontró.</b>\n\n"
        f"Alguien esta semana buscaba <i>{categoria}</i>.\n"
        f"El resultado ya está en el Canal VIP.\n\n"
        f"<i>Los miembros VIP lo reciben antes.</i>"
    )
    payload_free = {
        "chat_id":                  CHANNEL_FREE_ID,
        "text":                     msg_free_texto,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }
    if LAUNCHPASS_LINK:
        payload_free["reply_markup"] = {
            "inline_keyboard": [[{
                "text": "📲 Ver en Canal VIP",
                "url":  LAUNCHPASS_LINK
            }]]
        }
    _enviar(payload_free)


def _inferir_categoria(nombre: str) -> str:
    """Convierte el nombre del producto en una categoría vaga para el FOMO."""
    n = nombre.lower()
    if any(w in n for w in ["iphone", "samsung", "celular", "smartphone", "redmi", "xiaomi"]):
        return "un celular con buena oferta"
    if any(w in n for w in ["laptop", "lenovo", "dell", "hp", "asus", "macbook"]):
        return "una laptop con descuento"
    if any(w in n for w in ["tv", "televisor", "smart tv", "oled", "qled"]):
        return "un televisor en oferta"
    if any(w in n for w in ["audifonos", "airpods", "sony wh", "beats"]):
        return "audífonos con precio bajo"
    if any(w in n for w in ["consola", "playstation", "xbox", "nintendo"]):
        return "una consola o videojuego"
    if any(w in n for w in ["tablet", "ipad"]):
        return "una tablet en oferta"
    return "un producto que estaban buscando"


def _enviar(payload: dict):
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=15)
    except Exception as e:
        logger.error(f"[PETICIONES] Envío: {e}")