# =============================================================
# DROPNODE MX — github_scraper_ml.py v12
# v12: horarios centralizados (horarios.py), modo nocturno VIP (score>=8),
#      NADA de sleep de 3600 s: lo que pasa al free entra a la cola de 60 min
#      (cola_free) y lo publica main.py. Sin snippets de 'ya se agotó'.
# =============================================================
import os, time, random, logging, sys, requests
import datetime as _dt
from datetime import datetime, timedelta, timezone
from supabase import create_client
from playwright.sync_api import sync_playwright
import horarios as H
import estado as E
import ml_api

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

SUPABASE_URL     = os.environ["SUPABASE_URL"].strip()
SUPABASE_KEY     = os.environ["SUPABASE_KEY"].strip()
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"].strip()
CHANNEL_FREE_ID  = int(os.environ["CHANNEL_FREE_ID"].strip())
CHANNEL_VIP_ID   = int(os.environ["CHANNEL_VIP_ID"].strip())
ML_AFFILIATE_ID  = os.environ.get("ML_AFFILIATE_ID","marcodurzo").strip()
LAUNCHPASS_LINK  = os.environ.get("LAUNCHPASS_LINK","").strip()
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL","").strip()

TZ_MEXICO    = timezone(timedelta(hours=-6))
TELEGRAM_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN
ML_API       = "https://api.mercadolibre.com"

db = None
try:
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("[DB] OK")
except Exception as e:
    logger.warning("[DB] " + str(e))

# ─────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────
def upsert_prod(url, nombre, categoria, sku):
    if not db: return None
    try:
        r = db.table("productos").upsert(
            {"url":url,"tienda":"mercadolibre","nombre":nombre,
             "categoria":categoria,"sku":sku,"activo":True},
            on_conflict="sku,tienda").execute()
        if r.data: return r.data[0]["id"]
        r2 = db.table("productos").select("id").eq("sku",sku).eq("tienda","mercadolibre").execute()
        return r2.data[0]["id"] if r2.data else None
    except Exception as e:
        logger.error("[DB upsert] "+str(e)[:80]); return None

def guardar_precio(pid, precio, precio_orig, stock):
    if not pid or not db: return
    try:
        db.table("historial_precios").insert({
            "producto_id":pid,"precio":precio,"precio_original":precio_orig,
            "stock":stock if stock else 0,"disponible":True,
            "timestamp":datetime.utcnow().isoformat()}).execute()
    except: pass

def alerta_hoy(pid):
    if not pid or not db: return False
    try:
        desde = datetime.utcnow().replace(hour=0,minute=0,second=0).isoformat()
        r = db.table("alertas_enviadas").select("id").eq(
            "producto_id",pid).gte("timestamp",desde).execute()
        return len(r.data) > 0
    except: return False

def guardar_alerta(pid, score, canal, precio, descuento):
    if not pid or not db: return
    try:
        db.table("alertas_enviadas").insert({
            "producto_id":pid,"heat_score":score,"canal":canal,
            "precio_alerta":precio,"descuento_real":descuento,
            "clicks":0,"timestamp":datetime.utcnow().isoformat()}).execute()
    except: pass

def get_stats(pid, precio_actual):
    if not pid or not db: return {}
    try:
        desde = (datetime.utcnow()-timedelta(days=90)).isoformat()
        r = db.table("historial_precios").select("precio,timestamp").eq(
            "producto_id",pid).gte("timestamp",desde).order("timestamp").execute()
        regs = r.data or []
        if len(regs) < 5: return {}
        precios = [float(x["precio"]) for x in regs]
        primer  = datetime.fromisoformat(regs[0]["timestamp"].replace("Z",""))
        dias    = (datetime.utcnow()-primer).days+1
        min_p   = min(precios)
        return {"min":min_p,"max":max(precios),"avg":sum(precios)/len(precios),
                "dias":dias,"es_minimo":precio_actual<=min_p*1.02 and dias>=7}
    except: return {}

# ─────────────────────────────────────────────
# CONFIGURACION
# ─────────────────────────────────────────────
DESCUENTO_HOT      = 0.35
MAX_VIP            = 12
MAX_FREE           = 4

