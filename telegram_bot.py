# =============================================================
# DROPNODE MX — telegram_bot.py
# Publica alertas en los canales de Telegram
# Formato distinto para canal Free vs VIP
# =============================================================

import requests
import logging
import urllib.parse
from datetime import datetime
from config import (
    TELEGRAM_TOKEN, CHANNEL_FREE_ID,
    CHANNEL_VIP_ID, ML_AFFILIATE_ID, AMAZON_TAG,
    HORA_INICIO_ENVIOS, HORA_FIN_ENVIOS
)
from heat_score import interpretar_score
from database import guardar_alerta

logger = logging.getLogger(__name__)

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


# ─────────────────────────────────────────────
#  HORARIO DE ENVÍO
# ─────────────────────────────────────────────

def dentro_de_horario() -> bool:
    """Verifica que estemos en el horario de operación."""
    hora = datetime.now().hour
    return HORA_INICIO_ENVIOS <= hora < HORA_FIN_ENVIOS


# ─────────────────────────────────────────────
#  GENERACIÓN DE LINKS DE AFILIADO
# ─────────────────────────────────────────────

def link_afiliado_ml(url: str, item_id: str) -> str:
    """
    Genera link de afiliado para Mercado Libre.
    Formato oficial del programa de afiliados ML.
    """
    if not ML_AFFILIATE_ID:
        return url

    # Parámetros de tracking estándar de ML Afiliados
    base = "https://go.mercadolibre.com.mx"
    params = urllib.parse.urlencode({
        "as_src":        "affiliate",
        "as_plataforma": "telegram",
        "as_campaign":   "dropnodemx",
        "as_content":    item_id,
        "url":           url,
        "affiliate_id":  ML_AFFILIATE_ID,
    })
    return f"{base}?{params}"


def link_afiliado_amazon(url: str) -> str:
    """Agrega tag de afiliado Amazon si está configurado."""
    if not AMAZON_TAG:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}tag={AMAZON_TAG}"


# ─────────────────────────────────────────────
#  FORMATEO DE MENSAJES
# ─────────────────────────────────────────────

def formatear_mensaje_vip(alerta: dict) -> str:
    """
    Mensaje para canal VIP — más detallado, urgente, con tips de flip.
    """
    interp      = interpretar_score(alerta["heat_score"])
    nombre      = alerta["nombre"][:60]
    precio_act  = alerta["precio_actual"]
    precio_min  = alerta["precio_minimo"]
    precio_orig = alerta["precio_original"]
    descuento   = alerta["descuento_real"] * 100
    stock       = alerta["stock"]
    cat_emoji   = alerta["categoria"]["emoji"]
    link        = link_afiliado_ml(alerta["permalink"], alerta["item_id"])
    score       = alerta["heat_score"]

    # Calcular precio de reventa estimado (10-20% sobre precio normal)
    reventa_low  = precio_min * 0.85
    reventa_high = precio_min * 0.95

    # Stock urgency text
    if stock == 1:
        stock_txt = "⚠️ *¡ÚLTIMA UNIDAD!*"
    elif stock <= 3:
        stock_txt = f"⚠️ *Solo {stock} unidades*"
    elif stock <= 10:
        stock_txt = f"📦 {stock} unidades disponibles"
    else:
        stock_txt = f"📦 Stock disponible"

    msg = f"""{interp['emoji']} *{interp['etiqueta']}* — {cat_emoji} {alerta['categoria']['nombre']}

📦 {nombre}

💰 Precio actual: *${precio_act:,.0f} MXN*
📉 Mínimo histórico: ${precio_min:,.0f} MXN
🔥 Caída real: *−{descuento:.0f}%*
{stock_txt}
🎯 Heat Score: {score}/10

🔗 [COMPRAR AHORA]({link})

💡 _Rango de reventa estimado: ${reventa_low:,.0f}–${reventa_high:,.0f} MXN_

⏰ Detectado: {datetime.now().strftime('%H:%M:%S')}"""

    return msg


