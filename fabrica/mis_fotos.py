"""Tus propias fotos, por categoría, en Google Drive:

    Mi unidad › Fabrica de Videos › mis fotos › muebles › (fotos)
                                              › promociones › (fotos)

Cuando un pedido habla de algo que tiene carpeta (ej. "video de mi mueblería"),
la fábrica baja esas fotos, las describe con Gemini (una sola vez: guarda las
descripciones en la misma carpeta) y el guion las usa en las escenas."""

import json
import shutil
import subprocess
from pathlib import Path

from loguru import logger

from fabrica import ia
from fabrica.config import RAIZ

EXTENSIONES = (".jpg", ".jpeg", ".png", ".webp")
CACHE = "descripciones.json"


def _remoto(cfg: dict) -> str | None:
    d = cfg.get("drive", {})
    if not shutil.which("rclone"):
        return None
    return f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}/{d.get('carpeta_fotos', 'mis fotos')}"


def _local() -> Path:
    return RAIZ / "mis fotos"


def categorias(cfg: dict) -> list[str]:
    """Carpetas de fotos que tienes (en Drive o en tu PC), incluidas las de adentro:
    "Comida", "Comida/Comida salvadoreña", ..."""
    nombres = set()
    remoto = _remoto(cfg)
    if remoto:
        r = subprocess.run(["rclone", "lsf", remoto, "--dirs-only", "-R", "--max-depth", "3"],
                           capture_output=True, text=True, timeout=120)
        nombres |= {n.strip().rstrip("/") for n in r.stdout.splitlines() if n.strip()}
    if _local().is_dir():
        nombres |= {str(p.relative_to(_local())).replace("\\", "/") for p in _local().rglob("*") if p.is_dir()}
    return sorted(nombres)


def _normal(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()


def mencionadas(texto: str, cats: list[str]) -> list[str]:
    """Carpetas cuyo nombre aparece en el texto del pedido (sin importar acentos ni mayúsculas)."""
    import re
    palabras = set(re.findall(r"[a-z0-9]+", _normal(texto)))
    halladas = []
    for cat in cats:
        nombre = set(re.findall(r"[a-z0-9]+", _normal(cat.split("/")[-1])))
        if nombre and nombre <= palabras:
            halladas.append(cat)
    return quitar_repetidas(halladas)


def quitar_repetidas(cats: list[str]) -> list[str]:
    """Si se eligió una carpeta y también una de adentro, basta con la de afuera (ya la incluye)."""
    return [c for c in cats if not any(c != o and c.startswith(o + "/") for o in cats)]


def preparar(cfg: dict, cats: list[str], trabajo: Path) -> dict[str, tuple[Path, str]]:
    """Baja las fotos de esas categorías y devuelve {nombre: (ruta, descripción)}."""
    maximo = int(cfg.get("imagenes", {}).get("max_fotos_propias", 40))
    remoto = _remoto(cfg)
    fotos: dict[str, tuple[Path, str]] = {}
    for cat in cats:
        destino = trabajo / "mis-fotos" / cat
        destino.mkdir(parents=True, exist_ok=True)
        if remoto:
            subprocess.run(["rclone", "copy", f"{remoto}/{cat}", str(destino), "--max-depth", "3",
                            "--filter", "+ *.{jpg,jpeg,png,webp,JPG,JPEG,PNG,WEBP,json}", "--filter", "- *"],
                           capture_output=True, timeout=900)
        if (_local() / cat).is_dir():
            for p in (_local() / cat).rglob("*"):
                if p.is_file() and p.suffix.lower() in EXTENSIONES + (".json",):
                    copia = destino / p.relative_to(_local() / cat)
                    copia.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(p, copia)
        cache_ruta = destino / CACHE
        cache = json.loads(cache_ruta.read_text(encoding="utf-8")) if cache_ruta.exists() else {}
        imagenes = sorted((p for p in destino.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONES),
                          key=lambda p: p.stat().st_mtime, reverse=True)[:maximo]
        nuevas = 0
        for p in imagenes:
            clave = str(p.relative_to(destino)).replace("\\", "/")
            if clave not in cache:
                cache[clave] = ia.describir_imagen(cfg, p) or p.stem.replace("_", " ").replace("-", " ")
                nuevas += 1
            fotos[f"{cat}/{clave}"] = (p, cache[clave])
        if nuevas:
            cache_ruta.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
            if remoto:  # se guardan las descripciones para no volver a gastar en ellas
                subprocess.run(["rclone", "copyto", str(cache_ruta), f"{remoto}/{cat}/{CACHE}"],
                               capture_output=True, timeout=120)
        logger.info(f"Mis fotos: {len(imagenes)} fotos de '{cat}' ({nuevas} descritas nuevas)")
    return fotos


def mejorar(ruta: Path) -> Path:
    """Retoque suave para fotos de celular: contraste, color y nitidez."""
    from PIL import Image, ImageEnhance, ImageOps

    img = ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
    img = ImageOps.autocontrast(img, cutoff=1)
    img = ImageEnhance.Color(img).enhance(1.12)
    img = ImageEnhance.Sharpness(img).enhance(1.25)
    salida = ruta.with_name(ruta.stem + "-mejorada.jpg")
    img.save(salida, quality=93)
    return salida
