"""Revisión automática del video terminado, ANTES de publicarlo. Si sale mal (pantalla negra,
sin voz, muy corto, casi sin imágenes), se guarda en Drive igual pero NO se publica, y la
ficha dice por qué. Así no sale nada feo en tus redes."""
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
from loguru import logger


def _ff(*args, timeout=900) -> str:
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", *map(str, args)],
                       capture_output=True, text=True, timeout=timeout)
    return r.stderr


def revisar(video: Path, conteo: dict | None = None, minimo_segundos: float = 15) -> list[str]:
    """Lista de problemas encontrados (vacía = el video está bien)."""
    problemas = []
    info = _ff("-i", video)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info)
    duracion = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0
    if duracion < minimo_segundos:
        problemas.append(f"muy corto ({duracion:.0f} s)")
    if "Audio:" not in info:
        problemas.append("no tiene audio")
    else:
        vol = _ff("-i", video, "-af", "volumedetect", "-vn", "-f", "null", "-")
        media = re.search(r"mean_volume: (-?[\d.]+) dB", vol)
        if media and float(media.group(1)) < -45:
            problemas.append(f"casi sin sonido ({media.group(1)} dB)")
    negro = _ff("-i", video, "-vf", "blackdetect=d=1.0:pic_th=0.97", "-an", "-f", "null", "-")
    oscuro = sum(float(x) for x in re.findall(r"black_duration:([\d.]+)", negro))
    if duracion and oscuro / duracion > 0.2:
        problemas.append(f"{oscuro:.0f} s de pantalla negra")
    if conteo and "ia" in conteo:  # (los videos de stock no usan imágenes)
        usadas = sum(conteo.get(k, 0) for k in ("ia", "real", "stock", "propias", "clips"))
        graficas = conteo.get("_graficas", 0)
        if usadas + graficas == 0 and conteo.get("_escenas", 0) > 0:
            problemas.append("ninguna imagen encajó con el guion")
    if problemas:
        logger.warning("Revisión del video: " + "; ".join(problemas) + " → no se publica")
    else:
        logger.info(f"Revisión del video: bien ({duracion:.0f} s)")
    return problemas
