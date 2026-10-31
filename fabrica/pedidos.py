"""Videos a pedido: un link (YouTube, TikTok, Instagram, X o una noticia) o un
texto libre como "quiero un video que hable de...". La fábrica investiga y
escribe su PROPIO guion; no reutiliza el video ni el texto original."""

import re
from urllib.parse import urlparse

import requests
from loguru import logger

from fabrica import ia, tendencias
from fabrica.estilos import ESTILO_AUTOMATICO, ESTILOS, resumen_para_ia

REDES = ("youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch",
         "x.com", "twitter.com")
CABECERAS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FabricaVideos/1.0"}
MAX_CONTEXTO = 6000


def _es_red_social(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith("." + d) for d in REDES)


def _subtitulos(info: dict) -> str:
    """Texto de los subtítulos (manuales o automáticos) en español o inglés."""
    for fuente in ("subtitles", "automatic_captions"):
        pistas = info.get(fuente) or {}
        for idioma in ("es", "es-419", "es-US", "es-MX", "en", "en-US"):
            for formato in pistas.get(idioma, []):
                if formato.get("ext") != "vtt":
                    continue
                try:
                    vtt = requests.get(formato["url"], headers=CABECERAS, timeout=30).text
                except requests.RequestException:
                    continue
                lineas = [l for l in vtt.splitlines()
                          if l and "-->" not in l and not l.startswith(("WEBVTT", "Kind:", "Language:"))]
                texto = re.sub(r"<[^>]+>", "", " ".join(dict.fromkeys(lineas)))
                if texto.strip():
                    return texto
    return ""


def leer_video(url: str) -> dict:
    """Título, descripción y lo que se dice en el video, sin descargarlo."""
    try:
        import yt_dlp

        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        texto = "\n".join(filter(None, [info.get("description", ""), _subtitulos(info)]))
        return {"titulo": info.get("title") or "", "autor": info.get("uploader") or "",
                "texto": texto}
    except Exception as e:
        logger.warning(f"Pedido: no se pudo leer el video con yt-dlp ({type(e).__name__}); uso oEmbed")
    # Respaldo: oEmbed da al menos el título (en TikTok, el texto de la publicación).
    host = urlparse(url).netloc.lower()
    oembed = ("https://www.tiktok.com/oembed" if "tiktok" in host
              else "https://www.youtube.com/oembed" if "youtu" in host else "")
    if oembed:
        try:
            r = requests.get(oembed, params={"url": url, "format": "json"}, headers=CABECERAS, timeout=20)
            if r.ok:
                d = r.json()
                return {"titulo": d.get("title", ""), "autor": d.get("author_name", ""), "texto": ""}
        except Exception:
            pass
    return {"titulo": "", "autor": "", "texto": ""}


def leer_articulo(url: str) -> dict:
    try:
        import trafilatura

        html = trafilatura.fetch_url(url)
        texto = trafilatura.extract(html) or "" if html else ""
        meta = trafilatura.extract_metadata(html) if html else None
        return {"titulo": getattr(meta, "title", "") or "", "autor": getattr(meta, "sitename", "") or "",
                "texto": texto}
    except Exception as e:
        logger.warning(f"Pedido: no se pudo leer la noticia ({type(e).__name__})")
        return {"titulo": "", "autor": "", "texto": ""}


def preparar(cfg: dict, pedido: str, estilo: str, categoria: str = "") -> dict:
    """Convierte un link o un texto libre en un tema listo para hacer el video."""
    links = re.findall(r"https?://\S+", pedido)
    indicaciones = re.sub(r"https?://\S+", "", pedido).strip()
    fuentes, contexto = [], ""
    if links:
        url = links[0]
        datos = leer_video(url) if _es_red_social(url) else leer_articulo(url)
        contexto = datos["texto"][:MAX_CONTEXTO]
        fuentes.append((datos["titulo"] or url, datos["autor"], url))
        logger.info(f"Pedido: link leído → '{datos['titulo']}' ({len(contexto)} caracteres de contenido)")

    sistema = ("Eres productor de un canal de videos cortos para público latino. Conviertes pedidos "
               "en un tema concreto. Respondes SOLO JSON válido.")
    usuario = f"""Pedido del usuario: {indicaciones or '(sin texto, solo el link)'}
Título del link: {fuentes[0][0] if fuentes else '(sin link)'}
Contenido del link (resumen): {contexto[:1500] or '(nada)'}
Estilos: {resumen_para_ia()}

Devuelve {{"tema": "título corto en español", "consulta": "2-6 palabras para buscar noticias",
"categoria": "deportes|entretenimiento|tecnologia|economia|mundo|ciencia|general",
"estilo": "clave del estilo más adecuado"}}"""
    try:
        d = ia.pedir_json(cfg, sistema, usuario, temperatura=0.3)
    except Exception as e:
        logger.warning(f"Pedido: no se pudo interpretar con IA ({e}); uso el texto tal cual")
        d = {}
    tema = d.get("tema") or (fuentes[0][0] if fuentes else indicaciones)[:80]
    consulta = d.get("consulta") or tema
    fuentes += tendencias.buscar_noticias(consulta)
    elegido = estilo if estilo != ESTILO_AUTOMATICO else d.get("estilo", "")
    return {
        "tema": tema,
        "categoria": categoria or d.get("categoria", "general"),
        "estilo": elegido if elegido in ESTILOS else "caricatura",
        "por_que": "pedido a mano" + (f": {indicaciones}" if indicaciones else ""),
        "fuentes": fuentes[:10],
        "contexto": contexto,
        "indicaciones": indicaciones,
    }
