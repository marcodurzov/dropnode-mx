# =============================================================
# DROPNODE MX — contenido.py  (v1.0)
# Contenido que le da identidad al servicio (no son ofertas):
#   - Promoción de Plata Card / Nu (enlaces de referido, con aviso de transparencia)
#   - Temporada: arranque de mes y recordatorios semanales en el free
#   - Oferta manual del dueño (/oferta desde el chat privado con el bot)
# Regla de oro: NUNCA se menciona automatización: "el equipo".
# =============================================================
import re, random, hashlib, logging
from urllib.parse import urlparse
from datetime import date

import estado as E
import horarios as H
import temporada_calendario as T

logger = logging.getLogger(__name__)
TRANSPARENCIA = "<i>Enlace de invitación: al registrarte con él accedes a los beneficios del programa de referidos.</i>"


def _productos():
    try:
        import config
        return {p["nombre"]: p for p in config.PRODUCTOS_FINANCIEROS if p.get("activo")}
    except Exception:
        return {}


def _elegir(dia, slot="a"):
    """Plata Card casi siempre (es la que más le deja al dueño): en el free, la 1ª promo del día es SIEMPRE Plata
    y la 2ª es Plata 3 de cada 4 días; Nu solo ocasionalmente."""
    prods = _productos()
    plata, nu = prods.get("Plata Card"), prods.get("Nu")
    if plata and (slot == "a" or dia % 4 != 3 or not nu):
        return plata
    return nu or plata or (list(prods.values())[0] if prods else None)


PLATA_FREE = [
    "💳 <b>¿Compras seguido en oferta?</b>\n\nPlata Card es una tarjeta sin anualidad con cashback en tus compras. "
    "Si ya vas a comprar lo que encontramos aquí, que además te regrese algo.",
    "💳 <b>Tip del equipo</b>\n\nDe nada sirve encontrar el mejor precio si pagas comisiones por tu tarjeta. "
    "Plata Card: sin anualidad y con cashback en cada compra.",
    "💳 <b>Cashback en tus ofertas</b>\n\nCada compra que haces con descuento puede regresarte algo extra con Plata Card (sin anualidad).",
]
NU_FREE = ["💜 <b>Otra opción que recomendamos</b>\n\nNu: tarjeta de crédito sin anualidad y cuenta de débito, todo desde el celular."]


def promo_financiera_free(slot="a"):
    p = _elegir(H.ahora().day, slot)
    if not p:
        return False
    cuerpo = random.choice(PLATA_FREE if p["nombre"] == "Plata Card" else NU_FREE)
    return bool(E.tg_send(E.cfg_int("CHANNEL_FREE_ID"), f"{cuerpo}\n\n{TRANSPARENCIA}",
                          boton=(f"{p['emoji']} Conocer {p['nombre']}", p["link"])))


def promo_financiera_vip():
    p = _elegir(H.ahora().day + 1, "b")
    if not p:
        return False
    return bool(E.tg_send(E.cfg_int("CHANNEL_VIP_ID"),
                          f"{p['emoji']} <b>{E.esc(p['nombre'])}</b> — {E.esc(p['descripcion'])}.\n\n{TRANSPARENCIA}",
                          boton=(f"{p['emoji']} Conocer {p['nombre']}", p["link"])))


def promo_financiera_grupo():
    p = _elegir(H.ahora().day, "b")
    if not p:
        return False
    return bool(E.tg_send(E.cfg_int("GROUP_ID"),
                          f"{p['emoji']} <b>Tip financiero</b>\n\n{E.esc(p['nombre'])}: {E.esc(p['descripcion'])}.\n\n"
                          f"{TRANSPARENCIA}", boton=(f"{p['emoji']} Más info", p["link"])))


# ─────────────────────────────────────────────
# Recordatorio del VIP en el free (solo afirmaciones que el servicio cumple de verdad)
# ─────────────────────────────────────────────
VIP_FREE = [
    ("🔒 <b>Los descuentos de más del 40% son solo del Canal VIP</b>\n\n"
     "Aquí publicamos ofertas de hasta 40%. Lo mejor se queda en el VIP, junto con los errores de precio y las alertas "
     "desde las 6:30 AM.\n\n$299 MXN/mes · cancela cuando quieras"),
    ("⭐ <b>Lo que incluye el Canal VIP</b>\n\n"
     "• Alertas de 6:30 AM a 11:30 PM (y de madrugada si aparece un error de precio)\n"
     "• Descuentos de más del 40% que no llegan a este canal\n"
     "• Verificación contra el historial de precios\n"
     "• Etiquetas en cada oferta para buscar por producto, marca o tienda (#tenis, #nike, #liverpool…)\n"
     "• Cierre diario con el ahorro del día\n"
     "• Búsquedas que pide la comunidad\n\n$299 MXN/mes"),
    ("💡 <b>Una sola compra a buen precio puede pagar el mes</b>\n\n"
     "En el Canal VIP las ofertas llegan primero y con más descuento. Pruébalo y decide tú.\n\n$299 MXN/mes"),
]


