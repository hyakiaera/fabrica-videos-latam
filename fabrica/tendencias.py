"""Busca de qué está hablando la gente: Google Trends (lo más buscado por país)
y Google News (titulares por categoría) en español e inglés.

Todo es RSS público y gratis, sin claves. Luego la IA elige los mejores temas
dando prioridad al mercado latino."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests
from loguru import logger

from fabrica import ia
from fabrica.estilos import ESTILO_AUTOMATICO, ESTILOS, resumen_para_ia

NS_TRENDS = {"ht": "https://trends.google.com/trending/rss"}
CABECERAS = {"User-Agent": "Mozilla/5.0 (FabricaVideos/1.0)"}

SECCIONES_NEWS = {
    "deportes": "SPORTS",
    "entretenimiento": "ENTERTAINMENT",
    "tecnologia": "TECHNOLOGY",
    "economia": "BUSINESS",
    "ciencia": "SCIENCE",
    "salud": "HEALTH",
    "mundo": "WORLD",
}


@dataclass
class Candidato:
    titulo: str
    origen: str  # "trends" o "news"
    pais: str
    idioma: str
    categoria: str = ""
    trafico: str = ""
    titulares: list = field(default_factory=list)  # [(titular, fuente, url)]
    peso: float = 1.0


def _get(url: str) -> ET.Element | None:
    try:
        r = requests.get(url, headers=CABECERAS, timeout=30)
        r.raise_for_status()
        return ET.fromstring(r.content)
    except Exception as e:
        logger.warning(f"Tendencias: no se pudo leer {url}: {e}")
        return None


def google_trends(pais: str, peso: float) -> list[Candidato]:
    raiz = _get(f"https://trends.google.com/trending/rss?geo={pais}")
    if raiz is None:
        return []
    salida = []
    for item in raiz.iter("item"):
        titulares = [
            (
                n.findtext("ht:news_item_title", "", NS_TRENDS),
                n.findtext("ht:news_item_source", "", NS_TRENDS),
                n.findtext("ht:news_item_url", "", NS_TRENDS),
            )
            for n in item.findall("ht:news_item", NS_TRENDS)
        ]
        salida.append(Candidato(
            titulo=item.findtext("title", "").strip(),
            origen="trends",
            pais=pais,
            idioma="en" if pais in ("US", "GB") else "es",
            trafico=item.findtext("ht:approx_traffic", "", NS_TRENDS),
            titulares=titulares,
            peso=peso,
        ))
    return salida


def google_news(edicion: dict, categoria: str, peso: float, limite: int) -> list[Candidato]:
    hl, gl, ceid = edicion["hl"], edicion["gl"], edicion["ceid"]
    seccion = SECCIONES_NEWS.get(categoria)
    base = "https://news.google.com/rss"
    url = f"{base}/headlines/section/topic/{seccion}" if seccion else base
    raiz = _get(f"{url}?hl={hl}&gl={gl}&ceid={ceid}")
    if raiz is None:
        return []
    salida = []
    for item in list(raiz.iter("item"))[:limite]:
        titulo = item.findtext("title", "").strip()
        fuente = item.findtext("source", "")
        salida.append(Candidato(
            titulo=titulo,
            origen="news",
            pais=gl,
            idioma=hl.split("-")[0],
            categoria=categoria,
            titulares=[(titulo, fuente, item.findtext("link", ""))],
            peso=peso,
        ))
    return salida


def recolectar(cfg: dict) -> list[Candidato]:
    t = cfg.get("tendencias", {})
    candidatos: list[Candidato] = []
    for pais, peso in t.get("trends_paises", {}).items():
        candidatos += google_trends(pais, float(peso))
    for edicion in t.get("news_ediciones", []):
        for categoria in t.get("categorias", ["deportes", "entretenimiento", "tecnologia"]):
            candidatos += google_news(edicion, categoria, float(edicion.get("peso", 1.0)),
                                      int(t.get("titulares_por_categoria", 8)))
    logger.info(f"Tendencias: {len(candidatos)} candidatos recolectados")
    return candidatos


def _texto_candidatos(candidatos: list[Candidato], maximo: int) -> tuple[str, list[Candidato]]:
    ordenados = sorted(candidatos, key=lambda c: c.peso, reverse=True)[:maximo]
    lineas = []
    for i, c in enumerate(ordenados):
        extra = f" | tráfico {c.trafico}" if c.trafico else ""
        cat = f" | {c.categoria}" if c.categoria else ""
        heads = "; ".join(h[0] for h in c.titulares[:2] if h[0] and h[0] != c.titulo)
        lineas.append(f"[{i}] {c.titulo} ({c.origen} {c.pais}/{c.idioma}{cat}{extra})"
                      + (f" — {heads}" if heads else ""))
    return "\n".join(lineas), ordenados


def elegir_temas(cfg: dict, candidatos: list[Candidato], cantidad: int,
                 recientes: list[str], estilo: str = ESTILO_AUTOMATICO) -> list[dict]:
    """La IA elige los temas con más potencial y les asigna categoría y estilo."""
    t = cfg.get("tendencias", {})
    texto, ordenados = _texto_candidatos(candidatos, int(t.get("max_candidatos_ia", 90)))
    from fabrica import mis_fotos
    try:
        carpetas = mis_fotos.categorias(cfg)
    except Exception:
        carpetas = []
    sistema = (
        "Eres editor jefe de un canal de videos cortos (TikTok/Reels/Shorts) para público "
        "latinoamericano. Eliges temas con alto potencial viral, priorizando lo que interesa en "
        "Latinoamérica y a latinos en EE.UU., sin descartar noticias en inglés o de otros países "
        "si son relevantes para ese público. Evitas temas trágicos con víctimas recientes, "
        "contenido sexual y rumores sin fuente. Respondes SOLO JSON válido."
    )
    usuario = f"""Candidatos de hoy (índice entre corchetes):
{texto}

