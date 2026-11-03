"""Tu avatar: tus videos reales con la boca moviéndose al ritmo de la narración
(LatentSync de ByteDance, gratis), hecho en Kaggle con su GPU gratis y sin que
tengas que estar presente. Después se pone en el video de varias formas:

  intro y cierre  tú a pantalla completa al inicio y al final
  esquina         imágenes del tema y tú en un círculo arriba a la derecha
  dividida        tú arriba, imágenes y subtítulos abajo (estilo análisis)
  mixto           intro completo + esquina en medio + cierre completo

Si algo falla (Kaggle ocupado, no se ve tu cara...), el video sale sin avatar."""

import json
import os
import random
import shutil
import subprocess
import time
from pathlib import Path

import imageio_ffmpeg
from loguru import logger

from fabrica.config import RAIZ, secreto

MODOS = ("intro y cierre", "esquina", "dividida", "mixto")
HISTORIAL = RAIZ / "estado" / "avatares.json"
VIDEOS = (".mp4", ".mov", ".m4v", ".webm")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# Lo que corre en Kaggle: lo mismo que tu cuaderno "Avatar que Habla", sin preguntas.
SCRIPT_KAGGLE = r'''
import glob, os, subprocess, sys
ENTRADA = glob.glob("/kaggle/input/*/audio.wav")[0].rsplit("/", 1)[0]
LS, PY = "/kaggle/working/LatentSync", "/kaggle/working/ls_env/bin/python"
def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True)
    print((p.stdout + p.stderr)[-3000:], flush=True)
    return p.returncode, p.stdout + p.stderr
run("git clone -q --depth 1 https://github.com/bytedance/LatentSync " + LS)
run(f"sed -i 's/get_device_capability()\\[0\\] > 7/get_device_capability()[0] >= 7/' {LS}/scripts/inference.py")
run([sys.executable, "-m", "pip", "install", "-q", "uv"])
run([sys.executable, "-m", "uv", "venv", "/kaggle/working/ls_env", "--python", "3.10"])
reqs = [l.strip() for l in open(f"{LS}/requirements.txt") if l.strip() and not l.startswith(("gradio", "#"))]
open("/kaggle/working/reqs.txt", "w").write("\n".join(reqs) + "\n")
run([sys.executable, "-m", "uv", "pip", "install", "--python", PY, "-r", "/kaggle/working/reqs.txt",
     "--index-strategy", "unsafe-best-match"])
run([PY, "-c", "from huggingface_hub import hf_hub_download as d; [d('ByteDance/LatentSync-1.5', f, "
     "local_dir='/kaggle/working/LatentSync/checkpoints') for f in ('latentsync_unet.pt', 'whisper/tiny.pt')]"])
for base in sorted(glob.glob(ENTRADA + "/base*.mp4")):
    print("Probando", base, flush=True)
    codigo, texto = run([PY, "-m", "scripts.inference", "--unet_config_path", "configs/unet/stage2.yaml",
                         "--inference_ckpt_path", "checkpoints/latentsync_unet.pt", "--inference_steps", "20",
                         "--guidance_scale", "1.5", "--enable_deepcache", "--video_path", base,
                         "--audio_path", ENTRADA + "/audio.wav", "--video_out_path", "/kaggle/working/salida.mp4",
                         "--temp_dir", "/kaggle/working/temp"], cwd=LS)
    if codigo == 0 and os.path.exists("/kaggle/working/salida.mp4"):
        print("AVATAR_OK", flush=True)
        break
    print("No sirvió este pedazo (¿no se ve la cara?), se prueba otro", flush=True)
subprocess.run("rm -rf /kaggle/working/LatentSync /kaggle/working/ls_env /kaggle/working/temp", shell=True)
'''


def modo(cfg: dict) -> str:
    m = (cfg.get("avatar", {}).get("modo") or "no").strip().lower()
    return m if m in MODOS else "no"


def _duracion(ruta: Path) -> float:
    import re
    r = subprocess.run([FFMPEG, "-i", str(ruta)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _ff(*args):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *map(str, args)], check=True)


# ---------- 1. Escoger y cortar tu video base ----------

