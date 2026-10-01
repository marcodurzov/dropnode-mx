# =============================================================
# DROPNODE MX — main.py v3.6
# GitHub Actions cada 15 min. Cambios vs v3.5:
#   - Horarios/reglas centralizados (horarios.py)
#   - Cola VIP->Free de 60 min (TODO el free sale de aquí, también ML)
#   - Fix: la cola crasheaba (categoria anidada) y dependía de la BD
#   - Fix: candados anti-duplicado en Supabase (resúmenes, deal, etc.)
#   - Resumen de cierre FREE (6-7 PM) y VIP (11-11:30 PM) mejorados
#   - 2 fuentes por corrida + respaldo con motor multi-tienda
#   - Score de temporada (calendario por mes) + scraper de temporada
#   - Comunidad: lectura/moderación del grupo en cada corrida
#   - Salud de fuentes y alertas privadas al dueño (ADMIN_CHAT_ID)
# =============================================================
import logging, sys, time, os, random, importlib
from datetime import datetime

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

import horarios as H
import estado as E
import temporada_calendario as T


def _imp(mod, fn, fb=None):
    try:
        return getattr(importlib.import_module(mod), fn)
    except Exception as e:
        logger.warning(f"[IMPORT] {mod}.{fn}: {e}")
        return fb or (lambda *a, **k: [])


# ── Scrapers ──
ciclo_walmart    = _imp("scraper_walmart",   "ejecutar_ciclo_walmart")
ciclo_liverpool  = _imp("scraper_liverpool", "ejecutar_ciclo_liverpool")
ciclo_coppel     = _imp("scraper_coppel",    "ejecutar_ciclo_coppel")
ciclo_amazon     = _imp("scraper_amazon",    "ejecutar_ciclo_amazon")
ciclo_aliexpress = _imp("scraper_otros",     "ejecutar_ciclo_aliexpress")
ciclo_shein      = _imp("scraper_otros",     "ejecutar_ciclo_shein")
ciclo_marcas     = _imp("scraper_otros",     "ejecutar_ciclo_marcas")
ciclo_tiktok     = _imp("scraper_otros",     "ejecutar_ciclo_tiktok_trending")
ciclo_costco     = _imp("scraper_tiendas",   "ejecutar_ciclo_costco")
ciclo_sears      = _imp("scraper_tiendas",   "ejecutar_ciclo_sears")
ciclo_inditex    = _imp("scraper_tiendas",   "ejecutar_ciclo_inditex")
ciclo_marcas_d   = _imp("scraper_tiendas",   "ejecutar_ciclo_marcas_directo")
ciclo_palacio_a  = _imp("scraper_api",       "ejecutar_ciclo_palacio_api")
ciclo_petco_a    = _imp("scraper_api",       "ejecutar_ciclo_petco_api")
ciclo_ml_deals   = _imp("scraper_api",       "ejecutar_ciclo_ml_deals")
ciclo_sams_a     = _imp("scraper_api",       "ejecutar_ciclo_sams_api")
ciclo_elektra    = _imp("scraper_elektra",   "ejecutar_ciclo_elektra")
ciclo_bodega     = _imp("scraper_bodega",    "ejecutar_ciclo_bodega")
ciclo_temporada  = _imp("scraper_temporada", "ejecutar_ciclo_temporada")
ciclo_multi      = _imp("scraper_multi",     "ejecutar_ciclo_multi")

try:
    from telegram_bot import (enviar_mensaje_financiero, enviar_recordatorio_vip,
                              enviar_y_fijar_bienvenida_grupo, setup_canal_free, canal_free_tiene_fijado)
except Exception as e:
    logger.warning(f"[IMPORT] telegram_bot: {e}")
    enviar_mensaje_financiero = enviar_recordatorio_vip = enviar_y_fijar_bienvenida_grupo = setup_canal_free = lambda *a, **k: None
    canal_free_tiene_fijado = lambda: True

from community_manager import (ejecutar_community_manager, procesar_actualizaciones, fomo_vip_al_free)
import resumenes

