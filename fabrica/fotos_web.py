"""Fotos reales de la web para un tema:
- Noticias (Bing News RSS): la foto principal de cada nota (og:image) o su miniatura.
- Openverse: millones de fotos con licencia Creative Commons.
Se baja un "banco" de fotos por video y las escenas las van usando sin repetir."""

import re
import threading
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import requests
from loguru import logger

CABECERAS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
MINIMO_BYTES = 25_000


def _bajar(url: str, ruta: Path) -> Path | None:
    try:
        r = requests.get(url, headers=CABECERAS, timeout=30)
        if r.ok and r.headers.get("content-type", "").startswith("image/") and len(r.content) > MINIMO_BYTES:
            ruta.write_bytes(r.content)
            return ruta
    except requests.RequestException:
        pass
    return None


def _og_image(url: str) -> str:
    """Foto principal de una nota (la que sale al compartirla en redes)."""
    try:
        html = requests.get(url, headers=CABECERAS, timeout=15).text[:200_000]
    except requests.RequestException:
        return ""
    for patron in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                   r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                   r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
        m = re.search(patron, html, re.I)
        if m:
            return unescape(m.group(1))
    return ""


def noticias(consulta: str, maximo: int = 8) -> list[tuple[str, str, str]]:
    """[(url_imagen, medio, url_nota)] de las noticias más recientes del tema."""
    try:
        r = requests.get(f"https://www.bing.com/news/search?q={quote(consulta)}&format=rss&setlang=es",
                         headers=CABECERAS, timeout=30)
        xml = r.text if r.ok else ""
    except requests.RequestException:
        xml = ""
    resultados = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S)[: maximo * 2]:
        enlace = unescape((re.search(r"<link>(.*?)</link>", item, re.S) or [None, ""])[1]).strip()
        destino = parse_qs(urlparse(enlace).query).get("url", [enlace])[0]
        medio = re.search(r"<News:Source>(.*?)</News:Source>", item, re.S)
        miniatura = re.search(r"<News:Image>(.*?)</News:Image>", item, re.S)
        imagen = _og_image(destino) if destino else ""
        if not imagen and miniatura:
            imagen = unescape(miniatura.group(1)).strip() + "&w=1200&h=1200&c=7"
        if imagen:
            resultados.append((imagen, unescape(medio.group(1)) if medio else urlparse(destino).netloc, destino))
        if len(resultados) >= maximo:
            break
    return resultados


def bing_imagenes(consulta: str, maximo: int = 8, vertical: bool = True) -> list[tuple[str, str, str]]:
    """[(url_imagen, sitio, página)] de una búsqueda de imágenes: fotos reales de productos,
    marcas, lugares y personas (las mismas que salen al buscarlas en internet)."""
    filtros = "+filterui:imagesize-large" + ("+filterui:aspect-tall" if vertical else "")
    try:
        r = requests.get("https://www.bing.com/images/search", headers=CABECERAS, timeout=30,
                         params={"q": consulta, "form": "HDRSC2", "qft": filtros, "first": 1})
        html = r.text if r.ok else ""
    except requests.RequestException:
        html = ""
    resultados = []
    for bloque in re.findall(r'm="(\{[^"]*?murl[^"]*?\})"', html):
        datos = unescape(bloque)
        murl = re.search(r'"murl":"(.*?)"', datos)
        purl = re.search(r'"purl":"(.*?)"', datos)
        if murl:
            pagina = purl.group(1) if purl else ""
            resultados.append((murl.group(1), urlparse(pagina).netloc or "web", pagina))
        if len(resultados) >= maximo:
            break
    return resultados


