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

def enviar_grupo(texto):
    try:
        r = requests.post(TELEGRAM_API + "/sendMessage", json={
            "chat_id": GROUP_ID, "text": texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        logger.error("[COMMUNITY] " + str(e))
        return False

def enviar_poll(pregunta, opciones):
    try:
        r = requests.post(TELEGRAM_API + "/sendPoll", json={
            "chat_id": GROUP_ID, "question": pregunta,
            "options": opciones, "is_anonymous": True
        }, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        logger.error("[POLL] " + str(e))
        return False


MENSAJES_LUNES = [
    "*DropNode te escucha*\n\nComienza la semana. Dinos: que producto estas buscando?\n\nNuestro equipo monitorea lo que la comunidad pide. Los mas solicitados van al canal primero.\n\nEscribe aqui: marca, modelo o categoria.",
    "*Inicio de semana en DropNode MX*\n\nQue compra tienes pendiente esta semana?\n\nNos lo dices aqui y lo ponemos en el radar. Sin promesas, pero lo intentamos.",
    "*Que quieres encontrar esta semana?*\n\nNuestro equipo esta monitoreando. Si hay algo especifico que buscas, dilo aqui.\n\nLos mas pedidos aparecen primero en el canal.",
]

POLLS_MIERCOLES = [
    {"pregunta": "Que categoria te interesa mas esta semana?",
     "opciones": ["Celulares y smartphones", "Laptops y computadoras", "Televisores y audio", "Videojuegos y consolas", "Electrodomesticos"]},
    {"pregunta": "Para que usas mas las alertas de DropNode MX?",
     "opciones": ["Para mi uso personal", "Para revender (flipping)", "Para regalar", "Solo estoy explorando"]},
    {"pregunta": "Con que presupuesto sueles comprar cuando hay buena oferta?",
     "opciones": ["Menos de $500 MXN", "$500 - $2,000 MXN", "$2,000 - $5,000 MXN", "Mas de $5,000 MXN"]},
    {"pregunta": "Que tienda tiene las mejores ofertas reales en tu experiencia?",
     "opciones": ["Mercado Libre", "Amazon MX", "Liverpool", "Walmart MX"]},
]

MENSAJES_VIERNES = [
    "*Fin de semana DropNode MX*\n\nAlguien aprovecho alguna oferta esta semana?\n\nCuentanos: que compraste, a que precio y donde. La comunidad aprende de todos.\n\nLos mejores casos los destacamos en el canal.",
    "*Esta semana compraste algo con nuestras alertas?*\n\nDinos que conseguiste. Precio, producto, donde.\n\nEso ayuda a toda la comunidad a entender que vale la pena.",
    "*Viernes de resultados*\n\nQue tal estuvo la semana en ofertas?\n\nSi compraste algo bueno, comparte aqui. Si encontraste algo que no enviamos, tambien nos interesa saber.",
]

TIPS_DOMINGO = [
    "*Tip DropNode - Como saber si un descuento es real*\n\nNo compares vs el precio tachado. Ese puede estar inflado.\n\nCompara vs el precio de hace 30-60 dias.\n\nNuestro equipo hace eso automaticamente. Un descuento real es cuando el precio actual esta por debajo de su historico, no solo por debajo del tachado.",
    "*Tip DropNode - La hora de los errores de precio*\n\nLos errores de precio ocurren mas seguido entre 11 PM y 3 AM cuando los sistemas se actualizan.\n\nTambien los lunes por la manana y justo despues del Buen Fin.\n\nNuestro equipo monitorea 24 horas. El VIP recibe estas alertas en segundos.",
    "*Tip DropNode - Que productos tienen mejor margen de reventa*\n\nEn orden para el mercado mexicano:\n1. iPhones y Samsung desbloqueados\n2. Consolas de videojuegos\n3. Laptops gaming\n4. Audifonos premium\n5. Smartwatches\n\nLa clave: comprar por debajo del precio de ML y revender ahi mismo con 15-25% de margen.",
    "*Tip DropNode - Como no perder una oferta de stock limitado*\n\n1. Activa notificaciones del canal\n2. Cuando llegue la alerta: entra al link ANTES de leer el mensaje completo\n3. Agrega al carrito primero\n4. Si en 5 minutos no te convence, lo quitas\n\nEl stock en errores de precio se agota en minutos. La velocidad es la ventaja del VIP.",
]

RECORDATORIOS_VIP = [
    "*Canal VIP DropNode MX*\n\nLo que incluye:\n- Alertas en tiempo real (3 min antes que el canal free)\n- Analisis de precio historico de 90 dias\n- Estimacion de reventa\n- Alertas de stock critico\n- Cupones exclusivos\n\n$299 MXN/mes\n" + LAUNCHPASS_LINK,
    "*Mientras lees esto...*\n\nLos miembros VIP ya recibieron las alertas de hoy con analisis completo.\n\nUn solo error de precio bien aprovechado paga la suscripcion del ano.\n\n" + LAUNCHPASS_LINK,
    "*Por que pagar el VIP?*\n\nEl canal free recibe 3 alertas por run.\nEl VIP recibe hasta 8, con 3 minutos de ventaja.\n\nEn ofertas de stock limitado, 3 minutos es la diferencia entre comprar y llegar tarde.\n\n$299 MXN/mes - cancela cuando quieras\n" + LAUNCHPASS_LINK,
]


def ejecutar_community_manager():
    ahora  = hora_mx()
    dia    = ahora.weekday()
    hora   = ahora.hour
    minuto = ahora.minute

    if minuto > 15:
        return

    publicado = False

    if dia == 0 and hora == 10:
        msg = random.choice(MENSAJES_LUNES)
        enviar_grupo(msg)
        publicado = True
        logger.info("[COMMUNITY] Lunes - peticion de productos")

    elif dia == 2 and hora == 18:
        p = random.choice(POLLS_MIERCOLES)
        enviar_poll(p["pregunta"], p["opciones"])
        publicado = True
        logger.info("[COMMUNITY] Miercoles - poll")

    elif dia == 4 and hora == 17:
        msg = random.choice(MENSAJES_VIERNES)
        enviar_grupo(msg)
        publicado = True
        logger.info("[COMMUNITY] Viernes - social proof")

    elif dia == 6 and hora == 11:
        msg = random.choice(TIPS_DOMINGO)
        enviar_grupo(msg)
        publicado = True
        logger.info("[COMMUNITY] Domingo - tip educativo")

    elif dia in (1, 3) and hora == 20:
        if LAUNCHPASS_LINK:
            msg = random.choice(RECORDATORIOS_VIP)
            enviar_grupo(msg)
            publicado = True
            logger.info("[COMMUNITY] Recordatorio VIP en grupo")

    if publicado:
        logger.info("[COMMUNITY] Mensaje enviado al grupo")