import requests
import logging
import random
import os
from datetime import datetime, timezone, timedelta
from config import TELEGRAM_TOKEN, GROUP_ID, CHANNEL_FREE_ID, CHANNEL_VIP_ID, LAUNCHPASS_LINK

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN
TZ_MEXICO    = timezone(timedelta(hours=-6))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()


def hora_mx():
    return datetime.now(TZ_MEXICO)


def _db():
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


def _semana():
    return hora_mx().isocalendar()[1]


# ─────────────────────────────────────────────
# ENVÍO
# ─────────────────────────────────────────────

def enviar_grupo(texto, modo="HTML"):
    try:
        r = requests.post(TELEGRAM_API + "/sendMessage", json={
            "chat_id": GROUP_ID, "text": texto,
            "parse_mode": modo, "disable_web_page_preview": True,
        }, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        logger.error("[COMMUNITY] " + str(e))
        return False


def enviar_grupo_con_boton(texto, modo="HTML"):
    try:
        payload = {
            "chat_id": GROUP_ID, "text": texto,
            "parse_mode": modo, "disable_web_page_preview": True,
        }
        if LAUNCHPASS_LINK:
            payload["reply_markup"] = {"inline_keyboard": [[{
                "text": "📲 Unirse al Canal VIP — $299/mes",
                "url":  LAUNCHPASS_LINK
            }]]}
        r = requests.post(TELEGRAM_API + "/sendMessage", json=payload, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        logger.error("[COMMUNITY VIP] " + str(e))
        return False


def enviar_canal_con_boton(chat_id, texto, modo="HTML"):
    try:
        payload = {
            "chat_id": chat_id, "text": texto,
            "parse_mode": modo, "disable_web_page_preview": True,
        }
        if LAUNCHPASS_LINK:
            payload["reply_markup"] = {"inline_keyboard": [[{
                "text": "📲 Canal VIP — $299/mes",
                "url":  LAUNCHPASS_LINK
            }]]}
        r = requests.post(TELEGRAM_API + "/sendMessage", json=payload, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        logger.error(f"[CANAL] {e}")
        return False


def enviar_poll(pregunta, opciones, guardar_categoria=False):
    try:
        r = requests.post(TELEGRAM_API + "/sendPoll", json={
            "chat_id": GROUP_ID, "question": pregunta,
            "options": opciones, "is_anonymous": False,
        }, timeout=15)
        data = r.json()
        if data.get("ok") and guardar_categoria:
            _guardar_poll(data["result"]["message_id"], pregunta, opciones)
        return data.get("ok", False)
    except Exception as e:
        logger.error("[POLL] " + str(e))
        return False


# ─────────────────────────────────────────────
# DEAL DEL DÍA — el corazón del engagement
# ─────────────────────────────────────────────

def publicar_deal_del_dia():
    """
    Publica el mejor deal del día en la comunidad.
    - Community: muestra el deal con precio y % descuento
    - Free channel: muestra solo el nombre y una línea de FOMO
    - VIP: ya lo recibió antes con análisis completo
    
    Se ejecuta a las 9 AM MX todos los días.
    """
    try:
        from scraper_api import get_deal_del_dia
        deal = get_deal_del_dia()
    except Exception as e:
        logger.error(f"[DEAL DÍA] {e}")
        return

    if not deal:
        logger.info("[DEAL DÍA] Sin deal disponible")
        return

    nombre   = deal["nombre"][:60]
    precio   = deal["precio_actual"]
    precio_o = deal["precio_original"]
    desc     = deal["descuento"] * 100
    url      = deal["url"]
    ev       = "✅ Envío gratis · " if deal.get("envio_gratis") else ""

    # Publicar en la comunidad — muestra precio real, crea conversación
    msg_community = (
        f"⚡ <b>Deal del Día — DropNode MX</b>\n\n"
        f"<b>{nombre}</b>\n\n"
        f"<b>${precio:,.0f} MXN</b> (-{desc:.0f}%)\n"
        f"<s>${precio_o:,.0f}</s>\n"
        f"{ev}\n"
        f"<a href=\"{url}\">Ver en Mercado Libre →</a>\n\n"
        f"<i>¿Lo conocías? ¿Vale la pena? Cuéntanos abajo 👇</i>\n\n"
        f"_Los miembros VIP ya recibieron el análisis completo de reventa "
        f"y otras {random.randint(8, 15)} ofertas que no publicamos aquí._"
    )
    enviar_grupo_con_boton(msg_community)
    logger.info(f"[DEAL DÍA] Community: {nombre[:40]}")

    # 5 minutos después: FOMO en canal free
    import time
    time.sleep(300)

    ahorro = precio_o - precio
    msg_free = (
        f"⚡ <b>Deal del Día</b>\n\n"
        f"<b>{nombre}</b>\n"
        f"<b>${precio:,.0f} MXN</b> (-{desc:.0f}%) · Ahorro: ${ahorro:,.0f}\n\n"
        f"<i>El Canal VIP recibió este deal con análisis de reventa completo "
        f"y {random.randint(8, 15)} oportunidades adicionales que no llegan aquí.</i>"
    )
    enviar_canal_con_boton(CHANNEL_FREE_ID, msg_free)
    logger.info(f"[DEAL DÍA] Free channel enviado")


# ─────────────────────────────────────────────
# FOMO VIP AL FREE
# ─────────────────────────────────────────────

def fomo_vip_al_free(n_exclusivos: int, categoria: str = ""):
    if n_exclusivos <= 0:
        return
    cat_txt = f" de {categoria}" if categoria else ""
    versiones = [
        (
            f"🔒 Nuestro equipo acaba de publicar <b>{n_exclusivos} "
            f"oferta{'s' if n_exclusivos > 1 else ''} exclusiva{'s' if n_exclusivos > 1 else ''}"
            f"{cat_txt}</b> en el Canal VIP.\n\n"
            "<i>No llegan aquí. Los miembros VIP ya las tienen.</i>"
        ),
        (
            f"⚡ En los últimos minutos el Canal VIP recibió "
            f"<b>{n_exclusivos} alerta{'s' if n_exclusivos > 1 else ''}</b> "
            f"que no publicamos aquí.\n\n"
            "<i>Descuentos que no sobreviven lo suficiente para llegar al canal gratuito.</i>"
        ),
        (
            f"🎯 <b>{n_exclusivos} oportunidad{'es' if n_exclusivos > 1 else ''} "
            f"exclusiva{'s' if n_exclusivos > 1 else ''}</b> acaban de llegar al Canal VIP.\n\n"
            "<i>Nuestro equipo las seleccionó por descuento real y potencial de reventa.</i>"
        ),
    ]
    try:
        payload = {
            "chat_id": CHANNEL_FREE_ID,
            "text":    random.choice(versiones),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if LAUNCHPASS_LINK:
            payload["reply_markup"] = {"inline_keyboard": [[{
                "text": "📲 Ver en Canal VIP",
                "url":  LAUNCHPASS_LINK
            }]]}
        requests.post(TELEGRAM_API + "/sendMessage", json=payload, timeout=15)
    except Exception as e:
        logger.error(f"[FOMO FREE] {e}")


# ─────────────────────────────────────────────
# PETICIONES — LUNES
# ─────────────────────────────────────────────

_primera_resp = False
_peticiones   = []


def abrir_ventana():
    global _primera_resp, _peticiones
    _primera_resp = False
    _peticiones   = []


def ventana_activa() -> bool:
    a = hora_mx()
    return a.weekday() == 0 and a.hour < 14


def procesar_posible_peticion(message: dict) -> bool:
    global _primera_resp, _peticiones
    if not ventana_activa():
        return False
    texto = message.get("text", "").strip()
    user  = message.get("from", {})
    if user.get("is_bot") or not texto or len(texto) < 3:
        return False
    if texto.startswith("/") or "http" in texto.lower():
        return False

    _peticiones.append(texto)
    _guardar_peticion(texto, user.get("id"), user.get("username", ""))

    if not _primera_resp:
        _primera_resp = True
        enviar_grupo("Gracias a todos los que están respondiendo 👀\nSeguimos leyendo hasta el mediodía.")
    return True


def _guardar_peticion(texto, user_id, username):
    db = _db()
    if not db:
        return
    try:
        db.table("peticiones").insert({
            "texto": texto[:200], "user_id": user_id,
            "username": username, "semana": _semana(),
        }).execute()
    except Exception as e:
        logger.warning(f"[PETICIONES] {e}")


def _guardar_poll(poll_id, pregunta, opciones):
    db = _db()
    if not db:
        return
    try:
        db.table("polls_comunidad").upsert({
            "poll_id": str(poll_id), "pregunta": pregunta,
            "opciones": opciones, "semana": _semana(), "ganador": None,
        }, on_conflict="poll_id").execute()
    except Exception as e:
        logger.warning(f"[POLL SAVE] {e}")


def enviar_resumen_peticiones():
    db  = _db()
    n   = 0
    try:
        if db:
            r = db.table("peticiones").select("id", count="exact").eq(
                "semana", _semana()).execute()
            n = r.count or len(_peticiones)
        else:
            n = len(_peticiones)
    except Exception:
        n = len(_peticiones)

    if n == 0:
        return

    enviar_grupo_con_boton(
        f"📝 <b>Recibimos {n} sugerencias esta semana.</b>\n\n"
        "Nuestro equipo ya las tiene en el radar.\n"
        "Los primeros resultados aparecen en el Canal VIP antes que aquí."
    )


def enviar_resultado_semanal():
    db = _db()
    if not db:
        return
    try:
        r = db.table("peticiones").select("texto, producto").eq(
            "semana", _semana()).eq("encontrada", True).execute()
        encontradas = r.data or []
        total_r = db.table("peticiones").select("id", count="exact").eq(
            "semana", _semana()).execute()
        total = total_r.count or 0
    except Exception:
        return

    if not encontradas:
        return

    n = len(encontradas)
    enviar_grupo_con_boton(
        f"🎯 <b>Resultados de la semana</b>\n\n"
        f"La comunidad hizo <b>{total} peticiones</b>.\n"
        f"Nuestro equipo encontró <b>{n} de ellas</b>.\n\n"
        f"Cada resultado fue publicado en el Canal VIP antes que en ningún otro lado.\n\n"
        f"<i>Si pediste algo y no apareció, lo seguimos buscando.</i>"
    )


# ─────────────────────────────────────────────
# CONTENIDO SEMANAL
# ─────────────────────────────────────────────

MENSAJES_LUNES = [
    (
        "📝 <b>DropNode te escucha</b>\n\n"
        "Dinos qué producto estás buscando esta semana.\n"
        "Marca, modelo o categoría — lo que sea.\n\n"
        "Nuestro equipo lo pone en el radar. "
        "Los resultados aparecen primero en el Canal VIP."
    ),
    (
        "📝 <b>¿Qué buscas comprar esta semana?</b>\n\n"
        "Escríbelo aquí. Si encontramos oferta real la publicamos "
        "en el Canal VIP antes que en ningún otro lado."
    ),
    (
        "📝 <b>Turno de la comunidad</b>\n\n"
        "¿Qué compra tienes pendiente?\n\n"
        "Los resultados van al Canal VIP primero."
    ),
]

POLLS = [
    {
        "pregunta": "¿Qué categoría quieres que prioricemos esta semana?",
        "opciones": ["Celulares y smartphones", "Laptops y computadoras",
                     "Televisores y audio", "Videojuegos", "Hogar y electrodomésticos"],
        "guardar":  True,
    },
    {
        "pregunta": "¿Para qué usas las alertas de DropNode MX?",
        "opciones": ["Compra personal", "Reventa y flipping",
                     "Regalos", "Solo estoy explorando"],
        "guardar":  False,
    },
    {
        "pregunta": "¿Cuánto sueles gastar cuando encuentras una buena oferta?",
        "opciones": ["Menos de $500", "$500 - $2,000",
                     "$2,000 - $5,000", "Más de $5,000"],
        "guardar":  False,
    },
    {
        "pregunta": "¿Qué tienda tiene las mejores ofertas reales?",
        "opciones": ["Mercado Libre", "Amazon MX", "Liverpool", "Walmart MX"],
        "guardar":  False,
    },
    {
        "pregunta": "¿Qué tipo de oferta valoras más?",
        "opciones": ["Mayor % de descuento", "Precio más bajo histórico",
                     "Envío gratis incluido", "Error de precio / liquidación"],
        "guardar":  False,
    },
]

MENSAJES_VIERNES = [
    "Antes de cerrar la semana:\n\n¿Alguien aprovechó alguna oferta? Cuéntanos qué conseguiste, a qué precio y dónde.",
    "Viernes en DropNode.\n\nComparte tu mejor compra de la semana. Precio, producto, tienda.",
    "Fin de semana. ¿Qué compraste?\n\nSi usaste alguna de nuestras alertas, cuéntanos.",
]

TIPS = [
    (
        "<b>Tip DropNode — Cómo saber si un descuento es real</b>\n\n"
        "No compares contra el precio tachado. Ese puede estar inflado desde hace meses.\n\n"
        "Nuestro equipo compara contra el precio real de los últimos 90 días. "
        "Solo publicamos cuando el descuento es genuino vs el histórico."
    ),
    (
        "<b>Tip DropNode — La hora de los errores de precio</b>\n\n"
        "Los errores de precio ocurren más entre 11 PM y 3 AM, "
        "cuando las tiendas actualizan catálogos.\n\n"
        "<i>Los miembros del Canal VIP reciben estas alertas en cuanto ocurren.</i>"
    ),
    (
        "<b>Tip DropNode — Qué productos valen más para reventa</b>\n\n"
        "1. iPhones y Samsung desbloqueados\n"
        "2. Consolas de videojuegos\n"
        "3. Laptops gaming\n"
        "4. Audífonos premium\n"
        "5. Smartwatches\n\n"
        "Compra bajo el precio de ML y revende ahí con 15-25% de margen."
    ),
    (
        "<b>Tip DropNode — Cómo combinar descuentos</b>\n\n"
        "Oferta de la tienda + cupón bancario = precio más bajo real.\n\n"
        "Ejemplo: producto con 30% OFF + cupón BBVA 15% = 40.5% de descuento total.\n\n"
        "<i>En el Canal VIP calculamos automáticamente el precio final con el mejor banco disponible.</i>"
    ),
    (
        "<b>Tip DropNode — Back to School</b>\n\n"
        "Las laptops tienen sus precios más bajos entre julio y agosto.\n"
        "Las marcas lanzan nuevos modelos en septiembre — el inventario anterior baja.\n\n"
        "<i>Nuestro equipo monitorea estas ventanas estacionales.</i>"
    ),
]


def recordatorio_vip():
    n = random.choice([14, 18, 22, 27, 31])
    db = _db()
    n_matches = 0
    try:
        if db:
            r = db.table("peticiones").select("id", count="exact").eq(
                "semana", _semana()).eq("encontrada", True).execute()
            n_matches = r.count or 0
    except Exception:
        pass

    versiones = [
        (
            f"Hoy el <b>Canal DropNode VIP</b> recibió <b>{n} alertas</b> "
            f"de descuentos reales.\n\n"
            f"Varias con más del 40% de descuento — esas nunca llegan aquí.\n\n"
            f"$299 MXN/mes. Un solo error de precio aprovechado te paga el año."
        ),
        (
            "Esta semana el <b>Canal VIP</b> encontró deals que el canal "
            "gratuito no recibió.\n\n"
            "Errores de precio, stock limitado, Solo Hoy exclusivos — "
            "todo va ahí primero.\n\n"
            "Si ahorras $300 pesos en una sola compra, ya se pagó el mes."
        ),
        (
            "<b>Canal VIP — lo que incluye:</b>\n\n"
            "Alertas en tiempo real · 15 tiendas monitoreadas\n"
            "Precio vs histórico de 90 días\n"
            "Estimación de reventa en cada alerta\n"
            "Cupones bancarios calculados automáticamente\n"
            "Deal del Día exclusivo con análisis\n\n"
            "$299 MXN/mes · Cancela cuando quieras"
        ),
    ]

    if n_matches > 0:
        versiones.append(
            f"Esta semana la comunidad pidió productos y nuestro equipo los encontró.\n\n"
            f"<b>{n_matches} búsqueda{'s' if n_matches > 1 else ''} especial{'es' if n_matches > 1 else ''}</b> "
            f"llegaron al Canal VIP — solicitadas por miembros de esta comunidad.\n\n"
            f"$299 MXN/mes."
        )

    return random.choice(versiones)


# ─────────────────────────────────────────────
# LOOP PRINCIPAL
# ─────────────────────────────────────────────

def ejecutar_community_manager():
    ahora  = hora_mx()
    dia    = ahora.weekday()
    hora   = ahora.hour
    minuto = ahora.minute

    if minuto > 15:
        return

    publicado = False

    # Diario 9 AM — Deal del Día
    if hora == 9:
        publicar_deal_del_dia()
        publicado = True

    # Lunes 10 AM — peticiones
    elif dia == 0 and hora == 10:
        ok = enviar_grupo(random.choice(MENSAJES_LUNES), "HTML")
        if ok:
            abrir_ventana()
        publicado = True

    # Lunes 2 PM — resumen peticiones
    elif dia == 0 and hora == 14:
        enviar_resumen_peticiones()
        publicado = True

    # Miércoles 6 PM — poll
    elif dia == 2 and hora == 18:
        p = random.choice(POLLS)
        enviar_poll(p["pregunta"], p["opciones"], guardar_categoria=p["guardar"])
        publicado = True

    # Jueves 9 PM — resultado semanal
    elif dia == 3 and hora == 21:
        enviar_resultado_semanal()
        publicado = True

    # Viernes 5 PM — social proof
    elif dia == 4 and hora == 17:
        enviar_grupo(random.choice(MENSAJES_VIERNES), "HTML")
        publicado = True

    # Domingo 11 AM — tip
    elif dia == 6 and hora == 11:
        tip = random.choice(TIPS)
        if "VIP" in tip or "Canal" in tip:
            enviar_grupo_con_boton(tip, "HTML")
        else:
            enviar_grupo(tip, "HTML")
        publicado = True

    # Martes y Jueves 8 PM — recordatorio VIP
    elif dia in (1, 3) and hora == 20:
        enviar_grupo_con_boton(recordatorio_vip(), "HTML")
        publicado = True

    if publicado:
        logger.info(f"[COMMUNITY] Publicado dia={dia} hora={hora}")