# Páginas ML — Flash primero, luego base, luego categorías rotativas
PAGINAS_FLASH = [
    {"url":"https://www.mercadolibre.com.mx/ofertas/solo-hoy",
     "nombre":"Solo Hoy","emoji":"⏰","es_flash":True},
    {"url":"https://www.mercadolibre.com.mx/ofertas/solo-hoy?page=2",
     "nombre":"Solo Hoy p2","emoji":"⏰","es_flash":True},
    {"url":"https://www.mercadolibre.com.mx/remates",
     "nombre":"Remates","emoji":"💥","es_flash":True},
    {"url":"https://www.mercadolibre.com.mx/ofertas?deal_type=DAILY_DEAL",
     "nombre":"Oferta del Dia","emoji":"📅","es_flash":True},
    # URL alternativa por si cambia la principal
    {"url":"https://www.mercadolibre.com.mx/ofertas#DAILY_DEAL",
     "nombre":"Oferta Dia Alt","emoji":"📅","es_flash":True},
]

PAGINAS_BASE = [
    {"url":f"https://www.mercadolibre.com.mx/ofertas?page={i}",
     "nombre":f"Ofertas p{i}","emoji":"🔥","es_flash":False}
    for i in range(1, 7)
]

PAGINAS_CAT = [
    {"url":"https://www.mercadolibre.com.mx/ofertas/electronica",  "nombre":"Electronica", "emoji":"🔌","es_flash":False},
    {"url":"https://www.mercadolibre.com.mx/ofertas/celulares",    "nombre":"Celulares",   "emoji":"📱","es_flash":False},
    {"url":"https://www.mercadolibre.com.mx/ofertas/computacion",  "nombre":"Computacion", "emoji":"💻","es_flash":False},
    {"url":"https://www.mercadolibre.com.mx/ofertas/juguetes",     "nombre":"Juguetes",    "emoji":"🧸","es_flash":False},
    {"url":"https://www.mercadolibre.com.mx/ofertas/bebes",        "nombre":"Bebes",       "emoji":"👶","es_flash":False},
    {"url":"https://www.mercadolibre.com.mx/ofertas/mascotas",     "nombre":"Mascotas",    "emoji":"🐾","es_flash":False},
    {"url":"https://www.mercadolibre.com.mx/ofertas/deportes",     "nombre":"Deportes",    "emoji":"⚽","es_flash":False},
    {"url":"https://www.mercadolibre.com.mx/ofertas/hogar",        "nombre":"Hogar",       "emoji":"🏠","es_flash":False},
]

_hora_run = _dt.datetime.utcnow().hour
_idx      = (_hora_run // 2) % len(PAGINAS_CAT)
PAGINAS   = PAGINAS_FLASH + PAGINAS_BASE + PAGINAS_CAT[_idx:_idx+2]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]

