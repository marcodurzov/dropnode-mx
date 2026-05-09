# =============================================================
# DROPNODE MX — main.py v2.5 Railway
# + Cola FOMO: free recibe 2 ciclos después que VIP
# + Selección: 1 high-score + hasta 2 más por ciclo al free
# + Mensaje free menciona siempre que llegó antes al VIP
# =============================================================

import schedule, time, logging, sys
import requests as req
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
    revisar_actualizaciones_grupo,
    enviar_mensaje,
    publicar_mejores_del_dia,
    setup_canal_free,
    canal_free_tiene_fijado,
)
from auto_learning     import ejecutar_autolearning
from community_manager import ejecutar_community_manager
from heat_score        import calcular_heat_score
from peticiones        import verificar_match
from config import (
    TELEGRAM_TOKEN, GROUP_ID, CHANNEL_FREE_ID, CHANNEL_VIP_ID,
    LAUNCHPASS_LINK, TIMEZONE_OFFSET_HOURS, FRECUENCIA_AUTOLEARNING_HORAS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("dropnode.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

TZ_MEXICO = timezone(timedelta(hours=TIMEZONE_OFFSET_HOURS))


def hora_mx():
    return datetime.now(TZ_MEXICO)


def dentro_de_horario():
    return 8 <= hora_mx().hour < 22


contadores   = {"vip": 0, "free": 0, "fecha": hora_mx().date()}
ciclo_numero = 0

# ── Cola FOMO ──────────────────────────────────────────────
# Items en espera para envío retrasado al canal free.
# Estructura: {item, ciclo_agregado, n_vip_ese_ciclo, score}
_cola_free   = []
_CICLOS_DELAY = 2   # Ciclos a esperar antes de enviar al free (2 × 15min = 30min)
_MAX_FREE_POR_CICLO = 3   # Máximo a enviar al free por ciclo (1 top + 2 más)

EMOJIS = {
    "walmart":      "🛒",
    "liverpool":    "🏬",
    "coppel":       "🏪",
    "amazon":       "📦",
    "aliexpress":   "🌐",
    "shein":        "👗",
    "samsung":      "📱",
    "sony":         "🎮",
    "lg":           "📺",
    "lenovo":       "💻",
    "dell":         "💻",
    "hp":           "💻",
    "asus":         "💻",
    "xiaomi":       "📱",
    "ghia":         "💻",
    "hisense":      "📺",
    "tcl":          "📺",
    "tiktok_trend": "🎵",
}


def resetear():
    hoy = hora_mx().date()
    if contadores["fecha"] != hoy:
        contadores.update({"vip": 0, "free": 0, "fecha": hoy})
        _cola_free.clear()


# ─────────────────────────────────────────────
# FORMATO MENSAJES EXTERNOS
# ─────────────────────────────────────────────

def formatear_externa_vip(item):
    """Mensaje VIP para scrapers externos (Walmart, Liverpool, etc.)"""
    tienda   = item["tienda"]
    nombre   = item["nombre"][:60]
    precio   = item["precio_actual"]
    precio_o = item["precio_original"]
    desc     = item["descuento"] * 100
    url      = item["url"]
    et       = EMOJIS.get(tienda, "🛍️")
    ec       = item["categoria"]["emoji"]
    tienda_d = tienda.upper() if tienda in (
        "samsung", "sony", "lg", "lenovo", "dell", "hp",
        "asus", "xiaomi", "ghia", "hisense", "tcl"
    ) else tienda.capitalize()
    rl = precio_o * 0.78
    rh = precio_o * 0.90

    return (
        f"{et} *{tienda_d} — OFERTA EXCLUSIVA* {ec}\n\n"
        f"*{nombre}*\n\n"
        f"*${precio:,.0f} MXN* (-{desc:.0f}%)\n"
        f"Normal: ${precio_o:,.0f} MXN\n\n"
        f"[COMPRAR AHORA]({url})\n\n"
        f"_Reventa estimada: ${rl:,.0f} - ${rh:,.0f} MXN_"
    )


def formatear_externa_free_fomo(item, n_vip_ese_ciclo, n_exclusivos, delay_min):
    """
    Mensaje FOMO para el canal free.
    Llega siempre con delay de 2 ciclos (30 min) vs VIP.
    Menciona cuánto tiempo lleva en VIP y qué se perdió.
    """
    tienda   = item["tienda"]
    nombre   = item["nombre"][:55]
    precio   = item["precio_actual"]
    precio_o = item["precio_original"]
    desc     = item["descuento"] * 100
    url      = item["url"]
    et       = EMOJIS.get(tienda, "🛍️")
    ec       = item["categoria"]["emoji"]
    tienda_d = tienda.upper() if tienda in (
        "samsung", "sony", "lg", "lenovo", "dell", "hp",
        "asus", "xiaomi", "ghia", "hisense", "tcl"
    ) else tienda.capitalize()

    # Texto de tiempo transcurrido
    if delay_min < 60:
        delay_txt = f"{delay_min} minutos"
    else:
        h = delay_min // 60
        delay_txt = f"{h} hora{'s' if h > 1 else ''}"

    m  = f"{et} <b>OFERTA {tienda_d}</b> {ec}\n\n"
    m += f"<b>{nombre}</b>\n\n"
    m += f"<b>${precio:,.0f} MXN</b> (-{desc:.0f}%)\n"
    if precio_o > precio:
        m += f"<s>${precio_o:,.0f}</s>\n"
    m += f"\n<a href=\"{url}\">Ver oferta</a>\n\n"

    # Bloque FOMO — siempre presente
    m += f"<i>Esta alerta llegó al Canal VIP hace {delay_txt} con análisis de reventa completo.</i>\n"
    if n_exclusivos > 0:
        m += (f"<i>En ese mismo ciclo hubo "
              f"{n_exclusivos} oportunidad{'es' if n_exclusivos > 1 else ''} "
              f"exclusiva{'s' if n_exclusivos > 1 else ''} que no llegaron aquí.</i>\n")
    m += "<i>Los miembros VIP actúan primero — la ventana de tiempo importa.</i>\n"

    if LAUNCHPASS_LINK:
        m += f"\n<a href=\"{LAUNCHPASS_LINK}\">📲 Unirse al Canal VIP — $299/mes</a>"
    return m


# ─────────────────────────────────────────────
# COLA FOMO
# ─────────────────────────────────────────────

def agregar_a_cola(item, score, n_vip_ese_ciclo):
    """Encola un item para enviarse al free en ciclos posteriores."""
    _cola_free.append({
        "item":    item,
        "ciclo":   ciclo_numero,
        "n_vip":   n_vip_ese_ciclo,
        "score":   score,
    })


def procesar_cola_free():
    """
    Revisa la cola y envía al free los items que llevan >= _CICLOS_DELAY ciclos.
    Selección: 1 de mayor score + hasta 2 más.
    """
    if not _cola_free:
        return

    ahora  = ciclo_numero
    listos = [x for x in _cola_free if ahora - x["ciclo"] >= _CICLOS_DELAY]
    if not listos:
        return

    # Limpiar los listos de la cola
    for x in listos:
        if x in _cola_free:
            _cola_free.remove(x)

    # Limpiar también los muy viejos (> 8 ciclos = 2h) sin enviar
    viejos = [x for x in _cola_free if ahora - x["ciclo"] > 8]
    for x in viejos:
        if x in _cola_free:
            _cola_free.remove(x)

    # Ordenar por score descendente
    listos.sort(key=lambda x: x["score"], reverse=True)

    # Seleccionar: 1 top + hasta 2 más = máximo 3
    seleccionados  = [listos[0]]
    seleccionados += listos[1:_MAX_FREE_POR_CICLO]

    # Cuántas oportunidades NO van al free (exclusivas VIP)
    n_excl_total = sum(x["n_vip"] for x in listos) - len(seleccionados)
    n_excl_total = max(0, n_excl_total)

    logger.info(f"[COLA FREE] Enviando {len(seleccionados)} de {len(listos)} listos")

    for i, entrada in enumerate(seleccionados):
        item      = entrada["item"]
        n_vip     = entrada["n_vip"]
        delay_min = (ahora - entrada["ciclo"]) * 15

        # Solo mencionar exclusivos en el primero del lote
        n_excl = n_excl_total if i == 0 else 0

        msg = formatear_externa_free_fomo(item, n_vip, n_excl, delay_min)
        enviar_mensaje(CHANNEL_FREE_ID, msg, parse_mode="HTML")
        contadores["free"] += 1
        time.sleep(6)


# ─────────────────────────────────────────────
# CICLO PRINCIPAL
# ─────────────────────────────────────────────

def procesar_externa(items, max_vip=2):
    """
    Envía al VIP directamente si el score lo amerita.
    Agrega a la cola del free — NO envía al free directamente.
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

        # Check peticiones de la comunidad
        try:
            verificar_match(item["nombre"], item["url"], item["precio_actual"])
        except Exception:
            pass

        # VIP: directo si score alto y no superamos el límite del ciclo
        if score >= 6 and vip_este_ciclo < max_vip:
            enviar_mensaje(CHANNEL_VIP_ID, formatear_externa_vip(item))
            contadores["vip"] += 1
            vip_este_ciclo += 1
            time.sleep(3)

        # Encolar para el free (todos los que pasaron score >= 3)
        agregar_a_cola(item, score, vip_este_ciclo)

    return vip_este_ciclo


def ciclo_externas():
    global ciclo_numero
    resetear()
    if not dentro_de_horario():
        return

    ciclo_numero += 1
    logger.info(f"[CICLO #{ciclo_numero}] {hora_mx().strftime('%d/%m %H:%M')} MX")

    try:
        turno = ciclo_numero % 8
        if   turno == 1: procesar_externa(ciclo_walmart(),    2)
        elif turno == 2: procesar_externa(ciclo_liverpool(),  2)
        elif turno == 3: procesar_externa(ciclo_coppel(),     2)
        elif turno == 4: procesar_externa(ciclo_amazon(),     2)
        elif turno == 5: procesar_externa(ciclo_aliexpress(), 2)
        elif turno == 6: procesar_externa(ciclo_shein(),      2)
        elif turno == 7: procesar_externa(ciclo_marcas(),     2)
        elif turno == 0: procesar_externa(ciclo_tiktok(),     2)

        # Procesar cola del free SIEMPRE al final del ciclo
        procesar_cola_free()

        logger.info(f"[CICLO] VIP:{contadores['vip']} Free:{contadores['free']} Cola:{len(_cola_free)}")
    except Exception as e:
        logger.error(f"[ERROR] {e}", exc_info=True)


def reporte_vip_semanal():
    if hora_mx().weekday() != 0:
        return
    msg = (
        "*Reporte semanal exclusivo — DropNode VIP*\n\n"
        "Esta semana monitoreamos tiendas y marcas en tiempo real.\n\n"
        "Tip de flip de la semana:\n"
        "_iPhones reacondicionados certificados con 40%+ descuento "
        "en Liverpool tienen el mejor margen. "
        "Compra y revende en ML como nuevo._\n\n"
        f"Acceso VIP: {LAUNCHPASS_LINK}"
    )
    enviar_mensaje(CHANNEL_VIP_ID, msg)


def grupo_tiene_fijado():
    try:
        r = req.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat",
                    params={"chat_id": GROUP_ID}, timeout=10)
        return "pinned_message" in r.json().get("result", {})
    except Exception:
        return False


def configurar():
    schedule.every(15).minutes.do(ciclo_externas)
    schedule.every(60).seconds.do(revisar_actualizaciones_grupo)

    # UTC = MX + 6h
    schedule.every().day.at("17:00").do(enviar_mensaje_financiero)   # 11 AM MX
    schedule.every().day.at("00:00").do(enviar_mensaje_financiero)   # 6  PM MX
    schedule.every().day.at("20:00").do(enviar_recordatorio_vip)     # 2  PM MX
    schedule.every().day.at("02:00").do(enviar_recordatorio_vip)     # 8  PM MX
    schedule.every().day.at("03:05").do(
        lambda: enviar_resumen_diario(contadores["vip"], contadores["free"])
    )
    schedule.every().day.at("15:00").do(reporte_vip_semanal)
    schedule.every(FRECUENCIA_AUTOLEARNING_HORAS).hours.do(ejecutar_autolearning)
    schedule.every().hour.do(ejecutar_community_manager)

    logger.info("Railway: Walmart|Liverpool|Coppel|Amazon|AliExpress|SHEIN|Marcas|TikTok")
    logger.info("ML: GitHub Actions cada 30min")
    logger.info("Free channel: cola FOMO — delay 2 ciclos (30min)")


if __name__ == "__main__":
    logger.info(
        f"\n{'='*50}\n"
        f" DROPNODE MX v2.5 — {hora_mx().strftime('%d/%m/%Y %H:%M')} MX\n"
        f"{'='*50}\n"
    )

    if not grupo_tiene_fijado():
        enviar_y_fijar_bienvenida_grupo()

    if not canal_free_tiene_fijado():
        setup_canal_free()

    ciclo_externas()
    configurar()
    logger.info("\nSistema activo.\n")

    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"[ERROR loop] {e}")
            time.sleep(60)