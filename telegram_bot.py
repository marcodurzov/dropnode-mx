# =============================================================
# DROPNODE MX — telegram_bot.py  v2.1
# Mensajes con contexto histórico + urgencia + prueba social
# =============================================================

import requests, logging, urllib.parse, time, random
from datetime import datetime, timezone, timedelta
from config import (
    TELEGRAM_TOKEN, CHANNEL_FREE_ID, CHANNEL_VIP_ID, GROUP_ID,
    ML_AFFILIATE_ID, AMAZON_TAG, EBAY_CAMPAIGN_ID, EBAY_CUSTOM_ID,
    LAUNCHPASS_LINK, HORA_INICIO_ENVIOS, HORA_FIN_ENVIOS,
    PRODUCTOS_FINANCIEROS, TIMEZONE_OFFSET_HOURS,
)
from heat_score import interpretar_score
from database  import guardar_alerta, get_stats_historicas, get_engagement_producto

logger       = logging.getLogger(__name__)
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TZ_MEXICO    = timezone(timedelta(hours=TIMEZONE_OFFSET_HOURS))

def hora_mx():
    return datetime.now(TZ_MEXICO)

def dentro_de_horario():
    return HORA_INICIO_ENVIOS <= hora_mx().hour < HORA_FIN_ENVIOS


# ─────────────────────────────────────────────
#  AFILIADOS
# ─────────────────────────────────────────────

def link_ml(url, item_id):
    if not ML_AFFILIATE_ID:
        return url
    p = urllib.parse.urlencode({
        "as_src": "affiliate", "as_campaign": "dropnodemx",
        "as_content": item_id, "url": url, "affiliate_id": ML_AFFILIATE_ID,
    })
    return f"https://go.mercadolibre.com.mx?{p}"

def link_amazon(url):
    if not AMAZON_TAG:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}tag={AMAZON_TAG}"

def link_auto(url, item_id=""):
    if "mercadolibre" in url: return link_ml(url, item_id)
    if "amazon.com.mx" in url or "amazon.mx" in url: return link_amazon(url)
    return url


# ─────────────────────────────────────────────
#  CONTEXTO HISTORICO (el diferenciador real)
# ─────────────────────────────────────────────

def construir_contexto_historico(producto_id: str,
                                  precio_actual: float) -> dict:
    """
    Trae estadísticas reales de Supabase y las convierte
    en frases de urgencia y contexto para el mensaje.
    """
    stats = get_stats_historicas(producto_id)
    ctx   = {}

    if not stats:
        return ctx

    min_p   = stats.get("precio_minimo", precio_actual)
    max_p   = stats.get("precio_maximo", precio_actual)
    avg_p   = stats.get("precio_promedio", precio_actual)
    dias_h  = stats.get("dias_historial", 0)
    dias_act = stats.get("dias_en_precio_actual", 0)

    # ¿Es el precio más bajo registrado?
    if precio_actual <= min_p * 1.01 and dias_h >= 7:
        ctx["es_minimo"] = True
        ctx["frase_minimo"] = (
            f"Precio mas bajo en {dias_h} dias de seguimiento"
        )

    # Diferencia vs promedio
    if avg_p > 0 and precio_actual < avg_p * 0.90:
        ahorro_vs_promedio = avg_p - precio_actual
        ctx["vs_promedio"] = (
            f"${ahorro_vs_promedio:,.0f} menos que el precio promedio"
        )

    # Diferencia vs máximo histórico
    if max_p > precio_actual * 1.20:
        ctx["vs_maximo"] = (
            f"Llego a costar ${max_p:,.0f} MXN hace {dias_h} dias"
        )

    # Cuánto tiempo lleva en este precio
    if dias_act >= 2:
        ctx["tiempo_precio"] = f"En este precio hace {dias_act} dias"
    elif dias_act == 0:
        ctx["tiempo_precio"] = "Precio cambiado hoy"

    return ctx


