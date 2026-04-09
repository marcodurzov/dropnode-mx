# =============================================================
# DROPNODE MX — config.py
# Configuración central del sistema
# NUNCA compartir este archivo públicamente
# =============================================================

# --- SUPABASE (Base de datos) ---
SUPABASE_URL = "https://zssrlvchovlcehhlvdfm.supabase.co"
SUPABASE_KEY = "sb_publishable_IgTaSZpi5MdS6RyPiVWyXw_NybM_w2W"

# --- TELEGRAM ---
TELEGRAM_TOKEN = "8608754195:AAGaJNwtnAEh_N15cJOXP-1F0qVp0Yixlps"
CHANNEL_FREE_ID  = -1003897783132   # Canal público: DropNode MX
CHANNEL_VIP_ID   = -1003840453350   # Canal privado: DropNode VIP
GROUP_ID         = -1003848632862   # Grupo: DropNode Community

# --- AFILIADOS ---
ML_AFFILIATE_ID  = "marcodurzo"     # Tu ID en ML Afiliados
AMAZON_TAG       = ""               # Llenar cuando Amazon apruebe: ej. "dropnodemx-20"

# --- UMBRALES DE DETECCIÓN ---
# Descuento mínimo vs mínimo histórico de 90 días (no vs precio tachado)
UMBRAL_DESCUENTO_VIP  = 0.50   # 50%+ → canal VIP inmediato
UMBRAL_DESCUENTO_FREE = 0.30   # 30%+ → canal gratuito

# Heat Score
HEAT_VIP_MIN  = 8   # Score 8-10 → VIP
HEAT_FREE_MIN = 5   # Score 5-7  → Free
# Score 0-4 → descartar silenciosamente

# Días de historial para calcular el "precio mínimo real"
DIAS_HISTORIAL = 90

# --- ANTI-BLOQUEO: delays aleatorios entre peticiones (segundos) ---
DELAY_MIN = 3
DELAY_MAX = 9

# --- CATEGORÍAS DE MERCADO LIBRE A MONITOREAR ---
# Ordenadas por rentabilidad de afiliado + frecuencia de errores de precio
CATEGORIAS_ML = [
    {"id": "MLM1051",  "nombre": "Celulares",         "emoji": "📱"},
    {"id": "MLM1648",  "nombre": "Computación",        "emoji": "💻"},
    {"id": "MLM1000",  "nombre": "Electrónica",        "emoji": "🔌"},
    {"id": "MLM1002",  "nombre": "Televisores",        "emoji": "📺"},
    {"id": "MLM1574",  "nombre": "Electrodomésticos",  "emoji": "🏠"},
    {"id": "MLM1144",  "nombre": "Videojuegos",        "emoji": "🎮"},
    {"id": "MLM1276",  "nombre": "Herramientas",       "emoji": "🔧"},
    {"id": "MLM1499",  "nombre": "Deportes",           "emoji": "⚽"},
]

# Máximo de productos a revisar por categoría en cada ciclo
MAX_ITEMS_POR_CATEGORIA = 48

# --- HORARIO DE OPERACIÓN ---
# El sistema solo envía alertas en este horario (respeto de audiencia)
HORA_INICIO_ENVIOS = 8    # 8:00 AM
HORA_FIN_ENVIOS    = 22   # 10:00 PM

# --- AUTO-LEARNING ---
# Cada cuántas horas se ejecuta el optimizador
FRECUENCIA_AUTOLEARNING_HORAS = 24

# Mínimo de datos para ajustar umbrales automáticamente
MIN_ALERTAS_PARA_APRENDER = 20
