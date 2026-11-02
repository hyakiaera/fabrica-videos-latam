"""Voz "yo": una IA lectora de código abierto (Chatterbox multilingüe, licencia MIT)
escucha una muestra tuya y lee el guion imitando tu forma de hablar (tono, ritmo,
acento). Después, si tienes tu modelo de voz (HYAKO_LOCUTOR), lo pule con tu timbre.

Tus grabaciones van en Google Drive:  Mi unidad › Fabrica de Videos › mi voz
Puedes subir ahí todos los audios que quieras (se van juntando para entrenar algún día
tu propio lector). Si un archivo se llama "muestra" (muestra.mp3, muestra.wav...), se usa
ese; si no, se toma un pedazo limpio del audio más largo."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg
from loguru import logger

from fabrica.config import RAIZ

MOTOR = RAIZ / ".chatterbox"
AUDIOS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".mp4", ".webm")

LECTOR = r"""
import re, sys, torch, torchaudio
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
texto_ruta, muestra, salida, cfg_weight, exageracion = sys.argv[1:6]
texto = open(texto_ruta, encoding="utf-8").read()
# Una oración por pedazo: cortar a media frase es lo que causaba pausas raras.
frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto) if f.strip()]
modelo = ChatterboxMultilingualTTS.from_pretrained(device="cpu")


def recortar(wav, umbral=0.01):
    # Quita el silencio del principio y del final de cada oración.
    activo = (wav.abs() > umbral).nonzero()
    if activo.numel() == 0:
        return wav
    margen = int(modelo.sr * 0.04)
    return wav[:, max(0, activo[0, 1].item() - margen): activo[-1, 1].item() + margen]


pedazos = []
pausa = torch.zeros(1, int(modelo.sr * 0.18))
for k, frase in enumerate(frases):
    print(f"frase {k + 1}/{len(frases)}", flush=True)
    wav = modelo.generate(frase, language_id="es", audio_prompt_path=muestra,
                          cfg_weight=float(cfg_weight), exaggeration=float(exageracion))
    pedazos += [recortar(wav), pausa]
torchaudio.save(salida, torch.cat(pedazos, dim=1), modelo.sr)
print("ok")
"""


SIMBOLOS = [(r"%", " por ciento"), (r"\$\s?", ""), (r"&", " y "), (r"\bvs\.?\b", "contra"),
            (r"\bEE\.?\s?UU\b", "Estados Unidos"), (r"\bkm\b", "kilómetros"), (r"\bkg\b", "kilos"),
            (r"\bNo\.\s?", "número "), (r"#", "número ")]


def para_leer(texto: str) -> str:
    """Deja el guion listo para leerse en voz alta: números en palabras, símbolos y
    abreviaturas escritos completos (la IA lectora se trababa con ellos)."""
    import re as _re

    from num2words import num2words

    dolares = _re.sub(r"\$\s?(\d[\d,.]*)", lambda m: f"{m.group(1)} dólares", texto)
    for patron, cambio in SIMBOLOS:
        dolares = _re.sub(patron, cambio, dolares, flags=_re.I)

    def a_palabras(m):
        crudo = m.group(0).replace(",", "")
        try:
            return num2words(float(crudo) if "." in crudo else int(crudo), lang="es")
        except Exception:
            return m.group(0)

    # Marcadores deportivos "2-1" → "dos a uno"
    dolares = _re.sub(r"\b(\d+)\s?-\s?(\d+)\b", lambda m: f"{m.group(1)} a {m.group(2)}", dolares)
    # Comas solo como separador de miles (1,500); la coma de una frase se respeta.
    return _re.sub(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?", a_palabras, dolares)


def activo(cfg: dict) -> bool:
    return cfg.get("voz", {}).get("lector") == "yo"


def _python() -> Path:
    return MOTOR / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")


def _correr(cmd: list, timeout: int, cwd: Path | None = None) -> str:
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, timeout=timeout,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    salida = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 or "Traceback (most recent call last)" in salida:
        raise RuntimeError(salida[-1200:])
    return salida


def instalar():
    """Instala Chatterbox en su propio entorno (no toca nada de la fábrica). Una sola vez."""
    marca = MOTOR / ".fabrica_ok2"
    if marca.exists() and _python().exists():
        return
    import sys

    logger.info("Voz yo: instalando la IA lectora por primera vez (unos 10 minutos)...")
    MOTOR.mkdir(parents=True, exist_ok=True)
    _correr([sys.executable, "-m", "pip", "install", "-q", "uv"], 600)
    uv = [sys.executable, "-m", "uv"]
    shutil.rmtree(MOTOR / ".venv", ignore_errors=True)
    _correr(uv + ["venv", MOTOR / ".venv", "--python", "3.11"], 600, cwd=MOTOR)
    # setuptools<81: la librería de marca de agua de Chatterbox (perth) todavía usa
    # pkg_resources, que las versiones nuevas de setuptools ya no traen.
    _correr(uv + ["pip", "install", "--python", _python(), "chatterbox-tts", "setuptools<81",
                  "--extra-index-url", "https://download.pytorch.org/whl/cpu",
                  "--index-strategy", "unsafe-best-match"], 3600, cwd=MOTOR)
    marca.write_text("ok")


def traer_grabaciones(cfg: dict, carpeta: Path) -> list[Path]:
    """Tus grabaciones de la carpeta 'mi voz' de Drive (o de la carpeta 'mi voz' en tu PC)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    d = cfg.get("drive", {})
    nombre = cfg.get("voz", {}).get("carpeta_grabaciones", "mi voz")
    if shutil.which("rclone"):
        origen = f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}/{nombre}"
        subprocess.run(["rclone", "copy", origen, str(carpeta), "--max-depth", "2"],
                       capture_output=True, timeout=1800)
    if (RAIZ / nombre).is_dir():
        for p in (RAIZ / nombre).rglob("*"):
            if p.is_file() and p.suffix.lower() in AUDIOS:
                shutil.copy(p, carpeta / p.name)
    return [p for p in carpeta.rglob("*") if p.is_file() and p.suffix.lower() in AUDIOS]