def construir_prueba_social(producto_id: str,
                             stock: int) -> dict:
    """
    Genera frases de prueba social basadas en datos reales:
    - Engagement del producto en el canal
    - Stock actual (urgencia real)
    - Actividad reciente
    """
    eng  = get_engagement_producto(producto_id)
    ps   = {}

    # Urgencia por stock real
    if stock == 1:
        ps["stock"] = "ULTIMA UNIDAD disponible"
    elif stock <= 3:
        ps["stock"] = f"Solo {stock} unidades en existencia"
    elif stock <= 5:
        ps["stock"] = f"{stock} unidades disponibles"
    elif stock <= 10:
        ps["stock"] = f"{stock} unidades — stock bajo"

    # Engagement real del canal
    clicks = eng.get("total_clicks", 0)
    if clicks >= 10:
        ps["clicks"] = f"{clicks} personas del canal vieron esta oferta"
    elif clicks >= 3:
        ps["clicks"] = f"{clicks} personas del canal revisaron este producto"

    # Cuántas veces se ha alertado este producto
    alertas = eng.get("total_alertas", 0)
    if alertas >= 3:
        ps["recurrente"] = f"Alerta enviada {alertas} veces — precio vuelve a caer"

    return ps


def estimar_ventana_oferta(descuento: float, stock: int) -> str:
    """
    Estima cuánto tiempo podría durar la oferta.
    Basado en patrones reales de ML y otras tiendas.
    Legal porque es una estimación declarada como tal.
    """
    if descuento >= 0.50 or stock <= 2:
        return "Oferta podria terminar en minutos"
    elif descuento >= 0.35 or stock <= 5:
        return "Disponible probablemente pocas horas"
    elif descuento >= 0.25:
        return "Oferta de tiempo limitado"
    else:
        return ""


# ─────────────────────────────────────────────
#  FORMATOS DE MENSAJES
# ─────────────────────────────────────────────

def formatear_vip(alerta: dict) -> str:
    interp     = interpretar_score(alerta["heat_score"])
    nombre     = alerta["nombre"][:65]
    p_act      = alerta["precio_actual"]
    p_ref      = alerta["precio_minimo"]
    p_orig     = alerta["precio_original"]
    descuento  = alerta["descuento_real"] * 100
    stock      = alerta["stock"]
    emoji_c    = alerta["categoria"]["emoji"]
    cat_nombre = alerta["categoria"]["nombre"]
    link       = link_auto(alerta["permalink"], alerta["item_id"])
    score      = alerta["heat_score"]
    es_frio    = alerta.get("modo_frio", False)

    ctx = construir_contexto_historico(alerta["producto_id"], p_act)
    ps  = construir_prueba_social(alerta["producto_id"], stock)
    ventana = estimar_ventana_oferta(alerta["descuento_real"], stock)

    rl = p_ref * 0.80
    rh = p_ref * 0.92

    # Linea de precio de referencia
    ref_label = "Precio tachado" if es_frio else "Minimo historico"

    msg = f"{interp['emoji']} *{interp['etiqueta']}*  {emoji_c} {cat_nombre}\n\n"
    msg += f"*{nombre}*\n\n"

    # Bloque de precio
    msg += f"Precio ahora:   *${p_act:,.0f} MXN*\n"
    msg += f"{ref_label}:  ${p_ref:,.0f} MXN\n"
    msg += f"Descuento real: *-{descuento:.0f}%*\n"

    # Contexto histórico
    if ctx.get("es_minimo"):
        msg += f"\n*{ctx['frase_minimo']}*\n"
    if ctx.get("vs_promedio"):
        msg += f"{ctx['vs_promedio']}\n"
    if ctx.get("vs_maximo"):
        msg += f"{ctx['vs_maximo']}\n"

    # Stock y urgencia
    msg += "\n"
    if ps.get("stock"):
        msg += f"*{ps['stock']}*\n"
    if ventana:
        msg += f"_{ventana}_\n"

    # Prueba social real
    if ps.get("clicks"):
        msg += f"_{ps['clicks']}_\n"
    if ps.get("recurrente"):
        msg += f"_{ps['recurrente']}_\n"

    msg += f"\nScore: {score}/10\n\n"
    msg += f"[COMPRAR AHORA]({link})\n\n"
    msg += f"_Reventa estimada: ${rl:,.0f} - ${rh:,.0f} MXN_\n"
    msg += f"_{hora_mx().strftime('%H:%M:%S')} hora MX_"

    return msg


