# =============================================================
# DROPNODE MX — scraper_ml_catalogo.py  (v1.0)
# Ofertas de Mercado Libre SIN navegador y SIN /sites/MLM/search (que da 403):
# más vendidos de cada categoría (highlights) -> producto ganador -> /items
# (precio, precio original, permalink). Solo deja lo que tiene descuento real.
# =============================================================
import logging, random
import ml_api
import horarios as H

logger = logging.getLogger(__name__)

CATEGORIAS = [
    ("MLM1051", "Celulares", "📱"), ("MLM1648", "Computación", "💻"), ("MLM1002", "Televisores", "📺"),
    ("MLM1144", "Videojuegos", "🎮"), ("MLM1574", "Electrodomésticos", "🏠"), ("MLM1000", "Electrónica", "🔌"),
    ("MLM1276", "Juguetes", "🧸"), ("MLM1430", "Deportes", "⚽"), ("MLM1246", "Belleza", "💄"),
    ("MLM1182", "Moda", "👗"),
]


def a_item(body, cat_n="Mercado Libre", cat_e="🛒"):
    """body de /items -> item estándar (o None si no hay descuento real)."""
    try:
        precio = float(body.get("price") or 0)
        orig = float(body.get("original_price") or 0)
        if precio <= 0 or orig <= precio or body.get("status") not in (None, "active"):
            return None
        if body.get("condition") not in (None, "new"):
            return None
        desc = (orig - precio) / orig
        link = body.get("permalink") or ""
        if desc < 0.15 or desc > 0.9 or not link:
            return None
        return {
            "tienda": "mercadolibre", "nombre": str(body.get("title", ""))[:90],
            "precio_actual": precio, "precio_original": orig, "descuento": desc,
            "sku": str(body.get("id", "")), "url": link,
            "thumbnail": str(body.get("thumbnail", "")).replace("I.jpg", "O.jpg"),
            "categoria": {"nombre": cat_n, "emoji": cat_e},
            "envio_gratis": bool((body.get("shipping") or {}).get("free_shipping")),
        }
    except Exception:
        return None


def ejecutar_ciclo_ml_catalogo():
    a = H.ahora()
    base = (a.timetuple().tm_yday * 4 + a.hour // 6 + a.minute // 15) % len(CATEGORIAS)
    elegidas = [CATEGORIAS[base], CATEGORIAS[(base + 3) % len(CATEGORIAS)]]
    res, vistos = [], set()
    for cat_id, cat_n, cat_e in elegidas:
        try:
            bodies = ml_api.highlights_items(cat_id)
        except Exception as e:
            logger.warning(f"[ML CATALOGO] {cat_id}: {e}")
            continue
        n = 0
        for b in bodies:
            it = a_item(b, cat_n, cat_e)
            if it and it["sku"] not in vistos:
                vistos.add(it["sku"]); res.append(it); n += 1
        logger.info(f"[ML CATALOGO] {cat_n}: {len(bodies)} items leídos, {n} con descuento real")
    res.sort(key=lambda x: x["descuento"], reverse=True)
    return res[:15]
