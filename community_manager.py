# =============================================================
# DROPNODE MX — community_manager.py  (v5.0)
# Comunidad completa, pensada para GitHub Actions (sin proceso 24/7):
#   - Lee el grupo con getUpdates en cada corrida (cada ~15 min)
#   - Todo lo programado usa candados en Supabase (no se duplica)
# 5 pilares:
#   1) Identidad y normas   : bienvenida, /reglas, propósito mensual
#   2) Activación           : rompehielos, encuestas, quizzes, retos, tendencias
#   3) Reconocimiento       : reacciones, gracias, niveles, top semanal, miembro del mes
#   4) Moderación emocional : spam, insultos, mediación, flood, inclusión
#   5) Métricas             : actividad por hora/día, tipo de post que más responde
# + /pedir <producto>  -> busca el producto y avisa al VIP
# REQUISITO: el bot debe ser ADMIN del grupo (borrar, silenciar, ver mensajes).
# Regla de oro: NUNCA se menciona automatización; todo es "el equipo".
# =============================================================
import re, json, random, logging
from datetime import datetime, timedelta, timezone

import requests

import estado as E
import horarios as H
import temporada_calendario as T
import peticiones as P

logger = logging.getLogger(__name__)

GROUP = E.cfg_int("GROUP_ID")
FREE = E.cfg_int("CHANNEL_FREE_ID")
VIP = E.cfg_int("CHANNEL_VIP_ID")
LINK_VIP = E.cfg("LAUNCHPASS_LINK")
BTN_VIP = ("📲 Unirse al Canal VIP — $299/mes", LINK_VIP)
NIVELES = [(25, "🏆 Experto"), (10, "⭐ Colaborador"), (3, "🔎 Cazador de ofertas"), (0, "🌱 Nuevo")]


def _una_vez(clave, fallback_minuto=True):
    """Candado: cada mensaje programado sale una sola vez aunque haya varias corridas."""
    return E.reclamar_evento(f"cm:{clave}", fallback=(H.ahora().minute < 15) if fallback_minuto else False)


# ─────────────────────────────────────────────
# Envío y registro de posts (para medir qué responde la gente)
# ─────────────────────────────────────────────
def _registrar_post(tipo, msg_id):
    db = E.get_db()
    if not db or not msg_id:
        return
    try:
        db.table("comunidad_posts").upsert({"message_id": msg_id, "tipo": tipo}, on_conflict="message_id").execute()
    except Exception:
        pass


def publicar(tipo, texto, boton=None):
    mid = E.tg_send(GROUP, texto, boton=boton)
    _registrar_post(tipo, mid)
    return mid


def enviar_poll(pregunta, opciones, tipo="poll", quiz_correcta=None, explicacion=""):
    if not GROUP:
        return None
    payload = {"chat_id": GROUP, "question": pregunta[:300], "options": opciones, "is_anonymous": False}
    if quiz_correcta is not None:
        payload.update({"type": "quiz", "correct_option_id": quiz_correcta, "explanation": explicacion[:200]})
    try:
        r = requests.post(f"{E.TG}/sendPoll", json=payload, timeout=15).json()
        if r.get("ok"):
            mid = r["result"]["message_id"]
            _registrar_post(tipo, mid)
            return mid
        logger.warning(f"[POLL] {r.get('description')}")
    except Exception as e:
        logger.error(f"[POLL] {e}")
    return None


def fomo_vip_al_free(n, categoria=""):
    """Teaser en el free. Solo en horario free y máximo 1 cada 2 horas."""
    if n <= 0 or not H.en_horario_free():
        return
    a = H.ahora()
    if not E.reclamar_evento(f"fomo:{H.fecha_mx(a)}:{a.hour // 2}", fallback=False):
        return
    cat = f" de {categoria}" if categoria else ""
    s = "s" if n > 1 else ""
    msgs = [f"🔒 El Canal VIP tiene <b>{n} oferta{s} exclusiva{s}{cat}</b> hoy.\n\n<i>No se publican aquí.</i>",
            f"🎯 <b>{n} oportunidad{'es' if n > 1 else ''}</b> solo para miembros VIP{cat}.\n\n<i>Seleccionadas por el equipo por descuento real.</i>"]
    E.tg_send(FREE, random.choice(msgs), boton=("📲 Ver Canal VIP", LINK_VIP))


# ─────────────────────────────────────────────
# Pilar 1 — Identidad y normas
# ─────────────────────────────────────────────
def texto_reglas():
    t = T.actual()
    return ("📌 <b>Para qué existe esta comunidad</b>\n"
            "Ayudarnos a comprar inteligente: compartir ofertas reales, pedir productos y aprender a no pagar de más.\n\n"
            "<b>Reglas de convivencia</b>\n"
            "1. Respeto entre todos: se debate con argumentos, nunca con insultos.\n"
            "2. Sin spam ni links a otros grupos o canales.\n"
            "3. Comparte ofertas con precio, tienda y link.\n"
            "4. Sin discriminación ni acoso de ningún tipo.\n"
            "5. Las dudas son bienvenidas: no hay preguntas tontas.\n\n"
            "<i>Algunos enlaces pueden ser de afiliado; eso no cambia tu precio. Los precios pueden variar: verifica antes de comprar.</i>\n\n"
            f"{t['emoji']} Este mes: <b>{t['nombre']}</b>. Escribe <code>/pedir producto</code> y lo buscamos.")