def formatear_free(alerta: dict) -> str:
    interp    = interpretar_score(alerta["heat_score"])
    nombre    = alerta["nombre"][:60]
    p_act     = alerta["precio_actual"]
    p_ref     = alerta["precio_minimo"]
    descuento = alerta["descuento_real"] * 100
    emoji_c   = alerta["categoria"]["emoji"]
    link      = link_auto(alerta["permalink"], alerta["item_id"])
    stock     = alerta["stock"]

    ctx = construir_contexto_historico(alerta["producto_id"], p_act)
    ps  = construir_prueba_social(alerta["producto_id"], stock)

    msg = f"{interp['emoji']} *{interp['etiqueta']}*  {emoji_c}\n\n"
    msg += f"*{nombre}*\n\n"
    msg += f"*${p_act:,.0f} MXN* (-{descuento:.0f}%)\n"
    msg += f"Ref: ${p_ref:,.0f} MXN\n"

    if ctx.get("es_minimo"):
        msg += f"\n*{ctx['frase_minimo']}*\n"
    if ps.get("stock"):
        msg += f"*{ps['stock']}*\n"
    if ps.get("clicks"):
        msg += f"_{ps['clicks']}_\n"

    msg += f"\n[Ver oferta]({link})\n\n"
    msg += f"_El canal VIP recibe estas alertas primero + analisis de reventa._\n"
    msg += f"_{LAUNCHPASS_LINK}_"

    return msg


def formatear_mejor_del_dia(alertas: list) -> str:
    """
    Resumen de los mejores productos del ciclo.
    Con contexto histórico cuando está disponible.
    """
    if not alertas:
        return ""

    hora = hora_mx()
    titulo = "Mejores precios de la tarde" if hora.hour >= 15 else "Mejores precios de la manana"

    msg = f"📋 *{titulo} — DropNode MX*\n\n"
    msg += "_Nuestro equipo reviso miles de productos. Estos destacan hoy:_\n\n"

    for i, item in enumerate(alertas[:5], 1):
        nombre  = item["nombre"][:50]
        precio  = item["precio_actual"]
        emoji   = item["categoria"]["emoji"]
        link    = item.get("permalink", "")
        desc    = item.get("descuento_real", 0) * 100

        ctx = construir_contexto_historico(
            item.get("producto_id", ""), precio)

        linea = f"{i}. {emoji} *[{nombre}]({link})*\n"
        linea += f"   *${precio:,.0f} MXN*"
        if desc >= 10:
            linea += f" (-{desc:.0f}%)"
        if ctx.get("es_minimo"):
            linea += f"\n   _{ctx['frase_minimo']}_"
        msg += linea + "\n\n"

    msg += f"🔒 _Alertas de errores de precio van al VIP primero._\n"
    msg += f"_{LAUNCHPASS_LINK}_"
    return msg


# ─────────────────────────────────────────────
#  MENSAJES PERIODICOS
# ─────────────────────────────────────────────

def formatear_financiero_free():
    activos = [p for p in PRODUCTOS_FINANCIEROS if p["activo"]]
    if not activos:
        return None
    prod = activos[hora_mx().day % len(activos)]
    return (
        f"{prod['emoji']} *{prod['nombre']}*\n\n"
        f"{prod['descripcion']}\n\n"
        f"{prod['beneficio']}\n\n"
        f"[Conocer mas]({prod['link']})\n\n"
        f"_Recomendado por DropNode MX._"
    )

