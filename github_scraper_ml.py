# =============================================================
# DROPNODE MX — github_scraper_ml.py
# Corre en GitHub Actions (IPs de Azure — no bloqueadas por ML)
# Se ejecuta cada 30 minutos y publica directo a Telegram
# =============================================================

import os, requests, time, random, logging, sys
from datetime import datetime, timedelta, timezone
from supabase import create_client

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout)
logger = logging.getLogger(__name__)

# ── Variables de entorno (GitHub Secrets) ──────────────────
SUPABASE_URL     = os.environ["SUPABASE_URL"]
SUPABASE_KEY     = os.environ["SUPABASE_KEY"]
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
CHANNEL_FREE_ID  = int(os.environ["CHANNEL_FREE_ID"])
CHANNEL_VIP_ID   = int(os.environ["CHANNEL_VIP_ID"])
ML_APP_ID        = os.environ["ML_APP_ID"]
ML_SECRET        = os.environ["ML_SECRET"]
ML_AFFILIATE_ID  = os.environ.get("ML_AFFILIATE_ID", "marcodurzo")
AMAZON_TAG       = os.environ.get("AMAZON_TAG", "")
LAUNCHPASS_LINK  = os.environ.get("LAUNCHPASS_LINK", "")
MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL", "")

TZ_MEXICO = timezone(timedelta(hours=-6))
db        = create_client(SUPABASE_URL, SUPABASE_KEY)
TELEGRAM  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ── Parámetros ──────────────────────────────────────────────
UMBRAL_VIP  = 0.35
UMBRAL_FREE = 0.15

CATEGORIAS = [
    {"id": "MLM1051", "nombre": "Celulares",          "emoji": "📱"},
    {"id": "MLM1648", "nombre": "Computacion",         "emoji": "💻"},
    {"id": "MLM1000", "nombre": "Electronica",         "emoji": "🔌"},
    {"id": "MLM1002", "nombre": "Televisores",         "emoji": "📺"},
    {"id": "MLM1574", "nombre": "Electrodomesticos",   "emoji": "🏠"},
    {"id": "MLM1144", "nombre": "Videojuegos",         "emoji": "🎮"},
]

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/122.0.0.0 Mobile Safari/537.36",
]

_token = {"value": None, "expires": None}

# ── Auth ML ─────────────────────────────────────────────────

def get_token():
    ahora = datetime.utcnow()
    if _token["value"] and _token["expires"] and ahora < _token["expires"]:
        return _token["value"]
    try:
        r = requests.post("https://api.mercadolibre.com/oauth/token", data={
            "grant_type":    "client_credentials",
            "client_id":     ML_APP_ID,
            "client_secret": ML_SECRET,
        }, timeout=15)
        if r.status_code == 200:
            d = r.json()
            _token["value"]   = d["access_token"]
            _token["expires"] = ahora + timedelta(
                seconds=d.get("expires_in", 21600) - 300)
            logger.info("[AUTH] Token ML OK")
            return _token["value"]
    except Exception as e:
        logger.error(f"[AUTH] {e}")
    return None

