"""Música según el tono del video: tus beats o canciones en Google Drive, por ánimo:

    Mi unidad › Fabrica de Videos › musica › epica / tension / alegre / triste / motivacion / neutral

También sirven carpetas por categoría (deportes, finanzas, entretenimiento...). Si no hay
nada que encaje, se usa la música de siempre."""

import random
import shutil
import subprocess
import unicodedata
from pathlib import Path

from loguru import logger

LIBRE = Path(__file__).resolve().parent.parent / "resource" / "musica_libre"
CREDITO = {"texto": ""}  # crédito obligatorio de la última canción elegida (licencias CC BY)
AUDIOS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac")
# palabras del tono → carpeta de música
ANIMOS = {
    "triste": ("triste", "reflexivo", "emotivo", "nostalgico", "melancolico"),
    "tension": ("urgente", "serio", "tenso", "dramatico", "misterio", "alarmante"),
    "epica": ("epico", "intenso", "emocionante", "energico", "competitivo"),
    "alegre": ("alegre", "divertido", "gracioso", "festivo", "optimista"),
    "motivacion": ("motivador", "inspirador", "motivacional"),
    "neutral": ("informativo", "explicativo", "neutral", "curioso"),
}


def _normal(texto: str) -> str:
    return unicodedata.normalize("NFKD", (texto or "").lower()).encode("ascii", "ignore").decode()


def animo_de(tono: str) -> str:
    t = _normal(tono)
    for carpeta, palabras in ANIMOS.items():
        if any(p in t for p in palabras):
            return carpeta
    return "neutral"


def libre(tono: str, destino: Path) -> Path | None:
    """Música libre incluida en la fábrica (resource/musica_libre), con su crédito obligatorio."""
    tsv = LIBRE / "CREDITOS.tsv"
    if not tsv.exists():
        return None
    animo = animo_de(tono)
    filas = [l.split("\t") for l in tsv.read_text(encoding="utf-8").splitlines()
             if l.strip() and not l.startswith("#")]
    filas = [f for f in filas if len(f) >= 3 and (LIBRE / f[0]).exists()]
    if not filas:
        return None
    encajan = [f for f in filas if animo in f[1].split(",")] or filas
    archivo, _, credito = random.choice(encajan)[:3]
    destino.mkdir(parents=True, exist_ok=True)
    local = destino / f"fabrica-{archivo}"
    shutil.copy(LIBRE / archivo, local)
    CREDITO["texto"] = credito.strip()
    logger.info(f"Música libre: {archivo} (tono {tono or '?'} → {animo})")
    return local


def elegir(cfg: dict, tono: str, categoria: str, destino: Path, estilo: str = "") -> Path | None:
    """Una canción de tu carpeta 'musica' que encaje con el tono (o la categoría). En los videos
    de geografía, si tu carpeta no tiene nada, se usa la música libre incluida."""
    CREDITO["texto"] = ""
    elegida = _de_drive(cfg, tono, categoria, destino)
    if elegida is None and estilo == "geografia" and cfg.get("musica", {}).get("libre", True):
        elegida = libre(tono, destino)
    return elegida


def _de_drive(cfg: dict, tono: str, categoria: str, destino: Path) -> Path | None:
    d = cfg.get("drive", {})
    if not cfg.get("musica", {}).get("por_tono", True) or not shutil.which("rclone"):
        return None
    raiz = f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}/{cfg.get('musica', {}).get('carpeta', 'musica')}"
    r = subprocess.run(["rclone", "lsf", raiz, "-R", "--files-only", "--max-depth", "2"],
                       capture_output=True, text=True, timeout=120)
    archivos = [a.strip() for a in r.stdout.splitlines() if a.strip().lower().endswith(AUDIOS)]
    if not archivos:
        return None
    animo = animo_de(tono)
    for carpeta in (animo, _normal(categoria), "general"):
        opciones = [a for a in archivos if _normal(a.split("/")[0]) == carpeta]
        if opciones:
            elegido = random.choice(opciones)
            destino.mkdir(parents=True, exist_ok=True)
            local = destino / f"fabrica-{Path(elegido).name}"
            subprocess.run(["rclone", "copyto", f"{raiz}/{elegido}", str(local)], capture_output=True, timeout=600)
            if local.exists():
                logger.info(f"Música: '{elegido}' (tono {tono or '?'} → {carpeta})")
                return local
    return None
