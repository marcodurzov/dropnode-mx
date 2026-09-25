# =============================================================
# DROPNODE MX — temporadas.py
# Sistema de inteligencia estacional
# Detecta temporada activa, ajusta scoring, envía alertas previas
# y genera contenido específico por evento
# =============================================================

import os
import requests
import logging
import random
from datetime import datetime, timezone, timedelta, date

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHANNEL_VIP_ID  = int(os.environ.get("CHANNEL_VIP_ID", "0"))
CHANNEL_FREE_ID = int(os.environ.get("CHANNEL_FREE_ID", "0"))
LAUNCHPASS_LINK = os.environ.get("LAUNCHPASS_LINK", "").strip()
SUPABASE_URL    = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY", "").strip()

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
TZ_MEXICO    = timezone(timedelta(hours=-6))


def hoy_mx() -> date:
    return datetime.now(TZ_MEXICO).date()


def hora_mx() -> datetime:
    return datetime.now(TZ_MEXICO)


# ─────────────────────────────────────────────
# CALENDARIO DE TEMPORADAS
# Actualizar fechas cada año — solo cambiar los valores
# ─────────────────────────────────────────────

TEMPORADAS = {

    # ── GRAN TEMPORADA: BUEN FIN ──
    "buen_fin": {
        "nombre":           "El Buen Fin",
        "emoji":            "🛍️",
        "inicio":           date(2026, 11, 13),
        "fin":              date(2026, 11, 16),
        "prep_dias":        21,    # Empezar a avisar 3 semanas antes
        "score_bonus":      2.0,   # Sumar al score de cualquier producto
        "categorias_hot":   ["electronica", "hogar", "moda", "celulares", "laptops"],
        "descuento_min_vip": 0.20, # En Buen Fin bajar el umbral VIP a 20%
        "vip_preview": (
            "🛍️ *Preparación Buen Fin — Solo Canal VIP*\n\n"
            "En {dias} días arranca el Buen Fin.\n\n"
            "Nuestro equipo ya identificó los productos que históricamente "
            "tienen los mejores descuentos reales — no los descuentos inflados.\n\n"
            "*Lo que monitoreamos especialmente:*\n"
            "Televisores 55\"+ · Laptops gaming · Smartphones flagship · "
            "Línea blanca · Audífonos premium\n\n"
            "_Activamos monitoreo intensivo 24/7 desde hoy._"
        ),
        "free_inicio": (
            "🛍️ <b>Arrancó el Buen Fin</b>\n\n"
            "Nuestro equipo está revisando en tiempo real.\n"
            "Las mejores oportunidades llegan al Canal VIP primero."
        ),
        "tip_compra": (
            "💡 *Tip Buen Fin — Canal VIP*\n\n"
            "No compres en las primeras 2 horas. Las tiendas publican precios "
            "inflados para 'bajarlos' después.\n\n"
            "Nosotros comparamos contra 90 días de historial — solo publicamos "
            "cuando el descuento es real vs el precio anterior, no vs el precio inflado de hoy."
        ),
    },

    # ── BLACK FRIDAY ──
    "black_friday": {
        "nombre":           "Black Friday",
        "emoji":            "⚫",
        "inicio":           date(2026, 11, 27),
        "fin":              date(2026, 11, 27),
        "prep_dias":        14,
        "score_bonus":      1.5,
        "categorias_hot":   ["electronica", "celulares", "laptops", "gaming"],
        "descuento_min_vip": 0.25,
        "vip_preview": (
            "⚫ *Black Friday — Preparación VIP*\n\n"
            "En {dias} días. Amazon MX y ML suelen tener los mejores errores "
            "de precio exactamente a las 12:00 AM.\n\n"
            "Activa notificaciones del canal ahora — en Black Friday "
            "los deals de electrónica duran minutos."
        ),
        "free_inicio": (
            "⚫ <b>Black Friday arrancó</b>\n\n"
            "El equipo monitorea en tiempo real.\n"
            "Los mejores deals van al Canal VIP primero."
        ),
        "tip_compra": (
            "⚫ *Tip Black Friday — Canal VIP*\n\n"
            "En México el Black Friday real es solo viernes. "
            "El 'Black Weekend' suele tener precios ya subidos.\n\n"
            "Hoy es el día. Actúa rápido cuando llegue la alerta."
        ),
    },

    # ── CYBER MONDAY ──
    "cyber_monday": {
        "nombre":           "Cyber Monday",
        "emoji":            "💻",
        "inicio":           date(2026, 11, 30),
        "fin":              date(2026, 11, 30),
        "prep_dias":        7,
        "score_bonus":      1.5,
        "categorias_hot":   ["laptops", "tablets", "gaming", "electronica"],
        "descuento_min_vip": 0.25,
        "vip_preview": (
            "💻 *Cyber Monday — {dias} días*\n\n"
            "Enfocado en tecnología. Laptops, tablets y gaming "
            "suelen tener los mejores precios reales del año este día."
        ),
        "free_inicio": (
            "💻 <b>Cyber Monday</b>\n\n"
            "Los mejores deals de tecnología del año.\n"
            "Canal VIP recibe primero."
        ),
        "tip_compra": None,
    },

    # ── NAVIDAD ──
    "navidad": {
        "nombre":           "Navidad",
        "emoji":            "🎄",
        "inicio":           date(2026, 12, 1),
        "fin":              date(2026, 12, 24),
        "prep_dias":        30,
        "score_bonus":      1.0,
        "categorias_hot":   ["juguetes", "moda", "hogar", "gaming", "mascotas"],
        "descuento_min_vip": 0.20,
        "vip_preview": (
            "🎄 *Temporada Navidad — Preparación VIP*\n\n"
            "En {dias} días arranca diciembre.\n\n"
            "*Categorías con más descuentos reales en Navidad:*\n"
            "Juguetes · Consolas · Ropa de temporada · "
            "Artículos para bebé · Decoración\n\n"
            "_Nuestro equipo intensifica el monitoreo en estas categorías._"
        ),
        "free_inicio": (
            "🎄 <b>Temporada Navidad arrancó</b>\n\n"
            "El equipo busca los mejores regalos con descuento real.\n"
            "Canal VIP recibe primero."
        ),
        "tip_compra": (
            "🎄 *Tip Navidad — Canal VIP*\n\n"
            "Los juguetes más populares se agotan antes del 15 de diciembre.\n"
            "Si ves algo con buen precio para regalar, actúa — no esperes al 24."
        ),
    },

    # ── REYES MAGOS ──
    "reyes": {
        "nombre":           "Reyes Magos",
        "emoji":            "👑",
        "inicio":           date(2026, 12, 26),
        "fin":              date(2027, 1, 6),
        "prep_dias":        14,
        "score_bonus":      1.0,
        "categorias_hot":   ["juguetes", "gaming", "ropa_ninos"],
        "descuento_min_vip": 0.20,
        "vip_preview": (
            "👑 *Reyes Magos — {dias} días*\n\n"
            "Juguetes y gaming siguen con buenos precios post-Navidad.\n"
            "El 26 de diciembre suelen aparecer liquidaciones de temporada."
        ),
        "free_inicio": (
            "👑 <b>Temporada Reyes Magos</b>\n\n"
            "Juguetes y regalos para niños con descuento real.\n"
            "Canal VIP recibe primero."
        ),
        "tip_compra": None,
    },

    # ── SAN VALENTÍN ──
    "san_valentin": {
        "nombre":           "San Valentín",
        "emoji":            "❤️",
        "inicio":           date(2027, 2, 7),
        "fin":              date(2027, 2, 14),
        "prep_dias":        21,
        "score_bonus":      0.5,
        "categorias_hot":   ["joyeria", "perfumes", "chocolates", "flores", "moda"],
        "descuento_min_vip": 0.15,
        "vip_preview": (
            "❤️ *San Valentín — {dias} días*\n\n"
            "Perfumes, joyería y moda son los más buscados.\n"
            "Los precios suben cerca del 14 — actúa antes."
        ),
        "free_inicio": (
            "❤️ <b>Semana de San Valentín</b>\n\n"
            "El equipo busca los mejores regalos con precio real."
        ),
        "tip_compra": None,
    },

    # ── DÍA DE MADRES ──
    "dia_madres": {
        "nombre":           "Día de las Madres",
        "emoji":            "💐",
        "inicio":           date(2027, 5, 3),
        "fin":              date(2027, 5, 10),
        "prep_dias":        21,
        "score_bonus":      0.8,
        "categorias_hot":   ["joyeria", "perfumes", "moda", "hogar", "spa"],
        "descuento_min_vip": 0.15,
        "vip_preview": (
            "💐 *Día de Madres — {dias} días*\n\n"
            "El evento más importante del comercio en México.\n\n"
            "Perfumes, joyería, electrodomésticos y ropa de mujer "
            "son los más buscados — y donde los errores de precio aparecen más."
        ),
        "free_inicio": (
            "💐 <b>Semana del Día de las Madres</b>\n\n"
            "Los mejores regalos con precio real en el Canal VIP."
        ),
        "tip_compra": None,
    },

    # ── HOT SALE ──
    "hot_sale": {
        "nombre":           "Hot Sale",
        "emoji":            "🔥",
        "inicio":           date(2027, 5, 26),
        "fin":              date(2027, 6, 3),
        "prep_dias":        14,
        "score_bonus":      1.5,
        "categorias_hot":   ["electronica", "celulares", "laptops", "hogar", "moda"],
        "descuento_min_vip": 0.15,
        "vip_preview": (
            "🔥 *Hot Sale — {dias} días*\n\n"
            "El evento de e-commerce más grande de México.\n"
            "Activa notificaciones del VIP — los mejores deals "
            "aparecen en las primeras 2 horas del primer día."
        ),
        "free_inicio": (
            "🔥 <b>Arrancó el Hot Sale</b>\n\n"
            "El equipo monitorea en tiempo real todas las tiendas."
        ),
        "tip_compra": (
            "🔥 *Tip Hot Sale — Canal VIP*\n\n"
            "Combina los descuentos del Hot Sale con los cupones bancarios activos.\n"
            "En el Canal VIP calculamos el precio real después de aplicar el mejor cupón disponible."
        ),
    },

    # ── BACK TO SCHOOL ──
    "back_to_school": {
        "nombre":           "Back to School",
        "emoji":            "🎒",
        "inicio":           date(2026, 7, 15),
        "fin":              date(2026, 8, 31),
        "prep_dias":        21,
        "score_bonus":      0.8,
        "categorias_hot":   ["laptops", "mochilas", "tablets", "papeleria", "ropa"],
        "descuento_min_vip": 0.15,
        "vip_preview": (
            "🎒 *Back to School — {dias} días*\n\n"
            "Laptops, tablets y mochilas son lo más buscado.\n"
            "Nuestro equipo intensifica el monitoreo en estas categorías."
        ),
        "free_inicio": (
            "🎒 <b>Temporada Back to School</b>\n\n"
            "Laptops, tablets y útiles con precio real. Canal VIP recibe primero."
        ),
        "tip_compra": None,
    },

    # ── HALLOWEEN ──
    "halloween": {
        "nombre":           "Halloween",
        "emoji":            "🎃",
        "inicio":           date(2026, 10, 15),
        "fin":              date(2026, 10, 31),
        "prep_dias":        21,
        "score_bonus":      0.5,
        "categorias_hot":   ["disfraces", "dulces", "decoracion", "juguetes"],
        "descuento_min_vip": 0.15,
        "vip_preview": (
            "🎃 *Halloween — {dias} días*\n\n"
            "Disfraces y decoración tienen sus mejores precios 2 semanas antes.\n"
            "El 31 ya todo sube o se agota."
        ),
        "free_inicio": (
            "🎃 <b>Temporada Halloween</b>\n\n"
            "Disfraces y decoración con descuento real."
        ),
        "tip_compra": None,
    },

    # ── VERANO / PLAYA ──
    "verano": {
        "nombre":           "Verano y Playa",
        "emoji":            "🏖️",
        "inicio":           date(2026, 6, 15),
        "fin":              date(2026, 8, 15),
        "prep_dias":        30,
        "score_bonus":      0.3,
        "categorias_hot":   ["ropa_verano", "deportes", "viajes", "playeras"],
        "descuento_min_vip": 0.15,
        "vip_preview": (
            "🏖️ *Temporada Verano — {dias} días*\n\n"
            "Ropa de temporada, artículos deportivos y accesorios de viaje "
            "tienen las mayores liquidaciones al inicio del verano."
        ),
        "free_inicio": (
            "🏖️ <b>Temporada Verano</b>\n\n"
            "Los mejores precios en ropa y deportes. Canal VIP primero."
        ),
        "tip_compra": None,
    },
}


