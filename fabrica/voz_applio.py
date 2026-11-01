"""Clonación de voz con el mismo motor que usa tu cuaderno StudioVoz (Applio).

Toma el modelo que entrenaste en Colab directo de tu Google Drive
(Mi unidad › StudioVoz › modelos › <modelo> › respaldo) y convierte la voz
de Edge a tu voz. Funciona sin tarjeta gráfica (más lento), así que corre en
GitHub y en tu PC. La primera vez instala el motor (~10 min) y luego queda
guardado."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from loguru import logger

from fabrica.config import RAIZ

APPLIO = RAIZ / ".applio"
MODELOS = RAIZ / ".applio_modelos"
MARCA_OK = APPLIO / ".fabrica_ok"


def _python_applio() -> Path:
    if os.name == "nt":
        return APPLIO / ".venv" / "Scripts" / "python.exe"
    return APPLIO / ".venv" / "bin" / "python"


def _correr(cmd: list, cwd: Path | None = None, timeout: int = 3600):
    logger.info("Applio: " + " ".join(str(c) for c in cmd[:6]) + (" ..." if len(cmd) > 6 else ""))
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "MPLBACKEND": "Agg"}
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env, timeout=timeout,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    salida = (r.stdout or "") + (r.stderr or "")
    # core.py de Applio a veces termina con código 0 aunque falle
    if r.returncode != 0 or "Traceback (most recent call last)" in salida:
        raise RuntimeError(f"Applio falló: {salida[-1500:]}")
    return salida


def instalar():
    """Instala solo el motor de Applio (sin la interfaz web), con PyTorch para CPU."""
    if MARCA_OK.exists() and _python_applio().exists():
        return
    logger.info("Applio: instalando el motor por primera vez (unos 10 minutos)...")
    if not (APPLIO / "core.py").exists():
        shutil.rmtree(APPLIO, ignore_errors=True)
        _correr(["git", "clone", "--depth", "1", "https://github.com/IAHispano/Applio", APPLIO])
    _correr([sys.executable, "-m", "pip", "install", "-q", "uv"])
    uv = [sys.executable, "-m", "uv"]
    venv = APPLIO / ".venv"
    shutil.rmtree(venv, ignore_errors=True)
    _correr(uv + ["venv", venv, "--python", "3.12"], cwd=APPLIO)
    req = "requirements-engine.txt" if (APPLIO / "requirements-engine.txt").exists() else "requirements.txt"
    _correr(uv + ["pip", "install", "--python", _python_applio(), "-r", req, "python-ffmpeg",
                  "--extra-index-url", "https://download.pytorch.org/whl/cpu",
                  "--index-strategy", "unsafe-best-match"], cwd=APPLIO, timeout=3600)
    _correr([_python_applio(), "core.py", "prerequisites", "--no-pretraineds-hifigan",
             "--models", "--no-exe"], cwd=APPLIO)
    MARCA_OK.write_text("ok")


def _archivos_modelo(carpeta: Path) -> tuple[Path | None, Path | None]:
    def ultimo(patron):
        hallados = [p for p in carpeta.glob(patron) if not p.name.startswith(("G_", "D_"))]
        return max(hallados, key=lambda p: p.stat().st_mtime) if hallados else None
    return ultimo("*.pth"), ultimo("*.index")


EXTRAER = r"""
import json, sys, torch
sys.path.insert(0, ".")
from rvc.train.process.extract_model import extract_model
from rvc.train.utils import HParams
g, config, salida, nombre = sys.argv[1:5]
hps = HParams(**json.load(open(config, encoding="utf-8")))
ckpt = torch.load(g, map_location="cpu", weights_only=False)
pesos = ckpt.get("model", ckpt)
vocoder = getattr(hps.model, "vocoder", None) or "HiFi-GAN"
extract_model(ckpt=pesos, sr=hps.data.sample_rate, name=nombre, model_path=salida,
              epoch=ckpt.get("iteration", 0), step=0, hps=hps, vocoder=vocoder)
