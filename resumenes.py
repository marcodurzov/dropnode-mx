# =============================================================
# DROPNODE MX — resumenes.py  (v1.0)
# Cierre de cada día:
#   - FREE (limitado, vende el VIP)  -> 6:00-7:00 PM
#   - VIP  (completo, con ahorro $)  -> 11:00-11:30 PM
# + Resumen semanal VIP (domingo) + reporte de salud al admin.
# Todo sale de alertas_enviadas + productos (+ resumenes_hist).
# Regla de oro: NUNCA se menciona automatización: "el equipo".
# =============================================================
import logging
from datetime import datetime, timedelta

import estado as E
import horarios as H
import temporada_calendario as T

logger = logging.getLogger(__name__)
BTN_VIP = lambda: ("📲 Canal VIP — $299/mes", E.cfg("LAUNCHPASS_LINK"))


def _mxn(x):
    return f"${x:,.0f}"


def _cargar_dia(desde_utc, hasta_utc=None):
    """Publicaciones del día: lista de dicts con nombre, tienda, categoria,
    url, precio, original, desc, score, hora(dt MX), canal."""
    db = E.get_db()
    if not db:
        return []
    try:
        def q():
            b = db.table("alertas_enviadas").select(
                "producto_id,canal,heat_score,precio_alerta,descuento_real,timestamp") \
                .gte("timestamp", desde_utc.isoformat()).in_("canal", ["vip", "free"])
            if hasta_utc:
                b = b.lt("timestamp", hasta_utc.isoformat())
            return b
        filas = E.fetch_all(q)
        ids = list({f["producto_id"] for f in filas if f.get("producto_id")})
        prods = {}
        for i in range(0, len(ids), 100):
            r = db.table("productos").select("id,nombre,url,tienda,categoria") \
                .in_("id", ids[i:i + 100]).execute()
            for p in r.data or []:
                prods[p["id"]] = p
        out = []
        for f in filas:
            p = prods.get(f.get("producto_id"))
            if not p:
                continue
            precio = float(f.get("precio_alerta") or 0)
            d = float(f.get("descuento_real") or 0)
            if precio <= 0 or not (0 < d < 0.95):
                continue
            out.append({"pid": p["id"], "nombre": p.get("nombre") or "", "tienda": p.get("tienda") or "",
                        "categoria": p.get("categoria") or "General", "url": p.get("url") or "",
                        "precio": precio, "original": precio / (1 - d), "desc": d,
                        "score": f.get("heat_score") or 0, "canal": f["canal"],
                        "hora": H.a_hora_mx(f.get("timestamp"))})
        return out
    except Exception as e:
        logger.warning(f"[RESUMEN] cargar: {e}")
        return []


def _unicos(filas):
    """Un producto = una fila (la de mayor score), sin doble conteo VIP+free."""
    m = {}
    for f in filas:
        k = f["pid"]
        if k not in m or f["score"] > m[k]["score"]:
            m[k] = f
    return list(m.values())


NOMBRE_TIENDA = {"mercadolibre": "Mercado Libre", "sams": "Sam's", "palacio": "Palacio de Hierro",
                 "heb": "HEB", "bodega": "Bodega Aurrerá", "amazon": "Amazon", "elektra": "Elektra",
                 "costco": "Costco", "walmart": "Walmart", "liverpool": "Liverpool",
                 "coppel": "Coppel", "sears": "Sears", "petco": "Petco", "tiktok_trend": "Tendencias"}


def _tienda(t):
    return NOMBRE_TIENDA.get(t, (t or "Otras").capitalize())


def _linea(i, f, detalle=True):
    nombre = E.esc(f["nombre"][:48])
    url = E.link_afiliado(f["url"])
    base = f"{i}. {nombre}\n   <b>{_mxn(f['precio'])} MXN</b> (-{f['desc']*100:.0f}%)"
    if detalle:
        base += f" · ahorras {_mxn(f['original'] - f['precio'])}"
    return base + f" · <a href=\"{url}\">Ver</a>"


