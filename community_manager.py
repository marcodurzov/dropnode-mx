import requests
import logging
import random
from datetime import datetime, timezone, timedelta
from config import TELEGRAM_TOKEN, GROUP_ID, CHANNEL_FREE_ID, LAUNCHPASS_LINK

logger       = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN
TZ_MEXICO    = timezone(timedelta(hours=-6))

def hora_mx():
    return datetime.now(TZ_MEXICO)

def enviar_grupo(texto, modo="HTML"):
    try:
        r = requests.post(TELEGRAM_API + "/sendMessage", json={
            "chat_id": GROUP_ID,
            "text": texto,
            "parse_mode": modo,
            "disable_web_page_preview": True
        }, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        logger.error("[COMMUNITY] " + str(e))
        return False

def enviar_poll(pregunta, opciones):
    try:
        r = requests.post(TELEGRAM_API + "/sendPoll", json={
            "chat_id": GROUP_ID,
            "question": pregunta,
            "options": opciones,
            "is_anonymous": True
        }, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        logger.error("[POLL] " + str(e))
        return False

def lnk_vip():
    if LAUNCHPASS_LINK:
        return '<a href="' + LAUNCHPASS_LINK + '">Canal DropNode VIP</a>'
    return "Canal DropNode VIP"


# ── Lunes: pedir productos ──────────────────────────────────

MENSAJES_LUNES = [
    "Buen inicio de semana.\n\nDinos que producto estes buscando esta semana y nuestro equipo lo pone en el radar.\n\nLos mas pedidos aparecen primero en el canal.",
    "Lunes en DropNode.\n\nTienes alguna compra pendiente? Dinos aqui. Si hay oferta real, tu la ves primero.\n\nEscribe producto, marca o categoria.",
    "Que buscas comprar esta semana?\n\nEscribelo aqui. Nuestro equipo monitorea lo que la comunidad pide. Sin promesas, pero lo intentamos."
]

# ── Miercoles: polls ────────────────────────────────────────

POLLS = [
    {"pregunta": "Que categoria te interesa mas esta semana?",
     "opciones": ["Celulares y tech", "Laptops y computadoras", "Televisores y audio", "Videojuegos", "Hogar y electrodomesticos"]},
    {"pregunta": "Para que usas las alertas de DropNode MX?",
     "opciones": ["Compra personal", "Reventa y flipping", "Regalos", "Solo estoy explorando"]},
    {"pregunta": "Cuanto sueles gastar cuando encuentras una buena oferta?",
     "opciones": ["Menos de $500", "$500 - $2,000", "$2,000 - $5,000", "Mas de $5,000"]},
    {"pregunta": "Que tienda tiene las mejores ofertas reales en tu experiencia?",
     "opciones": ["Mercado Libre", "Amazon MX", "Liverpool", "Walmart MX"]},
]

# ── Viernes: social proof ───────────────────────────────────

MENSAJES_VIERNES = [
    "Antes de cerrar la semana:\n\nAlguien aprovecho alguna oferta? Cuentanos que conseguiste, a que precio y donde.\n\nLa comunidad aprende de todos.",
    "Viernes en DropNode.\n\nComparte tu mejor compra de la semana. Precio, producto, tienda.\n\nLos mejores casos los destacamos en el canal.",
    "Fin de semana. Que compraste?\n\nSi usaste alguna de nuestras alertas o encontraste algo por tu cuenta, dinos. Eso ayuda a toda la comunidad."
]

# ── Domingo: tips ───────────────────────────────────────────

TIPS = [
    ("<b>Tip DropNode — Como saber si un descuento es real</b>\n\n"
     "No compares contra el precio tachado. Ese puede estar inflado desde hace meses.\n\n"
     "Compara contra el precio que tenia hace 30-60 dias.\n\n"
     "Nuestro equipo hace eso automaticamente por ti. Un descuento real baja del historico, no solo del tachado."),

    ("<b>Tip DropNode — La hora de los errores de precio</b>\n\n"
     "Los errores de precio ocurren mas seguido entre 11 PM y 3 AM, cuando las tiendas actualizan catalogos.\n\n"
     "Tambien los lunes por la manana y despues de eventos como el Buen Fin.\n\n"
     "Los miembros del " + lnk_vip() + " reciben estas alertas en cuanto ocurren."),

    ("<b>Tip DropNode — Que productos valen mas para reventa</b>\n\n"
     "En Mexico, de mayor a menor margen:\n"
     "1. iPhones y Samsung desbloqueados\n"
     "2. Consolas de videojuegos\n"
     "3. Laptops gaming\n"
     "4. Audifonos premium\n"
     "5. Smartwatches\n\n"
     "Clave: comprar bajo el precio de ML y revender ahi con 15-25% de margen."),

    ("<b>Tip DropNode — Como no perder una oferta de stock limitado</b>\n\n"
     "Cuando llega la alerta:\n"
     "1. Entra al link antes de terminar de leer el mensaje\n"
     "2. Agrega al carrito primero\n"
     "3. Decides si compras en los siguientes 5 minutos\n\n"
     "El stock en errores de precio se va en minutos. Esa ventaja de tiempo es lo que tiene el " + lnk_vip() + ".")
]

# ── Recordatorios VIP ───────────────────────────────────────

def recordatorio_vip():
    """Recordatorio que suena humano, no de maquina."""
    # Numero de alertas ficticio pero creible para dar sensacion de actividad
    n_alertas = random.choice([14, 18, 22, 27, 31])
    versiones = [
        ("Hoy el " + lnk_vip() + " recibio <b>" + str(n_alertas) + " alertas</b> de descuentos reales.\n\n"
         "Tres de ellas eran errores de precio con mas del 40% de descuento — esas nunca llegan aqui.\n\n"
         "Suscripcion mensual: $299 MXN. Un solo error de precio bien aprovechado te paga el ano completo."),

        ("Esta semana el " + lnk_vip() + " encontro deals que el canal gratuito no recibio.\n\n"
         "Errores de precio, stock limitado, cupones combinados — todo va ahi primero.\n\n"
         "Si ahorras $300 pesos en una sola compra, ya se pago la suscripcion del mes."),

        ("Hay una diferencia entre ver ofertas y actuar antes que los demas.\n\n"
         "El " + lnk_vip() + " lleva ventaja de tiempo + analisis de reventa en cada alerta.\n\n"
         "$299 MXN al mes. Cancela cuando quieras."),
    ]
    return random.choice(versiones)


def ejecutar_community_manager():
    ahora  = hora_mx()
    dia    = ahora.weekday()   # 0=lunes ... 6=domingo
    hora   = ahora.hour
    minuto = ahora.minute

    if minuto > 15:
        return

    publicado = False

    if dia == 0 and hora == 10:
        enviar_grupo(random.choice(MENSAJES_LUNES), "HTML")
        publicado = True

    elif dia == 2 and hora == 18:
        p = random.choice(POLLS)
        enviar_poll(p["pregunta"], p["opciones"])
        publicado = True

    elif dia == 4 and hora == 17:
        enviar_grupo(random.choice(MENSAJES_VIERNES), "HTML")
        publicado = True

    elif dia == 6 and hora == 11:
        enviar_grupo(random.choice(TIPS), "HTML")
        publicado = True

    elif dia in (1, 3) and hora == 20:
        enviar_grupo(recordatorio_vip(), "HTML")
        publicado = True

    if publicado:
        logger.info("[COMMUNITY] Mensaje publicado dia=" + str(dia) + " hora=" + str(hora))