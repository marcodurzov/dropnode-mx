# =============================================================
# DROPNODE MX — github_scraper_ml.py  v2.3
# Usa ScraperAPI como proxy para evitar bloqueo de ML
# Registro gratuito: scraperapi.com — 1000 llamadas/mes gratis
# =============================================================

import os, requests, time, random, logging, sys, urllib.parse
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
ML_APP_ID       = os.environ["ML_APP_ID"]
ML_SECRET       = os.environ["ML_SECRET"]
ML_AFFILIATE_ID = os.environ.get("ML_AFFILIATE_ID", "marcodurzo")
LAUNCHPASS_LINK = os.environ.get("LAUNCHPASS_LINK", "")
MAKE_WEBHOOK_URL= os.environ.get("MAKE_WEBHOOK_URL", "")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")  # scraperapi.com

TZ_MEXICO = timezone(timedelta(hours=-6))
db        = create_client(SUPABASE_URL, SUPABASE_KEY)
TELEGRAM  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

UMBRAL_VIP  = 0.30
UMBRAL_FREE = 0.15

CATEGORIAS = [
    {"id": "MLM1051", "nombre": "Celulares",       "emoji": "📱"},
    {"id": "MLM1648", "nombre": "Computacion",      "emoji": "💻"},
    {"id": "MLM1000", "nombre": "Electronica",      "emoji": "🔌"},
    {"id": "MLM1002", "nombre": "Televisores",      "emoji": "📺"},
    {"id": "MLM1574", "nombre": "Electrodomesticos","emoji": "🏠"},
    {"id": "MLM1144", "nombre": "Videojuegos",      "emoji": "🎮"},
]

_token = {"value": None, "expires": None}


def get_token():
    ahora = datetime.utcnow()
    if _token["value"] and _token["expires"] and ahora < _token["expires"]:
        return _token["value"]
    try:
        r = requests.post("https://api.mercadolibre.com/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": ML_APP_ID, "client_secret": ML_SECRET,
        }, timeout=15)
        if r.status_code == 200:
            d = r.json()
            _token["value"]   = d["access_token"]
            _token["expires"] = ahora + timedelta(seconds=d.get("expires_in", 21600) - 300)
            logger.info("[AUTH] Token ML OK")
            return _token["value"]
    except Exception as e:
        logger.error(f"[AUTH] {e}")
    return None


def hacer_llamada_ml(url_ml: str, params: dict = None) -> dict | None:
    """
    Llama a la API de ML.
    Si SCRAPER_API_KEY está configurado, enruta a través de ScraperAPI
    para evitar el bloqueo 403 por IP de datacenter.
    """
    token = get_token()
    headers = {
        "Accept": "application/json",
        "Accept-Language": "es-MX,es;q=0.9",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Construir URL completa con params
    if params:
        url_ml = url_ml + "?" + urllib.parse.urlencode(params)

    # Si hay ScraperAPI key, rutar a través de él
    if SCRAPER_API_KEY:
        encoded = urllib.parse.quote(url_ml, safe="")
        proxy_url = (f"https://api.scraperapi.com"
                     f"?api_key={SCRAPER_API_KEY}"
                     f"&url={encoded}"
                     f"&country_code=mx")
        try:
            time.sleep(random.uniform(1, 3))
            r = requests.get(proxy_url, timeout=90)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"[SCRAPER_API] HTTP {r.status_code}: {r.text[:80]}")
        except Exception as e:
            logger.error(f"[SCRAPER_API] {e}")
        return None
    else:
        # Sin proxy — intento directo (puede dar 403 en datacenter)
        try:
            time.sleep(random.uniform(3, 7))
            r = requests.get(url_ml, headers=headers, timeout=15)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"[ML] HTTP {r.status_code}")
        except Exception as e:
            logger.error(f"[ML] {e}")
        return None


def buscar(cat_id, offset=0):
    data = hacer_llamada_ml(
        "https://api.mercadolibre.com/sites/MLM/search",
        {"category": cat_id, "sort": "relevance",
         "offset": offset, "limit": 50, "condition": "new"}
    )
    return data.get("results", []) if data else []


def detalle(item_id):
    return hacer_llamada_ml(f"https://api.mercadolibre.com/items/{item_id}")


# ── Base de datos ─────────────────────────────────────────────

def upsert_prod(url, nombre, categoria, sku):
    try:
        r = db.table("productos").upsert(
            {"url": url, "tienda": "mercadolibre", "nombre": nombre,
             "categoria": categoria, "sku": sku, "activo": True},
            on_conflict="sku,tienda").execute()
        if r.data:
            return r.data[0]["id"]
        r2 = db.table("productos").select("id").eq("sku", sku) \
            .eq("tienda", "mercadolibre").execute()
        return r2.data[0]["id"] if r2.data else None
    except Exception as e:
        logger.error(f"[DB] {e}")
        return None

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
        r = db.table("alertas_enviadas").select("id") \
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

