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
from fabrica.estilos import ESTILOS, Estilo, prompt_imagen

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


def estilizar(ruta: Path, prompt: str, aspecto: str, fuerza: float = 0.55) -> Path | None:
    """Pasa una foto real al estilo del video (caricatura, 3D, cómic...) conservando lo que se
    ve en ella (Stable Diffusion img2img en Cloudflare, cuota diaria gratis)."""
    import io

    from PIL import Image

    cuenta, token = secreto("CLOUDFLARE_ACCOUNT_ID"), secreto("CLOUDFLARE_API_TOKEN")
    if not (cuenta and token) or "estilizar" in _SIN_SERVICIO:
        return None
    ancho, alto = {"9:16": (576, 1024), "16:9": (1024, 576)}.get(aspecto, (768, 768))
    try:
        img = Image.open(ruta).convert("RGB")
        escala = max(ancho / img.width, alto / img.height)
        img = img.resize((int(img.width * escala) + 1, int(img.height * escala) + 1))
        x, y = (img.width - ancho) // 2, (img.height - alto) // 2
        buf = io.BytesIO()
        img.crop((x, y, x + ancho, y + alto)).save(buf, "PNG")
        r = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/run/@cf/runwayml/stable-diffusion-v1-5-img2img",
            headers={"Authorization": f"Bearer {token}"}, timeout=120,
            json={"prompt": prompt[:1500], "image_b64": base64.b64encode(buf.getvalue()).decode(),
                  "strength": fuerza, "num_steps": 20, "guidance": 7.5})
        if r.status_code in (401, 402, 403, 429):
            _SIN_SERVICIO.add("estilizar")
            return None
        if r.ok and r.headers.get("content-type", "").startswith("image/"):
            salida = ruta.with_name(ruta.stem + "-estilo.png")
            salida.write_bytes(r.content)
            return salida
    except Exception as e:
        logger.warning(f"No se pudo pasar la foto al estilo: {e}")
    return None


def cloudflare(prompt: str, carpeta: Path, nombre: str, pasos: int = 8) -> Path | None:
    """FLUX gratis en Cloudflare Workers AI (cuota diaria gratis). 8 pasos (el máximo)
    dan caras y manos más limpias que 4 y siguen alcanzando para varios videos al día."""
    cuenta, token = secreto("CLOUDFLARE_ACCOUNT_ID"), secreto("CLOUDFLARE_API_TOKEN")
    if not (cuenta and token) or "cloudflare" in _SIN_SERVICIO:
        return None
    url = f"https://api.cloudflare.com/client/v4/accounts/{cuenta}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    for intento in range(2):
        try:
            r = requests.post(url, headers={"Authorization": f"Bearer {token}"}, timeout=120,
                              json={"prompt": prompt[:2000], "steps": max(1, min(8, int(pasos)))})
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


def wikimedia(busqueda: str, carpeta: Path, nombre: str,
              incluir_logos: bool = False) -> tuple[Path, str] | None:
    """Foto (o logo, si incluir_logos) real con licencia libre de Wikimedia Commons."""
    if not busqueda:
        return None
    tipo = "filetype:bitmap|drawing" if incluir_logos else "filetype:bitmap"
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers=CABECERAS, timeout=30, params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
            "gsrsearch": f"{busqueda} {tipo}", "gsrlimit": 10,
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
        es_dibujo = info.get("url", "").lower().endswith(".svg")
        if not licencia.lower().startswith(LICENCIAS_LIBRES):
            continue
        if not es_dibujo and info.get("width", 0) < 800:
            continue
        url = info.get("thumburl") or info.get("url")
        from fabrica import fotos_web as _fw
        if not es_dibujo and _fw.ya_usada(info.get("url", url)):
            continue  # esa foto ya salió en otro video
        try:
            img = requests.get(url, headers=CABECERAS, timeout=60)
        except requests.RequestException:
            continue
        if _es_imagen(img):
            autor = _sin_html(meta.get("Artist", {}).get("value", "desconocido"))
            credito = f"Foto: {autor} / Wikimedia Commons ({licencia}) {info.get('descriptionurl', '')}"
            if not es_dibujo:
                _fw.marcar_usada(info.get("url", url))
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