def formatear_mensaje_free(alerta: dict) -> str:
    """
    Mensaje para canal público — más simple, con CTA al VIP.
    """
    interp     = interpretar_score(alerta["heat_score"])
    nombre     = alerta["nombre"][:60]
    precio_act = alerta["precio_actual"]
    precio_min = alerta["precio_minimo"]
    descuento  = alerta["descuento_real"] * 100
    cat_emoji  = alerta["categoria"]["emoji"]
    link       = link_afiliado_ml(alerta["permalink"], alerta["item_id"])

    msg = f"""{interp['emoji']} *{interp['etiqueta']}* {cat_emoji}

{nombre}

💰 *${precio_act:,.0f} MXN* _(−{descuento:.0f}% vs mínimo histórico)_
📉 Antes: ${precio_min:,.0f} MXN

[Ver oferta →]({link})

🔒 _Las alertas como esta llegan al canal VIP con varios minutos de ventaja._"""

    return msg


def formatear_mensaje_productos_financieros() -> str:
    """
    Mensaje periódico de productos financieros (Plata Card, etc.)
    Se envía automáticamente cada 7 días al canal free.
    """
    msg = """💳 *Mientras esperas la próxima alerta...*

¿Ya tienes tu tarjeta sin anualidad?

🔷 *Plata Card* — Sin anualidad, cashback real
🔷 *Nu (Nubank MX)* — Tarjeta de crédito sin comisiones
🔷 *GBM+* — Invierte desde $100 MXN

💡 Usarlos para tus compras de ofertas = doble beneficio: descuento + recompensa.

_Nuestro equipo los usa. Los recomendamos porque funcionan._"""
    return msg


# ─────────────────────────────────────────────
#  ENVÍO DE MENSAJES
# ─────────────────────────────────────────────

def enviar_mensaje(chat_id: int, texto: str,
                   parse_mode: str = "Markdown",
                   preview: bool = False) -> int | None:
    """
    Envía un mensaje a un canal/grupo de Telegram.
    Retorna el message_id si fue exitoso.
    """
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id":                  chat_id,
        "text":                     texto,
        "parse_mode":               parse_mode,
        "disable_web_page_preview": not preview,
    }

    try:
        resp = requests.post(url, json=payload, timeout=15)
        data = resp.json()

        if data.get("ok"):
            msg_id = data["result"]["message_id"]
            logger.info(f"[TELEGRAM ✓] chat={chat_id} | msg_id={msg_id}")
            return msg_id
        else:
            logger.error(f"[TELEGRAM ✗] {data.get('description', 'Error desconocido')}")
            return None

    except Exception as e:
        logger.error(f"[TELEGRAM ERROR] {e}")
        return None


def enviar_alerta(alerta: dict) -> bool:
    """
    Función principal: decide a qué canal enviar y ejecuta.
    """
    if not dentro_de_horario():
        logger.info(f"[FUERA DE HORARIO] {datetime.now().hour}h — alerta guardada para después")
        return False

    score  = alerta["heat_score"]
    interp = interpretar_score(score)
    canal  = interp["canal"]

    if canal == "descartar":
        return False

    msg_id = None

    if canal == "vip":
        # 1. Enviamos primero al VIP (ventaja de tiempo)
        texto_vip = formatear_mensaje_vip(alerta)
        msg_id = enviar_mensaje(CHANNEL_VIP_ID, texto_vip)

        # 2. Si el score también aplica para free (≥5), lo mandamos después
        if score >= 5:
            import time
            time.sleep(2)  # Pequeña pausa para asegurar orden
            texto_free = formatear_mensaje_free(alerta)
            enviar_mensaje(CHANNEL_FREE_ID, texto_free)

    elif canal == "free":
        texto_free = formatear_mensaje_free(alerta)
        msg_id = enviar_mensaje(CHANNEL_FREE_ID, texto_free)

    # Registrar en base de datos para auto-learning
    if msg_id:
        guardar_alerta(
            producto_id=alerta["producto_id"],
            heat_score=score,
            canal=canal,
            precio_alerta=alerta["precio_actual"],
            descuento_real=alerta["descuento_real"],
            msg_id=msg_id
        )

    return msg_id is not None


def enviar_resumen_diario(total_alertas: int,
                           total_vip: int,
                           total_free: int):
    """
    Envía resumen al canal VIP cada día a las 10 PM.
    """
    msg = f"""📊 *Resumen del día — DropNode MX*

🚨 Alertas VIP enviadas: *{total_vip}*
⚡ Alertas Free enviadas: *{total_free}*
🔍 Total oportunidades analizadas: *{total_alertas}*

_El equipo nunca descansa. Mañana más._"""

    enviar_mensaje(CHANNEL_VIP_ID, msg)
