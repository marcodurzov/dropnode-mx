# =============================================================
# DROPNODE MX — main.py  (v1.8)
# + Webhook Make.com para videos automaticos
# + Umbral reducido para primeras alertas reales
# =============================================================

import schedule
import time
import logging
import sys
import os
import requests as req
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
    MAKE_WEBHOOK_URL,
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

contadores = {"vip": 0, "free": 0, "fecha": datetime.now().date()}


def resetear_si_nuevo_dia():
    hoy = datetime.now().date()
    if contadores["fecha"] != hoy:
        contadores["vip"]   = 0
        contadores["free"]  = 0
        contadores["fecha"] = hoy


def notificar_make_webhook(alerta: dict):
    """
    Envia los datos de la alerta a Make.com para generar el video.
    Solo se llama para alertas score 8+ (VIP).
    """
    if not MAKE_WEBHOOK_URL:
        return

    descuento_pct = round(alerta["descuento_real"] * 100)

    payload = {
        "nombre":       alerta["nombre"][:80],
        "precio":       str(round(alerta["precio_actual"])),
        "descuento":    str(descuento_pct),
        "thumbnail":    alerta.get("thumbnail", ""),
        "link":         alerta["permalink"],
        "categoria":    alerta["categoria"]["nombre"],
        "heat_score":   alerta["heat_score"],
        "tienda":       "Mercado Libre",
        "timestamp":    datetime.now().isoformat(),
    }

    try:
        resp = req.post(MAKE_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(f"[MAKE] Webhook enviado — {alerta['nombre'][:40]}")
        else:
            logger.warning(f"[MAKE] Webhook error {resp.status_code}")
    except Exception as e:
        logger.warning(f"[MAKE] Webhook exception: {e}")


def grupo_ya_tiene_mensaje_fijado() -> bool:
    try:
        resp = req.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat",
            params={"chat_id": GROUP_ID},
            timeout=10
        )
        data = resp.json()
        if data.get("ok"):
            return "pinned_message" in data.get("result", {})
    except Exception:
        pass
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
                    # Notificar Make.com para generar video
                    if alerta["heat_score"] >= 8:
                        notificar_make_webhook(alerta)
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

    logger.info("Schedule activo: scraping 15min | financieros %s | VIP CTA %s | resumen 21h",
                HORAS_MENSAJES_FINANCIEROS, HORAS_RECORDATORIO_VIP)


if __name__ == "__main__":
    logger.info("\n" + "=" * 50)
    logger.info("  DROPNODE MX - v1.8")
    logger.info("=" * 50 + "\n")

    if not grupo_ya_tiene_mensaje_fijado():
        logger.info("[SETUP] Publicando bienvenida en grupo...")
        enviar_y_fijar_bienvenida_grupo()

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
