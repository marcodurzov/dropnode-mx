# =============================================================
# DROPNODE MX — telegram_bot.py
# v1.3 — Sin caracteres especiales en mensajes
#       + Plata Card en todos los canales
#       + Moderacion automatica del grupo Community
# =============================================================

import requests
import logging
import urllib.parse
import time
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
#  REGISTRO DE ADVERTENCIAS (en memoria)
#  Formato: { user_id: cantidad_de_advertencias }
#  Se reinicia cuando el bot se reinicia.
#  Para persistencia futura: mover a Supabase.
# ─────────────────────────────────────────────
advertencias = {}

# Links que el bot considera spam en el grupo
DOMINIOS_SPAM = [
    "t.me/",       # Links a otros canales de Telegram
    "whatsapp.com",
    "bit.ly",
    "tinyurl",
    "shorturl",
]

# Dominios permitidos aunque sean links
DOMINIOS_PERMITIDOS = [
    "mercadolibre",
    "amazon",
    "liverpool",
    "walmart",
    "coppel",
    "launchpass.com/marcodurzo",
    "platacard.mx",
]


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
    if "mercadolibre" in url:
        return link_afiliado_ml(url, item_id)
    elif "amazon.com.mx" in url or "amazon.mx" in url:
        return link_afiliado_amazon(url)
    return url


# ─────────────────────────────────────────────
#  FORMATO DE ALERTAS
# ─────────────────────────────────────────────

def formatear_mensaje_vip(alerta):
    interp     = interpretar_score(alerta["heat_score"])
    nombre     = alerta["nombre"][:60]
    p_act      = alerta["precio_actual"]
    p_ref      = alerta["precio_minimo"]
    descuento  = alerta["descuento_real"] * 100
    stock      = alerta["stock"]
    emoji_cat  = alerta["categoria"]["emoji"]
    nombre_cat = alerta["categoria"]["nombre"]
    link       = link_afiliado_auto(alerta["permalink"], alerta["item_id"])
    score      = alerta["heat_score"]
    es_frio    = alerta.get("modo_frio", False)
    ref_label  = "Precio tachado" if es_frio else "Minimo historico"

    if stock == 1:
        stock_txt = "ULTIMA UNIDAD"
    elif stock <= 3:
        stock_txt = f"Solo {stock} unidades"
    elif stock <= 10:
        stock_txt = f"{stock} unidades disponibles"
    else:
        stock_txt = "Stock disponible"

    reventa_low  = p_ref * 0.80
    reventa_high = p_ref * 0.92

    return (
        f"{interp['emoji']} *{interp['etiqueta']}*"
        f" - {emoji_cat} {nombre_cat}\n\n"
        f"*{nombre}*\n\n"
        f"Precio ahora: *${p_act:,.0f} MXN*\n"
        f"{ref_label}: ${p_ref:,.0f} MXN\n"
        f"Caida real: *-{descuento:.0f}%*\n"
        f"Stock: {stock_txt}\n"
        f"Score: {score}/10\n\n"
        f"[COMPRAR AHORA]({link})\n\n"
        f"_Reventa estimada: ${reventa_low:,.0f} - ${reventa_high:,.0f} MXN_\n"
        f"_{datetime.now().strftime('%H:%M:%S')}_"
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
        f"*${p_act:,.0f} MXN* (-{descuento:.0f}%)\n"
        f"Ref: ${p_ref:,.0f} MXN\n\n"
        f"[Ver oferta]({link})\n\n"
        f"_Canal VIP recibe estas alertas primero._\n"
        f"_{LAUNCHPASS_LINK}_"
    )


# ─────────────────────────────────────────────
#  MENSAJES PERIODICOS — FINANCIEROS
# ─────────────────────────────────────────────

def formatear_financiero_free():
    """Mensaje completo de producto financiero para canal free."""
    activos = [p for p in PRODUCTOS_FINANCIEROS if p["activo"]]
    if not activos:
        return None
    prod = activos[datetime.now().day % len(activos)]
    return (
        f"{prod['emoji']} *{prod['nombre']}*\n\n"
        f"{prod['descripcion']}\n\n"
        f"{prod['beneficio']}\n\n"
        f"[Conocer mas]({prod['link']})\n\n"
        f"_Recomendado por DropNode MX._"
    )