Temas ya publicados recientemente (NO repetir):
{chr(10).join('- ' + r for r in recientes[-60:]) or '- (ninguno)'}

Categorías permitidas: {', '.join(t.get('categorias', []))}
Estilos visuales disponibles:
{resumen_para_ia()}
Carpetas de fotos propias del usuario (logos, equipos, productos...): {', '.join(carpetas) or '(ninguna)'}

Elige {cantidad} temas distintos, variados en categoría. Devuelve:
{{"temas": [{{"indices": [números de candidatos que hablan de ese tema],
  "tema": "título corto en español", "categoria": "...",
  "estilo": "{estilo if estilo != ESTILO_AUTOMATICO else 'clave del estilo más adecuado'}",
  "por_que": "una frase",
  "carpetas_fotos": ["carpetas de fotos propias que sirven para ese tema; [] si ninguna"]}}]}}"""
    respuesta = ia.pedir_json(cfg, sistema, usuario, temperatura=0.5)
    temas = []
    for tema in respuesta.get("temas", [])[:cantidad]:
        fuentes = []
        for i in tema.get("indices", []):
            if isinstance(i, int) and 0 <= i < len(ordenados):
                c = ordenados[i]
                fuentes += [h for h in c.titulares if h[0]] or [(c.titulo, "", "")]
        estilo_tema = estilo if estilo != ESTILO_AUTOMATICO else tema.get("estilo", "")
        if estilo_tema not in ESTILOS:
            estilo_tema = "caricatura"
        temas.append({
            "tema": tema.get("tema", "").strip(),
            "categoria": tema.get("categoria", "general"),
            "estilo": estilo_tema,
            "por_que": tema.get("por_que", ""),
            "fuentes": fuentes[:8],
            "carpetas_fotos": [c for c in tema.get("carpetas_fotos", []) if c in carpetas],
        })
    return [t for t in temas if t["tema"]]


def buscar_noticias(consulta: str, limite: int = 6) -> list[tuple]:
    """Titulares recientes sobre un tema escrito a mano, en español y en inglés."""
    from urllib.parse import quote

    titulares = []
    for hl, gl, ceid in (("es-419", "US", "US:es-419"), ("en-US", "US", "US:en")):
        raiz = _get(f"https://news.google.com/rss/search?q={quote(consulta)}&hl={hl}&gl={gl}&ceid={ceid}")
        if raiz is None:
            continue
        for item in list(raiz.iter("item"))[: limite // 2]:
            titulares.append((item.findtext("title", ""), item.findtext("source", ""),
                              item.findtext("link", "")))
    return titulares
