"""Saca de cada video: datos técnicos, cortes de escena, fotogramas (en hojas de
contacto), el texto de lo que se dice con tiempos y el volumen de voz/música."""
import json
import re
import subprocess
import sys
from pathlib import Path

entrada, salida = Path(sys.argv[1]), Path(sys.argv[2])
salida.mkdir(parents=True, exist_ok=True)


def correr(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def slug(t):
    return re.sub(r"[^a-z0-9]+", "-", t.lower())[:60].strip("-") or "video"


for video in sorted(p for p in entrada.iterdir() if p.is_file()):
    dest = salida / slug(video.stem)
    dest.mkdir(exist_ok=True)
    info = json.loads(correr(["ffprobe", "-v", "quiet", "-print_format", "json",
                              "-show_format", "-show_streams", str(video)]).stdout or "{}")
    dur = float(info.get("format", {}).get("duration", 0))

    # Cortes de escena
    r = correr(["ffmpeg", "-i", str(video), "-vf", "select='gt(scene,0.25)',showinfo",
                "-f", "null", "-"])
    cortes = [round(float(t), 2) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]

    # Fotogramas: uno por segundo los primeros 5 s (el gancho) y luego cada 2 s
    cuadros = dest / "cuadros"
    cuadros.mkdir(exist_ok=True)
    tiempos = [0, 0.5, 1, 1.5, 2, 3, 4, 5] + [t for t in range(6, int(dur), 2)]
    for k, t in enumerate(tiempos):
        correr(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                "-vf", f"scale=360:-2,drawtext=text='{t}s':x=8:y=8:fontsize=28:fontcolor=yellow:box=1:boxcolor=black",
                str(cuadros / f"{k:03d}.jpg")])
    correr(["ffmpeg", "-y", "-v", "error", "-pattern_type", "glob", "-i", str(cuadros / "*.jpg"),
            "-vf", "tile=6x3:padding=4", "-q:v", "4", str(dest / "hoja-%02d.jpg")])

    # Texto con tiempos
    try:
        from faster_whisper import WhisperModel
        modelo = WhisperModel("small", device="cpu", compute_type="int8")
        segmentos, datos = modelo.transcribe(str(video), word_timestamps=False)
        lineas = [f"[{s.start:6.2f} - {s.end:6.2f}] {s.text.strip()}" for s in segmentos]
        texto = f"Idioma: {datos.language}\n" + "\n".join(lineas)
    except Exception as e:  # p. ej. el video no trae audio
        texto = f"No se pudo sacar el texto ({type(e).__name__}: {e}); ¿el video tiene audio?"
    (dest / "texto.txt").write_text(texto, encoding="utf-8")

    # Volumen
    r = correr(["ffmpeg", "-i", str(video), "-af", "ebur128", "-f", "null", "-"])
    volumen = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1:] or ["?"]

    resumen = {
        "archivo": video.name, "duracion_s": round(dur, 2),
        "video": [{k: s.get(k) for k in ("codec_name", "width", "height", "r_frame_rate")}
                  for s in info.get("streams", []) if s.get("codec_type") == "video"],
        "cortes_de_escena": cortes, "num_cortes": len(cortes),
        "segundos_por_escena": round(dur / (len(cortes) + 1), 2) if dur else None,
        "volumen_lufs": volumen[0],
    }
    (dest / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resumen, ensure_ascii=False))
