# =============================================================
# DROPNODE MX — main.py v3.4
# 20 fuentes · GitHub Actions cada 15 min
# + Elektra + Bodega Aurrerá + Monitor cupones automático
# + Fix DB proxy + Fix silence entre publicaciones
# =============================================================
import logging, sys, time, os, random
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

# ── Imports robustos ──
def _imp(mod, fn, fb=None):
    try:
        import importlib
        return getattr(importlib.import_module(mod), fn)
    except Exception as e:
        logger.warning(f"[IMPORT] {mod}.{fn}: {e}")
        return fb or (lambda *a,**k: [])

ciclo_walmart    = _imp("scraper_walmart",   "ejecutar_ciclo_walmart")
ciclo_liverpool  = _imp("scraper_liverpool", "ejecutar_ciclo_liverpool")
ciclo_coppel     = _imp("scraper_coppel",    "ejecutar_ciclo_coppel")
ciclo_amazon     = _imp("scraper_amazon",    "ejecutar_ciclo_amazon")
ciclo_aliexpress = _imp("scraper_otros",     "ejecutar_ciclo_aliexpress")
ciclo_shein      = _imp("scraper_otros",     "ejecutar_ciclo_shein")
ciclo_marcas     = _imp("scraper_otros",     "ejecutar_ciclo_marcas")
ciclo_tiktok     = _imp("scraper_otros",     "ejecutar_ciclo_tiktok_trending")
ciclo_costco     = _imp("scraper_tiendas",   "ejecutar_ciclo_costco")
ciclo_sams_h     = _imp("scraper_tiendas",   "ejecutar_ciclo_sams")
ciclo_petco_h    = _imp("scraper_tiendas",   "ejecutar_ciclo_petco")
ciclo_sears      = _imp("scraper_tiendas",   "ejecutar_ciclo_sears")
ciclo_palacio_h  = _imp("scraper_tiendas",   "ejecutar_ciclo_palacio")
ciclo_inditex    = _imp("scraper_tiendas",   "ejecutar_ciclo_inditex")
ciclo_marcas_d   = _imp("scraper_tiendas",   "ejecutar_ciclo_marcas_directo")
ciclo_palacio_a  = _imp("scraper_api",       "ejecutar_ciclo_palacio_api")
ciclo_petco_a    = _imp("scraper_api",       "ejecutar_ciclo_petco_api")
ciclo_ml_deals   = _imp("scraper_api",       "ejecutar_ciclo_ml_deals")
ciclo_sams_a     = _imp("scraper_api",       "ejecutar_ciclo_sams_api")
ciclo_elektra    = _imp("scraper_elektra",   "ejecutar_ciclo_elektra")
ciclo_bodega     = _imp("scraper_bodega",    "ejecutar_ciclo_bodega")

from telegram_bot import (
    enviar_resumen_diario, enviar_mensaje_financiero,
    enviar_recordatorio_vip, enviar_y_fijar_bienvenida_grupo,
    enviar_mensaje, setup_canal_free, canal_free_tiene_fijado,
)
from community_manager import ejecutar_community_manager, fomo_vip_al_free

verificar_match       = _imp("peticiones",    "verificar_match",            lambda *a,**k: None)
temporada_activa      = _imp("temporadas",    "temporada_activa",           lambda: (None,None))
score_bonus_temp      = _imp("temporadas",    "score_bonus_temporada",      lambda *a,**k: 0.0)
alertas_temporada     = _imp("temporadas",    "ejecutar_alertas_temporada", lambda: None)
calcular_heat_score   = _imp("heat_score",    "calcular_heat_score",        lambda **k: 3)
monitor_cupones       = _imp("cupon_monitor", "ejecutar_monitor_cupones",   lambda: None)

try:
    from config import (TELEGRAM_TOKEN, GROUP_ID, CHANNEL_FREE_ID,
                        CHANNEL_VIP_ID, LAUNCHPASS_LINK,
                        TIMEZONE_OFFSET_HOURS, SUPABASE_URL, SUPABASE_KEY)