# ─────────────────────────────────────────────
# FUNCIONES PRINCIPALES
# ─────────────────────────────────────────────

def temporada_activa() -> tuple:
    """Retorna (key, info) de la temporada activa hoy, o (None, None)."""
    hoy = hoy_mx()
    for key, t in TEMPORADAS.items():
        if t["inicio"] <= hoy <= t["fin"]:
            return key, t
    return None, None


def temporada_proxima() -> tuple:
    """Retorna (key, info, dias_restantes) del próximo evento."""
    hoy = hoy_mx()
    proximas = []
    for key, t in TEMPORADAS.items():
        if t["inicio"] > hoy:
            dias = (t["inicio"] - hoy).days
            if dias <= t["prep_dias"]:
                proximas.append((key, t, dias))
    if not proximas:
        return None, None, 0
    proximas.sort(key=lambda x: x[2])
    return proximas[0]


def score_bonus_temporada(categoria: str = "") -> float:
    """Bonus de score según temporada activa y categoría."""
    key, t = temporada_activa()
    if not t:
        # Revisar si hay evento próximo (últimos 3 días antes)
        pk, pt, dias = temporada_proxima()
        if pt and dias <= 3:
            return pt["score_bonus"] * 0.5
        return 0.0

    bonus = t["score_bonus"]
    # Bonus adicional si la categoría es hot para esta temporada
    cat_lower = categoria.lower()
    for cat_hot in t.get("categorias_hot", []):
        if cat_hot in cat_lower or cat_lower in cat_hot:
            bonus += 0.5
            break
    return bonus