JS_EXTRACT = r"""
() => {
    var productos = [];
    var cards = document.querySelectorAll('.poly-card,.andes-card,[class*="ui-search-result"],[class*="promotions-item"]');
    if (cards.length === 0) cards = document.querySelectorAll('li[class*="item"],div[class*="item-"]');

    function parsePrecio(card) {
        var selectors = [
            '[class*="price__fraction"],[class*="amount__fraction"],[class*="price-tag-fraction"]',
            '[class*="andes-money-amount__fraction"]',
            '[class*="price-tag__fraction"]'
        ];
        for (var s = 0; s < selectors.length; s++) {
            var frac = card.querySelector(selectors[s]);
            if (frac) {
                var f = frac.textContent.replace(/[^0-9]/g,"");
                var cEl = card.querySelector('[class*="price__cents"],[class*="amount__cents"],[class*="price-tag-cents"]');
                var c = cEl ? cEl.textContent.replace(/[^0-9]/g,"").substring(0,2) : "00";
                if (f) return parseFloat(f + "." + c);
            }
        }
        var els = card.querySelectorAll('[class*="price"],[class*="amount"]');
        for (var i = 0; i < els.length; i++) {
            var txt = "";
            els[i].childNodes.forEach(function(n){if(n.nodeType===3)txt+=n.textContent;});
            txt = txt.replace(/[^0-9.,]/g,"").trim();
            if (txt.length >= 2 && txt.length <= 10) {
                txt = txt.replace(/,([0-9]{3})/g,"$1").replace(",",".");
                var p = parseFloat(txt);
                if (p > 10 && p < 500000) return p;
            }
        }
        return 0;
    }

    function parseOrig(card) {
        var origEl = card.querySelector('s,del,[class*="original"],[class*="regular-price"],[class*="strike"],[class*="was-price"]');
        if (!origEl) return 0;
        var of = origEl.querySelector('[class*="fraction"]');
        if (of) return parseFloat(of.textContent.replace(/[^0-9]/g,"") || "0");
        var ot = origEl.textContent.replace(/[^0-9.,]/g,"").replace(/,([0-9]{3})/g,"$1");
        if (ot.length >= 2 && ot.length <= 8) return parseFloat(ot);
        return 0;
    }

    function getDescPct(card) {
        var m = card.innerHTML.match(/(\d{2,3})\s*%\s*(?:OFF|off|desc)/);
        if (m) return parseInt(m[1]);
        var b = card.querySelector('[class*="discount"],[class*="rebates"],[class*="off"]');
        if (b) { var bt = b.textContent.match(/(\d{2,3})/); if (bt) return parseInt(bt[1]); }
        return 0;
    }

    function parseStock(card) {
        var h = card.innerHTML.toLowerCase();
        if (h.indexOf("ltima unidad") >= 0) return 1;
        if (h.indexOf("pocas unidades") >= 0 || h.indexOf("ltimas unidades") >= 0) return 3;
        var m = h.match(/(\d+)\s*(unidad|pieza)/);
        if (m) { var n = parseInt(m[1]); if (n > 0 && n < 20) return n; }
        return null;
    }

    function detectFlash(card) {
        var h = card.innerHTML.toLowerCase();
        return h.indexOf("solo hoy") >= 0 || h.indexOf("remate") >= 0
            || h.indexOf("flash") >= 0 || h.indexOf("oferta del d") >= 0;
    }

    function detectEnvio(card) {
        var h = card.innerHTML.toLowerCase();
        return h.indexOf("env") >= 0 && (h.indexOf("gratis") >= 0
            || h.indexOf("full") >= 0 || h.indexOf("mismo d") >= 0);
    }

    for (var i = 0; i < cards.length; i++) {
        try {
            var card = cards[i];
            var tEl = card.querySelector('[class*="title"],[class*="product-name"],h2,h3');
            var titulo = tEl ? tEl.textContent.trim() : "";
            var precio = parsePrecio(card);
            var orig   = parseOrig(card);

            // Si no hay precio original, calcular desde badge de %
            if (orig === 0 || orig <= precio) {
                var dp = getDescPct(card);
                if (dp >= 15 && dp < 90) orig = Math.round(precio / (1 - dp/100));
            }

            var lEl = card.querySelector("a[href]");
            var link = lEl ? lEl.href : "";
            var iEl  = card.querySelector("img");
            var img  = iEl ? (iEl.src || iEl.getAttribute("data-src") || iEl.getAttribute("data-lazy") || "") : "";
            var idm  = link.match(/MLM[0-9]+/);
            var id   = idm ? idm[0] : ("item_" + i);
            var html = card.innerHTML.toLowerCase();
            var cupon = html.indexOf("cup") >= 0 && html.indexOf("descuento") >= 0;
            var cmonto = 0;
            if (cupon) { var cm = html.match(/cup[^0-9]*([0-9]{2,5})/); if (cm) cmonto = parseFloat(cm[1]); }

            if (titulo && titulo.length > 5 && precio > 10 && precio < 200000
                    && link.indexOf("mercadolibre") >= 0) {
                productos.push({
                    id:id, title:titulo.substring(0,100), price:precio,
                    original_price:(orig>precio && orig<precio*8)?orig:0,
                    permalink:link, thumbnail:img,
                    available_quantity:parseStock(card),
                    tiene_cupon:cupon, cupon_monto:cmonto,
                    precio_con_cupon:cmonto>0?precio-cmonto:precio,
                    es_flash:detectFlash(card), envio_gratis:detectEnvio(card),
                });
            }
        } catch(e) {}
    }
    return productos;
}
"""

def scrape_pagina(page, pagina):
    try:
        logger.info("[PW] " + pagina["nombre"])
        page.goto(pagina["url"], wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(3,6))
        items = page.evaluate(JS_EXTRACT)
        if pagina.get("es_flash"):
            for it in (items or []): it["es_flash"] = True
        count = len(items or [])
        logger.info(f"[PW] {pagina['nombre']}: {count}")
        return items or []
    except Exception as e:
        logger.error("[PW] " + str(e)); return []

