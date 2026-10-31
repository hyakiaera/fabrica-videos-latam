"""Estilos visuales disponibles. Cada estilo define cómo se piden las imágenes
y cómo se ven los subtítulos. Para sumar un estilo nuevo basta con agregar
una entrada a ESTILOS."""

from dataclasses import dataclass, field

# Se agrega a todas las imágenes generadas con IA para evitar caras reales,
# marcas registradas y texto deformado dentro de la imagen.
REGLAS_IMAGEN = "no text, no letters, no logos, no watermark, no recognizable real people"


@dataclass(frozen=True)
class Estilo:
    nombre: str
    descripcion: str
    plantilla: str  # {escena} se reemplaza por la descripción de la escena
    # Orden de fuentes de imagen: "ia" (Pollinations), "wikimedia" (fotos con
    # licencia libre), "pexels" (fotos de stock), "stock_video" (videos de
    # stock con el buscador original de MoneyPrinterTurbo).
    fuentes: tuple = ("ia", "pexels")
    color_texto: str = "#FFFFFF"
    color_borde: str = "#000000"
    fondo_subtitulo: str | bool = False
    fuente_letra: str = "BeVietnamPro-Bold.ttf"
    subtitulo_modo: str = "word_by_word"
    animacion: str = "pop_spring"
    temas_ideales: list = field(default_factory=list)


ESTILOS: dict[str, Estilo] = {
    "explicativo": Estilo(
        "Explicativo animado",
        "Infografía plana tipo diagrama, ideal para temas serios (hackeos, economía).",
        "flat vector infographic illustration of {escena}, clean isometric cutaway diagram, "
        "pastel colors, soft beige background, simple shapes, editorial explainer style",
        color_texto="#1E1E1E", color_borde="#FFFFFF", fondo_subtitulo="#FFFFFF",
        temas_ideales=["tecnologia", "economia", "politica", "noticias", "ciencia"],
    ),
    "caricatura": Estilo(
        "Caricatura",
        "Dibujo animado con contornos gruesos y colores vivos.",
        "cartoon caricature illustration of {escena}, bold black outlines, vibrant flat colors, "
        "exaggerated funny expressions, playful",
        temas_ideales=["entretenimiento", "farandula", "deportes", "virales"],
    ),
    "comic": Estilo(
        "Cómic",
        "Viñeta de cómic con tramas y tinta.",
        "comic book panel of {escena}, dynamic angle, halftone dots, bold ink lines, dramatic colors",
        color_texto="#FFE600",
        temas_ideales=["deportes", "entretenimiento", "historias"],
    ),
    "artistico": Estilo(
        "Artístico (óleo)",
        "Pintura al óleo, tono dramático.",
        "oil painting of {escena}, expressive brush strokes, dramatic lighting, fine art",
        subtitulo_modo="sentence", animacion="none",
        temas_ideales=["historia", "curiosidades", "cultura"],
    ),
    "acuarela": Estilo(
        "Acuarela",
        "Ilustración suave en acuarela.",
        "soft watercolor illustration of {escena}, delicate washes, paper texture, gentle colors",
        subtitulo_modo="sentence", animacion="none",
        temas_ideales=["salud", "estilo de vida", "cultura"],
    ),
    "pizarra": Estilo(
        "Dibujo a mano / pizarra",
        "Boceto a marcador sobre fondo blanco, ideal para aprender.",
        "hand-drawn whiteboard sketch of {escena}, black marker lines on white background, "
        "simple doodle explainer, minimal color accents",
        color_texto="#111111", color_borde="#FFFFFF", fondo_subtitulo="#FFF59D",
        temas_ideales=["aprendizaje", "ciencia", "como funciona"],
    ),
    "anime": Estilo(
        "Anime",
        "Ilustración estilo anime.",
        "anime style illustration of {escena}, cel shading, vivid colors, detailed background",
        temas_ideales=["videojuegos", "entretenimiento", "tecnologia"],
    ),
    "3d": Estilo(
        "Animación 3D",
        "Render 3D suave estilo película animada.",
        "3D animated movie style render of {escena}, soft global illumination, cute stylized, "
        "high detail",
        temas_ideales=["infantil", "curiosidades", "tecnologia"],
    ),
    "cinematografico": Estilo(
        "Cinematográfico",
        "Foto generada con IA de aspecto cinematográfico.",
        "cinematic photo of {escena}, dramatic lighting, shallow depth of field, 35mm film look",
        temas_ideales=["noticias", "misterio", "deportes"],
    ),
    "noticiero": Estilo(
        "Noticiero (fotos reales con licencia libre)",
        "Fotos reales de Wikimedia Commons con crédito, o de stock.",
        "{escena}",
        fuentes=("wikimedia", "pexels", "ia"),
        fondo_subtitulo="#C62828",
        temas_ideales=["noticias", "deportes", "politica"],
    ),
    "realista": Estilo(
        "Stock realista (original de MoneyPrinterTurbo)",
        "Videos de stock de Pexels/Pixabay.",
        "{escena}",
        fuentes=("stock_video",),
        temas_ideales=["general"],
    ),
}

ESTILO_AUTOMATICO = "auto"


def obtener(nombre: str) -> Estilo:
    try:
        return ESTILOS[nombre]
    except KeyError:
        disponibles = ", ".join(ESTILOS)
        raise ValueError(f"Estilo desconocido '{nombre}'. Disponibles: {disponibles}, auto")


def prompt_imagen(estilo: Estilo, escena: str) -> str:
    return f"{estilo.plantilla.replace('{escena}', escena)}, {REGLAS_IMAGEN}"


def resumen_para_ia() -> str:
    """Lista corta que se le pasa a la IA para que elija el estilo de cada tema."""
    return "\n".join(
        f"- {clave}: {e.descripcion} Ideal para: {', '.join(e.temas_ideales)}"
        for clave, e in ESTILOS.items()
    )
