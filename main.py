# =============================================================
# DROPNODE MX — main.py v3.2
# GitHub Actions cada 15 minutos
# 18 scrapers: Playwright (ML) + API JSON + requests
# ─────────────────────────────────────────────
# FIX: GROUP_ID puede estar vacío — protegido
# FIX: imports con try/except para no crashear si falta módulo
# =============================================================

import logging
import sys
import time
import os
import random
from datetime import datetime, timezone, timedelta

# ── Imports con fallback — nunca crashear por import ──
def _import(module, func):
    try:
        mod = __import__(module, fromlist=[func])
        return getattr(mod, func)
    except Exception as e:
        logging.warning(f"[IMPORT] {module}.{func}: {e}")
        return lambda *a, **k: []

ciclo_walmart        = _import("scraper_walmart",   "ejecutar_ciclo_walmart")
ciclo_liverpool      = _import("scraper_liverpool", "ejecutar_ciclo_liverpool")
ciclo_coppel         = _import("scraper_coppel",    "ejecutar_ciclo_coppel")
ciclo_amazon         = _import("scraper_amazon",    "ejecutar_ciclo_amazon")
ciclo_aliexpress     = _import("scraper_otros",     "ejecutar_ciclo_aliexpress")
ciclo_shein          = _import("scraper_otros",     "ejecutar_ciclo_shein")
ciclo_marcas         = _import("scraper_otros",     "ejecutar_ciclo_marcas")
ciclo_tiktok         = _import("scraper_otros",     "ejecutar_ciclo_tiktok_trending")
ciclo_costco         = _import("scraper_tiendas",   "ejecutar_ciclo_costco")
ciclo_sams           = _import("scraper_tiendas",   "ejecutar_ciclo_sams")
ciclo_petco          = _import("scraper_tiendas",   "ejecutar_ciclo_petco")
ciclo_sears          = _import("scraper_tiendas",   "ejecutar_ciclo_sears")
ciclo_palacio        = _import("scraper_tiendas",   "ejecutar_ciclo_palacio")
ciclo_inditex        = _import("scraper_tiendas",   "ejecutar_ciclo_inditex")
ciclo_marcas_directo = _import("scraper_tiendas",   "ejecutar_ciclo_marcas_directo")
ciclo_palacio_api    = _import("scraper_api",       "ejecutar_ciclo_palacio_api")
ciclo_petco_api      = _import("scraper_api",       "ejecutar_ciclo_petco_api")
ciclo_ml_deals       = _import("scraper_api",       "ejecutar_ciclo_ml_deals")
ciclo_sams_api       = _import("scraper_api",       "ejecutar_ciclo_sams_api")

from telegram_bot import (
    enviar_resumen_diario, enviar_mensaje_financiero,
    enviar_recordatorio_vip, enviar_y_fijar_bienvenida_grupo,
    enviar_mensaje, setup_canal_free, canal_free_tiene_fijado,
)
from community_manager import ejecutar_community_manager, fomo_vip_al_free
from heat_score        import calcular_heat_score
from config import (
    TELEGRAM_TOKEN, GROUP_ID, CHANNEL_FREE_ID, CHANNEL_VIP_ID,
    LAUNCHPASS_LINK, TIMEZONE_OFFSET_HOURS, SUPABASE_URL, SUPABASE_KEY,
)

try:
    from peticiones     import verificar_match
except Exception:
    verificar_match = lambda *a, **k: False

try:
    from temporadas import (
        temporada_activa, score_bonus_temporada, ejecutar_alertas_temporada
    )
except Exception:
    temporada_activa       = lambda: (None, None)
    score_bonus_temporada  = lambda *a, **k: 0.0
    ejecutar_alertas_temporada = lambda: None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

TZ_MEXICO = timezone(timedelta(hours=int(TIMEZONE_OFFSET_HOURS)))


def hora_mx():
    return datetime.now(TZ_MEXICO)


def dentro_de_horario():
    return 8 <= hora_mx().hour < 22


# ─────────────────────────────────────────────
# COLA FOMO — Supabase
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
        from datetime import timedelta as td
        send_after = (datetime.utcnow() + td(minutes=delay_min)).isoformat()
        item_s = {k: v for k, v in item.items()
                  if isinstance(v, (str, int, float, bool, type(None)))}
        db.table("cola_free").insert({
            "item": item_s, "score": score, "n_vip": n_vip,
            "send_after": send_after, "enviado": False,
        }).execute()
    except Exception as e:
        logger.warning(f"[COLA] {e}")


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


def cola_marcar(ids: list):
    db = get_db()
    if not db or not ids:
        return
    try:
        db.table("cola_free").update({"enviado": True}).in_("id", ids).execute()
    except Exception:
        pass


def cola_limpiar():
    db = get_db()
    if not db:
        return
    try:
        from datetime import timedelta as td
        limite = (datetime.utcnow() - td(hours=3)).isoformat()
        db.table("cola_free").delete().eq(
            "enviado", False).lt("send_after", limite).execute()
    except Exception:
        pass


