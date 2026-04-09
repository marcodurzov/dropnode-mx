# =============================================================
# DROPNODE MX — auto_learning.py
# El sistema aprende de sus propios resultados
# Se ejecuta automáticamente cada 24 horas
# =============================================================

import logging
from datetime import datetime
from collections import defaultdict
from database import get_metricas_autolearning
from telegram_bot import enviar_mensaje
from config import CHANNEL_VIP_ID

logger = logging.getLogger(__name__)


def analizar_rendimiento() -> dict:
    """
    Analiza las alertas de los últimos 7 días y extrae patrones:
    - Qué heat scores generaron más clicks
    - Qué categorías rinden más
    - Qué horas son mejores para publicar
    - Cuál es el descuento óptimo para máximo engagement
    """
    datos = get_metricas_autolearning()

    if len(datos) < 5:
        logger.info("[AUTO-LEARN] Pocos datos todavía — acumulando")
        return {}

    # ── Analizar por heat score ───────────────────────
    clicks_por_score = defaultdict(list)
    clicks_por_hora  = defaultdict(list)
    clicks_por_canal = defaultdict(list)
    clicks_por_desc  = []

    for alerta in datos:
        score  = alerta.get("heat_score", 0)
        canal  = alerta.get("canal", "free")
        clicks = alerta.get("clicks", 0)
        desc   = alerta.get("descuento_real", 0)
        ts     = alerta.get("timestamp", "")

        clicks_por_score[score].append(clicks)
        clicks_por_canal[canal].append(clicks)
        clicks_por_desc.append((desc, clicks))

        # Extraer hora del timestamp
        if ts:
            try:
                hora = datetime.fromisoformat(ts).hour
                clicks_por_hora[hora].append(clicks)
            except Exception:
                pass

    # ── Calcular promedios ────────────────────────────
    def promedio(lista):
        return sum(lista) / len(lista) if lista else 0

    promedios_score = {
        score: promedio(clicks_list)
        for score, clicks_list in clicks_por_score.items()
    }

    promedios_hora = {
        hora: promedio(clicks_list)
        for hora, clicks_list in clicks_por_hora.items()
    }

    mejor_hora = max(promedios_hora.items(),
                     key=lambda x: x[1])[0] if promedios_hora else 10

    mejor_score = max(promedios_score.items(),
                      key=lambda x: x[1])[0] if promedios_score else 8

    # ── Calcular descuento óptimo ─────────────────────
    # Ordenar por clicks y tomar el percentil 75
    clicks_por_desc.sort(key=lambda x: x[1], reverse=True)
    n75 = max(1, len(clicks_por_desc) // 4)
    desc_top = [d for d, _ in clicks_por_desc[:n75]]
    desc_optimo = sum(desc_top) / len(desc_top) if desc_top else 0.40

    reporte = {
        "total_alertas":    len(datos),
        "mejor_hora":       mejor_hora,
        "mejor_score":      mejor_score,
        "desc_optimo":      desc_optimo,
        "promedios_score":  promedios_score,
        "promedios_hora":   promedios_hora,
        "fecha_analisis":   datetime.now().isoformat(),
    }

    logger.info(
        f"[AUTO-LEARN] "
        f"Mejor hora: {mejor_hora}h | "
        f"Mejor score: {mejor_score} | "
        f"Desc. óptimo: {desc_optimo*100:.0f}%"
    )

    return reporte


def generar_reporte_texto(reporte: dict) -> str:
    """
    Genera un reporte legible para enviar al canal VIP.
    Solo el sistema (Marco) lo ve — sin revelar nada al público.
    """
    if not reporte:
        return "📊 *Reporte semanal*\n\n_Acumulando datos..._"

    total  = reporte.get("total_alertas", 0)
    hora   = reporte.get("mejor_hora", "?")
    score  = reporte.get("mejor_score", "?")
    desc   = reporte.get("desc_optimo", 0) * 100

    # Top scores con más clicks
    promedios = reporte.get("promedios_score", {})
    top_scores = sorted(promedios.items(),
                        key=lambda x: x[1],
                        reverse=True)[:3]
    top_txt = " · ".join([f"Score {s}: {c:.1f}★" for s, c in top_scores])

    msg = f"""🧠 *Reporte de Rendimiento — DropNode MX*
📅 {datetime.now().strftime('%d/%m/%Y')}

📊 Alertas analizadas (7 días): *{total}*
⏰ Mejor hora para publicar: *{hora}:00 h*
🎯 Heat score con más respuesta: *{score}/10*
📉 Descuento que más convierte: *−{desc:.0f}%*

Top scores por engagement:
{top_txt}

_El sistema ajusta sus parámetros automáticamente._"""

    return msg


def ejecutar_autolearning():
    """
    Función principal: analiza, reporta y ajusta.
    Llamada automáticamente desde main.py cada 24 horas.
    """
    logger.info("[AUTO-LEARN] Iniciando análisis...")

    reporte = analizar_rendimiento()

    if reporte:
        texto = generar_reporte_texto(reporte)
        enviar_mensaje(CHANNEL_VIP_ID, texto)
        logger.info("[AUTO-LEARN] Reporte enviado al canal VIP")
    else:
        logger.info("[AUTO-LEARN] Sin suficientes datos todavía")

    return reporte
