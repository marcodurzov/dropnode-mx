# =============================================================
# DROPNODE MX — diagnostico.py  (v1.0)
# Se corre MANUAL desde GitHub: Actions -> "DropNode Diagnóstico" -> Run workflow.
# Dice, con datos reales desde los servidores de GitHub:
#   1) ¿Supabase responde? (DNS, lectura, escritura)
#   2) ¿La API de Mercado Libre responde (con/sin token)?
#   3) Por cada tienda: ¿carga la página, la bloquean, cuántos productos
#      saca cada estrategia, y una muestra?
#   4) Lo que devuelven los scrapers dedicados (Walmart, Liverpool, etc.)
# Con ADMIN_CHAT_ID configurado, además te manda el resumen por Telegram.
# =============================================================
import sys, logging, importlib, time
logging.basicConfig(level=logging.WARNING, format="%(message)s")

import estado as E
import ml_api
import scraper_multi as M

L = []
def out(s=""):
    print(s); L.append(s)

out("== 1) SUPABASE ==")
out(str(E.db_health()))

out("\n== 2) API MERCADO LIBRE ==")
t = ml_api.token()
out(f"token de aplicación: {'OK' if t else 'NO (sin ML_APP_ID/ML_SECRET o falló)'}")
r = ml_api.buscar("audifonos", limit=5)
out(f"búsqueda 'audifonos': {len(r)} resultados" + ("" if r else "  <-- la API no responde: revisar token/403"))
con_orig = sum(1 for x in r if x.get("original_price"))
out(f"  con precio original: {con_orig}/{len(r)}")

out("\n== 3) TIENDAS (motor multi) ==")
resumen = []
for clave in M.TIENDAS:
    d = {}
    try:
        items = M.scrapear_tienda(clave, diag=d)
    except Exception as e:
        items, d = [], {"error": str(e)[:100], "paginas": [], "estrategias": {}}
    pag = d.get("paginas", [])
    ok = sum(1 for p in pag if not p["nota"])
    bloq = sum(1 for p in pag if p["nota"] == "BLOQUEADA")
    out(f"\n[{clave}] páginas ok={ok}/{len(pag)} bloqueadas={bloq} items={len(items)} estrategias={d.get('estrategias')}")
    for p in pag[:4]:
        out(f"   {p['status']} {p['bytes']:>7}b {p['nota'] or 'ok':<10} {p['url'][:70]}")
    for m in d.get("muestra", []):
        out(f"   ej: {m}")
    resumen.append((clave, len(items), bloq, len(pag)))

out("\n== 4) SCRAPERS DEDICADOS ==")
dedic = [("scraper_walmart", "ejecutar_ciclo_walmart"), ("scraper_liverpool", "ejecutar_ciclo_liverpool"),
         ("scraper_coppel", "ejecutar_ciclo_coppel"), ("scraper_amazon", "ejecutar_ciclo_amazon"),
         ("scraper_elektra", "ejecutar_ciclo_elektra"), ("scraper_bodega", "ejecutar_ciclo_bodega"),
         ("scraper_api", "ejecutar_ciclo_ml_deals"), ("scraper_temporada", "ejecutar_ciclo_temporada")]
for mod, fn in dedic:
    try:
        n = len(getattr(importlib.import_module(mod), fn)() or [])
        out(f"{mod}.{fn}: {n} productos")
    except Exception as e:
        out(f"{mod}.{fn}: ERROR {str(e)[:100]}")

out("\n== RESUMEN ==")
for clave, n, b, p in resumen:
    estado = "✅ saca productos" if n else ("🚫 bloqueada (hace falta proxy)" if b and b == p else "⚠️ carga pero no extrae")
    out(f"{clave:<10} {n:>3}  {estado}")

if E.ADMIN_CHAT_ID:
    txt = "\n".join(L)
    for i in range(0, len(txt), 3800):
        E.tg_send(E.ADMIN_CHAT_ID, "<pre>" + E.esc(txt[i:i + 3800]) + "</pre>")