verificar_match  = _imp("peticiones", "verificar_match", lambda *a, **k: None)
temporada_activa = _imp("temporadas", "temporada_activa", lambda: (None, None))
score_bonus_temp = _imp("temporadas", "score_bonus_temporada", lambda *a, **k: 0.0)
alertas_temp     = _imp("temporadas", "ejecutar_alertas_temporada", lambda: None)
calcular_score   = _imp("heat_score", "calcular_heat_score", lambda **k: 3)
monitor_cupones  = _imp("cupon_monitor", "ejecutar_monitor_cupones", lambda: None)

VIP  = E.cfg_int("CHANNEL_VIP_ID")
FREE = E.cfg_int("CHANNEL_FREE_ID")
GROUP_ID = E.cfg("GROUP_ID")
LAUNCHPASS_LINK = E.cfg("LAUNCHPASS_LINK")
BTN_VIP = ("📲 Canal VIP — $299/mes", LAUNCHPASS_LINK)

# ─────────────────────────────────────────────
# FORMATO (HTML: los nombres con _ * [ ya no rompen el mensaje)
# ─────────────────────────────────────────────
EMOJIS = {"walmart": "🛒", "liverpool": "🏬", "coppel": "🏪", "amazon": "📦", "aliexpress": "🌐", "shein": "👗",
          "costco": "🏪", "sams": "🏬", "petco": "🐾", "sears": "🏬", "palacio": "💎", "zara": "👗",
          "pullbear": "👕", "bershka": "👕", "lefties": "👕", "samsung": "📱", "lg": "📺", "sony": "🎮",
          "mercadolibre": "🛒", "tiktok_trend": "🎵", "elektra": "⚡", "bodega": "🛒", "heb": "🛒"}
NOMBRES = {"sams": "Sam's Club", "palacio": "Palacio de Hierro", "pullbear": "Pull&Bear", "mercadolibre": "Mercado Libre",
           "tiktok_trend": "Trending", "elektra": "Elektra", "bodega": "Bodega Aurrerá", "heb": "HEB"}


def _td(t):
    return NOMBRES.get(t, t.upper() if t in ("costco", "samsung", "lg", "sony", "zara", "bershka", "lefties", "sears", "amazon")
                       else t.capitalize())


def fmt_vip(item, sf):
    t = item["tienda"]
    p, po, d = item["precio_actual"], item["precio_original"], item["descuento"] * 100
    etiqueta = "🚨 ERROR DE PRECIO" if sf >= 8 else ("🔥 HOT DEAL" if d >= 35 else "⚡ ALERTA VIP")
    _, ti = temporada_activa()
    tag = f" · {ti['emoji']} {ti['nombre']}" if ti else ""
    noc = " · 🌙 NOCTURNO" if H.modo_nocturno() else ""
    flash = " · ⏰ SOLO HOY" if item.get("es_flash") else ""
    m = (f"{EMOICONO(t)} <b>{etiqueta} — {E.esc(_td(t))}{flash}{tag}{noc}</b> {item['cat_emoji']}\n\n"
         f"<b>{E.esc(item['nombre'][:70])}</b>\n\n"
         f"<b>${p:,.0f} MXN</b> (-{d:.0f}%)\nNormal: ${po:,.0f} · ahorras ${po - p:,.0f}\n")
    if item.get("envio_gratis"):
        m += "✅ Envío gratis\n"
    m += f"\n<a href=\"{E.link_afiliado(item['url'])}\">COMPRAR AHORA</a>\n\n<i>Reventa estimada: ${po*0.78:,.0f} - ${po*0.90:,.0f} MXN</i>"
    return m


def EMOICONO(t):
    return EMOJIS.get(t, "🛍️")


