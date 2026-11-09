"""Mezcla de temas de los videos automáticos, con los porcentajes que tú elegiste.
Cada ronda escoge la categoría que más "le falta" según los últimos videos, así con el
tiempo la mezcla queda en esos porcentajes. Se cambia en fabrica.toml, sección [mezcla]."""

import random
import re
import unicodedata
from datetime import datetime, timedelta

from loguru import logger

from fabrica import ia, tendencias

# clave: (porcentaje, para qué es, búsquedas de noticias; vacío = temas que no dependen de noticias)
CATEGORIAS = {
    "general": (20, "lo que está en tendencia ahora para el público latino (el sistema de siempre)", None),
    "deportes": (17, "deportes: fútbol mexicano, fútbol salvadoreño, fútbol español, MLS, Premier League, "
                     "selecciones, Messi, Cristiano Ronaldo, farándula de futbolistas, béisbol",
                 ["Liga MX", "fútbol salvadoreño", "LaLiga", "MLS", "Premier League", "Selección Mexicana",
                  "Messi", "Cristiano Ronaldo", "futbolistas polémica", "béisbol MLB"]),
    "mundo": (9, "tendencias y noticias NO latinas (Estados Unidos, Europa, Asia) contadas para latinos",
              ["trending news United States", "world news today", "viral news"]),
    "entretenimiento": (18, "entretenimiento latino: novelas, series, lo mejor de la semana, moda, ropa, "
                            "maquillaje, temas de mujeres y de hombres, famosos latinos",
                        ["telenovelas", "series más vistas Netflix", "moda tendencias", "maquillaje tendencia",
                         "famosos latinos", "reality show"]),
    "curiosidades": (18, "curiosidades y valor: cómo hacer algo, sabías que, consejos, reflexiones, motivación, "
                         "ideas de negocio, ofertas, top 5 / top 10 (ej. máquinas para empezar un negocio), "
                         "cómo gastar mejor 500 dólares", []),
    "finanzas": (10, "cripto y bolsa: resumen del mercado del día, Wall Street, memecoins, bitcoin, ahorrar "
                     "en BTC, mejores apps para invertir, mejores exchanges",
                 ["bitcoin hoy", "Wall Street hoy", "bolsa de valores hoy", "memecoin", "criptomonedas"]),
    "musica": (8, "música y estudio: música latina y urbana, reggaetón, tendencias y top 5 de la semana, "
                  "artistas latinos, El Hyako Mayor y Hyakiaera Records, consejos de grabación, mejores "
                  "programas y VST, Suno y música con IA, todo sobre estudio musical",
               ["reggaeton estrenos", "música urbana latina", "canciones latinas más escuchadas semana",
                "El Hyako Mayor", "Hyakiaera Records", "producción musical consejos", "Suno IA música",
                "plugins VST", "artistas latinos"]),
}


def _pesos(cfg: dict) -> dict[str, float]:
    m = cfg.get("mezcla", {})
    pesos = {k: float(m.get(k, v[0])) for k, v in CATEGORIAS.items()}
    if m.get("segun_vistas", True) and m.get("segun_notas", True):
        try:  # lo que mejor nota saca sube un poco (máximo ±15 %)
            for k, factor in factores_por_nota(_historial_guardado()).items():
                if k in pesos:
                    pesos[k] *= factor
        except Exception:
            pass
    if m.get("segun_vistas", True):
        from fabrica import estadisticas
        for k, factor in estadisticas.leer().get("factores", {}).items():
            if k in pesos:
                pesos[k] *= factor  # lo que más vistas tiene en tu canal sale un poco más seguido
    return pesos


def _historial_guardado() -> list[dict]:
    import json
    from fabrica.config import RAIZ
    ruta = RAIZ / "estado" / "historial.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []


def factores_por_nota(historial: list[dict]) -> dict[str, float]:
    """Promedio de nota por categoría (últimos 60 automáticos) comparado con el general."""
    por_cat: dict[str, list[float]] = {}
    for e in historial[-60:]:
        if e.get("automatico") and isinstance(e.get("nota"), (int, float)) and e.get("mezcla"):
            por_cat.setdefault(e["mezcla"], []).append(e["nota"])
    todas = [n for v in por_cat.values() for n in v]
    if len(todas) < 6:
        return {}
    media = sum(todas) / len(todas)
    return {k: max(0.85, min(1.15, (sum(v) / len(v)) / media)) for k, v in por_cat.items() if len(v) >= 3}


def elegir_categorias(cfg: dict, historial: list[dict], cantidad: int) -> list[str]:
    """Las categorías que más faltan según los últimos 40 videos automáticos."""
    pesos = _pesos(cfg)
    total = sum(pesos.values()) or 1
    ultimos = [e.get("mezcla") for e in historial[-40:] if e.get("mezcla")]
    elegidas = []
    for _ in range(cantidad):
        cuenta = {k: ultimos.count(k) + elegidas.count(k) for k in pesos}
        n = max(1, len(ultimos) + len(elegidas))
        falta = {k: pesos[k] / total - cuenta[k] / n + random.uniform(0, 0.01) for k in pesos}
        elegidas.append(max(falta, key=falta.get))
    return elegidas