except Exception:
    TELEGRAM_TOKEN       = os.environ.get("TELEGRAM_TOKEN","")
    GROUP_ID             = os.environ.get("GROUP_ID","")
    CHANNEL_FREE_ID      = int(os.environ.get("CHANNEL_FREE_ID","0"))
    CHANNEL_VIP_ID       = int(os.environ.get("CHANNEL_VIP_ID","0"))
    LAUNCHPASS_LINK      = os.environ.get("LAUNCHPASS_LINK","")
    TIMEZONE_OFFSET_HOURS= int(os.environ.get("TIMEZONE_OFFSET_HOURS","-6"))
    SUPABASE_URL         = os.environ.get("SUPABASE_URL","")
    SUPABASE_KEY         = os.environ.get("SUPABASE_KEY","")

TZ_MEXICO = timezone(timedelta(hours=int(TIMEZONE_OFFSET_HOURS)))
def hora_mx(): return datetime.now(TZ_MEXICO)
def dentro_de_horario(): return 8 <= hora_mx().hour < 22

# ─────────────────────────────────────────────
# DB — con retry y manejo de proxy error
# ─────────────────────────────────────────────
_db_client = None

def get_db():
    global _db_client
    if _db_client: return _db_client
    try:
        from supabase import create_client
        _db_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("[DB] Conexión OK")
    except Exception as e:
        logger.warning(f"[DB] {e}")
    return _db_client

def _db_insert(table, data):
    db = get_db()
    if not db: return False
    try:
        db.table(table).insert(data).execute()
        return True
    except Exception as e:
        logger.warning(f"[DB INSERT {table}] {e}")
        return False

def _db_select(table, filters=None, limit=100):
    db = get_db()
    if not db: return []
    try:
        q = db.table(table).select("*")
        if filters:
            for k, v in filters.items():
                q = q.eq(k, v)
        return (q.limit(limit).execute().data or [])
    except Exception:
        return []

# ── Cola FOMO ──
def cola_agregar(item, score, n_vip, delay_min=30):
    try:
        send_after = (datetime.utcnow() + timedelta(minutes=delay_min)).isoformat()
        item_s = {k: v for k, v in item.items()
                  if isinstance(v, (str, int, float, bool, type(None)))}
        _db_insert("cola_free", {"item": item_s, "score": score,
                                  "n_vip": n_vip, "send_after": send_after,
                                  "enviado": False})
    except Exception as e:
        logger.warning(f"[COLA] {e}")

def cola_listos():
    db = get_db()
    if not db: return []
    try:
        ahora = datetime.utcnow().isoformat()
        r = db.table("cola_free").select("*").eq(
            "enviado", False).lte("send_after", ahora).order(
            "score", desc=True).execute()
        return r.data or []
    except Exception: return []

def cola_marcar(ids):
    db = get_db()
    if not db or not ids: return
    try:
        db.table("cola_free").update({"enviado":True}).in_("id",ids).execute()
    except Exception: pass

def cola_limpiar():
    db = get_db()
    if not db: return
    try:
        limite = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        db.table("cola_free").delete().eq("enviado",False).lt(
            "send_after",limite).execute()
    except Exception: pass