def fmt_free(item):
    t = item["tienda"]
    p, po, d = item["precio_actual"], item["precio_original"], item["descuento"] * 100
    m = f"{EMOICONO(t)} <b>{E.esc(_td(t))}</b> {item.get('cat_emoji', '🛍️')}\n\n<b>{E.esc(item['nombre'][:60])}</b>\n\n<b>${p:,.0f} MXN</b> (-{d:.0f}%)\n"
    if po > p:
        m += f"<s>${po:,.0f}</s>\n"
    if item.get("envio_gratis"):
        m += "✅ Envío gratis\n"
    m += f"\n<a href=\"{E.link_afiliado(item['url'])}\">Ver oferta</a>\n\n"
    m += ("<i>Esta alerta llegó al Canal VIP hace más de 1 hora.</i>" if item.get("en_vip")
          else "<i>Selección del equipo. Las mejores ofertas llegan primero al Canal VIP.</i>")
    return m


# ─────────────────────────────────────────────
# COLA FREE  (60 min, solo horario free, con variedad)
# ─────────────────────────────────────────────
def procesar_cola_free():
    if not H.en_horario_free():
        logger.info("[COLA FREE] fuera de horario (8:00-19:00)")
        return
    ya = E.contar_alertas("free", H.dia_inicio_utc())
    cupo = min(H.FREE_MAX_POR_CORRIDA, H.FREE_MAX_POR_DIA - ya)
    if cupo <= 0:
        logger.info(f"[COLA FREE] tope diario alcanzado ({ya})")
        return
    listos = E.cola_listos()
    E.cola_limpiar()
    if not listos:
        logger.info("[COLA FREE] sin items listos")
        return
    # variedad: primero la mejor de cada tienda, luego el resto por score
    orden = sorted(listos, key=lambda e: e.get("score", 0), reverse=True)
    vistas, sel, resto = set(), [], []
    for e in orden:
        tienda = (e.get("item") or {}).get("tienda", "")
        (resto if tienda in vistas else sel).append(e)
        vistas.add(tienda)
    cola = (sel + resto)
    enviados, usados = [], []
    for e in cola:
        if len(enviados) >= cupo:
            break
        item = e.get("item") or {}
        usados.append(e["id"])
        if not item.get("nombre") or not item.get("url"):
            continue
        if E.item_hoy_publicado(item, "free"):
            continue
        mid = E.tg_send(FREE, fmt_free(item), boton=BTN_VIP,
                        foto=item["thumbnail"] if str(item.get("thumbnail", "")).startswith("http") else None)
        if mid:
            enviados.append(e["id"])
            E.registrar_publicacion(item, "free", e.get("score", 0), mid)
            time.sleep(6)
    E.cola_marcar(usados)
    logger.info(f"[COLA FREE] enviados={len(enviados)} (cupo {cupo}, hoy {ya})")


# ─────────────────────────────────────────────
# FUENTES
# ─────────────────────────────────────────────
def _con_respaldo(fn, clave):
    def run():
        try:
            r = fn() or []
        except Exception as e:
            logger.warning(f"[{clave}] principal falló: {e}")
            r = []
        if r:
            return r
        logger.info(f"[{clave}] principal vacío -> motor multi-tienda")
        return ciclo_multi(clave)
    return run


def _multi(clave):
    return lambda: ciclo_multi(clave)


SCRAPERS = [
    ("ML Deals API",   ciclo_ml_deals, 4),
    ("Temporada ML",   ciclo_temporada, 3),
    ("Walmart",        _con_respaldo(ciclo_walmart, "walmart"), 3),
    ("Liverpool",      _con_respaldo(ciclo_liverpool, "liverpool"), 3),
    ("Amazon",         _con_respaldo(ciclo_amazon, "amazon"), 3),
    ("Elektra",        _con_respaldo(ciclo_elektra, "elektra"), 3),
    ("Bodega Aurrerá", _con_respaldo(ciclo_bodega, "bodega"), 3),
    ("HEB",            _multi("heb"), 3),
    ("Palacio",        _con_respaldo(ciclo_palacio_a, "palacio"), 2),
    ("Sam's",          _con_respaldo(ciclo_sams_a, "sams"), 2),
    ("Costco",         _con_respaldo(ciclo_costco, "costco"), 2),
    ("Sears",          _con_respaldo(ciclo_sears, "sears"), 2),
    ("Coppel",         _con_respaldo(ciclo_coppel, "coppel"), 2),
    ("ML Marcas",      ciclo_marcas, 2),
    ("Petco API",      ciclo_petco_a, 1),
    ("Inditex",        ciclo_inditex, 1),
    ("Marcas Directo", ciclo_marcas_d, 1),
    ("TikTok Trend",   ciclo_tiktok, 1),
    ("SHEIN",          ciclo_shein, 1),
    ("AliExpress",     ciclo_aliexpress, 1),
]
_pool = []
for _n, _f, _p in SCRAPERS:
    _pool.extend([(_n, _f)] * _p)


