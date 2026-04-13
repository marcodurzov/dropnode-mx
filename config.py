# =============================================================
# DROPNODE MX — config.py  (version final)
# NUNCA compartas este archivo publicamente
# =============================================================

# --- SUPABASE ---
SUPABASE_URL = "https://zssrlvchovlcehhlvdfm.supabase.co"
SUPABASE_KEY = "sb_publishable_IgTaSZpi5MdS6RyPiVWyXw_NybM_w2W"

# --- TELEGRAM ---
TELEGRAM_TOKEN   = "8608754195:AAGaJNwtnAEh_N15cJOXP-1F0qVp0Yixlps"
CHANNEL_FREE_ID  = -1003897783132   # Canal publico: DropNode MX
CHANNEL_VIP_ID   = -1003840453350   # Canal privado: DropNode VIP
GROUP_ID         = -1003848632862   # Grupo: DropNode Community

# --- AFILIADOS ---
ML_AFFILIATE_ID = "marcodurzo"       # Tu ID de ML Afiliados
AMAZON_TAG      = "dropnodemx-20"    # Tu tag de Amazon Associates USA

# --- LAUNCHPASS (cobro VIP) ---
LAUNCHPASS_LINK = "https://www.launchpass.com/marcodurzo/dropnodemxvip"

# --- MODO ARRANQUE EN FRIO ---
# True = compara vs precio tachado de ML (funciona desde dia 1, menos preciso)
# False = compara vs minimo historico 90 dias (mas preciso, cambiar despues de 30 dias)
MODO_FRIO   = True
UMBRAL_FRIO = 0.35   # 35% de descuento minimo para alertar en modo frio

# --- UMBRALES NORMALES (cuando MODO_FRIO = False) ---
UMBRAL_DESCUENTO_VIP  = 0.50
UMBRAL_DESCUENTO_FREE = 0.30
DIAS_HISTORIAL        = 90

# --- HEAT SCORE (que canal recibe cada alerta) ---
HEAT_VIP_MIN  = 7    # Score 7-10 -> canal VIP
HEAT_FREE_MIN = 5    # Score 5-6  -> canal free
                     # Score 0-4  -> se descarta

# --- ANTI-BLOQUEO (tiempo de espera entre peticiones) ---
DELAY_MIN = 4    # segundos minimo
DELAY_MAX = 11   # segundos maximo

# --- CATEGORIAS DE MERCADO LIBRE A MONITOREAR ---
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

# --- HORARIO DE OPERACION ---
HORA_INICIO_ENVIOS = 8    # 8:00 AM - primera alerta del dia
HORA_FIN_ENVIOS    = 22   # 10:00 PM - ultima alerta del dia

# --- AUTO-LEARNING ---
FRECUENCIA_AUTOLEARNING_HORAS = 24
MIN_ALERTAS_PARA_APRENDER     = 20

# --- PRODUCTOS FINANCIEROS ---
# Mensajes automaticos en canal free — 2 veces al dia
# Cuando tengas links de referido de Nu, GBM, Bitso: reemplaza los links
PRODUCTOS_FINANCIEROS = [
    {
        "nombre":      "Plata Card",
        "descripcion": "Tarjeta sin anualidad + cashback en cada compra",
        "beneficio":   "Cada oferta que compres aqui te genera recompensa adicional",
        "link":        "https://platacard.mx/amigos/marco2eeh",
        "emoji":       "💳",
        "activo":      True,
    },
    {
        "nombre":      "Nu (Nubank MX)",
        "descripcion": "Tarjeta de credito sin comisiones ni anualidad",
        "beneficio":   "Sin letra chica. Limite que crece con el uso.",
        "link":        "https://nu.com.mx",
        "emoji":       "💜",
        "activo":      True,
    },
    {
        "nombre":      "GBM+",
        "descripcion": "Invierte el dinero que ahorras con las ofertas",
        "beneficio":   "Rendimiento diario desde $100 MXN, sin comisiones",
        "link":        "https://gbm.com",
        "emoji":       "📈",
        "activo":      True,
    },
    {
        "nombre":      "Bitso",
        "descripcion": "Compra dolares desde tu celular al mejor tipo de cambio",
        "beneficio":   "Util para aprovechar ofertas en tiendas internacionales",
        "link":        "https://bitso.com",
        "emoji":       "₿",
        "activo":      False,   # Cambiar a True cuando tengas tu link de referido Bitso
    },
]

# Horas del dia para mensajes financieros en canal free
HORAS_MENSAJES_FINANCIEROS = [11, 18]   # 11 AM y 6 PM

# Horas del dia para recordatorio VIP en canal free
HORAS_RECORDATORIO_VIP = [14, 20]       # 2 PM y 8 PM
