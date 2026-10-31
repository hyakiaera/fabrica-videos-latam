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


def armar(cfg: dict, datos: dict, estilo: Estilo, imagenes: list, trabajo: Path) -> Path:
    """Arma el video. 'imagenes' trae una imagen (o None) por escena."""
    # Se importa aquí porque cargar MoneyPrinterTurbo es lento y lee su config.toml.
    from app.config import config as mpt_config
    from app.models.schema import MaterialInfo, VideoAspect, VideoParams
    from app.services import task as tm
    from app.utils import utils

    from fabrica import movimiento

    v = cfg.get("video", {})
    vz = cfg.get("voz", {})
    aspecto = v.get("aspecto", "9:16")
    task_id = str(uuid.uuid4())

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

    audio_propio = None
    if voz.clonar_activo(cfg):
        audio_propio = voz.generar_y_clonar(cfg, datos["guion"], trabajo / "voz")

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
            # Los bancos de videos no tienen marcas ni nombres propios: se buscan ideas comunes.
            video_terms=list(dict.fromkeys(
                e.get("busqueda_stock") or e.get("busqueda_foto", "") for e in datos["escenas"]
                if e.get("busqueda_stock") or e.get("busqueda_foto"))),
            video_clip_duration=int(v.get("duracion_clip_stock", 4)),
        )
    else:
        # Cada escena dura lo mismo que su parte de la narración, con movimiento de cámara.
        total = (voz.duracion_archivo(audio_propio) if audio_propio
                 else voz.duracion_audio(cfg, datos["guion"], trabajo / "voz"))
        clips = movimiento.clips_de_escenas(cfg, datos["escenas"], imagenes, estilo_clave(estilo),
                                            total + 0.6, trabajo / "clips")
        # MoneyPrinterTurbo solo acepta materiales locales dentro de storage/local_videos.
        permitidas = Path(utils.storage_dir("local_videos", create=True)) / "fabrica" / task_id
        permitidas.mkdir(parents=True, exist_ok=True)
        copias = [Path(shutil.copy(c, permitidas / c.name)) for c in clips]
        params.update(
            video_source="local",
            video_materials=[MaterialInfo(provider="local", url=str(c), duration=0) for c in copias],
            video_concat_mode="sequential",
            # Más largo que cualquier escena: así cada clip se usa completo y en orden.
            video_clip_duration=int(max(movimiento.duraciones(datos["escenas"], total))) + 2,
        )

    proveedor_subs_original = mpt_config.app.get("subtitle_provider", "edge")
    if audio_propio:
        destino = Path(utils.task_dir(task_id)) / audio_propio.name
        shutil.copy(audio_propio, destino)
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


def estilo_clave(estilo: Estilo) -> str:
    from fabrica.estilos import ESTILOS
    return next((k for k, e in ESTILOS.items() if e is estilo), "")


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


def logo_de_texto(texto: str, salida: Path) -> Path:
    """Convierte un texto (ej. "@MiCanal") en un logo PNG con fondo redondeado."""
    from PIL import Image, ImageDraw, ImageFont

    from fabrica.config import RAIZ

    letra = ImageFont.truetype(str(RAIZ / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"), 120)
    caja = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), texto, font=letra)
    ancho, alto = caja[2] - caja[0] + 120, caja[3] - caja[1] + 80
    img = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, ancho - 1, alto - 1], alto // 3, fill=(0, 0, 0, 170))
    d.text((60 - caja[0], 40 - caja[1]), texto, font=letra, fill="white")
    salida.parent.mkdir(parents=True, exist_ok=True)
    img.save(salida)
    return salida


def preparar_logo(cfg: dict):
    """Trae tu logo antes de empezar: desde un link, o desde la carpeta
    'Fabrica de Videos/marca' de tu Google Drive (si existe un .png ahí)."""
    import shutil as _sh
    import subprocess as _sp
    import tempfile

    lg = cfg.get("logo", {})
    destino = ruta_logo(cfg)
    if lg.get("link"):
        try:
            from fabrica import descargas
            pngs = [p for p in descargas.bajar(lg["link"], Path(tempfile.mkdtemp()))
                    if p.suffix.lower() == ".png"]
            if pngs:
                destino.parent.mkdir(parents=True, exist_ok=True)
                _sh.copy(pngs[0], destino)
                logger.info(f"Logo: descargado desde el link ({pngs[0].name})")
                return
            logger.warning("Logo: el link no tiene ningún .png")
        except Exception as e:
            logger.warning(f"Logo: no se pudo bajar el link ({e})")
    d = cfg.get("drive", {})
    if _sh.which("rclone") and d.get("carpeta_marca", True):
        temporal = Path(tempfile.mkdtemp())
        origen = f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}/marca"
        _sp.run(["rclone", "copy", origen, str(temporal), "--include", "*.png", "--include", "*.PNG"],
                capture_output=True, timeout=300)
        pngs = sorted(temporal.glob("*.[pP][nN][gG]"), key=lambda p: p.stat().st_mtime, reverse=True)
        if pngs:
            destino.parent.mkdir(parents=True, exist_ok=True)
            _sh.copy(pngs[0], destino)
            logger.info(f"Logo: tomado de tu Drive ({pngs[0].name})")


def obtener_logo(cfg: dict, carpeta: Path) -> Path | None:
    """Tu logo PNG si lo subiste; si no, el texto de marca convertido en logo."""
    lg = cfg.get("logo", {})
    if not lg.get("activo", True):
        return None
    logo = ruta_logo(cfg)
    if logo.is_file():
        return logo
    if lg.get("texto", "").strip():
        return logo_de_texto(lg["texto"].strip(), carpeta / "logo-texto.png")
    return None


def filtro_logo(cfg: dict, es_texto: bool = False) -> str:
    x, y, ancho = ubicacion_logo(cfg)
    if es_texto:  # un texto es más ancho que un logo: necesita más espacio para leerse
        ancho = float(cfg.get("logo", {}).get("tamano_texto", 0.34)) * 100
    ancho_logo = int(ANCHOS.get(cfg.get("video", {}).get("aspecto", "9:16"), 1080) * ancho / 100)
    opacidad = float(cfg.get("logo", {}).get("opacidad", 0.9))
    return (f"[1:v]scale={ancho_logo}:-1,format=rgba,colorchannelmixer=aa={opacidad}[logo];"
            f"[0:v][logo]overlay={_expresion_x(x)}:H*{y / 100:.4f}")


def poner_logo(cfg: dict, video: Path, salida: Path) -> Path:
    logo = obtener_logo(cfg, salida.parent)
    if not logo:
        if cfg.get("logo", {}).get("activo", True):
            logger.warning("Logo: no subiste marca/logo.png ni pusiste texto de marca; sale sin logo")
        shutil.copy(video, salida)
        return salida

    comando = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video),
               "-i", str(logo), "-filter_complex", filtro_logo(cfg, logo.name == "logo-texto.png"), "-c:v", "libx264", "-preset", "veryfast",
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
