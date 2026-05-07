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

logger.info("[CONFIG] Supabase: " + SUPABASE_URL[:40])

TZ_MEXICO    = timezone(timedelta(hours=-6))
db           = create_client(SUPABASE_URL, SUPABASE_KEY)
TELEGRAM_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

UMBRAL_VIP  = 0.20
UMBRAL_FREE = 0.10

PAGINAS = [
    {"url": "https://www.mercadolibre.com.mx/ofertas",         "nombre": "Ofertas p1", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=2",  "nombre": "Ofertas p2", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=3",  "nombre": "Ofertas p3", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=4",  "nombre": "Ofertas p4", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=5",  "nombre": "Ofertas p5", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=6",  "nombre": "Ofertas p6", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/cupon-de-descuento", "nombre": "Cupones ML", "emoji": "🎟️"},
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
    if (cards.length === 0) cards = document.querySelectorAll('[class*="promotion-item"]');

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

            var origEl = card.querySelector('s, del, [class*="original"], [class*="regular"]');
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

            // Detectar cupones
            var cupon_texto = "";
            var cupon_monto = 0;
            var cupon_porcentaje = 0;

            var cardHtml = card.innerHTML.toLowerCase();

            // Buscar textos de cupon en el HTML de la tarjeta
            var cuponKeywords = ["cupon", "cupon", "coupon", "descuento adicional", "con cupon", "codigo"];
            var tieneCupon = false;
            for (var ki = 0; ki < cuponKeywords.length; ki++) {
                if (cardHtml.indexOf(cuponKeywords[ki]) >= 0) {
                    tieneCupon = true;
                    break;
                }
            }

            if (tieneCupon) {
                // Buscar monto del cupon (ej: "Cupon $500")
                var montoMatch = cardHtml.match(/cup[o|o]n[^0-9]*([0-9]{2,5})/);
                if (montoMatch) cupon_monto = parseFloat(montoMatch[1]);

                // Buscar porcentaje del cupon (ej: "10% de descuento adicional")
                var pctMatch = cardHtml.match(/([0-9]{1,2})%[^>]*(?:cup|desc|adic)/);
                if (!pctMatch) pctMatch = cardHtml.match(/cup[^0-9]*([0-9]{1,2})%/);
                if (pctMatch) cupon_porcentaje = parseFloat(pctMatch[1]);

                // Texto visible del cupon
                var cuponEls = card.querySelectorAll('[class*="coupon"], [class*="cupon"], [class*="discount-label"]');
                for (var ci = 0; ci < cuponEls.length; ci++) {
                    var ct = cuponEls[ci].textContent.trim();
                    if (ct.length > 2 && ct.length < 50) { cupon_texto = ct; break; }
                }
                if (!cupon_texto) cupon_texto = "Cupon disponible";
            }

            // Precio efectivo con cupon
            var precio_con_cupon = precio;
            if (cupon_monto > 0 && cupon_monto < precio) {
                precio_con_cupon = precio - cupon_monto;
            } else if (cupon_porcentaje > 0) {
                precio_con_cupon = precio * (1 - cupon_porcentaje / 100);
            }

            if (titulo && titulo.length > 5 && precio > 50 && link.includes("mercadolibre")) {
                productos.push({
                    id: id,
                    title: titulo.substring(0, 100),
                    price: precio,
                    original_price: orig > precio ? orig : 0,
                    permalink: link,
                    thumbnail: img,
                    available_quantity: 10,
                    cupon_texto: cupon_texto,
                    cupon_monto: cupon_monto,
                    cupon_porcentaje: cupon_porcentaje,
                    precio_con_cupon: precio_con_cupon
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
        con_cupon = sum(1 for x in items if x.get("cupon_monto", 0) > 0 or x.get("cupon_porcentaje", 0) > 0)
        logger.info("[PW] " + pagina["nombre"] + ": " + str(len(items)) + " productos (" + str(con_cupon) + " con cupon)")
        return items or []
    except Exception as e:
        logger.error("[PW] " + str(e))
        return []


def upsert_prod(url, nombre, categoria, sku):
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
        logger.error("[DB] " + str(e))
        return None


def guardar_precio(pid, precio, precio_orig, stock):
    if not pid:
        return
    try:
        db.table("historial_precios").insert({
            "producto_id": pid, "precio": precio,
            "precio_original": precio_orig, "stock": stock,
            "disponible": stock > 0,
            "timestamp": datetime.utcnow().isoformat()
        }).execute()
    except Exception:
        pass


def alerta_hoy(pid):
    if not pid:
        return False
    try:
        desde = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
        r = db.table("alertas_enviadas").select("id").eq("producto_id", pid).gte("timestamp", desde).execute()
        return len(r.data) > 0
    except Exception:
        return False


def guardar_alerta(pid, score, canal, precio, descuento):
    if not pid:
        return
    try:
        db.table("alertas_enviadas").insert({
            "producto_id": pid, "heat_score": score, "canal": canal,
            "precio_alerta": precio, "descuento_real": descuento,
            "clicks": 0, "timestamp": datetime.utcnow().isoformat()
        }).execute()
    except Exception:
        pass


def get_minimo(pid):
    try:
        desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
        r = db.table("historial_precios").select("precio").eq("producto_id", pid).gte("timestamp", desde).eq("disponible", True).order("precio").limit(1).execute()
        return float(r.data[0]["precio"]) if r.data else None
    except Exception:
        return None


def get_stats(pid, precio_actual):
    try:
        desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
        r = db.table("historial_precios").select("precio, timestamp").eq("producto_id", pid).gte("timestamp", desde).eq("disponible", True).order("timestamp").execute()
        regs = r.data or []
        if len(regs) < 5:
            return {}
        precios = [float(x["precio"]) for x in regs]
        primer  = datetime.fromisoformat(regs[0]["timestamp"].replace("Z", ""))
        dias    = (datetime.utcnow() - primer).days + 1
        min_p   = min(precios)
        return {
            "min": min_p, "max": max(precios),
            "avg": sum(precios) / len(precios), "dias": dias,
            "es_minimo": precio_actual <= min_p * 1.02 and dias >= 7
        }
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


def calcular_score(descuento, stock, precio, tiene_cupon=False):
    s = 0.0
    if descuento >= 0.60:
        s += 3.0
    elif descuento >= 0.40:
        s += 2.5
    elif descuento >= 0.25:
        s += 1.8
    elif descuento >= 0.10:
        s += 1.0
    if stock == 1:
        s += 2.0
    elif stock <= 3:
        s += 1.8
    elif stock <= 10:
        s += 1.0
    if precio >= 5000:
        s += 1.5
    elif precio >= 2000:
        s += 1.0
    if tiene_cupon:
        s += 1.0
    return min(10, round(s))


def msg_vip(item):
    nombre      = item["nombre"][:65]
    precio      = item["precio"]
    precio_orig = item["precio_orig"]
    desc        = item["descuento"] * 100
    stock       = item["stock"]
    lnk         = link_ml(item["url"], item["id"])
    score       = item["score"]
    stats       = item.get("stats", {})
    emoji       = item["categoria"]["emoji"]
    cat         = item["categoria"]["nombre"]
    hora        = datetime.now(TZ_MEXICO).strftime("%H:%M:%S")
    cupon_txt   = item.get("cupon_texto", "")
    cupon_monto = item.get("cupon_monto", 0)
    cupon_pct   = item.get("cupon_porcentaje", 0)
    p_cupon     = item.get("precio_con_cupon", precio)

    if score >= 8:
        icono = "🚨"
        etiqueta = "ERROR DE PRECIO"
    elif score >= 6:
        icono = "🔥"
        etiqueta = "OFERTA AGRESIVA"
    else:
        icono = "⚡"
        etiqueta = "DESCUENTO REAL"

    if cupon_txt:
        icono = "🎟️"
        etiqueta = "OFERTA + CUPON"

    if stock == 1:
        stock_txt = "*ULTIMA UNIDAD*"
    elif stock <= 3:
        stock_txt = "*Solo " + str(stock) + " unidades*"
    elif stock <= 10:
        stock_txt = str(stock) + " unidades"
    else:
        stock_txt = "Stock disponible"

    rl = precio_orig * 0.80
    rh = precio_orig * 0.92

    m = icono + " *" + etiqueta + "*  " + emoji + " " + cat + "\n\n"
    m += "*" + nombre + "*\n\n"
    m += "Precio ahora:    *$" + "{:,.0f}".format(precio) + " MXN*\n"
    if precio_orig > precio:
        m += "Precio original:  $" + "{:,.0f}".format(precio_orig) + " MXN\n"
        m += "Descuento:       *-" + "{:.0f}".format(desc) + "%*\n"

    if cupon_txt:
        m += "\n🎟️ *CUPON DISPONIBLE*\n"
        if cupon_monto > 0:
            m += "Ahorro adicional con cupon: *-$" + "{:,.0f}".format(cupon_monto) + " MXN*\n"
            m += "Precio final con cupon:     *$" + "{:,.0f}".format(p_cupon) + " MXN*\n"
        elif cupon_pct > 0:
            m += "Descuento adicional: *-" + str(cupon_pct) + "%*\n"
            m += "Precio final con cupon: *$" + "{:,.0f}".format(p_cupon) + " MXN*\n"
        else:
            m += "_" + cupon_txt + "_\n"

    if stats.get("es_minimo") and stats.get("dias", 0) >= 7:
        m += "\n*Precio mas bajo en " + str(stats["dias"]) + " dias*\n"
    if stats.get("avg") and precio < stats["avg"] * 0.90:
        m += "$" + "{:,.0f}".format(stats["avg"] - precio) + " menos que el promedio\n"

    m += "\n" + stock_txt + "\n"
    if desc >= 30 or stock <= 3:
        m += "_Oferta podria terminar pronto_\n"

    m += "\nScore: " + str(score) + "/10\n\n"
    m += "[COMPRAR AHORA](" + lnk + ")\n\n"
    if precio_orig > precio:
        m += "_Reventa estimada: $" + "{:,.0f}".format(rl) + " - $" + "{:,.0f}".format(rh) + " MXN_\n"
    m += "_" + hora + " hora MX_"
    return m


def msg_free(item):
    nombre      = item["nombre"][:60]
    precio      = item["precio"]
    precio_orig = item["precio_orig"]
    desc        = item["descuento"] * 100
    stock       = item["stock"]
    lnk         = link_ml(item["url"], item["id"])
    stats       = item.get("stats", {})
    emoji       = item["categoria"]["emoji"]
    score       = item["score"]
    cupon_txt   = item.get("cupon_texto", "")
    cupon_monto = item.get("cupon_monto", 0)
    p_cupon     = item.get("precio_con_cupon", precio)

    if cupon_txt:
        icono = "🎟️"
    elif score >= 8:
        icono = "🚨"
    elif score >= 6:
        icono = "🔥"
    else:
        icono = "⚡"

    m = icono + " *DESCUENTO REAL*  " + emoji + "\n\n"
    m += "*" + nombre + "*\n\n"
    m += "*$" + "{:,.0f}".format(precio) + " MXN*"
    if desc >= 5:
        m += " (-" + "{:.0f}".format(desc) + "%)"
    m += "\n"
    if precio_orig > precio:
        m += "Ref: $" + "{:,.0f}".format(precio_orig) + " MXN\n"

    if cupon_txt and cupon_monto > 0:
        m += "\n🎟️ *Con cupon: $" + "{:,.0f}".format(p_cupon) + " MXN* (-$" + "{:,.0f}".format(cupon_monto) + " adicional)\n"

    if stats.get("es_minimo") and stats.get("dias", 0) >= 7:
        m += "\n*Precio mas bajo en " + str(stats["dias"]) + " dias*\n"
    if stock <= 5:
        m += "*Solo " + str(stock) + " unidades*\n"

    m += "\n[Ver oferta](" + lnk + ")\n\n"
    m += "_Canal VIP: alertas primero + analisis de reventa._\n"
    if LAUNCHPASS_LINK:
        m += "_" + LAUNCHPASS_LINK + "_"
    return m


def procesar(prod_raw, categoria):
    try:
        item_id     = str(prod_raw.get("id", ""))
        nombre      = str(prod_raw.get("title", ""))[:80]
        precio      = float(prod_raw.get("price", 0))
        precio_o    = prod_raw.get("original_price")
        precio_o    = float(precio_o) if precio_o else 0
        permalink   = str(prod_raw.get("permalink", ""))
        stock       = int(prod_raw.get("available_quantity", 10))
        thumb       = str(prod_raw.get("thumbnail", ""))
        cupon_txt   = str(prod_raw.get("cupon_texto", ""))
        cupon_monto = float(prod_raw.get("cupon_monto", 0))
        cupon_pct   = float(prod_raw.get("cupon_porcentaje", 0))
        p_cupon     = float(prod_raw.get("precio_con_cupon", precio))
        tiene_cupon = cupon_txt != "" or cupon_monto > 0 or cupon_pct > 0

        if not nombre or precio <= 0 or not permalink:
            return None

        pid = upsert_prod(permalink, nombre, categoria["nombre"], item_id)
        guardar_precio(pid, precio, precio_o or precio, stock)
        if alerta_hoy(pid):
            return None

        descuento = 0.0
        if precio_o and precio_o > precio:
            descuento = (precio_o - precio) / precio_o
        else:
            minimo = get_minimo(pid)
            if minimo and precio < minimo * 0.88:
                descuento = (minimo - precio) / minimo
                precio_o = minimo

        # Si hay cupon, calcular descuento efectivo total
        if tiene_cupon and p_cupon < precio and precio > 0:
            descuento_cupon = (precio - p_cupon) / precio
            descuento = max(descuento, descuento_cupon)

        score = calcular_score(descuento, stock, precio, tiene_cupon)
        stats = get_stats(pid, precio)

        return {
            "id": item_id, "pid": pid, "nombre": nombre,
            "precio": precio, "precio_orig": precio_o or precio,
            "descuento": descuento, "stock": stock,
            "url": permalink, "thumbnail": thumb,
            "categoria": categoria, "score": score, "stats": stats,
            "cupon_texto": cupon_txt, "cupon_monto": cupon_monto,
            "cupon_porcentaje": cupon_pct, "precio_con_cupon": p_cupon,
            "tiene_cupon": tiene_cupon
        }
    except Exception:
        return None


def main():
    hora_mx = datetime.now(TZ_MEXICO)
    logger.info("[GITHUB v4.3] " + hora_mx.strftime("%d/%m %H:%M") + " MX")
    if not (8 <= hora_mx.hour < 22):
        logger.info("[GITHUB] Fuera de horario")
        return

    alertas    = []
    destacados = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale="es-MX",
            timezone_id="America/Mexico_City",
            viewport={"width": 1366, "height": 768}
        )
        page = context.new_page()

        for pagina in PAGINAS:
            prods_raw = scrape_pagina(page, pagina)
            cat = {"nombre": pagina["nombre"], "emoji": pagina["emoji"]}
            mejor    = None
            mejor_sc = -1
            for prod_raw in prods_raw:
                item = procesar(prod_raw, cat)
                if not item:
                    continue
                if item["score"] > mejor_sc:
                    mejor_sc = item["score"]
                    mejor    = item
                if item["descuento"] >= UMBRAL_FREE or item["tiene_cupon"]:
                    alertas.append(item)
            if mejor:
                destacados.append(mejor)
            time.sleep(random.uniform(2, 4))

        browser.close()

    seen   = set()
    unicos = []
    for a in alertas:
        if a["id"] not in seen:
            seen.add(a["id"])
            unicos.append(a)
    alertas = sorted(unicos, key=lambda x: x["score"], reverse=True)

    logger.info("[GITHUB] Alertas unicas: " + str(len(alertas)))

    vip_n  = 0
    free_n = 0

    for item in alertas[:15]:
        if item["descuento"] >= UMBRAL_VIP and item["score"] >= 6:
            mid = enviar(CHANNEL_VIP_ID, msg_vip(item))
            if mid:
                guardar_alerta(item["pid"], item["score"], "vip", item["precio"], item["descuento"])
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
                time.sleep(4)
        if item["descuento"] >= UMBRAL_FREE and item["score"] >= 3:
            mid = enviar(CHANNEL_FREE_ID, msg_free(item))
            if mid:
                if item["descuento"] < UMBRAL_VIP:
                    guardar_alerta(item["pid"], item["score"], "free", item["precio"], item["descuento"])
                free_n += 1
                time.sleep(5)

    if free_n == 0 and hora_mx.hour in (12, 19) and destacados:
        top    = sorted(destacados, key=lambda x: x["score"], reverse=True)[:5]
        titulo = "Mejores precios de la tarde" if hora_mx.hour >= 15 else "Mejores precios de la manana"
        msg    = "📋 *" + titulo + " - DropNode MX*\n\n"
        msg   += "_Nuestro equipo reviso miles de productos. Estos destacan:_\n\n"
        for i, it in enumerate(top, 1):
            lnk   = link_ml(it["url"], it["id"])
            d     = it["descuento"] * 100
            linea = str(i) + ". " + it["categoria"]["emoji"] + " *[" + it["nombre"][:50] + "](" + lnk + ")*\n"
            linea += "   *$" + "{:,.0f}".format(it["precio"]) + " MXN*"
            if d >= 10:
                linea += " (-" + "{:.0f}".format(d) + "%)"
            if it.get("tiene_cupon"):
                linea += " 🎟️"
            msg += linea + "\n\n"
        if LAUNCHPASS_LINK:
            msg += "🔒 _Errores de precio van al VIP primero._\n_" + LAUNCHPASS_LINK + "_"
        enviar(CHANNEL_FREE_ID, msg)
        free_n += 1

    logger.info("[GITHUB] Fin - VIP:" + str(vip_n) + " Free:" + str(free_n))


if __name__ == "__main__":
    main()