def mensaje_bienvenida(nombres_html):
    t = T.actual()
    return (f"👋 <b>¡Bienvenido/a {nombres_html}!</b>\n\n"
            "Esta es la comunidad de DropNode MX: personas que compran inteligente.\n\n"
            "• Aquí compartimos ofertas y pedimos productos\n"
            "• Los mejores precios llegan primero al Canal VIP\n"
            "• Escribe <code>/reglas</code> para ver las normas, o <code>/pedir producto</code> para que lo busquemos\n\n"
            f"{t['emoji']} Este mes: <i>{t['nombre']}</i>\n\n"
            "Preséntate si quieres: ¿qué producto te gustaría conseguir al mejor precio? "
            "(y si prefieres solo leer, también está perfecto 🙌)")


# ─────────────────────────────────────────────
# Pilar 2 — Activación
# ─────────────────────────────────────────────
ICEBREAKERS = [
    "💬 <b>Pregunta de la semana</b>\n\n¿Cuál fue la mejor compra que hiciste con descuento? Producto, precio y tienda 👇",
    "💬 <b>Debate</b>\n\n¿50% de descuento en algo que no necesitas o 20% en algo que sí? 👇",
    "💬 <b>Consejo de la comunidad</b>\n\n¿Cuál es el error más común al comprar en oferta? 👇",
    "💬 <b>Sin pena</b>\n\n¿Qué duda tienes sobre ofertas, cupones o tiendas? Aquí nadie se ríe: pregunta lo que quieras 👇",
    "💬 <b>Historia de éxito</b>\n\n¿Compraste algo que te haya ahorrado un buen dinero? Cuéntanos cómo lo encontraste 👇",
]
POLLS = [
    ("¿Para qué usas las alertas de DropNode?", ["Compra personal", "Reventa", "Regalos", "Solo exploro"]),
    ("¿Cuánto gastas cuando encuentras una buena oferta?", ["Menos de $500", "$500 - $2,000", "$2,000 - $5,000", "Más de $5,000"]),
    ("¿Qué valoras más en una oferta?", ["Mayor % de descuento", "Precio más bajo histórico", "Envío gratis", "Que sea de una tienda confiable"]),
]
QUIZZES = [
    ("Un producto 'tachado' de $10,000 hoy a $6,000. ¿Cómo saber si el descuento es real?",
     ["Comparar contra su precio de las últimas semanas", "Confiar en el % que dice la tienda", "Comprarlo rápido antes de que se acabe", "Ver si tiene muchas estrellas"], 0,
     "El precio tachado puede estar inflado. Lo que importa es el historial real."),
    ("Producto con 30% de descuento + cupón bancario del 15%. ¿Descuento total aproximado?",
     ["45%", "40.5%", "30%", "15%"], 1, "Se aplican en cadena: 0.70 × 0.85 = 0.595, o sea 40.5% de ahorro."),
    ("¿Cuándo suelen bajar más los juguetes populares?",
     ["El mismo día de la fiesta", "Semanas antes de la fecha grande", "Nunca bajan", "Solo en enero"], 1,
     "Comprar antes del pico de demanda suele salir más barato y hay más stock."),
]
TIPS = [
    "<b>Tip DropNode — ¿Descuento real?</b>\n\nNo compares contra el precio tachado; puede estar inflado desde hace meses. Compara contra lo que costaba las últimas semanas.",
    "<b>Tip DropNode — Combina descuentos</b>\n\nOferta de la tienda + cupón bancario = precio más bajo real. Ej.: 30% + 15% = 40.5% de ahorro total.",
    "<b>Tip DropNode — Vendedor</b>\n\nEn marketplaces revisa reputación del vendedor y si el envío es completo. Un buen precio con mal vendedor no es buen precio.",
    "<b>Tip DropNode — Stock bajo</b>\n\nCuando quedan pocas piezas, agrega al carrito primero y decide después. Los errores de precio duran poco.",
]
VIERNES = [
    "🏆 <b>Viernes de recomendaciones</b>\n\n¿Aprovechaste alguna oferta esta semana? Cuéntanos qué, a qué precio y dónde 👇",
    "📸 <b>Cierre de semana</b>\n\nComparte tu mejor compra de la semana. Producto, precio y tienda. La comunidad aprende de todos 👇",
]


def _lideres(n=2):
    try:
        r = _ranking(datetime.utcnow() - timedelta(days=14), n=n)
        return [x for x in r if x.get("username")]
    except Exception:
        return []


def icebreaker():
    t = T.actual()
    base = f"💬 <b>Pregunta de temporada — {t['emoji']} {t['nombre']}</b>\n\n{t['pregunta']}\n\n<i>Cuéntanos abajo 👇</i>" \
        if H.ahora().isocalendar()[1] % 2 == 0 else random.choice(ICEBREAKERS)
    lid = _lideres()
    if lid:
        base += "\n\n<i>Nos encantaría leer a " + " y ".join(f"@{E.esc(x['username'])}" for x in lid) + " 🙌</i>"
    return base


