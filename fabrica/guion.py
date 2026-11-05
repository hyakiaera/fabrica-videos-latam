"""Escribe el guion del video a partir de un tema y sus titulares de noticias."""

import re
import unicodedata
from pathlib import Path

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
    if tema.get("obligatorio"):
        extra += ("\nOBLIGATORIO (el video DEBE decir y mostrar esto, tal cual, sin cambiar datos; si no "
                  f"cabe, acorta otras partes): {tema['obligatorio']}\n")
    if contexto:
        extra += ("\nSi el contenido del link trae una LISTA o RANKING (top 10, posiciones, precios), el video "
                  "la recorre EN ORDEN diciendo el puesto y el nombre de cada uno, una escena por elemento.\n")
    if fotos_propias:
        lista = "\n".join(f"- {nombre}: {desc}" for nombre, (_, desc) in fotos_propias.items())
        extra += ("\nFOTOS PROPIAS del usuario (logos, equipos, productos, lugares). Úsalas en todas las "
                  "escenas donde encajen, poniendo el nombre exacto en \"foto_propia\"; tienen prioridad "
                  "sobre generar imágenes. Usa TODAS las que tengan que ver con el tema (si una foto es de "
                  "algo que se menciona, la escena que lo menciona lleva esa foto). No repitas la misma "
                  f"foto seguida:\n{lista}\n")
    if tema.get("prioridad_fotos_propias"):
        extra += ("\nEl usuario pidió usar SUS FOTOS: el video debe apoyarse en ellas; cuenta la historia "
                  "alrededor de lo que se ve en sus fotos.\n")
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
 "guion": "texto narrado completo, unas {palabras} palabras, con puntuación normal (puntos al final de cada oración, comas, signos ¿? ¡!), oraciones cortas, sin emojis ni acotaciones",
 "descripcion": "2-3 frases para la descripción del video",
 "titulo_miniatura": "2 a 4 palabras MUY llamativas para la portada (ej. '¡CAYÓ EN PLENA CALLE!', 'NADIE LO VIO VENIR'), sin mentir",
 "hashtags": ["#...", "... 5 a 8 hashtags en español e inglés"],
 "tono": "una palabra: triste, reflexivo, inspirador, motivador, alegre, divertido, épico, serio, urgente o informativo",
 "tipo_contenido": "noticia, deporte, finanzas, consejo/mensaje, historia, aprendizaje, entretenimiento o anuncio",
 "direccion_visual": "en INGLÉS: iluminación, paleta de colores y atmósfera que transmiten ese tono (ej. 'melancholic blue dusk light, rain on windows, muted colors, slowly turning to warm golden hopeful light')",
 "personaje": "en INGLÉS, solo si el video gira alrededor de una persona genérica (ej. consejos): su descripción fija para que sea el mismo en todas las escenas (ej. 'a Latino man in his 30s, short black hair, trimmed beard, grey hoodie'); si no, vacío",
 "visual_global": "en INGLÉS: el tema principal y el lugar/país, descrito para un generador de imágenes (ej. 'Salvadoran pupusas, thick griddled corn cakes stuffed with cheese and beans, in El Salvador')",
 "escenas": [{{"texto": "parte del guion que se narra en esta escena",
   "imagen": "descripción visual en INGLÉS de LO QUE SE DICE en esta escena, concreta y autosuficiente (el generador no conoce el resto del guion)",
   "busqueda_foto": "2-5 palabras en inglés con el tema y el lugar exactos (ej. 'pupusas El Salvador', 'Guadalajara cathedral')",
   "foto_real": "SOLO si en esta escena es clave una marca, logo, equipo, producto, lugar famoso o persona real: su nombre exacto para buscar su foto/logo real (ej. 'Binance logo', 'Club América', 'Estadio Azteca', 'iPhone 17'). Si no, vacío",
   "busqueda_stock": "1-3 palabras en inglés MUY comunes que existan en bancos de videos (ej. 'cryptocurrency', 'hacker laptop', 'stock market', 'soccer fans'); nada de nombres propios",
   "foto_propia": "nombre exacto de una foto propia si encaja, si no vacío",
   "movimiento": "en INGLÉS, qué se mueve en la escena si se anima (ej. 'the jet flies low over the houses, smoke rising', 'fans jumping and waving flags')",
   "grafica": null}}]}}

GRÁFICAS: cuando una escena da CIFRAS que están en los titulares o el contenido (precios, %,
goles, récords, rankings), pon en "grafica" en vez de null:
 - barras: {{"tipo": "barras", "titulo": "máx 30 letras", "datos": [["Intel", -29], ["Nasdaq", -2.4]], "unidad": "%", "fuente": "medio"}}
 - una cifra grande: {{"tipo": "cifra", "titulo": "máx 30 letras", "valor": -29, "unidad": "%", "detalle": "texto corto"}}
 - una tarjeta de texto (ofertas, datos de contacto, conclusión): {{"tipo": "tarjeta", "titulo": "máx 24 letras", "lineas": ["máx 5 líneas cortas"]}}
 - un MAPA animado cuando la noticia pasa en un lugar concreto (accidente, partido, tormenta, ciudad, negocio):
   {{"tipo": "mapa", "lugar": "lugar buscable con país (ej. 'Palm Beach, Florida, Estados Unidos')", "titulo": "nombre corto", "detalle": "qué pasó ahí, máx 35 letras"}}
   Úsalo en la escena donde se dice DÓNDE ocurrió (máximo uno por video).
 Solo números reales de las fuentes (nunca inventados). Máximo una gráfica cada 3 escenas.
 En temas de finanzas, economía o deportes con datos, úsalas siempre que haya números.
