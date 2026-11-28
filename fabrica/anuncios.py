"""Un anuncio vertical al día para tu mueblería.

En tu Drive:  Fabrica de Videos › muebleria anuncios ›
    promociones.txt   (o cualquier .txt) con tus promociones numeradas, y si quieres los datos
                      del negocio arriba:
                          nombre: Mueblería ...
                          telefono: (713) 000-0000
                          horario: lunes a sábado 10am a 7pm
                          1. 20% de descuento en salas nuevas este fin de semana
                          2. Recámaras usadas desde $299
    fotos/            tus fotos y videos de muebles, y tu LOGO (un archivo con "logo" en el nombre)

Cada día toma la primera promoción sin ✔, hace el anuncio y la tacha. Si no queda ninguna,
hace un anuncio automático (muebles nuevos y usados) con tus fotos, sin inventar precios.

El anuncio: guion súper llamativo de ofertas, tus fotos y videos (sin audio), tu logo grande al
inicio y al final, y la dirección escrita en TODO el video.
"""
import random
import re
import shutil
import subprocess
from pathlib import Path

from loguru import logger

from fabrica import horizontal, ia

CARPETA = "muebleria anuncios"
FOTOS = "fotos"
DIRECCION = "14109 S Post Oak Rd, Houston, TX 77045"
DATO = re.compile(r"^\s*(nombre|negocio|tel[eé]fono|telefono|whatsapp|direcci[oó]n|horario|web|facebook|instagram)\s*:\s*(.+)$", re.I)
_RAIZ: dict = {}


def _remoto(cfg: dict) -> str | None:
    """La carpeta de la mueblería en tu Drive (sin importar MAYÚSCULAS ni acentos)."""
    if not shutil.which("rclone"):
        return None
    d = cfg.get("drive", {})
    base = f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}"
    if base in _RAIZ:
        return _RAIZ[base]
    encontrada = None
    for donde in (base, f"{d.get('remoto', 'drive')}:"):  # dentro de Fabrica de Videos, o en Mi unidad
        try:
            r = subprocess.run(["rclone", "lsf", donde, "--dirs-only"], capture_output=True, text=True, timeout=120)
            for nombre in r.stdout.splitlines():
                nombre = nombre.rstrip("/")
                if horizontal._igual(nombre, CARPETA):
                    encontrada = f"{donde.rstrip('/')}/{nombre}" if not donde.endswith(":") else f"{donde}{nombre}"
                    break
        except Exception:
            pass
        if encontrada:
            break
    _RAIZ[base] = encontrada or f"{base}/{CARPETA}"
    return _RAIZ[base]


def _archivos(remoto: str) -> list[str]:
    try:
        r = subprocess.run(["rclone", "lsf", remoto, "--files-only"], capture_output=True, text=True, timeout=120)
        return r.stdout.splitlines()
    except Exception:
        return []


def _carpeta_fotos(remoto: str) -> str:
    try:
        r = subprocess.run(["rclone", "lsf", remoto, "--dirs-only"], capture_output=True, text=True, timeout=120)
        for nombre in r.stdout.splitlines():
            if horizontal._igual(nombre.rstrip("/"), FOTOS):
                return nombre.rstrip("/")
    except Exception:
        pass
    return FOTOS


def leer(texto: str) -> tuple[dict, list[dict]]:
    """(datos del negocio, promociones). Las líneas "nombre: ..." son datos, no promociones."""
    negocio, lineas_datos = {}, set()
    for k, linea in enumerate(texto.splitlines()):
        m = DATO.match(linea)
        if m and not re.match(r"^\s*\d", linea):
            clave = m.group(1).lower()
            clave = {"negocio": "nombre", "teléfono": "telefono", "dirección": "direccion",
                     "direccion": "direccion"}.get(clave, clave)
            negocio[clave] = m.group(2).strip()
            lineas_datos.add(k)
    promos = [p for p in horizontal.leer(texto) if p["linea"] not in lineas_datos]
    return negocio, promos