def formatear_financiero_vip():
    activos = [p for p in PRODUCTOS_FINANCIEROS if p["activo"]]
    if not activos:
        return None
    prod = activos[hora_mx().day % len(activos)]
    return f"{prod['emoji']} *{prod['nombre']}* — {prod['descripcion']}\n[Ver]({prod['link']})"

def formatear_recordatorio_vip():
    lnk = (f'<a href="{LAUNCHPASS_LINK}">Canal DropNode VIP</a>'
           if LAUNCHPASS_LINK else "Canal DropNode VIP")
    versiones = [
        (
            "<b>Canal VIP DropNode MX</b>\n\n"
            "Errores de precio - Analisis de reventa - Stock critico\n"
            "Todo antes que el canal publico.\n\n"
            "$299 MXN/mes - cancela cuando quieras\n" + lnk
        ),
        (
            "<b>Mientras lees esto...</b>\n\n"
            "Los miembros VIP ya recibieron alertas con analisis completo.\n"
            "Las mejores oportunidades no esperan.\n\n" + lnk
        ),
        (
            "<b>Canal VIP - lo que incluye:</b>\n\n"
            "Alertas en tiempo real\n"
            "Precio vs historico de 90 dias\n"
            "Estimacion de reventa\n"
            "Alertas de stock critico\n"
            "Reporte semanal exclusivo\n\n"
            "$299 MXN/mes\n" + lnk
        ),
    ]
    idx = (hora_mx().day + hora_mx().hour) % len(versiones)
    return versiones[idx]


def mensaje_bienvenida_grupo():
    vip_link = (f'<a href="{LAUNCHPASS_LINK}">Canal VIP DropNode</a>'
                if LAUNCHPASS_LINK else "Canal VIP DropNode")
    return (
        "<b>Bienvenido a DropNode Community MX</b>\n\n"
        "Aqui compartimos los mejores descuentos que nuestro equipo encuentra.\n\n"
        "Canal gratuito: @DropNodeMX\n"
        "Canal VIP: " + vip_link + "\n\n"
        "<b>Reglas:</b>\n"
        "1. Solo ofertas reales verificadas\n"
        "2. Sin links a otros canales\n"
        "3. Sin publicidad no autorizada\n"
        "4. Respeta a todos\n\n"
        "<i>DropNode MX - Siempre encontramos el mejor precio.</i>"
    )



# ─────────────────────────────────────────────
#  RESUMEN DIARIO
# ─────────────────────────────────────────────

def calcular_ahorro_estimado(alertas):
    total = 0.0
    for a in alertas:
        p = a.get("precio_alerta", 0)
        d = a.get("descuento_real", 0)
        if p and d and 0 < d < 1:
            total += (p / (1 - d)) - p
    return total