Usa exactamente {escenas} escenas, en el mismo orden que el guion.

REGLAS PARA LAS IMÁGENES (muy importante, deben encajar con lo que se narra):
- Primero analiza el TONO y el TIPO de contenido; todas las imágenes deben transmitir ese tono.
- En consejos, mensajes, reflexiones o motivación: cada imagen muestra la EMOCIÓN o la situación
  de esa frase con el personaje (ej. "no te valoran" → the man sitting alone at a table while
  others ignore him; "pon límites" → the man calmly raising his hand, standing firm; "invierte en
  ti" → the man training at a gym at sunrise). Nada de objetos sueltos sin relación.
- Cada "imagen" nombra SIEMPRE el tema concreto (la comida, el lugar, el objeto exacto) con sus
  rasgos visibles. Ej.: no "food on a table" sino "Salvadoran pupusas, round thick corn cakes
  stuffed with cheese, with curtido cabbage slaw, on a clay plate".
- Si se habla de un lugar (Guadalajara, El Salvador, Bogotá...), escribe el lugar y elementos
  típicos reconocibles de ese lugar (arquitectura, paisaje, colores). Nunca otro país o ciudad.
- Si el tema es algo poco conocido, describe cómo se ve, no solo su nombre.
- No confundas cosas parecidas (pupusas no son tacos ni arepas; un estadio de béisbol no es de fútbol).
- SÍ usa marcas, logos, equipos, productos y lugares por su nombre (Binance, Club América, FC
  Barcelona, Toyota, iPhone, La Selecta...) con sus colores y rasgos, adaptados al estilo.
- Si el video recomienda o compara productos (tenis, celulares, autos...), NOMBRA modelos concretos que
  aparezcan en las fuentes y pon cada uno en "foto_real"; la gente espera ver lo que se menciona.
- Deportes: cada vez que se mencione un equipo, pon en "foto_real" "escudo <nombre completo del
  equipo>" (ej. "escudo Club América", "escudo Club Deportivo Guadalajara Chivas"); si hay
  marcadores en el contenido, dilos y muéstralos en una gráfica tipo "tarjeta" (ej. lineas:
  ["América 2 - 1 Pumas", "Chivas 0 - 0 Toluca"]).
- Personas reales famosas: en "imagen" no describas su cara (descríbelas de espaldas, de lejos o
  por su camiseta/uniforme); pon su nombre en "foto_real" para usar una foto real con licencia."""
    datos = ia.pedir_json(cfg, sistema, usuario, temperatura=0.8)
    if not datos.get("guion") or not datos.get("escenas"):
        raise ValueError("La IA devolvió un guion incompleto")
    datos["hashtags"] = [h if h.startswith("#") else f"#{h}" for h in datos.get("hashtags", [])]
    datos["guion"] = puntuar(cfg, datos["guion"])
    if fotos_propias:
        asignar_fotos_propias(datos["escenas"], fotos_propias, llenar=tema.get("prioridad_fotos_propias", False))
    return datos


def _palabras(texto: str) -> set[str]:
    texto = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return {p for p in re.findall(r"[a-z0-9]+", texto) if len(p) > 2 and not p.isdigit()}


def asignar_fotos_propias(escenas: list[dict], fotos_propias: dict, llenar: bool = False):
    """Si una escena menciona algo que tiene foto propia (por el nombre del archivo o su
    descripción) y la IA no se la puso, se la pone. Así se usan todas las fotos que encajan.
    Con llenar=True (pediste usar tus fotos), las que sobren van a las escenas que no tienen
    foto propia, en orden: primero tus fotos y solo se genera lo que falte."""
    usadas = {e.get("foto_propia") for e in escenas if e.get("foto_propia") in fotos_propias}
    for nombre, (ruta, descripcion) in fotos_propias.items():
        if nombre in usadas:
            continue
        claves = _palabras(Path(nombre).stem)
        if not claves:
            continue
        mejor, puntaje = None, 0.0
        for e in escenas:
            if e.get("foto_propia") in fotos_propias or e.get("grafica"):
                continue
            dicho = _palabras(f"{e.get('texto', '')} {e.get('foto_real', '')}")
            coincide = len(claves & dicho) / len(claves)
            if coincide > puntaje:
                mejor, puntaje = e, coincide
        if mejor is not None and puntaje >= 0.6:
            mejor["foto_propia"] = nombre
            usadas.add(nombre)
    if llenar:
        libres = [n for n in fotos_propias if n not in usadas]
        for e in escenas:
            if not libres:
                break
            if not e.get("grafica") and e.get("foto_propia") not in fotos_propias:
                e["foto_propia"] = libres.pop(0)


def puntuar(cfg: dict, guion: str) -> str:
    """Si el guion llegó sin puntos (todo seguido), se le pide a la IA que solo le ponga la
    puntuación. La voz y los subtítulos necesitan los puntos para leer bien."""
    puntos = len(re.findall(r"[.!?¿¡]", guion))
    if len(guion) < 300 or puntos >= len(guion) / 250:
        return guion
    sistema = "Corriges textos en español. Respondes SOLO JSON válido."
    usuario = ("Agrega la puntuación correcta (puntos, comas, ¿?, ¡!) y las tildes que falten a este texto, "
               "sin cambiar, quitar ni agregar palabras. Devuelve {\"texto\": \"...\"}.\n\n" + guion)
    try:
        nuevo = ia.pedir_json(cfg, sistema, usuario, temperatura=0).get("texto", "")
    except Exception:
        return guion
    # Solo se acepta si son las mismas palabras (no se reescribió el guion).
    if nuevo and abs(len(nuevo.split()) - len(guion.split())) <= max(3, len(guion.split()) // 20):
        return nuevo
    return guion
