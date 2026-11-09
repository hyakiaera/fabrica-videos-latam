"""Voz "yo": una IA lectora de código abierto (Chatterbox multilingüe, licencia MIT)
escucha una muestra tuya y lee el guion imitando tu forma de hablar (tono, ritmo,
acento). Después, si tienes tu modelo de voz (HYAKO_LOCUTOR), lo pule con tu timbre.

Tus grabaciones van en Google Drive:  Mi unidad › Fabrica de Videos › mi voz
Puedes subir ahí todos los audios que quieras (se van juntando para entrenar algún día
tu propio lector). Si un archivo se llama "muestra" (muestra.mp3, muestra.wav...), se usa
ese (o se juntan pedazos de muestra1, muestra2, muestra3); si no, se toma un pedazo
limpio del audio más largo."""

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
texto_ruta, muestra, salida, cfg_weight, exageracion, por_pedazo = sys.argv[1:7]
texto = open(texto_ruta, encoding="utf-8").read()
# Varias oraciones juntas para que la entonación fluya (cada pedazo "arranca de cero").
oraciones = []
for f in re.split(r"(?<=[.!?])\s+", texto):
    f = f.strip()
    # Una "oración" larguísima (guion sin puntos) se parte en comas o, si no hay, cada ~25
    # palabras: si la IA recibe un texto muy largo de un jalón, se pierde y balbucea.
    while len(f) > 240:
        corte = max(f.rfind(",", 0, 240), f.rfind(";", 0, 240))
        if corte < 80:
            palabras = f[:240].split(" ")
            corte = len(" ".join(palabras[:-1]))
        oraciones.append(f[:corte + 1].strip().rstrip(",;") + ".")
        f = f[corte + 1:].strip()
    if f:
        oraciones.append(f)
frases, actual, cuenta = [], "", 0
for o in oraciones:
    if actual and (cuenta >= int(por_pedazo) or len(actual) + len(o) > 300):
        frases.append(actual.strip()); actual, cuenta = "", 0
    actual += " " + o
    cuenta += 1
if actual.strip():
    frases.append(actual.strip())
modelo = ChatterboxMultilingualTTS.from_pretrained(device="cpu")


def recortar(wav, umbral=0.01):
    # Quita el silencio del principio y del final de cada oración.
    activo = (wav.abs() > umbral).nonzero()
    if activo.numel() == 0:
        return wav
    margen = int(modelo.sr * 0.04)
    return wav[:, max(0, activo[0, 1].item() - margen): activo[-1, 1].item() + margen]


pedazos = []
for k, frase in enumerate(frases):
    print(f"pedazo {k + 1}/{len(frases)}", flush=True)
    wav = modelo.generate(frase, language_id="es", audio_prompt_path=muestra,
                          cfg_weight=float(cfg_weight), exaggeration=float(exageracion))
    # Pausa según cómo termina: una pregunta o exclamación respira un poco más.
    segundos = 0.32 if frase.endswith(("?", "!")) else 0.26
    pedazos += [recortar(wav), torch.zeros(1, int(modelo.sr * segundos))]
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


# Por qué no se pudo pulir con tu modelo la última vez (va a la ficha).
ERROR_PULIDO = {"motivo": ""}


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


