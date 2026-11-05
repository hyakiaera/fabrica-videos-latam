"""Efectos de sonido en los cortes: un "whoosh" suave en cada cambio de escena, como en
los videos de TikTok. El sonido se genera aquí mismo (no tiene derechos de autor)."""

import re
import subprocess
from pathlib import Path

import imageio_ffmpeg
from loguru import logger

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def duracion(ruta: Path) -> float:
    r = subprocess.run([FFMPEG, "-i", str(ruta)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def cortes_de(clips: list[Path]) -> list[float]:
    """Segundos donde cambia la escena (el inicio de cada clip, menos el primero)."""
    tiempos, t = [], 0.0
    for clip in clips[:-1]:
        t += duracion(clip)
        tiempos.append(round(t, 3))
    return tiempos


def whoosh(salida: Path) -> Path:
    if not salida.exists():
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "anoisesrc=color=pink:duration=0.5:amplitude=0.6:sample_rate=44100",
                        "-af", "highpass=f=400,lowpass=f=6000,afade=t=in:st=0:d=0.28,afade=t=out:st=0.28:d=0.22",
                        "-ac", "2", str(salida)], check=True)
    return salida


def agregar(cfg: dict, video: Path, cortes: list[float], salida: Path) -> Path:
    """Mezcla un whoosh en cada corte. Si algo falla, devuelve el video tal cual."""
    import os
    e = cfg.get("efectos", {})
    # Apagados por defecto: el whoosh sonaba como un soplido de aire en las pausas.
    # Se prenden con la variable EFECTOS = si (o activos = true en fabrica.toml).
    activos = os.environ.get("EFECTOS", "").strip().lower() in ("si", "sí", "1", "true") or e.get("activos", False)
    if not activos or not cortes:
        return video
    volumen = float(e.get("volumen", 0.15))
    cortes = cortes[: int(e.get("maximo", 40))]
    try:
        sonido = whoosh(salida.with_name("whoosh.wav"))
        # Cada whoosh empieza un poco antes del corte, para que "empuje" la escena nueva.
        partes = [f"[1:a]adelay={max(0, int((t - 0.22) * 1000))}|{max(0, int((t - 0.22) * 1000))},"
                  f"volume={volumen}[w{k}]" for k, t in enumerate(cortes)]
        separar = f"[1:a]asplit={len(cortes)}" + "".join(f"[s{k}]" for k in range(len(cortes)))
        partes = [p.replace("[1:a]", f"[s{k}]", 1) for k, p in enumerate(partes)]
        mezcla = "[0:a]" + "".join(f"[w{k}]" for k in range(len(cortes)))
        filtro = ";".join([separar, *partes, f"{mezcla}amix=inputs={len(cortes) + 1}:normalize=0:duration=first[a]"])
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(video), "-i", str(sonido),
                        "-filter_complex", filtro, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", str(salida)], check=True, timeout=600)
        return salida
    except Exception as ex:
        logger.warning(f"Efectos: no se pudieron agregar ({ex}); el video sigue sin ellos")
        return video
