"""Consigue una imagen por escena según el estilo:
- "ia": imagen original generada gratis con Pollinations (FLUX)
- "wikimedia": foto real con licencia libre (se guarda el crédito)
- "pexels": foto de stock gratis
Si una fuente falla se prueba la siguiente del estilo."""

import hashlib
import random
import time
from pathlib import Path
from urllib.parse import quote

import requests
from loguru import logger

from fabrica.config import secreto
from fabrica.estilos import Estilo, prompt_imagen

CABECERAS = {"User-Agent": "FabricaVideos/1.0 (videos educativos; contacto via GitHub)"}
LICENCIAS_LIBRES = ("cc0", "public domain", "cc by", "cc-by", "pd")
TAMANOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}


def _es_imagen(r: requests.Response) -> bool:
    return r.ok and r.headers.get("content-type", "").startswith("image/") and len(r.content) > 5000


def _guardar(contenido: bytes, carpeta: Path, nombre: str, ext: str = ".jpg") -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{nombre}{ext}"
    ruta.write_bytes(contenido)
    return ruta


def pollinations(cfg: dict, prompt: str, aspecto: str, carpeta: Path, nombre: str) -> Path | None:
    im = cfg.get("imagenes", {})
    ancho, alto = TAMANOS.get(aspecto, TAMANOS["9:16"])
    params = {
        "width": ancho, "height": alto, "nologo": "true",
        "model": im.get("modelo_pollinations", "flux"),
        "seed": random.randint(1, 10**9),
    }
    cabeceras = dict(CABECERAS)
    if secreto("POLLINATIONS_TOKEN"):
        cabeceras["Authorization"] = f"Bearer {secreto('POLLINATIONS_TOKEN')}"
    base = im.get("url_pollinations", "https://image.pollinations.ai/prompt/").rstrip("/") + "/"
    for intento in range(3):
        try:
            r = requests.get(base + quote(prompt[:900]), params=params, headers=cabeceras, timeout=180)
            if _es_imagen(r):
                return _guardar(r.content, carpeta, nombre)
            logger.warning(f"Pollinations HTTP {r.status_code} (intento {intento + 1})")
        except requests.RequestException as e:
            logger.warning(f"Pollinations error (intento {intento + 1}): {e}")
        time.sleep(8 * (intento + 1))
    return None


def wikimedia(busqueda: str, carpeta: Path, nombre: str) -> tuple[Path, str] | None:
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers=CABECERAS, timeout=30, params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
            "gsrsearch": f"{busqueda} filetype:bitmap", "gsrlimit": 10,
            "prop": "imageinfo", "iiprop": "url|extmetadata|size", "iiurlwidth": 1600,
        })
        paginas = r.json().get("query", {}).get("pages", {}).values()
    except Exception as e:
        logger.warning(f"Wikimedia: búsqueda falló: {e}")
        return None
    for pagina in sorted(paginas, key=lambda p: p.get("index", 99)):
        info = (pagina.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        licencia = meta.get("LicenseShortName", {}).get("value", "")
        if not licencia.lower().startswith(LICENCIAS_LIBRES) or info.get("width", 0) < 800:
            continue
        url = info.get("thumburl") or info.get("url")
        try:
            img = requests.get(url, headers=CABECERAS, timeout=60)
        except requests.RequestException:
            continue
        if _es_imagen(img):
            autor = _sin_html(meta.get("Artist", {}).get("value", "desconocido"))
            credito = f"Foto: {autor} / Wikimedia Commons ({licencia}) {info.get('descriptionurl', '')}"
            return _guardar(img.content, carpeta, nombre), credito
    return None


def pexels_foto(busqueda: str, aspecto: str, carpeta: Path, nombre: str) -> Path | None:
    clave = secreto("PEXELS_API_KEY")
    if not clave:
        return None
    orientacion = {"9:16": "portrait", "16:9": "landscape"}.get(aspecto, "square")
    try:
        r = requests.get("https://api.pexels.com/v1/search", timeout=30, headers={"Authorization": clave},
                         params={"query": busqueda, "orientation": orientacion, "per_page": 10})
        fotos = r.json().get("photos", [])
        if not fotos:
            return None
        foto = random.choice(fotos[:5])
        img = requests.get(foto["src"]["large2x"], timeout=60)
        return _guardar(img.content, carpeta, nombre) if _es_imagen(img) else None
    except Exception as e:
        logger.warning(f"Pexels fotos falló: {e}")
        return None


def _sin_html(texto: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", texto).strip()[:120]


def para_escenas(cfg: dict, escenas: list[dict], estilo: Estilo, aspecto: str,
                 carpeta: Path) -> tuple[list[Path], list[str]]:
    """Devuelve las imágenes en el orden de las escenas y los créditos de fotos."""
    imagenes, creditos = [], []
    usadas_wiki = set()
    for i, escena in enumerate(escenas):
        nombre = f"escena-{i:02d}"
        resultado = None
        for fuente in estilo.fuentes:
            if fuente == "ia":
                resultado = pollinations(cfg, prompt_imagen(estilo, escena.get("imagen", "")),
                                         aspecto, carpeta, nombre)
            elif fuente == "wikimedia":
                hallado = wikimedia(escena.get("busqueda_foto", ""), carpeta, nombre)
                if hallado:
                    huella = hashlib.md5(hallado[0].read_bytes()).hexdigest()
                    if huella not in usadas_wiki:
                        usadas_wiki.add(huella)
                        resultado = hallado[0]
                        creditos.append(hallado[1])
            elif fuente == "pexels":
                resultado = pexels_foto(escena.get("busqueda_foto", ""), aspecto, carpeta, nombre)
            if resultado:
                break
        if resultado:
            imagenes.append(resultado)
        else:
            logger.warning(f"Sin imagen para la escena {i}; se reutilizará otra")
    return imagenes, creditos
