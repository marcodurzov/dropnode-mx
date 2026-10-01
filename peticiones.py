# =============================================================
# DROPNODE MX — peticiones.py  (v2.0)
# Peticiones de la comunidad -> alerta VIP "Pedido por la comunidad"
# CAMBIOS v2 (GitHub Actions no conserva variables entre corridas):
#   - La ventana del lunes se calcula por HORA, no con una bandera en memoria
#   - Las peticiones se guardan vía registrar_peticion() (Supabase)
#   - buscar_ahora(): busca el producto pedido en ese momento (no espera a
#     que un scraper lo encuentre por casualidad)
#   - Respeta horario VIP / modo nocturno; HTML seguro
# =============================================================
import re, logging
from datetime import datetime

import estado as E
import horarios as H
import temporada_calendario as T

logger = logging.getLogger(__name__)
_cache = {"t": 0, "rows": None}

IGNORAR = {"para", "quiero", "busco", "algo", "como", "unos", "unas", "este", "esta", "buen", "buena",
           "precio", "barato", "barata", "oferta", "descuento", "tiene", "favor", "algun", "alguna",
           "donde", "cual", "cuando", "necesito", "comprar", "alguien", "pedir", "sobre", "gracias"}


def _semana():
    return H.ahora().isocalendar()[1]


def _tokens(txt):
    return [w for w in re.findall(r"[a-z0-9]{4,}", T.normalizar(txt)) if w not in IGNORAR]


def ventana_activa():
    """Lunes de 10:00 a 13:59 (hora México)."""
    a = H.ahora()
    return a.weekday() == 0 and 10 <= a.hour < 14


# Compatibilidad con código anterior (ya no hacen falta)
def abrir_ventana(): pass
def cerrar_ventana(): pass


def registrar_peticion(texto, user_id, username):
    db = E.get_db()
    texto = (texto or "").strip()[:200]
    if not db or len(texto) < 3:
        return None
    try:
        r = db.table("peticiones").insert({"texto": texto, "user_id": user_id,
                                           "username": username or "", "semana": _semana()}).execute()
        _cache["rows"] = None
        return r.data[0]["id"] if r.data else True
    except Exception as e:
        logger.warning(f"[PETICIONES] guardar: {e}")
        return None


def contar_semana():
    db = E.get_db()
    if not db:
        return 0
    try:
        r = db.table("peticiones").select("id", count="exact").eq("semana", _semana()).execute()
        return r.count or 0
    except Exception:
        return 0


def _pendientes():
    if _cache["rows"] is not None:
        return _cache["rows"]
    db = E.get_db()
    rows = []
    if db:
        try:
            r = db.table("peticiones").select("id,texto").eq("semana", _semana()) \
                .eq("encontrada", False).limit(200).execute()
            rows = r.data or []
        except Exception:
            rows = []
    _cache["rows"] = rows
    return rows


def get_peticiones_como_keywords():
    return [p["texto"] for p in _pendientes()]


def verificar_match(nombre_producto, url_producto, precio, descuento=None):
    """Llamar desde los scrapers por cada producto. True si disparó una alerta."""
    pend = _pendientes()
    if not pend:
        return False
    prod = set(_tokens(nombre_producto))
    for p in pend:
        pet = set(_tokens(p["texto"]))
        if not pet:
            continue
        comunes = prod & pet
        if len(comunes) >= 2 or (len(pet) == 1 and comunes):
            if _disparar_alertas(p, nombre_producto, url_producto, precio, descuento):
                _marcar_encontrada(p["id"], nombre_producto, url_producto)
                _cache["rows"] = [x for x in pend if x["id"] != p["id"]]
                return True
    return False


def buscar_ahora(texto):
    """Busca YA el producto pedido en ML y, si hay oferta real, avisa al VIP."""
    try:
        import ml_api
        toks = set(_tokens(texto))
        mejor = None
        for it in ml_api.buscar(texto, limit=40):
            precio = float(it.get("price") or 0)
            orig = float(it.get("original_price") or 0)
            if precio <= 0 or orig <= precio:
                continue
            desc = (orig - precio) / orig
            if desc < 0.20 or not it.get("permalink"):
                continue
            comunes = toks & set(_tokens(it.get("title", "")))
            if len(comunes) < min(2, len(toks)):
                continue
            if not mejor or desc > mejor[0]:
                mejor = (desc, it, precio)
        if not mejor:
            return False
        desc, it, precio = mejor
        pet = {"id": None, "texto": texto}
        if _disparar_alertas(pet, it.get("title", ""), E.link_afiliado(it["permalink"]), precio, desc):
            _marcar_por_texto(texto, it.get("title", ""), it["permalink"])
            return True
    except Exception as e:
        logger.warning(f"[PETICIONES] buscar_ahora: {e}")
    return False


def _marcar_encontrada(pid, producto, url):
    db = E.get_db()
    if not db or not pid:
        return
    try:
        db.table("peticiones").update({"encontrada": True, "procesada": True,
                                       "producto": producto[:200], "producto_url": url}).eq("id", pid).execute()
    except Exception:
        pass


def _marcar_por_texto(texto, producto, url):
    db = E.get_db()
    if not db:
        return
    try:
        db.table("peticiones").update({"encontrada": True, "procesada": True, "producto": producto[:200],
                                       "producto_url": url}).eq("texto", texto[:200]).eq("semana", _semana()).execute()
    except Exception:
        pass


def _categoria_vaga(nombre):
    n = T.normalizar(nombre)
    for claves, txt in [(("iphone", "samsung", "celular", "smartphone", "redmi", "xiaomi"), "un celular con buena oferta"),
                        (("laptop", "lenovo", "dell", "asus", "macbook"), "una laptop con descuento"),
                        (("tv", "televisor", "pantalla", "oled"), "un televisor en oferta"),
                        (("audifonos", "airpods", "bocina"), "audífonos o bocinas con precio bajo"),
                        (("consola", "playstation", "xbox", "nintendo"), "una consola o videojuego"),
                        (("tablet", "ipad"), "una tablet en oferta")]:
        if any(c in n for c in claves):
            return txt
    return "un producto que estaban buscando"


def _disparar_alertas(peticion, nombre, url, precio, descuento=None):
    """VIP: alerta completa con etiqueta. Free: FOMO sin revelar el producto (solo en horario free)."""
    desc = descuento if descuento is not None else 0.0
    if not H.en_horario_vip() and desc < 0.5:
        return False                                   # de noche solo si es realmente excepcional
    vip = E.cfg_int("CHANNEL_VIP_ID")
    txt = (f"🎯 <b>Pedido por la comunidad — encontrado</b>\n\n<b>{E.esc(nombre[:70])}</b>\n\n"
           f"<b>${precio:,.0f} MXN</b>" + (f" (-{desc*100:.0f}%)" if desc else "") +
           f"\n\n<a href=\"{E.link_afiliado(url)}\">COMPRAR AHORA</a>")
    if not E.tg_send(vip, txt):
        return False
    if H.en_horario_free() and E.reclamar_evento(f"pet_free:{H.fecha_mx()}:{H.ahora().hour}", fallback=False):
        E.tg_send(E.cfg_int("CHANNEL_FREE_ID"),
                  f"🎯 <b>La comunidad lo pidió — el equipo lo encontró.</b>\n\n"
                  f"Alguien buscaba <i>{_categoria_vaga(nombre)}</i>. El resultado ya está en el Canal VIP.",
                  boton=("📲 Ver en Canal VIP", E.cfg("LAUNCHPASS_LINK")))
    return True