def promo_automatica(cfg: dict, negocio: dict, recientes: list[str]) -> str:
    sistema = "Eres publicista de una mueblería latina en Houston. Respondes SOLO JSON."
    usuario = ("Propón UNA idea de anuncio corto y llamativo para una mueblería de muebles NUEVOS y USADOS "
               "(salas, recámaras, comedores, colchones). Sin inventar precios ni porcentajes: usa ganchos como "
               "'llegó mercancía nueva', 'muebles usados como nuevos', 'aparta el tuyo', 'precios que no vas a "
               "creer, ven a verlos'. Distinta a estas recientes: " + ("; ".join(recientes[-15:]) or "ninguna")
               + '\nDevuelve {"promocion": "la idea en una frase"}')
    try:
        return str(ia.pedir_json(cfg, sistema, usuario, temperatura=0.9).get("promocion", "")).strip()
    except Exception:
        return random.choice(["Llegó mercancía nueva: salas, recámaras y comedores",
                              "Muebles usados como nuevos a precios que no vas a creer",
                              "Renueva tu casa este fin de semana: ven a ver lo nuevo"])


def preparar_cfg(cfg: dict) -> dict:
    """Ajustes del anuncio: vertical, ~35-45 s, sin la marca de DESVERGUE (va el logo de la mueblería)."""
    import copy
    a = cfg.get("anuncios", {})
    nuevo = copy.deepcopy(cfg)
    nuevo.setdefault("video", {})["aspecto"] = "9:16"
    nuevo.setdefault("guion", {})["duracion_segundos"] = int(a.get("duracion_segundos", 40))
    lg = nuevo.setdefault("logo", {})
    lg["activo"] = False          # sin la marquita DESVERGUEOFFICIAL
    lg["cierre_activo"] = False   # el cierre lo hace el logo de la mueblería
    nuevo.setdefault("avatar", {})["modo"] = "no"
    nuevo.setdefault("imagenes", {})["max_imagenes"] = int(a.get("max_imagenes", 12))
    return nuevo


def tema_del_dia(cfg: dict, historial: list[dict], trabajo: Path) -> dict:
    trabajo.mkdir(parents=True, exist_ok=True)
    remoto = _remoto(cfg)
    texto, archivo_txt = "", ""
    if remoto:
        txts = [f for f in _archivos(remoto) if f.lower().endswith(".txt")]
        if txts:
            archivo_txt = txts[0]
            subprocess.run(["rclone", "copyto", f"{remoto}/{archivo_txt}", str(trabajo / "promos.txt")],
                           capture_output=True, timeout=120)
            if (trabajo / "promos.txt").exists():
                texto = (trabajo / "promos.txt").read_text(encoding="utf-8", errors="ignore")
    negocio, promos = leer(texto)
    elegida = horizontal.siguiente(promos)
    recientes = [e.get("tema", "") for e in historial if e.get("mezcla") == "anuncio"]
    promo = elegida["tema"] if elegida else promo_automatica(cfg, negocio, recientes)
    direccion = negocio.get("direccion") or cfg.get("anuncios", {}).get("direccion", DIRECCION)
    nombre = negocio.get("nombre") or cfg.get("anuncios", {}).get("nombre", "")
    datos = [f"Dirección: {direccion}"] + [f"{k}: {v}" for k, v in negocio.items() if k not in ("direccion",)]
    tema = {
        "tema": f"Anuncio {nombre or 'mueblería'}: {promo}", "categoria": "anuncio", "estilo": "realista",
        "es_negocio": True, "prioridad_fotos_propias": True, "mezcla": "anuncio",
        "indicaciones": (f"Anuncio vertical SÚPER llamativo para la mueblería{(' ' + nombre) if nombre else ''} "
                         f"(muebles nuevos y usados) en Houston. Promoción de hoy: {promo}. Tono de oferta, "
                         "urgencia amable y alegría; frases cortas; llamado a visitar la tienda HOY. Datos del "
                         f"negocio: {'; '.join(datos)}. Usa SOLO precios o descuentos que estén en la promoción."),
        "obligatorio": f"Decir la dirección: {direccion}" + (f". Nombre: {nombre}" if nombre else ""),
        "formato": "anuncio",
        "anuncio": {"direccion": direccion, "nombre": nombre, "telefono": negocio.get("telefono", "")},
        "_lista": elegida, "_texto_lista": texto, "_archivo_lista": archivo_txt, "fuentes": [],
    }
    if remoto:
        tema["carpetas_fotos"] = [_carpeta_fotos(remoto)]
        tema["raiz_fotos"] = remoto
    logger.info(f"Anuncio del día: {promo}" + ("" if elegida else " (automático: no había promociones pendientes)"))
    return tema