print("ok")
"""


def extraer_de_entrenamiento(carpeta: Path) -> Path | None:
    """Si el entrenamiento se cortó antes de guardar el modelo final, lo saca del
    checkpoint G_*.pth (es lo mismo que hace Applio al terminar)."""
    gs = sorted(carpeta.rglob("G_*.pth"), key=lambda p: p.stat().st_mtime)
    configs = list(carpeta.rglob("config.json"))
    if not gs or not configs:
        return None
    instalar()
    nombre = gs[-1].parent.name if gs[-1].parent != carpeta else "mi_voz"
    salida = gs[-1].parent / f"{nombre}_desde_checkpoint.pth"
    script = APPLIO / "fabrica_extraer.py"
    script.write_text(EXTRAER, encoding="utf-8")
    logger.info("Applio: el modelo final no existe; se saca del último checkpoint de entrenamiento")
    _correr([_python_applio(), script.name, gs[-1].resolve(), configs[0].resolve(), salida.resolve(), nombre],
            cwd=APPLIO, timeout=900)
    return salida if salida.exists() else None


def _archivos_modelo_recursivo(carpeta: Path) -> tuple[Path | None, Path | None]:
    pths = [p for p in carpeta.rglob("*.pth") if not p.name.startswith(("G_", "D_"))]
    idxs = list(carpeta.rglob("*.index"))
    ultimo = lambda lista: max(lista, key=lambda p: p.stat().st_mtime) if lista else None
    return ultimo(pths), ultimo(idxs)


def traer_modelo(cfg: dict) -> tuple[Path, Path | None]:
    """Busca el modelo en la carpeta local; si no está, lo baja de tu Drive con rclone."""
    v = cfg.get("voz", {})
    nombre = v.get("modelo", "mi_voz")
    if v.get("link_modelo"):
        local = MODELOS / "_desde_link"
        pth, idx = _archivos_modelo_recursivo(local)
        if not pth:
            from fabrica import descargas
            logger.info("Applio: bajando tu modelo de voz desde el link...")
            # Solo el modelo final (.pth y .index); los G_/D_ de entrenamiento no hacen falta.
            remoto = cfg.get("drive", {}).get("remoto", "drive")
            descargas.bajar_con_rclone(v["link_modelo"], local, ["- G_*", "- D_*", "+ *.pth", "+ *.index",
                                                                 "+ */", "- *"], remoto)
            pth, idx = _archivos_modelo_recursivo(local)
        if not pth:
            descargas.bajar(v["link_modelo"], local, saltar=lambda n: n.startswith(("G_", "D_"))
                            or not n.lower().endswith((".pth", ".index", ".zip")))
            pth, idx = _archivos_modelo_recursivo(local)
        if not pth:
            # Entrenamiento sin terminar: solo hay G_/D_. Se baja el G_ y su config para sacar el modelo.
            descargas.bajar_con_rclone(v["link_modelo"], local, ["+ G_*.pth", "+ config.json",
                                                                 "+ model_info.json", "+ */", "- *"], remoto)
            extraido = extraer_de_entrenamiento(local)
            if extraido:
                pth, idx = extraido, _archivos_modelo_recursivo(local)[1]
        if pth:
            return pth, idx
        raise RuntimeError("En el link del modelo no encontré ningún archivo .pth (que no empiece con G_ o D_). "
                           "Revisa que la carpeta 'respaldo' tenga el modelo guardado.")
    local = MODELOS / nombre
    pth, idx = _archivos_modelo(local)
    if pth and not v.get("actualizar_modelo_siempre", True):
        return pth, idx
    if shutil.which("rclone"):
        remoto = cfg.get("drive", {}).get("remoto", "drive")
        origen = f"{remoto}:{v.get('carpeta_modelos_drive', 'StudioVoz/modelos')}/{nombre}/respaldo"
        local.mkdir(parents=True, exist_ok=True)
        try:
            # Solo el modelo final (.pth y .index); los G_/D_ de entrenamiento pesan mucho.
            subprocess.run(["rclone", "copy", origen, str(local), "--filter", "- G_*", "--filter", "- D_*",
                            "--filter", "+ *.pth", "--filter", "+ *.index", "--filter", "- *"], check=True, timeout=1200)
        except Exception as e:
            logger.warning(f"Applio: no se pudo bajar el modelo de Drive ({e})")
        pth, idx = _archivos_modelo(local)
    if not pth:
        raise RuntimeError(
            f"No encontré el modelo de voz '{nombre}'. Entrénalo con StudioVoz (botón 2) o copia "
            f"su .pth y .index a {local}")
    return pth, idx


def convertir(cfg: dict, entrada: Path, salida: Path) -> Path:
    v = cfg.get("voz", {})
    instalar()
    pth, idx = traer_modelo(cfg)
    logger.info(f"Applio: cambiando voz con {pth.name}" + ("" if idx else " (sin .index)"))
    _correr([_python_applio(), "core.py", "infer",
             "--input-path", entrada.resolve(), "--output-path", salida.resolve(),
             "--pth-path", pth.resolve(), "--index-path", idx.resolve() if idx else "",
             "--pitch", int(v.get("tono", 0)),
             "--index-rate", float(v.get("parecido", 0.5)) if idx else 0,
             "--protect", float(v.get("proteger_consonantes", 0.33)),
             "--f0-method", v.get("metodo_tono", "rmvpe"),
             "--export-format", "WAV", "--embedder-model", "contentvec"],
            cwd=APPLIO, timeout=int(v.get("tiempo_max_clonar", 1800)))
    return salida