# ── Fallback: ML API cuando Playwright devuelve 0 ──
def ml_api_fallback(limit=50):
    """
    Cuando las páginas de Playwright devuelven 0 items,
    usar la API pública de ML como respaldo.
    Retorna items en el mismo formato que JS_EXTRACT.
    """
    logger.info("[ML API] Activando fallback...")
    resultados = []
    endpoints = [
        f"{ML_API}/sites/MLM/search?sort=best_discount&condition=new&limit={limit}",
        f"{ML_API}/sites/MLM/search?sort=best_discount&has_pictures=Y&limit={limit}&shipping_cost=free",
    ]
    for url in endpoints[:1]:
        try:
            r = ml_api.get(url, timeout=15)
            if r.status_code != 200: continue
            for item in r.json().get("results",[]):
                p = float(item.get("price",0))
                po = float(item.get("original_price") or 0)
                if p <= 0 or po <= p: continue
                resultados.append({
                    "id":    str(item.get("id","")),
                    "title": item.get("title","")[:100],
                    "price": p,
                    "original_price": po,
                    "permalink":  item.get("permalink",""),
                    "thumbnail":  item.get("thumbnail","").replace("I.jpg","O.jpg"),
                    "available_quantity": None,
                    "tiene_cupon": False, "cupon_monto": 0,
                    "precio_con_cupon": p,
                    "es_flash": False,
                    "envio_gratis": item.get("shipping",{}).get("free_shipping",False),
                })
        except Exception as e:
            logger.error(f"[ML API fallback] {e}")
    logger.info(f"[ML API] {len(resultados)} productos via API")
    return resultados

# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────
def _md(t):
    return str(t).replace("_", " ").replace("*", "").replace("[", "(").replace("]", ")").replace("`", "")


def enviar(chat_id, texto, modo="Markdown"):
    try:
        r = requests.post(TELEGRAM_API+"/sendMessage", json={
            "chat_id":chat_id,"text":texto,"parse_mode":modo,
            "disable_web_page_preview":True}, timeout=15)
        d = r.json()
        if d.get("ok"): return d["result"]["message_id"]
        logger.warning("[TG] "+str(d.get("description","")))
        if "parse" in str(d.get("description","")).lower():
            r = requests.post(TELEGRAM_API+"/sendMessage", json={"chat_id":chat_id,"text":texto,
                "disable_web_page_preview":True}, timeout=15)
            d = r.json()
            if d.get("ok"): return d["result"]["message_id"]
    except Exception as e: logger.error("[TG] "+str(e))
    return None

def enviar_foto(chat_id, foto_url, caption, modo="Markdown"):
    try:
        r = requests.post(TELEGRAM_API+"/sendPhoto", json={
            "chat_id":chat_id,"photo":foto_url,
            "caption":caption[:1024],"parse_mode":modo}, timeout=20)
        d = r.json()
        if d.get("ok"): return d["result"]["message_id"]
        return enviar(chat_id, caption, modo)
    except Exception as e:
        logger.error("[TG foto] "+str(e)); return enviar(chat_id, caption, modo)

def link_ml(url, item_id):
    return url.split("?")[0].split("#")[0] + "?matt_tool=" + ML_AFFILIATE_ID

# ─────────────────────────────────────────────
# SCORE
# ─────────────────────────────────────────────
def score(descuento, stock, precio, cupon, envio_gratis=False, es_flash=False):
    s = 0.0
    if descuento >= 0.60:   s += 4.0
    elif descuento >= 0.40: s += 3.5
    elif descuento >= 0.25: s += 3.0
    elif descuento >= 0.15: s += 2.0
    else:                   s += 0.5
    stk = stock if stock is not None else 10
    if stk == 1:    s += 2.0
    elif stk <= 3:  s += 1.8
    elif stk <= 10: s += 1.0
    if precio >= 8000:   s += 1.5
    elif precio >= 3000: s += 1.0
    if cupon:        s += 1.0
    if envio_gratis: s += 0.5
    if es_flash:     s += 1.0
    return min(10, round(s))

