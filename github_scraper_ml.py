import os
import time
import random
import logging
import sys
import json
import re
import requests
import datetime as _dt
from datetime import datetime, timedelta, timezone
from supabase import create_client
from playwright.sync_api import sync_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ["SUPABASE_URL"].strip()
SUPABASE_KEY = os.environ["SUPABASE_KEY"].strip()
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"].strip()
CHANNEL_FREE_ID = int(os.environ["CHANNEL_FREE_ID"].strip())
CHANNEL_VIP_ID = int(os.environ["CHANNEL_VIP_ID"].strip())
ML_AFFILIATE_ID = os.environ.get("ML_AFFILIATE_ID", "marcodurzo").strip()
LAUNCHPASS_LINK = os.environ.get("LAUNCHPASS_LINK", "").strip()
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL", "").strip()

TZ_MEXICO = timezone(timedelta(hours=-6))
TELEGRAM_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

db = None
try:
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("[DB] Conexion OK")
except Exception as e:
    logger.warning("[DB] Sin historial: " + str(e))


def upsert_prod(url, nombre, categoria, sku):
    if not db:
        return None
    try:
        r = db.table("productos").upsert(
            {"url": url, "tienda": "mercadolibre", "nombre": nombre,
             "categoria": categoria, "sku": sku, "activo": True},
            on_conflict="sku,tienda"
        ).execute()
        if r.data:
            return r.data[0]["id"]
        r2 = db.table("productos").select("id").eq("sku", sku).eq("tienda", "mercadolibre").execute()
        return r2.data[0]["id"] if r2.data else None
    except Exception as e:
        logger.error("[DB upsert] " + str(e)[:80])
        return None


HORA_FREE_INICIO = 8
HORA_FREE_FIN = 22
DESCUENTO_HOT = 0.35
SCORE_VIP_EXCL = 7
MAX_VIP = 12
MAX_FREE = 4
VENTAJA_SEG = 180

