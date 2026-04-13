# =============================================================
# DROPNODE MX — telegram_bot.py  (version final)
# Publica alertas, mensajes financieros, recordatorios VIP
# y resumen diario con datos reales en ambos canales
# =============================================================

import requests
import logging
import urllib.parse
from datetime import datetime
from config import (
    TELEGRAM_TOKEN, CHANNEL_FREE_ID, CHANNEL_VIP_ID, GROUP_ID,
    ML_AFFILIATE_ID, AMAZON_TAG, LAUNCHPASS_LINK,
    HORA_INICIO_ENVIOS, HORA_FIN_ENVIOS,
    PRODUCTOS_FINANCIEROS
)
from heat_score import interpretar_score
from database import guardar_alerta

logger       = logging.getLogger(__name__)
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


# ─────────────────────────────────────────────
#  HORARIO
# ─────────────────────────────────────────────

def dentro_de_horario():
    hora = datetime.now().hour
    return HORA_INICIO_ENVIOS <= hora < HORA_FIN_ENVIOS


# ─────────────────────────────────────────────
#  LINKS DE AFILIADO
# ─────────────────────────────────────────────

def link_afiliado_ml(url, item_id):
    if not ML_AFFILIATE_ID:
        return url
    params = urllib.parse.urlencode({
        "as_src":       "affiliate",
        "as_campaign":  "dropnodemx",
        "as_content":   item_id,
        "url":          url,
        "affiliate_id": ML_AFFILIATE_ID,
    })
    return f"https://go.mercadolibre.com.mx?{params}"


def link_afiliado_amazon(url):
    if not AMAZON_TAG:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}tag={AMAZON_TAG}"


def link_afiliado_auto(url, item_id=""):
    """Detecta la tienda y aplica el afiliado correcto."""
    if "mercadolibre" in url:
        return link_afiliado_ml(url, item_id)
    elif "amazon.com.mx" in url or "amazon.mx" in url:
        return link_afiliado_amazon(url)
    return url


# ─────────────────────────────────────────────
#  FORMATO DE ALERTAS
# ─────────────────────────────────────────────

def formatear_mensaje_vip(alerta):
    interp    = interpretar_score(alerta["heat_score"])
    nombre    = alerta["nombre"][:60]
    p_act     = alerta["precio_actual"]
    p_ref     = alerta["precio_minimo"]
    descuento = alerta["descuento_real"] * 100
    stock     = alerta["stock"]
    emoji_cat = alerta["categoria"]["emoji"]
    nombre_cat= alerta["categoria"]["nombre"]
    link      = link_afiliado_auto(alerta["permalink"], alerta["item_id"])
    score     = alerta["heat_score"]
    es_frio   = alerta.get("modo_frio", False)
    ref_label = "Precio tachado" if es_frio else "Minimo historico"

    if stock == 1:
        stock_txt = "⚠️ *¡ULTIMA UNIDAD!*"
    elif stock <= 3:
        stock_txt = f"⚠️ *Solo {stock} unidades*"
    elif stock <= 10:
        stock_txt = f"📦 {stock} unidades"
    else:
        stock_txt = "📦 Stock disponible"

    reventa_low  = p_ref * 0.80
    reventa_high = p_ref * 0.92

    return (
        f"{interp['emoji']} *{interp['etiqueta']}*"
        f" — {emoji_cat} {nombre_cat}\n\n"
        f"📦 {nombre}\n\n"
        f"💰 Precio ahora: *${p_act:,.0f} MXN*\n"
        f"📉 {ref_label}: ${p_ref:,.0f} MXN\n"
        f"🔥 Caida real: *−{descuento:.0f}%*\n"
        f"{stock_txt}\n"
        f"🎯 Score: {score}/10\n\n"
        f"🔗 [COMPRAR AHORA]({link})\n\n"
        f"💡 _Reventa estimada: ${reventa_low:,.0f}–${reventa_high:,.0f} MXN_\n"
        f"⏰ _{datetime.now().strftime('%H:%M:%S')}_"
    )