def imagen_wikipedia(nombre: str) -> list[tuple[str, str, str]]:
    """Imagen principal del artículo de Wikipedia: el escudo de un equipo, el logo de una
    empresa o marca, la foto de un lugar o producto. Busca en español y luego en inglés."""
    resultados = []
    for idioma in ("es", "en"):
        try:
            r = requests.get(f"https://{idioma}.wikipedia.org/w/api.php", headers=CABECERAS, timeout=20, params={
                "action": "query", "format": "json", "generator": "search", "gsrsearch": nombre,
                "gsrlimit": 2, "prop": "pageimages", "piprop": "original|name"})
            paginas = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 9))
        except Exception:
            continue
        for p in paginas:
            original = p.get("original", {}).get("source")
            if original:
                resultados.append((original, f"Wikipedia ({p.get('title', '')})",
                                   f"https://{idioma}.wikipedia.org/wiki/{quote(p.get('title', ''))}"))
        if resultados:
            break
    return resultados


def noticias_texto(consulta: str, maximo: int = 3) -> list[tuple[str, str, str, str]]:
    """[(titular, medio, url, texto)] de las notas más recientes del tema, con su contenido,
    para que el guion tenga datos concretos (resultados, cifras, nombres)."""
    try:
        import trafilatura
    except ImportError:
        return []
    try:
        r = requests.get(f"https://www.bing.com/news/search?q={quote(consulta)}&format=rss&setlang=es",
                         headers=CABECERAS, timeout=30)
        xml = r.text if r.ok else ""
    except requests.RequestException:
        return []
    notas = []
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S)[: maximo * 2]:
        titulo = unescape((re.search(r"<title>(.*?)</title>", item, re.S) or [None, ""])[1]).strip()
        enlace = unescape((re.search(r"<link>(.*?)</link>", item, re.S) or [None, ""])[1]).strip()
        destino = parse_qs(urlparse(enlace).query).get("url", [enlace])[0]
        medio = re.search(r"<News:Source>(.*?)</News:Source>", item, re.S)
        try:
            html = requests.get(destino, headers=CABECERAS, timeout=20).text
            texto = trafilatura.extract(html) or ""
        except Exception:
            texto = ""
        if len(texto) > 300:
            notas.append((titulo, unescape(medio.group(1)) if medio else urlparse(destino).netloc,
                          destino, texto[:2500]))
        if len(notas) >= maximo:
            break
    return notas


def openverse(consulta: str, maximo: int = 6) -> list[tuple[str, str, str]]:
    """[(url_imagen, crédito, página)] con licencia Creative Commons."""
    try:
        r = requests.get("https://api.openverse.org/v1/images/", headers=CABECERAS, timeout=30,
                         params={"q": consulta, "page_size": maximo, "mature": "false"})
        datos = r.json().get("results", []) if r.ok else []
    except Exception:
        datos = []
    return [(d["url"], f"{d.get('creator') or 'autor'} / {d.get('source', 'Openverse')} "
                       f"({(d.get('license') or '').upper()} {d.get('license_version') or ''})".strip(),
             d.get("foreign_landing_url", "")) for d in datos if d.get("url")]