def recordatorio_vip_free():
    return bool(E.tg_send(E.cfg_int("CHANNEL_FREE_ID"), random.choice(VIP_FREE),
                          boton=("📲 Canal VIP — $299/mes", E.cfg("LAUNCHPASS_LINK"))))


# ─────────────────────────────────────────────
# Temporada
# ─────────────────────────────────────────────
def temporada_inicio_mes():
    t = T.actual()
    prods = ", ".join(t["productos"][:4])
    free = (f"{t['emoji']} <b>Arrancó {E.esc(t['nombre'])}</b>\n\nEste mes el equipo busca con lupa: {E.esc(prods)}.\n\n"
            f"<i>{E.esc(t['tip'])}</i>")
    vip = (f"{t['emoji']} <b>Temporada: {E.esc(t['nombre'])}</b>\n\nPrioridad del equipo este mes: {E.esc(prods)}. "
           "Las ofertas de temporada llevan etiqueta y puntos extra en el score.")
    grupo = (f"{t['emoji']} <b>{E.esc(t['nombre'])}</b>\n\n{E.esc(t['pregunta'])}\n\n"
             "<i>Cuéntanos qué buscas y lo ponemos en el radar: escribe /pedir seguido del producto 👇</i>")
    ok = True
    if H.en_horario_free():
        ok &= bool(E.tg_send(E.cfg_int("CHANNEL_FREE_ID"), free, boton=("📲 Canal VIP — $299/mes", E.cfg("LAUNCHPASS_LINK"))))
    E.tg_send(E.cfg_int("CHANNEL_VIP_ID"), vip)
    E.tg_send(E.cfg_int("GROUP_ID"), grupo)
    return ok


def temporada_semana_free():
    t = T.actual()
    dia = H.ahora().timetuple().tm_yday
    prods = t["productos"]
    foco = prods[dia % len(prods)]
    msg = (f"{t['emoji']} <b>{E.esc(t['nombre'])}</b>\n\nEsta semana el equipo está atento a: <b>{E.esc(foco)}</b>.\n\n"
           f"<i>{E.esc(t['tip'])}</i>")
    return bool(E.tg_send(E.cfg_int("CHANNEL_FREE_ID"), msg, boton=("📲 Ver Canal VIP", E.cfg("LAUNCHPASS_LINK"))))


# ─────────────────────────────────────────────
# Oferta manual del dueño:  /oferta <url> <precio_ahora> <precio_antes> [nombre]
# ─────────────────────────────────────────────
BONITO = {"mercadolibre": "Mercado Libre", "sams": "Sam's Club", "palacio": "Palacio de Hierro", "bodega": "Bodega Aurrerá", "heb": "HEB"}


def _tienda(url):
    host = (urlparse(url).netloc or "").lower()
    for k, v in (("mercadolibre", "mercadolibre"), ("amazon", "amazon"), ("liverpool", "liverpool"), ("walmart", "walmart"),
                 ("costco", "costco"), ("coppel", "coppel"), ("elektra", "elektra"), ("sams", "sams"), ("heb", "heb"),
                 ("sears", "sears"), ("palaciodehierro", "palacio"), ("bodegaaurrera", "bodega")):
        if k in host:
            return v
    return host.replace("www.", "").split(".")[0] or "otra"


def oferta_manual(cmd):
    """Publica en VIP (y programa el free si aplica). Devuelve el texto de respuesta para el dueño."""
    partes = cmd.split()
    url = next((x for x in partes if x.startswith("http")), "")
    nums = []
    for x in partes:
        if x.startswith("http") or x.startswith("/"):
            continue
        try:
            nums.append(float(x.replace("$", "").replace(",", "")))
        except ValueError:
            break
    if not url or len(nums) < 2 or nums[0] <= 0 or nums[1] <= nums[0]:
        return ("Formato: <code>/oferta URL precio_ahora precio_antes nombre del producto</code>\n"
                "Ejemplo: <code>/oferta https://www.mercadolibre.com.mx/p/MLM123 1999 3499 Audífonos Sony WH</code>")
    precio, orig = nums[0], nums[1]
    resto = [x for x in partes[1:] if not x.startswith("http")]
    nombre = " ".join(resto[2:]).strip() or f"Oferta en {_tienda(url).capitalize()}"
    desc = (orig - precio) / orig
    tienda = _tienda(url)
    item = {"tienda": tienda, "nombre": nombre[:90], "precio_actual": precio, "precio_original": orig,
            "descuento": desc, "sku": hashlib.md5(url.split("?")[0].encode()).hexdigest()[:14], "url": url,
            "thumbnail": "", "categoria": {"nombre": "Selección del equipo", "emoji": "🛍️"}, "en_vip": True}
    txt = (f"⭐ <b>SELECCIÓN DEL EQUIPO — {E.esc(BONITO.get(tienda, tienda.capitalize()))}</b>\n\n<b>{E.esc(nombre[:70])}</b>\n\n"
           f"<b>${precio:,.0f} MXN</b> (-{desc*100:.0f}%)\nNormal: ${orig:,.0f} · ahorras ${orig - precio:,.0f}\n\n"
           f"<a href=\"{E.link_afiliado(url)}\">COMPRAR AHORA</a>")
    mid = E.tg_send(E.cfg_int("CHANNEL_VIP_ID"), txt)
    if not mid:
        return "No pude publicar en el VIP (revisa permisos del bot)."
    E.registrar_publicacion(item, "vip", 6, mid)
    en_free = ""
    if H.puede_pasar_al_free(desc, 6):
        E.cola_agregar(item, 6, 1, delay_min=H.VENTAJA_VIP_MIN)
        en_free = " Pasará al free en 1 hora."
    return f"✅ Publicada en el VIP.{en_free}"