def mensaje_peticion():
    t = T.actual()
    return ("📝 <b>DropNode te escucha</b>\n\nDinos qué producto buscas esta semana: marca, modelo o categoría. "
            "Responde a este mensaje o escribe <code>/pedir producto</code>.\n\n"
            "El equipo lo busca y, si hay oferta real, llega primero al Canal VIP.\n\n"
            f"<i>{t['emoji']} Este mes priorizamos: {', '.join(t['productos'][:3])}</i>")


def tendencia_semana():
    db = E.get_db()
    cats = {}
    if db:
        try:
            desde = (datetime.utcnow() - timedelta(days=7)).isoformat()
            filas = E.fetch_all(lambda: db.table("alertas_enviadas").select("producto_id").gte("timestamp", desde).eq("canal", "vip"))
            ids = list({f["producto_id"] for f in filas if f.get("producto_id")})
            for i in range(0, len(ids), 100):
                for p in db.table("productos").select("categoria").in_("id", ids[i:i + 100]).execute().data or []:
                    cats[p["categoria"]] = cats.get(p["categoria"], 0) + 1
        except Exception:
            pass
    t = T.actual()
    top = sorted(cats.items(), key=lambda x: -x[1])[:3]
    if top:
        linea = "Lo que más apareció esta semana en el Canal VIP: " + ", ".join(f"<b>{E.esc(c)}</b>" for c, _ in top) + "."
    else:
        linea = f"En temporada de {t['nombre']} el equipo busca más: {', '.join(t['productos'][:3])}."
    return (f"📈 <b>Tendencia de la semana — {t['emoji']} {t['nombre']}</b>\n\n{linea}\n\n"
            "¿Te sorprende? ¿Qué tendencia ves tú en tus compras? 👇")


def _deal_desde_bd():
    """Mejor descuento publicado en el VIP en las últimas 24 h (no depende de la API de ML)."""
    db = E.get_db()
    if not db:
        return None
    try:
        desde = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        filas = E.fetch_all(lambda: db.table("alertas_enviadas").select("producto_id,precio_alerta,descuento_real")
                            .eq("canal", "vip").gte("timestamp", desde), max_pages=3)
        filas = [f for f in filas if f.get("producto_id") and 0.2 <= float(f.get("descuento_real") or 0) < 0.9
                 and float(f.get("precio_alerta") or 0) > 0]
        if not filas:
            return None
        mejor = max(filas, key=lambda f: float(f["descuento_real"]))
        p = db.table("productos").select("nombre,url").eq("id", mejor["producto_id"]).limit(1).execute().data
        if not p:
            return None
        precio, d = float(mejor["precio_alerta"]), float(mejor["descuento_real"])
        return {"nombre": p[0]["nombre"], "url": p[0]["url"], "precio_actual": precio,
                "precio_original": precio / (1 - d), "descuento": d}
    except Exception as e:
        logger.warning(f"[DEAL BD] {e}")
        return None


def deal_del_dia():
    d = None
    try:
        from scraper_api import get_deal_del_dia
        d = get_deal_del_dia()
    except Exception as e:
        logger.warning(f"[DEAL] {e}")
    if not d:
        d = _deal_desde_bd()
    if not d:
        return False
    t = T.actual()
    url = E.link_afiliado(d["url"])
    return bool(publicar("deal_dia",
        f"⚡ <b>Deal del Día — {t['emoji']} {t['nombre']}</b>\n\n<b>{E.esc(d['nombre'][:60])}</b>\n\n"
        f"<b>${d['precio_actual']:,.0f} MXN</b> (-{d['descuento']*100:.0f}%)\n"
        f"<s>${d['precio_original']:,.0f}</s> · Ahorro: ${d['precio_original'] - d['precio_actual']:,.0f}\n\n"
        f"<a href=\"{url}\">Ver oferta →</a>\n\n<i>💬 ¿Lo conocías? ¿Vale la pena? Cuéntanos 👇</i>", boton=BTN_VIP))


def recordatorio_vip():
    t = T.actual()
    return random.choice([
        f"{t['emoji']} En temporada de <b>{t['nombre']}</b> el Canal VIP revisa especialmente: {', '.join(t['productos'][:3])}.\n\n"
        "Errores de precio, stock crítico y cupones bancarios calculados. $299 MXN/mes, cancela cuando quieras.",
        "<b>Canal VIP — lo que incluye</b>\n\nAlertas desde las 6:30 AM (y de madrugada si hay error de precio)\nPrecio vs histórico\n"
        "Cierre diario con el ahorro del día\nBúsquedas pedidas por la comunidad\n\n$299 MXN/mes",
    ])


# ─────────────────────────────────────────────
# Pilar 3 — Reconocimiento
# ─────────────────────────────────────────────
PUNTOS = {"msg": 1, "reply_bot": 2, "aporte": 3, "peticion": 2}


