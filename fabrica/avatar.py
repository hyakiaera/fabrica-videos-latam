"""Tu avatar en los videos. Toma un look de tu banco de avatares en Google Drive
(el que creas con el cuaderno StudioAvatar) y lo pone en el video.

Banco en Drive:  Fabrica de Videos/MIS AVATARES/AVATARES 2026/<AVATAR>/02_looks/<ESTILO>/*.png

- Modo "auto": el look depende del TONO del guion. Temas serios → solo looks
  formales; temas chistosos → nunca traje ni casual; neutrales → casual/deportivo...
- Modo manual: siempre el estilo que elijas (ej. "04_FORMAL").
- "no": sin avatar.

Si no hay ningún look permitido para ese tono, el video sale SIN avatar (nunca
se usa un look que no corresponde, por ejemplo urbano en un tema serio)."""

import random
import shutil
import subprocess
from pathlib import Path

from loguru import logger

EXT_IMG = (".png", ".jpg", ".jpeg", ".webp")
TONOS = ("serio", "neutral", "chistoso")

# Qué looks puede usar cada tono (en orden de preferencia). Se cambian en fabrica.toml.
LOOKS_POR_TONO = {
    "serio": ["04_FORMAL", "02_LUXURY"],
    "neutral": ["07_CASUAL", "06_SPORT", "02_LUXURY", "01_STREET", "05_VACACIONES"],
    "chistoso": ["01_STREET", "03_HIPHOP", "05_VACACIONES", "06_SPORT", "08_FUTURISTA"],
}
# El guion trae un tono (triste, serio, divertido...): se agrupa en serio / neutral / chistoso.
TONO_DEL_GUION = {
    "triste": "serio", "reflexivo": "serio", "serio": "serio", "urgente": "serio",
    "divertido": "chistoso", "alegre": "chistoso", "gracioso": "chistoso", "chistoso": "chistoso",
    "inspirador": "neutral", "motivador": "neutral", "epico": "neutral",
}
# "informativo" o sin tono: se decide por la categoría.
TONO_POR_CATEGORIA = {
    "economia": "serio", "mundo": "serio", "politica": "serio", "ciencia": "serio",
    "salud": "serio", "noticias": "serio", "tecnologia": "neutral", "deportes": "neutral",
    "entretenimiento": "chistoso", "virales": "chistoso", "farandula": "chistoso",
}
# Dentro de los looks permitidos, algunos encajan mejor con ciertas categorías.
PREFERIDO_POR_CATEGORIA = {"deportes": "06_SPORT", "economia": "04_FORMAL", "tecnologia": "08_FUTURISTA"}


def modo(cfg: dict) -> str:
    """'no', 'auto' o el nombre de un estilo (modo manual)."""
    a = cfg.get("avatar", {})
    valor = str(a.get("modo", "no")).strip()
    if valor.lower() in ("", "no", "false", "apagado"):
        return "no"
    return "auto" if valor.lower() == "auto" else valor