def formatear_financiero_vip():
    """Version corta para canal VIP — sin parecer publicidad."""
    activos = [p for p in PRODUCTOS_FINANCIEROS if p["activo"]]
    if not activos:
        return None
    prod = activos[datetime.now().day % len(activos)]
    return (
        f"{prod['emoji']} *{prod['nombre']}* "
        f"- {prod['descripcion']}\n"
        f"[Ver]({prod['link']})"
    )


def formatear_financiero_grupo():
    """Version para el grupo Community — mas espaciada, menos frecuente."""
    activos = [p for p in PRODUCTOS_FINANCIEROS if p["activo"]]
    if not activos:
        return None
    # En el grupo rota diferente para no coincidir con el canal free
    prod = activos[(datetime.now().day + 1) % len(activos)]
    return (
        f"{prod['emoji']} *Tip financiero del equipo DropNode*\n\n"
        f"*{prod['nombre']}* - {prod['descripcion']}\n\n"
        f"{prod['beneficio']}\n\n"
        f"[Mas informacion]({prod['link']})"
    )


# ─────────────────────────────────────────────
#  RECORDATORIO VIP
# ─────────────────────────────────────────────

def formatear_recordatorio_vip():
    versiones = [
        (
            "Canal VIP DropNode MX\n\n"
            "Las alertas de errores de precio llegan ahi primero.\n"
            "Un solo error de precio bien aprovechado paga meses de acceso.\n\n"
            f"{LAUNCHPASS_LINK}"
        ),
        (
            "Mientras lees esto...\n\n"
            "En el canal VIP ya hay alertas de stock critico.\n"
            "Las mejores oportunidades no esperan.\n\n"
            f"{LAUNCHPASS_LINK}"
        ),
        (
            "*Canal VIP DropNode MX*\n\n"
            "Errores de precio - Stock limitado - Liquidaciones\n"
            "Todo antes que este canal.\n\n"
            f"$299 MXN/mes - cancela cuando quieras\n"
            f"{LAUNCHPASS_LINK}"
        ),
    ]
    idx = (datetime.now().day + datetime.now().hour) % len(versiones)
    return versiones[idx]


# ─────────────────────────────────────────────
#  MENSAJE BIENVENIDA GRUPO
# ─────────────────────────────────────────────

def mensaje_bienvenida_grupo():
    return (
        "*Bienvenido a DropNode Community MX*\n\n"
        "Aqui compartimos los mejores descuentos que nuestro equipo encuentra.\n\n"
        "Canal de alertas gratuito: @DropNodeMX\n"
        f"Canal VIP (errores de precio): {LAUNCHPASS_LINK}\n\n"
        "*Reglas del grupo:*\n"
        "1. Comparte solo ofertas reales verificadas\n"
        "2. Sin spam ni links a otros canales\n"
        "3. Sin publicidad no autorizada\n"
        "4. Respeta a todos los miembros\n\n"
        "El incumplimiento de las reglas resulta en advertencia, "
        "silencio temporal o expulsion segun la gravedad.\n\n"
        "_DropNode MX - Siempre encontramos el mejor precio._"
    )


# ─────────────────────────────────────────────
#  RESUMEN DIARIO
# ─────────────────────────────────────────────

def calcular_ahorro_estimado(alertas):
    total = 0.0
    for a in alertas:
        precio    = a.get("precio_alerta", 0)
        descuento = a.get("descuento_real", 0)
        if precio and descuento and 0 < descuento < 1:
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

    # Mensaje VIP
    msg_vip = (
        f"Resumen ultimas 24 hrs - DropNode MX VIP\n\n"
        f"Alertas exclusivas VIP: *{total_vip}*\n"
        f"Alertas canal publico: *{total_free}*\n"
        f"Oportunidades analizadas: *{total_ops}*\n"
    )
    if mejor_desc > 0:
        msg_vip += f"Mejor descuento del dia: *-{mejor_desc:.0f}%*\n"
    if ahorro_est > 0:
        msg_vip += f"Ahorro acumulado estimado: *~${ahorro_est:,.0f} MXN*\n"
    msg_vip += "\n_Seguimos monitoreando las mejores oportunidades._"

    # Mensaje Free
    msg_free = f"Resumen del dia - DropNode MX\n\nOportunidades encontradas: *{total_ops}*\n"
    if ahorro_est > 0:
        msg_free += f"Ahorro estimado del canal: *~${ahorro_est:,.0f} MXN*\n"
    msg_free += (
        f"\n_Nuestro equipo sigue monitoreando._\n\n"
        f"Acceso VIP: {LAUNCHPASS_LINK}"
    )

    enviar_mensaje(CHANNEL_VIP_ID, msg_vip)
    enviar_mensaje(CHANNEL_FREE_ID, msg_free)


