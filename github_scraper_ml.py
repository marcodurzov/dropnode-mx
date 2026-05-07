import os
import time
import random
import logging
import sys
import requests
from datetime import datetime, timedelta, timezone
from supabase import create_client
from playwright.sync_api import sync_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

SUPABASE_URL     = os.environ["SUPABASE_URL"].strip()
SUPABASE_KEY     = os.environ["SUPABASE_KEY"].strip()
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"].strip()
CHANNEL_FREE_ID  = int(os.environ["CHANNEL_FREE_ID"].strip())
CHANNEL_VIP_ID   = int(os.environ["CHANNEL_VIP_ID"].strip())
ML_AFFILIATE_ID  = os.environ.get("ML_AFFILIATE_ID", "marcodurzo").strip()
LAUNCHPASS_LINK  = os.environ.get("LAUNCHPASS_LINK", "").strip()
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL", "").strip()

TZ_MEXICO    = timezone(timedelta(hours=-6))
TELEGRAM_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

# Supabase con manejo de error graceful
db = None
try:
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("[DB] Conexion OK")
except Exception as e:
    logger.warning("[DB] Sin Supabase - modo sin historial: " + str(e))

# Umbrales
# VIP: recibe TODAS las alertas score >= 3 (con mas detalle)
# Free: recibe solo las mejores (score >= 5), menos cantidad, version corta
MAX_ALERTAS_VIP  = 8   # max alertas por run en VIP
MAX_ALERTAS_FREE = 3   # max alertas por run en canal free (las 3 mejores)
SCORE_MIN_VIP    = 3   # score minimo para VIP
SCORE_MIN_FREE   = 5   # score minimo para free

