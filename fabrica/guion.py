"""Escribe el guion del video a partir de un tema y sus titulares de noticias."""

from fabrica import ia
from fabrica.estilos import Estilo


def escribir(cfg: dict, tema: dict, estilo: Estilo) -> dict:
    g = cfg.get("guion", {})
    segundos = int(g.get("duracion_segundos", 60))
    palabras = int(segundos * 2.5)  # ~2.5 palabras por segundo en español
    escenas = max(4, segundos // int(g.get("segundos_por_escena", 5)))
    fuentes = "\n".join(f"- {t} ({f})" for t, f, _ in tema.get("fuentes", [])) or "- (sin titulares)"
    sistema = (
        "Eres guionista de videos cortos virales en español latino neutro. Escribes con gancho "
        "fuerte en los primeros 3 segundos, frases cortas, tono cercano y cierre con pregunta o "
        "llamado a seguir el canal. Si la información viene en inglés, la traduces y adaptas. "
        "REGLA DE ORO: usa solo los hechos de los titulares dados; no inventes cifras, fechas, "
        "nombres ni declaraciones. Si falta un dato, habla en general. Respondes SOLO JSON válido."
    )
    usuario = f"""Tema: {tema['tema']}
Categoría: {tema.get('categoria', '')}
Titulares de referencia:
{fuentes}

Estilo visual del video: {estilo.nombre} ({estilo.descripcion})
{g.get('instrucciones_extra', '')}

Devuelve este JSON:
{{"titulo": "título para la plataforma, máx 80 caracteres, con gancho",
 "guion": "texto narrado completo, unas {palabras} palabras, sin emojis ni acotaciones",
 "descripcion": "2-3 frases para la descripción del video",
 "hashtags": ["#...", "... 5 a 8 hashtags en español e inglés"],
 "escenas": [{{"texto": "parte del guion que se narra en esta escena",
   "imagen": "descripción visual en INGLÉS de la escena para generar una imagen; describe objetos, lugares y acciones genéricas, sin nombres de personas reales ni marcas",
   "busqueda_foto": "2-4 palabras en inglés para buscar una foto real con licencia libre (puede incluir equipo, estadio o lugar)"}}]}}
Usa exactamente {escenas} escenas, en el mismo orden que el guion."""
    datos = ia.pedir_json(cfg, sistema, usuario, temperatura=0.8)
    if not datos.get("guion") or not datos.get("escenas"):
        raise ValueError("La IA devolvió un guion incompleto")
    datos["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in datos.get("hashtags", [])]
    return datos