def _duracion(ruta: Path) -> float:
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(ruta)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def preparar_muestra(grabaciones: list[Path], salida: Path) -> Path:
    """Muestra de ~15 segundos: el archivo 'muestra' si existe; si no, un pedazo del medio
    del audio más largo (lejos del inicio y del final, donde suele haber ruidos)."""
    elegida = next((g for g in grabaciones if g.stem.lower().startswith("muestra")), None)
    inicio, largo = 0.0, 20.0
    if elegida is None:
        elegida = max(grabaciones, key=_duracion)
        total = _duracion(elegida)
        inicio = max(0.0, total / 2 - 7.5) if total > 20 else 0.0
        largo = 15.0
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-ss", f"{inicio:.1f}",
                    "-i", str(elegida), "-t", f"{largo:.1f}", "-ac", "1", "-ar", "24000",
                    "-af", "loudnorm", str(salida)], check=True)
    logger.info(f"Voz yo: muestra tomada de '{elegida.name}' ({largo:.0f} s)")
    return salida


def generar(cfg: dict, texto: str, carpeta: Path) -> Path:
    """Lee el guion con tu forma de hablar y, si hay modelo de voz, lo pule con tu timbre."""
    carpeta.mkdir(parents=True, exist_ok=True)
    grabaciones = traer_grabaciones(cfg, carpeta / "grabaciones")
    if not grabaciones:
        raise RuntimeError("No hay grabaciones en la carpeta 'mi voz' de tu Drive")
    total = sum(_duracion(g) for g in grabaciones) / 60
    logger.info(f"Voz yo: {len(grabaciones)} grabaciones tuyas ({total:.1f} minutos en total)")
    muestra = preparar_muestra(grabaciones, carpeta / "muestra.wav")
    instalar()
    (carpeta / "guion.txt").write_text(para_leer(texto), encoding="utf-8")
    script = MOTOR / "fabrica_lector.py"
    script.write_text(LECTOR, encoding="utf-8")
    leido = carpeta / "voz-yo.wav"
    v = cfg.get("voz", {})
    _correr([_python(), script, (carpeta / "guion.txt").resolve(), muestra.resolve(), leido.resolve(),
             v.get("yo_ritmo", 0.4), v.get("yo_expresion", 0.5)],
            int(cfg.get("voz", {}).get("tiempo_max_yo", 3600)), cwd=MOTOR)
    if cfg.get("voz", {}).get("link_modelo") or cfg.get("voz", {}).get("pulir_con_modelo"):
        from fabrica import voz_applio
        try:
            pulido = voz_applio.convertir(cfg, leido, carpeta / "voz-yo-pulida.wav")
            if pulido.exists() and pulido.stat().st_size > 1000:
                return pulido
        except Exception as e:
            logger.warning(f"Voz yo: no se pudo pulir con tu modelo ({e}); se usa la lectura tal cual")
    return leido