# ─────────────────────────────────────────────
# HASHTAGS — sin falsos positivos
# ─────────────────────────────────────────────
def generar_hashtags(nombre, descuento, sc, cupon=False, es_flash=False, categoria=""):
    n = nombre.lower(); tags = []
    if any(w in n for w in ["minoxidil","shampoo","crema","vitamina","suplemento",
                              "maquillaje","perfume","serum","colageno","proteina"]):
        tags.append("#saludybelleza")
    elif any(w in n for w in ["camisa","pantalon","zapato","tenis","vestido","licra",
                               "leggin","blusa","ropa","calcetines","playera",
                               "chamarra","short","sudadera","calzado","bota"]):
        tags.append("#moda")
    elif any(w in n for w in ["llave","taladro","herramienta","martillo","tornillo",
                               "destornillador","sierra","impacto","torque"]):
        tags.append("#herramientas")
    elif any(w in n for w in ["silla","mesa","sofa","lampara","colchon","cortina",
                               "toalla","sabana","almohada","mueble","cajonera"]):
        tags.append("#hogar")
    elif any(w in n for w in ["juguete","muneca","lego","muñeca","figura","plush"]):
        tags.append("#juguetes")
    elif any(w in n for w in ["iphone","galaxy","celular","smartphone","redmi","poco","moto g"]):
        tags.append("#celulares")
    elif any(w in n for w in ["laptop","notebook","macbook","thinkpad","ideapad","chromebook"]):
        tags.append("#laptops")
    elif any(w in n for w in ["televisor"," tv ","smart tv","oled","qled"]):
        tags.append("#televisores")
    elif any(w in n for w in ["audifonos","airpods","bocina","speaker","wh-","wf-","earbuds"]):
        tags.append("#audio")
    elif any(w in n for w in ["playstation","xbox","nintendo","switch","ps5","ps4"]):
        tags.append("#gaming")
    elif any(w in n for w in ["tablet","ipad"]):
        tags.append("#tablets")
    elif any(w in n for w in ["smartwatch","reloj inteligente","band "]):
        tags.append("#wearables")
    elif any(w in n for w in ["impresora","router","monitor","teclado","mouse","disco","ssd","memoria"]):
        tags.append("#computacion")
    elif any(w in n for w in ["lavadora","refrigerador","estufa","microondas","licuadora","aspiradora"]):
        tags.append("#electrodomesticos")
    elif categoria and len(categoria) > 2:
        tags.append("#"+categoria.lower().replace(" ",""))

    marcas = {
        "apple":["iphone","ipad","macbook","airpods"],"samsung":["samsung"],
        "sony":["sony"],"lenovo":["lenovo","thinkpad"],"dell":["dell","inspiron"],
        "hp":[" hp "],"asus":["asus"],"xiaomi":["xiaomi","redmi","poco"],
        "motorola":["motorola","moto "],"lg":[" lg "],"bosch":["bosch"],
        "dewalt":["dewalt"],"milwaukee":["milwaukee"],
    }
    for marca, kws in marcas.items():
        if any(kw in n for kw in kws): tags.append(f"#{marca}"); break

    if sc >= 8 or descuento >= 0.50: tags.append("#errorprecio")
    elif descuento >= 0.35:           tags.append("#hotdeal")
    if es_flash:                      tags.append("#solohoy")
    if cupon:                         tags.append("#cupon")
    if descuento >= 0.50:             tags.append("#reventa")
    return " ".join(tags)

# ─────────────────────────────────────────────
# FORMATOS
# ─────────────────────────────────────────────
def _stk(stk, bold=True):
    if stk is None or stk >= 10: return ""
    if stk == 1:   return "*ÚLTIMA UNIDAD*" if bold else "ÚLTIMA UNIDAD"
    if stk <= 3:   return f"*Solo {stk} unidades*" if bold else f"Solo {stk} unidades"
    return f"{stk} unidades"

def _vida(descuento, stock, es_flash):
    stk = stock if stock is not None else 99
    if descuento >= 0.50 or stk == 1:     return "⏱ Vida estimada: minutos"
    elif descuento >= 0.40 or stk <= 3 or es_flash: return "⏱ Vida estimada: 1-2 horas"
    elif descuento >= 0.30:                return "⏱ Vida estimada: 2-6 horas"
    return ""

