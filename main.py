# =============================================================
# DROPNODE MX — main.py v3.1
# GitHub Actions cada 15 minutos
# 15 scrapers en rotación inteligente
# + Sistema de temporadas integrado
# =============================================================

import logging
import sys
import time
import os
import random
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
from scraper_tiendas import (
    ejecutar_ciclo_costco    as ciclo_costco,
    ejecutar_ciclo_sams      as ciclo_sams,
    ejecutar_ciclo_petco     as ciclo_petco,
    ejecutar_ciclo_sears     as ciclo_sears,
    ejecutar_ciclo_palacio   as ciclo_palacio,
    ejecutar_ciclo_inditex   as ciclo_inditex,
    ejecutar_ciclo_marcas_directo as ciclo_marcas_directo,
)
from telegram_bot import (
    enviar_resumen_diario,
    enviar_mensaje_financiero,
    enviar_recordatorio_vip,
    enviar_y_fijar_bienvenida_grupo,
    enviar_mensaje,
    setup_canal_free,
    canal_free_tiene_fijado,
)
from community_manager  import ejecutar_community_manager
from heat_score         import calcular_heat_score
from peticiones         import verificar_match
from temporadas         import (
    temporada_activa,
    score_bonus_temporada,
    ejecutar_alertas_temporada,
)
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
# COLA FOMO en Supabase
# ─────────────────────────────────────────────

_db_client = None


def get_db():
    global _db_client
    if _db_client:
        return _db_client
    try:
        from supabase import create_client
        _db_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logger.warning(f"[DB] {e}")
    return _db_client


