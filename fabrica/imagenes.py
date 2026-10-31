"""Consigue una imagen por escena según el estilo:
- "ia": imagen original generada gratis (Pollinations o Cloudflare, ambos FLUX)
- "wikimedia": foto real con licencia libre (se guarda el crédito)
- "pexels": foto de stock gratis (Pexels o Pixabay)
Si una fuente falla se prueba la siguiente del estilo."""

import base64
import hashlib
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import requests
from loguru import logger

from fabrica import ia
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


_SIN_SERVICIO: set[str] = set()  # servicios que ya pidieron pago en esta ronda


def pollinations(cfg: dict, prompt: str, aspecto: str, carpeta: Path, nombre: str) -> Path | None:
    if "pollinations" in _SIN_SERVICIO:
        return None
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
            if r.status_code in (401, 402, 403):
                logger.warning(f"Pollinations pide pago o clave (HTTP {r.status_code}); se usan otras fuentes")
                _SIN_SERVICIO.add("pollinations")
                return None
            logger.warning(f"Pollinations HTTP {r.status_code} (intento {intento + 1})")
        except requests.RequestException as e:
            logger.warning(f"Pollinations error (intento {intento + 1}): {e}")
        time.sleep(8 * (intento + 1))
    return None


def cloudflare(prompt: str, carpeta: Path, nombre: str) -> Path | None:
    """FLUX gratis en Cloudflare Workers AI (cuota diaria gratis)."""
    cuenta, token = secreto("CLOUDFLARE_ACCOUNT_ID"), secreto("CLOUDFLARE_API_TOKEN")
    if not (cuenta and token) or "cloudflare" in _SIN_SERVICIO:
        return None
    url = f"https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    for intento in range(2):
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {token}"}, timeout=120,
                              json={"prompt": prompt[:2000], "steps": 6})
            if r.ok:
                imagen = r.json().get("result", {}).get("image")
                if imagen:
                    return _guardar(base64.b64decode(imagen), carpeta, nombre)
            if r.status_code in (401, 402, 403, 429):
                logger.warning(f"Cloudflare HTTP {r.status_code}: {r.text[:200]}")
                _SIN_SERVICIO.add("cloudflare")
                return None
            logger.warning(f"Cloudflare HTTP {r.status_code} (intento {intento + 1})")
        except requests.RequestException as e:
            logger.warning(f"Cloudflare error (intento {intento + 1}): {e}")
        time.sleep(5)
    return None


def pixabay_foto(busqueda: str, aspecto: str, carpeta: Path, nombre: str) -> Path | None:
    clave = secreto("PIXABAY_API_KEY")
    if not clave or not busqueda:
        return None
    orientacion = {"9:16": "vertical", "16:9": "horizontal"}.get(aspecto, "all")
    try:
        r = requests.get("https://pixabay.com/api/", timeout=30, params={
            "key": clave, "q": busqueda[:100], "image_type": "photo", "orientation": orientacion,
            "per_page": 10, "safesearch": "true"})
        fotos = r.json().get("hits", []) if r.ok else []
        if not fotos:
            return None
        foto = random.choice(fotos[:5])
        img = requests.get(foto["largeImageURL"], timeout=60)
        return _guardar(img.content, carpeta, nombre) if _es_imagen(img) else None
    except Exception as e:
        logger.warning(f"Pixabay fotos falló: {e}")
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
                 carpeta: Path, visual_global: str = "", tema: str = "") -> tuple[list[Path], list[str]]:
    """Devuelve las imágenes en el orden de las escenas y los créditos de fotos.
    Se piden varias a la vez para que el video tarde menos."""
    usadas_wiki: set[str] = set()
    candado = threading.Lock()
    revisar = bool(cfg.get("imagenes", {}).get("revisar", True))

    def una(indice_escena):
        i, escena = indice_escena
        nombre = f"escena-{i:02d}"
        descripcion = escena.get("imagen", "") or tema
        busqueda = escena.get("busqueda_foto", "") or tema
        for fuente in estilo.fuentes:
            if fuente == "ia":
                # El contexto global va al principio: el generador da más peso a lo primero.
                escena_completa = f"{visual_global}. Scene: {descripcion}" if visual_global else descripcion
                prompt = prompt_imagen(estilo, escena_completa)
                ruta = (pollinations(cfg, prompt, aspecto, carpeta, nombre)
                        or cloudflare(prompt, carpeta, nombre))
                if ruta and revisar and not ia.imagen_encaja(cfg, ruta, escena_completa):
                    logger.info(f"Escena {i}: la imagen no encaja con el guion, se genera otra")
                    otra = (pollinations(cfg, prompt, aspecto, carpeta, nombre + "b")
                            or cloudflare(prompt, carpeta, nombre + "b"))
                    if otra and ia.imagen_encaja(cfg, otra, escena_completa) is not False:
                        ruta = otra
                if ruta:
                    return ruta, None
            elif fuente == "wikimedia":
                hallado = wikimedia(busqueda, carpeta, nombre)
                if hallado:
                    huella = hashlib.md5(hallado[0].read_bytes()).hexdigest()
                    with candado:
                        repetida = huella in usadas_wiki
                        usadas_wiki.add(huella)
                    if not repetida:
                        return hallado
            elif fuente == "pexels":
                ruta = (pexels_foto(busqueda, aspecto, carpeta, nombre)
                        or pixabay_foto(busqueda, aspecto, carpeta, nombre))
                if ruta:
                    return ruta, None
        logger.warning(f"Sin imagen para la escena {i}; se reutilizará otra")
        return None, None

    simultaneas = int(cfg.get("imagenes", {}).get("simultaneas", 3))
    with ThreadPoolExecutor(max_workers=max(1, simultaneas)) as grupo:
        resultados = list(grupo.map(una, enumerate(escenas)))
    imagenes = [ruta for ruta, _ in resultados if ruta]
    creditos = [credito for _, credito in resultados if credito]
    return imagenes, creditos