def formatear_mensaje_free(alerta):
    interp    = interpretar_score(alerta["heat_score"])
    nombre    = alerta["nombre"][:60]
    p_act     = alerta["precio_actual"]
    p_ref     = alerta["precio_minimo"]
    descuento = alerta["descuento_real"] * 100
    emoji_cat = alerta["categoria"]["emoji"]
    link      = link_afiliado_auto(alerta["permalink"], alerta["item_id"])

    return (
        f"{interp['emoji']} *{interp['etiqueta']}* {emoji_cat}\n\n"
        f"{nombre}\n\n"
        f"💰 *${p_act:,.0f} MXN* _(−{descuento:.0f}%)_\n"
        f"📉 Ref: ${p_ref:,.0f} MXN\n\n"
        f"[Ver oferta →]({link})\n\n"
        f"🔒 _Canal VIP recibe estas alertas primero._\n"
        f"_{LAUNCHPASS_LINK}_"
    )


# ─────────────────────────────────────────────
#  MENSAJES PERIODICOS AUTOMATICOS
# ─────────────────────────────────────────────

def formatear_mensaje_financiero():
    """Rota entre productos financieros activos segun el dia del mes."""
    activos = [p for p in PRODUCTOS_FINANCIEROS if p["activo"]]
    if not activos:
        return None
    prod = activos[datetime.now().day % len(activos)]
    return (
        f"{prod['emoji']} *{prod['nombre']}*\n\n"
        f"{prod['descripcion']}\n\n"
        f"✅ {prod['beneficio']}\n\n"
        f"🔗 [Conocer mas]({prod['link']})\n\n"
        f"_Recomendado por DropNode MX — nuestro equipo lo usa._"
    )


def formatear_recordatorio_vip():
    """Rota entre 3 versiones para no repetirse."""
    versiones = [
        (
            "🔒 *¿Aun no estas en el canal VIP?*\n\n"
            "Las alertas de errores de precio llegan ahi primero.\n"
            "Un solo error de precio bien aprovechado paga meses de acceso.\n\n"
            f"👉 {LAUNCHPASS_LINK}"
        ),
        (
            "⚡ *Mientras lees esto...*\n\n"
            "En el canal VIP ya hay alertas de stock critico esperando.\n"
            "Las mejores oportunidades no esperan.\n\n"
            f"🔗 {LAUNCHPASS_LINK}"
        ),
        (
            "📊 *Canal VIP DropNode MX*\n\n"
            "Errores de precio · Stock limitado · Liquidaciones\n"
            "Todo antes que el canal publico.\n\n"
            f"$299 MXN/mes — cancela cuando quieras\n"
            f"👉 {LAUNCHPASS_LINK}"
        ),
    ]
    idx = (datetime.now().day + datetime.now().hour) % len(versiones)
    return versiones[idx]


def mensaje_bienvenida_grupo():
    """Mensaje para fijar en el grupo Community."""
    return (
        "👋 *Bienvenido a DropNode Community MX*\n\n"
        "Aqui compartimos los mejores descuentos que nuestro equipo encuentra.\n\n"
        "📢 *Canal de alertas gratuito:* @DropNodeMX\n"
        f"🔒 *Canal VIP (errores de precio):* {LAUNCHPASS_LINK}\n\n"
        "📌 *Reglas del grupo:*\n"
        "• Comparte ofertas reales que hayas encontrado\n"
        "• Sin spam ni publicidad no solicitada\n"
        "• Respeta a todos los miembros\n\n"
        "_DropNode MX — Siempre encontramos el mejor precio._"
    )


# ─────────────────────────────────────────────
#  RESUMEN DIARIO (mejorado con datos reales)
# ─────────────────────────────────────────────

def calcular_ahorro_estimado(alertas):
    total = 0.0
    for a in alertas:
        precio     = a.get("precio_alerta", 0)
        descuento  = a.get("descuento_real", 0)
        if precio and descuento and descuento < 1:
            precio_original = precio / (1 - descuento)
            total += (precio_original - precio)
    return total