def msg_vip(item, stats):
    nombre=_md(item["nombre"][:65]); precio=item["precio"]; p_orig=item["precio_orig"]
    desc=item["descuento"]*100; stk=item["stock"]; lnk=link_ml(item["url"],item["id"])
    sc=item["score"]; cupon=item.get("tiene_cupon",False)
    c_monto=item.get("cupon_monto",0); p_cupon=item.get("precio_con_cupon",precio)
    es_flash=item.get("es_flash",False); ev=item.get("envio_gratis",False)
    rl=p_orig*0.78; rh=p_orig*0.90; vida=_vida(item["descuento"],stk,es_flash)
    hora_det=datetime.now(TZ_MEXICO).strftime("%H:%M")
    es_rev=item["descuento"]>=0.50

    if es_rev:      icono="💰"; tag="[REVENTA] EXCLUSIVO VIP"
    elif es_flash:  icono="⏰"; tag="SOLO HOY — VIP PRIMERO"
    elif sc>=8 or item["descuento"]>=0.50: icono="🚨"; tag="ERROR DE PRECIO — SOLO VIP"
    elif item["descuento"]>=DESCUENTO_HOT: icono="🔥"; tag="HOT DEAL — EXCLUSIVO VIP"
    elif cupon:     icono="🎟️"; tag="OFERTA + CUPÓN — VIP"
    else:           icono="⚡"; tag="ALERTA VIP"

    stxt=_stk(stk)
    m  = f"{icono} *{tag}*\n\n*{nombre}*\n\n"
    m += f"Precio ahora: *${precio:,.0f} MXN*\n"
    if p_orig>precio: m += f"Precio original: ${p_orig:,.0f} MXN\n"
    m += f"Descuento: *-{desc:.0f}%*\n"
    if ev: m += "✅ *Envío gratis*\n"
    if cupon and c_monto>0: m += f"\n🎟️ *Con cupón: ${p_cupon:,.0f} MXN* (−${c_monto:,.0f})\n"
    if stats.get("es_minimo") and stats.get("dias",0)>=7:
        m += f"\n*Precio más bajo en {stats['dias']} días*\n"
    if stats.get("avg") and precio < stats["avg"]*0.90:
        m += f"${stats['avg']-precio:,.0f} menos que el promedio\n"
    if stxt: m += f"\n{stxt}\n"
    if vida: m += f"{vida}\n"
    m += f"\n━━━━━━━━━━━\n📋 Score: {sc}/10 · {hora_det} MX\n━━━━━━━━━━━\n\n"
    m += f"[COMPRAR AHORA]({lnk})\n\n"
    if es_rev and p_orig>precio:
        m += f"💰 *Reventa estimada: ${rl:,.0f}–${rh:,.0f} MXN*\n_Ganancia: +${rl-precio:,.0f}_\n"
    elif p_orig>precio:
        m += f"_Reventa: ${rl:,.0f}–${rh:,.0f} MXN_\n"
    ht = generar_hashtags(nombre, item["descuento"], sc, cupon, es_flash)
    if ht: m += f"\n{ht}"
    return m

def msg_vip_caption(item, stats):
    nombre=_md(item["nombre"][:50]); precio=item["precio"]; p_orig=item["precio_orig"]
    desc=item["descuento"]*100; stk=item["stock"]; lnk=link_ml(item["url"],item["id"])
    sc=item["score"]; cupon=item.get("tiene_cupon",False)
    c_monto=item.get("cupon_monto",0); p_cupon=item.get("precio_con_cupon",precio)
    es_flash=item.get("es_flash",False); ev=item.get("envio_gratis",False)
    rl=p_orig*0.78; rh=p_orig*0.90; vida=_vida(item["descuento"],stk,es_flash)
    es_rev=item["descuento"]>=0.50

    if es_rev:     icono="💰"; tag="[REVENTA]"
    elif es_flash: icono="⏰"; tag="SOLO HOY"
    elif sc>=8 or item["descuento"]>=0.50: icono="🚨"; tag="ERROR PRECIO"
    elif item["descuento"]>=DESCUENTO_HOT: icono="🔥"; tag="HOT DEAL"
    else:          icono="⚡"; tag="VIP"

    stxt=_stk(stk)
    m  = f"{icono} *{tag}*\n\n*{nombre}*\n\n"
    m += f"*${precio:,.0f} MXN* (−{desc:.0f}%)\n"
    if p_orig>precio: m += f"Normal: ${p_orig:,.0f}\n"
    if ev: m += "✅ Envío gratis\n"
    if cupon and c_monto>0: m += f"🎟️ Con cupón: *${p_cupon:,.0f}*\n"
    if stxt: m += f"\n{stxt}\n"
    if vida: m += f"{vida}\n"
    m += f"\nScore: {sc}/10\n"
    if es_rev and p_orig>precio:
        m += f"💰 Reventa: ${rl:,.0f}–${rh:,.0f}\nGanancia: *+${rl-precio:,.0f}*\n"
    elif p_orig>precio:
        m += f"_Reventa: ${rl:,.0f}–${rh:,.0f}_\n"
    m += f"\n[COMPRAR AHORA]({lnk})\n"
    ht = generar_hashtags(nombre, item["descuento"], sc, cupon, es_flash)
    if ht: m += f"\n{ht}"
    return m[:1024]

