# =============================================================
# DROPNODE MX — main.py v3.0
# Script de una sola corrida — GitHub Actions cada 15 minutos
# Sin scheduler, sin while loop, sin Railway
# Cola FOMO persistida en Supabase entre runs
# =============================================================

import logging
import sys
import time
import os
from datetime import datetime, timezone, timedelta

from scraper_walmart   import ejecutar_ciclo_walmart   as ciclo_walmart
from scraper_liverpool import ejecutar_ciclo_liverpool as ciclo_liverpool
from scraper_coppel    import ejecutar_ciclo_coppel    as ciclo_coppel
from scraper_amazon    import ejecutar_ciclo_amazon    as ciclo_amazon
from scraper_otros import (
    ejecutar_ciclo_aliexpress      as ciclo_aliexpress,
    ejecutar_ciclo_shein           as ciclo_shein,
    ejecutar_ciclo_marcas          as ciclo_marcas,
    ejecutar_ciclo_tiktok_trending as ciclo_tiktok,
)
from telegram_bot import (
    enviar_resumen_diario,
    enviar_mensaje_financiero,
    enviar_recordatorio_vip,
    enviar_y_fijar_bienvenida_grupo,
    enviar_mensaje,
    publicar_mejores_del_dia,
    setup_canal_free,
    canal_free_tiene_fijado,
)
from community_manager import ejecutar_community_manager
from heat_score        import calcular_heat_score
from peticiones        import verificar_match
from config import (
    TELEGRAM_TOKEN, GROUP_ID, CHANNEL_FREE_ID, CHANNEL_VIP_ID,
    LAUNCHPASS_LINK, TIMEZONE_OFFSET_HOURS,
    SUPABASE_URL, SUPABASE_KEY,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

TZ_MEXICO = timezone(timedelta(hours=TIMEZONE_OFFSET_HOURS))


def hora_mx():
    return datetime.now(TZ_MEXICO)


def dentro_de_horario():
    return 8 <= hora_mx().hour < 22


# ─────────────────────────────────────────────
# COLA FOMO — persistida en Supabase
# Los items se encolan con send_after = ahora + 30 min
# En cada run se procesan los que ya están listos
# ─────────────────────────────────────────────

_db = None


def get_db():
    global _db
    if _db:
        return _db
    try:
        from supabase import create_client
        _db = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.warning(f"[DB] No disponible: {e}")
    return _db


def cola_agregar(item: dict, score: float, n_vip: int, delay_min: int = 30):
    db = get_db()
    if not db:
        return
    try:
        send_after = (datetime.utcnow() + timedelta(minutes=delay_min)).isoformat()
        # Serializar item — eliminar campos no serializables si los hay
        item_serial = {k: v for k, v in item.items()
                       if isinstance(v, (str, int, float, bool, type(None)))}
        db.table("cola_free").insert({
            "item":      item_serial,
            "score":     score,
            "n_vip":     n_vip,
            "send_after": send_after,
            "enviado":   False,
        }).execute()
    except Exception as e:
        logger.warning(f"[COLA] agregar: {e}")


def cola_listos() -> list:
    db = get_db()
    if not db:
        return []
    try:
        ahora = datetime.utcnow().isoformat()
        r = db.table("cola_free").select("*").eq(
            "enviado", False
        ).lte("send_after", ahora).order("score", desc=True).execute()
        return r.data or []
    except Exception as e:
        logger.warning(f"[COLA] listos: {e}")
        return []


def cola_marcar_enviados(ids: list):
    db = get_db()
    if not db or not ids:
        return
    try:
        db.table("cola_free").update({"enviado": True}).in_("id", ids).execute()
    except Exception as e:
        logger.warning(f"[COLA] marcar: {e}")


def cola_limpiar_viejos():
    """Elimina items con más de 3 horas sin enviar — ya no son relevantes."""
    db = get_db()
    if not db:
        return
    try:
        limite = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        db.table("cola_free").delete().eq(
            "enviado", False
        ).lt("send_after", limite).execute()
    except Exception as e:
        logger.warning(f"[COLA] limpiar: {e}")


# ─────────────────────────────────────────────
# FORMATO MENSAJES EXTERNOS — igual que antes
# ─────────────────────────────────────────────

EMOJIS = {
    "walmart":      "🛒", "liverpool":    "🏬", "coppel":       "🏪",
    "amazon":       "📦", "aliexpress":   "🌐", "shein":        "👗",
    "samsung":      "📱", "sony":         "🎮", "lg":           "📺",
    "lenovo":       "💻", "dell":         "💻", "hp":           "💻",
    "asus":         "💻", "xiaomi":       "📱", "ghia":         "💻",
    "hisense":      "📺", "tcl":          "📺", "tiktok_trend": "🎵",
}


def formatear_externa_vip(item: dict) -> str:
    tienda   = item["tienda"]
    nombre   = item["nombre"][:60]
    precio   = item["precio_actual"]
    precio_o = item["precio_original"]
    desc     = item["descuento"] * 100
    url      = item["url"]
    et       = EMOJIS.get(tienda, "🛍️")
    ec       = item["categoria"]["emoji"]
    td       = tienda.upper() if tienda in (
        "samsung","sony","lg","lenovo","dell","hp",
        "asus","xiaomi","ghia","hisense","tcl"
    ) else tienda.capitalize()
    rl = precio_o * 0.78
    rh = precio_o * 0.90
    return (
        f"{et} *{td} — OFERTA EXCLUSIVA* {ec}\n\n"
        f"*{nombre}*\n\n"
        f"*${precio:,.0f} MXN* (-{desc:.0f}%)\n"
        f"Normal: ${precio_o:,.0f} MXN\n\n"
        f"[COMPRAR AHORA]({url})\n\n"
        f"_Reventa estimada: ${rl:,.0f} - ${rh:,.0f} MXN_"
    )


def formatear_externa_free_fomo(item: dict, n_vip: int,
                                 n_excl: int, delay_min: int) -> str:
    tienda   = item["tienda"]
    nombre   = item["nombre"][:55]
    precio   = item["precio_actual"]
    precio_o = item["precio_original"]
    desc     = item["descuento"] * 100
    url      = item["url"]
    et       = EMOJIS.get(tienda, "🛍️")
    ec       = item["categoria"]["emoji"]
    td       = tienda.upper() if tienda in (
        "samsung","sony","lg","lenovo","dell","hp",
        "asus","xiaomi","ghia","hisense","tcl"
    ) else tienda.capitalize()

    delay_txt = (f"{delay_min} minutos" if delay_min < 60
                 else f"{delay_min // 60} hora{'s' if delay_min >= 120 else ''}")

    m  = f"{et} <b>OFERTA {td}</b> {ec}\n\n"
    m += f"<b>{nombre}</b>\n\n"
    m += f"<b>${precio:,.0f} MXN</b> (-{desc:.0f}%)\n"
    if precio_o > precio:
        m += f"<s>${precio_o:,.0f}</s>\n"
    m += f"\n<a href=\"{url}\">Ver oferta</a>\n\n"
    m += f"<i>Esta alerta llegó al Canal VIP hace {delay_txt} con análisis de reventa.</i>\n"
    if n_excl > 0:
        m += (f"<i>En ese mismo momento hubo {n_excl} "
              f"oportunidad{'es' if n_excl > 1 else ''} "
              f"exclusiva{'s' if n_excl > 1 else ''} que no llegan aquí.</i>\n")
    m += "<i>Los miembros VIP actúan primero — la ventana de tiempo importa.</i>\n"
    if LAUNCHPASS_LINK:
        m += f"\n<a href=\"{LAUNCHPASS_LINK}\">📲 Unirse al Canal VIP — $299/mes</a>"
    return m


# ─────────────────────────────────────────────
# CICLO DE SCRAPERS EXTERNOS
# ─────────────────────────────────────────────

def procesar_externa(items: list, max_vip: int = 2) -> int:
    """
    Envía al VIP directamente si el score lo amerita.
    Encola en Supabase para el free con delay de 30 min.
    Retorna número de items enviados al VIP.
    """
    vip_este_ciclo = 0

    for item in items:
        score = calcular_heat_score(
            descuento_real=item["descuento"],
            stock=99,
            categoria=item["categoria"]["nombre"],
            precio_actual=item["precio_actual"],
            precio_original=item["precio_original"],
        )
        if score < 3:
            continue

        try:
            verificar_match(item["nombre"], item["url"], item["precio_actual"])
        except Exception:
            pass

        if score >= 6 and vip_este_ciclo < max_vip:
            enviar_mensaje(CHANNEL_VIP_ID, formatear_externa_vip(item))
            vip_este_ciclo += 1
            time.sleep(3)

        # Encolar para el free — persiste en Supabase
        cola_agregar(item, score, vip_este_ciclo, delay_min=30)

    return vip_este_ciclo


def ejecutar_ciclo_scrapers():
    """
    Rota entre los 8 scrapers usando la hora actual como índice.
    Cada run de 15 min toca un scraper diferente.
    """
    # Usar minuto del run para elegir scraper (0,15,30,45 → 4 slots/hora × 8 scrapers)
    ahora  = hora_mx()
    slot   = (ahora.hour * 4 + ahora.minute // 15) % 8
    nombre = ""

    try:
        if   slot == 0: items = ciclo_walmart();    nombre = "Walmart"
        elif slot == 1: items = ciclo_liverpool();  nombre = "Liverpool"
        elif slot == 2: items = ciclo_coppel();     nombre = "Coppel"
        elif slot == 3: items = ciclo_amazon();     nombre = "Amazon"
        elif slot == 4: items = ciclo_aliexpress(); nombre = "AliExpress"
        elif slot == 5: items = ciclo_shein();      nombre = "SHEIN"
        elif slot == 6: items = ciclo_marcas();     nombre = "Marcas"
        elif slot == 7: items = ciclo_tiktok();     nombre = "TikTok"
        else:           items = [];                 nombre = "?"

        n_vip = procesar_externa(items, max_vip=2)
        logger.info(f"[CICLO] {nombre} → VIP:{n_vip} encolados:{len(items)}")
    except Exception as e:
        logger.error(f"[CICLO] {nombre}: {e}", exc_info=True)


def ejecutar_cola_free():
    """
    Procesa items listos de la cola — los que llevan 30+ min esperando.
    Selección: 1 de mayor score + hasta 2 más = máximo 3 por run.
    """
    listos = cola_listos()
    if not listos:
        logger.info("[COLA FREE] Sin items listos")
        return

    logger.info(f"[COLA FREE] {len(listos)} items listos")
    cola_limpiar_viejos()

    MAX_POR_RUN = 3
    seleccionados = listos[:MAX_POR_RUN]
    n_excl_total  = max(0, sum(x.get("n_vip", 0) for x in listos) - len(seleccionados))
    ids_enviados  = []

    for i, entrada in enumerate(seleccionados):
        item      = entrada.get("item", {})
        n_vip     = entrada.get("n_vip", 0)
        # Calcular delay real desde cuando se encoló
        try:
            send_after  = datetime.fromisoformat(
                entrada["send_after"].replace("Z", ""))
            created_str = entrada.get("created_at", entrada["send_after"])
            created     = datetime.fromisoformat(created_str.replace("Z", ""))
            delay_min   = int((datetime.utcnow() - created).total_seconds() / 60)
        except Exception:
            delay_min = 30

        n_excl = n_excl_total if i == 0 else 0
        msg    = formatear_externa_free_fomo(item, n_vip, n_excl, delay_min)
        mid    = enviar_mensaje(CHANNEL_FREE_ID, msg, parse_mode="HTML")
        if mid:
            ids_enviados.append(entrada["id"])
        time.sleep(6)

    if ids_enviados:
        cola_marcar_enviados(ids_enviados)
        logger.info(f"[COLA FREE] Enviados: {len(ids_enviados)}")


# ─────────────────────────────────────────────
# TAREAS PERIÓDICAS — basadas en hora actual
# ─────────────────────────────────────────────

def tareas_periodicas():
    ahora = hora_mx()
    h, m  = ahora.hour, ahora.minute

    # Solo ejecutar en los primeros 15 min de cada hora para evitar duplicados
    if m >= 15:
        return

    # Resumen diario — 9 PM MX
    if h == 21:
        enviar_resumen_diario()

    # Mensajes financieros — 11 AM y 6 PM MX
    if h in (11, 18):
        enviar_mensaje_financiero()

    # Recordatorio VIP — 2 PM y 8 PM MX
    if h in (14, 20):
        enviar_recordatorio_vip()

    # Reporte semanal VIP — lunes 9 AM MX
    if ahora.weekday() == 0 and h == 9:
        enviar_mensaje(
            CHANNEL_VIP_ID,
            "*Reporte semanal exclusivo — DropNode VIP*\n\n"
            "Esta semana monitoreamos todas las tiendas y secciones.\n\n"
            "Tip de flip:\n"
            "_iPhones reacondicionados certificados con 40%+ en Liverpool "
            "tienen el mejor margen. Compra y revende en ML con 15-25%._\n\n"
            f"{LAUNCHPASS_LINK}"
        )


# ─────────────────────────────────────────────
# SETUP INICIAL — solo si es necesario
# ─────────────────────────────────────────────

def setup_si_necesario():
    import requests as req
    try:
        r = req.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat",
            params={"chat_id": GROUP_ID}, timeout=10
        )
        if "pinned_message" not in r.json().get("result", {}):
            enviar_y_fijar_bienvenida_grupo()
    except Exception:
        pass

    if not canal_free_tiene_fijado():
        setup_canal_free()


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    ahora_str = hora_mx().strftime("%d/%m/%Y %H:%M")
    logger.info(f"\n{'='*50}\n DROPNODE MX v3.0 — {ahora_str} MX\n{'='*50}")

    # Setup inicial (solo actúa si falta algo)
    setup_si_necesario()

    if dentro_de_horario():
        # 1. Procesar cola del free — items de runs anteriores listos para enviar
        ejecutar_cola_free()

        # 2. Scraper del turno actual → VIP directo + encolar para free
        ejecutar_ciclo_scrapers()

    # 3. Community manager — revisa hora internamente y actúa si corresponde
    ejecutar_community_manager()

    # 4. Tareas periódicas — resumen, financiero, VIP reminder
    tareas_periodicas()

    logger.info("[DROPNODE] Run completado.")