def get_stats(pid, precio_actual):
    try:
        desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
        r = db.table("historial_precios").select("precio, timestamp") \
            .eq("producto_id", pid).gte("timestamp", desde) \
            .eq("disponible", True).order("timestamp").execute()
        regs = r.data or []
        if len(regs) < 5: return {}
        precios   = [float(x["precio"]) for x in regs]
        primer_ts = datetime.fromisoformat(regs[0]["timestamp"].replace("Z",""))
        dias      = (datetime.utcnow() - primer_ts).days + 1
        min_p     = min(precios)
        max_p     = max(precios)
        avg_p     = sum(precios) / len(precios)
        es_minimo = precio_actual <= min_p * 1.02 and dias >= 7
        return {"min": min_p, "max": max_p, "avg": avg_p,
                "dias": dias, "es_minimo": es_minimo}
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
    p = urllib.parse.urlencode({
        "as_src": "affiliate", "as_campaign": "dropnodemx",
        "as_content": item_id, "url": url,
        "affiliate_id": ML_AFFILIATE_ID,
    })
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

    m  = f"{icono} *{tag}*  {em} {cat}\n\n"
    m += f"*{n}*\n\n"
    m += f"Precio ahora:    *${p:,.0f} MXN*\n"
    m += f"Precio original:  ${po:,.0f} MXN\n"
    m += f"Descuento real:  *-{d:.0f}%*\n"
    if st.get("es_minimo") and st.get("dias", 0) >= 7:
        m += f"\n*Precio mas bajo en {st['dias']} dias de seguimiento*\n"
    if st.get("avg") and p < st["avg"] * 0.90:
        m += f"${st['avg']-p:,.0f} menos que el precio promedio\n"
    m += f"\n{stxt}\n"
    if d >= 35 or s <= 3:
        m += "_Oferta podria terminar pronto_\n"
    m += f"\nScore: {sc}/10\n\n"
    m += f"[COMPRAR AHORA]({lnk})\n\n"
    m += f"_Reventa estimada: ${rl:,.0f} - ${rh:,.0f} MXN_\n"
    m += f"_{hr} hora MX_"
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
    m  = f"{icono} *DESCUENTO REAL*  {em}\n\n"
    m += f"*{n}*\n\n"
    m += f"*${p:,.0f} MXN* (-{d:.0f}%)\n"
    m += f"Ref: ${po:,.0f} MXN\n"
    if st.get("es_minimo") and st.get("dias", 0) >= 7:
        m += f"\n*Precio mas bajo en {st['dias']} dias*\n"
    if s <= 5:
        m += f"*Solo {s} unidades*\n"
    m += f"\n[Ver oferta]({lnk})\n\n"
    m += f"_Canal VIP: alertas primero + analisis de reventa._\n"
    if LAUNCHPASS_LINK:
        m += f"_{LAUNCHPASS_LINK}_"
    return m

def notificar_make(item):
    if not MAKE_WEBHOOK_URL: return
    try:
        requests.post(MAKE_WEBHOOK_URL, json={
            "nombre": item["nombre"][:80],
            "precio": str(round(item["precio"])),
            "descuento": str(round(item["descuento"] * 100)),
            "thumbnail": item.get("thumbnail", ""),
            "link": item["url"], "score": item["score"],
        }, timeout=10)
    except Exception: pass


# ── Ciclo principal ───────────────────────────────────────────

def main():
    hora_mx = datetime.now(TZ_MEXICO)
    logger.info(f"[GITHUB] {hora_mx.strftime('%d/%m %H:%M')} MX | "
                f"ScraperAPI: {'SI' if SCRAPER_API_KEY else 'NO'}")

    if not (8 <= hora_mx.hour < 22):
        logger.info("[GITHUB] Fuera de horario")
        return

    if not get_token():
        logger.error("[GITHUB] Sin token ML")
        return

    alertas    = []
    destacados = []

    for cat in CATEGORIAS:
        logger.info(f"[CAT] {cat['emoji']} {cat['nombre']}")
        mejor_cat  = None
        mejor_sc   = -1

        items_raw = buscar(cat["id"], 0)
        if not items_raw:
            logger.info(f"[CAT] {cat['nombre']}: sin resultados (probablemente bloqueado)")
            continue

        for item_raw in items_raw:
            item_id  = item_raw.get("id")
            nombre   = item_raw.get("title", "")
            precio   = item_raw.get("price", 0)
            precio_o = item_raw.get("original_price") or 0
            permalink= item_raw.get("permalink", "")
            stock    = item_raw.get("available_quantity", 0)
            thumb    = item_raw.get("thumbnail", "")

            if not precio or precio <= 0: continue

            det = detalle(item_id)
            if det:
                precio   = det.get("price", precio)
                precio_o = det.get("original_price") or precio_o
                stock    = det.get("available_quantity", stock)
                thumb    = det.get("thumbnail", thumb)

            pid = upsert_prod(permalink, nombre, cat["nombre"], item_id)
            guardar_precio_db(pid, precio, precio_o or precio, stock)

            if stock <= 0 or alerta_hoy(pid): continue

            descuento = 0.0
            if precio_o and precio_o > precio:
                descuento = (precio_o - precio) / precio_o

            sc    = score_item(descuento, stock, precio)
            stats = get_stats(pid, precio)

            proc = {"id": item_id, "pid": pid, "nombre": nombre,
                    "precio": precio, "precio_orig": precio_o or precio,
                    "descuento": descuento, "stock": stock,
                    "url": permalink, "thumbnail": thumb,
                    "categoria": cat, "score": sc, "stats": stats}

            if sc > mejor_sc:
                mejor_sc  = sc
                mejor_cat = proc

            if descuento >= UMBRAL_FREE:
                alertas.append(proc)

        if mejor_cat:
            destacados.append(mejor_cat)

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

    # Mejores del dia si no hubo alertas
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
            if it.get("stats", {}).get("es_minimo"):
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
