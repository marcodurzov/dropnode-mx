# =============================================================
# DROPNODE MX — community_manager.py
# Mensajes automaticos de engagement para el grupo Community
# Genera conversacion, cercania y datos de la audiencia
# =============================================================

import requests, logging, random
from datetime import datetime, timezone, timedelta
from config import TELEGRAM_TOKEN, GROUP_ID, CHANNEL_FREE_ID, LAUNCHPASS_LINK

logger       = logging.getLogger(__name__)
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TZ_MEXICO    = timezone(timedelta(hours=-6))

def hora_mx():
    return datetime.now(TZ_MEXICO)


# ─────────────────────────────────────────────
#  POLLS (encuestas nativas de Telegram)
# ─────────────────────────────────────────────

def enviar_poll(chat_id: int, pregunta: str,
                opciones: list, anonimo: bool = True):
    """
    Envia una encuesta nativa de Telegram.
    Los resultados se ven en tiempo real dentro del grupo.
    """
    try:
        resp = requests.post(f"{TELEGRAM_API}/sendPoll", json={
            "chat_id":    chat_id,
            "question":   pregunta,
            "options":    opciones,
            "is_anonymous": anonimo,
        }, timeout=15)
        data = resp.json()
        if data.get("ok"):
            logger.info(f"[POLL] Enviado: {pregunta[:40]}")
            return data["result"]["message_id"]
        else:
            logger.error(f"[POLL] Error: {data.get('description')}")
    except Exception as e:
        logger.error(f"[POLL] {e}")
    return None

def enviar_mensaje_grupo(texto: str):
    """Envia mensaje de texto al grupo Community."""
    try:
        resp = requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id":    GROUP_ID,
            "text":       texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=15)
        return resp.json().get("ok", False)
    except Exception as e:
        logger.error(f"[COMMUNITY] {e}")
        return False


# ─────────────────────────────────────────────
#  MENSAJES POR DIA DE LA SEMANA
# ─────────────────────────────────────────────

def mensaje_lunes():
    """Lunes 10 AM — Peticion de productos."""
    preguntas = [
        ("¿Que producto estas buscando esta semana?\n\n"
         "Dinos aqui y nuestro equipo lo monitorea.\n"
         "Los mas pedidos van al canal primero."),
        ("Inicio de semana en DropNode MX\n\n"
         "¿Que compra tienes pendiente?\n"
         "Ponlo aqui y lo buscamos para ti."),
        ("¿Que producto quieres encontrar a buen precio esta semana?\n\n"
         "Respondenos aqui — monitoreamos lo que la comunidad pide."),
    ]
    return random.choice(preguntas)

def poll_miercoles():
    """Miercoles 6 PM — Poll de categoria."""
    polls = [
        {
            "pregunta": "¿Que categoria te interesa mas esta semana?",
            "opciones": ["📱 Celulares y smartphones",
                         "💻 Laptops y computadoras",
                         "📺 Televisores y audio",
                         "🎮 Videojuegos",
                         "🏠 Electrodomesticos"]
        },
        {
            "pregunta": "¿Para que usas mas las alertas de DropNode MX?",
            "opciones": ["Para compra personal",
                         "Para revender (flipping)",
                         "Para regalar",
                         "Solo estoy viendo como funciona"]
        },
        {
            "pregunta": "¿Que tienda prefieres para comprar tech?",
            "opciones": ["Amazon MX", "Mercado Libre",
                         "Liverpool", "Walmart MX", "Otra"]
        },
        {
            "pregunta": "¿Con que presupuesto sueles comprar cuando hay una buena oferta?",
            "opciones": ["Menos de $500 MXN",
                         "$500 - $2,000 MXN",
                         "$2,000 - $5,000 MXN",
                         "Mas de $5,000 MXN"]
        },
    ]
    return random.choice(polls)

def mensaje_viernes():
    """Viernes 5 PM — Social proof y comunidad."""
    mensajes = [
        ("¿Alguien aprovecho alguna oferta esta semana?\n\n"
         "Comparte aqui tu compra — precio, producto y donde lo encontraste.\n"
         "La comunidad aprende de todos."),
        ("Fin de semana en DropNode MX\n\n"
         "¿Cual fue la mejor oferta que encontraste esta semana?\n"
         "Cuéntanos — eso ayuda a toda la comunidad."),
        ("¿Compraste algo con nuestras alertas esta semana?\n\n"
         "Dinos que conseguiste y a que precio.\n"
         "Los mejores casos los destacamos en el canal."),
    ]
    return random.choice(mensajes)