TAMANOS_PIXELES = TAMANOS


def tiene_transparencia(img) -> bool:
    """True si la imagen tiene zonas transparentes de verdad (logos), no solo canal alfa."""
    if img.mode not in ("RGBA", "LA", "P"):
        return False
    alfa = img.convert("RGBA").getchannel("A")
    return alfa.getextrema()[0] < 250


def fondo_de_producto(img) -> bool:
    """Fotos de tienda (producto sobre fondo blanco o liso): no se deben recortar,
    así que se muestran completas al centro."""
    pequena = img.convert("RGB").resize((40, 40))
    esquinas = [pequena.getpixel(p) for p in ((1, 1), (38, 1), (1, 38), (38, 38))]
    return all(min(c) > 225 for c in esquinas)


def preparar_real(ruta: Path, aspecto: str) -> Path:
    """Logos (con transparencia) se centran sobre un fondo; las fotos van tal cual:
    el movimiento de cámara las llena en vertical (con barrido si son anchas)."""
    from PIL import Image

    try:
        with Image.open(ruta) as img:
            if tiene_transparencia(img) or fondo_de_producto(img):
                return encuadrar(ruta, aspecto)
            if img.mode != "RGB":
                salida = ruta.with_name(ruta.stem + "-rgb.jpg")
                img.convert("RGB").save(salida, quality=92)
                return salida
    except Exception:
        pass
    return ruta


