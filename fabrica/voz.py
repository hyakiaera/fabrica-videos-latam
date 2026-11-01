"""Voz: Edge TTS gratis (hombre o mujer, español latino neutro) y perilla
opcional para convertirla a tu voz con tu modelo de StudioVoz (Applio) o
con cualquier otro programa."""

import asyncio
import shlex
import subprocess
from pathlib import Path

import edge_tts
from loguru import logger

GENEROS = ("hombre", "mujer")
# Si la voz principal falla, se prueban otras parecidas (español latino neutro).
RESPALDO = {"hombre": ["es-US-AlonsoNeural-Male", "es-MX-JorgeNeural-Male"],
            "mujer": ["es-US-PalomaNeural-Female", "es-MX-DaliaNeural-Female"]}


def voz_edge(cfg: dict) -> str:
    """Voz de Edge según el género elegido. Por defecto: hombre."""
    v = cfg.get("voz", {})
    genero = v.get("genero", "hombre")
    if genero not in GENEROS:
        logger.warning(f"Voz: género '{genero}' no válido, se usa hombre")
        genero = "hombre"
    return v.get(f"voz_{genero}", {"hombre": "es-MX-JorgeNeural-Male",
                                   "mujer": "es-MX-DaliaNeural-Female"}[genero])


# Qué voz se usó en el último video y por qué (va a la ficha .txt).
ULTIMA = {"voz": "", "motivo": ""}


def anotar(voz: str, motivo: str = ""):
    ULTIMA["voz"], ULTIMA["motivo"] = voz, motivo[:400]


def clonar_activo(cfg: dict) -> bool:
    v = cfg.get("voz", {})
    if not v.get("clonar"):
        return False
    return v.get("motor", "applio") == "applio" or bool(v.get("comando_clonar"))


def _comando(cfg: dict, base: Path, salida: Path):
    comando = cfg["voz"]["comando_clonar"].format(entrada=shlex.quote(str(base)),
                                                  salida=shlex.quote(str(salida)))
    logger.info(f"Voz: clonando con tu herramienta → {comando}")
    subprocess.run(comando, shell=True, check=True,
                   timeout=int(cfg["voz"].get("tiempo_max_clonar", 1800)))


def generar_y_clonar(cfg: dict, texto: str, carpeta: Path) -> Path:
    """Genera la voz con Edge TTS y la convierte a tu voz.
    Si la conversión falla, devuelve la voz de Edge para no perder el video."""
    v = cfg.get("voz", {})
    carpeta.mkdir(parents=True, exist_ok=True)
    base = carpeta / "voz-base.mp3"
    salida = carpeta / "voz-clonada.wav"
    voz = voz_edge(cfg).removesuffix("-Male").removesuffix("-Female")
    velocidad = round((float(v.get("velocidad", 1.0)) - 1) * 100)
    asyncio.run(edge_tts.Communicate(texto, voz, rate=f"{velocidad:+d}%").save(str(base)))

    try:
        if v.get("motor", "applio") == "applio":
            from fabrica import voz_applio
            voz_applio.convertir(cfg, base, salida)
        else:
            _comando(cfg, base, salida)
    except Exception as e:
        logger.error(f"Voz: la clonación falló ({e}); se usa la voz gratis de Edge")
        anotar(f"Edge ({voz}) — tu voz clonada falló", f"{type(e).__name__}: {e}")
        return base
    if not salida.exists() or salida.stat().st_size < 1000:
        logger.error("Voz: no se creó el audio clonado; se usa la voz de Edge")
        anotar(f"Edge ({voz}) — tu voz clonada no creó audio")
        return base
    anotar("tu voz clonada")
    return salida


def probar_edge(cfg: dict, texto: str, carpeta: Path) -> Path | None:
    """Genera la narración con Edge. Sirve para medir su duración exacta (así cada imagen
    dura lo que su parte del guion) y de respaldo si luego Edge falla. None si Edge no responde."""
    v = cfg.get("voz", {})
    velocidad = float(v.get("velocidad", 1.0))
    carpeta.mkdir(parents=True, exist_ok=True)
    prueba = carpeta / "voz-edge.mp3"
    voces = [voz_edge(cfg)] + [x for x in v.get("voces_respaldo", RESPALDO.get(v.get("genero", "hombre"), []))]
    for nombre in voces:
        voz = nombre.removesuffix("-Male").removesuffix("-Female")
        for intento in range(2):
            try:
                asyncio.run(edge_tts.Communicate(texto, voz, rate=f"{round((velocidad - 1) * 100):+d}%")
                            .save(str(prueba)))
                if prueba.exists() and prueba.stat().st_size > 2000:
                    return prueba
            except Exception as e:
                logger.warning(f"Voz: Edge falló con {voz} (intento {intento + 1}): {e}")
    return None


def narracion_google(cfg: dict, texto: str, carpeta: Path) -> Path:
    """Respaldo cuando Edge no responde: voz gratis de Google (gTTS), español de México."""
    import subprocess

    import imageio_ffmpeg
    from gtts import gTTS

    carpeta.mkdir(parents=True, exist_ok=True)
    base = carpeta / "voz-google.mp3"
    gTTS(texto, lang="es", tld="com.mx").save(str(base))
    velocidad = float(cfg.get("voz", {}).get("velocidad", 1.0)) * 1.12  # gTTS habla algo lento
    salida = carpeta / "voz-google-final.mp3"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(base),
                    "-filter:a", f"atempo={velocidad:.2f}", str(salida)], check=True)
    logger.warning("Voz: se usó la voz de respaldo de Google porque Edge no respondió")
    anotar("Google (respaldo) — Edge no respondió")
    return salida


def duracion_audio(cfg: dict, texto: str, carpeta: Path) -> float:
    prueba = probar_edge(cfg, texto, carpeta)
    if prueba:
        return duracion_archivo(prueba)
    return len(texto.split()) / (2.5 * float(cfg.get("voz", {}).get("velocidad", 1.0)))


def duracion_archivo(ruta: Path) -> float:
    from moviepy import AudioFileClip

    with AudioFileClip(str(ruta)) as audio:
        return float(audio.duration)