def enviar_resumen_diario(total_vip=0, total_free=0):
    import datetime as _dt
    from database import get_client

    vip_real = 0
    free_real = 0
    ahorro = 0.0
    mejor_d = 0.0
    try:
        db = get_client()
        # Buscar alertas de las ultimas 24h (cubre diferencia UTC/Mexico)
        desde_utc = (_dt.datetime.utcnow() - _dt.timedelta(hours=24)).isoformat()
        r = db.table("alertas_enviadas").select(
            "canal, precio_alerta, descuento_real"
        ).gte("timestamp", desde_utc).execute()
        rows = r.data or []
        vip_real  = sum(1 for x in rows if x.get("canal") == "vip")
        free_real = sum(1 for x in rows if x.get("canal") == "free")
        for row in rows:
            p = float(row.get("precio_alerta") or 0)
            d = float(row.get("descuento_real") or 0)
            if p > 0 and 0 < d < 1:
                ahorro += (p / (1 - d)) - p
            if d > mejor_d:
                mejor_d = d
    except Exception:
        pass

    total = vip_real + free_real
    lnk = (f'<a href="{LAUNCHPASS_LINK}">Acceso VIP</a>'
           if LAUNCHPASS_LINK else "Acceso VIP")

    if total == 0:
        msg_vip = (
            "Resumen ultimas 24 hrs - DropNode MX VIP\n\n"
            "Nuestro equipo sigue monitoreando las mejores oportunidades."
        )
        msg_free = (
            "Resumen del dia - DropNode MX\n\n"
            "Nuestro equipo sigue monitoreando.\n\n" + lnk
        )
    else:
        msg_vip = "<b>Resumen ultimas 24 hrs - DropNode MX VIP</b>\n\n"
        if vip_real > 0:
            msg_vip += f"Alertas exclusivas VIP: <b>{vip_real}</b>\n"
        if free_real > 0:
            msg_vip += f"Alertas canal publico: <b>{free_real}</b>\n"
        if total > 0:
            msg_vip += f"Oportunidades analizadas: <b>{total}</b>\n"
        if mejor_d > 0:
            msg_vip += f"Mejor descuento del dia: <b>-{mejor_d * 100:.0f}%</b>\n"
        if ahorro > 0:
            msg_vip += f"Ahorro estimado: <b>~${ahorro:,.0f} MXN</b>\n"
        msg_vip += "\n<i>Nuestro equipo sigue monitoreando.</i>"

        msg_free = "<b>Resumen del dia - DropNode MX</b>\n\n"
        if total > 0:
            msg_free += f"Oportunidades encontradas: <b>{total}</b>\n"
        if ahorro > 0:
            msg_free += f"Ahorro estimado: <b>~${ahorro:,.0f} MXN</b>\n"
        msg_free += "\n<i>Nuestro equipo sigue monitoreando.</i>\n\n" + lnk

    enviar_mensaje(CHANNEL_VIP_ID, msg_vip, parse_mode="HTML")
    enviar_mensaje(CHANNEL_FREE_ID, msg_free, parse_mode="HTML")



# ─────────────────────────────────────────────
#  MODERACION DEL GRUPO
# ─────────────────────────────────────────────

advertencias = {}
DOMINIOS_SPAM = ["t.me/", "whatsapp.com", "bit.ly", "tinyurl", "shorturl"]
DOMINIOS_OK   = ["mercadolibre", "amazon", "liverpool", "walmart",
                  "coppel", "launchpass.com/marcodurzo", "platacard.mx"]

def es_spam(texto):
    if not texto:
        return False
    t = texto.lower()
    for ok in DOMINIOS_OK:
        if ok in t:
            return False
    for spam in DOMINIOS_SPAM:
        if spam in t:
            return True
    return False

def eliminar_mensaje_chat(chat_id, message_id):
    try:
        requests.post(f"{TELEGRAM_API}/deleteMessage",
                      json={"chat_id": chat_id, "message_id": message_id},
                      timeout=10)
    except Exception:
        pass

def silenciar(chat_id, user_id, segundos=3600):
    import time as t
    try:
        requests.post(f"{TELEGRAM_API}/restrictChatMember",
                      json={"chat_id": chat_id, "user_id": user_id,
                            "until_date": int(t.time()) + segundos,
                            "permissions": {
                                "can_send_messages": False,
                                "can_send_media_messages": False,
                            }}, timeout=10)
    except Exception:
        pass

def banear(chat_id, user_id):
    try:
        requests.post(f"{TELEGRAM_API}/banChatMember",
                      json={"chat_id": chat_id, "user_id": user_id},
                      timeout=10)
    except Exception:
        pass

def procesar_mensaje_grupo(update):
    try:
        msg     = update.get("message", {})
        chat    = msg.get("chat", {})
        user    = msg.get("from", {})
        texto   = msg.get("text", "")
        msg_id  = msg.get("message_id")
        chat_id = chat.get("id")
        user_id = user.get("id")
        nombre  = user.get("first_name", "Usuario")

        if chat_id != GROUP_ID or user.get("is_bot"):
            return
        if not es_spam(texto):
            return

        count = advertencias.get(user_id, 0) + 1
        advertencias[user_id] = count
        eliminar_mensaje_chat(chat_id, msg_id)

        if count == 1:
            enviar_mensaje(chat_id,
                f"{nombre}, tu mensaje fue removido. "
                f"Primera advertencia — sin links a otros canales.")
        elif count == 2:
            silenciar(chat_id, user_id, 3600)
            enviar_mensaje(chat_id,
                f"{nombre} silenciado 1 hora por reincidencia.")
        else:
            banear(chat_id, user_id)
            advertencias.pop(user_id, None)
            enviar_mensaje(chat_id,
                f"{nombre} expulsado por multiples infracciones.")
    except Exception as e:
        logger.error(f"[MOD] {e}")