def nivel(aportes):
    for minimo, nombre in NIVELES:
        if aportes >= minimo:
            return nombre
    return NIVELES[-1][1]


def _ranking(desde_utc, hasta_utc=None, n=5):
    db = E.get_db()
    if not db:
        return []
    def q():
        b = db.table("comunidad_msgs").select("user_id,username,nombre,puntos").gte("ts", desde_utc.isoformat())
        return b.lt("ts", hasta_utc.isoformat()) if hasta_utc else b
    filas = E.fetch_all(q, max_pages=8)
    tot = {}
    for f in filas:
        u = tot.setdefault(f["user_id"], {"user_id": f["user_id"], "username": f.get("username"),
                                          "nombre": f.get("nombre"), "puntos": 0})
        u["puntos"] += int(f.get("puntos") or 0)
        u["username"] = f.get("username") or u["username"]
    return sorted(tot.values(), key=lambda x: -x["puntos"])[:n]


def _mencion(u):
    nom = E.esc(u.get("nombre") or u.get("username") or "miembro")
    return f"<a href=\"tg://user?id={u['user_id']}\">{nom}</a>"


def top_semana():
    top = _ranking(datetime.utcnow() - timedelta(days=7), n=3)
    if len(top) < 1:
        return False
    med = ["🥇", "🥈", "🥉"]
    m = "🌟 <b>Los que hicieron grande la comunidad esta semana</b>\n\n"
    for i, u in enumerate(top):
        m += f"{med[i]} {_mencion(u)} — {u['puntos']} pts\n"
    m += "\n<i>Participar, recomendar ofertas y ayudar a otros suma puntos. ¡Gracias!</i>"
    return bool(publicar("top_semana", m))


def miembro_del_mes():
    a = H.ahora()
    ini_mes = a.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    fin_ant = ini_mes
    ini_ant = (ini_mes - timedelta(days=1)).replace(day=1)
    off = a.utcoffset()
    top = _ranking((ini_ant - off).replace(tzinfo=None), (fin_ant - off).replace(tzinfo=None), n=1)
    if not top:
        return False
    u = top[0]
    return bool(publicar("miembro_mes",
        f"🏅 <b>Miembro del mes</b>\n\nEl reconocimiento de {H.MESES[ini_ant.month - 1]} es para {_mencion(u)} "
        f"con {u['puntos']} puntos. ¡Gracias por ayudar a todos a comprar mejor! 👏"))


# ─────────────────────────────────────────────
# Pilar 4 — Moderación emocional
# ─────────────────────────────────────────────
SPAM_DOM = ["t.me/", "telegram.me/", "wa.me/", "chat.whatsapp", "whatsapp.com", "bit.ly", "tinyurl", "cutt.ly", "shorturl"]
OK_DOM = ["mercadolibre", "mercadolivre", "amazon", "liverpool", "walmart", "coppel", "elektra", "costco", "sams.com",
          "heb.com", "sears.com", "palaciodehierro", "bodegaaurrera", "launchpass.com/marcodurzo", "platacard.mx", "nu.com.mx"]
SCAM = ["duplica tu dinero", "inversion segura", "gana dinero facil", "forex", "opciones binarias", "cripto gratis", "trabaja desde casa y gana"]
GRAVES = [r"te voy a matar", r"hijo de (tu )?puta", r"hdtpm", r"maricon", r"\bjoto\b", r"\bputo\b", r"\bnegro de mierda\b",
          r"ojala te mueras", r"\bmuerete\b"]
ACALORADAS = [r"\bpendej[oa]s?\b", r"\bidiota\b", r"\bimbecil\b", r"\bestupid[oa]\b", r"\binutil\b", r"\btarad[oa]\b",
              r"\bcallate\b", r"\bbabos[oa]\b"]


def _norm(t):
    return T.normalizar(t)


def clasificar(texto):
    """'spam' | 'grave' | 'acalorada' | None"""
    n = _norm(texto)
    tiene_link = "http" in n or "www." in n or ".com" in n
    if any(s in n for s in SPAM_DOM) and not any(o in n for o in OK_DOM):
        return "spam"
    if sum(1 for s in SCAM if s in n) >= 1 and (tiene_link or sum(1 for s in SCAM if s in n) >= 2):
        return "spam"
    if any(re.search(g, n) for g in GRAVES):
        return "grave"
    letras = [c for c in texto if c.isalpha()]
    gritos = len(texto) > 25 and letras and sum(c.isupper() for c in letras) / len(letras) > 0.75
    if any(re.search(a, n) for a in ACALORADAS) or gritos:
        return "acalorada"
    return None


def _advertir(uid, nombre):
    """Escalera: 1 aviso · 2 silencio 1 h · 3+ silencio 24 h y aviso al dueño. Nunca banea solo."""
    db = E.get_db()
    cuenta = 1
    if db:
        try:
            r = db.table("comunidad_advertencias").select("cuenta").eq("user_id", uid).limit(1).execute()
            cuenta = (r.data[0]["cuenta"] if r.data else 0) + 1
            db.table("comunidad_advertencias").upsert({"user_id": uid, "cuenta": cuenta,
                                                       "ultima": datetime.utcnow().isoformat()}, on_conflict="user_id").execute()
        except Exception:
            pass
    return cuenta


