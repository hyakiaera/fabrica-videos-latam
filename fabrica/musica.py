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


CANCIONES_MPT = Path(__file__).resolve().parent.parent / "resource" / "songs"  # NO se usan: licencia desconocida
# (una de ellas, "Relaxing Peaceful Piano" de Praded, tiene reclamo de derechos en YouTube)

# Biblioteca libre extra: Kevin MacLeod (incompetech.com), licencia CC BY 4.0 → se puede monetizar
# poniendo el crédito (se agrega solo). Se baja una vez en GitHub y se guarda.
CATALOGO_LIBRE = [
    ("Fluffing a Duck", "alegre"), ("Sneaky Snitch", "alegre"), ("Monkeys Spinning Monkeys", "alegre"),
    ("Hyperfun", "alegre"), ("Carefree", "alegre"), ("Investigations", "tension"), ("Hitman", "tension"),
    ("Cipher", "tension"), ("Volatile Reaction", "epica"), ("Heroic Age", "epica"), ("Inspired", "motivacion"),
    ("Wallpaper", "neutral"), ("Easy Lemon", "neutral"), ("Thinking Music", "neutral"),
    ("Local Forecast - Elevator", "neutral"), ("Dreamer", "triste"), ("Long Note Two", "triste"),
]
EXTRA = Path(__file__).resolve().parent.parent / "storage" / "musica_libre"
URL_INCOMPETECH = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/{}.mp3"


def _credito_macleod(titulo: str) -> str:
    return (f"Música: «{titulo}» de Kevin MacLeod (incompetech.com), licencia CC BY 4.0: "
            "https://creativecommons.org/licenses/by/4.0/")


def biblioteca_extra() -> list[tuple[Path, list[str], str]]:
    """Las canciones libres extra (las baja la primera vez; si no se puede, no pasa nada)."""
    import requests
    from urllib.parse import quote
    EXTRA.mkdir(parents=True, exist_ok=True)
    salida = []
    for titulo, animo in CATALOGO_LIBRE:
        archivo = EXTRA / f"{titulo}.mp3"
        if not archivo.exists():
            try:
                r = requests.get(URL_INCOMPETECH.format(quote(titulo)), timeout=60,
                                 headers={"User-Agent": "FabricaVideos/1.0"})
                if r.ok and r.headers.get("content-type", "").startswith(("audio", "application/octet")) \
                        and len(r.content) > 200_000:
                    archivo.write_bytes(r.content)
            except Exception:
                pass
        if archivo.exists():
            salida.append((archivo, [animo], _credito_macleod(titulo)))
    return salida


def _recientes(cuantas: int = 4) -> list[str]:
    """Las últimas canciones usadas (del historial), para no repetirlas seguido."""
    try:
        import json
        from fabrica.config import RAIZ
        ruta = RAIZ / "estado" / "historial.json"
        entradas = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []
        return [e.get("musica", "") for e in entradas[-cuantas:] if e.get("musica")]
    except Exception:
        return []


def variada(tono: str, destino: Path) -> Path | None:
    """De la biblioteca fija y LIBRE (Kevin MacLeod, CC BY: se puede monetizar con el crédito),
    una canción que NO haya sonado en los últimos videos. Nunca se genera música nueva."""
    recientes = set(_recientes())
    libres = []
    tsv = LIBRE / "CREDITOS.tsv"
    if tsv.exists():
        for l in tsv.read_text(encoding="utf-8").splitlines():
            f = l.split("\t")
            if l.strip() and not l.startswith("#") and len(f) >= 3 and (LIBRE / f[0]).exists():
                libres.append((LIBRE / f[0], f[1].split(","), f[2].strip()))
    try:
        libres += biblioteca_extra()
    except Exception:
        pass
    # Solo música con licencia comprobada (nunca las canciones del programa base).
    todas = [c for c in libres if c[0].name not in recientes] or libres
    if not todas:
        return None
    animo = animo_de(tono)
    # Las libres que encajan con el tono tienen un poco más de chance, sin dejar de variar.
    pesos = [3 if animo in c[1] else 1 for c in todas]
    ruta, _, credito = random.choices(todas, weights=pesos, k=1)[0]
    destino.mkdir(parents=True, exist_ok=True)
    local = destino / f"fabrica-{ruta.name}"
    shutil.copy(ruta, local)
    CREDITO["texto"] = credito
    logger.info(f"Música: {ruta.name} (variada; sin repetir las últimas {len(recientes)})")
    return local


def elegir(cfg: dict, tono: str, categoria: str, destino: Path, estilo: str = "") -> Path | None:
    """Una canción de tu carpeta 'musica' que encaje con el tono (o la categoría). Si tu carpeta
    no tiene nada, una de la biblioteca fija gratis, distinta a las últimas que sonaron."""
    CREDITO["texto"] = ""
    elegida = _de_drive(cfg, tono, categoria, destino)
    if elegida is None and cfg.get("musica", {}).get("libre", True):
        elegida = variada(tono, destino)
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