def descuento_min_vip_temporada() -> float:
    """Descuento mínimo para VIP ajustado según temporada."""
    key, t = temporada_activa()
    if t:
        return t.get("descuento_min_vip", 0.35)
    return 0.35


# ─────────────────────────────────────────────
# ALERTAS DE TEMPORADA
# ─────────────────────────────────────────────

def _db():
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


def _ya_enviada_hoy(tipo: str) -> bool:
    """Verifica si ya enviamos este tipo de alerta hoy."""
    db = _db()
    if not db:
        return False
    try:
        desde = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
        r = db.table("alertas_temporada").select("id").eq(
            "tipo", tipo).gte("timestamp", desde).execute()
        return len(r.data) > 0
    except Exception:
        return False


def _marcar_enviada(tipo: str):
    db = _db()
    if not db:
        return
    try:
        db.table("alertas_temporada").insert({
            "tipo":      tipo,
            "timestamp": datetime.utcnow().isoformat(),
        }).execute()
    except Exception:
        pass


def _enviar_vip(texto, modo="Markdown"):
    try:
        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id":                  CHANNEL_VIP_ID,
            "text":                     texto,
            "parse_mode":               modo,
            "disable_web_page_preview": True,
        }, timeout=15)
    except Exception as e:
        logger.error(f"[TEMPORADA VIP] {e}")


