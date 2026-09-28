# =============================================================
# DROPNODE MX — cupon_monitor.py
# Detección automática de cupones de afiliado ML
# Corre cada hora — si encuentra cupón nuevo, lo publica
# automáticamente en VIP y free sin intervención manual
# =============================================================

import os, requests, time, logging, random
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN","").strip()
CHANNEL_VIP_ID  = int(os.environ.get("CHANNEL_VIP_ID","0"))
CHANNEL_FREE_ID = int(os.environ.get("CHANNEL_FREE_ID","0"))
LAUNCHPASS_LINK = os.environ.get("LAUNCHPASS_LINK","").strip()
ML_AFFILIATE_ID = os.environ.get("ML_AFFILIATE_ID","").strip()
SUPABASE_URL    = os.environ.get("SUPABASE_URL","").strip()
SUPABASE_KEY    = os.environ.get("SUPABASE_KEY","").strip()
API             = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# ─────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────

def _db():
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None

def _cupon_ya_publicado(codigo: str) -> bool:
    db = _db()
    if not db:
        return False
    try:
        r = db.table("cupones_publicados").select("id").eq(
            "codigo", codigo).execute()
        return len(r.data) > 0
    except Exception:
        return False

def _marcar_publicado(codigo: str, descuento: int, origen: str):
    db = _db()
    if not db:
        return
    try:
        db.table("cupones_publicados").insert({
            "codigo":    codigo,
            "descuento": descuento,
            "origen":    origen,
            "timestamp": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logger.warning(f"[CUPON DB] {e}")

# ─────────────────────────────────────────────
# DETECCIÓN DE CUPONES — múltiples fuentes
# ─────────────────────────────────────────────

def _headers():
    return {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/124.0.0.0",
        "Accept":     "application/json",
        "Accept-Language": "es-MX,es;q=0.9",
    }

def _detectar_cupones_ml_api() -> list:
    """
    Endpoint público de ML para cupones de afiliado.
    Retorna lista de {codigo, descuento_pct, vencimiento, categoria}
    """
    cupones = []
    endpoints = [
        # Cupones del programa de afiliados ML
        f"https://api.mercadolibre.com/affiliate/coupons?affiliate_id={ML_AFFILIATE_ID}",
        # Promociones públicas de ML México
        "https://api.mercadolibre.com/sites/MLM/promotions",
        # Cupones activos para compradores
        "https://api.mercadolibre.com/sites/MLM/coupon_campaigns",
    ]
    for url in endpoints:
        try:
            r = requests.get(url, headers=_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                # Normalizar respuesta según el endpoint
                if isinstance(data, list):
                    for item in data:
                        c = _normalizar_cupon(item)
                        if c:
                            cupones.append(c)
                elif isinstance(data, dict):
                    for item in data.get("coupons", data.get("campaigns", [])):
                        c = _normalizar_cupon(item)
                        if c:
                            cupones.append(c)
        except Exception as e:
            logger.debug(f"[CUPON API] {url}: {e}")
    return cupones

def _detectar_cupones_pagina_afiliados() -> list:
    """
    Scrape de la página de cupones del programa de afiliados ML.
    Funciona aunque la API no esté disponible.
    """
    cupones = []
    urls = [
        "https://www.mercadolibre.com.mx/cupon-afiliados",
        f"https://partners.mercadolibre.com.mx/affiliate/{ML_AFFILIATE_ID}/coupons",
    ]
    for url in urls:
        try:
            from bs4 import BeautifulSoup
            r = requests.get(url, headers=_headers(), timeout=15)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            # Buscar códigos de cupón en la página
            import re
            codigos = re.findall(r'\b([A-Z]{5,20})\b', r.text)
            pcts    = re.findall(r'(\d{1,2})%\s*(?:OFF|descuento|off)', r.text, re.I)
            for i, codigo in enumerate(codigos[:3]):
                pct = int(pcts[i]) if i < len(pcts) else 10
                cupones.append({
                    "codigo":    codigo,
                    "descuento": pct,
                    "origen":    "pagina_afiliados",
                })
        except Exception as e:
            logger.debug(f"[CUPON PAGE] {url}: {e}")
    return cupones

def _normalizar_cupon(item: dict) -> dict | None:
    """Convierte respuesta de API al formato interno."""
    try:
        codigo = (item.get("code") or item.get("coupon_code") or
                  item.get("codigo") or "")
        desc   = int(item.get("discount_percentage") or
                     item.get("discount") or
                     item.get("descuento") or 0)
        if not codigo or desc <= 0:
            return None
        return {
            "codigo":     codigo.upper().strip(),
            "descuento":  desc,
            "categoria":  item.get("category_name", "todas las categorías"),
            "vencimiento": item.get("expire_date") or item.get("end_date") or "",
            "origen":     "ml_api",
        }
    except Exception:
        return None

def detectar_cupones_nuevos() -> list:
    """
    Combina todas las fuentes de detección.
    Solo retorna cupones que NO han sido publicados antes.
    """
    todos = []
    todos.extend(_detectar_cupones_ml_api())
    todos.extend(_detectar_cupones_pagina_afiliados())

    # Dedup por código
    vistos = set()
    nuevos = []
    for c in todos:
        codigo = c.get("codigo","").upper()
        if codigo and codigo not in vistos:
            vistos.add(codigo)
            if not _cupon_ya_publicado(codigo):
                nuevos.append(c)

    logger.info(f"[CUPON] {len(todos)} detectados, {len(nuevos)} nuevos")
    return nuevos

# ─────────────────────────────────────────────
# PUBLICACIÓN AUTOMÁTICA
# ─────────────────────────────────────────────

def _enviar_vip(texto):
    try:
        requests.post(f"{API}/sendMessage", json={
            "chat_id":    CHANNEL_VIP_ID,
            "text":       texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=15)
    except Exception as e:
        logger.error(f"[CUPON VIP] {e}")

def _enviar_free(texto):
    try:
        payload = {
            "chat_id":    CHANNEL_FREE_ID,
            "text":       texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if LAUNCHPASS_LINK:
            payload["reply_markup"] = {"inline_keyboard": [[{
                "text": "📲 Ver cupón completo en Canal VIP",
                "url":  LAUNCHPASS_LINK
            }]]}
        requests.post(f"{API}/sendMessage", json=payload, timeout=15)
    except Exception as e:
        logger.error(f"[CUPON FREE] {e}")

def publicar_cupon(cupon: dict):
    """Publica un cupón en VIP (inmediato) y free (10 min después)."""
    codigo    = cupon["codigo"]
    desc      = cupon["descuento"]
    cat       = cupon.get("categoria", "todas las categorías")
    venc      = cupon.get("vencimiento","")
    venc_txt  = f"\n_Válido hasta: {venc}_" if venc else ""

    # ── VIP: código completo + guía de máximo aprovechamiento ──
    msg_vip = (
        f"🎟️ *CUPÓN DETECTADO — Canal VIP*\n\n"
        f"Código: `{codigo}`\n"
        f"*+{desc}% OFF* en {cat}\n"
        f"{venc_txt}\n\n"
        f"*Cómo maximizarlo:*\n"
        f"1. Busca un producto con descuento activo en el canal\n"
        f"2. Agrega al carrito en ML\n"
        f"3. Aplica este cupón al pagar\n"
        f"4. Combínalo con tu cupón bancario para el precio mínimo absoluto\n\n"
        f"_Detectado automáticamente por nuestro sistema._"
    )
    _enviar_vip(msg_vip)
    _marcar_publicado(codigo, desc, cupon.get("origen","auto"))
    logger.info(f"[CUPON] Publicado en VIP: {codigo} -{desc}%")

    # Esperar antes de enviar al free
    time.sleep(600)  # 10 minutos

    # ── Free: FOMO sin revelar el código ──
    msg_free = (
        f"🎟️ <b>Cupón de afiliado activo</b>\n\n"
        f"Nuestro sistema detectó un cupón de <b>+{desc}% OFF adicional</b> "
        f"en {cat}.\n\n"
        f"<i>Los miembros del Canal VIP ya lo tienen con la guía de cómo "
        f"combinarlo con descuentos y cupones bancarios para el precio más bajo.</i>"
    )
    _enviar_free(msg_free)
    logger.info(f"[CUPON] Publicado en free: {codigo}")

def ejecutar_monitor_cupones():
    """
    Punto de entrada — llamar desde main.py cada hora.
    Solo actúa si hay cupones nuevos, sin intervención manual.
    """
    try:
        nuevos = detectar_cupones_nuevos()
        for cupon in nuevos[:2]:  # Max 2 cupones por run
            publicar_cupon(cupon)
    except Exception as e:
        logger.error(f"[CUPON MONITOR] {e}")

# ─────────────────────────────────────────────
# SQL — ejecutar en Supabase una sola vez
# CREATE TABLE IF NOT EXISTS cupones_publicados (
#     id        BIGSERIAL PRIMARY KEY,
#     codigo    TEXT UNIQUE NOT NULL,
#     descuento INT DEFAULT 0,
#     origen    TEXT,
#     timestamp TIMESTAMPTZ DEFAULT NOW()
# );
# ─────────────────────────────────────────────