def _correr_fuente(nombre, func):
    err = ""
    try:
        items = func() or []
    except Exception as e:
        items, err = [], str(e)
        logger.error(f"[CICLO] {nombre}: {e}", exc_info=True)
    E.log_fuente(nombre, len(items), err)
    if not items:
        logger.info(f"[CICLO] {nombre}: sin items")
        return 0
    vip_n = 0
    hoy = H.fecha_mx()
    for raw in sorted(items, key=lambda x: x.get("descuento", 0), reverse=True)[:20]:
        try:
            item = E.aplanar(raw)
            if item["descuento"] < 0.12 or item["precio_actual"] <= 0 or not item["url"]:
                continue
            try:
                bs = calcular_score(descuento_real=item["descuento"], stock=99, categoria=item["cat_nombre"],
                                    precio_actual=item["precio_actual"], precio_original=item["precio_original"])
            except Exception:
                bs = 4 if item["descuento"] >= 0.20 else 0
            sf = min(10, bs + score_bonus_temp(item["cat_nombre"]) + T.bonus_item(item["nombre"], item["cat_nombre"]))
            if sf < 3:
                continue
            try:
                verificar_match(item["nombre"], item["url"], item["precio_actual"], item["descuento"])
            except Exception:
                pass
            # ── VIP ──
            if sf >= 5 and vip_n < 2 and H.vip_puede_publicar(sf) and not E.item_hoy_publicado(item, "vip"):
                mid = E.tg_send(VIP, fmt_vip(item, sf),
                                foto=item["thumbnail"] if item["thumbnail"].startswith("http") else None)
                if mid:
                    vip_n += 1
                    item["en_vip"] = True
                    E.registrar_publicacion(item, "vip", sf, mid)
                    time.sleep(3)
            # ── Cola hacia el free (60 min) ──
            if H.puede_pasar_al_free(item["descuento"], sf, item["es_flash"]):
                if E.reclamar_evento(f"cola:{item['tienda']}:{item['sku']}:{hoy}", fallback=True):
                    E.cola_agregar(item, sf, vip_n, delay_min=H.VENTAJA_VIP_MIN)
        except Exception as e:
            logger.warning(f"[CICLO] item: {e}")
    if vip_n:
        fomo_vip_al_free(vip_n)
    logger.info(f"[CICLO] {nombre} -> items={len(items)} VIP={vip_n} nocturno={H.modo_nocturno()}")
    return vip_n


