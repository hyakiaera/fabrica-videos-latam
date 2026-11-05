"""Imágenes que se mueven de verdad: las escenas más importantes se convierten en clips
de unos 4 segundos con IA de código abierto (LTX-Video de Lightricks) en Kaggle, con su
GPU gratis. Si algo falla, esas escenas quedan con el movimiento de cámara de siempre.

Tarda bastante (10-25 minutos por video), así que está apagado por defecto:
se prende con la variable ANIMAR = si (o [animar] activo = true)."""

import json
import shutil
from pathlib import Path

from loguru import logger

SCRIPT_KAGGLE = r'''
import glob, json, os, subprocess, sys, time
for _ in range(30):
    encontrados = glob.glob("/kaggle/input/**/escenas.json", recursive=True)
    if encontrados:
        break
    time.sleep(10)
ENTRADA = encontrados[0].rsplit("/", 1)[0]
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "diffusers", "transformers", "accelerate",
                "sentencepiece", "imageio", "imageio-ffmpeg"], check=False)
import torch
from diffusers import LTXImageToVideoPipeline
from diffusers.utils import export_to_video, load_image
escenas = json.load(open(ENTRADA + "/escenas.json"))
tipo = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float32
pipe = LTXImageToVideoPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=tipo)
pipe.enable_model_cpu_offload()
pipe.vae.enable_tiling()
os.makedirs("/kaggle/working/clips", exist_ok=True)
negativo = "worst quality, inconsistent motion, blurry, jittery, distorted, morphing, text, watermark"
for e in escenas:
    try:
        imagen = load_image(f"{ENTRADA}/{e['imagen']}").resize((480, 832))
        frames = pipe(image=imagen, prompt=e["prompt"], negative_prompt=negativo, width=480, height=832,
                      num_frames=97, num_inference_steps=int(e.get("pasos", 30))).frames[0]
        export_to_video(frames, f"/kaggle/working/clips/{e['id']}.mp4", fps=24)
        print("ANIMADA", e["id"], flush=True)
    except Exception as ex:
        print("FALLO", e["id"], ex, flush=True)
'''


def activo(cfg: dict) -> bool:
    import os
    variable = os.environ.get("ANIMAR", "").strip().lower()
    if variable in ("si", "sí", "yes", "true", "1"):
        return True
    if variable in ("no", "false", "0"):
        return False
    return bool(cfg.get("animar", {}).get("activo", False))


def elegir_escenas(escenas: list[dict], imagenes: list, cuantas: int) -> list[int]:
    """La primera escena (el gancho) y otras repartidas, solo con imágenes fijas."""
    validas = [i for i, img in enumerate(imagenes)
               if img and Path(img).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
               and not escenas[i].get("grafica") and "-encuadre" not in Path(img).name]
    if len(validas) <= cuantas:
        return validas
    paso = len(validas) / cuantas
    return [validas[int(k * paso)] for k in range(cuantas)]


def animar(cfg: dict, escenas: list[dict], imagenes: list, trabajo: Path, datos: dict) -> list:
    """Devuelve la lista de imágenes con algunas cambiadas por clips animados."""
    if not activo(cfg):
        return imagenes
    from fabrica import avatar

    a = cfg.get("animar", {})
    elegidas = elegir_escenas(escenas, imagenes, int(a.get("escenas", 3)))
    if not elegidas:
        return imagenes
    entrada = trabajo / "animar" / "entrada"
    entrada.mkdir(parents=True, exist_ok=True)
    lista = []
    for i in elegidas:
        nombre = f"escena{i:02d}{Path(imagenes[i]).suffix.lower()}"
        shutil.copy(imagenes[i], entrada / nombre)
        movimiento = escenas[i].get("movimiento") or "subtle natural motion, gentle camera push in"
        lista.append({"id": f"escena{i:02d}", "imagen": nombre, "pasos": int(a.get("pasos", 30)),
                      "prompt": f"{escenas[i].get('imagen', '')}. {movimiento}. {datos.get('direccion_visual', '')}"})
    (entrada / "escenas.json").write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")
    try:
        logger.info(f"Animar: Kaggle está animando {len(lista)} escenas (10-25 minutos)...")
        resultado = avatar.correr_en_kaggle(entrada, SCRIPT_KAGGLE, "animar", int(a.get("espera_max_segundos", 4500)))
    except Exception as e:
        logger.error(f"Animar: no se pudo ({e}); las escenas quedan con movimiento de cámara")
        datos["animadas"] = f"0 — {str(e)[:200]}"
        return imagenes
    nuevas = list(imagenes)
    hechas = 0
    for i in elegidas:
        clip = resultado / "clips" / f"escena{i:02d}.mp4"
        if clip.exists() and clip.stat().st_size > 20_000:
            destino = trabajo / "animar" / clip.name
            shutil.copy(clip, destino)
            nuevas[i] = destino
            hechas += 1
    datos["animadas"] = str(hechas)
    logger.info(f"Animar: {hechas} escenas animadas")
    return nuevas
