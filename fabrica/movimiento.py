"""Convierte cada imagen en un clip con movimiento de cámara (acercar, alejar,
paneos) y arma la lista de clips del video, una por escena, con la duración
de lo que se narra en esa escena."""

import random
import subprocess
from pathlib import Path

import imageio_ffmpeg
from loguru import logger

from fabrica import graficas

TAMANOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
FPS = 30

# Ritmo según el tono del guion: cuánto se mueve la cámara y si cada escena entra
# con un "golpe" de zoom (corte dinámico) en lugar de un fundido a negro.
RITMOS = {
    "lento": {"zoom": 0.10, "golpe": 0.0},    # triste, reflexivo, emotivo
    "normal": {"zoom": 0.16, "golpe": 0.12},
    "rapido": {"zoom": 0.24, "golpe": 0.22},  # deportes, épico, alegre, urgente
}
TONOS_LENTOS = ("triste", "reflexivo", "emotivo", "nostalgico", "melancolico", "inspirador", "calmado")
TONOS_RAPIDOS = ("epico", "alegre", "energico", "urgente", "divertido", "emocionante", "intenso")
EFECTOS = ("acercar", "alejar", "derecha", "izquierda", "subir", "bajar", "diagonal")


def ritmo_de(tono: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", (tono or "").lower()).encode("ascii", "ignore").decode()
    if any(x in t for x in TONOS_LENTOS):
        return "lento"
    if any(x in t for x in TONOS_RAPIDOS):
        return "rapido"
    return "normal"


def _expresiones(efecto: str, cuadros: int, zoom: float, golpe: float) -> tuple[str, str, str]:
    """Expresiones de zoompan ("on" = cuadro actual). El golpe es un zoom extra que se
    suelta en el primer tercio de segundo, como un corte dinámico."""
    n = cuadros
    extra = f"+{golpe}*pow(max(0,1-on/{max(1, int(FPS * 0.35))}),2)" if golpe else ""
    centro_x, centro_y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    return {
        "acercar": (f"1+{zoom}*on/{n}{extra}", centro_x, centro_y),
        "alejar": (f"1+{zoom}-{zoom}*on/{n}{extra}", centro_x, centro_y),
        "derecha": (f"1+{zoom}{extra}", f"(iw-iw/zoom)*on/{n}", centro_y),
        "izquierda": (f"1+{zoom}{extra}", f"(iw-iw/zoom)*(1-on/{n})", centro_y),
        "subir": (f"1+{zoom}{extra}", centro_x, f"(ih-ih/zoom)*(1-on/{n})"),
        "bajar": (f"1+{zoom}{extra}", centro_x, f"(ih-ih/zoom)*on/{n}"),
        "diagonal": (f"1+{zoom}*on/{n}{extra}", f"(iw-iw/zoom)*on/{n}", f"(ih-ih/zoom)*on/{n}"),
    }[efecto]


def _proporcion(imagen: Path) -> float:
    from PIL import Image

    with Image.open(imagen) as img:
        return img.width / img.height


def clip_de_barrido(imagen: Path, segundos: float, aspecto: str, salida: Path, a_la_derecha: bool) -> Path:
    """Foto ancha en video vertical: se muestra a pantalla completa y la cámara la recorre."""
    ancho, alto = TAMANOS.get(aspecto, TAMANOS["9:16"])
    x = f"(iw-ow)*t/{segundos:.3f}" if a_la_derecha else f"(iw-ow)*(1-t/{segundos:.3f})"
    filtro = f"scale=-2:{alto},crop={ancho}:{alto}:x='{x}':y=0,fps={FPS},format=yuv420p"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-loop", "1",
                    "-i", str(imagen), "-vf", filtro, "-t", f"{segundos:.3f}", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "20", "-an", str(salida)], check=True)
    return salida


def clip_de_imagen(imagen: Path, segundos: float, efecto: str, aspecto: str, salida: Path,
                   ritmo: str = "normal", primera: bool = False) -> Path:
    ancho, alto = TAMANOS.get(aspecto, TAMANOS["9:16"])
    try:
        if _proporcion(imagen) > (ancho / alto) * 1.6:
            return clip_de_barrido(imagen, segundos, aspecto, salida, efecto in ("derecha", "acercar", "subir"))
    except Exception:
        pass
    cuadros = max(1, round(segundos * FPS))
    r = RITMOS.get(ritmo, RITMOS["normal"])
    # La primera escena arranca ya con la imagen (sin golpe ni fundido): nada de inicio oscuro.
    z, x, y = _expresiones(efecto, cuadros, r["zoom"], 0.0 if primera else r["golpe"])
    # Se agranda la imagen antes del zoompan para que el movimiento sea suave (sin temblor).
    filtro = (f"scale={ancho * 2}:{alto * 2}:force_original_aspect_ratio=increase,"
              f"crop={ancho * 2}:{alto * 2},"
              f"zoompan=z='{z}':x='{x}':y='{y}':d={cuadros}:s={ancho}x{alto}:fps={FPS},"
              f"format=yuv420p")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-loop", "1",
                    "-i", str(imagen), "-vf", filtro, "-frames:v", str(cuadros), "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "20", "-an", str(salida)], check=True)
    return salida