def _sin_acentos(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().strip().lower()


def tono_de(tema: dict, datos: dict | None = None) -> str:
    """serio, neutral o chistoso: primero según el tono del guion, si no por la categoría."""
    for fuente in ((datos or {}).get("tono"), tema.get("tono")):
        palabra = _sin_acentos(fuente).split(" ")[0] if fuente else ""
        if palabra in TONOS:
            return palabra
        if palabra in TONO_DEL_GUION:
            return TONO_DEL_GUION[palabra]
    return TONO_POR_CATEGORIA.get(_sin_acentos(tema.get("categoria", "")), "neutral")


# ---------------- leer el banco (Drive con rclone, o carpeta local) ----------------
def _rclone_lsf(ruta: str, *extra) -> list[str]:
    r = subprocess.run(["rclone", "lsf", ruta, *extra], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return [l.strip().rstrip("/") for l in r.stdout.splitlines() if l.strip()]


class Banco:
    """Acceso al banco de looks, en tu Drive (rclone) o en una carpeta de tu PC."""

    def __init__(self, cfg: dict):
        a = cfg.get("avatar", {})
        local = str(a.get("carpeta_local", "")).strip()
        self.local = Path(local).expanduser() if local else None
        remoto = cfg.get("drive", {}).get("remoto", "drive")
        self.raiz = f"{remoto}:{a.get('carpeta_drive', 'Fabrica de Videos/MIS AVATARES/AVATARES 2026')}"
        self.nombre = str(a.get("nombre", "")).strip()

    def disponible(self) -> bool:
        if self.local:
            return self.local.is_dir()
        return bool(shutil.which("rclone"))

    def avatares(self) -> list[str]:
        if self.local:
            return sorted(p.name for p in self.local.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
        return sorted(n for n in _rclone_lsf(self.raiz, "--dirs-only") if not n.startswith((".", "_")))

    def elegir_avatar(self) -> str:
        if self.nombre:
            return self.nombre
        todos = self.avatares()
        if not todos:
            raise RuntimeError("no hay ningún avatar en tu carpeta AVATARES 2026")
        return todos[0]

    def estilos(self, avatar: str) -> list[str]:
        if self.local:
            carpeta = self.local / avatar / "02_looks"
            return sorted(p.name for p in carpeta.iterdir() if p.is_dir()) if carpeta.is_dir() else []
        return _rclone_lsf(f"{self.raiz}/{avatar}/02_looks", "--dirs-only")

    def looks(self, avatar: str, estilo: str) -> list[str]:
        if self.local:
            carpeta = self.local / avatar / "02_looks" / estilo
            return sorted(p.name for p in carpeta.iterdir() if p.suffix.lower() in EXT_IMG) if carpeta.is_dir() else []
        return [n for n in _rclone_lsf(f"{self.raiz}/{avatar}/02_looks/{estilo}", "--files-only")
                if n.lower().endswith(EXT_IMG)]

    def traer(self, avatar: str, estilo: str, archivo: str, destino: Path) -> Path:
        destino.mkdir(parents=True, exist_ok=True)
        salida = destino / f"avatar_{estilo}_{archivo}"
        if self.local:
            shutil.copy(self.local / avatar / "02_looks" / estilo / archivo, salida)
        else:
            subprocess.run(["rclone", "copyto", f"{self.raiz}/{avatar}/02_looks/{estilo}/{archivo}", str(salida)],
                           check=True, capture_output=True, timeout=300)
        return salida


def estilos_permitidos(cfg: dict, tema: dict, datos: dict | None = None) -> list[str]:
    """Estilos de look que se pueden usar con este tema, en orden de preferencia."""
    m = modo(cfg)
    if m != "auto":
        return [m]
    tono = tono_de(tema, datos)
    tabla = {**LOOKS_POR_TONO, **cfg.get("avatar", {}).get("looks_por_tono", {})}
    permitidos = list(tabla.get(tono, LOOKS_POR_TONO["neutral"]))
    preferido = PREFERIDO_POR_CATEGORIA.get(str(tema.get("categoria", "")).lower())
    if preferido in permitidos:
        permitidos.remove(preferido)
        permitidos.insert(0, preferido)
    return permitidos


def elegir(cfg: dict, tema: dict, carpeta: Path, datos: dict | None = None) -> Path | None:
    """Baja un look adecuado para el tema. Devuelve None si no hay avatar."""
    m = modo(cfg)
    if m == "no":
        return None
    banco = Banco(cfg)
    if not banco.disponible():
        logger.warning("Avatar: sin acceso a tu Drive (rclone) ni carpeta local; el video sale sin avatar")
        return None
    try:
        avatar = banco.elegir_avatar()
        existentes = set(banco.estilos(avatar))
        permitidos = estilos_permitidos(cfg, tema, datos)
        con_looks = [(e, banco.looks(avatar, e)) for e in permitidos if e in existentes]
        con_looks = [(e, l) for e, l in con_looks if l]
        if not con_looks:
            detalle = f"tono {tono_de(tema, datos)}" if m == "auto" else "modo manual"
            logger.warning(f"Avatar: no hay looks de {', '.join(permitidos)} ({detalle}) en el avatar "
                           f"'{avatar}'; el video sale sin avatar. Créalos con StudioAvatar (botón 2).")
            return None
        # Se prefiere el primer estilo, pero a veces se usa otro permitido para variar.
        estilo, looks = con_looks[0] if random.random() < 0.6 else random.choice(con_looks)
        archivo = random.choice(looks)
        ruta = banco.traer(avatar, estilo, archivo, carpeta)
        logger.info(f"Avatar: {avatar} con look {estilo}/{archivo} "
                    f"({'tono ' + tono_de(tema, datos) if m == 'auto' else 'manual'})")
        return ruta
    except Exception as e:
        logger.warning(f"Avatar: no se pudo traer el look ({e}); el video sale sin avatar")
        return None


# ---------------- ponerlo en el video ----------------
POSICIONES = {  # (x %, y %) de la esquina más cercana; fuera de subtítulos y botones de las apps
    "arriba_derecha": (96, 7),
    "arriba_izquierda": (4, 7),
    "centro_izquierda": (4, 40),
    "abajo_izquierda": (4, 50),
}


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return shutil.which("ffmpeg") or "ffmpeg"


def filtro_esquina(cfg: dict, ancho_video: int) -> str:
    a = cfg.get("avatar", {})
    x, y = POSICIONES.get(a.get("posicion", "arriba_derecha"), POSICIONES["arriba_derecha"])
    ancho = int(ancho_video * float(a.get("tamano", 0.28)))
    borde = max(2, ancho // 60)
    segundos = float(a.get("segundos", 0) or 0)
    expr_x = f"W*{x / 100:.4f}-w" if x >= 67 else f"W*{x / 100:.4f}"
    cuando = f":enable='lte(t,{segundos})'" if segundos > 0 else ""
    return (f"[1:v]scale={ancho}:-2,pad=iw+{borde * 2}:ih+{borde * 2}:{borde}:{borde}:white[av];"
            f"[0:v][av]overlay={expr_x}:H*{y / 100:.4f}:shortest=1{cuando}")


def poner_en_esquina(cfg: dict, video: Path, look: Path, salida: Path) -> Path:
    """Pone tu look como tarjeta en una esquina del video (con borde blanco)."""
    from fabrica.video import ANCHOS
    ancho = ANCHOS.get(cfg.get("video", {}).get("aspecto", "9:16"), 1080)
    comando = [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(video), "-loop", "1", "-i", str(look),
               "-filter_complex", filtro_esquina(cfg, ancho), "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "20", "-c:a", "copy", "-movflags", "+faststart", str(salida)]
    subprocess.run(comando, check=True)
    return salida


def aparicion(cfg: dict) -> str:
    """'esquina' (tarjeta todo el video), 'escenas' (primera y última imagen) o 'ambos'."""
    valor = str(cfg.get("avatar", {}).get("aparicion", "esquina")).lower()
    return valor if valor in ("esquina", "escenas", "ambos") else "esquina"