def preparar_muestra(grabaciones: list[Path], salida: Path, segundos_total: float = 10.0) -> Path:
    """Muestra de tu voz para la IA lectora.

    - Si hay archivos que empiezan con "muestra" (muestra.mp3, muestra1.mp3, muestra2.wav...),
      se toma un pedazo de cada uno (hasta 3) y se juntan: más variedad de cómo hablas.
    - Si no, un pedazo del medio del audio más largo.
    La IA solo escucha unos 10 segundos de muestra, así que el total se reparte en ese tiempo."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    muestras = sorted(g for g in grabaciones if g.stem.lower().startswith("muestra"))[:3]
    if not muestras:
        muestras = [max(grabaciones, key=_duracion)]
    por_cada = segundos_total / len(muestras)
    pedazos = []
    for k, audio in enumerate(muestras):
        total = _duracion(audio)
        # Del medio del audio, lejos del inicio y del final (donde suele haber ruidos o silencio).
        inicio = max(0.0, total / 2 - por_cada / 2) if total > por_cada + 1 else 0.0
        pedazo = salida.with_name(f"pedazo{k}.wav")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", f"{inicio:.1f}", "-i", str(audio),
                        "-t", f"{por_cada:.1f}", "-ac", "1", "-ar", "24000",
                        # Muestra limpia: sin zumbido grave, sin ruido de fondo, sin silencio al inicio.
                        "-af", "highpass=f=70,afftdn=nf=-30,silenceremove=start_periods=1:start_threshold=-45dB,loudnorm",
                        str(pedazo)], check=True)
        pedazos.append(pedazo)
    if len(pedazos) == 1:
        pedazos[0].replace(salida)
    else:
        entradas = sum((["-i", str(p)] for p in pedazos), [])
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", *entradas, "-filter_complex",
                        f"concat=n={len(pedazos)}:v=0:a=1", str(salida)], check=True)
    logger.info(f"Voz yo: muestra de {len(muestras)} audio(s): {', '.join(m.name for m in muestras)}")
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
             v.get("yo_ritmo", 0.4), v.get("yo_expresion", 0.5), v.get("yo_oraciones_por_pedazo", 3)],
            int(cfg.get("voz", {}).get("tiempo_max_yo", 3600)), cwd=MOTOR)
    ERROR_PULIDO["motivo"] = ""
    if v.get("yo_pulir", True) and not (v.get("link_modelo") or v.get("pulir_con_modelo")):
        ERROR_PULIDO["motivo"] = "no llegó el link de tu modelo (secreto MI_VOS)"
    if v.get("yo_pulir", True) and (v.get("link_modelo") or v.get("pulir_con_modelo")):
        from fabrica import voz_applio
        try:
            pulido = voz_applio.convertir(cfg, leido, carpeta / "voz-yo-pulida.wav")
            if pulido.exists() and pulido.stat().st_size > 1000:
                limpio = limpiar(cfg, pulido, pausas=False)
                try:  # el modelo mete ruido en las pausas: donde la lectora calló, silencio total
                    return silenciar_con_guia(limpio, leido)
                except Exception as e:
                    logger.warning(f"Voz yo: no se pudo usar la lectura como guía ({e})")
                    return limpio
        except Exception as e:
            logger.warning(f"Voz yo: no se pudo pulir con tu modelo ({e}); se usa la lectura tal cual")
            ERROR_PULIDO["motivo"] = f"{type(e).__name__}: {str(e)[-250:]}"
    return limpiar(cfg, leido)


def limpiar(cfg: dict, audio: Path, pausas: bool = True) -> Path:
    """Quita el soplido y el zumbido de los silencios entre frases: el modelo de voz a veces
    convierte el silencio en aire, y las muestras pueden traer ruido de fondo. La voz no se toca."""
    v = cfg.get("voz", {})
    if not v.get("yo_limpiar", True):
        return audio
    salida = audio.with_name(audio.stem + "-limpia.wav")
    umbral = v.get("yo_umbral_silencio", "-38dB")
    filtros = ("highpass=f=70,"                 # zumbido grave
               "afftdn=nf=-28,"                 # ruido de fondo parejo (aire, siseo)
               f"agate=threshold={umbral}:range=0.02:attack=5:release=180,"  # silencio de verdad entre frases
               "loudnorm=I=-16:TP=-1.5:LRA=11")
    try:
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(audio),
                        "-af", filtros, "-ar", "44100", str(salida)], check=True, timeout=600)
        if not (salida.exists() and salida.stat().st_size > 1000):
            return audio
    except Exception as e:
        logger.warning(f"Voz yo: no se pudo limpiar el audio ({e}); se usa tal cual")
        return audio
    if not pausas:
        return salida
    try:
        return silenciar_pausas(salida, float(v.get("yo_pausa_db", 24)))
    except Exception as e:
        logger.warning(f"Voz yo: no se pudieron limpiar las pausas ({e})")
        return salida


def _muestras(audio: Path, tasa: int):
    import numpy as np
    crudo = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-loglevel", "error", "-i", str(audio), "-f", "f32le",
                            "-ac", "1", "-ar", str(tasa), "-"], capture_output=True, check=True, timeout=600).stdout
    return np.frombuffer(crudo, dtype=np.float32).copy()


def silenciar_con_guia(audio: Path, guia: Path, margen_ms: int = 20) -> Path:
    """El modelo de tu voz (HYAKO) convierte el silencio de las pausas en un soplido de unos
    -35 dB. La lectura ORIGINAL (antes del modelo) tiene las pausas en silencio perfecto y dura
    lo mismo: se usa como guía y, donde ella calla, el resultado queda en silencio total."""
    import numpy as np
    tasa = 44100
    x, g = _muestras(audio, tasa), _muestras(guia, tasa)
    if abs(len(x) - len(g)) > tasa * 0.5:  # no están alineadas: no se toca
        logger.warning("Voz yo: la lectura y la voz pulida no duran lo mismo; no se usa la guía")
        return audio
    n = min(len(x), len(g))
    ventana = int(tasa * 0.01)
    cuadros = n // ventana
    rms = np.sqrt(np.mean(g[: cuadros * ventana].reshape(cuadros, ventana) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    voz = np.percentile(db, 90)
    habla = db > max(voz - 36, -52)  # la lectora habla (incluye "s" y finales suaves)
    margen = max(1, margen_ms // 10)
    habla = np.convolve(habla.astype(float), np.ones(2 * margen + 1), mode="same") > 0
    ganancia = np.repeat(habla.astype(np.float32), ventana)
    ganancia = np.concatenate([ganancia, np.full(len(x) - len(ganancia), ganancia[-1] if len(ganancia) else 1, np.float32)])
    rampa = int(tasa * 0.008)
    ganancia = np.convolve(ganancia, np.ones(rampa, np.float32) / rampa, mode="same")
    y = (x * ganancia[: len(x)]).astype(np.float32)
    salida = audio.with_name(audio.stem + "-guia.wav")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(tasa),
                    "-ac", "1", "-i", "-", "-c:a", "pcm_s16le", str(salida)], input=y.tobytes(), check=True, timeout=600)
    logger.info(f"Voz yo: pausas copiadas de la lectura original ({1 - habla.mean():.0%} en silencio total)")
    return salida


def silenciar_pausas(audio: Path, debajo_db: float = 24) -> Path:
    """Silencio digital en las pausas. El "loudnorm" sube lo bajito y el soplido que dejó el
    modelo vuelve a oírse; aquí, DESPUÉS de nivelar, todo lo que esté `debajo_db` por debajo
    de la voz se apaga con rampas suaves. Los finales de palabra se respetan (120 ms)."""
    import numpy as np
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    tasa = 44100
    crudo = subprocess.run([ff, "-loglevel", "error", "-i", str(audio), "-f", "f32le", "-ac", "1",
                            "-ar", str(tasa), "-"], capture_output=True, check=True, timeout=600).stdout
    x = np.frombuffer(crudo, dtype=np.float32).copy()
    ventana = int(tasa * 0.02)
    n = len(x) // ventana
    if n < 10:
        return audio
    cuadros = x[: n * ventana].reshape(n, ventana)
    rms = np.sqrt(np.mean(cuadros ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    voz = np.percentile(db, 90)
    umbral = max(voz - debajo_db, -60.0)
    # El soplido es "plano" (todas las frecuencias por igual); la voz tiene tono. Se queda lo que
    # suena a voz, más 120 ms alrededor para no cortar las "s" y los finales de palabra.
    espectro = np.abs(np.fft.rfft(cuadros * np.hanning(ventana), axis=1)) + 1e-9
    plano = np.exp(np.mean(np.log(espectro), axis=1)) / np.mean(espectro, axis=1)
    activo = (db > umbral) & ((plano < 0.35) | (db > voz - 12))
    margen = 6  # 120 ms antes y después de cada parte con voz
    activo = np.convolve(activo.astype(float), np.ones(2 * margen + 1), mode="same") > 0
    ganancia = np.repeat(activo.astype(np.float32), ventana)
    ganancia = np.concatenate([ganancia, np.full(len(x) - len(ganancia), ganancia[-1], np.float32)])
    rampa = int(tasa * 0.015)
    ganancia = np.convolve(ganancia, np.ones(rampa, np.float32) / rampa, mode="same")
    y = (x * ganancia).astype(np.float32)
    salida = audio.with_name(audio.stem + "-pausas.wav")
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(tasa), "-ac", "1", "-i", "-",
                    "-c:a", "pcm_s16le", str(salida)], input=y.tobytes(), check=True, timeout=600)
    apagado = 1 - activo.mean()
    logger.info(f"Voz yo: pausas en silencio total ({apagado:.0%} del audio, umbral {umbral:.0f} dB)")
    return salida