def _silenciar(uid, segundos):
    try:
        requests.post(f"{E.TG}/restrictChatMember", json={
            "chat_id": GROUP, "user_id": uid, "until_date": int(datetime.now(timezone.utc).timestamp()) + segundos,
            "permissions": {"can_send_messages": False}}, timeout=10)
    except Exception:
        pass


def _borrar(mid):
    try:
        requests.post(f"{E.TG}/deleteMessage", json={"chat_id": GROUP, "message_id": mid}, timeout=10)
    except Exception:
        pass


def _reaccionar(mid, emoji="👍"):
    try:
        requests.post(f"{E.TG}/setMessageReaction", json={"chat_id": GROUP, "message_id": mid,
                      "reaction": [{"type": "emoji", "emoji": emoji}]}, timeout=8)
    except Exception:
        pass


def _moderar(msg, user, tipo, ctx):
    uid, nombre, mid = user["id"], user.get("first_name", "Miembro"), msg["message_id"]
    _borrar(mid)
    cuenta = _advertir(uid, nombre)
    ctx["moderacion"] += 1
    ctx["filas"].append(_fila(msg, user, "moderacion", 0))
    if cuenta == 1:
        E.tg_send(GROUP, f"{E.esc(nombre)}, tu mensaje se retiró ({'enlace no permitido' if tipo == 'spam' else 'lenguaje no permitido'}). "
                         "Aquí cuidamos que todos se sientan cómodos. Escribe /reglas para ver las normas 🙏")
    elif cuenta == 2:
        _silenciar(uid, 3600)
        E.tg_send(GROUP, f"{E.esc(nombre)} queda en pausa 1 hora por reincidir. Podrás volver a escribir después 🙏")
    else:
        _silenciar(uid, 86400)
        E.admin_msg(f"⚠️ Moderación: {nombre} (id {uid}) acumula {cuenta} avisos ({tipo}). Silenciado 24 h. Revisa si amerita expulsión.",
                    clave=f"mod:{uid}:{H.fecha_mx()}")


# ─────────────────────────────────────────────
# Lectura del grupo (getUpdates)
# ─────────────────────────────────────────────
APORTE_RE = re.compile(r"\$\s?\d|\b\d{3,6}\s?(pesos|mxn)\b|encontr[eé]|recomiendo|compr[eé]|oferta|descuento", re.I)


def _es_aporte(texto):
    n = _norm(texto)
    return len(texto) >= 25 and (any(o in n for o in OK_DOM) or bool(APORTE_RE.search(texto)))


def _fila(msg, user, tipo, puntos, reply_tipo=""):
    ts = datetime.fromtimestamp(msg.get("date", datetime.now().timestamp()), tz=timezone.utc)
    loc = ts.astimezone(H.TZ)
    return {"ts": ts.replace(tzinfo=None).isoformat(), "user_id": user.get("id"),
            "username": user.get("username") or "", "nombre": user.get("first_name") or "",
            "tipo": tipo, "puntos": puntos, "reply_tipo": reply_tipo, "hora": loc.hour, "dow": loc.weekday()}


def _admins():
    try:
        r = requests.get(f"{E.TG}/getChatAdministrators", params={"chat_id": GROUP}, timeout=10).json()
        return {a["user"]["id"] for a in r.get("result", [])}
    except Exception:
        return set()


def _posts_recientes():
    db = E.get_db()
    if not db:
        return {}
    try:
        desde = (datetime.utcnow() - timedelta(days=8)).isoformat()
        rows = E.fetch_all(lambda: db.table("comunidad_posts").select("message_id,tipo").gte("ts", desde), max_pages=3)
        return {r["message_id"]: r["tipo"] for r in rows}
    except Exception:
        return {}


