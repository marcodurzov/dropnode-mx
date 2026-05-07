# =============================================================
# DROPNODE MX — github_scraper_ml.py  v3.0
# Usa la pagina web de ML (no la API) — menos restrictiva
# Extrae datos del JSON embebido en el HTML de ofertas
# =============================================================

import os, requests, time, random, logging, sys, json, re
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime, timedelta, timezone
from supabase import create_client

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

SUPABASE_URL    = os.environ["SUPABASE_URL"]
SUPABASE_KEY    = os.environ["SUPABASE_KEY"]
TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
CHANNEL_FREE_ID = int(os.environ["CHANNEL_FREE_ID"])
CHANNEL_VIP_ID  = int(os.environ["CHANNEL_VIP_ID"])
ML_AFFILIATE_ID = os.environ.get("ML_AFFILIATE_ID", "marcodurzo")
LAUNCHPASS_LINK = os.environ.get("LAUNCHPASS_LINK", "")
MAKE_WEBHOOK_URL= os.environ.get("MAKE_WEBHOOK_URL", "")

TZ_MEXICO = timezone(timedelta(hours=-6))
db        = create_client(SUPABASE_URL, SUPABASE_KEY)
TELEGRAM  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

UMBRAL_VIP  = 0.30
UMBRAL_FREE = 0.15

# Paginas de ofertas de ML — accesibles sin API key
PAGINAS_OFERTAS = [
    {"url": "https://www.mercadolibre.com.mx/ofertas#nav-header",
     "nombre": "Ofertas destacadas", "emoji": "🔥"},
    {"url": "https://www.mercadolibre.com.mx/c/celulares-y-telefonia",
     "nombre": "Celulares", "emoji": "📱"},
    {"url": "https://www.mercadolibre.com.mx/c/computacion",
     "nombre": "Computacion", "emoji": "💻"},
    {"url": "https://www.mercadolibre.com.mx/c/electronica-audio-y-video",
     "nombre": "Electronica", "emoji": "🔌"},
    {"url": "https://www.mercadolibre.com.mx/c/videojuegos",
     "nombre": "Videojuegos", "emoji": "🎮"},
    {"url": "https://www.mercadolibre.com.mx/c/electrodomesticos-y-aires-acondicionados",
     "nombre": "Electrodomesticos", "emoji": "🏠"},
]

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
]

def get_headers():
    return {
        "User-Agent":       random.choice(USER_AGENTS),
        "Accept":           "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":  "es-MX,es;q=0.9",
        "Accept-Encoding":  "gzip, deflate, br",
        "Connection":       "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest":   "document",
        "Sec-Fetch-Mode":   "navigate",
        "Sec-Fetch-Site":   "none",
    }

def esperar():
    time.sleep(random.uniform(4, 9))

