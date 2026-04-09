# =============================================================
# DROPNODE MX — heat_score.py
# Motor de puntuación de ofertas (0-10)
# Determina si una alerta va a VIP, Free, o se descarta
# =============================================================

import logging
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CATEGORÍAS DE ALTO VALOR PARA FLIPPERS
#  (electrodomésticos y tech se revenden bien)
# ─────────────────────────────────────────────
CATEGORIAS_FLIPEABLE = {
    "Celulares":        3.0,
    "Computación":      3.0,
    "Televisores":      2.5,
    "Electrónica":      2.0,
    "Videojuegos":      2.0,
    "Electrodomésticos":1.5,
    "Herramientas":     1.0,
    "Deportes":         0.5,
}

# Precios mínimos por categoría para filtrar basura
PRECIO_MINIMO_CATEGORIA = {
    "Celulares":        1_500,
    "Computación":      1_500,
    "Televisores":      2_000,
    "Electrónica":      500,
    "Videojuegos":      300,
    "Electrodomésticos":800,
    "Herramientas":     300,
    "Deportes":         200,
}


def calcular_heat_score(descuento_real: float, stock: int,
                         categoria: str, precio_actual: float,
                         precio_original: float) -> int:
    """
    Calcula el Heat Score de 0 a 10 para una oferta.

    Criterios:
    ┌──────────────────────────────┬──────┐
    │ Criterio                     │ Pts  │
    ├──────────────────────────────┼──────┤
    │ % descuento real             │ 0-3  │
    │ Categoría flipeable          │ 0-3  │
    │ Urgencia de stock            │ 0-2  │
    │ Precio atractivo (ticket)    │ 0-1  │
    │ Descuento vs precio tachado  │ 0-1  │
    └──────────────────────────────┴──────┘
    Total máximo: 10
    """
    score = 0.0

    # ── 1. DESCUENTO REAL (0-3 pts) ──────────────────
    # vs mínimo histórico de 90 días — el dato más confiable
    if descuento_real >= 0.70:
        score += 3.0   # 70%+ = error de precio casi seguro
    elif descuento_real >= 0.55:
        score += 2.5   # 55-69% = muy agresivo
    elif descuento_real >= 0.40:
        score += 2.0   # 40-54% = excelente
    elif descuento_real >= 0.30:
        score += 1.5   # 30-39% = bueno
    elif descuento_real >= 0.20:
        score += 0.8   # 20-29% = aceptable
    else:
        score += 0.2   # <20% = marginal

    # ── 2. CATEGORÍA FLIPEABLE (0-3 pts) ─────────────
    puntos_cat = CATEGORIAS_FLIPEABLE.get(categoria, 0.5)
    score += puntos_cat

    # ── 3. URGENCIA DE STOCK (0-2 pts) ───────────────
    if stock == 1:
        score += 2.0   # Última unidad — máxima urgencia
    elif stock <= 3:
        score += 1.8
    elif stock <= 5:
        score += 1.5
    elif stock <= 10:
        score += 1.0
    elif stock <= 20:
        score += 0.5
    else:
        score += 0.0   # Stock alto = menos urgencia

    # ── 4. TICKET MÍNIMO (0-1 pt) ────────────────────
    # Productos muy baratos no valen el ruido en el canal
    precio_min = PRECIO_MINIMO_CATEGORIA.get(categoria, 200)
    if precio_actual >= precio_min * 3:
        score += 1.0   # Producto de ticket alto en oferta
    elif precio_actual >= precio_min:
        score += 0.5
    else:
        score += 0.0   # Muy barato para la categoría

    # ── 5. DESCUENTO VS PRECIO TACHADO (0-1 pt) ──────
    # Este es secundario — el precio tachado puede estar inflado
    # Solo suma si el descuento vs tachado TAMBIÉN es significativo
    if precio_original > 0:
        descuento_tachado = (precio_original - precio_actual) / precio_original
        if descuento_tachado >= 0.50:
            score += 1.0
        elif descuento_tachado >= 0.30:
            score += 0.5

    # ── Redondear a entero (0-10) ─────────────────────
    score_final = min(10, round(score))

    logger.debug(
        f"[SCORE] {categoria} | "
        f"desc={descuento_real*100:.0f}% | "
        f"stock={stock} | "
        f"precio=${precio_actual:,.0f} | "
        f"→ {score_final}/10"
    )

    return score_final


def interpretar_score(score: int) -> dict:
    """
    Retorna canal destino y emoji según el score.
    """
    if score >= 8:
        return {
            "canal":     "vip",
            "emoji":     "🚨",
            "etiqueta":  "ERROR DE PRECIO",
            "urgencia":  "ALERTA MÁXIMA",
        }
    elif score >= 6:
        return {
            "canal":     "vip",
            "emoji":     "🔥",
            "etiqueta":  "OFERTA AGRESIVA",
            "urgencia":  "Stock limitado",
        }
    elif score >= 5:
        return {
            "canal":     "free",
            "emoji":     "⚡",
            "etiqueta":  "DESCUENTO REAL",
            "urgencia":  "Precio mínimo histórico",
        }
    else:
        return {
            "canal":     "descartar",
            "emoji":     "",
            "etiqueta":  "",
            "urgencia":  "",
        }
