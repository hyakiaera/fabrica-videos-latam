"""Arma el video con el motor de MoneyPrinterTurbo y le pone el logo."""

import shutil
import subprocess
import uuid
from pathlib import Path

import imageio_ffmpeg
from loguru import logger

from fabrica import voz
from fabrica.estilos import Estilo

ANCHOS = {"9:16": 1080, "16:9": 1920, "1:1": 1080}


def armar(cfg: dict, datos: dict, estilo: Estilo, imagenes: list[Path], trabajo: Path) -> Path:
    # Se importa aquí porque cargar MoneyPrinterTurbo es lento y lee su config.toml.
    from app.config import config as mpt_config
    from app.models.schema import MaterialInfo, VideoAspect, VideoParams
    from app.services import task as tm
    from app.utils import utils

    v = cfg.get("video", {})
    vz = cfg.get("voz", {})
    aspecto = v.get("aspecto", "9:16")
    task_id = str(uuid.uuid4())
    duracion_estimada = max(15, len(datos["guion"].split()) / 2.5)

    params = dict(
        video_subject=datos["titulo"],
        video_script=datos["guion"],
        video_aspect=VideoAspect(aspecto),
        video_language="es",
        voice_name=voz.voz_edge(cfg),
        voice_rate=float(vz.get("velocidad", 1.0)),
        bgm_type=v.get("musica", "random"),
        bgm_volume=float(v.get("volumen_musica", 0.15)),
        subtitle_enabled=True,
        subtitle_position=v.get("posicion_subtitulos", "custom"),
        custom_position=float(v.get("altura_subtitulos", 72)),
        subtitle_display_mode=estilo.subtitulo_modo,
        subtitle_animation=estilo.animacion,
        font_name=estilo.fuente_letra,
        font_size=int(v.get("tamano_letra", 70)),
        text_fore_color=estilo.color_texto,
        stroke_color=estilo.color_borde,
        stroke_width=float(v.get("grosor_borde", 2.5)),
        text_background_color=estilo.fondo_subtitulo,
        rounded_subtitle_background=bool(estilo.fondo_subtitulo),
        video_transition_mode=v.get("transicion") or None,
        n_threads=int(v.get("hilos", 2)),
    )
    if "stock_video" in estilo.fuentes:
        from fabrica.config import secreto
        claves = {"pexels": secreto("PEXELS_API_KEY"), "pixabay": secreto("PIXABAY_API_KEY")}
        for fuente, clave in claves.items():
            if clave and not mpt_config.app.get(f"{fuente}_api_keys"):
                mpt_config.app[f"{fuente}_api_keys"] = [clave]
        fuente = v.get("fuente_stock", "pexels")
        if not claves.get(fuente):
            fuente = "pixabay" if claves["pixabay"] else "pexels"
        params.update(
            video_source=fuente,
            video_terms=[e.get("busqueda_foto", "") for e in datos["escenas"] if e.get("busqueda_foto")],
            video_clip_duration=int(v.get("duracion_clip_stock", 4)),
        )
    else:
        if not imagenes:
            raise RuntimeError("No se consiguió ninguna imagen para el video")
        # MoneyPrinterTurbo solo acepta materiales locales dentro de storage/local_videos.
        permitidas = Path(utils.storage_dir("local_videos", create=True)) / "fabrica" / task_id
        permitidas.mkdir(parents=True, exist_ok=True)
        copias = [Path(shutil.copy(p, permitidas / p.name)) for p in imagenes]
        params.update(
            video_source="local",
            video_materials=[MaterialInfo(provider="local", url=str(p), duration=0) for p in copias],
            video_concat_mode="sequential",
            video_clip_duration=max(2, round(duracion_estimada / len(imagenes))),
            image_motion="zoom",
        )

    proveedor_subs_original = mpt_config.app.get("subtitle_provider", "edge")
    if voz.clonar_activo(cfg):
        audio = voz.generar_y_clonar(cfg, datos["guion"], trabajo / "voz")
        destino = Path(utils.task_dir(task_id)) / audio.name
        shutil.copy(audio, destino)
        params["custom_audio_file"] = str(destino)
        # Sin TTS no hay tiempos de palabras: Whisper saca los subtítulos del audio.
        mpt_config.app["subtitle_provider"] = "whisper"

    try:
        resultado = tm.start(task_id, VideoParams(**params))
    finally:
        mpt_config.app["subtitle_provider"] = proveedor_subs_original

    videos = (resultado or {}).get("videos") or []
    if not videos:
        raise RuntimeError(f"MoneyPrinterTurbo no produjo el video (tarea {task_id})")
    return Path(videos[0])


# Posiciones listas, en % del ancho/alto. Quedan fuera de la zona de los
# subtítulos y de los botones de TikTok/Reels/Shorts (columna derecha y abajo).
POSICIONES_LOGO = {
    "arriba_izquierda": (4, 7),
    "arriba_centro": (50, 7),
    "arriba_derecha": (96, 7),
    "centro_izquierda": (4, 45),
    "abajo_izquierda": (4, 62),
}


def ubicacion_logo(cfg: dict) -> tuple[float, float, float]:
    """Devuelve (x %, y %, ancho %). x/y marcan la esquina más cercana del logo:
    a la izquierda se ancla por su borde izquierdo, a la derecha por el derecho
    y en el centro por su centro."""
    lg = cfg.get("logo", {})
    posicion = lg.get("posicion", "arriba_izquierda")
    if posicion == "personalizada":
        x, y = float(lg.get("x", 4)), float(lg.get("y", 7))
    else:
        x, y = POSICIONES_LOGO.get(posicion, POSICIONES_LOGO["arriba_izquierda"])
    return x, y, float(lg.get("tamano", 0.16)) * 100


def _expresion_x(x: float) -> str:
    if x <= 33:
        return f"W*{x / 100:.4f}"
    if x >= 67:
        return f"W*{x / 100:.4f}-w"
    return f"W*{x / 100:.4f}-w/2"


def ruta_logo(cfg: dict) -> Path:
    logo = Path(cfg.get("logo", {}).get("archivo", "marca/logo.png"))
    if not logo.is_absolute():
        from fabrica.config import RAIZ
        logo = RAIZ / logo
    return logo


def filtro_logo(cfg: dict) -> str:
    x, y, ancho = ubicacion_logo(cfg)
    ancho_logo = int(ANCHOS.get(cfg.get("video", {}).get("aspecto", "9:16"), 1080) * ancho / 100)
    opacidad = float(cfg.get("logo", {}).get("opacidad", 0.9))
    return (f"[1:v]scale={ancho_logo}:-1,format=rgba,colorchannelmixer=aa={opacidad}[logo];"
            f"[0:v][logo]overlay={_expresion_x(x)}:H*{y / 100:.4f}")


def poner_logo(cfg: dict, video: Path, salida: Path) -> Path:
    lg = cfg.get("logo", {})
    logo = ruta_logo(cfg)
    if not lg.get("activo", True) or not logo.is_file():
        if lg.get("activo", True):
            logger.warning(f"Logo: no hay logo en '{logo}', el video sale sin logo")
        shutil.copy(video, salida)
        return salida

    comando = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video),
               "-i", str(logo), "-filter_complex", filtro_logo(cfg), "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "20", "-c:a", "copy", "-movflags", "+faststart", str(salida)]
    subprocess.run(comando, check=True)
    return salida


def miniatura(video: Path, salida: Path) -> Path | None:
    try:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", "1",
                        "-i", str(video), "-frames:v", "1", "-q:v", "3", str(salida)], check=True)
        return salida
    except subprocess.CalledProcessError:
        return None