def mensaje_domingo():
    """Domingo 11 AM — Tip educativo."""
    tips = [
        ("*Tip DropNode MX — Como saber si un descuento es real*\n\n"
         "El truco: no compares vs el precio tachado.\n"
         "Ese precio puede estar inflado.\n\n"
         "Compara vs el precio de hace 30-60 dias.\n"
         "Nuestro equipo hace eso automaticamente para ti.\n\n"
         "_Un descuento real es cuando el precio actual esta "
         "por debajo de su historico, no solo por debajo del tachado._"),
        ("*Tip DropNode MX — La hora de los errores de precio*\n\n"
         "Los errores de precio en Mexico ocurren mas frecuentemente:\n"
         "Entre 11 PM y 3 AM (actualizaciones de sistemas)\n"
         "Lunes por la manana (carga masiva de catalogos)\n"
         "Dias despues de el Buen Fin (liquidaciones reales)\n\n"
         "_Nuestro equipo monitorea las 24 horas. "
         "El canal VIP recibe estas alertas en segundos._"),
        ("*Tip DropNode MX — Que productos tienen mejor margen de reventa*\n\n"
         "En orden de rentabilidad para flipping en Mexico:\n"
         "1. iPhones y smartphones desbloqueados\n"
         "2. Consolas de videojuegos\n"
         "3. Laptops gaming\n"
         "4. Audifonos premium (AirPods, Sony, Bose)\n"
         "5. Smartwatches\n\n"
         "_La clave es comprar por debajo del precio de ML "
         "y revender ahi mismo con 15-25% de margen._"),
        ("*Tip DropNode MX — Como no perder una oferta de stock limitado*\n\n"
         "1. Activa las notificaciones del canal\n"
         "2. Cuando llegue la alerta, entra al link antes de leer el mensaje completo\n"
         "3. Agrega al carrito primero, lee los detalles despues\n"
         "4. Si en 5 minutos decides que no lo quieres, lo quitas del carrito\n\n"
         "_El stock en errores de precio se agota en minutos. "
         "La velocidad es la ventaja del canal VIP._"),
    ]
    return random.choice(tips)

def recordatorio_vip_grupo():
    """Recordatorio VIP sutil en el grupo — 2 veces por semana."""
    mensajes = [
        (f"*Canal VIP DropNode MX*\n\n"
         f"Las alertas de errores de precio y stock critico "
         f"llegan ahi primero.\n\n"
         f"Los miembros del grupo que ya estan en VIP "
         f"reciben las alertas con ventaja de tiempo.\n\n"
         f"$299 MXN/mes\n{LAUNCHPASS_LINK}"),
        (f"*¿Ya eres miembro VIP?*\n\n"
         f"El canal VIP incluye:\n"
         f"Alertas en tiempo real\n"
         f"Analisis de reventa\n"
         f"Reporte semanal exclusivo\n\n"
         f"{LAUNCHPASS_LINK}"),
    ]
    return random.choice(mensajes)


# ─────────────────────────────────────────────
#  FUNCION PRINCIPAL — llamada desde main.py
# ─────────────────────────────────────────────

def ejecutar_community_manager():
    """
    Ejecuta el mensaje o poll correspondiente al dia y hora.
    Llamar desde main.py cada hora para verificar si hay algo que publicar.
    """
    ahora  = hora_mx()
    dia    = ahora.weekday()   # 0=lunes, 6=domingo
    hora   = ahora.hour
    minuto = ahora.minute

    # Solo actuar en los primeros 15 minutos de la hora objetivo
    if minuto > 15:
        return

    publicado = False

    # Lunes 10 AM — Peticion de productos
    if dia == 0 and hora == 10:
        enviar_mensaje_grupo(mensaje_lunes())
        publicado = True

    # Miercoles 6 PM — Poll de categoria
    elif dia == 2 and hora == 18:
        p = poll_miercoles()
        enviar_poll(GROUP_ID, p["pregunta"], p["opciones"])
        publicado = True

    # Viernes 5 PM — Social proof
    elif dia == 4 and hora == 17:
        enviar_mensaje_grupo(mensaje_viernes())
        publicado = True

    # Domingo 11 AM — Tip educativo
    elif dia == 6 and hora == 11:
        enviar_mensaje_grupo(mensaje_domingo())
        publicado = True

    # Martes y jueves 8 PM — Recordatorio VIP en el grupo
    elif dia in (1, 3) and hora == 20:
        enviar_mensaje_grupo(recordatorio_vip_grupo())
        publicado = True

    if publicado:
        logger.info(f"[COMMUNITY] Mensaje publicado — dia={dia} hora={hora}h")
