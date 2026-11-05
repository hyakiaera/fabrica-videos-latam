"""Mapas animados: zoom desde lejos hasta el lugar exacto de la noticia, con un
marcador que cae y late, y el nombre del lugar. Mapas de OpenStreetMap (estilo CARTO),
gratis y sin clave."""

import math
import subprocess
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import imageio_ffmpeg
import requests
from loguru import logger
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from fabrica.config import RAIZ

FPS = 30
TESELA = 512  # teselas @2x
CABECERAS = {"User-Agent": "FabricaVideos/1.0 (generador de videos; github.com/hyakiaera/fabrica-videos-latam)"}
URL_TESELA = "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png"
NEGRITA = RAIZ / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"
NORMAL = RAIZ / "resource" / "fonts" / "BeVietnamPro-Medium.ttf"
TAMANOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}


@lru_cache(maxsize=64)
def geocodificar(lugar: str) -> tuple[float, float, str]:
    r = requests.get("https://nominatim.openstreetmap.org/search", headers=CABECERAS, timeout=30,
                     params={"q": lugar, "format": "json", "limit": 1, "accept-language": "es"})
    datos = r.json() if r.ok else []
    if not datos:
        raise ValueError(f"no encontré '{lugar}' en el mapa")
    return float(datos[0]["lat"]), float(datos[0]["lon"]), datos[0].get("display_name", lugar)


def _mundo(lat: float, lon: float, z: int) -> tuple[float, float]:
    """Posición en píxeles del punto en el mapa completo a ese zoom."""
    n = TESELA * 2 ** z
    x = (lon + 180) / 360 * n
    rad = math.radians(max(-85.0, min(85.0, lat)))
    y = (1 - math.log(math.tan(rad) + 1 / math.cos(rad)) / math.pi) / 2 * n
    return x, y


@lru_cache(maxsize=512)
def _tesela(z: int, x: int, y: int) -> Image.Image:
    n = 2 ** z
    url = URL_TESELA.format(s="abcd"[(x + y) % 4], z=z, x=x % n, y=y)
    try:
        r = requests.get(url, headers=CABECERAS, timeout=20)
        if r.ok:
            return Image.open(BytesIO(r.content)).convert("RGB")
    except requests.RequestException:
        pass
    return Image.new("RGB", (TESELA, TESELA), (225, 230, 235))


def lienzo(lat: float, lon: float, z: int, ancho: int, alto: int) -> Image.Image:
    """Mapa de ancho×alto píxeles centrado en el punto, a un zoom entero."""
    cx, cy = _mundo(lat, lon, z)
    x0, y0 = cx - ancho / 2, cy - alto / 2
    img = Image.new("RGB", (ancho, alto))
    for tx in range(int(x0 // TESELA), int((x0 + ancho) // TESELA) + 1):
        for ty in range(int(y0 // TESELA), int((y0 + alto) // TESELA) + 1):
            if 0 <= ty < 2 ** z:
                img.paste(_tesela(z, tx, ty), (int(tx * TESELA - x0), int(ty * TESELA - y0)))
    return img


def _suave(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def clip(g: dict, segundos: float, aspecto: str, salida: Path) -> Path:
    W, H = TAMANOS.get(aspecto, TAMANOS["9:16"])
    lat, lon, nombre_largo = geocodificar(g["lugar"])
    titulo = (g.get("titulo") or g["lugar"]).split(",")[0][:28]
    detalle = g.get("detalle") or ", ".join(nombre_largo.split(",")[-2:]).strip()
    z_ini, z_fin = int(g.get("zoom_inicio", 4)), int(g.get("zoom_final", 12))
    logger.info(f"Mapa: {titulo} ({lat:.4f}, {lon:.4f})")
    # Un mapa por cada zoom entero; los cuadros intermedios se agrandan entre uno y otro.
    lienzos = {z: lienzo(lat, lon, z, W, H) for z in range(z_ini, z_fin + 1)}
    letra_t = ImageFont.truetype(str(NEGRITA), 68)
    letra_d = ImageFont.truetype(str(NORMAL), 40)
    letra_c = ImageFont.truetype(str(NORMAL), 22)
    cuadros = max(1, round(segundos * FPS))
    fin_zoom = 0.7
    proceso = subprocess.Popen(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", str(salida)], stdin=subprocess.PIPE)
    for n in range(cuadros):
        t = n / max(1, cuadros - 1)
        z = z_ini + (z_fin - z_ini) * _suave(t / fin_zoom)
        zi = min(int(z), z_fin)
        escala = 2 ** (z - zi)
        base = lienzos[zi]
        rw, rh = W / escala, H / escala
        cuadro = base.crop((int((W - rw) / 2), int((H - rh) / 2), int((W + rw) / 2), int((H + rh) / 2))).resize((W, H))
        d = ImageDraw.Draw(cuadro, "RGBA")
        cx, cy = W / 2, H * 0.5
        if t > fin_zoom * 0.8:  # el marcador cae y luego late
            caida = _suave((t - fin_zoom * 0.8) / 0.12)
            py = cy - (1 - caida) * 120
            pulso = (t * segundos * 1.6) % 1
            radio = 30 + pulso * 70
            d.ellipse([cx - radio, cy - radio * 0.45, cx + radio, cy + radio * 0.45],
                      outline=(229, 57, 53, int(200 * (1 - pulso))), width=6)
            d.ellipse([cx - 30, py - 100, cx + 30, py - 40], fill=(229, 57, 53, 255))
            d.polygon([(cx - 24, py - 60), (cx + 24, py - 60), (cx, py)], fill=(229, 57, 53, 255))
            d.ellipse([cx - 11, py - 81, cx + 11, py - 59], fill=(255, 255, 255, 255))
        if t > fin_zoom * 0.9:  # tarjeta con el nombre
            aparece = _suave((t - fin_zoom * 0.9) / 0.1)
            y0 = H * 0.13 - (1 - aparece) * 40
            caja = d.textbbox((0, 0), titulo, font=letra_t)
            ancho = max(caja[2] - caja[0], d.textbbox((0, 0), detalle[:40], font=letra_d)[2]) + 100
            d.rounded_rectangle([(W - ancho) / 2, y0, (W + ancho) / 2, y0 + 190], 36,
                                fill=(15, 23, 36, int(230 * aparece)))
            d.text((W / 2, y0 + 70), titulo, font=letra_t, fill=(255, 255, 255, int(255 * aparece)), anchor="mm")
            d.text((W / 2, y0 + 140), detalle[:40], font=letra_d, fill=(250, 204, 21, int(255 * aparece)),
                   anchor="mm")
        d.text((W - 20, H - 20), "© OpenStreetMap © CARTO", font=letra_c, fill=(60, 60, 60, 200), anchor="rd")
        proceso.stdin.write(cuadro.tobytes())
    proceso.stdin.close()
    if proceso.wait() != 0:
        raise RuntimeError("ffmpeg no pudo crear el mapa")
    return salida
