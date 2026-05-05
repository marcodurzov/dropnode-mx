# =============================================================
# DROPNODE MX — main.py  (v2.1)
# + "Mejores del dia" publicados aunque no haya descuento
# + Todas las tiendas en rotacion
# + Timezone Mexico City (UTC-6)
# =============================================================

import schedule, time, logging, sys
import requests as req
from datetime import datetime, timezone, timedelta

from scraper_ml        import ejecutar_ciclo         as ciclo_ml
from scraper_walmart   import ejecutar_ciclo_walmart  as ciclo_walmart
from scraper_liverpool import ejecutar_ciclo_liverpool as ciclo_liverpool
from scraper_coppel    import ejecutar_ciclo_coppel   as ciclo_coppel
from scraper_amazon    import ejecutar_ciclo_amazon   as ciclo_amazon
from scraper_otros     import ejecutar_ciclo_aliexpress as ciclo_aliexpress
from scraper_otros     import ejecutar_ciclo_shein    as ciclo_shein

from telegram_bot import (
    enviar_alerta, enviar_resumen_diario,
    enviar_mensaje_financiero, enviar_recordatorio_vip,
    enviar_y_fijar_bienvenida_grupo, revisar_actualizaciones_grupo,
    enviar_mensaje,
)
from auto_learning import ejecutar_autolearning
from heat_score    import interpretar_score, calcular_heat_score
from config import (
    TELEGRAM_TOKEN, GROUP_ID, MAKE_WEBHOOK_URL,
    CHANNEL_FREE_ID, CHANNEL_VIP_ID, LAUNCHPASS_LINK,
    TIMEZONE_OFFSET_HOURS, FRECUENCIA_AUTOLEARNING_HORAS,
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
EMOJIS_TIENDA = {
    "walmart": "🛒", "liverpool": "🏬", "coppel": "🏪",
    "amazon": "📦", "aliexpress": "🌐", "shein": "👗",
}


def resetear_si_nuevo_dia():
    hoy = hora_mx().date()
    if contadores["fecha"] != hoy:
        contadores.update({"vip": 0, "free": 0, "fecha": hoy})
        logger.info(f"[RESET] {hoy}")


def notificar_make(alerta):
    if not MAKE_WEBHOOK_URL:
        return
    try:
        req.post(MAKE_WEBHOOK_URL, json={
            "nombre":    alerta["nombre"][:80],
            "precio":    str(round(alerta["precio_actual"])),
            "descuento": str(round(alerta["descuento_real"] * 100)),
            "thumbnail": alerta.get("thumbnail", ""),
            "link":      alerta.get("permalink", ""),
            "categoria": alerta["categoria"]["nombre"],
            "score":     alerta["heat_score"],
        }, timeout=10)
    except Exception:
        pass


def publicar_mejores_del_dia(destacados: list):
    """
    Publica un resumen de los mejores productos encontrados hoy
    aunque no tengan descuento formal. Genera contenido de valor diario.
    Se publica en canal free a las 12 PM y 7 PM.
    """
    if not destacados:
        return

    top = destacados[:5]   # Máximo 5 productos
    hora = hora_mx()
    titulo = "Mejores precios de la tarde" if hora.hour >= 15 else "Mejores precios del dia"

    msg = f"📋 *{titulo} — DropNode MX*\n\n"
    msg += "_Nuestro equipo revisó miles de productos. Estos destacan:_\n\n"

    for i, item in enumerate(top, 1):
        nombre  = item["nombre"][:45]
        precio  = item["precio_actual"]
        emoji   = item["categoria"]["emoji"]
        link    = item.get("permalink", "")
        desc    = item.get("descuento_real", 0) * 100

        linea = f"{i}. {emoji} [{nombre}]({link})\n   *${precio:,.0f} MXN*"
        if desc >= 10:
            linea += f" (-{desc:.0f}%)"
        msg += linea + "\n\n"

    msg += f"🔒 _Las alertas de errores de precio van directo al VIP._\n"
    msg += f"_{LAUNCHPASS_LINK}_"

    enviar_mensaje(CHANNEL_FREE_ID, msg)
    contadores["free"] += 1
    logger.info(f"[DESTACADOS] Publicados {len(top)} productos")


def formatear_alerta_externa(item):
    tienda   = item["tienda"]
    nombre   = item["nombre"][:60]
    precio   = item["precio_actual"]
    precio_o = item["precio_original"]
    desc     = item["descuento"] * 100
    url      = item["url"]
    emoji_t  = EMOJIS_TIENDA.get(tienda, "🛍️")
    emoji_c  = item["categoria"]["emoji"]

    msg_free = (
        f"{emoji_t} *OFERTA {tienda.upper()}*  {emoji_c}\n\n"
        f"{nombre}\n\n"
        f"*${precio:,.0f} MXN* (-{desc:.0f}%)\n"
        f"Antes: ${precio_o:,.0f} MXN\n\n"
        f"[Ver producto]({url})\n\n"
        f"_Nuestro equipo lo encontro._"
    )
    msg_vip = None
    if item["descuento"] >= 0.35:
        rl = precio_o * 0.75
        rh = precio_o * 0.88
        msg_vip = (
            f"🔥 *{tienda.upper()} — OFERTA EXCLUSIVA*  {emoji_c}\n\n"
            f"{nombre}\n\n"
            f"*${precio:,.0f} MXN* (-{desc:.0f}%)\n"
            f"Normal: ${precio_o:,.0f} MXN\n\n"
            f"[COMPRAR AHORA]({url})\n\n"
            f"_Reventa: ${rl:,.0f} – ${rh:,.0f} MXN_"
        )
    return msg_free, msg_vip


def procesar_tienda_externa(items, max_alertas=2):
    publicadas = 0
    for item in items:
        if publicadas >= max_alertas:
            break
        score = calcular_heat_score(
            descuento_real=item["descuento"], stock=99,
            categoria=item["categoria"]["nombre"],
            precio_actual=item["precio_actual"],
            precio_original=item["precio_original"],
        )
        if score < 3:
            continue
        msg_free, msg_vip = formatear_alerta_externa(item)
        if msg_vip:
            enviar_mensaje(CHANNEL_VIP_ID, msg_vip)
            contadores["vip"] += 1
            time.sleep(3)
        enviar_mensaje(CHANNEL_FREE_ID, msg_free)
        contadores["free"] += 1
        publicadas += 1
        time.sleep(6)


def ciclo_completo():
    global ciclo_numero
    resetear_si_nuevo_dia()
    if not dentro_de_horario():
        return

    ciclo_numero += 1
    logger.info(f"[CICLO #{ciclo_numero}] {hora_mx().strftime('%d/%m %H:%M')} MX")

    try:
        # ML — siempre
        alertas, destacados = ciclo_ml()

        for alerta in alertas:
            interp = interpretar_score(alerta["heat_score"])
            if interp["canal"] == "descartar":
                continue
            exito = enviar_alerta(alerta)
            if exito:
                if interp["canal"] == "vip":
                    contadores["vip"] += 1
                    if alerta["heat_score"] >= 8:
                        notificar_make(alerta)
                else:
                    contadores["free"] += 1
                time.sleep(6)

        # Publicar mejores del dia a las 12 PM y 7 PM hora MX
        hora = hora_mx().hour
        if hora in (12, 19) and hora_mx().minute < 15:
            publicar_mejores_del_dia(destacados)

        # Tiendas externas en rotacion (una por ciclo)
        turno = ciclo_numero % 6
        if   turno == 1: procesar_tienda_externa(ciclo_walmart(),    2)
        elif turno == 2: procesar_tienda_externa(ciclo_liverpool(),   2)
        elif turno == 3: procesar_tienda_externa(ciclo_coppel(),      2)
        elif turno == 4: procesar_tienda_externa(ciclo_amazon(),      2)
        elif turno == 5: procesar_tienda_externa(ciclo_aliexpress(),  2)
        elif turno == 0: procesar_tienda_externa(ciclo_shein(),       2)

        logger.info(f"[CICLO] Fin VIP:{contadores['vip']} Free:{contadores['free']}")

    except Exception as e:
        logger.error(f"[ERROR ciclo] {e}", exc_info=True)


def reporte_vip_semanal():
    if hora_mx().weekday() != 0:
        return
    msg = (
        "*Reporte semanal exclusivo — DropNode VIP*\n\n"
        "Esta semana monitoreamos 7 tiendas:\n"
        "ML, Walmart, Liverpool, Coppel, Amazon, AliExpress y SHEIN\n\n"
        "Tip de flip:\n"
        "_iPhones reacondicionados certificados con 40%+ descuento "
        "en Liverpool tienen el mejor margen de reventa en ML._\n\n"
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


def configurar_schedule():
    schedule.every(15).minutes.do(ciclo_completo)
    schedule.every(60).seconds.do(revisar_actualizaciones_grupo)

    # UTC equivalentes a hora Mexico (UTC-6)
    schedule.every().day.at("17:00").do(enviar_mensaje_financiero)   # 11 AM MX
    schedule.every().day.at("00:00").do(enviar_mensaje_financiero)   #  6 PM MX
    schedule.every().day.at("20:00").do(enviar_recordatorio_vip)     #  2 PM MX
    schedule.every().day.at("02:00").do(enviar_recordatorio_vip)     #  8 PM MX
    schedule.every().day.at("03:05").do(
        lambda: enviar_resumen_diario(contadores["vip"], contadores["free"])
    )
    schedule.every().day.at("15:00").do(reporte_vip_semanal)
    schedule.every(FRECUENCIA_AUTOLEARNING_HORAS).hours.do(ejecutar_autolearning)

    logger.info("Tiendas: ML | Walmart | Liverpool | Coppel | Amazon | AliExpress | SHEIN")


if __name__ == "__main__":
    logger.info("\n" + "=" * 50)
    logger.info(f"  DROPNODE MX v2.1 — {hora_mx().strftime('%d/%m/%Y %H:%M')} MX")
    logger.info("=" * 50 + "\n")

    if not grupo_tiene_fijado():
        enviar_y_fijar_bienvenida_grupo()

    ciclo_completo()
    configurar_schedule()

    logger.info("\nSistema activo. 7 tiendas monitoreadas.\n")

    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            logger.info("Sistema detenido.")
            break
        except Exception as e:
            logger.error(f"[ERROR loop] {e}")
            time.sleep(60)