def _procesar_msg(msg, admins, posts, ctx):
    chat = msg.get("chat", {})
    user = msg.get("from", {}) or {}
    texto = (msg.get("text") or msg.get("caption") or "").strip()

    if chat.get("type") == "private":                        # /id -> ayuda para configurar ADMIN_CHAT_ID
        if texto.startswith("/id") or texto.startswith("/start"):
            E.tg_send(chat["id"], f"Tu ID de Telegram es <code>{user.get('id')}</code>\n"
                                  "Guárdalo como secret ADMIN_CHAT_ID en GitHub para recibir alertas privadas.")
        return
    if chat.get("id") != GROUP:
        return
    for nm in msg.get("new_chat_members", []) or []:
        if not nm.get("is_bot"):
            ctx["nuevos"].append(nm)
            ctx["filas"].append(_fila(msg, nm, "nuevo", 0))
    if user.get("is_bot") or not user.get("id") or not texto:
        return
    uid = user["id"]
    es_admin = uid in admins

    cmd = texto.split()[0].lower().split("@")[0] if texto.startswith("/") else ""
    if cmd == "/reglas":
        ctx["respuestas"].append(("reglas", texto_reglas(), msg["message_id"]))
        return
    if cmd == "/pedir":
        partes = texto.split(None, 1)
        peticion = partes[1].strip() if len(partes) > 1 else ""
        if len(peticion) < 3:
            ctx["respuestas"].append(("pedir_ayuda", "Escribe el producto después del comando, por ejemplo: <code>/pedir audífonos sony</code>", msg["message_id"]))
        else:
            ctx["peticiones"].append((peticion, user, msg["message_id"]))
            ctx["filas"].append(_fila(msg, user, "peticion", PUNTOS["peticion"]))
        return

    # Moderación (no aplica a admins)
    clase = None if es_admin else clasificar(texto)
    if clase in ("spam", "grave"):
        _moderar(msg, user, clase, ctx)
        return

    # Flood: 6+ mensajes en 60 s
    ts = msg.get("date", 0)
    lst = ctx["fechas"].setdefault(uid, [])
    lst.append(ts)
    if not es_admin and len([x for x in lst if ts - x <= 60]) >= 6 and uid not in ctx["flood"]:
        ctx["flood"].add(uid)
        _silenciar(uid, 600)
        E.tg_send(GROUP, f"{E.esc(user.get('first_name', 'Miembro'))}, pausa de 10 minutos por enviar muchos mensajes seguidos 🙏")
        return

    if clase == "acalorada" and (msg.get("reply_to_message") or {}).get("from", {}).get("id") not in (None, uid):
        ctx["calientes"].append(msg["message_id"])

    # Actividad / puntos
    reply = msg.get("reply_to_message") or {}
    reply_tipo = posts.get(reply.get("message_id"), "") if reply else ""
    if _es_aporte(texto):
        tipo, pts = "aporte", PUNTOS["aporte"]
        ctx["aportes"][uid] = ctx["aportes"].get(uid, 0) + 1
        ctx["aportantes"].setdefault(uid, (user, msg["message_id"]))
    elif reply_tipo:
        tipo, pts = "reply_bot", PUNTOS["reply_bot"]
    else:
        tipo, pts = "msg", PUNTOS["msg"]
    ctx["filas"].append(_fila(msg, user, tipo, pts, reply_tipo))
    if tipo in ("aporte", "reply_bot") and ctx["reacciones"] < 10:
        ctx["reacciones"] += 1
        _reaccionar(msg["message_id"], random.choice(["👍", "🔥", "💯", "👏"]))

    # Peticiones: respuesta a un post de petición/pregunta de temporada, o lunes 10-14
    if not clase and not texto.startswith("/") and "http" not in texto.lower() and len(texto) >= 3:
        if reply_tipo in ("peticion", "pregunta_temporada") or P.ventana_activa():
            ctx["peticiones"].append((texto, user, msg["message_id"]))


def procesar_actualizaciones():
    """Lee lo nuevo del grupo, modera, reconoce y registra. Seguro si no hay BD."""
    if not GROUP or not E.TELEGRAM_TOKEN:
        return
    ctx = {"nuevos": [], "filas": [], "respuestas": [], "peticiones": [], "calientes": [], "aportes": {},
           "aportantes": {}, "fechas": {}, "flood": set(), "reacciones": 0, "moderacion": 0}
    admins, posts = _admins(), _posts_recientes()
    offset, total = None, 0
    for _ in range(5):
        try:
            params = {"timeout": 0, "limit": 100, "allowed_updates": json.dumps(["message"])}
            if offset:
                params["offset"] = offset
            r = requests.get(f"{E.TG}/getUpdates", params=params, timeout=15).json()
        except Exception as e:
            logger.warning(f"[UPDATES] {e}")
            break
        if not r.get("ok"):
            if "conflict" in str(r.get("description", "")).lower():
                E.admin_msg("⚠️ Telegram: hay OTRO proceso leyendo el bot (webhook o servicio viejo, p. ej. Railway). "
                            "Apágalo para que la comunidad funcione.", clave=f"conflicto:{H.fecha_mx()}")
            logger.warning(f"[UPDATES] {r.get('description')}")
            break
        ups = r.get("result", [])
        for u in ups:
            total += 1
            try:
                if u.get("message"):
                    _procesar_msg(u["message"], admins, posts, ctx)
            except Exception as e:
                logger.warning(f"[UPDATES] msg: {e}")
        if not ups:
            break
        offset = ups[-1]["update_id"] + 1
        if len(ups) < 100:
            break
    if offset:                                   # confirma lo leído para no reprocesarlo
        try:
            requests.get(f"{E.TG}/getUpdates", params={"offset": offset, "limit": 1, "timeout": 0}, timeout=10)
        except Exception:
            pass
    logger.info(f"[COMUNIDAD] updates={total} filas={len(ctx['filas'])} mod={ctx['moderacion']}")
    _cerrar(ctx)


