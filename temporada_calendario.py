# =============================================================
# DROPNODE MX — temporada_calendario.py  (v1.0)
# Calendario de consumo por MES. Fuente única para:
#   - scraper de temporada (qué buscar ese mes)
#   - bonus de score a productos de la temporada
#   - mensajes de comunidad, resúmenes y tips
# Actualiza solo los textos/keywords; la lógica no cambia.
# =============================================================
import unicodedata
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=-6))


def normalizar(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return s.lower()


CALENDARIO = {
    1: dict(nombre="Cuesta de Enero y Rebajas", emoji="💸",
            queries=["lavadora", "refrigerador", "chamarra invierno", "tenis", "television 55", "colchon"],
            palabras=["lavadora", "refrigerador", "chamarra", "abrigo", "tenis", "colchon", "television", "pantalla", "liquidacion"],
            productos=["electrodomésticos", "ropa de invierno", "calzado", "colchones"],
            tip="Enero es de liquidaciones: las tiendas sacan inventario de las fiestas. Compara contra el precio real, no contra el tachado.",
            poll="¿Qué aprovechaste en las rebajas de enero?",
            pregunta="Cuesta de enero 💸 ¿Qué compra te dio más ahorro este mes?",
            reto="Encuentra la mejor rebaja de electrodomésticos y compártela con precio y tienda."),
    2: dict(nombre="San Valentín", emoji="❤️",
            queries=["perfume mujer", "perfume hombre", "joyeria plata", "reloj", "bocina bluetooth", "peluche"],
            palabras=["perfume", "joyeria", "plata", "reloj", "peluche", "chocolate", "flores", "audifonos"],
            productos=["perfumes", "joyería", "relojes", "regalos tecnológicos"],
            tip="Perfumes y joyería suben de precio cerca del 14. Comprar la semana anterior suele salir mejor.",
            poll="¿Cuánto sueles gastar en San Valentín?",
            pregunta="❤️ ¿Qué regalo con buen precio tienes en la mira para San Valentín?",
            reto="Comparte la mejor idea de regalo por menos de $1,000."),
    3: dict(nombre="Playa, Vacaciones y Semana Santa", emoji="🏖️",
            queries=["traje de bano", "inflable alberca", "juguetes de arena", "lentes de sol", "hielera", "sandalias"],
            palabras=["traje de bano", "bikini", "inflable", "alberca", "arena", "playa", "lentes de sol", "hielera", "sandalia", "maleta", "sombrilla", "flotador"],
            productos=["trajes de baño", "inflables", "juguetes de arena", "lentes de sol", "hieleras"],
            tip="Semana Santa: lo de playa (inflables, trajes de baño, hieleras) baja de precio si compras antes de que empiece la temporada alta.",
            poll="¿Cuál es tu plan de vacaciones?",
            pregunta="🏖️ ¿Qué producto de playa o vacaciones quieres encontrar barato?",
            reto="Arma tu kit de playa completo al menor precio y comparte la lista."),
    4: dict(nombre="Vacaciones y Día del Niño", emoji="🧸",
            queries=["juguete", "lego", "bicicleta infantil", "alberca inflable", "traje de bano nino", "patineta"],
            palabras=["juguete", "lego", "bicicleta", "muneca", "inflable", "alberca", "patineta", "nino", "infantil", "peluche", "consola"],
            productos=["juguetes", "bicicletas", "juegos de mesa", "ropa infantil"],
            tip="El 30 de abril es Día del Niño: los juguetes populares se agotan la semana anterior.",
            poll="¿Cuánto inviertes en el Día del Niño?",
            pregunta="🧸 Día del Niño en puerta: ¿qué juguete están buscando en tu casa?",
            reto="Encuentra el mejor juguete por menos de $500 y compártelo."),
    5: dict(nombre="Día de las Madres y Hot Sale", emoji="💐",
            queries=["perfume mujer", "licuadora", "freidora de aire", "joyeria", "bolsa mujer", "celular"],
            palabras=["perfume", "licuadora", "freidora", "cafetera", "joyeria", "bolsa", "spa", "aspiradora", "celular", "laptop"],
            productos=["perfumes", "electrodomésticos de cocina", "joyería", "bolsas"],
            tip="Mayo y junio concentran Día de las Madres y Hot Sale: es cuando más errores de precio aparecen. Revisa el historial antes de comprar.",
            poll="¿Qué le regalarías a mamá con buen descuento?",
            pregunta="💐 ¿Qué producto buscas para sorprender a mamá sin gastar de más?",
            reto="Comparte el mejor regalo para mamá que encuentres por menos de $1,500."),
    6: dict(nombre="Hot Sale y Día del Padre", emoji="🔥",
            queries=["celular", "laptop", "television", "herramientas", "audifonos", "consola"],
            palabras=["celular", "laptop", "television", "pantalla", "herramienta", "taladro", "audifonos", "consola", "reloj", "ventilador"],
            productos=["electrónica", "herramientas", "consolas", "ventiladores"],
            tip="Hot Sale: combina el descuento de la tienda con el cupón bancario; el precio final real casi siempre está ahí.",
            poll="¿Qué comprarías si encuentras un 50% de descuento real?",
            pregunta="🔥 ¿Qué producto llevas meses esperando para comprar en oferta?",
            reto="Encuentra la mejor oferta de herramientas para papá y compártela."),
    7: dict(nombre="Regreso a Clases", emoji="🎒",
            queries=["laptop estudiante", "mochila escolar", "tablet", "impresora", "audifonos", "uniforme escolar"],
            palabras=["laptop", "mochila", "tablet", "impresora", "escolar", "uniforme", "utiles", "calculadora", "escritorio", "silla"],
            productos=["laptops", "tablets", "mochilas", "impresoras", "útiles"],
            tip="Julio y agosto traen los mejores precios del año en laptops y tablets; los modelos nuevos llegan en septiembre.",
            poll="¿Cuánto gastas en regreso a clases por hijo?",
            pregunta="🎒 ¿Qué necesitas encontrar al mejor precio para el regreso a clases?",
            reto="Arma la lista de útiles completa al menor precio y compártela."),
    8: dict(nombre="Regreso a Clases", emoji="📚",
            queries=["laptop", "mochila", "zapatos escolares", "tablet", "escritorio", "impresora"],
            palabras=["laptop", "mochila", "zapato", "escolar", "tablet", "escritorio", "impresora", "utiles", "uniforme"],
            productos=["laptops", "uniformes", "zapatos escolares", "mochilas"],
            tip="Últimas semanas de regreso a clases: las laptops y tablets tienen sus precios más bajos, pero el stock se mueve rápido.",
            poll="¿Ya terminaste tus compras de regreso a clases?",
            pregunta="📚 Última semana de regreso a clases: ¿qué te falta conseguir?",
            reto="Comparte la mejor compra escolar que hiciste este año y cuánto ahorraste."),
    9: dict(nombre="Fiestas Patrias", emoji="🇲🇽",
            queries=["parrilla", "decoracion mexicana", "sombrero charro", "bocina", "hielera", "television"],
            palabras=["parrilla", "asador", "hielera", "bocina", "decoracion", "sarape", "mexicana", "cerveza", "carbon", "televisor", "television"],
            productos=["parrillas", "hieleras", "bocinas", "decoración patria", "televisores"],
            tip="Septiembre: parrillas, hieleras y bocinas se encarecen cerca del 15. Compra con anticipación.",
            poll="¿Cómo celebras las Fiestas Patrias?",
            pregunta="🇲🇽 ¿Qué producto para la carne asada o la fiesta andas buscando?",
            reto="Encuentra la mejor parrilla o asador por menos de $3,000 y compártela."),
    10: dict(nombre="Halloween y Día de Muertos", emoji="🎃",
             queries=["disfraz", "decoracion halloween", "maquillaje artistico", "calaveras", "luces led", "television"],
             palabras=["disfraz", "halloween", "calavera", "catrina", "maquillaje", "decoracion", "luces", "dulces", "cempasuchil", "altar", "vela"],
             productos=["disfraces", "decoración", "maquillaje artístico", "luces"],
             tip="Los disfraces y la decoración tienen sus mejores precios 2-3 semanas antes del 31. Después se agotan o suben.",
             poll="¿Cómo celebras Halloween o Día de Muertos?",
             pregunta="🎃 ¿Ya tienes disfraz o decoración lista? ¿Qué buscas con descuento?",
             reto="Encuentra el mejor disfraz familiar por menos de $800 y compártelo."),
    11: dict(nombre="Buen Fin y Black Friday", emoji="🛍️",
             queries=["television", "celular", "laptop", "lavadora", "consola", "audifonos"],
             palabras=["television", "pantalla", "celular", "laptop", "lavadora", "refrigerador", "consola", "audifonos", "tablet", "bocina"],
             productos=["televisores", "celulares", "laptops", "línea blanca", "consolas"],
             tip="Buen Fin: no compres en las primeras horas sin revisar el historial; hay precios inflados para 'bajarlos' después.",
             poll="¿Cuánto planeas gastar en el Buen Fin?",
             pregunta="🛍️ ¿Qué producto llevas meses esperando para comprar en el Buen Fin?",
             reto="Comparte tu lista de compras del Buen Fin con el precio objetivo de cada una."),
    12: dict(nombre="Navidad y Cierre de Año", emoji="🎄",
             queries=["juguete", "consola", "arbol de navidad", "perfume", "pantalla", "lego"],
             palabras=["juguete", "consola", "navidad", "arbol", "perfume", "lego", "pantalla", "luces", "regalo", "bocina"],
             productos=["juguetes", "consolas", "decoración navideña", "perfumes"],
             tip="Los juguetes populares se agotan antes del 15 de diciembre; las liquidaciones de electrónica llegan después del 26.",
             poll="¿Cuánto gastas en regalos de Navidad?",
             pregunta="🎄 ¿Ya tienes todos los regalos o todavía buscas algo con buen precio?",
             reto="Encuentra el mejor regalo por menos de $500 y compártelo."),
}


def ahora():
    return datetime.now(TZ)


def actual(dt=None):
    return CALENDARIO[(dt or ahora()).month]


def queries_rotativas(n=3, dt=None):
    """n queries del mes, rotando por día/hora para cubrir todas."""
    dt = dt or ahora()
    qs = actual(dt)["queries"]
    base = (dt.timetuple().tm_yday * 4 + dt.hour // 6) % len(qs)
    return [qs[(base + i) % len(qs)] for i in range(min(n, len(qs)))]


def bonus_item(nombre, categoria="", dt=None):
    """+1.0 al score si el producto es de la temporada del mes."""
    txt = normalizar(f"{nombre} {categoria}")
    for p in actual(dt)["palabras"]:
        if normalizar(p) in txt:
            return 1.0
    return 0.0


def etiqueta(dt=None):
    t = actual(dt)
    return f"{t['emoji']} {t['nombre']}"