def tachar(cfg: dict, tema: dict, trabajo: Path) -> None:
    """Tacha la promoción hecha en tu .txt (las automáticas no se anotan)."""
    remoto = _remoto(cfg)
    if not (remoto and tema.get("_lista") and tema.get("_archivo_lista")):
        return
    nuevo = horizontal.marcar(tema.get("_texto_lista", ""), tema["_lista"])
    (trabajo / "promos.txt").write_text(nuevo, encoding="utf-8")
    subprocess.run(["rclone", "copyto", str(trabajo / "promos.txt"), f"{remoto}/{tema['_archivo_lista']}"],
                   capture_output=True, timeout=120)
    logger.info("Anuncio: promoción tachada en tu lista")


def logo_de(fotos_propias: dict) -> Path | None:
    """Tu logo: la imagen de la carpeta 'fotos' que tenga 'logo' en el nombre (mejor si es PNG)."""
    logos = [Path(r) for nombre, (r, _) in fotos_propias.items() if "logo" in nombre.lower()
             and Path(r).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")]
    logos.sort(key=lambda p: p.suffix.lower() != ".png")
    return logos[0] if logos else None


def franja(texto: str, ancho: int, salida: Path) -> Path:
    """La dirección en una franja (con ícono de ubicación) para que se vea en todo el video."""
    from PIL import Image, ImageDraw, ImageFont
    from fabrica.config import RAIZ
    letra = ImageFont.truetype(str(RAIZ / "resource" / "fonts" / "Montserrat-ExtraBold.ttf"), 40)
    medida = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), texto, font=letra)
    while medida[2] - medida[0] > ancho - 160 and letra.size > 22:
        letra = ImageFont.truetype(letra.path, letra.size - 2)
        medida = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), texto, font=letra)
    w, h = medida[2] - medida[0] + 110, medida[3] - medida[1] + 36
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], h // 2, fill=(200, 20, 30, 235))
    cx, cy = 40, h / 2  # pin de ubicación dibujado
    d.ellipse([cx - 14, cy - 18, cx + 14, cy + 8], fill="white")
    d.polygon([(cx - 12, cy + 2), (cx + 12, cy + 2), (cx, cy + 22)], fill="white")
    d.ellipse([cx - 6, cy - 11, cx + 6, cy + 1], fill=(200, 20, 30))
    d.text((70, (h - (medida[3] - medida[1])) / 2 - medida[1]), texto, font=letra, fill="white")
    img.save(salida)
    return salida


def marcar_video(video: Path, salida: Path, direccion: str, logo: Path | None, total: float) -> Path:
    """Tu logo grande al inicio (2.5 s) y al final (3.5 s), y la dirección en todo el video."""
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    ancho, alto = 1080, 1920
    banda = franja(f"{direccion}", ancho, salida.with_name("franja-direccion.png"))
    entradas = [ff, "-y", "-loglevel", "error", "-i", str(video), "-loop", "1", "-t", f"{total:.2f}", "-i", str(banda)]
    filtro = f"[0:v][1:v]overlay=(W-w)/2:H*0.875[v1]"
    final = "[v1]"
    if logo:
        fin = max(0.0, total - 3.5)
        entradas += ["-loop", "1", "-t", f"{total:.2f}", "-i", str(logo)]
        filtro += (f";[2:v]scale={int(ancho * 0.72)}:-1,format=rgba,split=2[la][lb];"
                   f"[la]fade=t=out:st=2.0:d=0.5:alpha=1[logo1];"
                   f"[lb]fade=t=in:st={fin:.2f}:d=0.45:alpha=1[logo2];"
                   f"[v1][logo1]overlay=(W-w)/2:H*0.40-h/2:enable='lt(t,2.5)'[v2];"
                   f"[v2][logo2]overlay=(W-w)/2:H*0.50-h/2:enable='gte(t,{fin:.2f})':shortest=1[v3]")
        final = "[v3]"
    subprocess.run(entradas + ["-filter_complex", filtro, "-map", final, "-map", "0:a?", "-c:v", "libx264",
                               "-preset", "veryfast", "-crf", "20", "-c:a", "copy", "-shortest", str(salida)],
                   check=True, timeout=900)
    return salida