def encuadrar(ruta: Path, aspecto: str, rellenar: bool = False) -> Path:
    """Pone una foto o logo real dentro del formato del video sin recortarlo:
    al centro, sobre un fondo hecho con la misma imagen difuminada."""
    from PIL import Image, ImageFilter

    ancho, alto = TAMANOS_PIXELES.get(aspecto, TAMANOS_PIXELES["9:16"])
    img = Image.open(ruta)
    img.load()
    transparente = tiene_transparencia(img)
    img = img.convert("RGBA")
    if rellenar and not transparente and abs(img.width / img.height - ancho / alto) < 0.2:
        # Foto con forma parecida al video: llena toda la pantalla (se recorta un poco).
        cubre = max(ancho / img.width, alto / img.height)
        img = img.convert("RGB").resize((int(img.width * cubre) + 1, int(img.height * cubre) + 1))
        x, y = (img.width - ancho) // 2, (img.height - alto) // 2
        salida = ruta.with_name(ruta.stem + "-encuadre.jpg")
        img.crop((x, y, x + ancho, y + alto)).save(salida, quality=92)
        return salida
    if transparente or fondo_de_producto(img):  # logos y productos: fondo claro, completos
        fondo = Image.new("RGB", (ancho, alto), (245, 245, 245))
        escala = min(ancho * 0.7 / img.width, alto * 0.45 / img.height)
    else:
        cubre = max(ancho / img.width, alto / img.height)
        fondo = img.convert("RGB").resize((int(img.width * cubre) + 1, int(img.height * cubre) + 1))
        fondo = fondo.crop((0, 0, ancho, alto)).filter(ImageFilter.GaussianBlur(40))
        fondo = Image.eval(fondo, lambda v: int(v * 0.55))
        escala = min(ancho * 0.94 / img.width, alto * 0.7 / img.height)
    img = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))))
    fondo.paste(img, ((ancho - img.width) // 2, (alto - img.height) // 2), img)
    salida = ruta.with_name(ruta.stem + "-encuadre.jpg")
    fondo.save(salida, quality=92)
    return salida


def foto_de_persona(nombre: str, carpeta: Path, archivo: str) -> tuple[Path, str] | None:
    """Foto principal del artículo de Wikipedia de la persona, solo si el artículo es de ella
    (su apellido está en el título)."""
    import unicodedata
    from fabrica import fotos_web

    def limpio(t):
        return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()

    claves = [w for w in limpio(nombre).replace(",", " ").split() if len(w) > 3]
    if not claves:
        return None
    for url, credito, pagina in fotos_web.imagen_wikipedia(nombre):
        if not any(c in limpio(credito) for c in claves[-2:]):
            continue
        if url.lower().endswith((".svg", ".gif")) or fotos_web.ya_usada(url):
            continue  # la foto de su artículo ya salió en otro video: se busca otra en Commons
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta = fotos_web._bajar(url, carpeta / f"{archivo}.jpg")
        if ruta:
            fotos_web.marcar_usada(url)
            logger.info(f"Foto de {nombre}: {credito}")
            return ruta, f"{credito} — {pagina}"
    return None


def _elegir_escenas(escenas: list[dict], maximo: int, propias: dict | None = None) -> set[int]:
    """Qué escenas llevan imagen nueva. Las gráficas no necesitan imagen; si hay más
    escenas que el máximo, se reparten parejo y las demás reutilizan la anterior
    (con otro movimiento). Así no se gasta la cuota diaria gratis de imágenes."""
    propias = propias or {}
    con_foto_propia = {i for i, e in enumerate(escenas) if e.get("foto_propia") in propias}
    candidatas = [i for i, e in enumerate(escenas)
                  if not e.get("grafica") and not e.get("mapa") and i not in con_foto_propia]
    if len(candidatas) <= maximo:
        return set(candidatas) | con_foto_propia
    paso = len(candidatas) / maximo
    return {candidatas[int(k * paso)] for k in range(maximo)} | con_foto_propia


def para_escenas(cfg: dict, escenas: list[dict], estilo: Estilo, aspecto: str,
                 carpeta: Path, visual_global: str = "", tema: str = "",
                 fotos_propias: dict | None = None, direccion: str = "",
                 personaje: str = "") -> tuple[list, list[str], dict]:
    """Imagen de cada escena (None = reutilizar la anterior o es una gráfica),
    créditos de fotos y un conteo de dónde salió cada imagen.
    Se piden varias a la vez para que el video tarde menos."""
    im = cfg.get("imagenes", {})
    carpeta.mkdir(parents=True, exist_ok=True)
    usadas_wiki: set[str] = set()
    candado = threading.Lock()
    revisar = bool(im.get("revisar", True))
    conteo = {"ia": 0, "real": 0, "stock": 0, "propias": 0, "rechazadas": 0, "estilizadas": 0, "clips": 0}
    generadas: list[tuple[Path, str]] = []
    fotos_propias = fotos_propias or {}
    banco = None
    if im.get("fotos_web", True):
        from fabrica import fotos_web
        banco = fotos_web.Banco(carpeta / "web")

    def sumar(clave):
        with candado:
            conteo[clave] += 1

    def encaja(ruta, descripcion) -> bool:
        if not revisar:
            return True
        if ia.imagen_encaja(cfg, ruta, descripcion) is False:
            sumar("rechazadas")
            return False
        return True

    def elegir(rutas, descripcion):
        if not im.get("revisar", True):
            return [0]
        buenos = ia.elegir_imagenes(cfg, rutas, descripcion)
        if buenos is not None:
            with candado:
                conteo["rechazadas"] += len(rutas) - len(buenos)
        return buenos

    # Pasar fotos reales al estilo dibujado (img2img) quedó APAGADO por defecto: el modelo gratis
    # deformaba las caras (ni foto ni dibujo). Las fotos reales se muestran limpias.
    estilizable = (im.get("estilizar_fotos", False) and estilo.fuentes and estilo.fuentes[0] == "ia"
                   and "photo" not in estilo.plantilla)

    def al_estilo(ruta, descripcion):
        lista = preparar_real(ruta, aspecto)
        if not estilizable or lista != ruta:  # logos y productos encuadrados quedan tal cual
            return lista
        convertida = estilizar(ruta, prompt_imagen(estilo, descripcion), aspecto)
        if convertida:
            sumar("estilizadas")
            return convertida
        return lista

    def de_internet(consulta, descripcion):
        return banco.mejor(consulta, descripcion, elegir) if banco and consulta else None

    # Clips de video reales en los estilos fotográficos: cada tanto, una escena se mueve de verdad.
    estilos_clip = im.get("clips_estilos", ["realista", "noticiero", "cinematografico"])
    usar_clips = bool(im.get("clips", True)) and any(ESTILOS.get(k) is estilo for k in estilos_clip)
    cada_clip = max(1, int(round(1 / max(0.05, float(im.get("clips_proporcion", 0.4))))))

    def de_clip(i, escena, descripcion):
        from fabrica import fotos_web
        consulta = escena.get("busqueda_stock") or escena.get("busqueda_foto") or tema
        candidatos = fotos_web.clips_stock(consulta)[:6]
        miniaturas = []
        for k, (url, mini, _) in enumerate(candidatos):
            ruta = fotos_web._bajar(mini, carpeta / f"clip-{i:02d}-{k}.jpg") if mini else None
            miniaturas.append(ruta)
        validas = [(k, m) for k, m in enumerate(miniaturas) if m]
        if not validas:
            return None
        buenos = elegir([m for _, m in validas], descripcion)
        if not buenos:
            return None
        url, _, credito = candidatos[validas[buenos[0]][0]]
        destino = carpeta / f"clip-{i:02d}.mp4"
        try:
            r = requests.get(url, timeout=120)
            if r.ok and len(r.content) > 50_000:
                destino.write_bytes(r.content)
                sumar("clips")
                return destino, credito
        except requests.RequestException:
            pass
        return None

    def una(indice_escena):
        # Si algo falla en UNA escena, se salta esa escena (reutiliza otra imagen); nunca el video entero.
        try:
            return _una(indice_escena)
        except Exception as e:
            logger.warning(f"Escena {indice_escena[0]}: falló la imagen ({type(e).__name__}: {e}); se reutilizará otra")
            return None, None

    def _una(indice_escena):
        nonlocal revisar
        i, escena = indice_escena
        nombre = f"escena-{i:02d}"
        descripcion = escena.get("imagen", "") or tema
        busqueda = escena.get("busqueda_foto", "") or tema
        escena_completa = f"{visual_global}. Scene: {descripcion}" if visual_global else descripcion
        if personaje:
            escena_completa += f". Main character (always the same): {personaje}"
        if direccion:
            escena_completa += f". Mood and lighting: {direccion}"
        propia = escena.get("foto_propia")
        if propia in fotos_propias:
            from fabrica import mis_fotos
            sumar("propias")
            return encuadrar(mis_fotos.mejorar(fotos_propias[propia][0]), aspecto, rellenar=True), None
        real = (escena.get("foto_real") or "").strip()
        if real:
            # Primero tus archivos con ese nombre (ej. tus escudos en "mis fotos/logos equipos").
            from fabrica import mis_fotos
            try:
                tuya = mis_fotos.buscar_referencia(cfg, real, carpeta / "referencias")
            except Exception:
                tuya = None
            if tuya:
                sumar("propias")
                return preparar_real(tuya, aspecto), None
        es_persona = real and (escena.get("foto_real_tipo") or "").lower().startswith("persona")
        if es_persona and im.get("fotos_reales", True):
            # Persona famosa: la foto de SU artículo de Wikipedia (la IA revisora no reconoce caras,
            # así que una foto suelta de internet puede ser de cualquiera).
            hallado = foto_de_persona(real, carpeta, nombre + "-persona")
            if hallado:
                sumar("real")
                return preparar_real(hallado[0], aspecto), hallado[1]
        if real and im.get("fotos_reales", True):
            # Marca, equipo, producto, lugar o persona real: su foto o logo verdadero.
            hallado = wikimedia(real, carpeta, nombre + "-real", incluir_logos=True)
            # Se revisa contra la escena completa: "Tesla" el auto no es Nikola Tesla.
            if hallado and encaja(hallado[0], f"{real} — {descripcion}"):
                sumar("real")
                return al_estilo(hallado[0], escena_completa), hallado[1]
            if banco and not es_persona:
                hallado = de_internet(real, f"{real} — {descripcion}")
                if hallado:
                    sumar("real")
                    return al_estilo(hallado[0], escena_completa), hallado[1]
        if usar_clips and not real and i % cada_clip == cada_clip - 1:
            hallado = de_clip(i, escena, escena_completa)
            if hallado:
                return hallado
        ia_de_respaldo = None
        for fuente in estilo.fuentes:
            if fuente == "web" and banco:
                consulta = real or escena.get("busqueda_foto") or tema
                hallado = de_internet(consulta, f"{consulta} ({descripcion})")
                if hallado:
                    sumar("real")
                    return al_estilo(hallado[0], escena_completa), hallado[1]
            elif fuente == "ia":
                # El contexto global va al principio: el generador da más peso a lo primero.
                prompt = prompt_imagen(estilo, escena_completa)
                for intento in ("", "b"):
                    # Cloudflare primero: Pollinations gratis ahora pone su marca de agua
                    # («pollinations.ai») y queda solo de respaldo.
                    ruta = (cloudflare(prompt, carpeta, nombre + intento,
                                       cfg.get("imagenes", {}).get("pasos_flux", 8))
                            or pollinations(cfg, prompt, aspecto, carpeta, nombre + intento))
                    if not ruta:
                        break  # sin cuota o sin servicio: no insistir
                    if encaja(ruta, escena_completa):
                        sumar("ia")
                        with candado:
                            generadas.append((ruta, escena.get("texto") or descripcion))
                        return ruta, None
                    ia_de_respaldo = ruta
                    logger.info(f"Escena {i}: la imagen no encaja con el guion, se intenta otra")
                # Si la revisión rechaza casi todo, el problema es la revisión: se apaga.
                with candado:
                    if revisar and conteo["rechazadas"] >= 6 and conteo["ia"] == 0:
                        logger.warning("La revisión de imágenes rechaza demasiado; se desactiva en este video")
                        revisar = False
            elif fuente == "wikimedia":
                hallado = wikimedia(busqueda, carpeta, nombre)
                if hallado:
                    huella = hashlib.md5(hallado[0].read_bytes()).hexdigest()
                    with candado:
                        repetida = huella in usadas_wiki
                        usadas_wiki.add(huella)
                    if not repetida and encaja(hallado[0], escena_completa):
                        sumar("real")
                        return al_estilo(hallado[0], escena_completa), hallado[1]
            elif fuente == "pexels":
                ruta = (pexels_foto(busqueda, aspecto, carpeta, nombre)
                        or pixabay_foto(busqueda, aspecto, carpeta, nombre))
                # Una foto de stock que no tiene que ver es peor que repetir una buena.
                if ruta and encaja(ruta, escena_completa):
                    sumar("stock")
                    return al_estilo(ruta, escena_completa), None
        # Antes de quedarse sin nada: una foto real del tema (también revisada).
        if banco and "web" not in estilo.fuentes:
            hallado = de_internet(real or busqueda or tema, f"{real or busqueda or tema} ({descripcion})")
            if hallado:
                sumar("real")
                return al_estilo(hallado[0], escena_completa), hallado[1]
        if ia_de_respaldo and im.get("usar_rechazadas", False):
            sumar("ia")
            return ia_de_respaldo, None
        # Una imagen que la revisión dijo que NO encaja no se usa: mejor repetir una buena.
        logger.warning(f"Sin imagen para la escena {i}; se reutilizará otra")
        return None, None

    elegidas = _elegir_escenas(escenas, int(im.get("max_imagenes", 10)), fotos_propias)
    simultaneas = int(im.get("simultaneas", 3))
    with ThreadPoolExecutor(max_workers=max(1, simultaneas)) as grupo:
        resultados = dict(zip(sorted(elegidas), grupo.map(una, [(i, escenas[i]) for i in sorted(elegidas)])))
    imagenes = [resultados.get(i, (None, None))[0] for i in range(len(escenas))]
    creditos = [c for _, c in resultados.values() if c]
    if not any(imagenes) and not any(e.get("grafica") or e.get("mapa") for e in escenas):
        raise RuntimeError("No se consiguió ninguna imagen que encaje (¿se acabó la cuota diaria de "
                           "Cloudflare?). Prueba más tarde o agrega POLLINATIONS_TOKEN.")
    conteo["_generadas"] = generadas
    conteo["_sin_cuota"] = sorted(_SIN_SERVICIO)
    logger.info(f"Imágenes: {conteo['propias']} tuyas, {conteo['ia']} IA, {conteo['real']} reales, {conteo['stock']} stock, "
                f"{conteo['rechazadas']} rechazadas por no encajar")
    return imagenes, creditos, conteo
