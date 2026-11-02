"""Tus propias fotos, por categoría, en Google Drive:

    Mi unidad › Fabrica de Videos › mis fotos › muebles › (fotos)
                                              › promociones › (fotos)

Cuando un pedido habla de algo que tiene carpeta (ej. "video de mi mueblería"),
la fábrica baja esas fotos, las describe con Gemini (una sola vez: guarda las
descripciones en la misma carpeta) y el guion las usa en las escenas."""

import json
import shutil
import subprocess
import tempfile
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


# Palabras que no ayudan a reconocer de quién es un archivo ("club-america-logo.png" → america).
GENERICAS = {"logo", "logos", "escudo", "escudos", "club", "fc", "cf", "png", "jpg", "jpeg", "svg", "webp",
             "seeklogo", "transparent", "background", "football", "futbol", "soccer", "icon", "digital",
             "download", "free", "de", "del", "la", "el", "los", "las", "deportivo", "estadio", "stadium",
             "oficial", "official", "foto", "imagen", "png_seeklogo"}
_INDICE: dict[str, list[str]] = {}


def _claves(texto: str) -> set[str]:
    import re
    palabras = re.findall(r"[a-z0-9]+", _normal(texto))
    return {p for p in palabras if p not in GENERICAS and len(p) > 2
            and not (any(c.isdigit() for c in p) and len(p) > 4)}  # quita códigos tipo "3a4adeb2"


def indice(cfg: dict) -> list[str]:
    """Todos los archivos de 'mis fotos' (solo nombres), para buscar logos y referencias."""
    if "lista" not in _INDICE:
        nombres = []
        remoto = _remoto(cfg)
        if remoto:
            r = subprocess.run(["rclone", "lsf", remoto, "-R", "--files-only", "--max-depth", "4"],
                               capture_output=True, text=True, timeout=180)
            nombres = [n.strip() for n in r.stdout.splitlines()
                       if n.strip().lower().endswith(EXTENSIONES)]
        if _local().is_dir():
            nombres += [str(p.relative_to(_local())).replace("\\", "/") for p in _local().rglob("*")
                        if p.suffix.lower() in EXTENSIONES]
        _INDICE["lista"] = nombres
    return _INDICE["lista"]


def buscar_referencia(cfg: dict, consulta: str, carpeta: Path) -> Path | None:
    """Si en 'mis fotos' hay un archivo con el nombre de lo que se busca (ej. el escudo
    'club-america.png' para "escudo Club América"), lo usa. Solo con coincidencia de nombre."""
    buscadas = _claves(consulta)
    if not buscadas:
        return None
    busca_lugar = any(x in _normal(consulta) for x in ("estadio", "stadium", "cancha"))
    for nombre in indice(cfg):
        if busca_lugar and "logo" in _normal(nombre):
            continue  # "estadio Real Madrid" no es el escudo del Real Madrid
        del_archivo = _claves(Path(nombre).stem)
        if del_archivo and (del_archivo <= buscadas or buscadas <= del_archivo):
            carpeta.mkdir(parents=True, exist_ok=True)
            destino = carpeta / Path(nombre).name
            if (_local() / nombre).is_file():
                shutil.copy(_local() / nombre, destino)
            elif _remoto(cfg):
                subprocess.run(["rclone", "copyto", f"{_remoto(cfg)}/{nombre}", str(destino)],
                               capture_output=True, timeout=300)
            if destino.exists():
                logger.info(f"Mis fotos: '{nombre}' para '{consulta}'")
                return destino
    return None


def guardar_generadas(cfg: dict, generadas: list[tuple[Path, str]], categoria: str, numero: int):
    """Guarda las imágenes hechas con IA en 'mis fotos/generadas/<categoría>' con un nombre
    que describe la escena (y su descripción en descripciones.json), para reusarlas."""
    import re
    remoto = _remoto(cfg)
    if not generadas or not remoto:
        return
    temporal = Path(tempfile.mkdtemp())
    destino = f"{remoto}/generadas/{categoria or 'general'}"
    subprocess.run(["rclone", "copyto", f"{destino}/{CACHE}", str(temporal / CACHE)], capture_output=True, timeout=120)
    cache = json.loads((temporal / CACHE).read_text(encoding="utf-8")) if (temporal / CACHE).exists() else {}
    for k, (ruta, texto) in enumerate(generadas):
        base = re.sub(r"[^a-z0-9]+", "-", _normal(texto))[:60].strip("-") or "escena"
        nombre = f"{base}-{numero:03d}-{k}.jpg"
        shutil.copy(ruta, temporal / nombre)
        cache[nombre] = texto
    (temporal / CACHE).write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    subprocess.run(["rclone", "copy", str(temporal), destino], capture_output=True, timeout=900)
    logger.info(f"Mis fotos: {len(generadas)} imágenes IA guardadas en generadas/{categoria}")
