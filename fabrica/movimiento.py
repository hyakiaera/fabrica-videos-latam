"""Convierte cada imagen en un clip con movimiento de cámara (acercar, alejar,
paneos) y arma la lista de clips del video, una por escena, con la duración
de lo que se narra en esa escena."""

import random
import subprocess
from pathlib import Path

import imageio_ffmpeg
from loguru import logger

from fabrica import graficas

TAMANOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
FPS = 30
ZOOM = 0.16  # cuánto se acerca la cámara en todo el clip

# Expresiones de zoompan: "on" es el cuadro actual y N el total de cuadros.
EFECTOS = {
    "acercar": (f"1+{ZOOM}*on/N", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    "alejar": (f"1+{ZOOM}-{ZOOM}*on/N", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    "derecha": (f"1+{ZOOM}", "(iw-iw/zoom)*on/N", "ih/2-(ih/zoom/2)"),
    "izquierda": (f"1+{ZOOM}", "(iw-iw/zoom)*(1-on/N)", "ih/2-(ih/zoom/2)"),
    "subir": (f"1+{ZOOM}", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(1-on/N)"),
    "bajar": (f"1+{ZOOM}", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/N"),
    "diagonal": (f"1+{ZOOM}*on/N", "(iw-iw/zoom)*on/N", "(ih-ih/zoom)*on/N"),
}


def _proporcion(imagen: Path) -> float:
    from PIL import Image

    with Image.open(imagen) as img:
        return img.width / img.height


def clip_de_barrido(imagen: Path, segundos: float, aspecto: str, salida: Path, a_la_derecha: bool) -> Path:
    """Foto ancha en video vertical: se muestra a pantalla completa y la cámara la recorre."""
    ancho, alto = TAMANOS.get(aspecto, TAMANOS["9:16"])
    x = f"(iw-ow)*t/{segundos:.3f}" if a_la_derecha else f"(iw-ow)*(1-t/{segundos:.3f})"
    filtro = f"scale=-2:{alto},crop={ancho}:{alto}:x='{x}':y=0,fps={FPS},format=yuv420p"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-loop", "1",
                    "-i", str(imagen), "-vf", filtro, "-t", f"{segundos:.3f}", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "20", "-an", str(salida)], check=True)
    return salida


def clip_de_imagen(imagen: Path, segundos: float, efecto: str, aspecto: str, salida: Path) -> Path:
    ancho, alto = TAMANOS.get(aspecto, TAMANOS["9:16"])
    try:
        if _proporcion(imagen) > (ancho / alto) * 1.6:
            return clip_de_barrido(imagen, segundos, aspecto, salida, efecto in ("derecha", "acercar", "subir"))
    except Exception:
        pass
    z, x, y = EFECTOS[efecto]
    cuadros = max(1, round(segundos * FPS))
    # Se agranda la imagen antes del zoompan para que el movimiento sea suave (sin temblor).
    filtro = (f"scale={ancho * 2}:{alto * 2}:force_original_aspect_ratio=increase,"
              f"crop={ancho * 2}:{alto * 2},"
              f"zoompan=z='{z.replace('N', str(cuadros))}':x='{x.replace('N', str(cuadros))}':"
              f"y='{y.replace('N', str(cuadros))}':d={cuadros}:s={ancho}x{alto}:fps={FPS},"
              f"format=yuv420p")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-loop", "1",
                    "-i", str(imagen), "-vf", filtro, "-frames:v", str(cuadros), "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "20", "-an", str(salida)], check=True)
    return salida


def duraciones(escenas: list[dict], total: float) -> list[float]:
    """Reparte la duración del audio según cuánto texto se narra en cada escena."""
    pesos = [max(1, len((e.get("texto") or "").strip())) for e in escenas]
    suma = sum(pesos)
    return [max(1.5, total * p / suma) for p in pesos]


def clips_de_escenas(cfg: dict, escenas: list[dict], imagenes: list, estilo_clave: str,
                     duracion_total: float, carpeta: Path) -> list[Path]:
    aspecto = cfg.get("video", {}).get("aspecto", "9:16")
    carpeta.mkdir(parents=True, exist_ok=True)
    clips, ultima, ultimo_efecto = [], None, None
    disponibles = [img for img in imagenes if img]
    for i, (escena, segundos) in enumerate(zip(escenas, duraciones(escenas, duracion_total))):
        salida = carpeta / f"clip-{i:02d}.mp4"
        if escena.get("grafica"):
            try:
                clips.append(graficas.clip(escena["grafica"], segundos, aspecto, estilo_clave, salida))
                continue
            except Exception as e:
                logger.warning(f"Escena {i}: no se pudo dibujar la gráfica ({e}); se usa imagen")
        imagen = imagenes[i] if i < len(imagenes) and imagenes[i] else ultima
        if imagen is None and disponibles:
            imagen = disponibles[0]
        if imagen is None:
            continue
        # Movimiento distinto al de la escena anterior, para que no se vea repetido.
        efecto = random.choice([e for e in EFECTOS if e != ultimo_efecto])
        clips.append(clip_de_imagen(imagen, segundos, efecto, aspecto, salida))
        ultima, ultimo_efecto = imagen, efecto
    if not clips:
        raise RuntimeError("No hay imágenes ni gráficas para armar el video")
    return clips