def cola_agregar(item: dict, score: float, n_vip: int, delay_min: int = 30):
    db = get_db()
    if not db:
        return
    try:
        from datetime import timedelta
        send_after = (datetime.utcnow() + timedelta(minutes=delay_min)).isoformat()
        item_s = {k: v for k, v in item.items()
                  if isinstance(v, (str, int, float, bool, type(None)))}
        db.table("cola_free").insert({
            "item": item_s, "score": score, "n_vip": n_vip,
            "send_after": send_after, "enviado": False,
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
    except Exception:
        return []


def cola_marcar_enviados(ids: list):
    db = get_db()
    if not db or not ids:
        return
    try:
        db.table("cola_free").update({"enviado": True}).in_("id", ids).execute()
    except Exception:
        pass


def cola_limpiar_viejos():
    db = get_db()
    if not db:
        return
    try:
        from datetime import timedelta
        limite = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        db.table("cola_free").delete().eq(
            "enviado", False).lt("send_after", limite).execute()
    except Exception:
        pass


# ─────────────────────────────────────────────
# FORMATO MENSAJES EXTERNOS
# ─────────────────────────────────────────────

EMOJIS = {
    "walmart":      "🛒", "liverpool": "🏬", "coppel":    "🏪",
    "amazon":       "📦", "aliexpress":"🌐", "shein":     "👗",
    "costco":       "🏪", "sams":      "🏬", "petco":     "🐾",
    "sears":        "🏬", "palacio":   "💎", "zara":      "👗",
    "pullbear":     "👕", "bershka":   "👕", "lefties":   "👕",
    "samsung":      "📱", "lg":        "📺", "sony":      "🎮",
    "marcas":       "🔌", "tiktok_trend":"🎵",
}

NOMBRE_DISPLAY = {
    "sams":    "Sam's Club",
    "palacio": "Palacio de Hierro",
    "pullbear":"Pull&Bear",
    "marcas":  "Tiendas de Marca",
    "tiktok_trend": "Trending",
}


def _nombre_tienda(tienda: str) -> str:
    return NOMBRE_DISPLAY.get(tienda, tienda.upper() if tienda in (
        "costco","samsung","lg","sony","zara","bershka","lefties","sears"
    ) else tienda.capitalize())


def formatear_vip_externa(item: dict) -> str:
    tienda   = item["tienda"]
    nombre   = item["nombre"][:60]
    precio   = item["precio_actual"]
    precio_o = item["precio_original"]
    desc     = item["descuento"] * 100
    url      = item["url"]
    et       = EMOJIS.get(tienda, "🛍️")
    ec       = item["categoria"]["emoji"]
    td       = _nombre_tienda(tienda)
    rl = precio_o * 0.78
    rh = precio_o * 0.90
    ev = "✅ Envío gratis\n" if item.get("envio_gratis") else ""

    # Temporada activa
    key_t, t_info = temporada_activa()
    tag_temp = f" [{t_info['emoji']} {t_info['nombre']}]" if t_info else ""

    return (
        f"{et} *{td} — OFERTA EXCLUSIVA{tag_temp}* {ec}\n\n"
        f"*{nombre}*\n\n"
        f"*${precio:,.0f} MXN* (-{desc:.0f}%)\n"
        f"Normal: ${precio_o:,.0f} MXN\n"
        f"{ev}\n"
        f"[COMPRAR AHORA]({url})\n\n"
        f"_Reventa estimada: ${rl:,.0f} - ${rh:,.0f} MXN_"
    )


def formatear_free_fomo(item: dict, n_vip: int,
                         n_excl: int, delay_min: int) -> str:
    tienda   = item["tienda"]
    nombre   = item["nombre"][:55]
    precio   = item["precio_actual"]
    precio_o = item["precio_original"]
    desc     = item["descuento"] * 100
    url      = item["url"]
    et       = EMOJIS.get(tienda, "🛍️")
    ec       = item["categoria"]["emoji"]
    td       = _nombre_tienda(tienda)
    ev       = "✅ Envío gratis\n" if item.get("envio_gratis") else ""
    delay_txt = (f"{delay_min} minutos" if delay_min < 60
                 else f"{delay_min // 60} hora{'s' if delay_min >= 120 else ''}")

    m  = f"{et} <b>{td}</b> {ec}\n\n"
    m += f"<b>{nombre}</b>\n\n"
    m += f"<b>${precio:,.0f} MXN</b> (-{desc:.0f}%)\n"
    if precio_o > precio:
        m += f"<s>${precio_o:,.0f}</s>\n"
    m += ev
    m += f"\n<a href=\"{url}\">Ver oferta</a>\n\n"
    m += f"<i>Esta alerta llegó al Canal VIP hace {delay_txt} con análisis de reventa.</i>\n"
    if n_excl > 0:
        m += (f"<i>Además hubo {n_excl} "
              f"oportunidad{'es' if n_excl > 1 else ''} "
              f"exclusiva{'s' if n_excl > 1 else ''} que no llegan aquí.</i>\n")
    m += "<i>Los miembros VIP actúan primero.</i>\n"
    if LAUNCHPASS_LINK:
        m += f"\n<a href=\"{LAUNCHPASS_LINK}\">📲 Canal VIP — $299/mes</a>"
    return m


# ─────────────────────────────────────────────
# COLA FREE — procesar
# ─────────────────────────────────────────────

def procesar_cola_free():
    listos = cola_listos()
    if not listos:
        return
    logger.info(f"[COLA FREE] {len(listos)} listos")
    cola_limpiar_viejos()

    seleccionados = listos[:3]
    n_excl_total  = max(0, sum(x.get("n_vip", 0) for x in listos) - len(seleccionados))
    ids_enviados  = []

    for i, entrada in enumerate(seleccionados):
        item = entrada.get("item", {})
        try:
            created = datetime.fromisoformat(
                entrada.get("created_at", entrada["send_after"]).replace("Z", ""))
            delay_min = int((datetime.utcnow() - created).total_seconds() / 60)
        except Exception:
            delay_min = 30

        n_excl = n_excl_total if i == 0 else 0
        msg    = formatear_free_fomo(item, entrada.get("n_vip", 0), n_excl, delay_min)
        mid    = enviar_mensaje(CHANNEL_FREE_ID, msg, parse_mode="HTML")
        if mid:
            ids_enviados.append(entrada["id"])
        time.sleep(6)

    if ids_enviados:
        cola_marcar_enviados(ids_enviados)
        logger.info(f"[COLA FREE] Enviados: {len(ids_enviados)}")


# ─────────────────────────────────────────────
# ROTACION DE SCRAPERS — 15 tiendas
# Slot determinado por minuto del run
# ─────────────────────────────────────────────

# Prioridad alta (más frecuentes) — slots duplicados
SCRAPERS = [
    # Alta prioridad — cada ~2h
    ("Walmart",        ciclo_walmart,        2),
    ("Liverpool",      ciclo_liverpool,      2),
    ("Amazon",         ciclo_amazon,         2),
    ("ML-Marcas",      ciclo_marcas,         2),
    ("Coppel",         ciclo_coppel,         2),
    # Media prioridad — cada ~3h
    ("Costco",         ciclo_costco,         2),
    ("Sam's Club",     ciclo_sams,           2),
    ("AliExpress",     ciclo_aliexpress,     2),
    ("Inditex",        ciclo_inditex,        1),
    ("Petco",          ciclo_petco,          1),
    # Baja prioridad — cada ~4h
    ("Sears",          ciclo_sears,          1),
    ("Palacio",        ciclo_palacio,        1),
    ("Marcas Directo", ciclo_marcas_directo, 2),
    ("SHEIN",          ciclo_shein,          1),
    ("TikTok Trend",   ciclo_tiktok,         1),
]


def _elegir_scraper(slot: int) -> tuple:
    """Elige el scraper del turno según slot y temporada activa."""
    # En temporada activa, dar más peso a scrapers relevantes
    key_t, t_info = temporada_activa()

    # Lista ponderada — scrapers de alta prioridad tienen más chances
    lista = []
    for nombre, func, peso in SCRAPERS:
        # Boost extra si es temporada y el scraper es relevante
        if t_info and any(k in nombre.lower() for k in ["liverpool", "amazon", "walmart", "costco", "sams"]):
            lista.extend([(nombre, func)] * (peso + 1))
        else:
            lista.extend([(nombre, func)] * peso)

    idx = slot % len(lista)
    return lista[idx]


def ejecutar_ciclo_scraper():
    ahora  = hora_mx()
    # Slot único por run: hora * 4 + minuto // 15
    slot   = (ahora.hour * 4 + ahora.minute // 15)
    nombre, func = _elegir_scraper(slot)

    try:
        items = func()
        if not items:
            logger.info(f"[CICLO] {nombre}: sin items")
            return

        vip_este_ciclo = 0
        _, t_info = temporada_activa()

        for item in items:
            base_score = calcular_heat_score(
                descuento_real=item["descuento"],
                stock=99,
                categoria=item["categoria"]["nombre"],
                precio_actual=item["precio_actual"],
                precio_original=item["precio_original"],
            )

            # Bonus de temporada
            temp_bonus = score_bonus_temporada(item["categoria"]["nombre"])
            score_final = min(10, base_score + temp_bonus)

            if score_final < 3:
                continue

            try:
                verificar_match(item["nombre"], item["url"], item["precio_actual"])
            except Exception:
                pass

            if score_final >= 6 and vip_este_ciclo < 2:
                enviar_mensaje(CHANNEL_VIP_ID, formatear_vip_externa(item))
                vip_este_ciclo += 1
                time.sleep(3)

            cola_agregar(item, score_final, vip_este_ciclo, delay_min=30)

        logger.info(f"[CICLO] {nombre} → VIP:{vip_este_ciclo} encolados:{len(items)}")

    except Exception as e:
        logger.error(f"[CICLO] {nombre}: {e}", exc_info=True)


# ─────────────────────────────────────────────
# TAREAS PERIODICAS
# ─────────────────────────────────────────────

def tareas_periodicas():
    ahora = hora_mx()
    h, m  = ahora.hour, ahora.minute
    dia   = ahora.weekday()

    if m >= 15:
        return

    if h == 21:
        enviar_resumen_diario()
    if h in (11, 18):
        enviar_mensaje_financiero()
    if h in (14, 20):
        enviar_recordatorio_vip()
    if dia == 0 and h == 9:
        _, t_info = temporada_activa()
        msg = (
            "*Reporte semanal exclusivo — DropNode VIP*\n\n"
            "Esta semana monitoreamos 15 tiendas y marcas.\n\n"
        )
        if t_info:
            msg += f"_{t_info['emoji']} Estamos en temporada {t_info['nombre']} — monitoreo intensivo activo._\n\n"
        msg += (
            "Tip de la semana:\n"
            "_Combina cualquier oferta con los cupones bancarios activos "
            "— en el canal calculamos el precio real después del banco._\n\n"
            f"{LAUNCHPASS_LINK}"
        )
        enviar_mensaje(CHANNEL_VIP_ID, msg)

    # Alertas de temporada — preparación y apertura
    ejecutar_alertas_temporada()


# ─────────────────────────────────────────────
# SETUP INICIAL
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
    _, t_info = temporada_activa()
    t_str = f" | {t_info['emoji']} {t_info['nombre']}" if t_info else ""
    logger.info(
        f"\n{'='*50}\n"
        f" DROPNODE MX v3.1 — {ahora_str} MX{t_str}\n"
        f" 15 scrapers activos\n"
        f"{'='*50}"
    )

    setup_si_necesario()

    if dentro_de_horario():
        procesar_cola_free()
        ejecutar_ciclo_scraper()

    ejecutar_community_manager()
    tareas_periodicas()

    logger.info("[DROPNODE] Run completado.")