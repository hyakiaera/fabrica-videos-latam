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


def voz_edge(cfg: dict) -> str:
    """Voz de Edge según el género elegido. Por defecto: hombre."""
    v = cfg.get("voz", {})
    genero = v.get("genero", "hombre")
    if genero not in GENEROS:
        logger.warning(f"Voz: género '{genero}' no válido, se usa hombre")
        genero = "hombre"
    return v.get(f"voz_{genero}", {"hombre": "es-MX-JorgeNeural-Male",
                                   "mujer": "es-MX-DaliaNeural-Female"}[genero])


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
        return base
    if not salida.exists() or salida.stat().st_size < 1000:
        logger.error("Voz: no se creó el audio clonado; se usa la voz de Edge")
        return base
    return salida


def duracion_audio(cfg: dict, texto: str, carpeta: Path) -> float:
    """Duración exacta de la narración (se genera la voz de prueba con Edge, que es
    gratis y rápida) para que cada imagen dure lo mismo que su parte del guion."""
    v = cfg.get("voz", {})
    velocidad = float(v.get("velocidad", 1.0))
    try:
        from moviepy import AudioFileClip

        carpeta.mkdir(parents=True, exist_ok=True)
        prueba = carpeta / "voz-medida.mp3"
        voz = voz_edge(cfg).removesuffix("-Male").removesuffix("-Female")
        asyncio.run(edge_tts.Communicate(texto, voz, rate=f"{round((velocidad - 1) * 100):+d}%").save(str(prueba)))
        with AudioFileClip(str(prueba)) as audio:
            return float(audio.duration)
    except Exception as e:
        logger.warning(f"Voz: no se pudo medir la narración ({e}); se estima")
        return len(texto.split()) / (2.5 * velocidad)


def duracion_archivo(ruta: Path) -> float:
    from moviepy import AudioFileClip

    with AudioFileClip(str(ruta)) as audio:
        return float(audio.duration)