PAGINAS = [
    {"url": "https://www.mercadolibre.com.mx/ofertas",        "nombre": "Ofertas p1", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=2", "nombre": "Ofertas p2", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=3", "nombre": "Ofertas p3", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=4", "nombre": "Ofertas p4", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=5", "nombre": "Ofertas p5", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=6", "nombre": "Ofertas p6", "emoji": "🔥"},
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

JS_EXTRACT = """
() => {
    var productos = [];
    var cards = document.querySelectorAll('.poly-card');
    if (cards.length === 0) cards = document.querySelectorAll('.andes-card');
    for (var i = 0; i < cards.length; i++) {
        try {
            var card = cards[i];
            var tituloEl = card.querySelector('[class*="title"], h2, h3');
            var titulo = tituloEl ? tituloEl.textContent.trim() : "";
            var precio = 0;
            var precioEls = card.querySelectorAll('[class*="price"], [class*="amount"]');
            for (var pi = 0; pi < precioEls.length; pi++) {
                var txt = precioEls[pi].textContent.replace(/[^0-9]/g, "");
                if (txt.length >= 2 && txt.length <= 7) {
                    var p = parseFloat(txt);
                    if (p > 50 && p < 999999) { precio = p; break; }
                }
            }
            var origEl = card.querySelector('s, del, [class*="original"]');
            var orig = 0;
            if (origEl) {
                var ot = origEl.textContent.replace(/[^0-9]/g, "");
                if (ot.length >= 2) orig = parseFloat(ot);
            }
            var linkEl = card.querySelector("a[href]");
            var link = linkEl ? linkEl.href : "";
            var imgEl = card.querySelector("img");
            var img = imgEl ? (imgEl.src || imgEl.getAttribute("data-src") || "") : "";
            var idm = link.match(/MLM[0-9]+/);
            var id = idm ? idm[0] : ("item_" + i);
            var cardHtml = card.innerHTML.toLowerCase();
            var tieneCupon = cardHtml.indexOf("cup") >= 0 && (cardHtml.indexOf("descuento") >= 0 || cardHtml.indexOf("adicional") >= 0);
            var cuponMonto = 0;
            if (tieneCupon) {
                var cm = cardHtml.match(/cup[^0-9]*([0-9]{2,5})/);
                if (cm) cuponMonto = parseFloat(cm[1]);
            }
            if (titulo && titulo.length > 5 && precio > 50 && link.includes("mercadolibre")) {
                productos.push({
                    id: id, title: titulo.substring(0, 100),
                    price: precio, original_price: orig > precio ? orig : 0,
                    permalink: link, thumbnail: img, available_quantity: 10,
                    tiene_cupon: tieneCupon, cupon_monto: cuponMonto,
                    precio_con_cupon: cuponMonto > 0 ? precio - cuponMonto : precio
                });
            }
        } catch (e) {}
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
        logger.info("[PW] " + pagina["nombre"] + ": " + str(len(items)) + " productos")
        return items or []
    except Exception as e:
        logger.error("[PW] " + str(e))
        return []


def alerta_hoy_db(item_id):
    if not db:
        return False
    try:
        desde = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
        r = db.table("alertas_enviadas").select("id").eq("producto_id", item_id).gte("timestamp", desde).execute()
        return len(r.data) > 0
    except Exception:
        return False


def guardar_alerta_db(item_id, score, canal, precio, descuento):
    if not db:
        return
    try:
        db.table("alertas_enviadas").insert({
            "producto_id": item_id, "heat_score": score, "canal": canal,
            "precio_alerta": precio, "descuento_real": descuento,
            "clicks": 0, "timestamp": datetime.utcnow().isoformat()
        }).execute()
    except Exception:
        pass


def get_stats_db(item_id, precio_actual):
    if not db:
        return {}
    try:
        desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
        r = db.table("historial_precios").select("precio, timestamp").eq("producto_id", item_id).gte("timestamp", desde).order("timestamp").execute()
        regs = r.data or []
        if len(regs) < 5:
            return {}
        precios = [float(x["precio"]) for x in regs]
        primer  = datetime.fromisoformat(regs[0]["timestamp"].replace("Z", ""))
        dias    = (datetime.utcnow() - primer).days + 1
        min_p   = min(precios)
        return {"min": min_p, "max": max(precios), "avg": sum(precios)/len(precios),
                "dias": dias, "es_minimo": precio_actual <= min_p * 1.02 and dias >= 7}
    except Exception:
        return {}


def enviar(chat_id, texto):
    try:
        r = requests.post(TELEGRAM_API + "/sendMessage", json={
            "chat_id": chat_id, "text": texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=15)
        d = r.json()
        if d.get("ok"):
            return d["result"]["message_id"]
    except Exception as e:
        logger.error("[TG] " + str(e))
    return None


def link_ml(url, item_id):
    encoded = requests.utils.quote(url, safe="")
    return ("https://go.mercadolibre.com.mx?as_src=affiliate"
            "&as_campaign=dropnodemx&as_content=" + str(item_id)
            + "&url=" + encoded + "&affiliate_id=" + ML_AFFILIATE_ID)


def calcular_score(descuento, stock, precio, tiene_cupon):
    s = 0.0
    if descuento >= 0.60: s += 3.0
    elif descuento >= 0.40: s += 2.5
    elif descuento >= 0.25: s += 1.8
    elif descuento >= 0.10: s += 1.0
    else: s += 0.3
    if stock == 1: s += 2.0
    elif stock <= 3: s += 1.8
    elif stock <= 10: s += 1.0
    if precio >= 5000: s += 1.5
    elif precio >= 2000: s += 1.0
    if tiene_cupon: s += 1.0
    return min(10, round(s))


def msg_vip(item, stats):
    """Mensaje VIP: completo, con historial, analisis de reventa, cupon."""
    nombre  = item["nombre"][:65]
    precio  = item["precio"]
    p_orig  = item["precio_orig"]
    desc    = item["descuento"] * 100
    stock   = item["stock"]
    lnk     = link_ml(item["url"], item["id"])
    score   = item["score"]
    emoji   = item["emoji"]
    hora    = datetime.now(TZ_MEXICO).strftime("%H:%M:%S")
    cupon   = item.get("tiene_cupon", False)
    c_monto = item.get("cupon_monto", 0)
    p_cupon = item.get("precio_con_cupon", precio)

    if score >= 8: icono = "🚨"; tag = "ERROR DE PRECIO"
    elif score >= 6: icono = "🔥"; tag = "OFERTA AGRESIVA"
    elif cupon: icono = "🎟️"; tag = "OFERTA + CUPON"
    else: icono = "⚡"; tag = "DESCUENTO REAL"

    if stock == 1: stxt = "*ULTIMA UNIDAD*"
    elif stock <= 3: stxt = "*Solo " + str(stock) + " unidades*"
    elif stock <= 10: stxt = str(stock) + " unidades"
    else: stxt = "Stock disponible"

    rl = p_orig * 0.80
    rh = p_orig * 0.92

    m = icono + " *" + tag + "*  " + emoji + "\n\n"
    m += "*" + nombre + "*\n\n"
    m += "Precio ahora:    *$" + "{:,.0f}".format(precio) + " MXN*\n"
    if p_orig > precio:
        m += "Precio original:  $" + "{:,.0f}".format(p_orig) + " MXN\n"
        m += "Descuento:       *-" + "{:.0f}".format(desc) + "%*\n"
    if cupon and c_monto > 0:
        m += "\n🎟️ *Con cupon: $" + "{:,.0f}".format(p_cupon) + " MXN* (-$" + "{:,.0f}".format(c_monto) + " adicional)\n"
    if stats.get("es_minimo") and stats.get("dias", 0) >= 7:
        m += "\n*Precio mas bajo en " + str(stats["dias"]) + " dias de seguimiento*\n"
    if stats.get("avg") and precio < stats["avg"] * 0.90:
        m += "$" + "{:,.0f}".format(stats["avg"] - precio) + " menos que el precio promedio\n"
    m += "\n" + stxt + "\n"
    if desc >= 25 or stock <= 3:
        m += "_Oferta podria terminar pronto_\n"
    m += "\nScore: " + str(score) + "/10\n\n"
    m += "[COMPRAR AHORA](" + lnk + ")\n\n"
    if p_orig > precio:
        m += "_Reventa estimada: $" + "{:,.0f}".format(rl) + " - $" + "{:,.0f}".format(rh) + " MXN_\n"
    m += "_" + hora + " hora MX_"
    return m


def msg_free(item):
    """Mensaje Free: corto, sin analisis de reventa, con CTA al VIP."""
    nombre = item["nombre"][:55]
    precio = item["precio"]
    p_orig = item["precio_orig"]
    desc   = item["descuento"] * 100
    lnk    = link_ml(item["url"], item["id"])
    score  = item["score"]
    cupon  = item.get("tiene_cupon", False)

    if score >= 8: icono = "🚨"
    elif score >= 6: icono = "🔥"
    elif cupon: icono = "🎟️"
    else: icono = "⚡"

    m = icono + " *" + nombre + "*\n\n"
    m += "*$" + "{:,.0f}".format(precio) + " MXN*"
    if desc >= 5:
        m += " _(−" + "{:.0f}".format(desc) + "%)_"
    m += "\n"
    if p_orig > precio:
        m += "~~$" + "{:,.0f}".format(p_orig) + "~~ MXN\n"
    if cupon and item.get("cupon_monto", 0) > 0:
        m += "🎟️ Con cupon: *$" + "{:,.0f}".format(item["precio_con_cupon"]) + " MXN*\n"
    m += "\n[Ver oferta](" + lnk + ")\n\n"
    m += "🔒 _Los VIP la recibieron antes + analisis de reventa._\n"
    if LAUNCHPASS_LINK:
        m += "_" + LAUNCHPASS_LINK + "_"
    return m


def procesar(prod_raw):
    try:
        item_id = str(prod_raw.get("id", ""))
        nombre  = str(prod_raw.get("title", ""))[:80]
        precio  = float(prod_raw.get("price", 0))
        p_orig  = prod_raw.get("original_price")
        p_orig  = float(p_orig) if p_orig else 0
        link    = str(prod_raw.get("permalink", ""))
        stock   = int(prod_raw.get("available_quantity", 10))
        thumb   = str(prod_raw.get("thumbnail", ""))
        cupon   = bool(prod_raw.get("tiene_cupon", False))
        c_monto = float(prod_raw.get("cupon_monto", 0))
        p_cupon = float(prod_raw.get("precio_con_cupon", precio))

        if not nombre or precio <= 0 or not link:
            return None

        descuento = 0.0
        if p_orig and p_orig > precio:
            descuento = (p_orig - precio) / p_orig
        if cupon and c_monto > 0:
            d_cupon = c_monto / precio
            descuento = max(descuento, d_cupon)

        score = calcular_score(descuento, stock, precio, cupon)
        stats = get_stats_db(item_id, precio)

        return {
            "id": item_id, "nombre": nombre, "precio": precio,
            "precio_orig": p_orig or precio, "descuento": descuento,
            "stock": stock, "url": link, "thumbnail": thumb,
            "emoji": "🔥", "score": score, "stats": stats,
            "tiene_cupon": cupon, "cupon_monto": c_monto,
            "precio_con_cupon": p_cupon
        }
    except Exception:
        return None


def main():
    hora_mx = datetime.now(TZ_MEXICO)
    logger.info("[GITHUB v5] " + hora_mx.strftime("%d/%m %H:%M") + " MX")
    if not (8 <= hora_mx.hour < 22):
        logger.info("[GITHUB] Fuera de horario")
        return

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
            prods_raw = scrape_pagina(page, pagina)
            for prod_raw in prods_raw:
                item = procesar(prod_raw)
                if item:
                    todos.append(item)
            time.sleep(random.uniform(2, 4))

        browser.close()

    # Deduplicar
    seen  = set()
    unicos = []
    for a in todos:
        if a["id"] not in seen and not alerta_hoy_db(a["id"]):
            seen.add(a["id"])
            unicos.append(a)

    # Ordenar por score descendente
    unicos.sort(key=lambda x: x["score"], reverse=True)
    logger.info("[GITHUB] Productos unicos: " + str(len(unicos)))

    vip_n  = 0
    free_n = 0
    ids_vip = set()

    # VIP primero: top MAX_ALERTAS_VIP con score >= SCORE_MIN_VIP
    for item in unicos:
        if vip_n >= MAX_ALERTAS_VIP:
            break
        if item["score"] < SCORE_MIN_VIP:
            continue
        mid = enviar(CHANNEL_VIP_ID, msg_vip(item, item.get("stats", {})))
        if mid:
            guardar_alerta_db(item["id"], item["score"], "vip", item["precio"], item["descuento"])
            ids_vip.add(item["id"])
            vip_n += 1
            if item["score"] >= 8 and MAKE_WEBHOOK_URL:
                try:
                    requests.post(MAKE_WEBHOOK_URL, json={
                        "nombre": item["nombre"][:80],
                        "precio": str(round(item["precio"])),
                        "descuento": str(round(item["descuento"] * 100)),
                        "thumbnail": item.get("thumbnail", ""),
                        "link": item["url"], "score": item["score"]
                    }, timeout=10)
                except Exception:
                    pass
            time.sleep(5)

    # Esperar 3 minutos antes de publicar en free (ventaja de tiempo real)
    if vip_n > 0:
        logger.info("[GITHUB] Esperando 3 min antes de publicar en free...")
        time.sleep(180)

    # Free: top MAX_ALERTAS_FREE con score >= SCORE_MIN_FREE
    free_candidatos = [x for x in unicos if x["score"] >= SCORE_MIN_FREE][:MAX_ALERTAS_FREE]
    for item in free_candidatos:
        mid = enviar(CHANNEL_FREE_ID, msg_free(item))
        if mid:
            if item["id"] not in ids_vip:
                guardar_alerta_db(item["id"], item["score"], "free", item["precio"], item["descuento"])
            free_n += 1
            time.sleep(6)

    # Si no hubo alertas free, publicar resumen de mejores
    if free_n == 0 and hora_mx.hour in (12, 19) and unicos:
        top = unicos[:5]
        titulo = "Mejores precios de la tarde" if hora_mx.hour >= 15 else "Mejores precios de la manana"
        msg = "📋 *" + titulo + " - DropNode MX*\n\n"
        msg += "_Nuestro equipo reviso miles de productos. Estos destacan:_\n\n"
        for i, it in enumerate(top, 1):
            lnk = link_ml(it["url"], it["id"])
            d   = it["descuento"] * 100
            ln  = str(i) + ". 🔥 *[" + it["nombre"][:50] + "](" + lnk + ")*\n"
            ln += "   *$" + "{:,.0f}".format(it["precio"]) + " MXN*"
            if d >= 10: ln += " (−" + "{:.0f}".format(d) + "%)"
            if it.get("tiene_cupon"): ln += " 🎟️"
            msg += ln + "\n\n"
        if LAUNCHPASS_LINK:
            msg += "🔒 _Los VIP los vieron primero con analisis completo._\n_" + LAUNCHPASS_LINK + "_"
        enviar(CHANNEL_FREE_ID, msg)
        free_n += 1

    logger.info("[GITHUB v5] Fin - VIP:" + str(vip_n) + " Free:" + str(free_n))


if __name__ == "__main__":
    main()