# ─────────────────────────────────────────────
# Buenos días, tip de etiquetas y cuenta regresiva de eventos (siempre "el equipo")
# ─────────────────────────────────────────────
def buenos_dias_vip():
    t = T.actual()
    return bool(E.tg_send(E.cfg_int("CHANNEL_VIP_ID"),
        f"🌅 <b>Buenos días — Canal VIP</b>\n\nEl equipo de DropNode ya está monitoreando las tiendas para encontrar las mejores ofertas de hoy.\n\n"
        f"{t['emoji']} Esta temporada: <b>{E.esc(t['nombre'])}</b> · el equipo prioriza {E.esc(', '.join(t['productos'][:3]))}.\n\n"
        "<i>Recuerda: busca por etiqueta (#tenis, #celulares, #errorprecio…) para ver todo lo relacionado.</i>"))


def buenos_dias_free():
    return bool(E.tg_send(E.cfg_int("CHANNEL_FREE_ID"),
        "🌅 <b>Buenos días</b>\n\nEl equipo de DropNode ya está buscando las mejores ofertas de hoy. "
        "Aquí compartimos una selección; lo mejor llega primero al Canal VIP.",
        boton=("📲 Canal VIP — $299/mes", E.cfg("LAUNCHPASS_LINK"))))


def tip_etiquetas_vip():
    return bool(E.tg_send(E.cfg_int("CHANNEL_VIP_ID"),
        "🔎 <b>Tip VIP: busca por etiquetas</b>\n\nCada oferta del VIP lleva etiquetas. Toca una o escríbela en el buscador del canal y verás "
        "todo lo relacionado:\n\n"
        "• Producto: #celulares #laptops #tenis #bolsas #perfumes #electrodomesticos\n"
        "• Tipo de oferta: #errorprecio #hotdeal #solohoy #idealparareventa\n"
        "• Tienda: #mercadolibre #elektra #liverpool #coppel #samsclub\n"
        "• Marca: #nike #apple #samsung #guess…\n\n"
        "<i>Esta búsqueda es exclusiva del Canal VIP.</i>"))


EVENTOS = [("el Buen Fin", date(2026, 11, 13), "🛍️"), ("Black Friday", date(2026, 11, 27), "⚫"), ("Cyber Monday", date(2026, 11, 30), "💻")]


def evento_cuenta_regresiva():
    """Avisos 14, 7, 3 y 1 días antes y el día de arranque. None si hoy no toca ninguno."""
    hoy = H.ahora().date()
    for nombre, ini, emoji in EVENTOS:
        d = (ini - hoy).days
        if d not in (14, 7, 3, 1, 0):
            continue
        if d == 0:
            vip = f"{emoji} <b>Arrancó {E.esc(nombre)}</b>\n\nEl equipo de DropNode está atento a las mejores ofertas y las publica primero aquí."
        else:
            vip = (f"{emoji} <b>Faltan {d} día{'s' if d > 1 else ''} para {E.esc(nombre)}</b>\n\n"
                   "El equipo de DropNode se prepara para encontrar las mejores ofertas. Mantén las notificaciones del canal activas.")
        ok = bool(E.tg_send(E.cfg_int("CHANNEL_VIP_ID"), vip))
        if H.en_horario_free():
            E.tg_send(E.cfg_int("CHANNEL_FREE_ID"),
                      f"{emoji} <b>{'Arrancó' if d == 0 else 'Se acerca'} {E.esc(nombre)}</b>\n\nEl equipo de DropNode está atento a las mejores ofertas. "
                      "Los descuentos más altos llegan primero al Canal VIP.", boton=("📲 Canal VIP — $299/mes", E.cfg("LAUNCHPASS_LINK")))
        E.tg_send(E.cfg_int("GROUP_ID"), f"{emoji} {'Arrancó' if d == 0 else 'Faltan ' + str(d) + ' día(s) para'} {E.esc(nombre)}. ¿Qué producto estás esperando? Escribe /pedir seguido del producto y el equipo lo busca 👇")
        return ok
    return None