# ─────────────────────────────────────────────
# FORMATO MENSAJES
# ─────────────────────────────────────────────

EMOJIS = {
    "walmart": "🛒", "liverpool": "🏬", "coppel": "🏪",
    "amazon": "📦", "aliexpress": "🌐", "shein": "👗",
    "costco": "🏪", "sams": "🏬", "petco": "🐾",
    "sears": "🏬", "palacio": "💎", "zara": "👗",
    "pullbear": "👕", "bershka": "👕", "lefties": "👕",
    "samsung": "📱", "lg": "📺", "sony": "🎮",
    "mercadolibre": "🛒", "tiktok_trend": "🎵",
}

NOMBRE_DISPLAY = {
    "sams": "Sam's Club", "palacio": "Palacio de Hierro",
    "pullbear": "Pull&Bear", "mercadolibre": "Mercado Libre",
    "tiktok_trend": "Trending",
}


def _td(t: str) -> str:
    return NOMBRE_DISPLAY.get(t, t.upper() if t in (
        "costco", "samsung", "lg", "sony", "zara", "bershka",
        "lefties", "sears", "amazon"
    ) else t.capitalize())


def fmt_vip(item: dict) -> str:
    t  = item["tienda"]
    n  = item["nombre"][:60]
    p  = item["precio_actual"]
    po = item["precio_original"]
    d  = item["descuento"] * 100
    u  = item["url"]
    et = EMOJIS.get(t, "🛍")
    ec = item["categoria"]["emoji"]
    td = _td(t)
    rl = po * 0.78; rh = po * 0.90
    ev = "✅ Envío gratis\n" if item.get("envio_gratis") else ""
    fl = " ⏰ SOLO HOY" if item.get("es_flash") else ""
    _, tinfo = temporada_activa()
    tag_t = f" [{tinfo['emoji']} {tinfo['nombre']}]" if tinfo else ""
    return (
        f"{et} *{td} — EXCLUSIVO VIP{fl}{tag_t}* {ec}\n\n"
        f"*{n}*\n\n*${p:,.0f} MXN* (-{d:.0f}%)\n"
        f"Normal: ${po:,.0f}\n{ev}\n"
        f"[COMPRAR AHORA]({u})\n\n"
        f"_Reventa: ${rl:,.0f} - ${rh:,.0f} MXN_"
    )


def fmt_free_fomo(item: dict, n_vip: int, n_excl: int, delay_min: int) -> str:
    t  = item["tienda"]
    n  = item["nombre"][:55]
    p  = item["precio_actual"]
    po = item["precio_original"]
    d  = item["descuento"] * 100
    u  = item["url"]
    et = EMOJIS.get(t, "🛍")
    ec = item["categoria"]["emoji"]
    td = _td(t)
    ev = "✅ Envío gratis\n" if item.get("envio_gratis") else ""
    dt = f"{delay_min} min" if delay_min < 60 else f"{delay_min//60}h"

    m  = f"{et} <b>{td}</b> {ec}\n\n<b>{n}</b>\n\n"
    m += f"<b>${p:,.0f} MXN</b> (-{d:.0f}%)\n"
    if po > p:
        m += f"<s>${po:,.0f}</s>\n"
    m += ev
    m += f"\n<a href=\"{u}\">Ver oferta</a>\n\n"
    m += f"<i>Llegó al Canal VIP hace {dt} con análisis de reventa.</i>\n"
    if n_excl > 0:
        m += f"<i>Además {n_excl} oferta{'s' if n_excl>1 else ''} exclusiva{'s' if n_excl>1 else ''} que no llegan aquí.</i>\n"
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
        logger.info("[COLA FREE] Sin items")
        return
    cola_limpiar()
    logger.info(f"[COLA FREE] {len(listos)} listos")

    sel   = listos[:3]
    n_exc = max(0, sum(x.get("n_vip", 0) for x in listos) - len(sel))
    ids   = []

    for i, e in enumerate(sel):
        item = e.get("item", {})
        try:
            c = datetime.fromisoformat(
                e.get("created_at", e["send_after"]).replace("Z", ""))
            delay = int((datetime.utcnow() - c).total_seconds() / 60)
        except Exception:
            delay = 30

        msg = fmt_free_fomo(item, e.get("n_vip", 0), n_exc if i == 0 else 0, delay)
        mid = enviar_mensaje(CHANNEL_FREE_ID, msg, parse_mode="HTML")
        if mid:
            ids.append(e["id"])
        time.sleep(6)

    if ids:
        cola_marcar(ids)
        logger.info(f"[COLA FREE] Enviados: {len(ids)}")


# ─────────────────────────────────────────────
# SCRAPERS — rotación de 18 fuentes
# ─────────────────────────────────────────────