def revisar_actualizaciones_grupo():
    try:
        resp = requests.get(f"{TELEGRAM_API}/getUpdates",
                           params={"timeout": 5,
                                   "allowed_updates": ["message"]},
                           timeout=15)
        data    = resp.json()
        updates = data.get("result", [])
        for u in updates:
            procesar_mensaje_grupo(u)
        if updates:
            last = updates[-1]["update_id"]
            requests.get(f"{TELEGRAM_API}/getUpdates",
                        params={"offset": last + 1, "limit": 1},
                        timeout=10)
    except Exception as e:
        logger.error(f"[MOD] getUpdates: {e}")


# ─────────────────────────────────────────────
#  ENVIO
# ─────────────────────────────────────────────

def enviar_mensaje(chat_id, texto, preview=False, parse_mode="Markdown"):
    url     = f"{TELEGRAM_API}/sendMessage"
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
            return data["result"]["message_id"]
        else:
            logger.error(f"[TG] {data.get('description', '?')}")
            return None
    except Exception as e:
        logger.error(f"[TG] {e}")
        return None

def fijar_mensaje(chat_id, message_id):
    try:
        requests.post(f"{TELEGRAM_API}/pinChatMessage",
                      json={"chat_id": chat_id, "message_id": message_id},
                      timeout=10)
    except Exception:
        pass

def enviar_y_fijar_bienvenida_grupo():
    msg_id = enviar_mensaje(GROUP_ID, mensaje_bienvenida_grupo(), parse_mode="HTML")
    if msg_id:
        fijar_mensaje(GROUP_ID, msg_id)


def enviar_alerta(alerta):
    if not dentro_de_horario():
        return False

    interp = interpretar_score(alerta["heat_score"])
    canal  = interp["canal"]
    if canal == "descartar":
        return False

    msg_id = None
    if canal == "vip":
        msg_id = enviar_mensaje(CHANNEL_VIP_ID, formatear_vip(alerta))
        if alerta["heat_score"] >= 5:
            time.sleep(3)
            enviar_mensaje(CHANNEL_FREE_ID, formatear_free(alerta))
    else:
        msg_id = enviar_mensaje(CHANNEL_FREE_ID, formatear_free(alerta))

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
    texto_free = formatear_financiero_free()
    texto_vip  = formatear_financiero_vip()
    if texto_free:
        enviar_mensaje(CHANNEL_FREE_ID, texto_free)
    if texto_vip:
        enviar_mensaje(CHANNEL_VIP_ID, texto_vip)
    if hora_mx().hour == 11:
        activos = [p for p in PRODUCTOS_FINANCIEROS if p["activo"]]
        if activos:
            prod = activos[(hora_mx().day + 1) % len(activos)]
            enviar_mensaje(GROUP_ID,
                f"{prod['emoji']} *Tip financiero*\n\n"
                f"*{prod['nombre']}* - {prod['descripcion']}\n\n"
                f"[Mas info]({prod['link']})")

def enviar_recordatorio_vip():
    if not LAUNCHPASS_LINK:
        return
    enviar_mensaje(CHANNEL_FREE_ID, formatear_recordatorio_vip(), parse_mode="HTML")


def publicar_mejores_del_dia(destacados: list):
    if not destacados:
        return
    msg = formatear_mejor_del_dia(destacados)
    if msg:
        enviar_mensaje(CHANNEL_FREE_ID, msg)
        logger.info(f"[DESTACADOS] {len(destacados[:5])} publicados")
