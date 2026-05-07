# =============================================================

# DROPNODE MX – github_scraper_ml.py  v4.0

# Usa Playwright (navegador headless) para ejecutar JavaScript

# ML carga productos via React – necesitamos un navegador real

# =============================================================

import os, time, random, logging, sys, json, re
import requests
from datetime import datetime, timedelta, timezone
from supabase import create_client
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

logging.basicConfig(level=logging.INFO,
format=”%(asctime)s [%(levelname)s] %(message)s”, stream=sys.stdout)
logger = logging.getLogger(**name**)

SUPABASE_URL    = os.environ[“SUPABASE_URL”]
SUPABASE_KEY    = os.environ[“SUPABASE_KEY”]
TELEGRAM_TOKEN  = os.environ[“TELEGRAM_TOKEN”]
CHANNEL_FREE_ID = int(os.environ[“CHANNEL_FREE_ID”])
CHANNEL_VIP_ID  = int(os.environ[“CHANNEL_VIP_ID”])
ML_AFFILIATE_ID = os.environ.get(“ML_AFFILIATE_ID”, “marcodurzo”)
LAUNCHPASS_LINK = os.environ.get(“LAUNCHPASS_LINK”, “”)
MAKE_WEBHOOK_URL= os.environ.get(“MAKE_WEBHOOK_URL”, “”)

TZ_MEXICO = timezone(timedelta(hours=-6))
db        = create_client(SUPABASE_URL, SUPABASE_KEY)
TELEGRAM  = f”https://api.telegram.org/bot{TELEGRAM_TOKEN}”

UMBRAL_VIP  = 0.25
UMBRAL_FREE = 0.12

PAGINAS = [
{“url”: “https://www.mercadolibre.com.mx/ofertas”,
“nombre”: “Ofertas ML”,      “emoji”: “🔥”},
{“url”: “https://listado.mercadolibre.com.mx/celulares-smartphones/#D[A:descuento]”,
“nombre”: “Celulares”,       “emoji”: “📱”},
{“url”: “https://listado.mercadolibre.com.mx/computacion/#D[A:descuento]”,
“nombre”: “Computacion”,     “emoji”: “💻”},
{“url”: “https://listado.mercadolibre.com.mx/electronica-audio-video/#D[A:descuento]”,
“nombre”: “Electronica”,     “emoji”: “🔌”},
{“url”: “https://listado.mercadolibre.com.mx/televisores/#D[A:descuento]”,
“nombre”: “Televisores”,     “emoji”: “📺”},
{“url”: “https://listado.mercadolibre.com.mx/videojuegos/#D[A:descuento]”,
“nombre”: “Videojuegos”,     “emoji”: “🎮”},
]

USER_AGENTS = [
“Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36”,
“Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36”,
“Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36”,
]

# ── Scraping con Playwright ───────────────────────────────────

def extraer_productos_de_pagina(page, pagina: dict) -> list:
“””
Navega a una pagina de ML con un navegador real y extrae productos.
El navegador ejecuta JavaScript, por lo que los productos cargan completo.
“””
productos = []
try:
logger.info(f”[PW] Cargando: {pagina[‘nombre’]}”)
page.goto(pagina[“url”], wait_until=“networkidle”, timeout=30000)
time.sleep(random.uniform(2, 4))  # Esperar carga adicional

