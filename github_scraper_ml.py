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

db = None
try:
    db = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("[DB] Conexion OK")
except Exception as e:
    logger.warning("[DB] Sin historial: " + str(e))

HORA_FREE_INICIO  = 8
HORA_FREE_FIN     = 23
HORA_VIP_INICIO   = 7

SCORE_EXCLUSIVO_VIP = 7
SCORE_MIN_FREE      = 5
DESCUENTO_HOT       = 0.40
MAX_VIP_POR_RUN     = 12
MAX_FREE_POR_RUN    = 4
VENTAJA_MINUTOS     = 3

PAGINAS = [
    {"url": "https://www.mercadolibre.com.mx/ofertas",        "nombre": "Ofertas p1", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=2", "nombre": "Ofertas p2", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=3", "nombre": "Ofertas p3", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=4", "nombre": "Ofertas p4", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=5", "nombre": "Ofertas p5", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=6", "nombre": "Ofertas p6", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=7", "nombre": "Ofertas p7", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/ofertas?page=8", "nombre": "Ofertas p8", "emoji": "🔥"},
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

    function parsearPrecioML(card, selector) {
        // ML muestra precios con fraccion y centavos separados
        // Ej: <span class="fraction">298</span><span class="cents">80</span>
        // Hay que leerlos por separado para no confundir $298.80 con $29,880
        var fraccionEl = card.querySelector(
            '[class*="price__fraction"], [class*="amount__fraction"], [class*="price-tag-fraction"]'
        );
        if (fraccionEl) {
            var fraccionTxt = fraccionEl.textContent.replace(/[^0-9]/g, "");
            var centavosEl = card.querySelector(
                '[class*="price__cents"], [class*="amount__cents"], [class*="price-tag-cents"]'
            );
            var centavosTxt = centavosEl ? centavosEl.textContent.replace(/[^0-9]/g, "").substring(0, 2) : "00";
            if (fraccionTxt) {
                return parseFloat(fraccionTxt + "." + centavosTxt);
            }
        }
        // Fallback: buscar en elementos de precio pero separar fraccion de centavos
        var priceEls = card.querySelectorAll('[class*="price"], [class*="amount"]');
        for (var pi = 0; pi < priceEls.length; pi++) {
            // Obtener solo el texto directo del elemento (sin hijos)
            var childNodes = priceEls[pi].childNodes;
            var textoDirecto = "";
            for (var ni = 0; ni < childNodes.length; ni++) {
                if (childNodes[ni].nodeType === 3) {
                    textoDirecto += childNodes[ni].textContent;
                }
            }
            var numeros = textoDirecto.replace(/[^0-9.,]/g, "").trim();
            if (numeros.length >= 2 && numeros.length <= 10) {
                // Convertir formato mexicano: 1,299.00 o 1299
                numeros = numeros.replace(/,([0-9]{3})/g, "$1").replace(",", ".");
                var p = parseFloat(numeros);
                if (p > 10 && p < 500000) return p;
            }
        }
        return 0;
    }

    for (var i = 0; i < cards.length; i++) {
        try {
            var card = cards[i];
            var tituloEl = card.querySelector('[class*="title"], h2, h3');
            var titulo = tituloEl ? tituloEl.textContent.trim() : "";

            var precio = parsearPrecioML(card, '[class*="price"]');

            // Precio original (tachado)
            var origEl = card.querySelector('s, del, [class*="original"], [class*="regular-price"]');
            var orig = 0;
            if (origEl) {
                var origFracEl = origEl.querySelector('[class*="fraction"]');
                if (origFracEl) {
                    var origFrac = origFracEl.textContent.replace(/[^0-9]/g, "");
                    if (origFrac) orig = parseFloat(origFrac);
                } else {
                    var ot = origEl.textContent.replace(/[^0-9.,]/g, "").replace(/,([0-9]{3})/g, "$1");
                    if (ot.length >= 2 && ot.length <= 8) orig = parseFloat(ot);
                }
            }

            var linkEl = card.querySelector("a[href]");
            var link = linkEl ? linkEl.href : "";
            var imgEl = card.querySelector("img");
            var img = imgEl ? (imgEl.src || imgEl.getAttribute("data-src") || "") : "";
            var idm = link.match(/MLM[0-9]+/);
            var id = idm ? idm[0] : ("item_" + i);

            var cardHtml = card.innerHTML.toLowerCase();
            var tieneCupon = cardHtml.indexOf("cup") >= 0 && cardHtml.indexOf("descuento") >= 0;
            var cuponMonto = 0;
            if (tieneCupon) {
                var cm = cardHtml.match(/cup[^0-9]*([0-9]{2,5})/);
                if (cm) cuponMonto = parseFloat(cm[1]);
            }

            if (titulo && titulo.length > 5 && precio > 10 && link.includes("mercadolibre")) {
                productos.push({
                    id: id, title: titulo.substring(0, 100),
                    price: precio,
                    original_price: (orig > precio && orig < precio * 10) ? orig : 0,
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
        return {"min": min_p, "max": max(precios),
                "avg": sum(precios) / len(precios), "dias": dias,
                "es_minimo": precio_actual <= min_p * 1.02 and dias >= 7}
    except Exception:
        return {}


# ── Telegram helpers ─────────────────────────────────────────

def tg_texto(chat_id, texto):
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


def tg_foto(chat_id, photo_url, caption):
    """Envia foto con caption. Si falla la foto, envia solo texto."""
    if not photo_url or not photo_url.startswith("http"):
        return tg_texto(chat_id, caption)
    try:
        r = requests.post(TELEGRAM_API + "/sendPhoto", json={
            "chat_id": chat_id,
            "photo": photo_url,
            "caption": caption[:1020],
            "parse_mode": "Markdown"
        }, timeout=20)
        d = r.json()
        if d.get("ok"):
            return d["result"]["message_id"]
        # Foto fallo (URL expirada, etc) — caer a texto
        return tg_texto(chat_id, caption)
    except Exception as e:
        logger.error("[TG foto] " + str(e))
        return tg_texto(chat_id, caption)


def tg_foto_mas_analisis(chat_id, photo_url, caption_corto, analisis):
    """
    VIP: foto con precio rapido, luego analisis completo separado.
    Se ve como ficha de producto profesional en el chat.
    """
    foto_ok = tg_foto(chat_id, photo_url, caption_corto)
    time.sleep(1)
    tg_texto(chat_id, analisis)
    return foto_ok


# ── Formateo de mensajes ──────────────────────────────────────

def link_ml(url, item_id):
    # Limpiar URL: quitar todo despues de ? o # para evitar URLs gigantes
    # que rompen el Markdown de Telegram
    url_limpia = url.split("?")[0].split("#")[0]
    # Solo agregar el parametro de afiliado
    return url_limpia + "?matt_tool=" + ML_AFFILIATE_ID


def calcular_score(descuento, stock, precio, tiene_cupon):
    s = 0.0
    if descuento >= 0.60: s += 4.0
    elif descuento >= 0.40: s += 3.5
    elif descuento >= 0.25: s += 3.0
    elif descuento >= 0.15: s += 2.0
    elif descuento >= 0.05: s += 1.0
    else: s += 0.2
    if stock == 1: s += 2.0
    elif stock <= 3: s += 1.8
    elif stock <= 10: s += 1.0
    if precio >= 8000: s += 1.5
    elif precio >= 3000: s += 1.0
    if tiene_cupon: s += 1.0
    return min(10, round(s))


def clasificar(item):
    score    = item["score"]
    desc     = item["descuento"]
    hora     = datetime.now(TZ_MEXICO).hour
    madrugada = hora < 8
    if desc >= DESCUENTO_HOT or score >= SCORE_EXCLUSIVO_VIP or madrugada:
        return "vip_exclusivo"
    elif score >= SCORE_MIN_FREE:
        return "compartido"
    elif score >= 3:
        return "vip_exclusivo"
    return "descartar"


def caption_vip(item):
    """Caption corto para la foto en VIP (max 1020 chars)."""
    nombre = item["nombre"][:50]
    precio = item["precio"]
    p_orig = item["precio_orig"]
    desc   = item["descuento"] * 100
    score  = item["score"]
    lnk    = link_ml(item["url"], item["id"])
    cupon  = item.get("tiene_cupon", False)
    c_monto = item.get("cupon_monto", 0)
    p_cupon = item.get("precio_con_cupon", precio)

    if score >= 8: icono = "🚨"
    elif item["descuento"] >= DESCUENTO_HOT: icono = "🔥"
    elif cupon: icono = "🎟️"
    else: icono = "⚡"

    c = icono + " *" + nombre + "*\n\n"
    c += "*$" + "{:,.0f}".format(precio) + " MXN*"
    if desc >= 5: c += " (−" + "{:.0f}".format(desc) + "%)"
    c += "\n"
    if p_orig > precio:
        c += "~~$" + "{:,.0f}".format(p_orig) + "~~\n"
    if cupon and c_monto > 0:
        c += "🎟️ Con cupon: *$" + "{:,.0f}".format(p_cupon) + " MXN*\n"
    c += "\n[COMPRAR AHORA](" + lnk + ")"
    return c


def analisis_vip(item, stats, es_exclusivo):
    """Analisis completo VIP como segundo mensaje."""
    nombre  = item["nombre"][:65]
    precio  = item["precio"]
    p_orig  = item["precio_orig"]
    desc    = item["descuento"] * 100
    stock   = item["stock"]
    score   = item["score"]
    hora    = datetime.now(TZ_MEXICO).strftime("%H:%M:%S")
    cupon   = item.get("tiene_cupon", False)
    c_monto = item.get("cupon_monto", 0)
    p_cupon = item.get("precio_con_cupon", precio)
    rl = p_orig * 0.80
    rh = p_orig * 0.92

    if es_exclusivo and desc >= 40: tag = "HOT DEAL — EXCLUSIVO VIP"
    elif es_exclusivo: tag = "ALERTA EXCLUSIVA VIP"
    else: tag = "ANALISIS VIP"

    if stock == 1: stxt = "*ULTIMA UNIDAD*"
    elif stock <= 3: stxt = "*Solo " + str(stock) + " unidades*"
    elif stock <= 10: stxt = str(stock) + " unidades"
    else: stxt = "Stock disponible"

    m = "*" + tag + "*\n\n"
    m += "*" + nombre + "*\n\n"
    m += "Precio ahora:    *$" + "{:,.0f}".format(precio) + " MXN*\n"
    if p_orig > precio:
        m += "Precio original:  $" + "{:,.0f}".format(p_orig) + " MXN\n"
        m += "Descuento real:  *-" + "{:.0f}".format(desc) + "%*\n"
    if cupon and c_monto > 0:
        m += "\n🎟️ *Con cupon: $" + "{:,.0f}".format(p_cupon) + " MXN* (−$" + "{:,.0f}".format(c_monto) + " adicional)\n"
    if stats.get("es_minimo") and stats.get("dias", 0) >= 7:
        m += "\n*Precio mas bajo en " + str(stats["dias"]) + " dias*\n"
    if stats.get("avg") and precio < stats["avg"] * 0.90:
        m += "$" + "{:,.0f}".format(stats["avg"] - precio) + " menos que el promedio historico\n"
    m += "\n" + stxt + "\n"
    if desc >= 30 or stock <= 3:
        m += "_Puede terminar pronto_\n"
    m += "\nScore: " + str(score) + "/10\n"
    if p_orig > precio:
        m += "_Reventa estimada: $" + "{:,.0f}".format(rl) + " - $" + "{:,.0f}".format(rh) + " MXN_\n"
    m += "_" + hora + " hora MX — DropNode VIP_"
    return m


def caption_free(item):
    """Caption para foto en canal free. Corto con CTA al VIP."""
    nombre  = item["nombre"][:50]
    precio  = item["precio"]
    p_orig  = item["precio_orig"]
    desc    = item["descuento"] * 100
    lnk     = link_ml(item["url"], item["id"])
    score   = item["score"]
    cupon   = item.get("tiene_cupon", False)
    c_monto = item.get("cupon_monto", 0)
    p_cupon = item.get("precio_con_cupon", precio)

    if score >= 7: icono = "🚨"
    elif score >= 5: icono = "🔥"
    elif cupon: icono = "🎟️"
    else: icono = "⚡"

    c = icono + " *" + nombre + "*\n\n"
    c += "*$" + "{:,.0f}".format(precio) + " MXN*"
    if desc >= 5: c += " (−" + "{:.0f}".format(desc) + "%)"
    c += "\n"
    if p_orig > precio:
        c += "~~$" + "{:,.0f}".format(p_orig) + "~~\n"
    if cupon and c_monto > 0:
        c += "🎟️ Con cupon: *$" + "{:,.0f}".format(p_cupon) + " MXN*\n"
    c += "\n[Ver oferta](" + lnk + ")\n\n"
    c += "_Los VIP la recibieron primero + reventa + historial._\n"
    c += "_VIP: " + LAUNCHPASS_LINK + "_"
    return c


# ── DB ────────────────────────────────────────────────────────

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
        # Validar precio razonable (entre $10 y $200,000 MXN)
        if precio > 200000 or precio < 10:
            return None
        descuento = 0.0
        if p_orig and p_orig > precio:
            descuento = (p_orig - precio) / p_orig
        if cupon and c_monto > 0:
            descuento = max(descuento, c_monto / precio)
        score = calcular_score(descuento, stock, precio, cupon)
        stats = get_stats_db(item_id, precio)
        return {
            "id": item_id, "nombre": nombre, "precio": precio,
            "precio_orig": p_orig or precio, "descuento": descuento,
            "stock": stock, "url": link, "thumbnail": thumb,
            "score": score, "stats": stats, "tiene_cupon": cupon,
            "cupon_monto": c_monto, "precio_con_cupon": p_cupon
        }
    except Exception:
        return None


# ── Main ──────────────────────────────────────────────────────

def main():
    hora_mx_actual = datetime.now(TZ_MEXICO)
    hora           = hora_mx_actual.hour
    logger.info("[GITHUB v5.2] " + hora_mx_actual.strftime("%d/%m %H:%M") + " MX")

    es_horario_free = HORA_FREE_INICIO <= hora < HORA_FREE_FIN
    es_madrugada    = hora < HORA_VIP_INICIO

    if es_madrugada:
        logger.info("[GITHUB] Madrugada — solo hot deals VIP")

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

    seen  = set()
    unicos = []
    for a in todos:
        if a["id"] not in seen and not alerta_hoy_db(a["id"]):
            seen.add(a["id"])
            unicos.append(a)
    unicos.sort(key=lambda x: x["score"], reverse=True)
    logger.info("[GITHUB] Productos unicos: " + str(len(unicos)))

    vip_n  = 0
    free_n = 0
    ids_vip = set()

    # VIP: foto + analisis completo
    for item in unicos:
        if vip_n >= MAX_VIP_POR_RUN:
            break
        tipo = clasificar(item)
        if tipo == "descartar":
            continue
        if es_madrugada and item["descuento"] < DESCUENTO_HOT:
            continue

        es_exclusivo = tipo == "vip_exclusivo"
        cap  = caption_vip(item)
        anal = analisis_vip(item, item.get("stats", {}), es_exclusivo)
        thumb = item.get("thumbnail", "")

        mid = tg_foto_mas_analisis(CHANNEL_VIP_ID, thumb, cap, anal)
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
                        "thumbnail": thumb,
                        "link": item["url"], "score": item["score"]
                    }, timeout=10)
                except Exception:
                    pass
            time.sleep(5)

    # Esperar ventaja antes del free
    if vip_n > 0 and es_horario_free:
        logger.info("[GITHUB] Esperando " + str(VENTAJA_MINUTOS) + " min...")
        time.sleep(VENTAJA_MINUTOS * 60)

    # Free: solo foto con caption corto
    if es_horario_free:
        candidatos = [
            x for x in unicos
            if x["score"] >= SCORE_MIN_FREE and clasificar(x) == "compartido"
        ][:MAX_FREE_POR_RUN]

        for item in candidatos:
            cap   = caption_free(item)
            thumb = item.get("thumbnail", "")
            mid   = tg_foto(CHANNEL_FREE_ID, thumb, cap)
            if mid:
                free_n += 1
                time.sleep(6)

        # Resumen a las 12 PM y 7 PM si no hubo alertas
        if free_n == 0 and hora in (12, 19) and unicos:
            top = unicos[:5]
            t   = "Mejores precios de la tarde" if hora >= 15 else "Mejores precios de la manana"
            msg = "📋 *" + t + " — DropNode MX*\n\n"
            msg += "_Nuestro equipo reviso miles de productos. Estos destacan:_\n\n"
            for i, it in enumerate(top, 1):
                lnk = link_ml(it["url"], it["id"])
                d   = it["descuento"] * 100
                ln  = str(i) + ". 🔥 *[" + it["nombre"][:48] + "](" + lnk + ")*\n"
                ln += "   *$" + "{:,.0f}".format(it["precio"]) + " MXN*"
                if d >= 10: ln += " (−" + "{:.0f}".format(d) + "%)"
                if it.get("tiene_cupon"): ln += " 🎟️"
                msg += ln + "\n\n"
            if LAUNCHPASS_LINK:
                msg += "🔒 _Los VIP los vieron primero + analisis de reventa._\n_" + LAUNCHPASS_LINK + "_"
            tg_texto(CHANNEL_FREE_ID, msg)
            free_n += 1

    logger.info("[GITHUB v5.2] Fin — VIP:" + str(vip_n) + " Free:" + str(free_n))


if __name__ == "__main__":
    main()
