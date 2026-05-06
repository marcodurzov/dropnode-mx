# =============================================================
# DROPNODE MX — main.py  (v2.2 Railway)
# ML scraping movido a GitHub Actions
# Railway maneja: Walmart, Liverpool, Coppel, Amazon, SHEIN
# + mensajes financieros, VIP, resumen, moderacion
# =============================================================

import schedule, time, logging, sys
import requests as req
from datetime import datetime, timezone, timedelta

from scraper_walmart   import ejecutar_ciclo_walmart   as ciclo_walmart
from scraper_liverpool import ejecutar_ciclo_liverpool  as ciclo_liverpool
from scraper_coppel    import ejecutar_ciclo_coppel     as ciclo_coppel
from scraper_amazon    import ejecutar_ciclo_amazon     as ciclo_amazon
from scraper_otros     import ejecutar_ciclo_aliexpress as ciclo_aliexpress
from scraper_otros     import ejecutar_ciclo_shein      as ciclo_shein

from telegram_bot import (
    enviar_resumen_diario, enviar_mensaje_financiero,
    enviar_recordatorio_vip, enviar_y_fijar_bienvenida_grupo,
    revisar_actualizaciones_grupo, enviar_mensaje,
    publicar_mejores_del_dia,
)
from auto_learning import ejecutar_autolearning
from heat_score    import calcular_heat_score
from config import (
    TELEGRAM_TOKEN, GROUP_ID, CHANNEL_FREE_ID, CHANNEL_VIP_ID,
    LAUNCHPASS_LINK, TIMEZONE_OFFSET_HOURS, FRECUENCIA_AUTOLEARNING_HORAS,
)

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout),
              logging.FileHandler("dropnode.log", encoding="utf-8")])
logger = logging.getLogger(__name__)

TZ_MEXICO = timezone(timedelta(hours=TIMEZONE_OFFSET_HOURS))
def hora_mx(): return datetime.now(TZ_MEXICO)
def dentro_de_horario(): return 8 <= hora_mx().hour < 22

contadores   = {"vip": 0, "free": 0, "fecha": hora_mx().date()}
ciclo_numero = 0

EMOJIS = {"walmart":"🛒","liverpool":"🏬","coppel":"🏪",
          "amazon":"📦","aliexpress":"🌐","shein":"👗"}

def resetear():
    hoy = hora_mx().date()
    if contadores["fecha"] != hoy:
        contadores.update({"vip":0,"free":0,"fecha":hoy})

def formatear_externa(item):
    tienda  = item["tienda"]
    nombre  = item["nombre"][:60]
    precio  = item["precio_actual"]
    precio_o= item["precio_original"]
    desc    = item["descuento"] * 100
    url     = item["url"]
    et      = EMOJIS.get(tienda,"🛍️")
    ec      = item["categoria"]["emoji"]

    free = (f"{et} *OFERTA {tienda.upper()}*  {ec}\n\n"
            f"*{nombre}*\n\n"
            f"*${precio:,.0f} MXN* (-{desc:.0f}%)\n"
            f"Antes: ${precio_o:,.0f} MXN\n\n"
            f"[Ver producto]({url})\n\n"
            f"_Nuestro equipo lo encontro._")

    vip = None
    if item["descuento"] >= 0.35:
        rl = precio_o * 0.78; rh = precio_o * 0.90
        vip = (f"🔥 *{tienda.upper()} — OFERTA EXCLUSIVA*  {ec}\n\n"
               f"*{nombre}*\n\n"
               f"*${precio:,.0f} MXN* (-{desc:.0f}%)\n"
               f"Normal: ${precio_o:,.0f} MXN\n\n"
               f"[COMPRAR AHORA]({url})\n\n"
               f"_Reventa estimada: ${rl:,.0f} - ${rh:,.0f} MXN_")
    return free, vip

