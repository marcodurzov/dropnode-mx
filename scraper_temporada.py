# =============================================================
# DROPNODE MX — scraper_temporada.py  (v1.0)
# Busca en Mercado Libre los productos del TEMA del mes
# (playa en marzo, regreso a clases en julio, etc.) usando
# temporada_calendario.py. Complementa las categorías fijas (electrónica).
# =============================================================
import logging
import ml_api
import temporada_calendario as T

logger = logging.getLogger(__name__)


def ejecutar_ciclo_temporada():
    t = T.actual()
    res, vistos = [], set()
    for q in T.queries_rotativas(3):
        for it in ml_api.buscar(q, limit=40):
            try:
                precio = float(it.get("price") or 0)
                orig = float(it.get("original_price") or 0)
                if precio <= 0 or orig <= precio:
                    continue
                desc = (orig - precio) / orig
                sku = str(it.get("id", ""))
                if desc < 0.15 or desc > 0.9 or sku in vistos or not it.get("permalink"):
                    continue
                vistos.add(sku)
                res.append({
                    "tienda": "mercadolibre", "nombre": str(it.get("title", ""))[:90],
                    "precio_actual": precio, "precio_original": orig, "descuento": desc,
                    "sku": sku, "url": it["permalink"],
                    "thumbnail": str(it.get("thumbnail", "")).replace("I.jpg", "O.jpg"),
                    "categoria": {"nombre": t["nombre"], "emoji": t["emoji"]},
                    "envio_gratis": bool((it.get("shipping") or {}).get("free_shipping")),
                })
            except Exception:
                continue
    res.sort(key=lambda x: x["descuento"], reverse=True)
    logger.info(f"[TEMPORADA] {t['nombre']}: {len(res)} productos")
    return res[:15]
