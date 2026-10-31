"""Imagen de prueba para acomodar el logo antes de hacer videos.

Muestra dónde quedaría tu logo, dónde van los subtítulos y las zonas que
tapan los botones de TikTok/Reels/Shorts (en rojo: mejor no poner nada ahí)."""

import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from fabrica import video
from fabrica.config import RAIZ

FUENTE = RAIZ / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"
TAMANOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}


def generar(cfg: dict, salida: Path) -> Path:
    ancho, alto = TAMANOS.get(cfg.get("video", {}).get("aspecto", "9:16"), TAMANOS["9:16"])
    fondo = Image.new("RGB", (ancho, alto))
    d = ImageDraw.Draw(fondo, "RGBA")
    for fila in range(alto):  # degradado para que se note el logo
        t = fila / alto
        d.line([(0, fila), (ancho, fila)], fill=(int(40 + 80 * t), int(70 + 60 * t), int(120 - 40 * t)))

    letra = ImageFont.truetype(str(FUENTE), 34)
    rojo = (229, 57, 53, 90)
    if ancho < alto:  # zonas que tapan las apps en videos verticales
        d.rectangle([0, 0, ancho, alto * 0.05], fill=rojo)
        d.rectangle([ancho * 0.85, alto * 0.42, ancho, alto * 0.85], fill=rojo)
        d.rectangle([0, alto * 0.84, ancho, alto], fill=rojo)
        d.text((ancho * 0.03, alto * 0.88), "Zona de la descripción y usuario (la tapa la app)", font=letra, fill="white")
        d.text((ancho * 0.60, alto * 0.38), "Botones de la app →", font=letra, fill="white")

    y_sub = alto * float(cfg.get("video", {}).get("altura_subtitulos", 72)) / 100
    texto = "Así se verán los subtítulos"
    grande = ImageFont.truetype(str(FUENTE), int(cfg.get("video", {}).get("tamano_letra", 70)))
    caja = d.textbbox((0, 0), texto, font=grande)
    x0 = (ancho - (caja[2] - caja[0])) / 2
    d.rounded_rectangle([x0 - 25, y_sub - 15, x0 + caja[2] - caja[0] + 25, y_sub + caja[3] - caja[1] + 30],
                        20, fill=(255, 255, 255, 230))
    d.text((x0, y_sub), texto, font=grande, fill="#1E1E1E")

    salida.parent.mkdir(parents=True, exist_ok=True)
    temporal = salida.with_suffix(".fondo.png")
    fondo.save(temporal)
    logo = video.obtener_logo(cfg, salida.parent)
    if not logo:  # logo de ejemplo si todavía no subiste el tuyo
        logo = salida.with_suffix(".logo.png")
        ejemplo = Image.new("RGBA", (500, 200), (0, 0, 0, 0))
        de = ImageDraw.Draw(ejemplo)
        de.rounded_rectangle([0, 0, 499, 199], 40, fill=(255, 193, 7, 255))
        de.text((70, 55), "TU LOGO", font=ImageFont.truetype(str(FUENTE), 80), fill="black")
        ejemplo.save(logo)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(temporal),
                    "-i", str(logo), "-filter_complex", video.filtro_logo(cfg, logo.name == "logo-texto.png"), "-frames:v", "1",
                    "-q:v", "2", str(salida)], check=True)
    temporal.unlink()
    return salida