# (nombre, función, peso)  — peso mayor = se ejecuta más seguido
SCRAPERS = [
    ("ML Deals API",    ciclo_ml_deals,       3),  # Extra frecuente — alta calidad
    ("Walmart",         ciclo_walmart,         3),
    ("Liverpool",       ciclo_liverpool,       3),
    ("Amazon",          ciclo_amazon,          3),
    ("ML Marcas",       ciclo_marcas,          2),
    ("Coppel",          ciclo_coppel,          2),
    ("Costco",          ciclo_costco,          2),
    ("Sam's API",       ciclo_sams_api,        2),
    ("Palacio API",     ciclo_palacio_api,     2),
    ("Petco API",       ciclo_petco_api,       2),
    ("AliExpress",      ciclo_aliexpress,      1),
    ("Inditex",         ciclo_inditex,         1),
    ("Sears",           ciclo_sears,           1),
    ("Sam's HTML",      ciclo_sams,            1),
    ("Palacio HTML",    ciclo_palacio,         1),
    ("Marcas Directo",  ciclo_marcas_directo,  1),
    ("TikTok Trend",    ciclo_tiktok,          1),
    ("Petco HTML",      ciclo_petco,           1),
]

_lista_ponderada = []
for n, f, p in SCRAPERS:
    _lista_ponderada.extend([(n, f)] * p)


def ejecutar_ciclo():
    ahora = hora_mx()
    slot  = (ahora.hour * 4 + ahora.minute // 15) % len(_lista_ponderada)
    nombre, func = _lista_ponderada[slot]

    try:
        items = func() or []
        if not items:
            logger.info(f"[CICLO] {nombre}: sin items")
            return

        vip_n = 0
        _, tinfo = temporada_activa()

        for item in items:
            try:
                base_score = calcular_heat_score(
                    descuento_real=item["descuento"],
                    stock=99,
                    categoria=item["categoria"]["nombre"],
                    precio_actual=item["precio_actual"],
                    precio_original=item["precio_original"],
                )
            except Exception:
                base_score = 3 if item["descuento"] >= 0.20 else 0

            temp_bonus  = score_bonus_temporada(item["categoria"]["nombre"])
            score_final = min(10, base_score + temp_bonus)

            if score_final < 3:
                continue

            try:
                verificar_match(item["nombre"], item["url"], item["precio_actual"])
            except Exception:
                pass

            if score_final >= 6 and vip_n < 2:
                enviar_mensaje(CHANNEL_VIP_ID, fmt_vip(item))
                vip_n += 1
                time.sleep(3)

            cola_agregar(item, score_final, vip_n, delay_min=30)

        if vip_n > 0:
            fomo_vip_al_free(vip_n)

        logger.info(f"[CICLO] {nombre} → VIP:{vip_n} encolados:{len(items)}")

    except Exception as e:
        logger.error(f"[CICLO] {nombre}: {e}", exc_info=True)


# ─────────────────────────────────────────────
# TAREAS PERIODICAS
# ─────────────────────────────────────────────

def tareas_periodicas():
    a = hora_mx()
    h, m, dia = a.hour, a.minute, a.weekday()
    if m >= 15:
        return
    if h == 21:
        enviar_resumen_diario()
    if h in (11, 18):
        enviar_mensaje_financiero()
    if h in (14, 20):
        enviar_recordatorio_vip()
    if dia == 0 and h == 9:
        _, ti = temporada_activa()
        t_str = f"\n\n_{ti['emoji']} Temporada {ti['nombre']} activa — monitoreo intensivo._" if ti else ""
        enviar_mensaje(
            CHANNEL_VIP_ID,
            f"*Reporte semanal — DropNode VIP*\n\n"
            f"18 tiendas y fuentes monitoreadas esta semana.{t_str}\n\n"
            f"_Tip: combina cualquier oferta con cupones bancarios — "
            f"en el VIP calculamos el precio final automáticamente._\n\n"
            f"{LAUNCHPASS_LINK}"
        )
    try:
        ejecutar_alertas_temporada()
    except Exception:
        pass


# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────

def setup():
    import requests as req
    # Canal free
    if not canal_free_tiene_fijado():
        setup_canal_free()
    # Grupo — solo si GROUP_ID está configurado
    if not GROUP_ID:
        logger.warning("[SETUP] GROUP_ID vacío — skipping grupo setup")
        return
    try:
        r = req.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat",
            params={"chat_id": GROUP_ID}, timeout=10
        )
        if "pinned_message" not in r.json().get("result", {}):
            enviar_y_fijar_bienvenida_grupo()
    except Exception:
        pass


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    _, tinfo = temporada_activa()
    t_str = f" | {tinfo['emoji']} {tinfo['nombre']}" if tinfo else ""
    logger.info(
        f"\n{'='*50}\n"
        f" DROPNODE MX v3.2 — {hora_mx().strftime('%d/%m/%Y %H:%M')} MX{t_str}\n"
        f" 18 fuentes · GitHub Actions\n"
        f"{'='*50}"
    )

    setup()

    if dentro_de_horario():
        procesar_cola_free()
        ejecutar_ciclo()

    ejecutar_community_manager()
    tareas_periodicas()

    logger.info("[DROPNODE] Run completado.")