# ─────────────────────────────────────────────
# PROCESAMIENTO
# ─────────────────────────────────────────────
def procesar(prod_raw, pagina_es_flash=False):
    try:
        item_id=str(prod_raw.get("id","")); nombre=str(prod_raw.get("title",""))[:80]
        precio=float(prod_raw.get("price",0)); p_orig=prod_raw.get("original_price")
        p_orig=float(p_orig) if p_orig else 0; link=str(prod_raw.get("permalink",""))
        stk_raw=prod_raw.get("available_quantity")
        stk=int(stk_raw) if stk_raw is not None else None
        thumb=str(prod_raw.get("thumbnail","")); cupon=bool(prod_raw.get("tiene_cupon",False))
        c_monto=float(prod_raw.get("cupon_monto",0))
        p_cupon=float(prod_raw.get("precio_con_cupon",precio))
        es_flash=bool(prod_raw.get("es_flash",False)) or pagina_es_flash
        ev=bool(prod_raw.get("envio_gratis",False))
        if not nombre or precio<=0 or not link: return None
        if precio>200000 or precio<10: return None
        descuento=0.0
        if p_orig and p_orig>precio: descuento=(p_orig-precio)/p_orig
        if cupon and c_monto>0: descuento=max(descuento,c_monto/precio)
        es_remate="remate" in link.lower()
        if descuento < (0.05 if es_remate else 0.15): return None
        pid=upsert_prod(link,nombre,"ML Ofertas",item_id)
        guardar_precio(pid,precio,p_orig or precio,stk or 0)
        sc=score(descuento,stk,precio,cupon,ev,es_flash)
        if not E.puede_publicar_pid(pid,sc,precio,"vip"): return None   # política de repeticiones (estado.py)
        stats=get_stats(pid,precio)
        thumb_hd=thumb.replace("I.jpg","O.jpg") if thumb else ""
        return {"id":item_id,"pid":pid,"nombre":nombre,"precio":precio,
                "precio_orig":p_orig or precio,"descuento":descuento,"stock":stk,
                "url":link,"thumbnail":thumb_hd or thumb,"score":sc,"stats":stats,
                "tiene_cupon":cupon,"cupon_monto":c_monto,"precio_con_cupon":p_cupon,
                "es_flash":es_flash,"envio_gratis":ev}
    except: return None

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def _a_cola(item, n_vip, en_vip):
    """Item ML -> formato estándar de cola_free (con link de afiliado ya aplicado)."""
    return {
        "tienda": "mercadolibre", "nombre": item["nombre"], "precio_actual": item["precio"],
        "precio_original": item["precio_orig"], "descuento": item["descuento"], "sku": item["id"],
        "url": link_ml(item["url"], item["id"]), "thumbnail": item.get("thumbnail", ""),
        "cat_nombre": "Mercado Libre", "cat_emoji": "🛒", "envio_gratis": item.get("envio_gratis", False),
        "es_flash": item.get("es_flash", False), "en_vip": en_vip,
    }