# ─────────────────────────────────────────────
#  MODERACION AUTOMATICA DEL GRUPO
# ─────────────────────────────────────────────

def es_spam(texto):
    """
    Revisa si un mensaje contiene contenido no permitido.
    Retorna True si debe ser moderado.
    """
    if not texto:
        return False

    texto_lower = texto.lower()

    # Verificar si contiene un dominio permitido
    for permitido in DOMINIOS_PERMITIDOS:
        if permitido in texto_lower:
            return False

    # Verificar si contiene un dominio de spam
    for spam in DOMINIOS_SPAM:
        if spam in texto_lower:
            return True

    return False


def eliminar_mensaje(chat_id, message_id):
    """Elimina un mensaje del grupo."""
    try:
        requests.post(
            f"{TELEGRAM_API}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=10
        )
    except Exception as e:
        logger.error(f"[MOD] Error eliminando mensaje: {e}")


def silenciar_usuario(chat_id, user_id, segundos=3600):
    """
    Restringe a un usuario para que no pueda escribir.
    Por default: 1 hora (3600 segundos).
    """
    import time as t
    hasta = int(t.time()) + segundos
    try:
        requests.post(
            f"{TELEGRAM_API}/restrictChatMember",
            json={
                "chat_id":     chat_id,
                "user_id":     user_id,
                "until_date":  hasta,
                "permissions": {
                    "can_send_messages":       False,
                    "can_send_media_messages": False,
                    "can_send_polls":          False,
                    "can_send_other_messages": False,
                }
            },
            timeout=10
        )
        logger.info(f"[MOD] Usuario {user_id} silenciado por {segundos}s")
    except Exception as e:
        logger.error(f"[MOD] Error silenciando: {e}")


def banear_usuario(chat_id, user_id):
    """Banea permanentemente a un usuario del grupo."""
    try:
        requests.post(
            f"{TELEGRAM_API}/banChatMember",
            json={"chat_id": chat_id, "user_id": user_id},
            timeout=10
        )
        logger.info(f"[MOD] Usuario {user_id} baneado")
    except Exception as e:
        logger.error(f"[MOD] Error baneando: {e}")


