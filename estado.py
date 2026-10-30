# =============================================================
# DROPNODE MX — estado.py  (v1.0)
# Todo lo que necesita MEMORIA entre corridas de GitHub Actions
# (cada corrida es un proceso nuevo: nada en variables globales sobrevive).
#   - Cliente Supabase único (credenciales: env primero, luego config.py)
#   - Candados anti-duplicado  (reclamar_evento)
#   - Cola VIP -> Free (60 min)
#   - Registro de publicaciones (alimenta los resúmenes)
#   - Alertas privadas al admin (opcional: ADMIN_CHAT_ID)
#   - Salud de fuentes (qué scraper está muerto)
# Si la base de datos no responde, TODO degrada con gracia (no crashea).
# =============================================================
import os, re, logging, socket, time, html, hashlib
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


def cfg(nombre, default=""):
    """Env primero (secrets de GitHub); si no, config.py."""
    v = os.environ.get(nombre)
    if v is not None and str(v).strip() != "":
        return str(v).strip()
    try:
        import config
        v = getattr(config, nombre, None)
        if v not in (None, ""):
            return v
    except Exception:
        pass
    return default


EQUIPO_LINEA = "<i>El equipo de DropNode monitorea las tiendas todo el día para encontrar las mejores ofertas.</i>"


def cfg_int(nombre, default=0):
    try:
        return int(str(cfg(nombre, default)).strip())
    except Exception:
        return default


TELEGRAM_TOKEN = cfg("TELEGRAM_TOKEN")
ADMIN_CHAT_ID = cfg("ADMIN_CHAT_ID")
TG = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ─────────────────────────────────────────────
# Supabase
# ─────────────────────────────────────────────
_db = None
_db_fallo = False
_eventos_mem = set()


def get_db():
    global _db, _db_fallo
    if _db is not None:
        return _db
    if _db_fallo:
        return None
    try:
        from supabase import create_client
        url, key = cfg("SUPABASE_URL"), cfg("SUPABASE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL / SUPABASE_KEY vacíos")
        _db = create_client(url.strip(), key.strip())
    except Exception as e:
        _db_fallo = True
        logger.warning(f"[DB] no disponible: {e}")
    return _db


def db_health():
    """Diagnóstico: resuelve DNS, hace una lectura y una escritura de prueba."""
    res = {"url": "", "dns": None, "lectura": None, "escritura": None, "error": ""}
    try:
        url = cfg("SUPABASE_URL")
        host = urlparse(url).hostname or ""
        res["url"] = host
        try:
            res["dns"] = socket.gethostbyname(host)
        except Exception as e:
            res["dns"] = None
            res["error"] = f"DNS: {e}"
            return res
        db = get_db()
        if not db:
            res["error"] = "cliente no creado"
            return res
        db.table("cola_free").select("id").limit(1).execute()
        res["lectura"] = True
        db.table("eventos_enviados").upsert(
            {"clave": "healthcheck", "detalle": datetime.utcnow().isoformat()},
            on_conflict="clave").execute()
        res["escritura"] = True
    except Exception as e:
        res["error"] = str(e)[:200]
    return res


def fetch_all(build, page=1000, max_pages=10):
    """Pagina consultas (Supabase corta en 1000 filas). build() -> query nueva."""
    out = []
    for i in range(max_pages):
        r = build().range(i * page, i * page + page - 1).execute()
        rows = r.data or []
        out += rows
        if len(rows) < page:
            break
    return out


# ─────────────────────────────────────────────
# Candados anti-duplicado
# ─────────────────────────────────────────────
def reclamar_evento(clave, detalle="", fallback=True):
    """True = este proceso es el dueño del evento (hazlo). False = ya se hizo.
    Usa la clave UNIQUE de eventos_enviados como candado atómico.
    Si la BD falla: devuelve `fallback` (el llamador decide el riesgo)."""
    if clave in _eventos_mem:
        return False
    db = get_db()
    if db:
        try:
            db.table("eventos_enviados").insert(
                {"clave": clave, "detalle": str(detalle)[:300]}).execute()
            _eventos_mem.add(clave)
            return True
        except Exception as e:
            msg = str(e).lower()
            if "duplicate" in msg or "23505" in msg or "unique" in msg:
                _eventos_mem.add(clave)
                return False
            logger.warning(f"[EVENTO] {clave}: {e}")
    if fallback:
        _eventos_mem.add(clave)
    return fallback


