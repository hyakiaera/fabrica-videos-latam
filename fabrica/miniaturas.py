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
    global W, H
    # YouTube: 1280x720 para videos horizontales, 1080x1920 para Shorts.
    W, H = (1280, 720) if cfg.get("video", {}).get("aspecto") == "16:9" else (1080, 1920)
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
        from fabrica.estilos import LETRA_MINIATURA, LETRA_MINIATURA_GENERAL
        archivo = NEGRITA.parent / LETRA_MINIATURA.get(datos.get("estilo_clave", ""), LETRA_MINIATURA_GENERAL)
        if archivo.name.startswith("Anton"):
            tam = int(tam * 1.15)  # Anton es angosta: cabe más grande
        horizontal = W > H
        if horizontal:  # YouTube horizontal: texto enorme a la izquierda, la imagen se ve a la derecha
            tam = int(tam * 0.95)
            capa = Image.new("L", (W, 1))
            for x in range(W):
                capa.putpixel((x, 0), int(max(0, 1 - x / (W * 0.7)) ** 1.2 * 215))
            fondo = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), fondo, capa.resize((W, H)))
            d = ImageDraw.Draw(fondo)
        letra = ImageFont.truetype(str(archivo if archivo.exists() else NEGRITA), tam)
        lineas = _partir(texto, letra, int(W * 0.6) if horizontal else W - 120, d)[:4]
        y = (H - len(lineas) * tam * 1.08) / 2 if horizontal else H * 0.60
        propios = datos.get("miniatura") or {}
        colores = [propios.get("color_1") or m.get("color_1", "#FFE600"),
                   propios.get("color_2") or m.get("color_2", "#FFFFFF")]
        if propios.get("marco"):  # marco de color (estilo campaña, ej. neón GTA)
            d.rectangle([0, 0, W - 1, H - 1], outline=propios["marco"], width=22)
        for k, linea in enumerate(lineas):
            d.text((60 if horizontal else W / 2, y), linea, font=letra, fill=colores[k % 2],
                   anchor="lt" if horizontal else "mt", stroke_width=max(6, tam // 14), stroke_fill="#000000")
            y += tam * 1.08

        cara = datos.get("avatar_clip")
        if cara and Path(cara).exists():
            foto = _cuadro(Path(cara), 1.0, salida.with_name("cara.jpg"))
            if foto:
                img = Image.open(foto).convert("RGB")
                lado = min(img.size)
                y0 = max(0, min(img.height - lado, int(img.height * 0.32 - lado / 2)))
                c = 300 if horizontal else 380
                img = img.crop(((img.width - lado) // 2, y0, (img.width - lado) // 2 + lado, y0 + lado)).resize((c, c))
                mascara = Image.new("L", (c, c), 0)
                ImageDraw.Draw(mascara).ellipse([0, 0, c - 1, c - 1], fill=255)
                cy = int(H * 0.5 - c / 2) if horizontal else int(H * 0.13)
                d.ellipse([W - c - 60 - 10, cy - 10, W - 60 + 10, cy + c + 10], fill="#FFE600")
                fondo.paste(img, (W - c - 60, cy), mascara)

        marca = cfg.get("logo", {}).get("texto")
        if marca:
            chica = ImageFont.truetype(str(NEGRITA), 30 if horizontal else 44)
            caja = d.textbbox((0, 0), marca, font=chica)
            y_m = 30 if horizontal else 90
            d.rounded_rectangle([40, y_m, 40 + caja[2] + 50, y_m + caja[3] + 34], 24, fill=(0, 0, 0))
            d.text((65, y_m + 15), marca, font=chica, fill="white")
        fondo.save(salida, quality=92)
        return salida
    except Exception as e:
        logger.warning(f"Miniatura: no se pudo hacer la llamativa ({e}); se usa un cuadro del video")
        return None