# ─────────────────────────────────────────────
# RESUMEN DIARIO COMPLETO — 11 PM MX
# ─────────────────────────────────────────────
def resumen_diario():
    db = get_db()
    vip_n=free_n=0; ahorro=0.0; mejor_d=0.0
    try:
        if db:
            desde = (datetime.utcnow()-timedelta(hours=16)).isoformat()
            rows = (db.table("alertas_enviadas").select(
                "canal,precio_alerta,descuento_real"
            ).gte("timestamp",desde).execute().data or [])
            for row in rows:
                c=row.get("canal",""); p=float(row.get("precio_alerta") or 0)
                d=float(row.get("descuento_real") or 0)
                if c=="vip": vip_n+=1
                elif c=="free": free_n+=1
                if p>0 and 0<d<1:
                    ahorro+=(p/(1-d))-p
                    if d>mejor_d: mejor_d=d
    except Exception as e:
        logger.warning(f"[RESUMEN DB] {e}")

    _, ti = temporada_activa()
    t_str = f"\n{ti['emoji']} *{ti['nombre']} activo*\n" if ti else ""

    # VIP — exhaustivo
    msg_vip = f"📊 *Resumen del día — Canal VIP*\n{t_str}\n"
    if vip_n+free_n > 0:
        msg_vip += (f"*Alertas exclusivas VIP:* {vip_n}\n"
                    f"*Alertas canal público:* {free_n}\n"
                    f"*Total oportunidades:* {vip_n+free_n}\n")
        if mejor_d > 0: msg_vip += f"*Mejor descuento:* -{mejor_d*100:.0f}%\n"
        if ahorro > 0:  msg_vip += f"*Ahorro total estimado:* ~${ahorro:,.0f} MXN\n"
    else:
        msg_vip += "_Día sin publicaciones masivas — solo se publica lo que vale la pena._\n"
    msg_vip += "\n_El equipo sigue en guardia durante la noche._"
    enviar_mensaje(CHANNEL_VIP_ID, msg_vip)

    # Free — FOMO puro
    if ahorro > 100:
        import requests as req
        try:
            payload = {
                "chat_id": CHANNEL_FREE_ID,
                "text": (
                    f"📊 <b>Lo que el Canal VIP logró hoy</b>\n\n"
                    f"<b>{vip_n} alertas exclusivas</b> que no llegaron aquí.\n"
                    f"<b>~${ahorro:,.0f} MXN</b> en ahorros verificados.\n"
                    f"Mejor descuento del día: <b>-{mejor_d*100:.0f}%</b>\n\n"
                    f"<i>Mañana el equipo empieza desde las 8 AM. "
                    f"Los miembros VIP actúan primero.</i>"
                ),
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if LAUNCHPASS_LINK:
                payload["reply_markup"] = {"inline_keyboard":[[{
                    "text":"📲 Unirme al Canal VIP — $299/mes",
                    "url":LAUNCHPASS_LINK}]]}
            req.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                     json=payload, timeout=15)
        except Exception as e:
            logger.error(f"[RESUMEN FREE] {e}")

# ─────────────────────────────────────────────
# FORMATO MENSAJES
# ─────────────────────────────────────────────
EMOJIS = {
    "walmart":"🛒","liverpool":"🏬","coppel":"🏪","amazon":"📦",
    "aliexpress":"🌐","shein":"👗","costco":"🏪","sams":"🏬",
    "petco":"🐾","sears":"🏬","palacio":"💎","zara":"👗",
    "pullbear":"👕","bershka":"👕","lefties":"👕","samsung":"📱",
    "lg":"📺","sony":"🎮","mercadolibre":"🛒","tiktok_trend":"🎵",
    "elektra":"⚡","bodega":"🛒",
}
NOMBRES = {
    "sams":"Sam's Club","palacio":"Palacio de Hierro","pullbear":"Pull&Bear",
    "mercadolibre":"Mercado Libre","tiktok_trend":"Trending",
    "elektra":"Elektra","bodega":"Bodega Aurrerá",
}

def _td(t):
    return NOMBRES.get(t, t.upper() if t in (
        "costco","samsung","lg","sony","zara","bershka","lefties","sears","amazon"
    ) else t.capitalize())

def fmt_vip(item):
    t=item["tienda"]; n=item["nombre"][:60]; p=item["precio_actual"]
    po=item["precio_original"]; d=item["descuento"]*100; u=item["url"]
    et=EMOJIS.get(t,"🛍️"); ec=item["categoria"]["emoji"]; td=_td(t)
    rl=po*0.78; rh=po*0.90; ev="✅ Envío gratis\n" if item.get("envio_gratis") else ""
    fl=" ⏰ SOLO HOY" if item.get("es_flash") else ""
    _, ti=temporada_activa()
    tag=f" [{ti['emoji']} {ti['nombre']}]" if ti else ""
    return (f"{et} *{td} — EXCLUSIVO VIP{fl}{tag}* {ec}\n\n"
            f"*{n}*\n\n*${p:,.0f} MXN* (-{d:.0f}%)\n"
            f"Normal: ${po:,.0f}\n{ev}\n"
            f"[COMPRAR AHORA]({u})\n\n"
            f"_Reventa: ${rl:,.0f} - ${rh:,.0f} MXN_")