def procesar_mensaje_grupo(update):
    """
    Revisa cada mensaje nuevo en el grupo Community.
    Sistema de 3 pasos:
      1ra infraccion  -> advertencia + borrar mensaje
      2da infraccion  -> silencio 1 hora + borrar mensaje
      3ra infraccion  -> ban permanente
    """
    try:
        msg      = update.get("message", {})
        chat     = msg.get("chat", {})
        user     = msg.get("from", {})
        texto    = msg.get("text", "")
        msg_id   = msg.get("message_id")
        chat_id  = chat.get("id")
        user_id  = user.get("id")
        username = user.get("username", "usuario")
        nombre   = user.get("first_name", "Usuario")

        # Solo moderar mensajes del grupo Community
        if chat_id != GROUP_ID:
            return

        # No moderar a administradores (bots o admins del canal)
        if user.get("is_bot"):
            return

        if not es_spam(texto):
            return

        # Contar advertencias
        count = advertencias.get(user_id, 0) + 1
        advertencias[user_id] = count

        # Borrar el mensaje en todos los casos
        eliminar_mensaje(chat_id, msg_id)

        if count == 1:
            # Primera vez: advertencia publica
            aviso = (
                f"Hola {nombre}, tu mensaje fue removido.\n\n"
                f"Las reglas del grupo no permiten links a otros canales "
                f"ni publicidad no autorizada.\n\n"
                f"Esta es tu primera advertencia. "
                f"Una segunda infraccion resultara en silencio temporal."
            )
            enviar_mensaje(chat_id, aviso)
            logger.info(f"[MOD] Advertencia 1 a {username} ({user_id})")

        elif count == 2:
            # Segunda vez: silencio 1 hora
            silenciar_usuario(chat_id, user_id, segundos=3600)
            aviso = (
                f"{nombre} ha sido silenciado por 1 hora "
                f"por reincidencia en el envio de spam.\n"
                f"Una tercera infraccion resultara en expulsion permanente."
            )
            enviar_mensaje(chat_id, aviso)
            logger.info(f"[MOD] Silencio 1h a {username} ({user_id})")

        else:
            # Tercera vez: ban permanente
            banear_usuario(chat_id, user_id)
            aviso = (
                f"{nombre} ha sido expulsado del grupo "
                f"por multiples infracciones a las reglas."
            )
            enviar_mensaje(chat_id, aviso)
            # Limpiar del registro
            advertencias.pop(user_id, None)
            logger.info(f"[MOD] Ban permanente a {username} ({user_id})")

    except Exception as e:
        logger.error(f"[MOD] Error procesando mensaje: {e}")


def revisar_actualizaciones_grupo():
    """
    Revisa mensajes nuevos en el grupo usando getUpdates.
    Se llama desde main.py cada minuto.
    """
    try:
        resp = requests.get(
            f"{TELEGRAM_API}/getUpdates",
            params={"timeout": 5, "allowed_updates": ["message"]},
            timeout=15
        )
        data = resp.json()
        if not data.get("ok"):
            return

        updates = data.get("result", [])
        for update in updates:
            procesar_mensaje_grupo(update)

        # Confirmar que procesamos hasta este update
        if updates:
            last_id = updates[-1]["update_id"]
            requests.get(
                f"{TELEGRAM_API}/getUpdates",
                params={"offset": last_id + 1, "limit": 1},
                timeout=10
            )
    except Exception as e:
        logger.error(f"[MOD] Error en getUpdates: {e}")


# ─────────────────────────────────────────────
#  ENVIO DE MENSAJES
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
    requests.post(
        f"{TELEGRAM_API}/pinChatMessage",
        json={"chat_id": chat_id, "message_id": message_id},
        timeout=10
    )


def enviar_y_fijar_bienvenida_grupo():
    texto  = mensaje_bienvenida_grupo()
    msg_id = enviar_mensaje(GROUP_ID, texto)
    if msg_id:
        fijar_mensaje(GROUP_ID, msg_id)
        logger.info(f"[SETUP] Bienvenida fijada en grupo")


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
        msg_id = enviar_mensaje(CHANNEL_VIP_ID, formatear_mensaje_vip(alerta))
        if alerta["heat_score"] >= 5:
            time.sleep(3)
            enviar_mensaje(CHANNEL_FREE_ID, formatear_mensaje_free(alerta))
    else:
        msg_id = enviar_mensaje(CHANNEL_FREE_ID, formatear_mensaje_free(alerta))

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
    """Publica en los 3 destinos con formato adaptado a cada uno."""
    # Canal free — version completa
    texto_free = formatear_financiero_free()
    if texto_free:
        enviar_mensaje(CHANNEL_FREE_ID, texto_free)

    # Canal VIP — version corta
    texto_vip = formatear_financiero_vip()
    if texto_vip:
        enviar_mensaje(CHANNEL_VIP_ID, texto_vip)

    # Grupo Community — solo una vez al dia, en el envio de las 11am
    if datetime.now().hour == 11:
        texto_grupo = formatear_financiero_grupo()
        if texto_grupo:
            enviar_mensaje(GROUP_ID, texto_grupo)

    logger.info("[FINANCIERO] Publicado en todos los canales")


def enviar_recordatorio_vip():
    if not LAUNCHPASS_LINK:
        return
    enviar_mensaje(CHANNEL_FREE_ID, formatear_recordatorio_vip())
    logger.info("[VIP CTA] Publicado en canal free")