def elegir_video_base(cfg: dict, carpeta: Path) -> Path:
    """Un video de tu carpeta (EL HYAKO 1), sin repetir los últimos que se usaron."""
    a = cfg.get("avatar", {})
    remoto = cfg.get("drive", {}).get("remoto", "drive")
    carpeta_id = a.get("carpeta_videos_id", "1ypNm-QUX-AJ7bhPd27xK_MAgly60Z-MF")
    r = subprocess.run(["rclone", "lsf", f"{remoto}:", "--drive-root-folder-id", carpeta_id, "--files-only"],
                       capture_output=True, text=True, timeout=120)
    videos = [n.strip() for n in r.stdout.splitlines() if n.strip().lower().endswith(VIDEOS)]
    if not videos:
        raise RuntimeError("No encontré videos en tu carpeta de avatar")
    usados = json.loads(HISTORIAL.read_text(encoding="utf-8")) if HISTORIAL.exists() else []
    frescos = [v for v in videos if v not in usados[-max(1, len(videos) // 2):]] or videos
    elegido = random.choice(frescos)
    HISTORIAL.parent.mkdir(parents=True, exist_ok=True)
    HISTORIAL.write_text(json.dumps((usados + [elegido])[-50:], ensure_ascii=False), encoding="utf-8")
    carpeta.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rclone", "copy", f"{remoto}:{elegido}", str(carpeta), "--drive-root-folder-id", carpeta_id],
                   capture_output=True, timeout=1800, check=True)
    logger.info(f"Avatar: video base '{elegido}'")
    return carpeta / elegido


def cortar_bases(video: Path, segundos: float, carpeta: Path, cuantos: int = 3) -> list[Path]:
    """Hasta 3 pedazos del video (25 fps, 720p, sin audio) desde puntos distintos: si en uno
    no se ve bien tu cara, Kaggle prueba el siguiente."""
    total = _duracion(video)
    margen = 1.0
    maximo_inicio = max(0.0, total - segundos - margen)
    inicios = sorted({round(random.uniform(margen if maximo_inicio > margen else 0, maximo_inicio), 1)
                      for _ in range(cuantos)}) if maximo_inicio > 0 else [0.0]
    bases = []
    for k, inicio in enumerate(inicios):
        salida = carpeta / f"base{k}.mp4"
        _ff("-ss", f"{inicio}", "-i", video, "-t", f"{segundos + 0.5:.2f}",
            "-vf", "scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)'", "-r", "25", "-an",
            "-c:v", "libx264", "-crf", "18", salida)
        bases.append(salida)
    return bases


def audio_para_avatar(narracion: Path, m: str, intro: float, cierre: float, carpeta: Path) -> tuple[Path, float]:
    """Audio que dirá el avatar. En 'intro y cierre' solo esos pedazos (menos GPU);
    en los demás modos, toda la narración."""
    salida = carpeta / "audio.wav"
    total = _duracion(narracion)
    if m == "intro y cierre" and total > intro + cierre + 4:
        _ff("-i", narracion, "-filter_complex",
            f"[0:a]atrim=0:{intro},asetpts=PTS-STARTPTS[a];"
            f"anullsrc=r=16000:cl=mono,atrim=0:0.4[s];"
            f"[0:a]atrim={total - cierre}:{total},asetpts=PTS-STARTPTS[b];"
            f"[a][s][b]concat=n=3:v=0:a=1[o]", "-map", "[o]", "-ac", "1", "-ar", "16000", salida)
    else:
        _ff("-i", narracion, "-ac", "1", "-ar", "16000", salida)
    return salida, total


# ---------- 2. Kaggle: mover tu boca con su GPU gratis ----------

_ENTORNO_KAGGLE: dict | None = None


def _entorno_kaggle() -> dict:
    """Kaggle tiene dos tipos de clave: la vieja (usuario + key) y la nueva "Access token".
    Se prueba la que sirva, sin importar en qué secreto la hayas guardado."""
    global _ENTORNO_KAGGLE
    if _ENTORNO_KAGGLE is not None:
        return _ENTORNO_KAGGLE
    base = {k: v for k, v in os.environ.items() if not k.startswith("KAGGLE_")}
    usuario = secreto("KAGGLE_USERNAME")
    claves = [c for c in (secreto("KAGGLE_KEY"), secreto("KAGGLE_API_TOKEN")) if c]
    opciones = []
    for clave in claves:
        opciones.append({**base, "KAGGLE_USERNAME": usuario, "KAGGLE_KEY": clave})  # clave vieja
        opciones.append({**base, "KAGGLE_API_TOKEN": clave, "KAGGLE_USERNAME": usuario})  # token nuevo
    errores = []
    for entorno in opciones:
        try:
            r = subprocess.run(["kaggle", "kernels", "list", "--mine"],
                               capture_output=True, text=True, timeout=120, env=entorno)
        except FileNotFoundError:
            raise RuntimeError("no está instalado el programa de Kaggle (pip install kaggle)")
        if r.returncode == 0:
            _ENTORNO_KAGGLE = entorno
            return entorno
        errores.append(((r.stderr or r.stdout).strip().splitlines() or ["?"])[-1][:160])
    if not opciones:
        raise RuntimeError("Faltan los secretos KAGGLE_USERNAME y KAGGLE_KEY")
    raise RuntimeError("Kaggle rechazó las claves: " + " | ".join(dict.fromkeys(errores)))


def _kaggle(*args, timeout=600) -> str:
    r = subprocess.run(["kaggle", *map(str, args)], capture_output=True, text=True, timeout=timeout,
                       env=_entorno_kaggle())
    if r.returncode != 0:
        raise RuntimeError(f"kaggle {args[0]} {args[1]}: {(r.stderr or r.stdout)[-400:]}")
    return r.stdout


def en_kaggle(entrada: Path, salida: Path, espera_max: int = 5400) -> Path:
    usuario = secreto("KAGGLE_USERNAME")
    if not (usuario and (secreto("KAGGLE_KEY") or secreto("KAGGLE_API_TOKEN"))):
        raise RuntimeError("Faltan KAGGLE_USERNAME y KAGGLE_KEY")
    datos_id, kernel_id = f"{usuario}/fabrica-avatar-entrada", f"{usuario}/fabrica-avatar"
    (entrada / "dataset-metadata.json").write_text(json.dumps(
        {"title": "fabrica-avatar-entrada", "id": datos_id, "licenses": [{"name": "CC0-1.0"}]}))
    try:
        _kaggle("datasets", "version", "-p", entrada, "-m", "nuevo video", "--dir-mode", "zip", timeout=1800)
    except RuntimeError:
        _kaggle("datasets", "create", "-p", entrada, "--dir-mode", "zip", timeout=1800)
    for _ in range(60):  # Kaggle tarda un poco en dejar lista la nueva versión
        if "ready" in _kaggle("datasets", "status", datos_id).lower():
            break
        time.sleep(10)
    codigo = entrada.parent / "kernel"
    codigo.mkdir(exist_ok=True)
    (codigo / "avatar.py").write_text(SCRIPT_KAGGLE, encoding="utf-8")
    (codigo / "kernel-metadata.json").write_text(json.dumps({
        "id": kernel_id, "title": "fabrica-avatar", "code_file": "avatar.py", "language": "python",
        "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
        "dataset_sources": [datos_id], "competition_sources": [], "kernel_sources": []}))
    _kaggle("kernels", "push", "-p", codigo)
    logger.info("Avatar: Kaggle está moviendo tu boca (puede tardar 10-30 minutos)...")
    inicio = time.time()
    while time.time() - inicio < espera_max:
        time.sleep(30)
        estado = _kaggle("kernels", "status", kernel_id).lower()
        if "complete" in estado:
            break
        if "error" in estado or "cancel" in estado:
            raise RuntimeError(f"Kaggle terminó con error: {estado.strip()[-200:]}")
    else:
        raise RuntimeError("Kaggle tardó demasiado")
    resultado = entrada.parent / "resultado"
    _kaggle("kernels", "output", kernel_id, "-p", resultado, timeout=1800)
    hecho = resultado / "salida.mp4"
    if not hecho.exists():
        raise RuntimeError("Kaggle no pudo hacer el avatar (¿no se ve tu cara en los pedazos?)")
    shutil.copy(hecho, salida)
    return salida


# ---------- 3. Poner el avatar en el video ----------

def _cubrir(ancho: int, alto: int) -> str:
    return f"scale={ancho}:{alto}:force_original_aspect_ratio=increase,crop={ancho}:{alto},setsar=1"


def componer(video: Path, avatar: Path, m: str, intro: float, cierre: float, salida: Path) -> Path:
    """Pone el avatar (solo su imagen; el audio sigue siendo el del video) según el modo."""
    total = _duracion(video)
    W, H = 1080, 1920
    if m == "intro y cierre":
        fin_intro = min(intro, _duracion(avatar))
        inicio_cierre_av = fin_intro + 0.4
        filtro = (f"[1:v]trim=0:{fin_intro},setpts=PTS-STARTPTS,{_cubrir(W, H)}[a];"
                  f"[1:v]trim=start={inicio_cierre_av},setpts=PTS-STARTPTS+{total - cierre}/TB,{_cubrir(W, H)}[b];"
                  f"[0:v][a]overlay=0:0:enable='between(t,0,{fin_intro})'[v1];"
                  f"[v1][b]overlay=0:0:eof_action=pass:enable='gte(t,{total - cierre})'[v]")
    elif m == "esquina":
        lado = 380
        filtro = (f"[1:v]{_cubrir(lado, lado)},format=rgba,"
                  f"geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
                  f"a='if(lte(hypot(X-{lado / 2},Y-{lado / 2}),{lado / 2 - 4}),255,0)'[a];"
                  f"[0:v][a]overlay=W-w-40:H*0.08:eof_action=pass[v]")
    elif m == "dividida":
        alto = int(H * 0.42)
        filtro = f"[1:v]{_cubrir(W, alto)}[a];[0:v][a]overlay=0:0:eof_action=pass[v]"
    else:  # mixto
        lado = 380
        filtro = (f"[1:v]split=2[c][e];[c]{_cubrir(W, H)}[full];"
                  f"[e]{_cubrir(lado, lado)},format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
                  f"a='if(lte(hypot(X-{lado / 2},Y-{lado / 2}),{lado / 2 - 4}),255,0)'[circ];"
                  f"[0:v][circ]overlay=W-w-40:H*0.08:eof_action=pass:"
                  f"enable='between(t,{intro},{total - cierre})'[v1];"
                  f"[v1][full]overlay=0:0:eof_action=pass:"
                  f"enable='lt(t,{intro})+gte(t,{total - cierre})'[v]")
    _ff("-i", video, "-i", avatar, "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", "-t", f"{total:.3f}", salida)
    return salida


# ---------- Todo junto ----------

def agregar(cfg: dict, video: Path, datos: dict, categoria: str, trabajo: Path, numero: int) -> Path:
    """Devuelve el video con tu avatar, o el mismo video si no se pudo."""
    m = modo(cfg)
    if m == "no":
        return video
    a = cfg.get("avatar", {})
    intro, cierre = float(a.get("intro_segundos", 5)), float(a.get("cierre_segundos", 5))
    narracion = Path(datos.get("audio_narracion") or "")
    try:
        if not narracion.exists():
            raise RuntimeError("no hay narración para el avatar")
        carpeta = trabajo / "avatar"
        entrada = carpeta / "entrada"
        entrada.mkdir(parents=True, exist_ok=True)
        audio, _ = audio_para_avatar(narracion, m, intro, cierre, entrada)
        base = elegir_video_base(cfg, carpeta / "base")
        cortar_bases(base, _duracion(audio), entrada)
        base.unlink(missing_ok=True)  # el video original puede pesar mucho
        hablado = en_kaggle(entrada, carpeta / "avatar.mp4", int(a.get("espera_max_segundos", 5400)))
        guardar(cfg, hablado, categoria, numero)
        datos["avatar_usado"] = m
        return componer(video, hablado, m, intro, cierre, trabajo / "con-avatar.mp4")
    except Exception as e:
        logger.error(f"Avatar: no se pudo ({e}); el video sale sin avatar")
        datos["avatar_usado"] = f"no — {str(e)[:300]}"
        return video


def guardar(cfg: dict, avatar: Path, categoria: str, numero: int):
    """Tus avatares hablando quedan en Drive por categoría: MIS AVATARES/<categoría>."""
    d = cfg.get("drive", {})
    if not shutil.which("rclone"):
        return
    destino = f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}/MIS AVATARES/{categoria}"
    subprocess.run(["rclone", "copyto", str(avatar), f"{destino}/avatar-{numero:03d}.mp4"],
                   capture_output=True, timeout=900)
