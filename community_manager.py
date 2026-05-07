import requests
import logging
import random
from datetime import datetime, timezone, timedelta
from config import TELEGRAM_TOKEN, GROUP_ID, CHANNEL_FREE_ID, CHANNEL_VIP_ID, LAUNCHPASS_LINK

logger       = logging.getLogger(__name__)
TELEGRAM_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN
TZ_MEXICO    = timezone(timedelta(hours=-6))

def hora_mx():
    return datetime.now(TZ_MEXICO)

def enviar_mensaje(chat_id, texto):
    try:
        r = requests.post(TELEGRAM_API + "/sendMessage", json={
            "chat_id": chat_id, "text": texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=15)
        d = r.json()
        if d.get("ok"):
            return d["result"]["message_id"]
    except Exception as e:
        logger.error("[MSG] " + str(e))
    return None

def fijar_mensaje(chat_id, message_id):
    try:
        requests.post(TELEGRAM_API + "/pinChatMessage", json={
            "chat_id": chat_id, "message_id": message_id,
            "disable_notification": True
        }, timeout=15)
    except Exception:
        pass

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


# Tabla comparativa Free vs VIP
TABLA_VIP = (
    "*DropNode MX — Free vs VIP*\n\n"
    "```\n"
    "Beneficio               Free    VIP\n"
    "─────────────────────────────────────\n"
    "Alertas por ciclo        3       8\n"
    "Ventaja de tiempo        —      +3 min\n"
    "Descuentos mayores 40%   No      Si\n"
    "Analisis de reventa      No      Si\n"
    "Historial 90 dias        No      Si\n"
    "Alertas nocturnas        No      Si\n"
    "Cupones analizados       No      Si\n"
    "Pedidos de comunidad     No      Si\n"
    "Walmart y Liverpool      No      Si\n"
    "```\n\n"
    "Un solo error de precio bien aprovechado paga la suscripcion del ano.\n\n"
    "*$299 MXN/mes — cancela cuando quieras*\n"
    + LAUNCHPASS_LINK
)

# Mensajes de pedidos respondidos en VIP
def msg_pedido_vip(producto_pedido):
    return (
        "📬 *Pedido de la comunidad — Respuesta VIP*\n\n"
        "Alguien en el grupo de comunidad pidio:\n"
        "_" + producto_pedido + "_\n\n"
        "Nuestro equipo lo puso en el radar.\n"
        "Si encontramos una buena oferta, la publicamos aqui primero.\n\n"
        "_Esta es una de las ventajas de ser VIP: tus pedidos tienen respuesta._"
    )

# Mensajes lunes — peticion de productos
MENSAJES_LUNES = [
    ("*DropNode te escucha*\n\n"
     "Que producto estas buscando esta semana?\n\n"
     "Escribelo aqui. Nuestro equipo lo monitorea y si aparece una buena oferta, "
     "los miembros VIP la reciben primero.\n\n"
     "_Sugerencia = prioridad en el radar._"),
    ("*Inicio de semana en DropNode MX*\n\n"
     "Que compra tienes pendiente?\n\n"
     "Nos lo dices aqui. Si encontramos el precio correcto, "
     "el canal VIP recibe la alerta con tu pedido incluido.\n\n"
     "_Los pedidos de la comunidad solo se responden en el VIP._"),
    ("*Que quieres encontrar esta semana?*\n\n"
     "Escribelo en este grupo. Marca, modelo o categoria.\n\n"
     "El equipo lo busca. Las respuestas van al canal VIP primero."),
]

# Polls miercoles
POLLS_MIERCOLES = [
    {"pregunta": "Que categoria te interesa mas esta semana?",
     "opciones": ["Celulares y smartphones", "Laptops y computadoras", "Televisores y audio", "Videojuegos y consolas", "Electrodomesticos"]},
    {"pregunta": "Para que usas las alertas de DropNode MX?",
     "opciones": ["Compra personal", "Reventa (flipping)", "Para regalar", "Solo explorando"]},
    {"pregunta": "Con que presupuesto compras cuando hay buena oferta?",
     "opciones": ["Menos de $500 MXN", "$500 a $2,000 MXN", "$2,000 a $5,000 MXN", "Mas de $5,000 MXN"]},
    {"pregunta": "Que tienda tiene las mejores ofertas reales?",
     "opciones": ["Mercado Libre", "Amazon MX", "Liverpool", "Walmart MX"]},
]

# Viernes — social proof
MENSAJES_VIERNES = [
    ("*Fin de semana DropNode*\n\n"
     "Alguien aprovecho alguna oferta esta semana?\n\n"
     "Comparte aqui: que compraste, a que precio y donde lo encontraste.\n"
     "Los mejores casos los destacamos en el canal."),
    ("*Esta semana compraste algo con nuestras alertas?*\n\n"
     "Precio, producto, tienda.\n\n"
     "Eso ayuda a toda la comunidad. Y si fue un flip exitoso, contalo."),
    ("*Viernes de resultados*\n\n"
     "Que tal estuvo la semana?\n\n"
     "Si encontraste algo bueno — con o sin nuestras alertas — compartelo aqui."),
]

# Tips domingo
TIPS_DOMINGO = [
    ("*Tip DropNode — Como saber si un descuento es real*\n\n"
     "No compares vs el precio tachado. Ese puede estar inflado artificialmente.\n\n"
     "Compara vs el precio de hace 30 a 60 dias.\n\n"
     "Nuestro equipo hace eso automaticamente con 90 dias de historial. "
     "Un descuento real es cuando el precio actual esta por debajo de su historico, "
     "no solo por debajo del tachado."),
    ("*Tip DropNode — Los errores de precio ocurren mas en estas horas*\n\n"
     "Entre 11 PM y 3 AM cuando los sistemas se actualizan.\n"
     "Los lunes por la manana al cargar nuevos catalogos.\n"
     "Justo despues del Buen Fin en liquidaciones reales.\n\n"
     "El canal VIP recibe estas alertas en segundos, incluyendo las de madrugada."),
    ("*Tip DropNode — Que productos tienen mejor margen de reventa en Mexico*\n\n"
     "1. iPhones y Samsung desbloqueados\n"
     "2. Consolas de videojuegos\n"
     "3. Laptops gaming\n"
     "4. Audifonos premium (AirPods, Sony, Bose)\n"
     "5. Smartwatches\n\n"
     "La clave: comprar por debajo del precio promedio de ML y revender ahi mismo "
     "con 15 a 25 por ciento de margen. El VIP incluye la estimacion de reventa en cada alerta."),
    ("*Tip DropNode — Como no perder una oferta de stock limitado*\n\n"
     "1. Activa notificaciones del canal\n"
     "2. Cuando llegue la alerta: entra al link antes de leer el mensaje completo\n"
     "3. Agrega al carrito primero, lee los detalles despues\n"
     "4. Si en 5 minutos no te convence, lo quitas\n\n"
     "En errores de precio el stock se agota en minutos. "
     "Los 3 minutos de ventaja del VIP son la diferencia entre comprar y llegar tarde."),
]

# Recordatorios VIP en el grupo
RECORDATORIOS_VIP_GRUPO = [
    TABLA_VIP,
    ("*Por que el VIP vale $299 MXN/mes?*\n\n"
     "Porque un solo error de precio bien aprovechado paga la suscripcion.\n\n"
     "Un iPhone con 40% de descuento que compras en $8,000 y vendes en $12,000 "
     "cubre 13 meses de VIP con una sola operacion.\n\n"
     "El canal free da el sabor. El VIP da la oportunidad.\n\n"
     + LAUNCHPASS_LINK),
    ("*Los miembros VIP reciben hoy:*\n\n"
     "Hasta 8 alertas por ciclo con 3 minutos de ventaja\n"
     "Descuentos mayores al 40 por ciento exclusivos\n"
     "Analisis de precio historico de 90 dias\n"
     "Estimacion de reventa por producto\n"
     "Respuesta a pedidos de la comunidad\n"
     "Alertas nocturnas de errores de precio\n\n"
     "El canal free recibe 3 alertas. El VIP recibe todo lo demas.\n\n"
     + LAUNCHPASS_LINK),
]

# Recordatorio en canal free (diferente tono)
RECORDATORIOS_VIP_FREE = [
    ("🔒 *Acceso VIP — DropNode MX*\n\n"
     "Lo que el canal free no muestra:\n"
     "Descuentos mayores al 40 por ciento\n"
     "Analisis de reventa por producto\n"
     "Alertas 3 minutos antes\n"
     "Errores de precio en madrugada\n"
     "Respuesta a tus pedidos de productos\n\n"
     "*$299 MXN/mes*\n"
     + LAUNCHPASS_LINK),
    TABLA_VIP,
]


def publicar_tabla_vip_grupo():
    mid = enviar_mensaje(GROUP_ID, TABLA_VIP)
    if mid:
        fijar_mensaje(GROUP_ID, mid)
        logger.info("[COMMUNITY] Tabla VIP publicada y fijada en grupo")

def publicar_tabla_vip_free():
    mid = enviar_mensaje(CHANNEL_FREE_ID, TABLA_VIP)
    if mid:
        fijar_mensaje(CHANNEL_FREE_ID, mid)
        logger.info("[COMMUNITY] Tabla VIP publicada y fijada en canal free")


def ejecutar_community_manager():
    ahora  = hora_mx()
    dia    = ahora.weekday()
    hora   = ahora.hour
    minuto = ahora.minute

    if minuto > 15:
        return

    publicado = False

    # Lunes 10 AM — peticion de productos (respuesta solo en VIP)
    if dia == 0 and hora == 10:
        msg = random.choice(MENSAJES_LUNES)
        enviar_mensaje(GROUP_ID, msg)
        publicado = True
        logger.info("[COMMUNITY] Lunes - peticion de productos")

    # Miercoles 6 PM — poll
    elif dia == 2 and hora == 18:
        p = random.choice(POLLS_MIERCOLES)
        enviar_poll(p["pregunta"], p["opciones"])
        publicado = True
        logger.info("[COMMUNITY] Miercoles - poll")

    # Viernes 5 PM — social proof
    elif dia == 4 and hora == 17:
        msg = random.choice(MENSAJES_VIERNES)
        enviar_mensaje(GROUP_ID, msg)
        publicado = True
        logger.info("[COMMUNITY] Viernes - social proof")

    # Domingo 11 AM — tip educativo
    elif dia == 6 and hora == 11:
        msg = random.choice(TIPS_DOMINGO)
        enviar_mensaje(GROUP_ID, msg)
        publicado = True
        logger.info("[COMMUNITY] Domingo - tip educativo")

    # Martes y Jueves 8 PM — tabla VIP en grupo y recordatorio en free
    elif dia in (1, 3) and hora == 20:
        msg_grupo = random.choice(RECORDATORIOS_VIP_GRUPO)
        enviar_mensaje(GROUP_ID, msg_grupo)
        msg_free = random.choice(RECORDATORIOS_VIP_FREE)
        enviar_mensaje(CHANNEL_FREE_ID, msg_free)
        publicado = True
        logger.info("[COMMUNITY] Recordatorio VIP en grupo y free")

    # Sabado 12 PM — tabla VIP fijada (se actualiza semanalmente)
    elif dia == 5 and hora == 12:
        publicar_tabla_vip_grupo()
        publicar_tabla_vip_free()
        publicado = True
        logger.info("[COMMUNITY] Sabado - tabla VIP fijada")

    if publicado:
        logger.info("[COMMUNITY] Ejecutado - dia=" + str(dia) + " hora=" + str(hora))