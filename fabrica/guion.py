"""Escribe el guion del video a partir de un tema y sus titulares de noticias."""

from fabrica import ia
from fabrica.estilos import Estilo


def escribir(cfg: dict, tema: dict, estilo: Estilo, fotos_propias: dict | None = None) -> dict:
    g = cfg.get("guion", {})
    segundos = int(g.get("duracion_segundos", 60))
    palabras = int(segundos * 2.5)  # ~2.5 palabras por segundo en español
    # Videos largos: escenas algo más largas para no pedir demasiadas imágenes.
    escenas = max(4, min(int(g.get("max_escenas", 24)), segundos // int(g.get("segundos_por_escena", 5))))
    if segundos > 75:
        extra_largo = ("\nEs un video largo: desarrolla la historia por partes (contexto, qué pasó, "
                       "por qué importa, qué viene), con mini-ganchos para que no se vayan.")
    else:
        extra_largo = ""
    fuentes = "\n".join(f"- {t} ({f})" for t, f, _ in tema.get("fuentes", [])) or "- (sin titulares)"
    contexto = tema.get("contexto", "")
    extra = ""
    if contexto:
        extra += f"\nContenido del link de referencia (úsalo como fuente; NO lo copies, cuéntalo con tus palabras):\n{contexto}\n"
    if tema.get("indicaciones"):
        extra += f"\nLo que pidió el dueño del canal (respétalo): {tema['indicaciones']}\n"
    if fotos_propias:
        lista = "\n".join(f"- {nombre}: {desc}" for nombre, (_, desc) in fotos_propias.items())
        extra += ("\nFOTOS PROPIAS del usuario (logos, equipos, productos, lugares). Úsalas en todas las "
                  "escenas donde encajen, poniendo el nombre exacto en \"foto_propia\"; tienen prioridad "
                  f"sobre generar imágenes. No repitas la misma foto seguida:\n{lista}\n")
    if tema.get("es_negocio"):
        extra += ("\nEs un ANUNCIO del negocio del usuario: tono vendedor y cercano, menciona ofertas y "
                  "datos exactamente como los dio (precios, %, dirección, teléfono, horario); no inventes "
                  "ninguno. La última escena lleva una grafica tipo \"tarjeta\" con el nombre del negocio, "
                  "la oferta y cómo llegar o contactar.\n")
    sistema = (
        "Eres guionista de videos cortos virales en español latino neutro. Escribes con gancho "
        "fuerte en los primeros 3 segundos, frases cortas, tono cercano y cierre con pregunta o "
        "llamado a seguir el canal. Si la información viene en inglés, la traduces y adaptas. "
        "REGLA DE ORO: usa solo los hechos de los titulares y del contenido dados; no inventes "
        "cifras, fechas, nombres, historias de fondo ni declaraciones. Si falta un dato, habla en "
        "general o plantéalo como pregunta. Respondes SOLO JSON válido."
    )
    usuario = f"""Tema: {tema['tema']}
Categoría: {tema.get('categoria', '')}
Titulares de referencia:
{fuentes}
{extra}
Estilo visual del video: {estilo.nombre} ({estilo.descripcion})
{g.get('instrucciones_extra', '')}{extra_largo}

Devuelve este JSON:
{{"titulo": "título para la plataforma, máx 80 caracteres, con gancho",
 "guion": "texto narrado completo, unas {palabras} palabras, sin emojis ni acotaciones",
 "descripcion": "2-3 frases para la descripción del video",
 "hashtags": ["#...", "... 5 a 8 hashtags en español e inglés"],
 "visual_global": "en INGLÉS: el tema principal y el lugar/país, descrito para un generador de imágenes (ej. 'Salvadoran pupusas, thick griddled corn cakes stuffed with cheese and beans, in El Salvador')",
 "escenas": [{{"texto": "parte del guion que se narra en esta escena",
   "imagen": "descripción visual en INGLÉS de LO QUE SE DICE en esta escena, concreta y autosuficiente (el generador no conoce el resto del guion)",
   "busqueda_foto": "2-5 palabras en inglés con el tema y el lugar exactos (ej. 'pupusas El Salvador', 'Guadalajara cathedral')",
   "foto_real": "SOLO si en esta escena es clave una marca, logo, equipo, producto, lugar famoso o persona real: su nombre exacto para buscar su foto/logo real (ej. 'Binance logo', 'Club América', 'Estadio Azteca', 'iPhone 17'). Si no, vacío",
   "busqueda_stock": "1-3 palabras en inglés MUY comunes que existan en bancos de videos (ej. 'cryptocurrency', 'hacker laptop', 'stock market', 'soccer fans'); nada de nombres propios",
   "foto_propia": "nombre exacto de una foto propia si encaja, si no vacío",
   "grafica": null}}]}}

GRÁFICAS: cuando una escena da CIFRAS que están en los titulares o el contenido (precios, %,
goles, récords, rankings), pon en "grafica" en vez de null:
 - barras: {{"tipo": "barras", "titulo": "máx 30 letras", "datos": [["Intel", -29], ["Nasdaq", -2.4]], "unidad": "%", "fuente": "medio"}}
 - una cifra grande: {{"tipo": "cifra", "titulo": "máx 30 letras", "valor": -29, "unidad": "%", "detalle": "texto corto"}}
 - una tarjeta de texto (ofertas, datos de contacto, conclusión): {{"tipo": "tarjeta", "titulo": "máx 24 letras", "lineas": ["máx 5 líneas cortas"]}}
 Solo números reales de las fuentes (nunca inventados). Máximo una gráfica cada 3 escenas.
 En temas de finanzas, economía o deportes con datos, úsalas siempre que haya números.
Usa exactamente {escenas} escenas, en el mismo orden que el guion.

REGLAS PARA LAS IMÁGENES (muy importante, deben encajar con lo que se narra):
- Cada "imagen" nombra SIEMPRE el tema concreto (la comida, el lugar, el objeto exacto) con sus
  rasgos visibles. Ej.: no "food on a table" sino "Salvadoran pupusas, round thick corn cakes
  stuffed with cheese, with curtido cabbage slaw, on a clay plate".
- Si se habla de un lugar (Guadalajara, El Salvador, Bogotá...), escribe el lugar y elementos
  típicos reconocibles de ese lugar (arquitectura, paisaje, colores). Nunca otro país o ciudad.
- Si el tema es algo poco conocido, describe cómo se ve, no solo su nombre.
- No confundas cosas parecidas (pupusas no son tacos ni arepas; un estadio de béisbol no es de fútbol).
- SÍ usa marcas, logos, equipos, productos y lugares por su nombre (Binance, Club América, FC
  Barcelona, Toyota, iPhone, La Selecta...) con sus colores y rasgos, adaptados al estilo.
- Personas reales famosas: en "imagen" no describas su cara (descríbelas de espaldas, de lejos o
  por su camiseta/uniforme); pon su nombre en "foto_real" para usar una foto real con licencia."""
    datos = ia.pedir_json(cfg, sistema, usuario, temperatura=0.8)
    if not datos.get("guion") or not datos.get("escenas"):
        raise ValueError("La IA devolvió un guion incompleto")
    datos["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in datos.get("hashtags", [])]
    return datos
