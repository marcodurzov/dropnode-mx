# =============================================================
# DROPNODE MX — horarios.py  (v1.0)
# UNA sola fuente de verdad para las reglas de canal:
#   - Horarios VIP / Free
#   - Modo nocturno (VIP solo score >= 8)
#   - Ventana VIP -> Free (60 min)
#   - Qué es "exclusivo VIP"
# Usado por main.py, github_scraper_ml.py, community_manager.py
# =============================================================
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=-6))          # Ciudad de México (sin horario de verano)

# ── Horarios (minutos desde medianoche, hora México) ──
VIP_INICIO  = 6 * 60 + 30     # 6:30 AM
VIP_FIN     = 23 * 60 + 30    # 11:30 PM
FREE_INICIO = 8 * 60          # 8:00 AM
FREE_FIN    = 19 * 60         # 7:00 PM (las 7:01 PM ya no se publica)

SCORE_NOCTURNO   = 8          # 11:31 PM - 6:29 AM: VIP solo si score >= 8
VENTAJA_VIP_MIN  = 60         # lo que pasa del VIP al free sale 60 min después

# ── Qué es exclusivo VIP ──
VIP_EXCL_DESCUENTO = 0.35
VIP_EXCL_SCORE     = 7
# Al canal free pasa (1 hora después) todo EXCEPTO los errores de precio (score >= FREE_BLOQUEA_SCORE),
# que se quedan solo en el VIP y aparecen en el resumen del día pasada 1 hora.
FREE_BLOQUEA_SCORE = 8

FREE_MAX_POR_DIA   = 24       # tope diario de alertas en el canal free
FREE_MAX_POR_CORRIDA = 2      # tope por corrida (cada 15 min)

DIAS  = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def ahora():
    return datetime.now(TZ)


def _min(dt=None):
    dt = dt or ahora()
    return dt.hour * 60 + dt.minute


def en_horario_vip(dt=None):
    return VIP_INICIO <= _min(dt) <= VIP_FIN


def modo_nocturno(dt=None):
    return not en_horario_vip(dt)


def en_horario_free(dt=None):
    return FREE_INICIO <= _min(dt) <= FREE_FIN


def vip_puede_publicar(score, dt=None):
    """Horario normal: lo decide el umbral de cada flujo. Nocturno: solo score >= 8."""
    return en_horario_vip(dt) or score >= SCORE_NOCTURNO


def es_exclusivo(descuento, score, es_flash=False):
    return bool(descuento >= VIP_EXCL_DESCUENTO or score >= VIP_EXCL_SCORE or es_flash)


def puede_pasar_al_free(descuento, score, es_flash=False):
    return score < FREE_BLOQUEA_SCORE


def nivel_emoji(descuento, score, es_flash=False):
    if es_exclusivo(descuento, score, es_flash):
        return "🔴"
    return "🟠" if descuento >= 0.30 else "🟡"


def fecha_mx(dt=None):
    return (dt or ahora()).strftime("%Y-%m-%d")


def fecha_larga(dt=None):
    dt = dt or ahora()
    return f"{DIAS[dt.weekday()]} {dt.day} de {MESES[dt.month - 1]}"


def dia_inicio_utc(dt=None):
    """Medianoche de HOY en México, expresada como datetime UTC naive
    (así se guardan los timestamps en Supabase)."""
    dt = dt or ahora()
    local_mid = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return (local_mid - dt.utcoffset()).replace(tzinfo=None)


def a_hora_mx(ts_iso):
    """Convierte un timestamp UTC naive/ISO de Supabase a datetime México."""
    try:
        d = datetime.fromisoformat(str(ts_iso).replace("Z", "").split("+")[0])
        return d.replace(tzinfo=timezone.utc).astimezone(TZ)
    except Exception:
        return None
