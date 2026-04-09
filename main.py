# =============================================================
# DROPNODE MX — main.py
# Orquestador principal del sistema
# Coordina scraping, scoring, envío y auto-learning
# =============================================================

import schedule
import time
import logging
import sys
from datetime import datetime
from scraper_ml import ejecutar_ciclo
from telegram_bot import enviar_alerta, enviar_resumen_diario
from auto_learning import ejecutar_autolearning
from heat_score import interpretar_score
from config import FRECUENCIA_AUTOLEARNING_HORAS

# ─────────────────────────────────────────────
#  LOGGING — ver qué hace el sistema en tiempo real
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


# ─────────────────────────────────────────────
#  CICLO PRINCIPAL
# ─────────────────────────────────────────────

def ciclo_completo():
    """
    1. Ejecuta scraping de todas las categorías
    2. Filtra por heat score
    3. Envía alertas a los canales correctos
    4. Registra resultados para auto-learning
    """
    logger.info(f"\n{'='*55}")
    logger.info(f"🚀 CICLO INICIADO — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    logger.info(f"{'='*55}\n")

    try:
        # Ejecutar scraping
        alertas = ejecutar_ciclo()

        if not alertas:
            logger.info("Sin alertas válidas en este ciclo")
            return

        enviadas_vip  = 0
        enviadas_free = 0

        for alerta in alertas:
            score  = alerta["heat_score"]
            interp = interpretar_score(score)

            if interp["canal"] == "descartar":
                continue

            exito = enviar_alerta(alerta)

            if exito:
                if interp["canal"] == "vip":
                    enviadas_vip += 1
                else:
                    enviadas_free += 1

                logger.info(
                    f"✅ Alerta enviada: {alerta['nombre'][:40]} | "
                    f"Score {score} → {interp['canal'].upper()}"
                )

                # Pausa entre alertas para no saturar el canal
                time.sleep(5)

        logger.info(
            f"\n📊 Ciclo terminado: "
            f"{enviadas_vip} VIP | {enviadas_free} Free"
        )

    except Exception as e:
        logger.error(f"[ERROR CRÍTICO en ciclo] {e}", exc_info=True)


def resumen_diario():
    """Envía resumen de actividad del día a las 9 PM."""
    try:
        # Para el resumen real necesitaríamos contar del día
        # Por ahora mandamos un mensaje motivacional + recordatorio VIP
        enviar_resumen_diario(
            total_alertas=0,   # Se actualizará con datos reales después
            total_vip=0,
            total_free=0
        )
    except Exception as e:
        logger.error(f"[ERROR resumen diario] {e}")


def autolearning_diario():
    """Ejecuta el análisis de auto-learning."""
    try:
        ejecutar_autolearning()
    except Exception as e:
        logger.error(f"[ERROR auto-learning] {e}")


# ─────────────────────────────────────────────
#  SCHEDULER — CUÁNDO HACE CADA COSA
# ─────────────────────────────────────────────

def configurar_schedule():
    """
    Programa todas las tareas automáticas.

    Horario:
    - Cada 15 min: ciclo de scraping y alertas
    - 21:00: resumen diario al canal VIP
    - Cada 24h: auto-learning y optimización
    """

    # Scraping cada 15 minutos (ajustable)
    schedule.every(15).minutes.do(ciclo_completo)

    # Resumen diario a las 9 PM
    schedule.every().day.at("21:00").do(resumen_diario)

    # Auto-learning cada 24 horas
    schedule.every(FRECUENCIA_AUTOLEARNING_HORAS).hours.do(autolearning_diario)

    logger.info("✅ Schedule configurado:")
    logger.info("   • Scraping: cada 15 minutos")
    logger.info("   • Resumen diario: 21:00")
    logger.info(f"   • Auto-learning: cada {FRECUENCIA_AUTOLEARNING_HORAS}h")


# ─────────────────────────────────────────────
#  PUNTO DE ENTRADA
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("\n" + "="*55)
    logger.info("  🟢 DROPNODE MX — Sistema iniciado")
    logger.info("="*55 + "\n")

    # Ejecutar un ciclo inmediatamente al arrancar
    logger.info("▶ Ejecutando primer ciclo inmediato...")
    ciclo_completo()

    # Configurar el scheduler para ciclos futuros
    configurar_schedule()

    logger.info("\n⏳ Sistema en modo continuo. Ctrl+C para detener.\n")

    # Loop infinito — el sistema corre para siempre
    while True:
        try:
            schedule.run_pending()
            time.sleep(30)  # Verificar el schedule cada 30 segundos
        except KeyboardInterrupt:
            logger.info("\n⛔ Sistema detenido manualmente.")
            break
        except Exception as e:
            logger.error(f"[ERROR en loop principal] {e}")
            time.sleep(60)  # Esperar 1 min y reintentar