class Banco:
    """Fotos reales de un tema que se reparten entre las escenas sin repetir."""

    def __init__(self, carpeta: Path):
        self.carpeta = carpeta
        self.fotos: dict[str, list[tuple[Path, str]]] = {}
        self.usadas: set[str] = set()
        self.candado = threading.Lock()

    def cargar(self, consulta: str, con_noticias: bool = True) -> int:
        """Fotos del tema: búsqueda de imágenes (vertical y luego cualquiera), noticias y Openverse."""
        with self.candado:
            if consulta in self.fotos:
                return len(self.fotos[consulta])
            self.fotos[consulta] = []
        self.carpeta.mkdir(parents=True, exist_ok=True)
        fuentes = []
        if re.search(r"\b(logo|escudo|emblema)\b", consulta, re.I):
            # Escudos y logos: el de Wikipedia es el oficial y casi nunca falla.
            nombre = re.sub(r"\b(logo|escudo|emblema|oficial|de|del)\b", " ", consulta, flags=re.I)
            fuentes += imagen_wikipedia(" ".join(nombre.split()))
        fuentes += bing_imagenes(consulta) + bing_imagenes(consulta, vertical=False)
        fuentes += (noticias(consulta) if con_noticias else []) + openverse(consulta)
        lista = []
        for k, (url, credito, pagina) in enumerate(fuentes):
            ruta = _bajar(url, self.carpeta / f"web-{abs(hash(consulta)) % 10**6}-{k:02d}.jpg")
            if ruta:
                lista.append((ruta, f"Foto: {credito} {pagina}".strip()))
        with self.candado:
            self.fotos[consulta] = lista
        logger.info(f"Fotos web: {len(lista)} fotos para '{consulta}'")
        return len(lista)

    def mejor(self, consulta: str, descripcion: str, elegir, lote: int = 6) -> tuple[Path, str] | None:
        """La foto no usada del tema que mejor muestra 'descripcion', revisando varias de una vez.
        'elegir(rutas, descripcion)' devuelve los índices buenos o None si no se pudo revisar:
        en ese caso NO se usa ninguna (una foto de internet sin revisar puede ser cualquier cosa)."""
        self.cargar(consulta)
        with self.candado:
            libres = [(r, c) for r, c in self.fotos.get(consulta, []) if str(r) not in self.usadas][:lote]
            for r, _ in libres:
                self.usadas.add(str(r))  # se reservan para que otra escena no revise las mismas
        if not libres:
            return None
        buenos = elegir([r for r, _ in libres], descripcion)
        if not buenos:
            with self.candado:  # las que no se eligieron vuelven a estar disponibles
                for r, _ in libres:
                    self.usadas.discard(str(r))
            return None
        with self.candado:
            for k, (r, _) in enumerate(libres):
                if k != buenos[0]:
                    self.usadas.discard(str(r))
        return libres[buenos[0]]

    def tomar(self, consulta: str, aceptar=lambda ruta: True) -> tuple[Path, str] | None:
        """Siguiente foto no usada del tema que pase el filtro 'aceptar'."""
        self.cargar(consulta)
        for ruta, credito in self.fotos.get(consulta, []):
            with self.candado:
                if str(ruta) in self.usadas:
                    continue
                self.usadas.add(str(ruta))
            if aceptar(ruta):
                return ruta, credito
        return None


# ---------- Clips de video reales (Pixabay y Pexels, gratis) ----------

def clips_stock(consulta: str, maximo: int = 6) -> list[tuple[str, str, str]]:
    """[(url_video, url_miniatura, crédito)] de bancos de video gratis."""
    import os
    resultados = []
    clave = os.environ.get("PIXABAY_API_KEY", "").strip()
    if clave:
        try:
            r = requests.get("https://pixabay.com/api/videos/", timeout=30, params={
                "key": clave, "q": consulta[:100], "per_page": 10, "safesearch": "true"})
            for hit in (r.json().get("hits", []) if r.ok else [])[:maximo]:
                tam = hit.get("videos", {}).get("medium") or hit.get("videos", {}).get("small") or {}
                if tam.get("url"):
                    resultados.append((tam["url"], tam.get("thumbnail", ""), f"Video: {hit.get('user', '')} / Pixabay"))
        except Exception:
            pass
    clave = os.environ.get("PEXELS_API_KEY", "").strip()
    if clave:
        try:
            r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": clave}, timeout=30,
                             params={"query": consulta, "orientation": "portrait", "per_page": maximo})
            for v in (r.json().get("videos", []) if r.ok else []):
                archivos = sorted((f for f in v.get("video_files", []) if (f.get("width") or 0) <= 1080),
                                  key=lambda f: -(f.get("width") or 0))
                if archivos:
                    resultados.append((archivos[0]["link"], v.get("image", ""),
                                       f"Video: {v.get('user', {}).get('name', '')} / Pexels"))
        except Exception:
            pass
    return resultados
