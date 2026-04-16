# =============================================================
# DROPNODE MX — config.py  (v1.4)
# Nu y GBM+ activados con links reales
# NUNCA compartir este archivo publicamente
# =============================================================

# --- SUPABASE ---
SUPABASE_URL = "https://zssrlvchovlcehhlvdfm.supabase.co"
SUPABASE_KEY = "sb_publishable_IgTaSZpi5MdS6RyPiVWyXw_NybM_w2W"

# --- TELEGRAM ---
TELEGRAM_TOKEN   = "8608754195:AAGaJNwtnAEh_N15cJOXP-1F0qVp0Yixlps"
CHANNEL_FREE_ID  = -1003897783132
CHANNEL_VIP_ID   = -1003840453350
GROUP_ID         = -1003848632862

# --- AFILIADOS ---
ML_AFFILIATE_ID = "marcodurzo"
AMAZON_TAG      = "dropnodemx-20"
LAUNCHPASS_LINK = "https://www.launchpass.com/marcodurzo/dropnodemxvip"

# --- MODO ARRANQUE EN FRIO ---
MODO_FRIO   = True
UMBRAL_FRIO = 0.35

# --- UMBRALES NORMALES ---
UMBRAL_DESCUENTO_VIP  = 0.50
UMBRAL_DESCUENTO_FREE = 0.30
DIAS_HISTORIAL        = 90

# --- HEAT SCORE ---
HEAT_VIP_MIN  = 7
HEAT_FREE_MIN = 5

# --- ANTI-BLOQUEO ---
DELAY_MIN = 4
DELAY_MAX = 11

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

# --- HORARIO ---
HORA_INICIO_ENVIOS = 8
HORA_FIN_ENVIOS    = 22

# --- AUTO-LEARNING ---
FRECUENCIA_AUTOLEARNING_HORAS = 24
MIN_ALERTAS_PARA_APRENDER     = 20

# --- PRODUCTOS FINANCIEROS ---
# Rota automaticamente entre los activos
# Para agregar Vexi y GBM link real: reemplaza el link cuando lo tengas
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
        "nombre":      "GBM+",
        "descripcion": "Invierte el dinero que ahorras con las ofertas",
        "beneficio":   "Rendimiento diario desde $100 MXN, sin comisiones",
        "link":        "https://gbm.com",   # <-- Reemplazar con tu link de referido GBM
        "emoji":       "📈",
        "activo":      False,  # Activar cuando tengas tu link de referido
    },
    {
        "nombre":      "Vexi",
        "descripcion": "Tarjeta de credito para construir historial crediticio",
        "beneficio":   "Aprobacion rapida sin buro. Ideal para empezar tu historial.",
        "link":        "https://vexi.mx",   # <-- Reemplazar con tu link de referido Vexi
        "emoji":       "🟦",
        "activo":      False,  # Activar cuando tengas tu link de referido
    },
    {
        "nombre":      "Bitso",
        "descripcion": "Compra dolares desde tu celular al mejor tipo de cambio",
        "beneficio":   "Util para aprovechar ofertas en tiendas internacionales",
        "link":        "https://bitso.com",
        "emoji":       "₿",
        "activo":      False,  # Activar cuando tengas tu link de referido
    },
]

# Horas para mensajes financieros (canal free, VIP y grupo)
HORAS_MENSAJES_FINANCIEROS = [11, 18]

# Horas para recordatorio VIP (solo canal free)
HORAS_RECORDATORIO_VIP = [14, 20]