PAGINAS_BASE = [
    {"url": "https://www.mercadolibre.com.mx/ofertas",           "nombre": "Ofertas p1", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=2",    "nombre": "Ofertas p2", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=3",    "nombre": "Ofertas p3", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=4",    "nombre": "Ofertas p4", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=5",    "nombre": "Ofertas p5", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=6",    "nombre": "Ofertas p6", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=7",    "nombre": "Ofertas p7", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=8",    "nombre": "Ofertas p8", "emoji": "🔥"},
]

PAGINAS_CAT = [
    {"url": "https://www.mercadolibre.com.mx/ofertas/electronica",   "nombre": "Electronica",   "emoji": "🔌"},
    {"url": "https://www.mercadolibre.com.mx/ofertas/celulares",     "nombre": "Celulares",     "emoji": "📱"},
    {"url": "https://www.mercadolibre.com.mx/ofertas/computacion",   "nombre": "Computacion",   "emoji": "💻"},
    {"url": "https://www.mercadolibre.com.mx/ofertas/juguetes",      "nombre": "Juguetes",      "emoji": "🧸"},
    {"url": "https://www.mercadolibre.com.mx/ofertas/bebes",         "nombre": "Bebes",         "emoji": "👶"},
    {"url": "https://www.mercadolibre.com.mx/ofertas/mascotas",      "nombre": "Mascotas",      "emoji": "🐾"},
    {"url": "https://www.mercadolibre.com.mx/ofertas/deportes",      "nombre": "Deportes",      "emoji": "⚽"},
    {"url": "https://www.mercadolibre.com.mx/ofertas/hogar",         "nombre": "Hogar",         "emoji": "🏠"},
]

_hora_run = _dt.datetime.utcnow().hour
_idx = (_hora_run // 2) % len(PAGINAS_CAT)
PAGINAS = PAGINAS_BASE + PAGINAS_CAT[_idx:_idx+2]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
]

JS_EXTRACT = """
() => {
    var productos = [];
    var cards = document.querySelectorAll('.poly-card');
    if (cards.length === 0) cards = document.querySelectorAll('.andes-card');

    function parsePrecio(card) {
        var frac = card.querySelector('[class*="price__fraction"],[class*="amount__fraction"],[class*="price-tag-fraction"]');
        if (frac) {
            var f = frac.textContent.replace(/[^0-9]/g, "");
            var cEl = card.querySelector('[class*="price__cents"],[class*="amount__cents"],[class*="price-tag-cents"]');
            var c = cEl ? cEl.textContent.replace(/[^0-9]/g, "").substring(0,2) : "00";
            if (f) return parseFloat(f + "." + c);
        }
        var els = card.querySelectorAll('[class*="price"],[class*="amount"]');
        for (var i = 0; i < els.length; i++) {
            var nodes = els[i].childNodes;
            var txt = "";
            for (var n = 0; n < nodes.length; n++) {
                if (nodes[n].nodeType === 3) txt += nodes[n].textContent;
            }
            txt = txt.replace(/[^0-9.,]/g,"").trim();
            if (txt.length >= 2 && txt.length <= 10) {
                txt = txt.replace(/,([0-9]{3})/g,"$1").replace(",",".");
                var p = parseFloat(txt);
                if (p > 10 && p < 500000) return p;
            }
        }
        return 0;
    }

    for (var i = 0; i < cards.length; i++) {
        try {
            var card = cards[i];
            var tEl = card.querySelector('[class*="title"],h2,h3');
            var titulo = tEl ? tEl.textContent.trim() : "";
            var precio = parsePrecio(card);
            var origEl = card.querySelector('s,del,[class*="original"],[class*="regular-price"]');
            var orig = 0;
            if (origEl) {
                var of = origEl.querySelector('[class*="fraction"]');
                if (of) {
                    orig = parseFloat(of.textContent.replace(/[^0-9]/g,"") || "0");
                } else {
                    var ot = origEl.textContent.replace(/[^0-9.,]/g,"").replace(/,([0-9]{3})/g,"$1");
                    if (ot.length >= 2 && ot.length <= 8) orig = parseFloat(ot);
                }
            }
            var lEl = card.querySelector("a[href]");
            var link = lEl ? lEl.href : "";
            var iEl = card.querySelector("img");
            var img = iEl ? (iEl.src || iEl.getAttribute("data-src") || "") : "";
            var idm = link.match(/MLM[0-9]+/);
            var id = idm ? idm[0] : ("item_" + i);
            var html = card.innerHTML.toLowerCase();
            var cupon = html.indexOf("cup") >= 0 && html.indexOf("descuento") >= 0;
            var cmonto = 0;
            if (cupon) {
                var cm = html.match(/cup[^0-9]*([0-9]{2,5})/);
                if (cm) cmonto = parseFloat(cm[1]);
            }
            if (titulo && titulo.length > 5 && precio > 10 && precio < 200000 && link.indexOf("mercadolibre") >= 0) {
                productos.push({
                    id: id, title: titulo.substring(0,100),
                    price: precio,
                    original_price: (orig > precio && orig < precio * 8) ? orig : 0,
                    permalink: link, thumbnail: img, available_quantity: 10,
                    tiene_cupon: cupon, cupon_monto: cmonto,
                    precio_con_cupon: cmonto > 0 ? precio - cmonto : precio
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
        time.sleep(random.uniform(4, 7))
        items = page.evaluate(JS_EXTRACT)
        logger.info("[PW] " + pagina["nombre"] + ": " + str(len(items or [])) + " productos")
        return items or []
    except Exception as e:
        logger.error("[PW] " + str(e))
        return []


def guardar_precio(pid, precio, precio_orig, stock):
    if not pid or not db:
        return
    try:
        db.table("historial_precios").insert({
            "producto_id": pid, "precio": precio,
            "precio_original": precio_orig, "stock": stock,
            "disponible": stock > 0,
            "timestamp": datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        logger.error("[DB precio] " + str(e)[:60])


def alerta_hoy(pid):
    if not pid or not db:
        return False
    try:
        desde = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
        r = db.table("alertas_enviadas").select("id").eq("producto_id", pid).gte("timestamp", desde).execute()
        return len(r.data) > 0
    except Exception:
        return False


def guardar_alerta(pid, score, canal, precio, descuento):
    if not pid or not db:
        return
    try:
        db.table("alertas_enviadas").insert({
            "producto_id": pid, "heat_score": score, "canal": canal,
            "precio_alerta": precio, "descuento_real": descuento,
            "clicks": 0, "timestamp": datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        logger.error("[DB alerta] " + str(e)[:60])


def get_stats(pid, precio_actual):
    if not pid or not db:
        return {}
    try:
        desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
        r = db.table("historial_precios").select("precio, timestamp").eq("producto_id", pid).gte("timestamp", desde).order("timestamp").execute()
        regs = r.data or []
        if len(regs) < 5:
            return {}
        precios = [float(x["precio"]) for x in regs]
        primer = datetime.fromisoformat(regs[0]["timestamp"].replace("Z", ""))
        dias = (datetime.utcnow() - primer).days + 1
        min_p = min(precios)
        return {"min": min_p, "max": max(precios),
                "avg": sum(precios)/len(precios), "dias": dias,
                "es_minimo": precio_actual <= min_p * 1.02 and dias >= 7}
    except Exception:
        return {}


# ─────────────────────────────────────────────
# TELEGRAM — envío
# ─────────────────────────────────────────────

def enviar(chat_id, texto, modo="Markdown"):
    try:
        r = requests.post(TELEGRAM_API + "/sendMessage", json={
            "chat_id": chat_id, "text": texto,
            "parse_mode": modo,
            "disable_web_page_preview": True
        }, timeout=15)
        d = r.json()
        if d.get("ok"):
            return d["result"]["message_id"]
        logger.warning("[TG] " + str(d.get("description", "")))
    except Exception as e:
        logger.error("[TG] " + str(e))
    return None


def enviar_foto(chat_id, foto_url, caption, modo="Markdown"):
    """
    Envía imagen con caption.
    Fallback automático a sendMessage si la foto falla
    (URL expirada, formato no soportado, timeout, etc.)
    """
    cap = caption[:1024]  # Telegram limita captions a 1024 chars
    try:
        r = requests.post(TELEGRAM_API + "/sendPhoto", json={
            "chat_id": chat_id,
            "photo": foto_url,
            "caption": cap,
            "parse_mode": modo,
        }, timeout=20)
        d = r.json()
        if d.get("ok"):
            return d["result"]["message_id"]
        logger.warning("[TG foto] " + str(d.get("description", "")) + " — fallback texto")
        return enviar(chat_id, caption, modo)
    except Exception as e:
        logger.error("[TG foto] " + str(e))
        return enviar(chat_id, caption, modo)


# ─────────────────────────────────────────────
# AFILIADOS
# ─────────────────────────────────────────────

def link_ml(url, item_id):
    base = url.split("?")[0].split("#")[0]
    return base + "?matt_tool=" + ML_AFFILIATE_ID


# ─────────────────────────────────────────────
# SCORE
# ─────────────────────────────────────────────

def score(descuento, stock, precio, cupon):
    s = 0.0
    if descuento >= 0.60:   s += 4.0
    elif descuento >= 0.40: s += 3.5
    elif descuento >= 0.25: s += 3.0
    elif descuento >= 0.15: s += 2.0
    elif descuento >= 0.05: s += 1.0
    else:                   s += 0.2

    if stock == 1:    s += 2.0
    elif stock <= 3:  s += 1.8
    elif stock <= 10: s += 1.0

    if precio >= 8000:   s += 1.5
    elif precio >= 3000: s += 1.0

    if cupon: s += 1.0
    return min(10, round(s))


# ─────────────────────────────────────────────
# FORMATOS DE MENSAJE
# ─────────────────────────────────────────────

def msg_vip(item, stats):
    """Mensaje VIP completo — para envío sin foto o como referencia."""
    nombre  = item["nombre"][:65]
    precio  = item["precio"]
    p_orig  = item["precio_orig"]
    desc    = item["descuento"] * 100
    stk     = item["stock"]
    lnk     = link_ml(item["url"], item["id"])
    sc      = item["score"]
    cupon   = item.get("tiene_cupon", False)
    c_monto = item.get("cupon_monto", 0)
    p_cupon = item.get("precio_con_cupon", precio)
    hora    = datetime.now(TZ_MEXICO).strftime("%H:%M:%S")
    rl = p_orig * 0.80
    rh = p_orig * 0.92

    if sc >= 8 or item["descuento"] >= 0.50:
        icono = "🚨"; tag = "ERROR DE PRECIO - SOLO VIP"
    elif item["descuento"] >= DESCUENTO_HOT:
        icono = "🔥"; tag = "HOT DEAL - EXCLUSIVO VIP"
    elif cupon:
        icono = "🎟️"; tag = "OFERTA + CUPON - VIP"
    else:
        icono = "⚡"; tag = "ALERTA VIP"

    if stk == 1:    stxt = "*ULTIMA UNIDAD*"
    elif stk <= 3:  stxt = "*Solo " + str(stk) + " unidades*"
    elif stk <= 10: stxt = str(stk) + " unidades"
    else:           stxt = "Stock disponible"

    m  = icono + " *" + tag + "*\n\n"
    m += "*" + nombre + "*\n\n"
    m += "Precio ahora: *$" + "{:,.2f}".format(precio) + " MXN*\n"
    if p_orig > precio:
        m += "Precio original: $" + "{:,.2f}".format(p_orig) + " MXN\n"
    m += "Descuento: *-" + "{:.0f}".format(desc) + "%*\n"
    if cupon and c_monto > 0:
        m += "\n🎟️ *Con cupon: $" + "{:,.2f}".format(p_cupon) + " MXN* (−$" + "{:,.0f}".format(c_monto) + " adicional)\n"
    if stats.get("es_minimo") and stats.get("dias", 0) >= 7:
        m += "\n*Precio mas bajo en " + str(stats["dias"]) + " dias de seguimiento*\n"
    if stats.get("avg") and precio < stats["avg"] * 0.90:
        m += "$" + "{:,.0f}".format(stats["avg"] - precio) + " menos que el precio promedio\n"
    m += "\n" + stxt + "\n"
    if desc >= 30 or stk <= 3:
        m += "_Oferta podria terminar pronto_\n"
    m += "\nScore: " + str(sc) + "/10\n\n"
    m += "[COMPRAR AHORA](" + lnk + ")\n\n"
    if p_orig > precio:
        m += "_Reventa estimada: $" + "{:,.0f}".format(rl) + " - $" + "{:,.0f}".format(rh) + " MXN_\n"
    m += "_" + hora + " hora MX_"
    return m


def msg_vip_caption(item, stats):
    """
    Versión compacta del mensaje VIP para usar como caption de foto.
    Max 1024 chars — muestra lo esencial de forma clara con la imagen.
    """
    nombre  = item["nombre"][:55]
    precio  = item["precio"]
    p_orig  = item["precio_orig"]
    desc    = item["descuento"] * 100
    stk     = item["stock"]
    lnk     = link_ml(item["url"], item["id"])
    sc      = item["score"]
    cupon   = item.get("tiene_cupon", False)
    c_monto = item.get("cupon_monto", 0)
    p_cupon = item.get("precio_con_cupon", precio)
    hora    = datetime.now(TZ_MEXICO).strftime("%H:%M")
    rl = p_orig * 0.80
    rh = p_orig * 0.92

    if sc >= 8 or item["descuento"] >= 0.50:
        icono = "🚨"; tag = "ERROR DE PRECIO — SOLO VIP"
    elif item["descuento"] >= DESCUENTO_HOT:
        icono = "🔥"; tag = "HOT DEAL — EXCLUSIVO VIP"
    elif cupon:
        icono = "🎟️"; tag = "OFERTA + CUPÓN — VIP"
    else:
        icono = "⚡"; tag = "ALERTA VIP"

    if stk == 1:    stxt = "*ÚLTIMA UNIDAD*"
    elif stk <= 3:  stxt = f"*Solo {stk} unidades*"
    elif stk <= 10: stxt = f"{stk} unidades"
    else:           stxt = ""

    m  = f"{icono} *{tag}*\n\n"
    m += f"*{nombre}*\n\n"
    m += f"*${precio:,.0f} MXN* (−{desc:.0f}%)\n"
    if p_orig > precio:
        m += f"Normal: ${p_orig:,.0f}\n"
    if cupon and c_monto > 0:
        m += f"🎟️ Con cupón: *${p_cupon:,.0f}*\n"
    if stats.get("es_minimo") and stats.get("dias", 0) >= 7:
        m += f"\n_Precio más bajo en {stats['dias']} días_\n"
    if stxt:
        m += f"\n{stxt}\n"
    if desc >= 30 or stk <= 3:
        m += "_Podría terminar pronto_\n"
    m += f"\nScore: {sc}/10"
    if p_orig > precio:
        m += f"\n_Reventa est: ${rl:,.0f}–${rh:,.0f}_"
    m += f"\n_{hora} MX_\n\n"
    m += f"[COMPRAR AHORA]({lnk})"
    return m[:1024]


def msg_free(item):
    nombre  = item["nombre"][:55]
    precio  = item["precio"]
    p_orig  = item["precio_orig"]
    desc    = item["descuento"] * 100
    stk     = item["stock"]
    lnk     = link_ml(item["url"], item["id"])
    sc      = item["score"]
    cupon   = item.get("tiene_cupon", False)
    c_monto = item.get("cupon_monto", 0)
    p_cupon = item.get("precio_con_cupon", precio)

    if sc >= 7:   icono = "🚨"
    elif sc >= 5: icono = "🔥"
    elif cupon:   icono = "🎟️"
    else:         icono = "⚡"

    m  = icono + " <b>" + nombre + "</b>\n\n"
    m += "<b>$" + "{:,.2f}".format(precio) + " MXN</b>"
    if desc >= 5:
        m += " <i>(-" + "{:.0f}".format(desc) + "%)</i>"
    m += "\n"
    if p_orig > precio:
        m += "<s>$" + "{:,.2f}".format(p_orig) + "</s>\n"
    if cupon and c_monto > 0:
        m += "🎟️ Con cupon: <b>$" + "{:,.2f}".format(p_cupon) + " MXN</b>\n"
    if stk <= 5:
        m += "<b>Solo " + str(stk) + " unidades disponibles</b>\n"
    m += "\n<a href=\"" + lnk + "\">Ver oferta en Mercado Libre</a>\n\n"
    m += "<i>Los VIP la recibieron antes con analisis completo.</i>\n"
    if LAUNCHPASS_LINK:
        m += "<a href=\"" + LAUNCHPASS_LINK + "\">📲 Pasar al canal DropNode VIP</a>"
    return m


# ─────────────────────────────────────────────
# PROCESAMIENTO
# ─────────────────────────────────────────────

def procesar(prod_raw):
    try:
        item_id = str(prod_raw.get("id", ""))
        nombre  = str(prod_raw.get("title", ""))[:80]
        precio  = float(prod_raw.get("price", 0))
        p_orig  = prod_raw.get("original_price")
        p_orig  = float(p_orig) if p_orig else 0
        link    = str(prod_raw.get("permalink", ""))
        stk     = int(prod_raw.get("available_quantity", 10))
        thumb   = str(prod_raw.get("thumbnail", ""))
        cupon   = bool(prod_raw.get("tiene_cupon", False))
        c_monto = float(prod_raw.get("cupon_monto", 0))
        p_cupon = float(prod_raw.get("precio_con_cupon", precio))

        if not nombre or precio <= 0 or not link:
            return None
        if precio > 200000 or precio < 10:
            return None

        descuento = 0.0
        if p_orig and p_orig > precio:
            descuento = (p_orig - precio) / p_orig
        if cupon and c_monto > 0:
            descuento = max(descuento, c_monto / precio)

        pid = upsert_prod(link, nombre, "ML Ofertas", item_id)
        guardar_precio(pid, precio, p_orig or precio, stk)
        if alerta_hoy(pid):
            return None

        sc = score(descuento, stk, precio, cupon)
        stats = get_stats(pid, precio)

        # Usar imagen de mayor resolución si está disponible
        thumb_hd = thumb.replace("I.jpg", "O.jpg") if thumb else ""

        return {
            "id": item_id, "pid": pid, "nombre": nombre,
            "precio": precio, "precio_orig": p_orig or precio,
            "descuento": descuento, "stock": stk,
            "url": link, "thumbnail": thumb_hd or thumb,
            "score": sc, "stats": stats,
            "tiene_cupon": cupon, "cupon_monto": c_monto,
            "precio_con_cupon": p_cupon
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    hora_mx = datetime.now(TZ_MEXICO)
    hora = hora_mx.hour
    logger.info("[GITHUB v6] " + hora_mx.strftime("%d/%m %H:%M") + " MX")

    es_horario_free = HORA_FREE_INICIO <= hora < HORA_FREE_FIN
    es_madrugada    = hora < 7

    todos = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale="es-MX", timezone_id="America/Mexico_City",
            viewport={"width": 1366, "height": 768}
        )
        page = context.new_page()
        for pagina in PAGINAS:
            for prod_raw in scrape_pagina(page, pagina):
                item = procesar(prod_raw)
                if item:
                    todos.append(item)
            time.sleep(random.uniform(2, 4))
        browser.close()

    seen = set()
    unicos = []
    for a in todos:
        if a and a["id"] not in seen:
            seen.add(a["id"])
            unicos.append(a)
    unicos.sort(key=lambda x: x["score"], reverse=True)
    logger.info("[GITHUB] Productos unicos: " + str(len(unicos)))

    vip_n  = 0
    free_n = 0
    ids_vip = set()

    # ── VIP primero ──
    for item in unicos:
        if vip_n >= MAX_VIP:
            break
        if es_madrugada and item["descuento"] < DESCUENTO_HOT:
            continue

        thumb   = item.get("thumbnail", "")
        caption = msg_vip_caption(item, item.get("stats", {}))

        # Enviar con foto si hay thumbnail válido, texto completo como fallback
        if thumb and len(thumb) > 10 and thumb.startswith("http"):
            mid = enviar_foto(CHANNEL_VIP_ID, thumb, caption)
        else:
            mid = enviar(CHANNEL_VIP_ID, msg_vip(item, item.get("stats", {})))

        if mid:
            guardar_alerta(item.get("pid"), item["score"], "vip",
                           item["precio"], item["descuento"])
            ids_vip.add(item["id"])
            vip_n += 1

            # Webhook Make para score alto
            if item["score"] >= 8 and MAKE_WEBHOOK_URL:
                try:
                    requests.post(MAKE_WEBHOOK_URL, json={
                        "nombre":    item["nombre"][:80],
                        "precio":    str(round(item["precio"])),
                        "descuento": str(round(item["descuento"] * 100)),
                        "thumbnail": item.get("thumbnail", ""),
                        "link":      item["url"],
                        "score":     item["score"]
                    }, timeout=10)
                except Exception:
                    pass

        time.sleep(5)

    # ── Esperar ventaja de tiempo antes del free ──
    if vip_n > 0 and es_horario_free:
        logger.info("[GITHUB] Esperando " + str(VENTAJA_SEG // 60) + " min antes del free...")
        time.sleep(VENTAJA_SEG)

    # ── Free ──
    if es_horario_free:
        candidatos = [x for x in unicos if x["score"] >= 2][:MAX_FREE]
        if not candidatos and unicos:
            candidatos = unicos[:MAX_FREE]

        for item in candidatos:
            mid = enviar(CHANNEL_FREE_ID, msg_free(item), "HTML")
            if mid:
                guardar_alerta(item.get("pid"), item["score"], "free",
                               item["precio"], item["descuento"])
                free_n += 1
            time.sleep(6)

    # ── Resumen si no hubo alertas a mediodía o 7pm ──
    if free_n == 0 and hora in (12, 19) and unicos:
        top    = unicos[:5]
        titulo = "Mejores precios de la tarde" if hora >= 15 else "Mejores precios de la manana"
        msg    = "📋 <b>" + titulo + " — DropNode MX</b>\n\n"
        msg   += "<i>Nuestro equipo reviso miles de productos. Estos destacan:</i>\n\n"
        for i, it in enumerate(top, 1):
            lnk = link_ml(it["url"], it["id"])
            d   = it["descuento"] * 100
            ln  = str(i) + ". 🔥 <b>" + it["nombre"][:50] + "</b>\n"
            ln += "   <b>$" + "{:,.2f}".format(it["precio"]) + " MXN</b>"
            if d >= 5:
                ln += " (-" + "{:.0f}".format(d) + "%)"
            if it.get("tiene_cupon"):
                ln += " 🎟️"
            ln += " <a href=\"" + lnk + "\">Ver oferta</a>"
            msg += ln + "\n\n"
        if LAUNCHPASS_LINK:
            msg += "🔒 <i>Los VIP los vieron primero con analisis completo.</i>\n"
            msg += "<a href=\"" + LAUNCHPASS_LINK + "\">📲 Pasar al canal DropNode VIP</a>"
        enviar(CHANNEL_FREE_ID, msg, "HTML")
        free_n += 1

    # ── Buenos días VIP ──
    if hora == 7 and vip_n == 0:
        enviar(CHANNEL_VIP_ID,
               "🌅 *Buenos dias — DropNode VIP*\n\nYa estamos monitoreando. "
               "Las alertas de hoy llegan en cuanto encontremos algo que valga tu atencion.\n\n"
               "_Solo publicamos cuando hay algo real._")

    logger.info("[GITHUB v6] Fin — VIP:" + str(vip_n) + " Free:" + str(free_n))


if __name__ == "__main__":
    main()