```
    # Extraer datos del JSON embebido en window.__PRELOADED_STATE__
    preloaded = page.evaluate("""
        () => {
            if (window.__PRELOADED_STATE__) {
                return JSON.stringify(window.__PRELOADED_STATE__);
            }
            // Buscar en otros objetos globales de ML
            if (window.meli_ga) {
                return JSON.stringify(window.meli_ga);
            }
            return null;
        }
    """)

    if preloaded:
        try:
            data  = json.loads(preloaded)
            items = (data.get("initialState", {}).get("results", []) or
                     data.get("results", []) or
                     data.get("items", []))
            if items:
                logger.info(f"[PW] {pagina['nombre']}: {len(items)} items via __PRELOADED_STATE__")
                return items
        except Exception:
            pass

    # Si no hay __PRELOADED_STATE__, extraer del DOM directamente
    items_dom = page.evaluate("""
        () => {
            const resultados = [];
            // Selector de tarjetas de producto en ML
            const selectores = [
                'li.ui-search-layout__item',
                '.andes-card',
                '[class*="result-item"]',
                '[data-id]',
            ];

            for (const sel of selectores) {
                const cards = document.querySelectorAll(sel);
                if (cards.length > 3) {
                    cards.forEach(card => {
                        try {
                            const titulo = card.querySelector(
                                '[class*="title"], h2, .ui-search-item__title'
                            )?.textContent?.trim();

                            const precioEl = card.querySelector(
                                '[class*="price__fraction"], .andes-money-amount__fraction, [class*="price-tag-fraction"]'
                            );
                            const precio = precioEl ?
                                parseFloat(precioEl.textContent.replace(/[^0-9.]/g, '')) : 0;

                            const precioOrigEl = card.querySelector(
                                '[class*="original"], .ui-search-price__original-value, s'
                            );
                            const precioOrig = precioOrigEl ?
                                parseFloat(precioOrigEl.textContent.replace(/[^0-9.]/g, '')) : 0;

                            const link = card.querySelector('a')?.href || '';
                            const img  = card.querySelector('img')?.src || '';
                            const id   = card.getAttribute('data-id') || link.match(/MLM[0-9]+/)?.[0] || '';

                            if (titulo && precio > 0 && link) {
                                resultados.push({
                                    id:             id,
                                    title:          titulo,
                                    price:          precio,
                                    original_price: precioOrig > precio ? precioOrig : null,
                                    permalink:      link,
                                    thumbnail:      img,
                                    available_quantity: 10,
                                });
                            }
                        } catch(e) {}
                    });
                    break;
                }
            }
            return resultados;
        }
    """)

    if items_dom and len(items_dom) > 0:
        logger.info(f"[PW] {pagina['nombre']}: {len(items_dom)} items via DOM")
        return items_dom

    logger.warning(f"[PW] {pagina['nombre']}: sin productos extraidos")
    return []

except PWTimeout:
    logger.warning(f"[PW] Timeout en {pagina['nombre']}")
    return []
except Exception as e:
    logger.error(f"[PW] Error en {pagina['nombre']}: {e}")
    return []
```

# ── Base de datos ─────────────────────────────────────────────

def upsert_prod(url, nombre, categoria, sku):
try:
r = db.table(“productos”).upsert(
{“url”: url, “tienda”: “mercadolibre”, “nombre”: nombre,
“categoria”: categoria, “sku”: sku, “activo”: True},
on_conflict=“sku,tienda”).execute()
if r.data: return r.data[0][“id”]
r2 = db.table(“productos”).select(“id”).eq(“sku”, sku)  
.eq(“tienda”, “mercadolibre”).execute()
return r2.data[0][“id”] if r2.data else None
except Exception as e:
logger.error(f”[DB] {e}”); return None

def guardar_precio_db(pid, precio, precio_orig, stock):
if not pid: return
try:
db.table(“historial_precios”).insert({
“producto_id”: pid, “precio”: precio,
“precio_original”: precio_orig, “stock”: stock,
“disponible”: stock > 0,
“timestamp”: datetime.utcnow().isoformat()
}).execute()
except Exception: pass

def alerta_hoy(pid):
if not pid: return False
try:
desde = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
r = db.table(“alertas_enviadas”).select(“id”)  
.eq(“producto_id”, pid).gte(“timestamp”, desde).execute()
return len(r.data) > 0
except Exception: return False

def guardar_alerta_db(pid, score, canal, precio, descuento):
if not pid: return
try:
db.table(“alertas_enviadas”).insert({
“producto_id”: pid, “heat_score”: score, “canal”: canal,
“precio_alerta”: precio, “descuento_real”: descuento,
“clicks”: 0, “timestamp”: datetime.utcnow().isoformat()
}).execute()
except Exception: pass

def get_minimo(pid):
try:
desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
r = db.table(“historial_precios”).select(“precio”)  
.eq(“producto_id”, pid).gte(“timestamp”, desde)  
.eq(“disponible”, True).order(“precio”).limit(1).execute()
return float(r.data[0][“precio”]) if r.data else None
except Exception: return None

def get_stats(pid, precio_actual):
try:
desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
r = db.table(“historial_precios”).select(“precio, timestamp”)  
.eq(“producto_id”, pid).gte(“timestamp”, desde)  
.eq(“disponible”, True).order(“timestamp”).execute()
regs = r.data or []
if len(regs) < 5: return {}
precios = [float(x[“precio”]) for x in regs]
primer  = datetime.fromisoformat(regs[0][“timestamp”].replace(“Z”,””))
dias    = (datetime.utcnow() - primer).days + 1
return {“min”: min(precios), “max”: max(precios),
“avg”: sum(precios)/len(precios), “dias”: dias,
“es_minimo”: precio_actual <= min(precios)*1.02 and dias >= 7}
except Exception: return {}

# ── Telegram ──────────────────────────────────────────────────

def enviar(chat_id, texto):
try:
r = requests.post(f”{TELEGRAM}/sendMessage”, json={
“chat_id”: chat_id, “text”: texto,
“parse_mode”: “Markdown”,
“disable_web_page_preview”: True,
}, timeout=15)
d = r.json()
if d.get(“ok”): return d[“result”][“message_id”]
logger.warning(f”[TG] {d.get(‘description’)}”)
except Exception as e: logger.error(f”[TG] {e}”)
return None