# ─────────────────────────────────────────────
# FREE
# ─────────────────────────────────────────────
def resumen_free():
    ahora = H.ahora()
    filas = _cargar_dia(H.dia_inicio_utc(ahora))
    # Solo lo que ya tiene más de 1 hora publicado (coherente con la ventana VIP->Free)
    corte = ahora - timedelta(minutes=H.VENTAJA_VIP_MIN)
    elegibles = _unicos([f for f in filas if f["hora"] and f["hora"] <= corte])
    if not elegibles:
        return False
    ordenadas = sorted(elegibles, key=lambda f: f["desc"], reverse=True)
    top, cont = [], {}
    for f in ordenadas:                                   # 1ª pasada: máx. 2 por tienda (variedad)
        if cont.get(f["tienda"], 0) < 2 and len(top) < 5:
            top.append(f); cont[f["tienda"]] = cont.get(f["tienda"], 0) + 1
    for f in ordenadas:                                   # 2ª pasada: completa hasta 5
        if len(top) >= 5:
            break
        if f not in top:
            top.append(f)
    top.sort(key=lambda f: f["desc"], reverse=True)
    vip = _unicos([f for f in filas if f["canal"] == "vip"])
    ahorro = sum(f["original"] - f["precio"] for f in vip)
    m = "📋 <b>Mejores precios de hoy — DropNode MX</b>\n\n<i>Nuestro equipo revisó todo. Estos destacan:</i>\n\n"
    for f in top:
        nivel = H.nivel_emoji(f["desc"], f["score"])
        url = E.link_afiliado(f["url"])
        m += (f"{nivel} {E.esc(f['nombre'][:46])}\n<b>{_mxn(f['precio'])} MXN</b> (-{f['desc']*100:.0f}%) "
              f"<a href=\"{url}\">Ver</a>\n\n")
    if len(vip) > len(top):
        m += f"➕ <b>{len(vip) - len(top)} ofertas más</b> se publicaron hoy en el Canal VIP.\n"
    if ahorro > 500:
        m += f"💰 Ahorro acumulado hoy en el VIP: <b>~{_mxn(ahorro)} MXN</b>\n"
    m += "\n<i>Las 🔴 llegan al VIP primero; los errores de precio (🚨) se quedan solo allá.</i>\n"
    m += "<i>El VIP arranca desde las 6:30 AM y, si aparece un error de precio, también de madrugada.</i>"
    return bool(E.tg_send(E.cfg_int("CHANNEL_FREE_ID"), m, boton=BTN_VIP()))


# ─────────────────────────────────────────────
# VIP
# ─────────────────────────────────────────────
def _acum(dias):
    """Suma de ahorro de los últimos `dias` días ya cerrados (resumenes_hist)."""
    db = E.get_db()
    if not db:
        return 0.0, 0
    try:
        desde = (H.ahora() - timedelta(days=dias)).strftime("%Y-%m-%d")
        rows = E.fetch_all(lambda: db.table("resumenes_hist").select("ahorro,n_alertas").gte("fecha", desde))
        return sum(float(r.get("ahorro") or 0) for r in rows), sum(int(r.get("n_alertas") or 0) for r in rows)
    except Exception:
        return 0.0, 0


def _total_historico():
    db = E.get_db()
    if not db:
        return 0.0
    try:
        rows = E.fetch_all(lambda: db.table("resumenes_hist").select("ahorro"), max_pages=20)
        return sum(float(r.get("ahorro") or 0) for r in rows)
    except Exception:
        return 0.0


def resumen_vip():
    ahora = H.ahora()
    hoy = H.fecha_mx(ahora)
    filas = _cargar_dia(H.dia_inicio_utc(ahora))
    vip = _unicos([f for f in filas if f["canal"] == "vip"])
    if not vip:
        E.tg_send(E.cfg_int("CHANNEL_VIP_ID"),
                  f"📊 <b>Cierre del día — {H.fecha_larga(ahora)}</b>\n\n"
                  "Hoy el equipo revisó todo y no apareció nada que valiera la pena publicar. "
                  "Preferimos no publicar a publicar ruido.\n\n"
                  "🌙 Esta noche solo avisamos si aparece un error de precio (score 8+).")
        _guardar_hist(hoy, 0, 0, 0, "")
        return True

    ahorro = sum(f["original"] - f["precio"] for f in vip)
    gasto = sum(f["precio"] for f in vip)
    errores = [f for f in vip if f["score"] >= 8]
    noct = [f for f in vip if f["hora"] and (H.VIP_FIN // 60 <= f["hora"].hour or f["hora"].hour < 6
                                              or (f["hora"].hour == 6 and f["hora"].minute < 30))]
    mejor_desc = max(vip, key=lambda f: f["desc"])
    mejor_ahorro = max(vip, key=lambda f: f["original"] - f["precio"])
    top5 = sorted(vip, key=lambda f: f["original"] - f["precio"], reverse=True)[:5]
    tiendas, cats = {}, {}
    for f in vip:
        tiendas[f["tienda"]] = tiendas.get(f["tienda"], 0) + 1
        cats[f["categoria"]] = cats.get(f["categoria"], 0) + 1
    tt = sorted(tiendas.items(), key=lambda x: -x[1])[:5]
    cc = sorted(cats.items(), key=lambda x: -x[1])[:3]

    sem, _ = _acum(6)
    mes, _ = _acum(29)
    hist = _total_historico()
    ahorro_sem, ahorro_mes, ahorro_tot = sem + ahorro, mes + ahorro, hist + ahorro
    pct_medio = (ahorro / (ahorro + gasto) * 100) if (ahorro + gasto) else 0

    m = f"📊 <b>CIERRE DEL DÍA — Canal VIP</b>\n🗓 {H.fecha_larga(ahora)} · {T.etiqueta()}\n\n"
    m += f"💰 <b>AHORRO DE HOY: {_mxn(ahorro)} MXN</b>\n"
    m += f"<i>Lo que pagaste de menos frente al precio normal, sumando las {len(vip)} alertas del día.</i>\n\n"
    m += "<b>Acumulado</b>\n"
    m += f"• Semana: <b>{_mxn(ahorro_sem)}</b>\n• Últimos 30 días: <b>{_mxn(ahorro_mes)}</b>\n"
    m += f"• Desde que abrió el VIP: <b>{_mxn(ahorro_tot)}</b>\n\n"
    m += "<b>El día en números</b>\n"
    m += f"• Alertas publicadas: <b>{len(vip)}</b> · descuento promedio ponderado: <b>-{pct_medio:.0f}%</b>\n"
    m += f"• 🚨 Errores de precio (8+): <b>{len(errores)}</b>\n"
    if noct:
        m += f"• 🌙 Alertas de madrugada/noche: <b>{len(noct)}</b>\n"
    m += f"• Mayor descuento: <b>-{mejor_desc['desc']*100:.0f}%</b> — {E.esc(mejor_desc['nombre'][:40])}\n"
    m += f"• Mayor ahorro en pesos: <b>{_mxn(mejor_ahorro['original'] - mejor_ahorro['precio'])}</b> — {E.esc(mejor_ahorro['nombre'][:40])}\n"
    m += "• Tiendas: " + " · ".join(f"{_tienda(t)} {n}" for t, n in tt) + "\n"
    m += "• Categorías top: " + " · ".join(f"{E.esc(c)} {n}" for c, n in cc) + "\n\n"
    m += "🏆 <b>TOP 5 DEL DÍA (por ahorro en pesos)</b>\n\n"
    for i, f in enumerate(top5, 1):
        m += _linea(i, f) + "\n\n"
    m += f"🌙 <b>Esta noche:</b> de 11:31 PM a 6:29 AM solo publicamos errores de precio (score 8+). Mañana arrancamos a las 6:30 AM.\n"
    m += "<i>Los precios pueden cambiar sin previo aviso; verifica antes de comprar.</i>"
    ok = E.tg_send(E.cfg_int("CHANNEL_VIP_ID"), m)
    _guardar_hist(hoy, ahorro, len(vip), len(errores), mejor_desc["nombre"][:80])
    return bool(ok)