def main():
    ahora = H.ahora()
    hora = ahora.hour
    hoy = H.fecha_mx(ahora)
    logger.info(f"[GITHUB v12] {ahora.strftime('%d/%m %H:%M')} MX · VIP={'sí' if H.en_horario_vip() else 'NOCTURNO'}")

    todos = []
    total_scrapeado = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(user_agent=random.choice(USER_AGENTS), locale="es-MX",
            timezone_id="America/Mexico_City", viewport={"width": 1366, "height": 768})
        page = ctx.new_page()
        for pagina in PAGINAS:
            items_pag = scrape_pagina(page, pagina)
            for prod_raw in items_pag:
                it = procesar(prod_raw, pagina_es_flash=pagina.get("es_flash", False))
                if it: todos.append(it)
            total_scrapeado += len(items_pag)
            time.sleep(random.uniform(2, 4))
        browser.close()

    if total_scrapeado < 10:
        logger.warning(f"[GITHUB] Solo {total_scrapeado} items en Playwright — activando API fallback")
        for prod_raw in ml_api_fallback(50):
            it = procesar(prod_raw)
            if it: todos.append(it)
    E.log_fuente("ML Playwright", total_scrapeado, "" if total_scrapeado else "0 items")

    seen = {}
    for a in todos:
        if a:
            ex = seen.get(a["id"])
            if ex is None or a["score"] > ex["score"]: seen[a["id"]] = a
    unicos = list(seen.values())
    unicos.sort(key=lambda x: (x.get("es_flash", False), x["score"]), reverse=True)
    logger.info(f"[GITHUB] Únicos >=15%: {len(unicos)} flash:{sum(1 for x in unicos if x.get('es_flash'))}")

    # ── VIP (6:30 AM-11:30 PM normal · resto del día solo score >= 8) ──
    vip_n = 0; ids_vip = set(); ids_excl = set()
    for item in unicos:
        if vip_n >= MAX_VIP: break
        if not H.vip_puede_publicar(item["score"]):
            continue
        es_excl = H.es_exclusivo(item["descuento"], item["score"], item.get("es_flash"))
        thumb = item.get("thumbnail", "")
        if thumb and len(thumb) > 10 and thumb.startswith("http"):
            mid = enviar_foto(CHANNEL_VIP_ID, thumb, msg_vip_caption(item, item.get("stats", {})))
        else:
            mid = enviar(CHANNEL_VIP_ID, msg_vip(item, item.get("stats", {})))
        if mid:
            guardar_alerta(item.get("pid"), item["score"], "vip", item["precio"], item["descuento"])
            vip_n += 1; ids_vip.add(item["id"])
            if es_excl: ids_excl.add(item["id"])
            if item["score"] >= 8 and MAKE_WEBHOOK_URL:
                try:
                    requests.post(MAKE_WEBHOOK_URL, json={
                        "nombre": item["nombre"][:80], "precio": str(round(item["precio"])),
                        "descuento": str(round(item["descuento"] * 100)), "thumbnail": item.get("thumbnail", ""),
                        "link": item["url"], "score": item["score"], "es_flash": item.get("es_flash", False)}, timeout=10)
                except: pass
        time.sleep(5)

    # ── Hacia el free: SIEMPRE por la cola, 60 min después (lo publica main.py) ──
    encolados = 0
    candidatos = [x for x in unicos if x["score"] >= 2 and H.puede_pasar_al_free(x["descuento"], x["score"], x.get("es_flash"))]
    for item in sorted(candidatos, key=lambda x: x["score"], reverse=True)[:8]:
        if E.reclamar_evento(f"cola:mercadolibre:{item['id']}:{hoy}", fallback=True):
            if E.cola_agregar(_a_cola(item, vip_n, item["id"] in ids_vip), item["score"], vip_n, delay_min=H.VENTAJA_VIP_MIN):
                encolados += 1

    # ── Teaser (sin revelar producto): solo en horario free, máximo 1 cada 2 h ──
    if ids_excl and H.en_horario_free() and E.reclamar_evento(f"fomo:{hoy}:{hora // 2}", fallback=False):
        n = len(ids_excl)
        E.tg_send(CHANNEL_FREE_ID, f"🔒 El Canal VIP tiene <b>{n} oferta{'s' if n > 1 else ''} exclusiva{'s' if n > 1 else ''}</b> hoy.\n\n<i>No se publican aquí.</i>",
                  boton=("📲 Ver Canal VIP", LAUNCHPASS_LINK))

    if hora == 7 and vip_n == 0 and E.reclamar_evento(f"buenos_dias:{hoy}", fallback=False):
        enviar(CHANNEL_VIP_ID, "🌅 *Buenos días — DropNode VIP*\n\nEl equipo ya está revisando Solo Hoy, Remates y todas las secciones.\n_Solo publicamos cuando hay algo real._")

    logger.info(f"[GITHUB v12] VIP:{vip_n} Excl:{len(ids_excl)} Cola free:{encolados}")


if __name__ == "__main__":
    main()
