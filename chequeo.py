# =============================================================
# DROPNODE MX — chequeo.py  (v1.0)
# "¿Está listo para operar?" — revisa en una sola pasada lo que hace
# falta antes de cobrar: token, permisos del bot, base de datos,
# secrets y qué se publicó en las últimas 24 h.
# Lo usa diagnostico.py (sección 0). Devuelve (lineas, n_fallas).
# =============================================================
import os
from datetime import datetime, timedelta

import requests

import estado as E
import horarios as H

TABLAS = ["productos", "historial_precios", "alertas_enviadas", "cola_free", "peticiones",
          "eventos_enviados", "resumenes_hist", "fuentes_log", "comunidad_posts", "comunidad_msgs",
          "comunidad_advertencias", "alertas_temporada", "cupones_publicados"]


def _tg(metodo, **params):
    try:
        return requests.get(f"{E.TG}/{metodo}", params=params, timeout=15).json()
    except Exception as e:
        return {"ok": False, "description": str(e)[:80]}


def correr():
    L, fallas = [], [0]

    def chk(ok, texto, nivel="falla"):
        if ok:
            L.append(f"✅ {texto}")
        else:
            L.append(("❌ " if nivel == "falla" else "⚠️ ") + texto)
            if nivel == "falla":
                fallas[0] += 1

    # ── Telegram ──
    me = _tg("getMe")
    bot_id = (me.get("result") or {}).get("id")
    chk(me.get("ok"), f"Token de Telegram válido (@{(me.get('result') or {}).get('username', '?')})")
    wh = _tg("getWebhookInfo")
    chk(not (wh.get("result") or {}).get("url"), "Sin webhook activo (no hay otro proceso leyendo el bot)")
    destinos = [("Canal FREE", E.cfg_int("CHANNEL_FREE_ID"), ["can_post_messages"]),
                ("Canal VIP", E.cfg_int("CHANNEL_VIP_ID"), ["can_post_messages"]),
                ("Grupo comunidad", E.cfg_int("GROUP_ID"), ["can_delete_messages", "can_restrict_members", "can_pin_messages"])]
    for nombre, cid, permisos in destinos:
        if not cid:
            chk(False, f"{nombre}: falta el ID en los secrets")
            continue
        m = _tg("getChatMember", chat_id=cid, user_id=bot_id) if bot_id else {"ok": False}
        r = m.get("result") or {}
        es_admin = r.get("status") in ("administrator", "creator")
        faltan = [p for p in permisos if not r.get(p) and r.get("status") != "creator"]
        chk(m.get("ok") and es_admin and not faltan,
            f"{nombre}: bot administrador" + (f" (faltan permisos: {', '.join(faltan)})" if faltan else "")
            + ("" if m.get("ok") else f" — {m.get('description', '')}"))

    # ── Admin privado ──
    adm = E.ADMIN_CHAT_ID
    if not adm:
        chk(False, "ADMIN_CHAT_ID no está configurado (no recibirás alertas privadas)", "aviso")
    elif str(adm).strip() == str(bot_id):
        chk(False, "ADMIN_CHAT_ID es el ID del BOT; debe ser el tuyo (escríbele /id al bot)")
    else:
        mid = E.tg_send(adm, "✅ Chequeo DropNode: este chat recibirá las alertas privadas.")
        chk(bool(mid), "ADMIN_CHAT_ID recibe mensajes")

    # ── Secrets ──
    chk(bool(E.cfg("LAUNCHPASS_LINK")), "LAUNCHPASS_LINK configurado")
    mk = os.environ.get("MAKE_WEBHOOK_URL", "").strip()
    chk(mk.startswith("https://hook."), "MAKE_WEBHOOK_URL configurado", "aviso")
    chk(bool(os.environ.get("ML_APP_ID") and os.environ.get("ML_SECRET")), "ML_APP_ID y ML_SECRET configurados", "aviso")
    chk(bool(os.environ.get("PROXY_URL", "").strip()), "PROXY_URL configurado (necesario para Walmart, Elektra, Palacio, Bodega, Coppel)", "aviso")

    # ── Base de datos ──
    db = E.get_db()
    if not db:
        chk(False, "Supabase: no se pudo crear el cliente")
    else:
        malas = []
        for t in TABLAS:
            try:
                db.table(t).select("*").limit(1).execute()
            except Exception as e:
                malas.append(t)
        chk(not malas, "Supabase: todas las tablas existen" + (f" (faltan: {', '.join(malas)})" if malas else ""))

        # ── Operación de las últimas 24 h ──
        desde = datetime.utcnow() - timedelta(hours=24)
        vip, free = E.contar_alertas("vip", desde), E.contar_alertas("free", desde)
        chk(vip > 0, f"Últimas 24 h: {vip} alertas VIP", "falla")
        chk(free > 0, f"Últimas 24 h: {free} alertas FREE", "aviso")
        try:
            pend = db.table("cola_free").select("id", count="exact").eq("enviado", False).execute().count or 0
            L.append(f"ℹ️ Cola del free: {pend} pendientes")
        except Exception:
            pass
        ayer = (H.ahora() - timedelta(days=1)).strftime("%Y-%m-%d")
        chk(E.evento_hecho(f"tp:resumen_vip:{ayer}"), f"Cierre VIP de ayer ({ayer}) publicado", "aviso")
        chk(E.evento_hecho(f"tp:resumen_free:{ayer}"), f"Cierre FREE de ayer ({ayer}) publicado", "aviso")
        s = E.salud_fuentes(24)
        vivas = sorted(n for n, (c, ok, tot) in s.items() if ok > 0)
        muertas = sorted(n for n, (c, ok, tot) in s.items() if ok == 0)
        chk(len(vivas) >= 1, f"Fuentes con productos (24 h): {', '.join(vivas) or 'ninguna'}", "falla")
        if muertas:
            L.append(f"ℹ️ Fuentes sin productos (24 h): {', '.join(muertas)}")
    return L, fallas[0]
