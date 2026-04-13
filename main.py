# =============================================================
# DROPNODE MX — main.py  (version final)
# El orquestador principal — coordina todo el sistema
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
)
from auto_learning import ejecutar_autolearning
from heat_score import interpretar_score
from config import (
    FRECUENCIA_AUTOLEARNING_HORAS,
    HORAS_MENSAJES_FINANCIEROS,
    HORAS_RECORDATORIO_VIP,
)

# ─────────────────────────────────────────────
#  LOGGING — lo que ves en los logs de Railway
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("dropnode.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# Contadores del dia (se reinician a medianoche)
contadores = {
    "vip":   0,
    "free":  0,
    "fecha": datetime.now().date()
}


def resetear_si_nuevo_dia():
    hoy = datetime.now().date()
    if contadores["fecha"] != hoy:
        contadores["vip"]   = 0
        contadores["free"]  = 0
        contadores["fecha"] = hoy
        logger.info("[RESET] Contadores reiniciados para nuevo dia")


# ─────────────────────────────────────────────
#  CICLO PRINCIPAL (cada 15 minutos)
# ─────────────────────────────────────────────

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
                time.sleep(6)  # Pausa entre alertas para no saturar el canal
        logger.info(
            f"[CICLO] Fin — "
            f"VIP:{contadores['vip']} Free:{contadores['free']}"
        )
    except Exception as e:
        logger.error(f"[ERROR ciclo] {e}", exc_info=True)


# ─────────────────────────────────────────────
#  SCHEDULE — horario completo del sistema
# ─────────────────────────────────────────────

def configurar_schedule():
    # Scraping y alertas — cada 15 minutos
    schedule.every(15).minutes.do(ciclo_completo)

    # Mensajes de productos financieros — 2 veces al dia (11am y 6pm)
    for hora in HORAS_MENSAJES_FINANCIEROS:
        schedule.every().day.at(f"{hora:02d}:00").do(enviar_mensaje_financiero)

    # Recordatorio canal VIP — 2 veces al dia (2pm y 8pm)
    for hora in HORAS_RECORDATORIO_VIP:
        schedule.every().day.at(f"{hora:02d}:00").do(enviar_recordatorio_vip)

    # Resumen diario a las 9 PM
    schedule.every().day.at("21:00").do(
        lambda: enviar_resumen_diario(
            total_vip=contadores["vip"],
            total_free=contadores["free"]
        )
    )

    # Auto-learning cada 24 horas
    schedule.every(FRECUENCIA_AUTOLEARNING_HORAS).hours.do(ejecutar_autolearning)

    logger.info("Schedule configurado:")
    logger.info("  Scraping:           cada 15 min")
    logger.info(f"  Financieros:        {HORAS_MENSAJES_FINANCIEROS}h")
    logger.info(f"  Recordatorio VIP:   {HORAS_RECORDATORIO_VIP}h")
    logger.info("  Resumen diario:     21:00h")
    logger.info(f"  Auto-learning:      cada {FRECUENCIA_AUTOLEARNING_HORAS}h")


# ─────────────────────────────────────────────
#  ARRANQUE DEL SISTEMA
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("\n" + "=" * 50)
    logger.info("  DROPNODE MX — Sistema iniciado (version final)")
    logger.info("=" * 50 + "\n")

    # Primera vez que arranca: publica y fija bienvenida en el grupo
    bandera = "grupo_bienvenida_enviada.txt"
    if not os.path.exists(bandera):
        logger.info("[SETUP] Publicando bienvenida en grupo Community...")
        enviar_y_fijar_bienvenida_grupo()
        with open(bandera, "w") as f:
            f.write(datetime.now().isoformat())
        logger.info("[SETUP] Bienvenida publicada y fijada.")

    # Primer ciclo inmediato al arrancar
    logger.info("Ejecutando primer ciclo...")
    ciclo_completo()

    # Activar el schedule
    configurar_schedule()

    logger.info("\nSistema activo. Ctrl+C para detener.\n")

    # Loop infinito — el sistema corre para siempre
    while True:
        try:
            schedule.run_pending()
            time.sleep(30)
        except KeyboardInterrupt:
            logger.info("Sistema detenido manualmente.")
            break
        except Exception as e:
            logger.error(f"[ERROR loop] {e}")
            time.sleep(60)
