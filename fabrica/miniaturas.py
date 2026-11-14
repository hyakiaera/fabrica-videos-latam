"""Miniatura llamativa: la mejor imagen del video, texto grande con borde (2 a 4 palabras
que den ganas de abrirlo) y tu cara en un círculo si el video lleva avatar."""

import subprocess
from pathlib import Path

import imageio_ffmpeg
from loguru import logger
from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

from fabrica.config import RAIZ

NEGRITA = RAIZ / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"
W, H = 1080, 1920


def _cuadro(video: Path, segundo: float, salida: Path) -> Path | None:
    try:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{segundo}",
                        "-i", str(video), "-frames:v", "1", "-q:v", "2", str(salida)], check=True)
        return salida if salida.exists() else None
    except subprocess.CalledProcessError:
        return None


def _partir(texto: str, letra, ancho_max: int, d: ImageDraw.ImageDraw) -> list[str]:
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if d.textbbox((0, 0), prueba, font=letra)[2] <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    return lineas + [actual] if actual else lineas


def crear(cfg: dict, datos: dict, imagenes: list, video: Path, salida: Path) -> Path | None:
    m = cfg.get("miniatura", {})
    if not m.get("activa", True):
        return None
    try:
        fondo_ruta = next((Path(i) for i in imagenes if i and Path(i).exists()
                           and Path(i).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")), None)
        if fondo_ruta is None or fondo_ruta.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            fondo_ruta = _cuadro(video, 2.5, salida.with_name("cuadro.jpg"))
        fondo = ImageOps.fit(Image.open(fondo_ruta).convert("RGB"), (W, H))
        fondo = ImageEnhance.Contrast(ImageEnhance.Color(fondo).enhance(1.25)).enhance(1.1)
        # Degradado oscuro abajo para que el texto resalte.
        sombra = Image.new("L", (1, H))
        for y in range(H):
            sombra.putpixel((0, y), int(max(0, (y - H * 0.42) / (H * 0.58)) ** 1.4 * 235))
        negro = Image.new("RGB", (W, H), (0, 0, 0))
        fondo = Image.composite(negro, fondo, sombra.resize((W, H)))
        d = ImageDraw.Draw(fondo)

        texto = (datos.get("titulo_miniatura") or " ".join(datos.get("titulo", "").split()[:5])).upper()
        tam = 150 if len(texto) < 18 else 120 if len(texto) < 30 else 96
        letra = ImageFont.truetype(str(NEGRITA), tam)
        lineas = _partir(texto, letra, W - 120, d)[:4]
        y = H * 0.60
        propios = datos.get("miniatura") or {}
        colores = [propios.get("color_1") or m.get("color_1", "#FFE600"),
                   propios.get("color_2") or m.get("color_2", "#FFFFFF")]
        if propios.get("marco"):  # marco de color (estilo campaña, ej. neón GTA)
            d.rectangle([0, 0, W - 1, H - 1], outline=propios["marco"], width=22)
        for k, linea in enumerate(lineas):
            d.text((W / 2, y), linea, font=letra, fill=colores[k % 2], anchor="mt",
                   stroke_width=max(6, tam // 14), stroke_fill="#000000")
            y += tam * 1.08

        cara = datos.get("avatar_clip")
        if cara and Path(cara).exists():
            foto = _cuadro(Path(cara), 1.0, salida.with_name("cara.jpg"))
            if foto:
                img = Image.open(foto).convert("RGB")
                lado = min(img.size)
                y0 = max(0, min(img.height - lado, int(img.height * 0.32 - lado / 2)))
                img = img.crop(((img.width - lado) // 2, y0, (img.width - lado) // 2 + lado, y0 + lado)).resize((380, 380))
                mascara = Image.new("L", (380, 380), 0)
                ImageDraw.Draw(mascara).ellipse([0, 0, 379, 379], fill=255)
                d.ellipse([W - 440 - 10, int(H * 0.13) - 10, W - 60 + 10, int(H * 0.13) + 390], fill="#FFE600")
                fondo.paste(img, (W - 440, int(H * 0.13)), mascara)

        marca = cfg.get("logo", {}).get("texto")
        if marca:
            chica = ImageFont.truetype(str(NEGRITA), 44)
            caja = d.textbbox((0, 0), marca, font=chica)
            d.rounded_rectangle([50, 90, 50 + caja[2] + 50, 90 + caja[3] + 34], 24, fill=(0, 0, 0))
            d.text((75, 105), marca, font=chica, fill="white")
        fondo.save(salida, quality=92)
        return salida
    except Exception as e:
        logger.warning(f"Miniatura: no se pudo hacer la llamativa ({e}); se usa un cuadro del video")
        return None