def procesar_externa(items, max_a=2):
    publicadas = 0
    for item in items:
        if publicadas >= max_a: break
        score = calcular_heat_score(
            descuento_real=item["descuento"], stock=99,
            categoria=item["categoria"]["nombre"],
            precio_actual=item["precio_actual"],
            precio_original=item["precio_original"])
        if score < 3: continue
        free, vip = formatear_externa(item)
        if vip:
            enviar_mensaje(CHANNEL_VIP_ID, vip)
            contadores["vip"] += 1; time.sleep(3)
        enviar_mensaje(CHANNEL_FREE_ID, free)
        contadores["free"] += 1
        publicadas += 1; time.sleep(6)

def ciclo_externas():
    global ciclo_numero
    resetear()
    if not dentro_de_horario(): return
    ciclo_numero += 1
    logger.info(f"[CICLO #{ciclo_numero}] {hora_mx().strftime('%d/%m %H:%M')} MX")
    try:
        turno = ciclo_numero % 6
        if   turno == 1: procesar_externa(ciclo_walmart(), 2)
        elif turno == 2: procesar_externa(ciclo_liverpool(), 2)
        elif turno == 3: procesar_externa(ciclo_coppel(), 2)
        elif turno == 4: procesar_externa(ciclo_amazon(), 2)
        elif turno == 5: procesar_externa(ciclo_aliexpress(), 2)
        elif turno == 0: procesar_externa(ciclo_shein(), 2)
        logger.info(f"[CICLO] VIP:{contadores['vip']} Free:{contadores['free']}")
    except Exception as e:
        logger.error(f"[ERROR] {e}", exc_info=True)

def reporte_vip_semanal():
    if hora_mx().weekday() != 0: return
    msg = ("*Reporte semanal exclusivo — DropNode VIP*\n\n"
           "Esta semana monitoreamos 7 tiendas en tiempo real.\n\n"
           "Tip de flip de la semana:\n"
           "_iPhones reacondicionados certificados con 40%+ descuento "
           "en Liverpool tienen el mejor margen. "
           "Compra y revende en ML como nuevo._\n\n"
           f"Acceso VIP: {LAUNCHPASS_LINK}")
    enviar_mensaje(CHANNEL_VIP_ID, msg)

def grupo_tiene_fijado():
    try:
        r = req.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat",
                    params={"chat_id":GROUP_ID}, timeout=10)
        return "pinned_message" in r.json().get("result",{})
    except Exception: return False

def configurar():
    schedule.every(15).minutes.do(ciclo_externas)
    schedule.every(60).seconds.do(revisar_actualizaciones_grupo)
    # UTC = MX + 6h
    schedule.every().day.at("17:00").do(enviar_mensaje_financiero)  # 11 AM MX
    schedule.every().day.at("00:00").do(enviar_mensaje_financiero)  #  6 PM MX
    schedule.every().day.at("20:00").do(enviar_recordatorio_vip)    #  2 PM MX
    schedule.every().day.at("02:00").do(enviar_recordatorio_vip)    #  8 PM MX
    schedule.every().day.at("03:05").do(
        lambda: enviar_resumen_diario(contadores["vip"], contadores["free"]))
    schedule.every().day.at("15:00").do(reporte_vip_semanal)
    schedule.every(FRECUENCIA_AUTOLEARNING_HORAS).hours.do(ejecutar_autolearning)
    logger.info("Railway: Walmart|Liverpool|Coppel|Amazon|AliExpress|SHEIN")
    logger.info("ML scraping: GitHub Actions (cada 30 min)")

if __name__ == "__main__":
    logger.info(f"\n{'='*50}\n  DROPNODE MX v2.2 — {hora_mx().strftime('%d/%m/%Y %H:%M')} MX\n{'='*50}\n")
    if not grupo_tiene_fijado():
        enviar_y_fijar_bienvenida_grupo()
    ciclo_externas()
    configurar()
    logger.info("\nSistema activo.\n")
    while True:
        try:
            schedule.run_pending(); time.sleep(30)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"[ERROR loop] {e}"); time.sleep(60)
