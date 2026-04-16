# =============================================================
# DROPNODE MX — main.py  (v1.4)
# Fix: verifica mensaje fijado antes de publicar bienvenida
# =============================================================

import schedule
import time
import logging
import sys
import os
from datetime import datetime
from scraper_ml import ejecutar_ciclo
from telegram_bot import (
    enviar_alerta,
    enviar_resumen_diario,
    enviar_mensaje_financiero,
    enviar_recordatorio_vip,
    enviar_y_fijar_bienvenida_grupo,
    revisar_actualizaciones_grupo,
)
from auto_learning import ejecutar_autolearning
from heat_score import interpretar_score
from config import (
    TELEGRAM_TOKEN, GROUP_ID,
    FRECUENCIA_AUTOLEARNING_HORAS,
    HORAS_MENSAJES_FINANCIEROS,
    HORAS_RECORDATORIO_VIP,
)
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("dropnode.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

contadores = {"vip": 0, "free": 0, "fecha": datetime.now().date()}


def resetear_si_nuevo_dia():
    hoy = datetime.now().date()
    if contadores["fecha"] != hoy:
        contadores["vip"]   = 0
        contadores["free"]  = 0
        contadores["fecha"] = hoy
        logger.info("[RESET] Contadores reiniciados")


def grupo_ya_tiene_mensaje_fijado() -> bool:
    """
    Verifica si el grupo ya tiene al menos un mensaje fijado.
    Evita publicar el mensaje de bienvenida multiples veces.
    """
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat",
            params={"chat_id": GROUP_ID},
            timeout=10
        )
        data = resp.json()
        if data.get("ok"):
            chat = data.get("result", {})
            # Si existe pinned_message, ya hay un mensaje fijado
            return "pinned_message" in chat
    except Exception as e:
        logger.warning(f"[SETUP] No se pudo verificar mensaje fijado: {e}")
    return False


def ciclo_completo():
    resetear_si_nuevo_dia()
    logger.info(f"[CICLO] {datetime.now().strftime('%d/%m %H:%M')}")
    try:
        alertas = ejecutar_ciclo()
        for alerta in alertas:
            interp = interpretar_score(alerta["heat_score"])
            if interp["canal"] == "descartar":
                continue
            exito = enviar_alerta(alerta)
            if exito:
                if interp["canal"] == "vip":
                    contadores["vip"] += 1
                else:
                    contadores["free"] += 1
                time.sleep(6)
        logger.info(
            f"[CICLO] Fin - VIP:{contadores['vip']} "
            f"Free:{contadores['free']}"
        )
    except Exception as e:
        logger.error(f"[ERROR ciclo] {e}", exc_info=True)


def configurar_schedule():
    schedule.every(15).minutes.do(ciclo_completo)
    schedule.every(60).seconds.do(revisar_actualizaciones_grupo)

    for hora in HORAS_MENSAJES_FINANCIEROS:
        schedule.every().day.at(f"{hora:02d}:00").do(enviar_mensaje_financiero)

    for hora in HORAS_RECORDATORIO_VIP:
        schedule.every().day.at(f"{hora:02d}:00").do(enviar_recordatorio_vip)

    schedule.every().day.at("21:00").do(
        lambda: enviar_resumen_diario(
            total_vip=contadores["vip"],
            total_free=contadores["free"]
        )
    )

    schedule.every(FRECUENCIA_AUTOLEARNING_HORAS).hours.do(ejecutar_autolearning)

    logger.info("Schedule configurado:")
    logger.info("  Scraping:          cada 15 min")
    logger.info("  Moderacion grupo:  cada 60 seg")
    logger.info(f"  Financieros:       {HORAS_MENSAJES_FINANCIEROS}h")
    logger.info(f"  Recordatorio VIP:  {HORAS_RECORDATORIO_VIP}h")
    logger.info("  Resumen diario:    21:00h")
    logger.info(f"  Auto-learning:     cada {FRECUENCIA_AUTOLEARNING_HORAS}h")


if __name__ == "__main__":
    logger.info("\n" + "=" * 50)
    logger.info("  DROPNODE MX - v1.4")
    logger.info("=" * 50 + "\n")

    # Solo publica bienvenida si el grupo NO tiene ningun mensaje fijado
    if not grupo_ya_tiene_mensaje_fijado():
        logger.info("[SETUP] Sin mensaje fijado — publicando bienvenida...")
        enviar_y_fijar_bienvenida_grupo()
        logger.info("[SETUP] Bienvenida publicada y fijada.")
    else:
        logger.info("[SETUP] El grupo ya tiene mensaje fijado — omitiendo.")

    logger.info("Ejecutando primer ciclo...")
    ciclo_completo()
    configurar_schedule()

    logger.info("\nSistema activo.\n")

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