def enviar_resumen_diario(total_vip=0, total_free=0):
    from database import get_metricas_autolearning

    alertas_hoy = []
    try:
        todas       = get_metricas_autolearning()
        hoy         = str(datetime.now().date())
        alertas_hoy = [a for a in todas
                       if a.get("timestamp", "")[:10] == hoy]
    except Exception:
        pass

    total_ops  = total_vip + total_free
    ahorro_est = calcular_ahorro_estimado(alertas_hoy)
    mejor_desc = 0.0
    if alertas_hoy:
        mejor_desc = max(
            a.get("descuento_real", 0) for a in alertas_hoy
        ) * 100

    # Mensaje VIP — detallado
    msg_vip = (
        f"📊 *Resumen ultimas 24 hrs — DropNode MX VIP*\n\n"
        f"🚨 Alertas exclusivas VIP: *{total_vip}*\n"
        f"⚡ Alertas canal publico: *{total_free}*\n"
        f"🔍 Oportunidades analizadas: *{total_ops}*\n"
    )
    if mejor_desc > 0:
        msg_vip += f"🔥 Mejor descuento del dia: *−{mejor_desc:.0f}%*\n"
    if ahorro_est > 0:
        msg_vip += f"💰 Ahorro acumulado estimado: *~${ahorro_est:,.0f} MXN*\n"
    msg_vip += (
        f"\n_Nuestro equipo sigue actualizando constantemente._\n"
        f"_Las mejores oportunidades de manana ya estan siendo monitoreadas._"
    )

    # Mensaje Free — corto con CTA
    msg_free = (
        f"📊 *Resumen del dia — DropNode MX*\n\n"
        f"⚡ Oportunidades encontradas: *{total_ops}*\n"
    )
    if ahorro_est > 0:
        msg_free += f"💰 Ahorro estimado del canal: *~${ahorro_est:,.0f} MXN*\n"
    msg_free += (
        f"\n_Nuestro equipo sigue monitoreando. Manana mas._\n\n"
        f"🔒 *Acceso VIP — alertas antes que nadie*\n"
        f"_{LAUNCHPASS_LINK}_"
    )

    enviar_mensaje(CHANNEL_VIP_ID, msg_vip)
    enviar_mensaje(CHANNEL_FREE_ID, msg_free)


# ─────────────────────────────────────────────
#  ENVIO DE MENSAJES A TELEGRAM
# ─────────────────────────────────────────────

def enviar_mensaje(chat_id, texto, preview=False):
    url     = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id":                  chat_id,
        "text":                     texto,
        "parse_mode":               "Markdown",
        "disable_web_page_preview": not preview,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        data = resp.json()
        if data.get("ok"):
            msg_id = data["result"]["message_id"]
            logger.info(f"[TG OK] chat={chat_id} msg={msg_id}")
            return msg_id
        else:
            logger.error(f"[TG ERR] {data.get('description', '?')}")
            return None
    except Exception as e:
        logger.error(f"[TG EXC] {e}")
        return None


def fijar_mensaje(chat_id, message_id):
    """Fija un mensaje en el canal o grupo."""
    requests.post(
        f"{TELEGRAM_API}/pinChatMessage",
        json={"chat_id": chat_id, "message_id": message_id},
        timeout=10
    )


def enviar_y_fijar_bienvenida_grupo():
    """Envia y fija el mensaje de bienvenida. Solo se llama una vez."""
    texto  = mensaje_bienvenida_grupo()
    msg_id = enviar_mensaje(GROUP_ID, texto)
    if msg_id:
        fijar_mensaje(GROUP_ID, msg_id)
        logger.info(f"[BIENVENIDA] Fijada en grupo (msg_id={msg_id})")


# ─────────────────────────────────────────────
#  FUNCIONES PUBLICAS PARA main.py
# ─────────────────────────────────────────────

def enviar_alerta(alerta):
    if not dentro_de_horario():
        return False

    interp = interpretar_score(alerta["heat_score"])
    canal  = interp["canal"]
    if canal == "descartar":
        return False

    msg_id = None
    if canal == "vip":
        msg_id = enviar_mensaje(CHANNEL_VIP_ID,
                                formatear_mensaje_vip(alerta))
        if alerta["heat_score"] >= 5:
            import time; time.sleep(3)
            enviar_mensaje(CHANNEL_FREE_ID,
                           formatear_mensaje_free(alerta))
    else:
        msg_id = enviar_mensaje(CHANNEL_FREE_ID,
                                formatear_mensaje_free(alerta))

    if msg_id:
        guardar_alerta(
            producto_id=alerta["producto_id"],
            heat_score=alerta["heat_score"],
            canal=canal,
            precio_alerta=alerta["precio_actual"],
            descuento_real=alerta["descuento_real"],
            msg_id=msg_id
        )
    return msg_id is not None


def enviar_mensaje_financiero():
    texto = formatear_mensaje_financiero()
    if texto:
        enviar_mensaje(CHANNEL_FREE_ID, texto)
        logger.info("[FINANCIERO] Publicado")


def enviar_recordatorio_vip():
    if not LAUNCHPASS_LINK:
        return
    enviar_mensaje(CHANNEL_FREE_ID, formatear_recordatorio_vip())
    logger.info("[VIP CTA] Publicado")
