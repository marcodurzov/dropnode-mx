# =============================================================
# DROPNODE MX — etiquetas.py  (v1.0)
# Hashtags para TODAS las alertas del VIP (sin importar la tienda) y bonus de marcas conocidas.
# Los hashtags solo van en el VIP: es lo que permite a los miembros buscar por etiqueta.
# =============================================================
import unicodedata


def _n(x):
    return unicodedata.normalize("NFKD", str(x or "")).encode("ascii", "ignore").decode().lower()


CATEGORIAS = [
    ("#bolsas",        ["bolsa", "mochila", "cartera", "bandolera", "crossbody", "maleta", "backpack", "tote"]),
    ("#tenis",         ["tenis", "sneaker", "running", "air max", "air force", "yeezy", "ultraboost", "new balance", "jordan"]),
    ("#calzado",       ["zapato", "zapatilla", "bota", "botin", "sandalia", "huarache", "mocasin", "tacon", "calzado"]),
    ("#moda",          ["camisa", "pantalon", "vestido", "licra", "legging", "blusa", "ropa", "playera", "chamarra", "short",
                        "sudadera", "jeans", "abrigo", "sueter", "falda"]),
    ("#perfumes",      ["perfume", "fragancia", "eau de", "colonia", "parfum"]),
    ("#belleza",       ["maquillaje", "serum", "crema", "shampoo", "minoxidil", "labial", "rubor", "skincare", "secadora de cabello", "plancha"]),
    ("#relojes",       ["reloj", "smartwatch", "watch", "band "]),
    ("#joyeria",       ["anillo", "collar", "pulsera", "arete", "joyeria", "plata 925"]),
    ("#celulares",     ["iphone", "galaxy", "celular", "smartphone", "redmi", "poco", "moto g", "pixel"]),
    ("#laptops",       ["laptop", "notebook", "macbook", "thinkpad", "ideapad", "chromebook", "vivobook"]),
    ("#televisores",   ["televisor", " tv ", "smart tv", "oled", "qled", "pantalla 4k"]),
    ("#audio",         ["audifonos", "airpods", "bocina", "speaker", "wh-", "wf-", "earbuds", "soundbar"]),
    ("#gaming",        ["playstation", "xbox", "nintendo", "switch", "ps5", "ps4", "videojuego", "gamer", "consola"]),
    ("#tablets",       ["tablet", "ipad"]),
    ("#computacion",   ["impresora", "router", "monitor", "teclado", "mouse", "disco duro", "ssd", "memoria usb"]),
    ("#electrodomesticos", ["lavadora", "refrigerador", "estufa", "microondas", "licuadora", "aspiradora", "freidora", "cafetera", "horno"]),
    ("#herramientas",  ["taladro", "herramienta", "martillo", "destornillador", "sierra", "llave", "rotomartillo", "esmeril"]),
    ("#hogar",         ["silla", "mesa", "sofa", "lampara", "colchon", "cortina", "toalla", "sabana", "almohada", "mueble", "cajonera", "escritorio"]),
    ("#juguetes",      ["juguete", "muneca", "lego", "figura", "plush", "peluche", "rompecabezas"]),
    ("#bebes",         ["bebe", "pañal", "panal", "carriola", "andadera", "biberon"]),
    ("#mascotas",      ["perro", "gato", "mascota", "croqueta", "arena para gato", "correa"]),
    ("#deportes",      ["bicicleta", "pesas", "mancuerna", "caminadora", "balon", "yoga", "fitness"]),
    ("#autos",         ["llanta", "aceite", "cera", "autoestereo", "dashcam"]),
]

MARCAS = {
    "apple": ["iphone", "ipad", "macbook", "airpods", "apple"], "samsung": ["samsung", "galaxy"], "sony": ["sony", "playstation"],
    "lenovo": ["lenovo", "thinkpad", "ideapad"], "dell": ["dell", "inspiron"], "hp": [" hp "], "asus": ["asus"],
    "xiaomi": ["xiaomi", "redmi", "poco"], "motorola": ["motorola", "moto "], "lg": [" lg "], "bosch": ["bosch"],
    "dewalt": ["dewalt"], "milwaukee": ["milwaukee"], "nike": ["nike", "jordan", "air max", "air force"], "adidas": ["adidas"],
    "puma": ["puma"], "newbalance": ["new balance"], "skechers": ["skechers"], "guess": ["guess"],
    "michaelkors": ["michael kors", " mk "], "coach": ["coach"], "levis": ["levi's", "levis"], "tommy": ["tommy hilfiger"],
    "calvinklein": ["calvin klein"], "lacoste": ["lacoste"], "ralphlauren": ["ralph lauren", "polo ralph"], "on": [" on cloud", "on running"],
    "hokaone": ["hoka"], "underarmour": ["under armour"], "gucci": ["gucci"], "carolinaherrera": ["carolina herrera"],
    "nintendo": ["nintendo"], "microsoft": ["xbox", "microsoft"], "jbl": ["jbl"], "bose": ["bose"],
}
# marcas que la gente "quiere encontrar en descuento" (moda/estatus): suman un punto de interés
PREMIUM = {"guess", "michaelkors", "coach", "nike", "adidas", "newbalance", "levis", "tommy", "calvinklein", "lacoste",
           "ralphlauren", "on", "hokaone", "underarmour", "gucci", "carolinaherrera", "apple", "sony", "bose", "jbl"}

TIENDAS = {"mercadolibre": "#mercadolibre", "elektra": "#elektra", "liverpool": "#liverpool", "coppel": "#coppel",
           "walmart": "#walmart", "bodega": "#bodegaaurrera", "sams": "#samsclub", "costco": "#costco", "amazon": "#amazon",
           "palacio": "#palaciodehierro", "sears": "#sears", "suburbia": "#suburbia", "sanborns": "#sanborns",
           "claroshop": "#claroshop", "bestbuy": "#bestbuy", "officedepot": "#officedepot", "homedepot": "#homedepot",
           "cyberpuerta": "#cyberpuerta", "heb": "#heb", "petco": "#petco", "innovasport": "#innovasport",
           "dportenis": "#dportenis", "puma": "#puma", "skechers": "#skechers", "priceshoes": "#priceshoes"}


def marcas_en(nombre):
    n = " " + _n(nombre) + " "
    return [m for m, kws in MARCAS.items() if any(kw in n for kw in kws)]


def bonus_marca(nombre):
    """+1 punto de interés si es una marca que la gente quiere encontrar en descuento."""
    return 1.0 if any(m in PREMIUM for m in marcas_en(nombre)) else 0.0


def generar(nombre, descuento, score, tienda="", categoria="", cupon=False, es_flash=False):
    """Cadena de hashtags: categoría · marca · tienda · tipo de oferta."""
    n = " " + _n(nombre) + " "
    tags = []
    for tag, kws in CATEGORIAS:
        if any(_n(k) in n for k in kws):
            tags.append(tag)
            break
    else:
        cat = _n(categoria).replace(" ", "")
        if len(cat) > 2 and cat not in ("mercadolibre", "mlofertas", "ofertas", "general"):
            tags.append("#" + cat)
    for m in marcas_en(nombre)[:1]:
        tags.append("#" + m)
    t = TIENDAS.get(_n(tienda))
    if t:
        tags.append(t)
    if score >= 8 or descuento >= 0.50:
        tags.append("#errorprecio")
    elif descuento >= 0.35:
        tags.append("#hotdeal")
    if es_flash:
        tags.append("#solohoy")
    if cupon:
        tags.append("#cupon")
    if descuento >= 0.50:
        tags.append("#idealparareventa")
    return " ".join(dict.fromkeys(tags))