def clip_de_video(video: Path, segundos: float, aspecto: str, salida: Path) -> Path:
    """Un clip real a pantalla completa en vertical, del largo de la escena (se repite si es corto)."""
    ancho, alto = TAMANOS.get(aspecto, TAMANOS["9:16"])
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-stream_loop", "-1",
                    "-i", str(video), "-t", f"{segundos:.3f}",
                    "-vf", f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},"
                           f"fps={FPS},format=yuv420p",
                    "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(salida)],
                   check=True, timeout=300)
    return salida


def texto_en_pantalla(imagen, texto: str, aspecto: str, salida: Path) -> Path:
    """Texto grande e inclinado (gancho, pregunta, dato clave) sobre la imagen, en la
    parte de arriba para no chocar con los subtítulos. Si algo falla, queda la imagen."""
    try:
        from PIL import Image, ImageOps
        from fabrica import mapa_geo
        ancho, alto = TAMANOS.get(aspecto, TAMANOS["9:16"])
        img = ImageOps.fit(Image.open(imagen).convert("RGB"), (ancho, alto)).convert("RGBA")
        capa = Image.new("RGBA", img.size, (0, 0, 0, 0))
        texto = str(texto).strip().upper()[:28]
        tam = int(min(150, ancho * 1.5 / max(6, len(texto))))
        mapa_geo._texto(capa, (ancho / 2, alto * 0.2), texto, tam, giro=-6)
        img.alpha_composite(capa)
        img.convert("RGB").save(salida)
        return salida
    except Exception as e:
        logger.warning(f"No se pudo poner el texto en pantalla: {e}")
        return imagen


def duraciones(escenas: list[dict], total: float) -> list[float]:
    """Reparte la duración del audio según cuánto texto se narra en cada escena."""
    pesos = [max(1, len((e.get("texto") or "").strip())) for e in escenas]
    suma = sum(pesos)
    return [max(1.5, total * p / suma) for p in pesos]


def clips_de_escenas(cfg: dict, escenas: list[dict], imagenes: list, estilo_clave: str,
                     duracion_total: float, carpeta: Path, tono: str = "") -> list[Path]:
    aspecto = cfg.get("video", {}).get("aspecto", "9:16")
    ritmo = ritmo_de(tono)
    logger.info(f"Movimiento: ritmo {ritmo} (tono: {tono or 'sin indicar'})")
    carpeta.mkdir(parents=True, exist_ok=True)
    clips, ultima, ultimo_efecto = [], None, None
    disponibles = [img for img in imagenes if img]
    estado_mapa = None
    for i, (escena, segundos) in enumerate(zip(escenas, duraciones(escenas, duracion_total))):
        salida = carpeta / f"clip-{i:02d}.mp4"
        if not escena.get("mapa") and escena.get("_mapa_respaldo") and not (i < len(imagenes) and imagenes[i]):
            escena = {**escena, "mapa": escena["_mapa_respaldo"]}
        if escena.get("mapa"):
            # Mapa satelital animado: la cámara sigue desde donde quedó en la escena anterior.
            try:
                from fabrica import mapa_geo
                estado_mapa = estado_mapa or mapa_geo.Estado()
                mapa = dict(escena["mapa"])
                if escena.get("texto_pantalla") and not mapa.get("pregunta"):
                    mapa["pregunta"] = escena["texto_pantalla"]
                clips.append(mapa_geo.clip(mapa, segundos, aspecto, salida, estado_mapa))
                continue
            except Exception as e:
                logger.warning(f"Escena {i}: no se pudo dibujar el mapa ({e}); se usa imagen")
        if escena.get("grafica"):
            try:
                clips.append(graficas.clip(escena["grafica"], segundos, aspecto, estilo_clave, salida))
                continue
            except Exception as e:
                logger.warning(f"Escena {i}: no se pudo dibujar la gráfica ({e}); se usa imagen")
        imagen = imagenes[i] if i < len(imagenes) and imagenes[i] else ultima
        if imagen is None and disponibles:
            imagen = disponibles[0]
        if imagen is None:
            continue
        if Path(imagen).suffix.lower() in (".mp4", ".mov", ".webm"):
            try:  # clip de video real: se usa tal cual, recortado a la duración de la escena
                clips.append(clip_de_video(Path(imagen), segundos, aspecto, salida))
                continue
            except Exception as e:
                logger.warning(f"Escena {i}: el clip de video no sirvió ({e})")
                imagen = next((d for d in disponibles if Path(d).suffix.lower() not in (".mp4", ".mov", ".webm")), None)
                if imagen is None:
                    continue
        # Movimiento distinto al de la escena anterior, para que no se vea repetido.
        efecto = random.choice([e for e in EFECTOS if e != ultimo_efecto])
        con_texto = imagen
        if escena.get("texto_pantalla"):
            con_texto = texto_en_pantalla(imagen, escena["texto_pantalla"], aspecto,
                                          carpeta / f"texto-{i:02d}.png")
        clips.append(clip_de_imagen(con_texto, segundos, efecto, aspecto, salida, ritmo, primera=not clips))
        ultima, ultimo_efecto = imagen, efecto
    if not clips:
        raise RuntimeError("No hay imágenes ni gráficas para armar el video")
    return clips