def _enviar_free_con_boton(texto, modo="HTML"):
    try:
        payload = {
            "chat_id":                  CHANNEL_FREE_ID,
            "text":                     texto,
            "parse_mode":               modo,
            "disable_web_page_preview": True,
        }
        if LAUNCHPASS_LINK:
            payload["reply_markup"] = {
                "inline_keyboard": [[{
                    "text": "📲 Canal VIP — $299/mes",
                    "url":  LAUNCHPASS_LINK
                }]]
            }
        requests.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=15)
    except Exception as e:
        logger.error(f"[TEMPORADA FREE] {e}")


def ejecutar_alertas_temporada():
    """
    Llamar una vez por hora desde main.py / bot.yml.
    Envía alertas de preparación y apertura de temporada cuando corresponde.
    """
    hora = hora_mx().hour
    if hora != 9:   # Solo a las 9 AM MX
        return

    hoy = hoy_mx()

    # 1. Verificar si hay temporada activa que acaba de empezar (día 1)
    key_activa, t_activa = temporada_activa()
    if key_activa and t_activa and t_activa["inicio"] == hoy:
        tipo = f"inicio_{key_activa}"
        if not _ya_enviada_hoy(tipo):
            # VIP: tip de compra si existe
            if t_activa.get("tip_compra"):
                _enviar_vip(t_activa["tip_compra"])
            # Free: alerta de inicio
            if t_activa.get("free_inicio"):
                _enviar_free_con_boton(t_activa["free_inicio"])
            _marcar_enviada(tipo)
            logger.info(f"[TEMPORADA] Inicio enviado: {t_activa['nombre']}")
        return

    # 2. Verificar preparación (X días antes)
    pk, pt, dias = temporada_proxima()
    if pk and pt:
        # Enviar preview en días específicos: 21, 14, 7, 3, 1
        dias_aviso = [21, 14, 7, 3, 1]
        if dias in dias_aviso:
            tipo = f"prep_{pk}_{dias}d"
            if not _ya_enviada_hoy(tipo):
                if pt.get("vip_preview"):
                    msg = pt["vip_preview"].replace("{dias}", str(dias))
                    _enviar_vip(msg)
                _marcar_enviada(tipo)
                logger.info(f"[TEMPORADA] Prep enviada: {pt['nombre']} en {dias} días")