def liberar_evento(clave):
    """Borra el candado para que la tarea se reintente en la próxima corrida (p. ej. si Telegram falló)."""
    _eventos_mem.discard(clave)
    db = get_db()
    if not db:
        return
    try:
        db.table("eventos_enviados").delete().eq("clave", clave).execute()
    except Exception:
        pass


def evento_hecho(clave):
    if clave in _eventos_mem:
        return True
    db = get_db()
    if not db:
        return False
    try:
        r = db.table("eventos_enviados").select("clave").eq("clave", clave).limit(1).execute()
        return bool(r.data)
    except Exception:
        return False


# ─────────────────────────────────────────────
# Telegram básico (HTML)
# ─────────────────────────────────────────────
def esc(s):
    return html.escape(str(s or ""), quote=False)


def _es_vip(chat_id):
    try:
        return str(chat_id) == str(cfg_int("CHANNEL_VIP_ID"))
    except Exception:
        return False


def tg_send(chat_id, texto, boton=None, parse_mode="HTML", foto=None, reply_to=None, solo_foto=False):
    """Devuelve message_id o None. boton = (texto, url). En el canal VIP el contenido va protegido
    (no se puede reenviar ni guardar). solo_foto=True: si la foto falla NO manda texto (devuelve None)."""
    if not chat_id or not TELEGRAM_TOKEN:
        return None
    payload = {"chat_id": chat_id, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if boton and boton[1]:
        payload["reply_markup"] = {"inline_keyboard": [[{"text": boton[0], "url": boton[1]}]]}
    if _es_vip(chat_id):
        payload["protect_content"] = True
    if reply_to:
        payload["reply_to_message_id"] = reply_to
        payload["allow_sending_without_reply"] = True
    try:
        if foto:
            payload.update({"photo": foto, "caption": texto[:1024]})
            r = requests.post(f"{TG}/sendPhoto", json=payload, timeout=20).json()
            if r.get("ok"):
                return r["result"]["message_id"]
            if solo_foto:
                return None
            payload.pop("photo", None); payload.pop("caption", None)
        payload["text"] = texto[:4096]
        r = requests.post(f"{TG}/sendMessage", json=payload, timeout=15).json()
        if r.get("ok"):
            return r["result"]["message_id"]
        logger.warning(f"[TG] {r.get('description', '?')}")
    except Exception as e:
        logger.error(f"[TG] {e}")
    return None


def admin_msg(texto, clave=None):
    """Mensaje privado al dueño. Sin ADMIN_CHAT_ID no hace nada. `clave` = anti-spam."""
    if not ADMIN_CHAT_ID:
        logger.info(f"[ADMIN] (sin ADMIN_CHAT_ID) {texto[:120]}")
        return None
    if str(ADMIN_CHAT_ID).strip() == str(TELEGRAM_TOKEN).split(":")[0]:
        logger.warning("[ADMIN] ADMIN_CHAT_ID es el ID del BOT, no el tuyo: escríbele /id al bot y usa el número que responde")
        return None
    if clave and not reclamar_evento(clave, fallback=False):
        return None
    return tg_send(ADMIN_CHAT_ID, texto)


# ─────────────────────────────────────────────
# Filtro de basura: accesorios baratos que no valen una alerta
# ─────────────────────────────────────────────
PRECIO_MIN_ALERTA = 150
_BASURA = re.compile(
    r"\b(funda|estuche|case|carcasa)s?\s+(para|de)\s+(celular|iphone|samsung|xiaomi|motorola|tablet|ipad|laptop|airpods|audifonos|audífonos)"
    r"|\bmica\b|protector(es)? de pantalla|vidrio templado|cristal templado|\bstickers?\b|calcoman[ií]as?"
    r"|cable (usb|lightning|tipo c|type c|hdmi|aux)\b|\bpilas?\b|\bbaterias? aa", re.I)


def es_basura(nombre, precio=0):
    try:
        if precio and float(precio) < PRECIO_MIN_ALERTA:
            return True
        return bool(_BASURA.search(str(nombre or "")))
    except Exception:
        return False


_bot = {}


def bot_info():
    """{'id':..., 'username':...} del bot (1 llamada por corrida)."""
    if not _bot and TELEGRAM_TOKEN:
        try:
            r = requests.get(f"{TG}/getMe", timeout=10).json().get("result") or {}
            _bot.update({"id": r.get("id"), "username": r.get("username") or ""})
        except Exception:
            pass
    return _bot


# ─────────────────────────────────────────────
# Afiliados
# ─────────────────────────────────────────────
def link_afiliado(url, sku=""):
    if not url:
        return url
    try:
        if "mercadolibre" in url or "mercadolivre" in url:
            aff = cfg("ML_AFFILIATE_ID", "marcodurzo")
            base = url.split("?")[0].split("#")[0]
            return f"{base}?matt_tool={aff}" if aff else base
        if "amazon.com" in url:
            tag = cfg("AMAZON_TAG")
            m = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", url)
            if m:                                   # enlace corto y limpio: sin parámetros de rastreo
                host = re.search(r"https?://([^/]+)", url)
                url = f"https://{host.group(1) if host else 'www.amazon.com.mx'}/dp/{m.group(1)}"
            if tag and "tag=" not in url:
                return url + ("&" if "?" in url else "?") + f"tag={tag}"
    except Exception:
        pass
    return url


# ─────────────────────────────────────────────
# Items: formato único (plano, serializable)
# ─────────────────────────────────────────────
def sku_de(item):
    sku = str(item.get("sku") or "").strip()
    if sku:
        return sku[:60]
    base = (item.get("url") or item.get("nombre") or "")
    return hashlib.md5(base.encode()).hexdigest()[:14]


def aplanar(item):
    """cola_free guarda JSON: nada de dicts anidados (el bug de 'categoria')."""
    cat = item.get("categoria")
    cat_n = item.get("cat_nombre") or (cat.get("nombre") if isinstance(cat, dict) else str(cat or "General"))
    cat_e = item.get("cat_emoji") or (cat.get("emoji") if isinstance(cat, dict) else "🛍️")
    return {
        "tienda": item.get("tienda", ""),
        "nombre": str(item.get("nombre", ""))[:90],
        "precio_actual": float(item.get("precio_actual") or 0),
        "precio_original": float(item.get("precio_original") or 0),
        "descuento": float(item.get("descuento") or 0),
        "sku": sku_de(item),
        "url": item.get("url", ""),
        "thumbnail": item.get("thumbnail", "") or "",
        "cat_nombre": cat_n, "cat_emoji": cat_e,
        "envio_gratis": bool(item.get("envio_gratis")),
        "es_flash": bool(item.get("es_flash")),
        "en_vip": bool(item.get("en_vip")),
    }


def item_hoy_publicado(item, canal="vip"):
    """True si este producto YA se publicó hoy en ese canal (evita repetidos)."""
    clave = f"item:{canal}:{item.get('tienda','')}:{sku_de(item)}:{datetime.utcnow().strftime('%Y%m%d')}"
    return not reclamar_evento(clave, fallback=True)


# ─────────────────────────────────────────────
# Política de repeticiones
#   score < 8  -> el producto sale UNA sola vez por ventana
#   score >= 8 -> hasta 3 veces por ventana, separadas al menos 4 h
#   siempre se permite si el precio bajó >= 15% vs la última alerta
#   (otro vendedor del mismo producto = otro producto = no cuenta)
# ─────────────────────────────────────────────
REP_VENTANA_DIAS = 14
REP_SCORE_ALTO = 8
REP_ALTO_MAX = 3
REP_ALTO_GAP_H = 4
REP_BAJA_PRECIO = 0.15


def _pid_de(item):
    db = get_db()
    if not db:
        return None
    r = db.table("productos").select("id").eq("sku", sku_de(item)).eq("tienda", item.get("tienda", "")).limit(1).execute()
    return r.data[0]["id"] if r.data else None


def puede_publicar_pid(pid, score, precio, canal="vip"):
    """True si la política permite publicar (de nuevo) este producto en ese canal."""
    db = get_db()
    if not pid or not db:
        return True
    desde = (datetime.utcnow() - timedelta(days=REP_VENTANA_DIAS)).isoformat()
    rows = db.table("alertas_enviadas").select("precio_alerta,timestamp") \
        .eq("producto_id", pid).eq("canal", canal).gte("timestamp", desde) \
        .order("timestamp", desc=True).limit(20).execute().data or []
    if not rows:
        return True
    p_ult = float(rows[0].get("precio_alerta") or 0)
    if p_ult > 0 and precio and precio <= p_ult * (1 - REP_BAJA_PRECIO):
        return True                                   # bajó de precio de verdad: es información nueva
    if score >= REP_SCORE_ALTO:
        if len(rows) >= REP_ALTO_MAX:
            return False
        try:
            ult = datetime.fromisoformat(str(rows[0]["timestamp"]).replace("Z", "").split("+")[0])
            return (datetime.utcnow() - ult) >= timedelta(hours=REP_ALTO_GAP_H)
        except Exception:
            return True
    return False


def puede_publicar_item(item, score, canal="vip", guardia_dia=True):
    """Versión para items sueltos (main.py). Si la BD falla, cae al candado de 1 vez por día."""
    try:
        if get_db():
            ok = puede_publicar_pid(_pid_de(item), score, float(item.get("precio_actual") or 0), canal)
            if not ok:
                return False
            # cinturón: si el registro en BD fallara, igual no repetir un score bajo el mismo día
            if guardia_dia and score < REP_SCORE_ALTO:
                clave = f"item:{canal}:{item.get('tienda','')}:{sku_de(item)}:{datetime.utcnow().strftime('%Y%m%d')}"
                return reclamar_evento(clave, fallback=True)
            return True
    except Exception as e:
        logger.warning(f"[REPETICION] {e}")
    return not item_hoy_publicado(item, canal)


# ─────────────────────────────────────────────
# Registro de publicaciones (alimenta resúmenes)
# ─────────────────────────────────────────────
def registrar_publicacion(item, canal, score, msg_id=None):
    """Upsert del producto + fila en alertas_enviadas. Falla en silencio."""
    db = get_db()
    if not db:
        return None
    try:
        sku = sku_de(item)
        tienda = item.get("tienda", "")
        cat = item.get("cat_nombre") or (item.get("categoria") or {}).get("nombre", "General") \
            if isinstance(item.get("categoria"), dict) or item.get("cat_nombre") else "General"
        r = db.table("productos").upsert(
            {"url": item.get("url", ""), "tienda": tienda, "nombre": str(item.get("nombre", ""))[:120],
             "categoria": cat, "sku": sku, "activo": True},
            on_conflict="sku,tienda").execute()
        pid = r.data[0]["id"] if r.data else None
        if not pid:
            r2 = db.table("productos").select("id").eq("sku", sku).eq("tienda", tienda).execute()
            pid = r2.data[0]["id"] if r2.data else None
        if not pid:
            return None
        db.table("alertas_enviadas").insert({
            "producto_id": pid, "heat_score": score, "canal": canal,
            "precio_alerta": item.get("precio_actual"),
            "descuento_real": item.get("descuento"),
            "telegram_msg_id": msg_id, "clicks": 0,
            "timestamp": datetime.utcnow().isoformat()}).execute()
        return pid
    except Exception as e:
        logger.warning(f"[REGISTRO] {e}")
        return None


def contar_alertas(canal, desde_utc):
    db = get_db()
    if not db:
        return 0
    try:
        r = db.table("alertas_enviadas").select("id", count="exact") \
            .eq("canal", canal).gte("timestamp", desde_utc.isoformat()).execute()
        return r.count or 0
    except Exception:
        return 0


# ─────────────────────────────────────────────
# Cola VIP -> Free  (tabla cola_free)
# ─────────────────────────────────────────────
def cola_agregar(item, score, n_vip=0, delay_min=60):
    db = get_db()
    if not db:
        return False
    try:
        send_after = (datetime.utcnow() + timedelta(minutes=delay_min)).isoformat()
        db.table("cola_free").insert({
            "item": aplanar(item), "score": score, "n_vip": n_vip,
            "send_after": send_after, "enviado": False}).execute()
        return True
    except Exception as e:
        logger.warning(f"[COLA] {e}")
        return False


def cola_listos(limite=60):
    db = get_db()
    if not db:
        return []
    try:
        r = db.table("cola_free").select("*").eq("enviado", False) \
            .lte("send_after", datetime.utcnow().isoformat()) \
            .order("score", desc=True).limit(limite).execute()
        return r.data or []
    except Exception as e:
        logger.warning(f"[COLA] leer: {e}")
        return []


def cola_marcar(ids):
    db = get_db()
    if not db or not ids:
        return
    try:
        db.table("cola_free").update({"enviado": True}).in_("id", ids).execute()
    except Exception:
        pass


def cola_limpiar(horas=5):
    db = get_db()
    if not db:
        return
    try:
        limite = (datetime.utcnow() - timedelta(hours=horas)).isoformat()
        db.table("cola_free").delete().eq("enviado", False).lt("send_after", limite).execute()
    except Exception:
        pass


# ─────────────────────────────────────────────
# Salud de fuentes
# ─────────────────────────────────────────────
def log_fuente(nombre, n_items, error=""):
    db = get_db()
    if not db:
        return
    try:
        db.table("fuentes_log").insert({"fuente": nombre, "items": n_items,
                                        "error": str(error)[:200]}).execute()
    except Exception:
        pass


def salud_fuentes(horas=24):
    """{fuente: (corridas, corridas_con_items, total_items)}"""
    db = get_db()
    if not db:
        return {}
    try:
        desde = (datetime.utcnow() - timedelta(hours=horas)).isoformat()
        rows = fetch_all(lambda: db.table("fuentes_log").select("fuente,items").gte("ts", desde))
        out = {}
        for r in rows:
            c, ok, tot = out.get(r["fuente"], (0, 0, 0))
            out[r["fuente"]] = (c + 1, ok + (1 if (r.get("items") or 0) > 0 else 0), tot + (r.get("items") or 0))
        return out
    except Exception:
        return {}


# ─────────────────────────────────────────────
# Cola VIP (ráfagas) — tabla cola_vip
# ─────────────────────────────────────────────
def cola_vip_agregar(payload, score):
    """True si quedó en la cola; False si la tabla no existe o la BD falla (el llamador publica directo)."""
    db = get_db()
    if not db:
        return False
    try:
        db.table("cola_vip").insert({"payload": payload, "score": score, "enviado": False}).execute()
        return True
    except Exception as e:
        logger.warning(f"[COLA VIP] {str(e)[:100]}")
        return False


def cola_vip_listos(limite=400):
    db = get_db()
    if not db:
        return []
    try:
        r = db.table("cola_vip").select("*").eq("enviado", False) \
            .order("score", desc=True).order("id").limit(limite).execute()
        return r.data or []
    except Exception as e:
        logger.warning(f"[COLA VIP] leer: {str(e)[:100]}")
        return []


def cola_vip_marcar(ids):
    db = get_db()
    if not db or not ids:
        return
    try:
        db.table("cola_vip").update({"enviado": True}).in_("id", ids).execute()
    except Exception:
        pass


def cola_vip_limpiar(horas=5):
    db = get_db()
    if not db:
        return
    try:
        limite = (datetime.utcnow() - timedelta(hours=horas)).isoformat()
        db.table("cola_vip").delete().eq("enviado", False).lt("created_at", limite).execute()
        db.table("cola_vip").delete().eq("enviado", True).lt("created_at", (datetime.utcnow() - timedelta(days=2)).isoformat()).execute()
    except Exception:
        pass


def guardar_alerta_pid(pid, score, canal, precio, descuento, msg_id=None):
    db = get_db()
    if not db or not pid:
        return
    try:
        db.table("alertas_enviadas").insert({
            "producto_id": pid, "heat_score": score, "canal": canal, "precio_alerta": precio,
            "descuento_real": descuento, "telegram_msg_id": msg_id, "clicks": 0,
            "timestamp": datetime.utcnow().isoformat()}).execute()
    except Exception as e:
        logger.warning(f"[ALERTA] {e}")


# ─────────────────────────────────────────────
# Fotos: que TODA alerta del VIP lleve imagen
# ─────────────────────────────────────────────
_UA_IMG = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
           "Accept": "image/avif,image/webp,image/*,*/*;q=0.8", "Accept-Language": "es-MX,es;q=0.9"}