def _cerrar(ctx):
    db = E.get_db()
    if db and ctx["filas"]:
        try:
            db.table("comunidad_msgs").insert(ctx["filas"]).execute()
        except Exception as e:
            logger.warning(f"[COMUNIDAD] guardar filas: {e}")

    # Bienvenida (una por persona)
    nuevos = [n for n in ctx["nuevos"] if E.reclamar_evento(f"bienvenida:{n['id']}", fallback=True)]
    if nuevos:
        nombres = ", ".join(f"<a href=\"tg://user?id={n['id']}\">{E.esc(n.get('first_name', ''))}</a>" for n in nuevos[:5])
        publicar("bienvenida", mensaje_bienvenida(nombres))

    for tipo, texto, reply in ctx["respuestas"][:2]:
        E.tg_send(GROUP, texto, reply_to=reply)

    # Mediación (una por hora)
    if ctx["calientes"] and E.reclamar_evento(f"mediacion:{H.fecha_mx()}:{H.ahora().hour}", fallback=False):
        E.tg_send(GROUP, "Entendemos que hay opiniones distintas 🙌 Aquí todos venimos a ahorrar y a aprender. "
                         "Cuéntenos cada quien su punto con calma: así la conversación nos sirve a todos.",
                  reply_to=ctx["calientes"][0])

    # Gracias y niveles para quien aportó
    gracias = 0
    for uid, (user, mid) in list(ctx["aportantes"].items())[:5]:
        total = _contar_aportes(uid)
        antes = total - ctx["aportes"].get(uid, 0)
        niv_antes, niv_ahora = nivel(antes), nivel(total)
        if niv_ahora != niv_antes:
            E.tg_send(GROUP, f"🎉 {_mencion({'user_id': uid, 'nombre': user.get('first_name')})} sube a <b>{niv_ahora}</b> "
                             "por compartir tantas ofertas. ¡Gracias!", reply_to=mid)
        elif gracias < 3 and E.reclamar_evento(f"gracias:{uid}:{H.fecha_mx()}", fallback=False):
            gracias += 1
            E.tg_send(GROUP, random.choice(["¡Gracias por compartirlo! 🙌", "Buen aporte 👏 a la comunidad le sirve.",
                                            "Excelente dato, gracias 🔥"]), reply_to=mid)

    # Peticiones -> BD -> búsqueda inmediata -> VIP
    pets = ctx["peticiones"][:5]
    for i, (texto, user, mid) in enumerate(pets):
        P.registrar_peticion(texto, user.get("id"), user.get("username") or user.get("first_name"))
        if i == 0:
            E.tg_send(GROUP, "Anotado ✅ El equipo lo pone en el radar. Si hay oferta real, llega primero al Canal VIP.", reply_to=mid)
        if i < 3:
            P.buscar_ahora(texto)


def _contar_aportes(uid):
    db = E.get_db()
    if not db:
        return 0
    try:
        desde = (datetime.utcnow() - timedelta(days=90)).isoformat()
        r = db.table("comunidad_msgs").select("id", count="exact").eq("user_id", uid).eq("tipo", "aporte").gte("ts", desde).execute()
        return r.count or 0
    except Exception:
        return 0


# ─────────────────────────────────────────────
# Pilar 5 — Métricas (reporte privado al dueño)
# ─────────────────────────────────────────────
def reporte_metricas():
    db = E.get_db()
    if not db:
        return
    desde = (datetime.utcnow() - timedelta(days=7)).isoformat()
    try:
        filas = E.fetch_all(lambda: db.table("comunidad_msgs").select("*").gte("ts", desde), max_pages=8)
    except Exception:
        return
    if not filas:
        E.admin_msg("📊 Comunidad: sin actividad registrada en 7 días.", clave=f"met:{H.fecha_mx()}")
        return
    humanos = [f for f in filas if f["tipo"] in ("msg", "aporte", "reply_bot", "peticion")]
    por_hora, por_dia, por_post, usuarios = {}, {}, {}, {}
    for f in humanos:
        por_hora[f["hora"]] = por_hora.get(f["hora"], 0) + 1
        por_dia[f["dow"]] = por_dia.get(f["dow"], 0) + 1
        usuarios[f["user_id"]] = usuarios.get(f["user_id"], 0) + 1
        if f.get("reply_tipo"):
            por_post[f["reply_tipo"]] = por_post.get(f["reply_tipo"], 0) + 1
    top = lambda d, n=3: sorted(d.items(), key=lambda x: -x[1])[:n]
    m = "📊 <b>Comunidad — semana</b>\n\n"
    m += f"Mensajes: <b>{len(humanos)}</b> · personas activas: <b>{len(usuarios)}</b> · nuevos: <b>{sum(1 for f in filas if f['tipo'] == 'nuevo')}</b> · moderaciones: <b>{sum(1 for f in filas if f['tipo'] == 'moderacion')}</b>\n"
    m += "Mejores horas: " + ", ".join(f"{h}:00 ({n})" for h, n in top(por_hora)) + "\n"
    m += "Mejores días: " + ", ".join(f"{H.DIAS[d]} ({n})" for d, n in top(por_dia)) + "\n"
    m += "Posts que más respuestas generan: " + (", ".join(f"{k} ({n})" for k, n in top(por_post, 4)) or "—") + "\n"
    m += "Más activos: " + ", ".join(f"{u} ({n})" for u, n in top(usuarios, 3))
    E.admin_msg(m, clave=f"met:{H.fecha_mx()}")


