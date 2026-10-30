# =============================================================
# DROPNODE MX — imagenes.py  (v1.0)
# Última red de seguridad: si una oferta no trae foto (o la tienda no deja usarla),
# se genera una tarjeta con el nombre, el precio y el descuento para que TODA alerta del VIP lleve imagen.
# =============================================================
import io, re, textwrap, logging

logger = logging.getLogger(__name__)
FUENTES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
           "DejaVuSans-Bold.ttf", "arialbd.ttf"]


def _fuente(tam, negrita=True):
    from PIL import ImageFont
    cand = FUENTES if negrita else FUENTES[1:2] + FUENTES[:1] + FUENTES[2:]
    for f in cand:
        try:
            return ImageFont.truetype(f, tam)
        except Exception:
            continue
    return ImageFont.load_default()


def tarjeta(nombre, precio, original, descuento, tienda=""):
    """JPEG (bytes) 900x900 con el resumen de la oferta. None si Pillow no está disponible."""
    try:
        from PIL import Image, ImageDraw
        W = H = 900
        img = Image.new("RGB", (W, H), (18, 24, 46))
        d = ImageDraw.Draw(img)
        for y in range(H):                                    # degradado vertical
            k = y / H
            d.line([(0, y), (W, y)], fill=(int(18 + 22 * k), int(24 + 40 * k), int(46 + 70 * k)))
        d.rounded_rectangle([40, 40, W - 40, H - 40], radius=36, outline=(255, 255, 255), width=3)
        d.text((80, 90), "DROPNODE MX", font=_fuente(40), fill=(120, 200, 255))
        if tienda:
            d.text((80, 145), str(tienda)[:34], font=_fuente(34, False), fill=(210, 220, 235))
        y = 240
        for linea in textwrap.wrap(re.sub(r"\s+", " ", str(nombre)), width=26)[:4]:
            d.text((80, y), linea, font=_fuente(52), fill=(255, 255, 255))
            y += 68
        d.text((80, 520), f"${float(precio):,.0f}", font=_fuente(120), fill=(255, 214, 10))
        d.text((84, 665), "MXN", font=_fuente(40, False), fill=(255, 214, 10))
        if original and float(original) > float(precio):
            d.text((84, 740), f"Antes ${float(original):,.0f}", font=_fuente(42, False), fill=(200, 205, 215))
        if descuento:
            d.ellipse([W - 330, 600, W - 100, 830], fill=(230, 40, 60))
            d.text((W - 215, 700), f"-{float(descuento) * 100:.0f}%", font=_fuente(64), fill=(255, 255, 255), anchor="mm")
            d.text((W - 215, 765), "OFF", font=_fuente(38), fill=(255, 255, 255), anchor="mm")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=88)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"[IMAGEN] tarjeta: {e}")
        return None