def url_absoluta(url, base=""):
    u = str(url or "").strip()
    if not u or u.startswith("data:"):
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/") and base:
        return base.rstrip("/") + u
    return u if u.startswith("http") else ""


def _bajar_imagen(url, referer=""):
    try:
        h = dict(_UA_IMG)
        if referer:
            h["Referer"] = referer
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code == 200 and len(r.content) > 3000 and "image" in r.headers.get("content-type", "image"):
            return r.content
    except Exception:
        pass
    return None


def _og_image(url_producto):
    """Foto principal de la página del producto (etiqueta og:image), por si la tarjeta no traía imagen."""
    try:
        r = requests.get(url_producto, headers={**_UA_IMG, "Accept": "text/html,*/*"}, timeout=15)
        if r.status_code != 200:
            return ""
        m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', r.text) or \
            re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', r.text)
        return url_absoluta(html.unescape(m.group(1))) if m else ""
    except Exception:
        return ""


def tg_send_foto_bytes(chat_id, caption, datos, parse_mode=None):
    if not chat_id or not TELEGRAM_TOKEN or not datos:
        return None
    data = {"chat_id": chat_id, "caption": caption[:1024]}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if _es_vip(chat_id):
        data["protect_content"] = "true"
    try:
        r = requests.post(f"{TG}/sendPhoto", data=data, files={"photo": ("oferta.jpg", datos)}, timeout=30).json()
        if r.get("ok"):
            return r["result"]["message_id"]
        logger.warning(f"[TG foto] {r.get('description', '?')}")
    except Exception as ex:
        logger.warning(f"[TG foto] {ex}")
    return None