def extraer_productos_html(html: str) -> list:
    """
    Extrae datos de productos del JSON embebido en el HTML de ML.
    ML embebe los datos de productos en window.__PRELOADED_STATE__
    o en scripts de tipo application/json.
    """
    productos = []

    # Patron 1: JSON en __PRELOADED_STATE__
    match = re.search(
        r'window\.__PRELOADED_STATE__\s*=\s*(\{.+?\});?\s*</script>',
        html, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            items = (data.get("initialState", {})
                        .get("results", []) or
                     data.get("results", []))
            productos.extend(items)
        except Exception:
            pass

    # Patron 2: JSON en script con id="__next_data__" o similar
    matches = re.findall(
        r'<script[^>]*type="application/json"[^>]*>(\{.+?\})</script>',
        html, re.DOTALL)
    for m in matches:
        try:
            data  = json.loads(m)
            items = data.get("results", data.get("items", []))
            if items and isinstance(items, list):
                productos.extend(items)
        except Exception:
            pass

    # Patron 3: Buscar precios directamente en HTML con regex
    if not productos:
        # Extraer datos basicos del HTML parseado
        precios_raw = re.findall(
            r'"price":\s*(\d+(?:\.\d+)?)',
            html)
        titulos_raw = re.findall(
            r'"title":\s*"([^"]{10,100})"',
            html)
        urls_raw = re.findall(
            r'"permalink":\s*"(https://www\.mercadolibre\.com\.mx/[^"]+)"',
            html)
        orig_raw = re.findall(
            r'"original_price":\s*(\d+(?:\.\d+)?)',
            html)
        ids_raw = re.findall(
            r'"id":\s*"(MLM\d+)"',
            html)
        thumbs_raw = re.findall(
            r'"thumbnail":\s*"(https://[^"]+\.(?:jpg|png|webp)[^"]*)"',
            html)

        n = min(len(precios_raw), len(titulos_raw), len(urls_raw))
        for i in range(n):
            productos.append({
                "id":             ids_raw[i] if i < len(ids_raw) else f"item_{i}",
                "title":          titulos_raw[i],
                "price":          float(precios_raw[i]),
                "original_price": float(orig_raw[i]) if i < len(orig_raw) else None,
                "permalink":      urls_raw[i],
                "thumbnail":      thumbs_raw[i] if i < len(thumbs_raw) else "",
                "available_quantity": 10,
            })

    return productos


def scrape_pagina(pagina: dict) -> list:
    """Descarga y extrae productos de una pagina de ofertas de ML."""
    esperar()
    try:
        resp = requests.get(pagina["url"], headers=get_headers(),
                           timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            logger.warning(f"[ML WEB] HTTP {resp.status_code} — {pagina['nombre']}")
            return []

        productos = extraer_productos_html(resp.text)
        logger.info(f"[ML WEB] {pagina['nombre']}: {len(productos)} productos extraidos")
        return productos

    except Exception as e:
        logger.error(f"[ML WEB] {pagina['nombre']}: {e}")
        return []


# ── Base de datos ─────────────────────────────────────────────

def upsert_prod(url, nombre, categoria, sku):
    try:
        r = db.table("productos").upsert(
            {"url": url, "tienda": "mercadolibre", "nombre": nombre,
             "categoria": categoria, "sku": sku, "activo": True},
            on_conflict="sku,tienda").execute()
        if r.data: return r.data[0]["id"]
        r2 = db.table("productos").select("id").eq("sku", sku)\
            .eq("tienda", "mercadolibre").execute()
        return r2.data[0]["id"] if r2.data else None
    except Exception as e:
        logger.error(f"[DB] {e}"); return None

def guardar_precio_db(pid, precio, precio_orig, stock):
    if not pid: return
    try:
        db.table("historial_precios").insert({
            "producto_id": pid, "precio": precio,
            "precio_original": precio_orig, "stock": stock,
            "disponible": stock > 0,
            "timestamp": datetime.utcnow().isoformat()
        }).execute()
    except Exception: pass

def alerta_hoy(pid):
    if not pid: return False
    try:
        desde = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
        r = db.table("alertas_enviadas").select("id")\
            .eq("producto_id", pid).gte("timestamp", desde).execute()
        return len(r.data) > 0
    except Exception: return False

def guardar_alerta_db(pid, score, canal, precio, descuento):
    if not pid: return
    try:
        db.table("alertas_enviadas").insert({
            "producto_id": pid, "heat_score": score, "canal": canal,
            "precio_alerta": precio, "descuento_real": descuento,
            "clicks": 0, "timestamp": datetime.utcnow().isoformat()
        }).execute()
    except Exception: pass

def get_minimo(pid):
    try:
        desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
        r = db.table("historial_precios").select("precio")\
            .eq("producto_id", pid).gte("timestamp", desde)\
            .eq("disponible", True).order("precio").limit(1).execute()
        return float(r.data[0]["precio"]) if r.data else None
    except Exception: return None

def get_stats(pid, precio_actual):
    try:
        desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
        r = db.table("historial_precios").select("precio, timestamp")\
            .eq("producto_id", pid).gte("timestamp", desde)\
            .eq("disponible", True).order("timestamp").execute()
        regs = r.data or []
        if len(regs) < 5: return {}
        precios = [float(x["precio"]) for x in regs]
        primer  = datetime.fromisoformat(regs[0]["timestamp"].replace("Z",""))
        dias    = (datetime.utcnow() - primer).days + 1
        return {"min": min(precios), "max": max(precios),
                "avg": sum(precios)/len(precios), "dias": dias,
                "es_minimo": precio_actual <= min(precios)*1.02 and dias >= 7}
    except Exception: return {}


# ── Telegram ──────────────────────────────────────────────────

def enviar(chat_id, texto):
    try:
        r = requests.post(f"{TELEGRAM}/sendMessage", json={
            "chat_id": chat_id, "text": texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=15)
        d = r.json()
        if d.get("ok"): return d["result"]["message_id"]
        logger.warning(f"[TG] {d.get('description')}")
    except Exception as e: logger.error(f"[TG] {e}")
    return None

def link_ml(url, item_id):
    p = f"as_src=affiliate&as_campaign=dropnodemx&as_content={item_id}&url={requests.utils.quote(url)}&affiliate_id={ML_AFFILIATE_ID}"
    return f"https://go.mercadolibre.com.mx?{p}"

def score_item(descuento, stock, precio):
    s = 0.0
    if descuento >= 0.60: s += 3
    elif descuento >= 0.40: s += 2.5
    elif descuento >= 0.25: s += 1.8
    elif descuento >= 0.15: s += 1
    if stock == 1: s += 2
    elif stock <= 3: s += 1.8
    elif stock <= 10: s += 1
    if precio >= 5000: s += 1.5
    elif precio >= 2000: s += 1
    return min(10, round(s))

def construir_msg_vip(item):
    n   = item["nombre"][:65]
    p   = item["precio"]
    po  = item["precio_orig"]
    d   = item["descuento"] * 100
    s   = item["stock"]
    lnk = link_ml(item["url"], item["id"])
    sc  = item["score"]
    st  = item.get("stats", {})
    em  = item["categoria"]["emoji"]
    cat = item["categoria"]["nombre"]
    hr  = datetime.now(TZ_MEXICO).strftime("%H:%M:%S")
    rl  = po * 0.80; rh = po * 0.92
    icono = "🚨" if sc >= 8 else ("🔥" if sc >= 6 else "⚡")
    tag   = "ERROR DE PRECIO" if sc >= 8 else ("OFERTA AGRESIVA" if sc >= 6 else "DESCUENTO REAL")
    if s == 1: stxt = "*ULTIMA UNIDAD*"
    elif s <= 3: stxt = f"*Solo {s} unidades*"
    elif s <= 10: stxt = f"{s} unidades"
    else: stxt = "Stock disponible"
    m  = f"{icono} *{tag}*  {em} {cat}\n\n*{n}*\n\n"
    m += f"Precio ahora:    *${p:,.0f} MXN*\n"
    m += f"Precio original:  ${po:,.0f} MXN\n"
    m += f"Descuento real:  *-{d:.0f}%*\n"
    if st.get("es_minimo") and st.get("dias",0) >= 7:
        m += f"\n*Precio mas bajo en {st['dias']} dias*\n"
    if st.get("avg") and p < st["avg"] * 0.90:
        m += f"${st['avg']-p:,.0f} menos que el promedio\n"
    m += f"\n{stxt}\n"
    if d >= 35 or s <= 3: m += "_Oferta podria terminar pronto_\n"
    m += f"\nScore: {sc}/10\n\n[COMPRAR AHORA]({lnk})\n\n"
    m += f"_Reventa estimada: ${rl:,.0f} - ${rh:,.0f} MXN_\n_{hr} hora MX_"
    return m

def construir_msg_free(item):
    n   = item["nombre"][:60]
    p   = item["precio"]
    po  = item["precio_orig"]
    d   = item["descuento"] * 100
    s   = item["stock"]
    lnk = link_ml(item["url"], item["id"])
    st  = item.get("stats", {})
    em  = item["categoria"]["emoji"]
    sc  = item["score"]
    icono = "🚨" if sc >= 8 else ("🔥" if sc >= 6 else "⚡")
    m  = f"{icono} *DESCUENTO REAL*  {em}\n\n*{n}*\n\n"
    m += f"*${p:,.0f} MXN* (-{d:.0f}%)\nRef: ${po:,.0f} MXN\n"
    if st.get("es_minimo") and st.get("dias",0) >= 7:
        m += f"\n*Precio mas bajo en {st['dias']} dias*\n"
    if s <= 5: m += f"*Solo {s} unidades*\n"
    m += f"\n[Ver oferta]({lnk})\n\n"
    m += f"_Canal VIP: alertas primero + analisis de reventa._\n"
    if LAUNCHPASS_LINK: m += f"_{LAUNCHPASS_LINK}_"
    return m

def notificar_make(item):
    if not MAKE_WEBHOOK_URL: return
    try:
        requests.post(MAKE_WEBHOOK_URL, json={
            "nombre": item["nombre"][:80], "precio": str(round(item["precio"])),
            "descuento": str(round(item["descuento"]*100)),
            "thumbnail": item.get("thumbnail",""),
            "link": item["url"], "score": item["score"],
        }, timeout=10)
    except Exception: pass


# ── Ciclo principal ───────────────────────────────────────────

def procesar_producto(prod_raw, categoria):
    """Normaliza un producto crudo y lo procesa."""
    try:
        item_id  = str(prod_raw.get("id", ""))
        nombre   = str(prod_raw.get("title", ""))[:80]
        precio   = float(prod_raw.get("price", 0))
        precio_o = prod_raw.get("original_price")
        precio_o = float(precio_o) if precio_o else 0
        permalink= str(prod_raw.get("permalink", ""))
        stock    = int(prod_raw.get("available_quantity", 10))
        thumb    = str(prod_raw.get("thumbnail", ""))

        if not nombre or precio <= 0 or not permalink:
            return None

        pid = upsert_prod(permalink, nombre, categoria["nombre"], item_id)
        guardar_precio_db(pid, precio, precio_o or precio, stock)

        if alerta_hoy(pid): return None

        descuento = 0.0
        if precio_o and precio_o > precio:
            descuento = (precio_o - precio) / precio_o
        else:
            minimo = get_minimo(pid)
            if minimo and precio < minimo * 0.85:
                descuento = (minimo - precio) / minimo
                precio_o  = minimo

        sc    = score_item(descuento, stock, precio)
        stats = get_stats(pid, precio)

        return {"id": item_id, "pid": pid, "nombre": nombre,
                "precio": precio, "precio_orig": precio_o or precio,
                "descuento": descuento, "stock": stock,
                "url": permalink, "thumbnail": thumb,
                "categoria": categoria, "score": sc, "stats": stats}
    except Exception:
        return None


def main():
    hora_mx = datetime.now(TZ_MEXICO)
    logger.info(f"[GITHUB v3] {hora_mx.strftime('%d/%m %H:%M')} MX")

    if not (8 <= hora_mx.hour < 22):
        logger.info("[GITHUB] Fuera de horario")
        return

    alertas    = []
    destacados = []

    for pagina in PAGINAS_OFERTAS:
        productos_raw = scrape_pagina(pagina)
        cat = {"nombre": pagina["nombre"], "emoji": pagina["emoji"]}
        mejor_pag  = None
        mejor_sc   = -1

        for prod_raw in productos_raw[:30]:
            item = procesar_producto(prod_raw, cat)
            if not item: continue

            if item["score"] > mejor_sc:
                mejor_sc  = item["score"]
                mejor_pag = item

            if item["descuento"] >= UMBRAL_FREE:
                alertas.append(item)

        if mejor_pag:
            destacados.append(mejor_pag)

    alertas.sort(key=lambda x: x["score"], reverse=True)

    vip_n = 0; free_n = 0

    for item in alertas[:10]:
        if item["descuento"] >= UMBRAL_VIP and item["score"] >= 6:
            msg_id = enviar(CHANNEL_VIP_ID, construir_msg_vip(item))
            if msg_id:
                guardar_alerta_db(item["pid"], item["score"], "vip",
                                  item["precio"], item["descuento"])
                vip_n += 1
                if item["score"] >= 8: notificar_make(item)
                time.sleep(4)

        if item["descuento"] >= UMBRAL_FREE and item["score"] >= 3:
            msg_id = enviar(CHANNEL_FREE_ID, construir_msg_free(item))
            if msg_id:
                if item["descuento"] < UMBRAL_VIP:
                    guardar_alerta_db(item["pid"], item["score"], "free",
                                      item["precio"], item["descuento"])
                free_n += 1
                time.sleep(5)

    # Mejores del dia si no hubo alertas a las 12 PM o 7 PM
    if free_n == 0 and hora_mx.hour in (12, 19) and destacados:
        top = sorted(destacados, key=lambda x: x["score"], reverse=True)[:5]
        hl  = "tarde" if hora_mx.hour >= 15 else "manana"
        msg = f"📋 *Mejores precios de la {hl} — DropNode MX*\n\n"
        msg += "_Nuestro equipo reviso miles de productos. Estos destacan:_\n\n"
        for i, it in enumerate(top, 1):
            lnk = link_ml(it["url"], it["id"])
            d   = it["descuento"] * 100
            ln  = f"{i}. {it['categoria']['emoji']} *[{it['nombre'][:50]}]({lnk})*\n"
            ln += f"   *${it['precio']:,.0f} MXN*"
            if d >= 10: ln += f" (-{d:.0f}%)"
            if it.get("stats",{}).get("es_minimo"):
                ln += f"\n   _Precio mas bajo en {it['stats']['dias']} dias_"
            msg += ln + "\n\n"
        if LAUNCHPASS_LINK:
            msg += f"🔒 _Errores de precio van al VIP primero._\n_{LAUNCHPASS_LINK}_"
        enviar(CHANNEL_FREE_ID, msg)
        free_n += 1

    logger.info(f"[GITHUB] Fin — VIP:{vip_n} Free:{free_n} | "
                f"Alertas:{len(alertas)} Destacados:{len(destacados)}")


if __name__ == "__main__":
    main()