def candidatos(cfg: dict, categoria: str) -> list[tendencias.Candidato]:
    """Noticias recientes de las búsquedas de esa categoría."""
    _, _, consultas = CATEGORIAS[categoria]
    if consultas is None:
        return tendencias.recolectar(cfg)
    ingles = categoria == "mundo"
    lista = []
    for consulta in random.sample(consultas, min(5, len(consultas))):
        for titulo, medio, url in tendencias.buscar_noticias(consulta, 8, solo_ingles=ingles):
            lista.append(tendencias.Candidato(titulo=titulo, origen="news", pais="US", idioma="en" if ingles else "es",
                                              categoria=categoria, titulares=[(titulo, medio, url)]))
    return lista


def tema_sin_noticias(cfg: dict, recientes: list[str], estilo: str) -> dict:
    """Curiosidades, consejos, tops: la IA propone un tema que no se haya hecho."""
    from fabrica.estilos import ESTILO_AUTOMATICO, ESTILOS, automatico, resumen_para_ia
    sistema = "Eres productor de un canal latino de videos cortos con mucho alcance. Respondes SOLO JSON válido."
    usuario = f"""Propón UN tema para un video de: {CATEGORIAS['curiosidades'][1]}.
Debe ser útil o sorprendente, con datos verificables, para público latino.
Ya se hicieron (no repetir): {'; '.join(recientes[-60:]) or 'ninguno'}
Estilos: {resumen_para_ia()}
Devuelve {{"tema": "título corto", "consulta": "2-5 palabras para buscar información",
"estilo": "clave del estilo", "por_que": "una frase"}}"""
    d = ia.pedir_json(cfg, sistema, usuario, temperatura=0.9)
    elegido = estilo if estilo != ESTILO_AUTOMATICO else d.get("estilo", "")
    return {"tema": d.get("tema", "").strip(), "categoria": "curiosidades",
            "estilo": (elegido if estilo != ESTILO_AUTOMATICO and elegido in ESTILOS
                       else automatico(elegido)), "por_que": d.get("por_que", ""),
            "fuentes": tendencias.buscar_noticias(d.get("consulta") or d.get("tema", ""))}


# ---------- No repetir temas ----------

VACIAS = {"de", "la", "el", "los", "las", "del", "en", "y", "a", "un", "una", "por", "para", "con", "que", "su",
          "sus", "como", "mas", "lo", "al", "se", "es", "hoy", "nuevo", "nueva", "sobre", "todo", "esto"}


def _palabras(texto: str) -> set[str]:
    t = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return {p.rstrip("s") for p in re.findall(r"[a-z0-9]+", t) if len(p) > 2 and p not in VACIAS}


def parecido(a: str, b: str) -> float:
    pa, pb = _palabras(a), _palabras(b)
    if not pa or not pb:
        return 0.0
    return len(pa & pb) / min(len(pa), len(pb))


def repetido(tema: str, historial: list[dict], dias: int = 21) -> bool:
    """True si ya se hizo un video casi igual en los últimos días (ej. dos de Jarritos)."""
    limite = datetime.now() - timedelta(days=dias)
    for e in historial[-200:]:
        try:
            if datetime.fromisoformat(e.get("fecha", "2000-01-01")) < limite:
                continue
        except ValueError:
            pass
        if parecido(tema, e.get("tema", "")) >= 0.5 or parecido(tema, e.get("titulo", "")) >= 0.5:
            logger.info(f"Tema repetido, se descarta: '{tema}' ≈ '{e.get('tema')}'")
            return True
    return False


def temas_de_la_ronda(cfg: dict, cantidad: int, historial: list[dict], estilo: str) -> list[dict]:
    from fabrica import estadisticas
    rendimiento = estadisticas.actualizar(cfg, historial)
    exitos = "; ".join(f"{v['titulo']} ({v['vistas']} vistas)" for v in rendimiento.get("mejores", [])[:5])
    # Aprende también de sus propias notas: los títulos que mejor calificó salen de ejemplo.
    notas = sorted((e for e in historial[-60:] if isinstance(e.get("nota"), (int, float))),
                   key=lambda e: -e["nota"])[:4]
    if notas:
        exitos = "; ".join(x for x in [exitos, "; ".join(f"{e.get('titulo', '')} (nota {e['nota']:.0f})" for e in notas)] if x)
    recientes = [e.get("tema", "") for e in historial]
    temas = []
    for categoria in elegir_categorias(cfg, historial, cantidad):
        logger.info(f"Mezcla: esta ronda toca '{categoria}'")
        try:
            if categoria == "curiosidades":
                opciones = [tema_sin_noticias(cfg, recientes, estilo) for _ in range(2)]
            else:
                lista = candidatos(cfg, categoria) or tendencias.recolectar(cfg)
                enfoque = CATEGORIAS[categoria][1]
                if exitos:
                    enfoque += f". En este canal funcionaron muy bien: {exitos}; prefiere temas con ese gancho"
                opciones = tendencias.elegir_temas(cfg, lista, 3, recientes, estilo, enfoque=enfoque)
        except Exception as e:
            logger.warning(f"Mezcla: falló '{categoria}' ({e}); se usa el sistema general")
            opciones = tendencias.elegir_temas(cfg, tendencias.recolectar(cfg), 3, recientes, estilo)
        for t in opciones:
            if t.get("tema") and not repetido(t["tema"], historial + [{"tema": x["tema"]} for x in temas]):
                t["mezcla"] = categoria
                temas.append(t)
                recientes.append(t["tema"])
                break
    return temas