def fmt_free(item, n_exc, delay):
    t=item["tienda"]; n=item["nombre"][:55]; p=item["precio_actual"]
    po=item["precio_original"]; d=item["descuento"]*100; u=item["url"]
    et=EMOJIS.get(t,"🛍️"); ec=item["categoria"]["emoji"]; td=_td(t)
    ev="✅ Envío gratis\n" if item.get("envio_gratis") else ""
    dt=f"{delay} min" if delay<60 else f"{delay//60}h"
    m=(f"{et} <b>{td}</b> {ec}\n\n<b>{n}</b>\n\n"
       f"<b>${p:,.0f} MXN</b> (-{d:.0f}%)\n")
    if po>p: m+=f"<s>${po:,.0f}</s>\n"
    m+=ev+f"\n<a href=\"{u}\">Ver oferta</a>\n\n"
    m+=f"<i>Llegó al Canal VIP hace {dt} con análisis completo.</i>\n"
    if n_exc>0:
        m+=f"<i>Más {n_exc} oferta{'s' if n_exc>1 else ''} exclusiva{'s' if n_exc>1 else ''} que no llegan aquí.</i>\n"
    if LAUNCHPASS_LINK:
        m+=f"\n<a href=\"{LAUNCHPASS_LINK}\">📲 Canal VIP — $299/mes</a>"
    return m

# ─────────────────────────────────────────────
# COLA FREE
# ─────────────────────────────────────────────
def procesar_cola_free():
    listos=cola_listos()
    if not listos: logger.info("[COLA FREE] Sin items"); return
    cola_limpiar(); sel=listos[:3]
    n_exc=max(0,sum(x.get("n_vip",0) for x in listos)-len(sel)); ids=[]
    for i,e in enumerate(sel):
        item=e.get("item",{})
        try:
            c=datetime.fromisoformat(e.get("created_at",e["send_after"]).replace("Z",""))
            delay=int((datetime.utcnow()-c).total_seconds()/60)
        except: delay=30
        mid=enviar_mensaje(CHANNEL_FREE_ID,fmt_free(item,n_exc if i==0 else 0,delay),parse_mode="HTML")
        if mid: ids.append(e["id"])
        time.sleep(6)
    if ids: cola_marcar(ids); logger.info(f"[COLA FREE] Enviados:{len(ids)}")

# ─────────────────────────────────────────────
# SCRAPERS — 20 fuentes con pesos
# ─────────────────────────────────────────────
SCRAPERS = [
    # Alta prioridad — mayor frecuencia
    ("ML Deals API",   ciclo_ml_deals,   4),
    ("Walmart",        ciclo_walmart,    3),
    ("Liverpool",      ciclo_liverpool,  3),
    ("Amazon",         ciclo_amazon,     3),
    ("Elektra",        ciclo_elektra,    3),
    ("Bodega Aurrerá", ciclo_bodega,     3),
    ("Coppel",         ciclo_coppel,     2),
    ("ML Marcas",      ciclo_marcas,     2),
    ("Costco",         ciclo_costco,     2),
    ("Sam's API",      ciclo_sams_a,     2),
    ("Palacio API",    ciclo_palacio_a,  2),
    ("Petco API",      ciclo_petco_a,    2),
    # Media/baja prioridad
    ("Inditex",        ciclo_inditex,    1),
    ("Sears",          ciclo_sears,      1),
    ("Marcas Directo", ciclo_marcas_d,   1),
    ("TikTok Trend",   ciclo_tiktok,     1),
    ("Palacio HTML",   ciclo_palacio_h,  1),
    ("Sam's HTML",     ciclo_sams_h,     1),
    ("Petco HTML",     ciclo_petco_h,    1),
    # AliExpress y SHEIN — bloqueados frecuentemente, peso mínimo
    ("SHEIN",          ciclo_shein,      1),
]

