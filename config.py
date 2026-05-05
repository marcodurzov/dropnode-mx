# =============================================================
# DROPNODE MX — config.py  (v1.7)
# + eBay Partner agregado
# + CJ Dropshipping como canal de dropshippers (nicho diferente)
# NUNCA compartir este archivo publicamente
# =============================================================

SUPABASE_URL = "https://zssrlvchovlcehhlvdfm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inpzc3JsdmNob3ZsY2VoaGx2ZGZtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU1MzkzMzAsImV4cCI6MjA5MTExNTMzMH0.-MPnRXkAiepKchuPlMwN17RsKhhUPHFBj2qNgHw3Dfw"

TELEGRAM_TOKEN   = "8608754195:AAGaJNwtnAEh_N15cJOXP-1F0qVp0Yixlps"
CHANNEL_FREE_ID  = -1003897783132
CHANNEL_VIP_ID   = -1003840453350
GROUP_ID         = -1003848632862

ML_AFFILIATE_ID  = "marcodurzo"
AMAZON_TAG       = "dropnodemx-20"
EBAY_CAMPAIGN_ID = "5339151577"
EBAY_CUSTOM_ID   = "dropnodemx"
LAUNCHPASS_LINK  = "https://www.launchpass.com/marcodurzo/dropnodemxvip"

# Make.com Webhook URL (llenar cuando lo configures)
MAKE_WEBHOOK_URL = ""

MODO_FRIO   = True
UMBRAL_FRIO = 0.35

UMBRAL_DESCUENTO_VIP  = 0.50
UMBRAL_DESCUENTO_FREE = 0.30
DIAS_HISTORIAL        = 90

HEAT_VIP_MIN  = 7
HEAT_FREE_MIN = 5

DELAY_MIN = 4
DELAY_MAX = 11

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

HORA_INICIO_ENVIOS = 8
HORA_FIN_ENVIOS    = 22

FRECUENCIA_AUTOLEARNING_HORAS = 24
MIN_ALERTAS_PARA_APRENDER     = 20

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
        "beneficio":   "Aprobacion rapida sin buro. Ideal para empezar tu historial.",
        "link":        "https://vexi.mx",
        "emoji":       "🟦",
        "activo":      False,
    },
]

HORAS_MENSAJES_FINANCIEROS = [11, 18]
HORAS_RECORDATORIO_VIP     = [14, 20]