# ─────────────────────────────────────────────
# Programación
# ─────────────────────────────────────────────
def ejecutar_community_manager():
    if not GROUP:
        return
    a = H.ahora()
    dia, h, dom = a.weekday(), a.hour, a.day
    f = H.fecha_mx(a)
    sem = f"{a.isocalendar()[0]}w{a.isocalendar()[1]}"
    t = T.actual()

    def prog(cond, clave, fn):
        if cond and _una_vez(clave):
            try:
                fn()
            except Exception as e:
                logger.error(f"[COMMUNITY] {clave}: {e}", exc_info=True)

    prog(h == 9, f"deal:{f}", deal_del_dia)
    prog(dia == 0 and h == 8, f"metricas:{sem}", reporte_metricas)
    prog(dia == 0 and h == 10, f"peticion:{sem}", lambda: publicar("peticion", mensaje_peticion()))
    prog(dia == 0 and h == 11 and dom <= 7, f"miembro_mes:{a.strftime('%Y-%m')}", miembro_del_mes)
    prog(dia == 0 and h == 14, f"resumen_pet:{sem}", _resumen_peticiones)
    prog(dia == 1 and h == 12, f"reto:{sem}", lambda: publicar("reto",
         f"🎯 <b>Reto de la semana — {t['emoji']} {t['nombre']}</b>\n\n{t['reto']}\n\n<i>El mejor hallazgo se destaca el domingo 👇</i>"))
    prog(dia == 1 and h == 20, f"rec_vip_mar:{sem}", lambda: publicar("recordatorio", recordatorio_vip(), boton=BTN_VIP))
    prog(dia == 2 and h == 12, f"tendencia:{sem}", lambda: publicar("tendencia", tendencia_semana()))
    prog(dia == 2 and h == 18, f"poll:{sem}", _poll_semana)
    prog(dia == 3 and h == 12, f"quiz:{sem}", _quiz_semana)
    prog(dia == 3 and h == 20, f"rec_vip_jue:{sem}", lambda: publicar("recordatorio", recordatorio_vip(), boton=BTN_VIP))
    prog(dia == 3 and h == 21, f"resultado_pet:{sem}", _resultado_semanal)
    prog(dia == 4 and h == 17, f"viernes:{sem}", lambda: publicar("recomendaciones", random.choice(VIERNES)))
    prog(dia == 5 and h == 11, f"icebreaker:{sem}", lambda: publicar("icebreaker", icebreaker()))
    prog(dia == 6 and h == 11, f"tip:{sem}", lambda: publicar("tip", f"💡 <b>Tip de temporada — {t['emoji']} {t['nombre']}</b>\n\n{t['tip']}"
                                                              if int(sem.split('w')[1]) % 3 == 0 else random.choice(TIPS)))
    prog(dia == 6 and h == 12, f"top:{sem}", top_semana)
    prog(dom == 1 and h == 10, f"reglas:{a.strftime('%Y-%m')}", lambda: publicar("reglas", texto_reglas()))
    # Pregunta de temporada = petición suave (sus respuestas también van al VIP)
    prog(dia == 2 and h == 10, f"preg_temp:{sem}", lambda: publicar("pregunta_temporada",
         f"{t['pregunta']}\n\n<i>Responde a este mensaje: lo que pidan, el equipo lo busca para el VIP 👇</i>"))


def _poll_semana():
    t = T.actual()
    if H.ahora().isocalendar()[1] % 2 == 0:
        enviar_poll(t["poll"], ["Ya lo tengo en la mira", "Lo busco y no encuentro precio", "No es prioridad ahora", "Espero mejores ofertas"], "poll")
    else:
        p = random.choice(POLLS)
        enviar_poll(p[0], p[1], "poll")


def _quiz_semana():
    q = random.choice(QUIZZES)
    enviar_poll("🧠 Quiz DropNode: " + q[0], q[1], "quiz", quiz_correcta=q[2], explicacion=q[3])


def _resumen_peticiones():
    n = P.contar_semana()
    if n:
        publicar("resumen_peticiones", f"📝 <b>Recibimos {n} sugerencias esta semana.</b>\n\nEl equipo ya las tiene en el radar. "
                                       "Los primeros resultados aparecen en el Canal VIP.", boton=BTN_VIP)


def _resultado_semanal():
    db = E.get_db()
    if not db:
        return
    try:
        sem = H.ahora().isocalendar()[1]
        enc = db.table("peticiones").select("id", count="exact").eq("semana", sem).eq("encontrada", True).execute().count or 0
        tot = P.contar_semana()
    except Exception:
        return
    if enc:
        publicar("resultado_peticiones", f"🎯 <b>Resultados de la semana</b>\n\nLa comunidad hizo <b>{tot}</b> peticiones y el equipo encontró "
                                         f"<b>{enc}</b> con oferta real. Cada una llegó al Canal VIP.\n\n<i>Si pediste algo y no apareció, lo seguimos buscando.</i>", boton=BTN_VIP)
