# =============================================================
# DROPNODE MX — diagnostico.py  (v2.0)
# Se corre MANUAL desde GitHub: Actions -> "DropNode Diagnóstico" -> Run workflow.
# Dice, con datos reales desde los servidores de GitHub:
#   1) ¿Supabase responde?
#   2) ¿Qué endpoints de la API de Mercado Libre responden (con token)?
#   3) Por cada tienda: ¿carga, la bloquean, cuántos productos salen
#      del HTML crudo y del HTML renderizado con JavaScript?
#   4) Guarda muestras del HTML en la carpeta muestras/ (el workflow las
#      sube como "artefacto" descargable para afinar los selectores).
# Con ADMIN_CHAT_ID configurado, además te manda el resumen por Telegram.
# =============================================================
import sys, os, logging, importlib, json
logging.basicConfig(level=logging.WARNING, format="%(message)s")

import estado as E
import ml_api
import scraper_multi as M

L = []
def out(s=""):
    print(s); L.append(s)

MUESTRAS = "muestras"

out("== 1) SUPABASE ==")
out(str(E.db_health()))
out(f"PROXY_URL configurado: {'SÍ' if os.environ.get('PROXY_URL','').strip() else 'NO'}")

out("\n== 2) API MERCADO LIBRE (con token) ==")
t = ml_api.token()
out(f"token de aplicación: {'OK' if t else 'NO (sin ML_APP_ID/ML_SECRET o falló)'}")
sondas = [
    ("search q",            "https://api.mercadolibre.com/sites/MLM/search", {"q": "audifonos", "limit": 3}),
    ("search categoría",    "https://api.mercadolibre.com/sites/MLM/search", {"category": "MLM1051", "limit": 3}),
    ("products/search",     "https://api.mercadolibre.com/products/search", {"status": "active", "site_id": "MLM", "q": "audifonos"}),
    ("highlights celulares","https://api.mercadolibre.com/highlights/MLM/category/MLM1051", None),
    ("trends",              "https://api.mercadolibre.com/trends/MLM", None),
    ("categorías",          "https://api.mercadolibre.com/sites/MLM/categories", None),
]
ids_item = []
for nombre, url, params in sondas:
    try:
        r = ml_api.get(url, params=params)
        cuerpo = r.text[:140].replace("\n", " ")
        out(f"  {nombre:<22} HTTP {r.status_code}  {'' if r.status_code == 200 else cuerpo}")
        if r.status_code == 200 and "highlights" in url:
            for x in (r.json().get("content") or [])[:3]:
                if x.get("type") == "ITEM":
                    ids_item.append(x.get("id"))
    except Exception as e:
        out(f"  {nombre:<22} ERROR {str(e)[:80]}")
if ids_item:
    try:
        r = ml_api.get("https://api.mercadolibre.com/items", params={"ids": ",".join(ids_item)})
        out(f"  items multiget         HTTP {r.status_code}  {'' if r.status_code == 200 else r.text[:140]}")
    except Exception as e:
        out(f"  items multiget         ERROR {str(e)[:80]}")

out("\n== 3) TIENDAS (motor multi, con render JS si el HTML crudo no trae productos) ==")
resumen = []
for clave in M.TIENDAS:
    d = {}
    try:
        items = M.scrapear_tienda(clave, diag=d, muestras_dir=MUESTRAS)
    except Exception as e:
        items, d = [], {"error": str(e)[:100], "paginas": [], "estrategias": {}}
    pag = d.get("paginas", [])
    ok = sum(1 for p in pag if not p["nota"])
    bloq = sum(1 for p in pag if "BLOQUEADA" in p["nota"])
    out(f"\n[{clave}] páginas ok={ok}/{len(pag)} bloqueadas={bloq} items={len(items)} candidatos={d.get('candidatos_crudos')} estrategias={d.get('estrategias')}")
    if "estrategias_render" in d:
        out(f"   render JS: páginas={d.get('renderizadas')} estrategias={d.get('estrategias_render')}")
    for p in pag[:4]:
        out(f"   {p['status']} {p['bytes']:>7}b {p['nota'] or 'ok':<14} {p['url'][:70]}")
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
