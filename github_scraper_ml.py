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

SUPABASE_URL    = os.environ["SUPABASE_URL"]
SUPABASE_KEY    = os.environ["SUPABASE_KEY"]
TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
CHANNEL_FREE_ID = int(os.environ["CHANNEL_FREE_ID"])
CHANNEL_VIP_ID  = int(os.environ["CHANNEL_VIP_ID"])
ML_AFFILIATE_ID = os.environ.get("ML_AFFILIATE_ID", "marcodurzo")
LAUNCHPASS_LINK = os.environ.get("LAUNCHPASS_LINK", "")
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL", "")

TZ_MEXICO = timezone(timedelta(hours=-6))
db = create_client(SUPABASE_URL, SUPABASE_KEY)
TELEGRAM_API = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

UMBRAL_VIP = 0.25
UMBRAL_FREE = 0.12

PAGINAS = [
    {"url": "https://www.mercadolibre.com.mx/ofertas", "nombre": "Ofertas", "emoji": "🔥"},
    {"url": "https://listado.mercadolibre.com.mx/celulares-smartphones/", "nombre": "Celulares", "emoji": "📱"},
    {"url": "https://listado.mercadolibre.com.mx/computacion/", "nombre": "Computacion", "emoji": "💻"},
    {"url": "https://listado.mercadolibre.com.mx/electronica-audio-video/", "nombre": "Electronica", "emoji": "🔌"},
    {"url": "https://listado.mercadolibre.com.mx/televisores/", "nombre": "Televisores", "emoji": "📺"},
    {"url": "https://listado.mercadolibre.com.mx/videojuegos/", "nombre": "Videojuegos", "emoji": "🎮"},
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Script de extraccion con diagnostico y multiples estrategias
JS_EXTRACT = """
() => {
    var info = {
        title: document.title,
        url: window.location.href,
        bodyLength: document.body ? document.body.innerHTML.length : 0,
        selectors: {}
    };

    // Diagnostico: contar elementos por selector
    var testSelectors = [
        'li.ui-search-layout__item',
        '.ui-search-layout__item',
        '[class*="ui-search-layout"]',
        '.poly-card',
        '[class*="poly-card"]',
        '.andes-card',
        'article',
        '[data-testid*="product"]',
        '[data-testid*="result"]',
        '.promotion-item',
        '[class*="result"]',
        '[class*="item--"]',
        'li[class]',
        '.ui-search-results li'
    ];

    for (var si = 0; si < testSelectors.length; si++) {
        var count = document.querySelectorAll(testSelectors[si]).length;
        if (count > 0) {
            info.selectors[testSelectors[si]] = count;
        }
    }

    // Intentar extraer con el selector que tenga mas elementos
    var bestSelector = null;
    var bestCount = 0;
    var selectorKeys = Object.keys(info.selectors);
    for (var ki = 0; ki < selectorKeys.length; ki++) {
        var key = selectorKeys[ki];
        if (info.selectors[key] > bestCount) {
            bestCount = info.selectors[key];
            bestSelector = key;
        }
    }

    var productos = [];
    if (bestSelector) {
        var cards = document.querySelectorAll(bestSelector);
        for (var ci = 0; ci < Math.min(cards.length, 30); ci++) {
            try {
                var card = cards[ci];
                var html = card.innerHTML;

                // Extraer precio - buscar numeros grandes en el HTML
                var precioMatch = html.match(/(\d{2,6})(?:,(\d{2,3}))?(?:\s*<\/span>|\s*MXN)/);
                var precio = 0;
                if (precioMatch) {
                    precio = parseFloat(precioMatch[1].replace(/,/g, "") + (precioMatch[2] ? "." + precioMatch[2] : ""));
                }

                // Buscar en texto de elementos de precio conocidos
                var precioEls = card.querySelectorAll('[class*="price"], [class*="precio"], [class*="amount"]');
                for (var pi = 0; pi < precioEls.length; pi++) {
                    var txt = precioEls[pi].textContent.replace(/[^0-9]/g, "");
                    if (txt.length >= 3 && txt.length <= 7) {
                        var p = parseFloat(txt);
                        if (p > 50 && p < 999999) {
                            precio = p;
                            break;
                        }
                    }
                }

                // Titulo
                var tituloEl = card.querySelector('[class*="title"], h2, h3, [class*="name"]');
                var titulo = tituloEl ? tituloEl.textContent.trim() : "";

                // Precio original (tachado)
                var origEl = card.querySelector('s, del, [class*="original"], [class*="regular"], [class*="before"]');
                var orig = 0;
                if (origEl) {
                    var origTxt = origEl.textContent.replace(/[^0-9]/g, "");
                    if (origTxt.length >= 3) {
                        orig = parseFloat(origTxt);
                    }
                }

                // Link
                var linkEl = card.querySelector("a[href]");
                var link = linkEl ? linkEl.href : "";

                // Imagen
                var imgEl = card.querySelector("img");
                var img = imgEl ? (imgEl.src || imgEl.getAttribute("data-src") || "") : "";

                // ID
                var idMatch = link.match(/MLM[0-9]+/);
                var id = idMatch ? idMatch[0] : ("item_" + ci);

                if (titulo && titulo.length > 5 && precio > 50 && link && link.includes("mercadolibre")) {
                    productos.push({
                        id: id,
                        title: titulo.substring(0, 100),
                        price: precio,
                        original_price: orig > precio ? orig : 0,
                        permalink: link,
                        thumbnail: img,
                        available_quantity: 10
                    });
                }
            } catch (e) {}
        }
    }

    return {diagnostico: info, productos: productos};
}
"""


def scrape_pagina(page, pagina):
    productos = []
    try:
        logger.info("[PW] Cargando: " + pagina["nombre"])
        page.goto(pagina["url"], wait_until="domcontentloaded", timeout=30000)
        # Esperar que cargue contenido dinamico
        time.sleep(random.uniform(5, 8))

        resultado = page.evaluate(JS_EXTRACT)

        # Mostrar diagnostico
        diag = resultado.get("diagnostico", {})
        logger.info("[PW] Titulo: " + str(diag.get("title", "?"))[:60])
        logger.info("[PW] HTML length: " + str(diag.get("bodyLength", 0)))
        selectores = diag.get("selectors", {})
        if selectores:
            logger.info("[PW] Selectores encontrados: " + str(selectores))
        else:
            logger.warning("[PW] NINGUN selector encontro elementos - posible CAPTCHA o bloqueo")

        prods = resultado.get("productos", [])
        logger.info("[PW] " + pagina["nombre"] + ": " + str(len(prods)) + " productos")
        return prods

    except Exception as e:
        logger.error("[PW] Error en " + pagina["nombre"] + ": " + str(e))
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
        primer = datetime.fromisoformat(regs[0]["timestamp"].replace("Z", ""))
        dias = (datetime.utcnow() - primer).days + 1
        min_p = min(precios)
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


def calcular_score(descuento, stock, precio):
    s = 0.0
    if descuento >= 0.60:
        s += 3.0
    elif descuento >= 0.40:
        s += 2.5
    elif descuento >= 0.25:
        s += 1.8
    elif descuento >= 0.12:
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
    return min(10, round(s))


def msg_vip(item):
    nombre = item["nombre"][:65]
    precio = item["precio"]
    precio_orig = item["precio_orig"]
    desc = item["descuento"] * 100
    stock = item["stock"]
    lnk = link_ml(item["url"], item["id"])
    score = item["score"]
    stats = item.get("stats", {})
    emoji = item["categoria"]["emoji"]
    cat = item["categoria"]["nombre"]
    hora = datetime.now(TZ_MEXICO).strftime("%H:%M:%S")
    if score >= 8:
        icono = "🚨"
        etiqueta = "ERROR DE PRECIO"
    elif score >= 6:
        icono = "🔥"
        etiqueta = "OFERTA AGRESIVA"
    else:
        icono = "⚡"
        etiqueta = "DESCUENTO REAL"
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
    m += "Precio original:  $" + "{:,.0f}".format(precio_orig) + " MXN\n"
    m += "Descuento real:  *-" + "{:.0f}".format(desc) + "%*\n"
    if stats.get("es_minimo") and stats.get("dias", 0) >= 7:
        m += "\n*Precio mas bajo en " + str(stats["dias"]) + " dias*\n"
    if stats.get("avg") and precio < stats["avg"] * 0.90:
        m += "$" + "{:,.0f}".format(stats["avg"] - precio) + " menos que el promedio\n"
    m += "\n" + stock_txt + "\n"
    if desc >= 30 or stock <= 3:
        m += "_Oferta podria terminar pronto_\n"
    m += "\nScore: " + str(score) + "/10\n\n"
    m += "[COMPRAR AHORA](" + lnk + ")\n\n"
    m += "_Reventa estimada: $" + "{:,.0f}".format(rl) + " - $" + "{:,.0f}".format(rh) + " MXN_\n"
    m += "_" + hora + " hora MX_"
    return m


def msg_free(item):
    nombre = item["nombre"][:60]
    precio = item["precio"]
    precio_orig = item["precio_orig"]
    desc = item["descuento"] * 100
    stock = item["stock"]
    lnk = link_ml(item["url"], item["id"])
    stats = item.get("stats", {})
    emoji = item["categoria"]["emoji"]
    score = item["score"]
    if score >= 8:
        icono = "🚨"
    elif score >= 6:
        icono = "🔥"
    else:
        icono = "⚡"
    m = icono + " *DESCUENTO REAL*  " + emoji + "\n\n"
    m += "*" + nombre + "*\n\n"
    m += "*$" + "{:,.0f}".format(precio) + " MXN* (-" + "{:.0f}".format(desc) + "%)\n"
    m += "Ref: $" + "{:,.0f}".format(precio_orig) + " MXN\n"
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
        item_id = str(prod_raw.get("id", ""))
        nombre = str(prod_raw.get("title", ""))[:80]
        precio = float(prod_raw.get("price", 0))
        precio_o = prod_raw.get("original_price")
        precio_o = float(precio_o) if precio_o else 0
        permalink = str(prod_raw.get("permalink", ""))
        stock = int(prod_raw.get("available_quantity", 10))
        thumb = str(prod_raw.get("thumbnail", ""))
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
        score = calcular_score(descuento, stock, precio)
        stats = get_stats(pid, precio)
        return {
            "id": item_id, "pid": pid, "nombre": nombre,
            "precio": precio, "precio_orig": precio_o or precio,
            "descuento": descuento, "stock": stock,
            "url": permalink, "thumbnail": thumb,
            "categoria": categoria, "score": score, "stats": stats
        }
    except Exception:
        return None


def main():
    hora_mx = datetime.now(TZ_MEXICO)
    logger.info("[GITHUB v4.1] " + hora_mx.strftime("%d/%m %H:%M") + " MX")
    if not (8 <= hora_mx.hour < 22):
        logger.info("[GITHUB] Fuera de horario")
        return

    alertas = []
    destacados = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu",
                  "--window-size=1366,768"]
        )
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale="es-MX",
            timezone_id="America/Mexico_City",
            viewport={"width": 1366, "height": 768},
            extra_http_headers={
                "Accept-Language": "es-MX,es;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
        )
        page = context.new_page()

        # Solo procesar primera pagina para diagnostico
        for pagina in PAGINAS[:2]:
            prods_raw = scrape_pagina(page, pagina)
            cat = {"nombre": pagina["nombre"], "emoji": pagina["emoji"]}
            mejor = None
            mejor_sc = -1
            for prod_raw in prods_raw[:25]:
                item = procesar(prod_raw, cat)
                if not item:
                    continue
                if item["score"] > mejor_sc:
                    mejor_sc = item["score"]
                    mejor = item
                if item["descuento"] >= UMBRAL_FREE:
                    alertas.append(item)
            if mejor:
                destacados.append(mejor)
            time.sleep(random.uniform(3, 5))

        # Si primer intento funciono, procesar el resto
        if len(alertas) > 0 or len(destacados) > 0:
            for pagina in PAGINAS[2:]:
                prods_raw = scrape_pagina(page, pagina)
                cat = {"nombre": pagina["nombre"], "emoji": pagina["emoji"]}
                mejor = None
                mejor_sc = -1
                for prod_raw in prods_raw[:25]:
                    item = procesar(prod_raw, cat)
                    if not item:
                        continue
                    if item["score"] > mejor_sc:
                        mejor_sc = item["score"]
                        mejor = item
                    if item["descuento"] >= UMBRAL_FREE:
                        alertas.append(item)
                if mejor:
                    destacados.append(mejor)
                time.sleep(random.uniform(3, 5))

        browser.close()

    alertas.sort(key=lambda x: x["score"], reverse=True)
    vip_n = 0
    free_n = 0

    for item in alertas[:10]:
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
        top = sorted(destacados, key=lambda x: x["score"], reverse=True)[:5]
        titulo = "Mejores precios de la tarde" if hora_mx.hour >= 15 else "Mejores precios de la manana"
        msg = "📋 *" + titulo + " - DropNode MX*\n\n"
        msg += "_Nuestro equipo reviso miles de productos. Estos destacan:_\n\n"
        for i, it in enumerate(top, 1):
            lnk = link_ml(it["url"], it["id"])
            d = it["descuento"] * 100
            linea = str(i) + ". " + it["categoria"]["emoji"] + " *[" + it["nombre"][:50] + "](" + lnk + ")*\n"
            linea += "   *$" + "{:,.0f}".format(it["precio"]) + " MXN*"
            if d >= 10:
                linea += " (-" + "{:.0f}".format(d) + "%)"
            msg += linea + "\n\n"
        if LAUNCHPASS_LINK:
            msg += "🔒 _Errores de precio van al VIP primero._\n_" + LAUNCHPASS_LINK + "_"
        enviar(CHANNEL_FREE_ID, msg)
        free_n += 1

    logger.info("[GITHUB] Fin - VIP:" + str(vip_n) + " Free:" + str(free_n)
                + " | Alertas:" + str(len(alertas)) + " Destacados:" + str(len(destacados)))


if __name__ == "__main__":
    main()