def ejecutar_ciclo():
    a = H.ahora()
    slot = a.hour * 4 + a.minute // 15
    n = len(_pool)
    elegidas, vistos = [], set()
    for idx in (slot % n, (slot + n // 2) % n):
        nombre, func = _pool[idx]
        if nombre not in vistos:
            vistos.add(nombre)
            elegidas.append((nombre, func))
    for nombre, func in elegidas:
        _correr_fuente(nombre, func)


# ─────────────────────────────────────────────
# TAREAS PERIÓDICAS (cada una una sola vez, con candado)
# ─────────────────────────────────────────────
def _claim(clave):
    return E.reclamar_evento(f"tp:{clave}", fallback=(H.ahora().minute < 15))


def tareas_periodicas():
    a = H.ahora()
    h, dia, mins, f = a.hour, a.weekday(), a.hour * 60 + a.minute, H.fecha_mx(a)

    # Cierre FREE: 6:00-7:00 PM  |  Cierre VIP: 11:00 PM en adelante (tope 11:59 como respaldo)
    if 18 * 60 <= mins <= H.FREE_FIN and _claim(f"resumen_free:{f}"):
        resumenes.resumen_free()
    if 23 * 60 <= mins <= 23 * 60 + 59 and _claim(f"resumen_vip:{f}"):
        resumenes.resumen_vip()
    if dia == 6 and h == 21 and _claim(f"semanal_vip:{a.isocalendar()[1]}"):
        resumenes.resumen_semanal_vip()
    if h == 8 and _claim(f"salud:{f}"):
        resumenes.reporte_salud_admin()

    if h in (11, 18) and H.en_horario_free() and _claim(f"financiero:{f}:{h}"):
        enviar_mensaje_financiero()
    if h in (12, 17) and H.en_horario_free() and _claim(f"recordatorio_vip:{f}:{h}"):
        enviar_recordatorio_vip()

    if os.environ.get("ENABLE_CUPONES", "0") == "1":        # apagado por defecto (ver HANDOFF.md)
        try:
            monitor_cupones()
        except Exception as e:
            logger.warning(f"[CUPONES] {e}")

    if dia == 0 and h == 9 and _claim(f"reporte_lunes:{f}"):
        _, ti = temporada_activa()
        t = T.actual()
        E.tg_send(VIP, f"<b>Reporte semanal — DropNode VIP</b>\n\nLa semana arranca con {t['emoji']} <b>{t['nombre']}</b>: "
                       f"el equipo prioriza {E.esc(', '.join(t['productos'][:3]))}.\n\n"
                       "<i>Horario VIP: 6:30 AM - 11:30 PM · de madrugada solo errores de precio (8+).</i>")
    try:
        alertas_temp()
    except Exception:
        pass


def setup():
    hc = E.db_health()
    logger.info(f"[DB] {hc}")
    if not hc.get("lectura") or not hc.get("escritura"):
        E.admin_msg(f"⚠️ DropNode: la base de datos no responde bien.\n{hc}",
                    clave=f"dbfail:{H.fecha_mx()}:{H.ahora().hour // 6}")
    try:
        if not canal_free_tiene_fijado():
            setup_canal_free()
        if GROUP_ID:
            import requests as req
            r = req.get(f"https://api.telegram.org/bot{E.TELEGRAM_TOKEN}/getChat", params={"chat_id": GROUP_ID}, timeout=10)
            if "pinned_message" not in r.json().get("result", {}):
                enviar_y_fijar_bienvenida_grupo()
    except Exception as e:
        logger.warning(f"[SETUP] {e}")


def _safe(nombre, fn):
    try:
        fn()
    except Exception as e:
        logger.error(f"[{nombre}] {e}", exc_info=True)
        E.admin_msg(f"⚠️ Error en {nombre}: {str(e)[:200]}", clave=f"err:{nombre}:{H.fecha_mx()}:{H.ahora().hour}")


if __name__ == "__main__":
    t = T.actual()
    logger.info(f"\n{'=' * 52}\n DROPNODE MX v3.6 — {H.ahora().strftime('%d/%m/%Y %H:%M')} MX · {t['emoji']} {t['nombre']}"
                f"{' · 🌙 NOCTURNO' if H.modo_nocturno() else ''}\n VIP 6:30-23:30 · Free 8:00-19:00 · ventana 60 min · {len(SCRAPERS)} fuentes\n{'=' * 52}")
    _safe("setup", setup)
    _safe("cola_free", procesar_cola_free)
    _safe("ciclo", ejecutar_ciclo)
    _safe("comunidad_lectura", procesar_actualizaciones)
    _safe("comunidad_programada", ejecutar_community_manager)
    _safe("tareas", tareas_periodicas)
    logger.info("[DROPNODE] Run completado.")