def link_ml(url, item_id):
encoded = requests.utils.quote(url, safe=””)
return (f”https://go.mercadolibre.com.mx?as_src=affiliate”
f”&as_campaign=dropnodemx&as_content={item_id}”
f”&url={encoded}&affiliate_id={ML_AFFILIATE_ID}”)

def score_item(descuento, stock, precio):
s = 0.0
if descuento >= 0.60: s += 3
elif descuento >= 0.40: s += 2.5
elif descuento >= 0.25: s += 1.8
elif descuento >= 0.12: s += 1
if stock == 1: s += 2
elif stock <= 3: s += 1.8
elif stock <= 10: s += 1
if precio >= 5000: s += 1.5
elif precio >= 2000: s += 1
return min(10, round(s))

def msg_vip(item):
n=item[“nombre”][:65]; p=item[“precio”]; po=item[“precio_orig”]
d=item[“descuento”]*100; s=item[“stock”]
lnk=link_ml(item[“url”],item[“id”]); sc=item[“score”]
st=item.get(“stats”,{}); em=item[“categoria”][“emoji”]
cat=item[“categoria”][“nombre”]
hr=datetime.now(TZ_MEXICO).strftime(”%H:%M:%S”)
rl=po*0.80; rh=po*0.92
ic=“🚨” if sc>=8 else(“🔥” if sc>=6 else “⚡”)
tg=“ERROR DE PRECIO” if sc>=8 else(“OFERTA AGRESIVA” if sc>=6 else “DESCUENTO REAL”)
if s==1: st2=”*ULTIMA UNIDAD*”
elif s<=3: st2=f”*Solo {s} unidades*”
elif s<=10: st2=f”{s} unidades”
else: st2=“Stock disponible”
m=f”{ic} *{tg}*  {em} {cat}\n\n*{n}*\n\n”
m+=f”Precio ahora:    *${p:,.0f} MXN*\n”
m+=f”Precio original:  ${po:,.0f} MXN\n”
m+=f”Descuento real:  *-{d:.0f}%*\n”
if st.get(“es_minimo”) and st.get(“dias”,0)>=7:
m+=f”\n*Precio mas bajo en {st[‘dias’]} dias*\n”
if st.get(“avg”) and p<st[“avg”]*0.90:
m+=f”${st[‘avg’]-p:,.0f} menos que el promedio\n”
m+=f”\n{st2}\n”
if d>=30 or s<=3: m+=”*Oferta podria terminar pronto*\n”
m+=f”\nScore: {sc}/10\n\n[COMPRAR AHORA]({lnk})\n\n”
m+=f”*Reventa estimada: ${rl:,.0f} - ${rh:,.0f} MXN*\n_{hr} hora MX_”
return m

def msg_free(item):
n=item[“nombre”][:60]; p=item[“precio”]; po=item[“precio_orig”]
d=item[“descuento”]*100; s=item[“stock”]
lnk=link_ml(item[“url”],item[“id”])
st=item.get(“stats”,{}); em=item[“categoria”][“emoji”]
sc=item[“score”]
ic=“🚨” if sc>=8 else(“🔥” if sc>=6 else “⚡”)
m=f”{ic} *DESCUENTO REAL*  {em}\n\n*{n}*\n\n”
m+=f”*${p:,.0f} MXN* (-{d:.0f}%)\nRef: ${po:,.0f} MXN\n”
if st.get(“es_minimo”) and st.get(“dias”,0)>=7:
m+=f”\n*Precio mas bajo en {st[‘dias’]} dias*\n”
if s<=5: m+=f”*Solo {s} unidades*\n”
m+=f”\n[Ver oferta]({lnk})\n\n”
m+=f”*Canal VIP: alertas primero + analisis de reventa.*\n”
if LAUNCHPASS_LINK: m+=f”*{LAUNCHPASS_LINK}*”
return m

def notificar_make(item):
if not MAKE_WEBHOOK_URL: return
try:
requests.post(MAKE_WEBHOOK_URL, json={
“nombre”: item[“nombre”][:80],
“precio”: str(round(item[“precio”])),
“descuento”: str(round(item[“descuento”]*100)),
“thumbnail”: item.get(“thumbnail”,””),
“link”: item[“url”], “score”: item[“score”],
}, timeout=10)
except Exception: pass

def procesar_prod(prod_raw, cat):
try:
item_id  = str(prod_raw.get(“id”,””))
nombre   = str(prod_raw.get(“title”,””))[:80]
precio   = float(prod_raw.get(“price”,0))
precio_o = prod_raw.get(“original_price”)
precio_o = float(precio_o) if precio_o else 0
permalink= str(prod_raw.get(“permalink”,””))
stock    = int(prod_raw.get(“available_quantity”,10))
thumb    = str(prod_raw.get(“thumbnail”,””))

