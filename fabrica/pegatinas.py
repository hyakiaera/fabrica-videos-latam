"""Pegatinas propias: personajes y objetos tipo juguete 3D (barco, avión, castillo, guía...)
que aparecen sobre los mapas. Son NUESTRAS: se generan con IA la primera vez que se piden,
se les quita el fondo, llevan borde blanco y se guardan en tu Drive
(Fabrica de Videos/pegatinas). La biblioteca crece sola y no se vuelve a gastar cuota.

También puedes poner ahí tus propios PNG (con fondo transparente): el nombre del archivo es
el nombre de la pegatina (ej. "guia.png", "barco de carga.png")."""
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from loguru import logger
from PIL import Image, ImageDraw, ImageFilter

from fabrica.config import RAIZ

LOCAL = RAIZ / "storage" / "pegatinas"
ESTILO = ("cute 3D toy figurine of {x}, glossy soft clay and plastic render, rounded friendly shapes, "
          "bright colors, soft studio lighting, isolated on a plain pure white background, centered, "
          "the whole object visible with empty margin around it, no text, no letters, no shadow on the floor")
GUIA = ("a friendly Latino explorer guide character, short and chubby toy proportions, big smile, "
        "safari hat, holding a folded map")
_SINCRONIZADO = {"listo": False}


def _clave(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:50] or "pegatina"


def _drive(cfg: dict) -> str | None:
    if not shutil.which("rclone"):
        return None
    d = cfg.get("drive", {})
    return f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}/pegatinas"


def _sincronizar(cfg: dict) -> None:
    """Trae una vez por ronda las pegatinas que ya tienes en Drive."""
    if _SINCRONIZADO["listo"]:
        return
    _SINCRONIZADO["listo"] = True
    remoto = _drive(cfg)
    LOCAL.mkdir(parents=True, exist_ok=True)
    if remoto:
        try:
            subprocess.run(["rclone", "copy", remoto, str(LOCAL), "--include", "*.png"],
                           check=False, timeout=300, capture_output=True)
        except Exception:
            pass
    # Tus PNG pueden tener cualquier nombre: se guarda también con el nombre "limpio".
    for png in LOCAL.glob("*.png"):
        limpio = LOCAL / f"{_clave(png.stem)}.png"
        if limpio != png and not limpio.exists():
            shutil.copy(png, limpio)


def recortar(imagen: Path, salida: Path) -> Path | None:
    """Quita el fondo blanco (relleno desde los bordes), pone borde blanco de pegatina y sombra."""
    img = Image.open(imagen).convert("RGB")
    w, h = img.size
    marca = (255, 0, 255)
    trabajo = img.copy()
    for semilla in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1),
                    (0, h // 2), (w - 1, h // 2)]:
        if sum(trabajo.getpixel(semilla)) > 600:  # solo si ese borde es claro (fondo)
            ImageDraw.floodfill(trabajo, semilla, marca, thresh=40)
    import numpy as np
    arr = np.asarray(trabajo)
    es_fondo = (arr[:, :, 0] == 255) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 255)
    alfa = Image.fromarray(np.where(es_fondo, 0, 255).astype("uint8"), "L")
    alfa = alfa.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1))
    caja = alfa.getbbox()
    if not caja or (caja[2] - caja[0]) * (caja[3] - caja[1]) < w * h * 0.04:
        return None  # no quedó nada (la imagen no tenía fondo blanco)
    objeto = img.convert("RGBA")
    objeto.putalpha(alfa)
    objeto = objeto.crop(caja)
    m = max(8, objeto.width // 40)
    lienzo = Image.new("RGBA", (objeto.width + 4 * m, objeto.height + 4 * m), (0, 0, 0, 0))
    silueta = Image.new("L", lienzo.size, 0)
    silueta.paste(objeto.getchannel("A"), (2 * m, 2 * m))
    borde = silueta.filter(ImageFilter.MaxFilter(2 * (m // 2) + 1)).filter(ImageFilter.GaussianBlur(1))
    sombra = borde.filter(ImageFilter.GaussianBlur(m))
    lienzo.paste((0, 0, 0, 90), (m // 2, m), sombra)
    lienzo.paste((255, 255, 255, 255), (0, 0), borde)
    lienzo.alpha_composite(objeto, (2 * m, 2 * m))
    lado = 512
    escala = lado / max(lienzo.size)
    lienzo = lienzo.resize((max(1, int(lienzo.width * escala)), max(1, int(lienzo.height * escala))), Image.LANCZOS)
    lienzo.save(salida)
    return salida


def obtener(cfg: dict, nombre: str, descripcion: str = "") -> Path | None:
    """La pegatina con ese nombre (de tu Drive o recién hecha). None si no se pudo."""
    if not nombre:
        return None
    _sincronizar(cfg)
    clave = _clave(nombre)
    ruta = LOCAL / f"{clave}.png"
    if ruta.exists():
        return ruta
    from fabrica import imagenes
    que = GUIA if clave in ("guia", "guide") else (descripcion or nombre)
    prompt = ESTILO.format(x=que)
    for intento in ("", "-b"):
        cruda = imagenes.cloudflare(prompt, LOCAL / "crudas", clave + intento)
        if not cruda:
            return None  # sin cuota hoy: el mapa sale sin pegatina
        try:
            if recortar(cruda, ruta):
                logger.info(f"Pegatina nueva: {nombre}")
                remoto = _drive(cfg)
                if remoto:
                    subprocess.run(["rclone", "copyto", str(ruta), f"{remoto}/{ruta.name}"],
                                   check=False, timeout=120, capture_output=True)
                return ruta
        except Exception as e:
            logger.warning(f"Pegatina '{nombre}': no se pudo recortar ({e})")
    return None