def _guardar_hist(fecha, ahorro, n, errores, mejor):
    db = E.get_db()
    if not db:
        return
    try:
        db.table("resumenes_hist").upsert({"fecha": fecha, "ahorro": round(ahorro, 2), "n_alertas": n,
                                           "errores": errores, "mejor": mejor}, on_conflict="fecha").execute()
    except Exception as e:
        logger.warning(f"[HIST] {e}")


def resumen_semanal_vip():
    db = E.get_db()
    if not db:
        return False
    try:
        desde = (H.ahora() - timedelta(days=6)).strftime("%Y-%m-%d")
        rows = E.fetch_all(lambda: db.table("resumenes_hist").select("*").gte("fecha", desde).order("fecha"))
    except Exception:
        return False
    if not rows:
        return False
    tot = sum(float(r["ahorro"] or 0) for r in rows)
    n = sum(int(r["n_alertas"] or 0) for r in rows)
    err = sum(int(r["errores"] or 0) for r in rows)
    mejor_dia = max(rows, key=lambda r: float(r["ahorro"] or 0))
    m = "🗓 <b>SEMANA EN NÚMEROS — Canal VIP</b>\n\n"
    m += f"💰 Ahorro de la semana: <b>{_mxn(tot)} MXN</b>\n"
    m += f"📦 Alertas publicadas: <b>{n}</b> · 🚨 errores de precio: <b>{err}</b>\n"
    m += f"⭐ Mejor día: <b>{mejor_dia['fecha']}</b> ({_mxn(float(mejor_dia['ahorro'] or 0))})\n\n"
    m += f"{T.etiqueta()}: esta semana el equipo prioriza {', '.join(T.actual()['productos'][:3])}.\n"
    m += "¿Qué quieres que busquemos la próxima semana? Cuéntalo en la comunidad 👇"
    return bool(E.tg_send(E.cfg_int("CHANNEL_VIP_ID"), m))


def reporte_salud_admin():
    """Mensaje privado al dueño: fuentes que no traen nada + estado de BD."""
    s = E.salud_fuentes(24)
    if not s:
        E.admin_msg("⚠️ DropNode: no hay registros de fuentes en 24 h (¿la base de datos está caída?).",
                    clave=f"salud_vacia:{H.fecha_mx()}")
        return
    muertas = [f"• {n}: {c} corridas, 0 con productos" for n, (c, ok, tot) in sorted(s.items()) if ok == 0]
    vivas = [f"• {n}: {ok}/{c} corridas, {tot} productos" for n, (c, ok, tot) in sorted(s.items()) if ok > 0]
    m = "🩺 <b>Salud de fuentes (últimas 24 h)</b>\n\n"
    m += ("<b>Sin productos:</b>\n" + "\n".join(muertas) + "\n\n") if muertas else "Todas las fuentes aportaron productos ✅\n\n"
    m += "<b>Activas:</b>\n" + "\n".join(vivas)
    E.admin_msg(m, clave=f"salud:{H.fecha_mx()}")