```
    if not nombre or precio<=0 or not permalink: return None

    pid = upsert_prod(permalink, nombre, cat["nombre"], item_id)
    guardar_precio_db(pid, precio, precio_o or precio, stock)
    if alerta_hoy(pid): return None

    descuento = 0.0
    if precio_o and precio_o > precio:
        descuento = (precio_o - precio) / precio_o
    else:
        minimo = get_minimo(pid)
        if minimo and precio < minimo*0.88:
            descuento = (minimo-precio)/minimo
            precio_o  = minimo

    sc    = score_item(descuento, stock, precio)
    stats = get_stats(pid, precio)
    return {"id":item_id,"pid":pid,"nombre":nombre,
            "precio":precio,"precio_orig":precio_o or precio,
            "descuento":descuento,"stock":stock,"url":permalink,
            "thumbnail":thumb,"categoria":cat,"score":sc,"stats":stats}
except Exception: return None
```

# ── Main ──────────────────────────────────────────────────────

def main():
hora_mx = datetime.now(TZ_MEXICO)
logger.info(f”[GITHUB v4 Playwright] {hora_mx.strftime(’%d/%m %H:%M’)} MX”)

```
if not (8 <= hora_mx.hour < 22):
    logger.info("[GITHUB] Fuera de horario"); return

alertas=[]; destacados=[]

with sync_playwright() as pw:
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox", "--disable-setuid-sandbox",
            "--disable-dev-shm-usage", "--disable-gpu",
            "--no-first-run", "--no-zygote",
        ]
    )
    context = browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        locale="es-MX",
        timezone_id="America/Mexico_City",
        viewport={"width": 1366, "height": 768},
    )
    page = context.new_page()

    # Bloquear recursos innecesarios para ir mas rapido
    page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())
    page.route("**/analytics/**", lambda r: r.abort())
    page.route("**/tracking/**", lambda r: r.abort())

    for pagina in PAGINAS:
        prods_raw = extraer_productos_de_pagina(page, pagina)
        cat = {"nombre": pagina["nombre"], "emoji": pagina["emoji"]}
        mejor_pag=None; mejor_sc=-1

        for prod_raw in prods_raw[:25]:
            item = procesar_prod(prod_raw, cat)
            if not item: continue
            if item["score"] > mejor_sc:
                mejor_sc=item["score"]; mejor_pag=item
            if item["descuento"] >= UMBRAL_FREE:
                alertas.append(item)

        if mejor_pag: destacados.append(mejor_pag)
        time.sleep(random.uniform(2, 5))

    browser.close()

alertas.sort(key=lambda x: x["score"], reverse=True)
vip_n=0; free_n=0

for item in alertas[:10]:
    if item["descuento"]>=UMBRAL_VIP and item["score"]>=6:
        mid=enviar(CHANNEL_VIP_ID, msg_vip(item))
        if mid:
            guardar_alerta_db(item["pid"],item["score"],"vip",
                              item["precio"],item["descuento"])
            vip_n+=1
            if item["score"]>=8: notificar_make(item)
            time.sleep(4)
    if item["descuento"]>=UMBRAL_FREE and item["score"]>=3:
        mid=enviar(CHANNEL_FREE_ID, msg_free(item))
        if mid:
            if item["descuento"]<UMBRAL_VIP:
                guardar_alerta_db(item["pid"],item["score"],"free",
                                  item["precio"],item["descuento"])
            free_n+=1; time.sleep(5)

if free_n==0 and hora_mx.hour in (12,19) and destacados:
    top=sorted(destacados,key=lambda x:x["score"],reverse=True)[:5]
    hl="tarde" if hora_mx.hour>=15 else "manana"
    msg=f"📋 *Mejores precios de la {hl} -- DropNode MX*\n\n"
    msg+="_Nuestro equipo reviso miles de productos. Estos destacan:_\n\n"
    for i,it in enumerate(top,1):
        lnk=link_ml(it["url"],it["id"]); d=it["descuento"]*100
        ln=f"{i}. {it['categoria']['emoji']} *[{it['nombre'][:50]}]({lnk})*\n"
        ln+=f"   *${it['precio']:,.0f} MXN*"
        if d>=10: ln+=f" (-{d:.0f}%)"
        msg+=ln+"\n\n"
    if LAUNCHPASS_LINK:
        msg+=f"🔒 _Errores de precio van al VIP primero._\n_{LAUNCHPASS_LINK}_"
    enviar(CHANNEL_FREE_ID, msg); free_n+=1

logger.info(f"[GITHUB] Fin -- VIP:{vip_n} Free:{free_n} | "
            f"Alertas:{len(alertas)} Destacados:{len(destacados)}")
```

if **name**==”**main**”:
main()