# =============================================================
# DROPNODE MX — config.py   (v2.0)
# v2.0: SIN SECRETOS. Todo lo sensible se lee de variables de entorno
#       (GitHub -> Settings -> Secrets and variables -> Actions).
# + Timezone Mexico City (UTC-6)
# + Umbrales ajustados para generar contenido diario
# + Multiples tiendas activadas
# =============================================================

import os


def _env(nombre, default=""):
    return str(os.environ.get(nombre, default) or default).strip()


def _env_int(nombre, default=0):
    try:
        return int(_env(nombre, str(default)))
    except Exception:
        return default

SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_KEY = _env("SUPABASE_KEY")

TELEGRAM_TOKEN   = _env("TELEGRAM_TOKEN")
CHANNEL_FREE_ID  = _env_int("CHANNEL_FREE_ID", -1003897783132)
CHANNEL_VIP_ID   = _env_int("CHANNEL_VIP_ID", -1003840453350)
GROUP_ID         = _env_int("GROUP_ID", -1003848632862)

ML_AFFILIATE_ID  = "marcodurzo"
AMAZON_TAG       = "dropnodemx-20"
EBAY_CAMPAIGN_ID = "5339151577"
EBAY_CUSTOM_ID   = "dropnodemx"
LAUNCHPASS_LINK  = "https://www.launchpass.com/marcodurzo/dropnodemxvip"
MAKE_WEBHOOK_URL = _env("MAKE_WEBHOOK_URL")

# --- TIMEZONE ---
# Mexico City / Guadalajara / Monterrey — UTC-6 (sin horario de verano desde 2023)
TIMEZONE_OFFSET_HOURS = -6

# --- UMBRALES ---
MODO_FRIO   = True
UMBRAL_FRIO = 0.15   # 15% — genera contenido diario garantizado

# Umbral separado por canal
UMBRAL_VIP  = 0.30   # 30%+ va al VIP (exclusivo)
UMBRAL_FREE = 0.15   # 15%+ va al free

UMBRAL_DESCUENTO_VIP  = 0.30
UMBRAL_DESCUENTO_FREE = 0.15
DIAS_HISTORIAL        = 90

HEAT_VIP_MIN  = 6
HEAT_FREE_MIN = 3

# --- ANTI-BLOQUEO ---
DELAY_MIN = 4
DELAY_MAX = 11

# --- TIENDAS A MONITOREAR ---
# Con afiliado: ML, Amazon, eBay
# Sin afiliado pero con contenido de valor: Walmart, Coppel, Liverpool
TIENDAS_ACTIVAS = {
    "mercadolibre": True,
    "walmart":      True,
    "coppel":       True,
    "liverpool":    True,   # Scraping directo, sin afiliado por ahora
}

# --- CATEGORIAS ML ---
CATEGORIAS_ML = [
    {"id": "MLM1051", "nombre": "Celulares",         "emoji": "📱"},
    {"id": "MLM1648", "nombre": "Computacion",        "emoji": "💻"},
    {"id": "MLM1000", "nombre": "Electronica",        "emoji": "🔌"},
    {"id": "MLM1002", "nombre": "Televisores",        "emoji": "📺"},
    {"id": "MLM1574", "nombre": "Electrodomesticos",  "emoji": "🏠"},
    {"id": "MLM1144", "nombre": "Videojuegos",        "emoji": "🎮"},
    {"id": "MLM1276", "nombre": "Herramientas",       "emoji": "🔧"},
    {"id": "MLM1499", "nombre": "Deportes",           "emoji": "⚽"},
]
MAX_ITEMS_POR_CATEGORIA = 48

# --- HORARIO (hora local Mexico City) ---
# El sistema convierte automaticamente de UTC a hora Mexico
HORA_INICIO_ENVIOS = 8    # 8:00 AM hora Mexico
HORA_FIN_ENVIOS    = 22   # 10:00 PM hora Mexico

FRECUENCIA_AUTOLEARNING_HORAS = 24
MIN_ALERTAS_PARA_APRENDER     = 20

# --- PRODUCTOS FINANCIEROS ---
PRODUCTOS_FINANCIEROS = [
    {
        "nombre":      "Plata Card",
        "descripcion": "Tarjeta sin anualidad con cashback en cada compra",
        "beneficio":   "Cada oferta que compres aqui te genera recompensa adicional",
        "link":        "https://platacard.mx/amigos/marco2eeh",
        "emoji":       "💳",
        "activo":      True,
    },
    {
        "nombre":      "Nu",
        "descripcion": "Tarjeta de credito con $0 anualidad y cuenta de debito",
        "beneficio":   "Tu dinero crece hasta 13% anual en la cuenta Nu",
        "link":        "https://nu.com.mx/mgm/?channel=referral&id=LNCqQBH3cpk4qn0W56ZAjw&medium=other&msg=06478&source=mgm",
        "emoji":       "💜",
        "activo":      True,
    },
    {
        "nombre":      "Flink",
        "descripcion": "Invierte desde $1 MXN con rendimientos diarios",
        "beneficio":   "Haz crecer el dinero que ahorras con cada oferta",
        "link":        "https://flink.com.mx",
        "emoji":       "📊",
        "activo":      False,
    },
    {
        "nombre":      "Vexi",
        "descripcion": "Tarjeta de credito para construir historial crediticio",
        "beneficio":   "Aprobacion rapida sin buro.",
        "link":        "https://vexi.mx",
        "emoji":       "🟦",
        "activo":      False,
    },
]

# Horarios en hora Mexico City
HORAS_MENSAJES_FINANCIEROS = [11, 18]
HORAS_RECORDATORIO_VIP     = [14, 20]
HORA_RESUMEN_DIARIO        = 21