# ─────────────────────────────────────────────
# CUPONES DE AFILIADO ML
# Sistema para que Marco pueda distribuir cupones ML afiliado
# a VIP y free con un solo comando
# ─────────────────────────────────────────────

def publicar_cupon_afiliado(codigo: str, descuento_pct: int,
                             vencimiento: str = "", categoria: str = ""):
    """
    Publica un cupón de afiliado de ML a ambos canales.
    
    Uso desde Telegram (bot de admin) o manualmente:
    publicar_cupon_afiliado("MARCO10", 10, "31 de octubre", "todas las categorías")
    
    Este es el flujo para explotar los cupones que ML envía a Marco:
    1. ML manda notificación de cupón a Marco
    2. Marco llama esta función con el código y detalles
    3. VIP lo recibe inmediatamente con análisis de cómo combinarlo
    4. Free lo recibe 10 min después con FOMO
    """
    if not codigo or descuento_pct <= 0:
        return

    venc_txt = f"\n_Válido hasta: {vencimiento}_" if vencimiento else ""
    cat_txt  = f"en {categoria}" if categoria else "en tu próxima compra"

    # Mensaje VIP — primero y con más detalle
    msg_vip = (
        f"🎟️ *CUPÓN EXCLUSIVO — Afiliado DropNode*\n\n"
        f"Código: `{codigo}`\n"
        f"Descuento: *{descuento_pct}% adicional* {cat_txt}\n"
        f"{venc_txt}\n\n"
        f"*Cómo maximizarlo:*\n"
        f"1. Aplícalo sobre cualquier oferta que ya tenga descuento\n"
        f"2. Combínalo con el cupón bancario disponible\n"
        f"3. Suma ambos descuentos para el precio real más bajo\n\n"
        f"_Actúa antes de que se comparta en el canal público._"
    )
    _enviar_vip(msg_vip)
    logger.info(f"[CUPON] Enviado al VIP: {codigo}")

    # Esperar 10 minutos antes de enviar al free
    import time
    time.sleep(600)

    msg_free = (
        f"🎟️ <b>Cupón de afiliado disponible</b>\n\n"
        f"Código: <code>{codigo}</code>\n"
        f"<b>{descuento_pct}% adicional</b> {cat_txt}\n"
        f"{venc_txt.replace('_', '').replace('*', '')}\n\n"
        f"<i>Los miembros VIP lo recibieron hace 10 minutos con guía "
        f"de cómo combinarlo con cupones bancarios para el precio mínimo.</i>"
    )
    _enviar_free_con_boton(msg_free)
    logger.info(f"[CUPON] Enviado al free: {codigo}")


# ─────────────────────────────────────────────
# SQL PARA TABLA alertas_temporada
# Ejecutar en Supabase SQL Editor:
# =============================================================
# CREATE TABLE IF NOT EXISTS alertas_temporada (
#     id        BIGSERIAL PRIMARY KEY,
#     tipo      TEXT NOT NULL,
#     timestamp TIMESTAMPTZ DEFAULT NOW()
# );
# =============================================================