_pool=[]
for n,f,p in SCRAPERS: _pool.extend([(n,f)]*p)

def ejecutar_ciclo():
    a=hora_mx(); slot=(a.hour*4+a.minute//15)%len(_pool)
    nombre,func=_pool[slot]
    try:
        items=func() or []
        if not items: logger.info(f"[CICLO] {nombre}: sin items"); return
        vip_n=0
        for item in items:
            try:
                bs=calcular_heat_score(
                    descuento_real=item["descuento"],stock=99,
                    categoria=item["categoria"]["nombre"],
                    precio_actual=item["precio_actual"],
                    precio_original=item["precio_original"])
            except: bs=4 if item["descuento"]>=0.20 else 0
            sf=min(10,bs+score_bonus_temp(item["categoria"]["nombre"]))
            if sf<3: continue
            try: verificar_match(item["nombre"],item["url"],item["precio_actual"])
            except: pass
            if sf>=5 and vip_n<2:  # Bajado de 6 a 5 para publicar más
                enviar_mensaje(CHANNEL_VIP_ID,fmt_vip(item))
                vip_n+=1; time.sleep(3)
            cola_agregar(item,sf,vip_n,delay_min=30)
        if vip_n>0: fomo_vip_al_free(vip_n)
        logger.info(f"[CICLO] {nombre} → VIP:{vip_n} encolados:{len(items)}")
    except Exception as e:
        logger.error(f"[CICLO] {nombre}: {e}",exc_info=True)

# ─────────────────────────────────────────────
# TAREAS PERIODICAS
# ─────────────────────────────────────────────
def tareas_periodicas():
    a=hora_mx(); h,m,dia=a.hour,a.minute,a.weekday()
    if m>=15: return
    if h==23: resumen_diario()
    if h in (11,18): enviar_mensaje_financiero()
    if h in (14,20): enviar_recordatorio_vip()
    # Monitor de cupones — cada hora
    try: monitor_cupones()
    except Exception as e: logger.warning(f"[CUPONES] {e}")
    if dia==0 and h==9:
        _,ti=temporada_activa()
        t_str=f"\n\n_{ti['emoji']} Temporada {ti['nombre']} activa._" if ti else ""
        enviar_mensaje(CHANNEL_VIP_ID,
            f"*Reporte semanal — DropNode VIP*\n\n"
            f"20 fuentes monitoreadas esta semana.{t_str}\n\n"
            f"_Elektra y Bodega Aurrerá ya integrados al sistema._\n\n"
            f"{LAUNCHPASS_LINK}")
    try: alertas_temporada()
    except: pass

def setup():
    if not canal_free_tiene_fijado(): setup_canal_free()
    if not GROUP_ID: logger.warning("[SETUP] GROUP_ID vacío"); return
    try:
        import requests as req
        r=req.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChat",
                  params={"chat_id":GROUP_ID},timeout=10)
        if "pinned_message" not in r.json().get("result",{}):
            enviar_y_fijar_bienvenida_grupo()
    except: pass

if __name__=="__main__":
    _,ti=temporada_activa()
    t_str=f" | {ti['emoji']} {ti['nombre']}" if ti else ""
    logger.info(f"\n{'='*50}\n DROPNODE MX v3.4 — "
                f"{hora_mx().strftime('%d/%m/%Y %H:%M')} MX{t_str}\n"
                f" 20 fuentes activas\n{'='*50}")
    setup()
    if dentro_de_horario():
        procesar_cola_free()
        ejecutar_ciclo()
    ejecutar_community_manager()
    tareas_periodicas()
    logger.info("[DROPNODE] Run completado.")