def headers():
    token = get_token()
    h = {"User-Agent": random.choice(USER_AGENTS),
         "Accept": "application/json",
         "Accept-Language": "es-MX,es;q=0.9"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

def esperar():
    time.sleep(random.uniform(3, 7))

# ── API ML ──────────────────────────────────────────────────

def buscar(cat_id, offset=0):
    esperar()
    try:
        r = requests.get("https://api.mercadolibre.com/sites/MLM/search",
            params={"category": cat_id, "sort": "relevance",
                    "offset": offset, "limit": 50, "condition": "new"},
            headers=headers(), timeout=15)
        if r.status_code == 200:
            return r.json().get("results", [])
        logger.warning(f"[ML] HTTP {r.status_code} cat={cat_id}")
    except Exception as e:
        logger.error(f"[ML] {e}")
    return []

def detalle(item_id):
    esperar()
    try:
        r = requests.get(f"https://api.mercadolibre.com/items/{item_id}",
                         headers=headers(), timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None

# ── Base de datos ────────────────────────────────────────────

def upsert_prod(url, nombre, categoria, sku):
    try:
        r = db.table("productos").upsert(
            {"url": url, "tienda": "mercadolibre", "nombre": nombre,
             "categoria": categoria, "sku": sku, "activo": True},
            on_conflict="sku,tienda").execute()
        if r.data:
            return r.data[0]["id"]
        r2 = db.table("productos").select("id") \
            .eq("sku", sku).eq("tienda", "mercadolibre").execute()
        return r2.data[0]["id"] if r2.data else None
    except Exception as e:
        logger.error(f"[DB] upsert: {e}")
        return None

def guardar_precio_db(pid, precio, precio_orig, stock):
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
        r = db.table("alertas_enviadas").select("id") \
            .eq("producto_id", pid).gte("timestamp", desde).execute()
        return len(r.data) > 0
    except Exception:
        return False

def guardar_alerta_db(pid, score, canal, precio, descuento):
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
        r = db.table("historial_precios").select("precio") \
            .eq("producto_id", pid).gte("timestamp", desde) \
            .eq("disponible", True).order("precio").limit(1).execute()
        return float(r.data[0]["precio"]) if r.data else None
    except Exception:
        return None

def get_stats(pid, precio_actual):
    try:
        desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
        r = db.table("historial_precios").select("precio, timestamp") \
            .eq("producto_id", pid).gte("timestamp", desde) \
            .eq("disponible", True).order("timestamp").execute()
        registros = r.data or []
        if len(registros) < 3:
            return {}
        precios    = [float(x["precio"]) for x in registros]
        min_p      = min(precios)
        max_p      = max(precios)
        avg_p      = sum(precios) / len(precios)
        primer_ts  = datetime.fromisoformat(
            registros[0]["timestamp"].replace("Z",""))
        dias       = (datetime.utcnow() - primer_ts).days + 1
        es_minimo  = precio_actual <= min_p * 1.02 and dias >= 7
        return {"min": min_p, "max": max_p, "avg": avg_p,
                "dias": dias, "es_minimo": es_minimo}
    except Exception:
        return {}

# ── Telegram ─────────────────────────────────────────────────

def enviar(chat_id, texto):
    try:
        r = requests.post(f"{TELEGRAM}/sendMessage", json={
            "chat_id": chat_id, "text": texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=15)
        d = r.json()
        if d.get("ok"):
            return d["result"]["message_id"]
        logger.warning(f"[TG] {d.get('description')}")
    except Exception as e:
        logger.error(f"[TG] {e}")
    return None

def link_ml(url, item_id):
    import urllib.parse
    p = urllib.parse.urlencode({
        "as_src": "affiliate", "as_campaign": "dropnodemx",
        "as_content": item_id, "url": url,
        "affiliate_id": ML_AFFILIATE_ID,
    })
    return f"https://go.mercadolibre.com.mx?{p}"

def score_simple(descuento, stock, precio):
    s = 0.0
    if descuento >= 0.60: s += 3
    elif descuento >= 0.40: s += 2
    elif descuento >= 0.25: s += 1.5
    elif descuento >= 0.15: s += 1
    if stock == 1: s += 2
    elif stock <= 3: s += 1.8
    elif stock <= 10: s += 1
    if precio >= 5000: s += 1.5
    elif precio >= 2000: s += 1
    return min(10, round(s))

def msg_vip(item):
    nombre  = item["nombre"][:65]
    p_act   = item["precio"]
    p_orig  = item["precio_orig"]
    desc    = item["descuento"] * 100
    stock   = item["stock"]
    link    = link_ml(item["url"], item["id"])
    score   = item["score"]
    stats   = item.get("stats", {})
    emoji   = item["categoria"]["emoji"]
    cat     = item["categoria"]["nombre"]
    hora    = datetime.now(TZ_MEXICO).strftime("%H:%M:%S")

    if score >= 8: icono = "🚨"
    elif score >= 6: icono = "🔥"
    else: icono = "⚡"

    if score >= 8: etiqueta = "ERROR DE PRECIO"
    elif score >= 6: etiqueta = "OFERTA AGRESIVA"
    else: etiqueta = "DESCUENTO REAL"

    rl = p_orig * 0.80
    rh = p_orig * 0.92

    if stock == 1: stock_txt = "*ULTIMA UNIDAD*"
    elif stock <= 3: stock_txt = f"*Solo {stock} unidades*"
    elif stock <= 10: stock_txt = f"{stock} unidades"
    else: stock_txt = "Stock disponible"

    m = f"{icono} *{etiqueta}*  {emoji} {cat}\n\n"
    m += f"*{nombre}*\n\n"
    m += f"Precio ahora:   *${p_act:,.0f} MXN*\n"
    m += f"Precio original: ${p_orig:,.0f} MXN\n"
    m += f"Descuento real: *-{desc:.0f}%*\n"

    if stats.get("es_minimo") and stats.get("dias", 0) >= 7:
        m += f"\n*Precio mas bajo en {stats['dias']} dias de seguimiento*\n"
    if stats.get("avg") and p_act < stats["avg"] * 0.90:
        ahorro = stats["avg"] - p_act
        m += f"${ahorro:,.0f} menos que el precio promedio\n"
    if stats.get("max") and stats["max"] > p_act * 1.20:
        m += f"Llego a costar ${stats['max']:,.0f} MXN\n"

    m += f"\n{stock_txt}\n"
    if desc >= 40 or stock <= 3:
        m += "_Oferta podria terminar pronto_\n"

    m += f"\nScore: {score}/10\n\n"
    m += f"[COMPRAR AHORA]({link})\n\n"
    m += f"_Reventa estimada: ${rl:,.0f} - ${rh:,.0f} MXN_\n"
    m += f"_{hora} hora MX_"
    return m

def msg_free(item):
    nombre = item["nombre"][:60]
    p_act  = item["precio"]
    p_orig = item["precio_orig"]
    desc   = item["descuento"] * 100
    stock  = item["stock"]
    link   = link_ml(item["url"], item["id"])
    stats  = item.get("stats", {})
    emoji  = item["categoria"]["emoji"]

    if item["score"] >= 8: icono = "🚨"
    elif item["score"] >= 6: icono = "🔥"
    else: icono = "⚡"

    m  = f"{icono} *DESCUENTO REAL*  {emoji}\n\n"
    m += f"*{nombre}*\n\n"
    m += f"*${p_act:,.0f} MXN* (-{desc:.0f}%)\n"
    m += f"Ref: ${p_orig:,.0f} MXN\n"

    if stats.get("es_minimo") and stats.get("dias", 0) >= 7:
        m += f"\n*Precio mas bajo en {stats['dias']} dias*\n"
    if stock <= 5:
        m += f"*Solo {stock} unidades*\n"

    m += f"\n[Ver oferta]({link})\n\n"
    m += f"_Canal VIP: alertas primero + analisis de reventa._\n"
    if LAUNCHPASS_LINK:
        m += f"_{LAUNCHPASS_LINK}_"
    return m

def notificar_make(item):
    if not MAKE_WEBHOOK_URL:
        return
    try:
        requests.post(MAKE_WEBHOOK_URL, json={
            "nombre":    item["nombre"][:80],
            "precio":    str(round(item["precio"])),
            "descuento": str(round(item["descuento"] * 100)),
            "thumbnail": item.get("thumbnail", ""),
            "link":      item["url"],
            "categoria": item["categoria"]["nombre"],
            "score":     item["score"],
        }, timeout=10)
    except Exception:
        pass

# ── Ciclo principal ──────────────────────────────────────────

def main():
    hora_mx = datetime.now(TZ_MEXICO)
    logger.info(f"[GITHUB] Inicio — {hora_mx.strftime('%d/%m %H:%M')} MX")

    if not (8 <= hora_mx.hour < 22):
        logger.info("[GITHUB] Fuera de horario — terminando")
        return

    token = get_token()
    if not token:
        logger.error("[GITHUB] Sin token ML — abortando")
        return

    alertas    = []
    destacados = []

    for cat in CATEGORIAS:
        logger.info(f"[CAT] {cat['emoji']} {cat['nombre']}")
        mejor_cat   = None
        mejor_score = -1

        for offset in range(0, 100, 50):
            items = buscar(cat["id"], offset)
            if not items:
                break

            for item_raw in items:
                item_id    = item_raw.get("id")
                nombre     = item_raw.get("title", "")
                precio     = item_raw.get("price", 0)
                precio_orig= item_raw.get("original_price") or 0
                permalink  = item_raw.get("permalink", "")
                stock      = item_raw.get("available_quantity", 0)
                thumbnail  = item_raw.get("thumbnail", "")

                if not precio or precio <= 0:
                    continue

                # Detalle completo
                det = detalle(item_id)
                if det:
                    precio      = det.get("price", precio)
                    precio_orig = det.get("original_price") or precio_orig
                    stock       = det.get("available_quantity", stock)
                    thumbnail   = det.get("thumbnail", thumbnail)

                pid = upsert_prod(permalink, nombre, cat["nombre"], item_id)
                guardar_precio_db(pid, precio, precio_orig or precio, stock)

                if stock <= 0 or alerta_hoy(pid):
                    continue

                # Calcular descuento
                descuento = 0.0
                if precio_orig and precio_orig > precio:
                    descuento = (precio_orig - precio) / precio_orig
                else:
                    minimo = get_minimo(pid)
                    if minimo and precio < minimo * 0.85:
                        descuento = (minimo - precio) / minimo
                        precio_orig = minimo

                score = score_simple(descuento, stock, precio)
                stats = get_stats(pid, precio)

                item_proc = {
                    "id":         item_id,
                    "pid":        pid,
                    "nombre":     nombre,
                    "precio":     precio,
                    "precio_orig":precio_orig or precio,
                    "descuento":  descuento,
                    "stock":      stock,
                    "url":        permalink,
                    "thumbnail":  thumbnail,
                    "categoria":  cat,
                    "score":      score,
                    "stats":      stats,
                }

                if score > mejor_score:
                    mejor_score = score
                    mejor_cat   = item_proc

                if descuento >= UMBRAL_FREE:
                    alertas.append(item_proc)

        if mejor_cat:
            destacados.append(mejor_cat)

    # Ordenar por score
    alertas.sort(key=lambda x: x["score"], reverse=True)

    enviadas_vip  = 0
    enviadas_free = 0

    # Publicar alertas con descuento real
    for item in alertas[:10]:
        if item["descuento"] >= UMBRAL_VIP and item["score"] >= 7:
            msg_id = enviar(CHANNEL_VIP_ID, msg_vip(item))
            if msg_id:
                guardar_alerta_db(item["pid"], item["score"], "vip",
                                  item["precio"], item["descuento"])
                enviadas_vip += 1
                if item["score"] >= 8:
                    notificar_make(item)
                time.sleep(4)

        if item["descuento"] >= UMBRAL_FREE and item["score"] >= 4:
            msg_id = enviar(CHANNEL_FREE_ID, msg_free(item))
            if msg_id:
                if item["descuento"] < UMBRAL_VIP:
                    guardar_alerta_db(item["pid"], item["score"], "free",
                                      item["precio"], item["descuento"])
                enviadas_free += 1
                time.sleep(5)

    # Si no hubo alertas, publicar mejores del dia (12 PM y 7 PM MX)
    if enviadas_free == 0 and hora_mx.hour in (12, 19) and destacados:
        top = sorted(destacados, key=lambda x: x["score"], reverse=True)[:5]
        hora_label = "tarde" if hora_mx.hour >= 15 else "manana"
        msg = f"📋 *Mejores precios de la {hora_label} — DropNode MX*\n\n"
        msg += "_Nuestro equipo reviso miles de productos. Estos destacan:_\n\n"
        for i, it in enumerate(top, 1):
            nombre = it["nombre"][:50]
            precio = it["precio"]
            desc   = it["descuento"] * 100
            lnk    = link_ml(it["url"], it["id"])
            emoji  = it["categoria"]["emoji"]
            linea  = f"{i}. {emoji} *[{nombre}]({lnk})*\n   *${precio:,.0f} MXN*"
            if desc >= 10:
                linea += f" (-{desc:.0f}%)"
            if it.get("stats", {}).get("es_minimo"):
                linea += f"\n   _Precio mas bajo en {it['stats']['dias']} dias_"
            msg += linea + "\n\n"
        if LAUNCHPASS_LINK:
            msg += f"🔒 _Errores de precio van al VIP primero._\n_{LAUNCHPASS_LINK}_"
        enviar(CHANNEL_FREE_ID, msg)
        enviadas_free += 1

    logger.info(f"[GITHUB] Fin — VIP:{enviadas_vip} Free:{enviadas_free}")


if __name__ == "__main__":
    main()
