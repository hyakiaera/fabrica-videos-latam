"""Arma el video con el motor de MoneyPrinterTurbo y le pone el logo."""

import shutil
from datetime import datetime
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

    # Música según el tono (tus beats de la carpeta "musica" en Drive); si no hay, la de siempre.
    from app.services import bgm as mpt_bgm
    from fabrica import musica
    try:
        cancion = musica.elegir(cfg, datos.get("tono", ""), datos.get("categoria", ""),
                                Path(mpt_bgm.uploaded_bgm_dir(create=True)))
    except Exception as e:
        logger.warning(f"Música: no se pudo elegir por tono ({e})")
        cancion = None
    if cancion and v.get("musica", "random"):
        params["bgm_file"] = str(cancion)
        datos["musica_usada"] = cancion.name.removeprefix("fabrica-")

    audio_propio = None
    audio_edge = None
    voz.anotar(f"Edge ({voz.voz_edge(cfg)})")
    from fabrica import voz_yo
    if voz_yo.activo(cfg):
        try:
            audio_propio = voz_yo.generar(cfg, datos["guion"], trabajo / "voz-yo")
            if "pulida" in audio_propio.name:  # (también "…-pulida-limpia.wav")
                voz.anotar("yo (la IA lectora imitando tu forma de hablar + tu modelo HYAKO_LOCUTOR)")
            elif cfg.get("voz", {}).get("yo_pulir", True):
                voz.anotar("yo (la IA lectora imitando tu forma de hablar) — NO se pulió con tu modelo",
                           voz_yo.ERROR_PULIDO["motivo"])
            else:
                voz.anotar("yo sin modelo (la IA lectora imitando tu forma de hablar)")
        except Exception as e:
            logger.error(f"Voz yo falló; se usa la voz normal: {e}")
            voz.anotar(f"Edge ({voz.voz_edge(cfg)}) — la voz 'yo' falló", f"{type(e).__name__}: {str(e)[-300:]}")
    if audio_propio:
        pass  # ya está la voz "yo"
    elif voz.clonar_activo(cfg):
        audio_propio = voz.generar_y_clonar(cfg, datos["guion"], trabajo / "voz")
    else:
        audio_edge = voz.probar_edge(cfg, datos["guion"], trabajo / "voz")
        if audio_edge is None:
            audio_propio = voz.narracion_google(cfg, datos["guion"], trabajo / "voz")

    if "stock_video" in estilo.fuentes:
        from fabrica.config import secreto
        claves = {"pexels": secreto("PEXELS_API_KEY"), "pixabay": secreto("PIXABAY_API_KEY")}
        for fuente, clave in claves.items():
            if clave and not mpt_config.app.get(f"{fuente}_api_keys"):
                mpt_config.app[f"{fuente}_api_keys"] = [clave]
        fuente = v.get("fuente_stock", "pexels")
        if not claves.get(fuente):
            fuente = "pixabay" if claves["pixabay"] else "pexels"
        # Pixabay/Pexels bloquean (error 429) si se bajan muchos videos a la vez.
        mpt_config.app["material_concurrency"] = int(v.get("descargas_simultaneas_stock", 2))
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
        total = voz.duracion_archivo(audio_propio or audio_edge)
        clips = movimiento.clips_de_escenas(cfg, datos["escenas"], imagenes, estilo_clave(estilo),
                                            total + 0.6, trabajo / "clips", tono=datos.get("tono", ""))
        from fabrica import efectos
        datos["cortes"] = efectos.cortes_de(clips)
        # Las escenas ya traen sus cortes dinámicos: sin transiciones de MoneyPrinterTurbo
        # (sus fundidos dejaban el primer cuadro del video en negro).
        params["video_transition_mode"] = None
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

    def correr(audio: Path | None):
        """Corre MoneyPrinterTurbo; con 'audio' usa ese archivo y saca subtítulos con Whisper."""
        from app.services import subtitle as mpt_subtitulos

        proveedor_original = mpt_config.app.get("subtitle_provider", "edge")
        modelo_original = mpt_subtitulos.model_size
        datos_tarea = dict(params)
        if audio:
            destino = Path(utils.task_dir(task_id)) / audio.name
            shutil.copy(audio, destino)
            datos_tarea["custom_audio_file"] = str(destino)
            # Sin TTS no hay tiempos de palabras: Whisper saca los subtítulos del audio.
            # Un modelo chico basta para español claro y es mucho más rápido sin tarjeta gráfica.
            mpt_config.app["subtitle_provider"] = "whisper"
            mpt_subtitulos.model_size = vz.get("modelo_whisper", "small")
        try:
            return tm.start(task_id, VideoParams(**datos_tarea))
        finally:
            mpt_config.app["subtitle_provider"] = proveedor_original
            mpt_subtitulos.model_size = modelo_original

    resultado = correr(audio_propio)
    if not (resultado or {}).get("videos") and not audio_propio:
        # Edge falló justo al hacer el video: se usa la narración que ya teníamos (o la de Google).
        logger.warning("La voz falló al armar el video; se reintenta con la narración guardada")
        task_id = str(uuid.uuid4())
        resultado = correr(audio_edge or voz.narracion_google(cfg, datos["guion"], trabajo / "voz"))

    datos["voz_usada"] = dict(voz.ULTIMA)
    # Narración sola (sin música), para que el avatar mueva la boca con ella.
    narracion = Path(utils.task_dir(task_id)) / "audio.mp3"
    candidatos = [a for a in (audio_propio, narracion, audio_edge) if a]
    datos["audio_narracion"] = next((str(a) for a in candidatos if Path(a).exists()), "")
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


def firma(cfg: dict, titulo: str = "") -> list[str]:
    """Datos del archivo (metadatos) con tu marca como autor del video. Se borran las
    etiquetas técnicas del programa de edición para que el autor que se vea sea tu canal."""
    marca = cfg.get("firma", {})
    nombre = marca.get("autor") or cfg.get("logo", {}).get("texto") or "DESVERGUEOFFICIAL"
    datos = {
        "artist": nombre, "author": nombre, "album_artist": nombre, "publisher": nombre,
        "copyright": marca.get("copyright", f"© {datetime.now().year} {nombre}"),
        "comment": marca.get("comentario", f"Video de {nombre}"),
        "title": titulo,
    }
    argumentos = ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:v", "+bitexact",
                  "-flags:a", "+bitexact"]
    for clave, valor in datos.items():
        if valor:
            argumentos += ["-metadata", f"{clave}={valor}"]
    return argumentos


def poner_logo(cfg: dict, video: Path, salida: Path, titulo: str = "") -> Path:
    """Pone el logo (si hay) y firma el archivo con tu marca."""
    logo = obtener_logo(cfg, salida.parent)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if not logo:
        if cfg.get("logo", {}).get("activo", True):
            logger.warning("Logo: no subiste marca/logo.png ni pusiste texto de marca; sale sin logo")
        comando = [ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-c", "copy",
                   *firma(cfg, titulo), "-movflags", "+faststart", str(salida)]
    else:
        comando = [ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-i", str(logo),
                   "-filter_complex", filtro_logo(cfg, logo.name == "logo-texto.png"),
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy",
                   *firma(cfg, titulo), "-movflags", "+faststart", str(salida)]
    subprocess.run(comando, check=True)
    return salida


def miniatura(video: Path, salida: Path) -> Path | None:
    try:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", "1",
                        "-i", str(video), "-frames:v", "1", "-q:v", "3", str(salida)], check=True)
        return salida
    except subprocess.CalledProcessError:
        return None