def enviar_payload(chat_id, p):
    """Mensaje ya formateado. Orden: foto por URL -> foto descargada -> foto de la página del producto ->
    tarjeta generada -> (último recurso) solo texto. Si Telegram rechaza el formato, reintenta sin formato."""
    modo = p.get("modo") or None
    texto = p.get("texto") or ""
    caption = p.get("caption") or texto[:1024]
    it = p.get("item") or {}
    plano_tx = re.sub(r"[*_`\[\]]", "", texto)
    plano_cap = re.sub(r"[*_`\[\]]", "", caption)

    def intento_foto(url):
        if not url:
            return None
        mid = tg_send(chat_id, caption, parse_mode=modo, foto=url, solo_foto=True)
        if not mid and modo:
            mid = tg_send(chat_id, plano_cap, parse_mode=None, foto=url, solo_foto=True)
        return mid

    foto = url_absoluta(p.get("foto"), "")
    fuentes = [foto] if foto else []
    mid = intento_foto(foto) if foto else None
    if mid:
        return mid
    if foto:                                           # la tienda no deja que Telegram la baje: la bajamos nosotros
        datos = _bajar_imagen(foto, it.get("url") or "")
        if datos:
            mid = tg_send_foto_bytes(chat_id, caption, datos, modo) or tg_send_foto_bytes(chat_id, plano_cap, datos, None)
            if mid:
                return mid
    if it.get("url"):                                  # foto principal de la página del producto
        og = _og_image(it["url"])
        if og and og not in fuentes:
            mid = intento_foto(og)
            if mid:
                return mid
            datos = _bajar_imagen(og, it["url"])
            if datos:
                mid = tg_send_foto_bytes(chat_id, caption, datos, modo) or tg_send_foto_bytes(chat_id, plano_cap, datos, None)
                if mid:
                    return mid
    try:                                               # tarjeta generada con nombre, precio y descuento
        import imagenes
        datos = imagenes.tarjeta(it.get("nombre", ""), it.get("precio_actual") or p.get("precio") or 0,
                                 it.get("precio_original") or 0, it.get("descuento") or p.get("descuento") or 0,
                                 it.get("tienda", ""))
        if datos:
            mid = tg_send_foto_bytes(chat_id, caption, datos, modo) or tg_send_foto_bytes(chat_id, plano_cap, datos, None)
            if mid:
                return mid
    except Exception as ex:
        logger.warning(f"[FOTO] tarjeta: {ex}")
    mid = tg_send(chat_id, texto, parse_mode=modo)
    if not mid and modo:
        mid = tg_send(chat_id, plano_tx, parse_mode=None)
    return mid
