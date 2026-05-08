import requests
import logging
import random
from datetime import datetime, timezone, timedelta
from config import TELEGRAM_TOKEN, GROUP_ID, CHANNEL_FREE_ID, LAUNCHPASS_LINK
from peticiones import abrir_ventana, enviar_resumen_peticiones, ventana_activa

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN
TZ_MEXICO    = timezone(timedelta(hours=-6))


def hora_mx():
    return datetime.now(TZ_MEXICO)


def enviar_grupo(texto, modo="HTML"):
    """Mensaje de texto simple al grupo."""
    try:
        r = requests.post(TELEGRAM_API + "/sendMessage", json={
            "chat_id":                  GROUP_ID,
            "text":                     texto,
            "parse_mode":               modo,
            "disable_web_page_preview": True,
        }, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        logger.error("[COMMUNITY] " + str(e))
        return False


def enviar_grupo_con_boton(texto, modo="HTML"):
    """
    Mensaje al grupo con botón inline del canal VIP.
    Usar siempre que el mensaje mencione el VIP.
    """
    try:
        payload = {
            "chat_id":                  GROUP_ID,
            "text":                     texto,
            "parse_mode":               modo,
            "disable_web_page_preview": True,
        }
        if LAUNCHPASS_LINK:
            payload["reply_markup"] = {
                "inline_keyboard": [[{
                    "text": "📲 Unirse al Canal VIP — $299/mes",
                    "url":  LAUNCHPASS_LINK
                }]]
            }
        r = requests.post(TELEGRAM_API + "/sendMessage", json=payload, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        logger.error("[COMMUNITY VIP] " + str(e))
        return False


def enviar_poll(pregunta, opciones):
    try:
        r = requests.post(TELEGRAM_API + "/sendPoll", json={
            "chat_id":      GROUP_ID,
            "question":     pregunta,
            "options":      opciones,
            "is_anonymous": True,
        }, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        logger.error("[POLL] " + str(e))
        return False


# ── Lunes: peticiones ──────────────────────────────────────
# Versiones variadas para no repetir siempre lo mismo

MENSAJES_LUNES = [
    (
        "📝 <b>DropNode te escucha</b>\n\n"
        "Dinos qué producto estás buscando esta semana.\n"
        "Marca, modelo, categoría — lo que sea.\n\n"
        "Nuestro equipo lo pone en el radar y los resultados "
        "aparecen primero en el Canal VIP."
    ),
    (
        "📝 <b>¿Qué buscas comprar esta semana?</b>\n\n"
        "Escríbelo aquí. Si encontramos oferta real, "
        "lo publicamos en el Canal VIP antes que en ningún otro lado.\n\n"
        "Producto, marca o categoría — cualquier cosa cuenta."
    ),
    (
        "📝 <b>Turno de la comunidad</b>\n\n"
        "¿Qué compra tienes pendiente?\n"
        "Nuestro equipo monitorea lo que la comunidad pide.\n\n"
        "Los resultados van al Canal VIP primero."
    ),
]

# ── Miércoles: polls ────────────────────────────────────────

POLLS = [
    {
        "pregunta": "¿Qué categoría te interesa más esta semana?",
        "opciones": ["Celulares y tech", "Laptops y computadoras",
                     "Televisores y audio", "Videojuegos", "Hogar y electrodomésticos"],
    },
    {
        "pregunta": "¿Para qué usas las alertas de DropNode MX?",
        "opciones": ["Compra personal", "Reventa y flipping",
                     "Regalos", "Solo estoy explorando"],
    },
    {
        "pregunta": "¿Cuánto sueles gastar cuando encuentras una buena oferta?",
        "opciones": ["Menos de $500", "$500 - $2,000",
                     "$2,000 - $5,000", "Más de $5,000"],
    },
    {
        "pregunta": "¿Qué tienda tiene las mejores ofertas reales en tu experiencia?",
        "opciones": ["Mercado Libre", "Amazon MX", "Liverpool", "Walmart MX"],
    },
]

# ── Viernes: social proof ───────────────────────────────────

MENSAJES_VIERNES = [
    (
        "Antes de cerrar la semana:\n\n"
        "¿Alguien aprovechó alguna oferta? Cuéntanos qué conseguiste, "
        "a qué precio y dónde.\n\nLa comunidad aprende de todos."
    ),
    (
        "Viernes en DropNode.\n\n"
        "Comparte tu mejor compra de la semana. Precio, producto, tienda.\n\n"
        "Los mejores casos los destacamos en el canal."
    ),
    (
        "Fin de semana. ¿Qué compraste?\n\n"
        "Si usaste alguna de nuestras alertas o encontraste algo por tu cuenta, "
        "dinos. Eso ayuda a toda la comunidad."
    ),
]

# ── Domingo: tips ───────────────────────────────────────────

TIPS = [
    (
        "<b>Tip DropNode — Cómo saber si un descuento es real</b>\n\n"
        "No compares contra el precio tachado. Ese puede estar inflado desde hace meses.\n\n"
        "Compara contra el precio que tenía hace 30-60 días.\n\n"
        "Nuestro equipo hace eso automáticamente. Un descuento real baja del histórico, "
        "no solo del tachado."
    ),
    (
        "<b>Tip DropNode — La hora de los errores de precio</b>\n\n"
        "Los errores de precio ocurren más seguido entre 11 PM y 3 AM, "
        "cuando las tiendas actualizan catálogos.\n\n"
        "También los lunes por la mañana y después de eventos como el Buen Fin.\n\n"
        "<i>Los miembros del Canal VIP reciben estas alertas en cuanto ocurren.</i>"
    ),
    (
        "<b>Tip DropNode — Qué productos valen más para reventa</b>\n\n"
        "En México, de mayor a menor margen:\n"
        "1. iPhones y Samsung desbloqueados\n"
        "2. Consolas de videojuegos\n"
        "3. Laptops gaming\n"
        "4. Audífonos premium\n"
        "5. Smartwatches\n\n"
        "Clave: comprar bajo el precio de ML y revender ahí con 15-25% de margen."
    ),
    (
        "<b>Tip DropNode — Cómo no perder una oferta de stock limitado</b>\n\n"
        "Cuando llega la alerta:\n"
        "1. Entra al link antes de terminar de leer el mensaje\n"
        "2. Agrega al carrito primero\n"
        "3. Decides si compras en los siguientes 5 minutos\n\n"
        "El stock en errores de precio se va en minutos.\n"
        "<i>Esa ventaja de tiempo es exclusiva del Canal VIP.</i>"
    ),
]

# ── Recordatorios VIP ───────────────────────────────────────

def recordatorio_vip():
    """Recordatorio humano del canal VIP. Link via botón inline."""
    n_alertas = random.choice([14, 18, 22, 27, 31])
    versiones = [
        (
            f"Hoy el <b>Canal DropNode VIP</b> recibió <b>{n_alertas} alertas</b> "
            f"de descuentos reales.\n\n"
            f"Tres de ellas eran errores de precio con más del 40% de descuento "
            f"— esas nunca llegan aquí.\n\n"
            f"Suscripción mensual: $299 MXN. Un solo error de precio bien "
            f"aprovechado te paga el año completo."
        ),
        (
            "Esta semana el <b>Canal VIP</b> encontró deals que el canal "
            "gratuito no recibió.\n\n"
            "Errores de precio, stock limitado, cupones combinados — "
            "todo va ahí primero.\n\n"
            "Si ahorras $300 pesos en una sola compra, ya se pagó la "
            "suscripción del mes."
        ),
        (
            "Hay una diferencia entre ver ofertas y actuar antes que los demás.\n\n"
            "<b>Canal VIP DropNode MX</b> — ventaja de tiempo + análisis de "
            "reventa en cada alerta.\n\n"
            "$299 MXN al mes. Cancela cuando quieras."
        ),
    ]
    return random.choice(versiones)


# ── Loop principal ──────────────────────────────────────────

def ejecutar_community_manager():
    ahora  = hora_mx()
    dia    = ahora.weekday()   # 0=lunes ... 6=domingo
    hora   = ahora.hour
    minuto = ahora.minute

    # Ventana de ejecución: primeros 15 min de cada hora
    if minuto > 15:
        return

    publicado = False

    # Lunes 10 AM — pregunta de peticiones
    if dia == 0 and hora == 10:
        ok = enviar_grupo(random.choice(MENSAJES_LUNES), "HTML")
        if ok:
            abrir_ventana()   # Activa la recepción de peticiones
        publicado = True

    # Lunes 14 PM (2 PM MX) — resumen de peticiones recibidas
    elif dia == 0 and hora == 14:
        enviar_resumen_peticiones()
        publicado = True

    # Miércoles 6 PM — poll
    elif dia == 2 and hora == 18:
        p = random.choice(POLLS)
        enviar_poll(p["pregunta"], p["opciones"])
        publicado = True

    # Viernes 5 PM — social proof
    elif dia == 4 and hora == 17:
        enviar_grupo(random.choice(MENSAJES_VIERNES), "HTML")
        publicado = True

    # Domingo 11 AM — tip educativo
    elif dia == 6 and hora == 11:
        tip = random.choice(TIPS)
        # Tips que mencionan VIP → botón inline
        if "VIP" in tip or "Canal" in tip:
            enviar_grupo_con_boton(tip, "HTML")
        else:
            enviar_grupo(tip, "HTML")
        publicado = True

    # Martes y Jueves 8 PM — recordatorio VIP con botón
    elif dia in (1, 3) and hora == 20:
        enviar_grupo_con_boton(recordatorio_vip(), "HTML")
        publicado = True

    if publicado:
        logger.info(f"[COMMUNITY] Publicado dia={dia} hora={hora}")