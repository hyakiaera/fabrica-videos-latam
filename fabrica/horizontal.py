"""Un video horizontal largo al día (~5 minutos, 16:9, para YouTube).

En tu Drive:  Fabrica de Videos › videos horizontales info ›
    temas.txt       un tema por línea, numerado:
                        1. video de ronaldo
                        2. san miguel el salvador | detalles: que diga su fecha de fundación
                        3. hdshdkdhdydhbsysbsb | voz: yo
    1/  3 negocios/  4/   carpetas con tus fotos y videos: la carpeta EMPIEZA con el número
                          del tema (el nombre largo no importa)

Cada día toma el primer tema sin ✔, lo hace y lo tacha:  "✔ 1. video de ronaldo  (hecho 25/11)".
Si no queda ninguno, hace uno automático de información de valor y lo anota al final.

El video: capítulos, avatar al inicio / a la mitad / al final, mapas, gráficas, tus fotos y
videos (sin audio), miniatura horizontal, descripción con capítulos y 3 Shorts sacados de él.
"""
import random
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from loguru import logger

from fabrica import ia

CARPETA = "videos horizontales info"
ARCHIVO = "temas.txt"
MARCA = "✔"
LINEA = re.compile(r"^\s*(?P<hecho>✔|✓|\[x\])?\s*(?P<num>\d+)\s*[.)\-:]?\s*(?P<texto>.+?)\s*$", re.I)


def _remoto(cfg: dict) -> str | None:
    if not shutil.which("rclone"):
        return None
    d = cfg.get("drive", {})
    return f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}/{CARPETA}"


def leer(texto: str) -> list[dict]:
    """Las líneas de temas.txt como temas (las sin número también valen, con número 0)."""
    temas = []
    for k, linea in enumerate(texto.splitlines()):
        if not linea.strip() or linea.strip().startswith("#"):
            continue
        m = LINEA.match(linea)
        hecho = linea.strip().startswith((MARCA, "✓", "[x]"))
        if m:
            numero, cuerpo = int(m.group("num")), m.group("texto")
        else:
            numero, cuerpo = 0, linea.strip().lstrip("✔✓").strip()
        cuerpo = re.sub(r"\s*\((hecho|automático)[^)]*\)\s*$", "", cuerpo)
        partes = [x.strip() for x in cuerpo.split("|")]
        opciones = {}
        for extra in partes[1:]:
            if ":" in extra:
                clave, valor = extra.split(":", 1)
                opciones[clave.strip().lower()] = valor.strip()
        temas.append({"linea": k, "numero": numero, "tema": partes[0], "hecho": hecho, **opciones})
    return temas


def siguiente(temas: list[dict]) -> dict | None:
    return next((t for t in temas if not t["hecho"] and t["tema"]), None)


def marcar(texto: str, tema: dict | None, automatico: str = "") -> str:
    """Tacha la línea hecha con la fecha; un tema automático se agrega al final ya tachado."""
    hoy = datetime.now().strftime("%d/%m")
    lineas = texto.splitlines()
    if tema is not None and 0 <= tema["linea"] < len(lineas):
        lineas[tema["linea"]] = f"{MARCA} {lineas[tema['linea']].strip()}  (hecho {hoy})"
    elif automatico:
        lineas.append(f"{MARCA} (automático {hoy}) {automatico}")
    return "\n".join(lineas).rstrip() + "\n"


def bajar_lista(cfg: dict, destino: Path) -> str:
    remoto = _remoto(cfg)
    archivo = destino / ARCHIVO
    if remoto:
        subprocess.run(["rclone", "copyto", f"{remoto}/{ARCHIVO}", str(archivo)], capture_output=True, timeout=120)
    return archivo.read_text(encoding="utf-8", errors="ignore") if archivo.exists() else ""


def subir_lista(cfg: dict, texto: str, destino: Path) -> None:
    remoto = _remoto(cfg)
    archivo = destino / ARCHIVO
    archivo.write_text(texto, encoding="utf-8")
    if remoto:
        subprocess.run(["rclone", "copyto", str(archivo), f"{remoto}/{ARCHIVO}"], capture_output=True, timeout=120)


def carpeta_del_numero(cfg: dict, numero: int) -> str | None:
    """La carpeta cuyo nombre EMPIEZA con ese número ("4", "04", "4 negocios", "4-ronaldo")."""
    remoto = _remoto(cfg)
    if not remoto or numero <= 0:
        return None
    r = subprocess.run(["rclone", "lsf", remoto, "--dirs-only"], capture_output=True, text=True, timeout=120)
    for nombre in r.stdout.splitlines():
        nombre = nombre.rstrip("/")
        m = re.match(r"^0*(\d+)(\D|$)", nombre)
        if m and int(m.group(1)) == numero:
            return nombre
    return None


def tema_automatico(cfg: dict, recientes: list[str]) -> str:
    """Un tema de información de valor que no pasa de moda, distinto a los ya hechos."""
    sistema = "Eres productor de un canal de YouTube latino de videos documentales de 5 minutos. Respondes SOLO JSON."
    usuario = ("Propón UN tema para un video horizontal de 5 minutos con información valiosa, verificable y "
               "entretenida para público latino: historia, biografías, finanzas personales, ciencia, tecnología "
               "explicada, cómo funciona algo, misterios reales, lugares de Latinoamérica, deportes con historia. "
               "Que tenga gancho y dé ganas de verlo completo.\n"
               f"Ya se hicieron (no repetir): {'; '.join(recientes[-60:]) or 'ninguno'}\n"
               'Devuelve {"tema": "título corto del tema", "por_que": "una frase"}')
    try:
        return str(ia.pedir_json(cfg, sistema, usuario, temperatura=0.9).get("tema", "")).strip()
    except Exception:
        return random.choice(["La historia de la Coca-Cola en Latinoamérica", "Cómo funciona el interés compuesto",
                              "El misterio de las líneas de Nazca", "La vida de Roberto Clemente"])


def preparar_cfg(cfg: dict) -> dict:
    """Ajustes de un video largo horizontal (sin tocar los de los Shorts)."""
    import copy
    h = cfg.get("horizontal", {})
    nuevo = copy.deepcopy(cfg)
    nuevo.setdefault("video", {})["aspecto"] = "16:9"
    nuevo["video"]["tamano_letra"] = int(h.get("tamano_letra", 52))
    nuevo["video"]["altura_subtitulos"] = float(h.get("altura_subtitulos", 84))
    g = nuevo.setdefault("guion", {})
    g["duracion_segundos"] = int(h.get("duracion_segundos", 300))
    g["max_escenas"] = int(h.get("max_escenas", 42))
    g["segundos_por_escena"] = int(h.get("segundos_por_escena", 7))
    g["instrucciones_extra"] = (g.get("instrucciones_extra", "") + "\n" + LARGO).strip()
    nuevo.setdefault("imagenes", {})["max_imagenes"] = int(h.get("max_imagenes", 22))
    a = nuevo.setdefault("avatar", {})
    if h.get("avatar", True):  # tú al inicio, a la mitad y al final ([horizontal] avatar = false lo quita)
        a["modo"] = "tres momentos"
        a["intro_segundos"] = float(h.get("avatar_inicio", 15))
        a["cierre_segundos"] = float(h.get("avatar_cierre", 15))
    lg = nuevo.setdefault("logo", {})
    lg["cierre_altura"] = float(h.get("cierre_altura", 73))   # debajo de la tarjeta, encima de subtítulos
    lg["cierre_ancho"] = float(h.get("cierre_ancho", 0.42))
    # En horizontal la marquita va arriba a la izquierda (la de siempre, más chica), sin tapar tarjetas.
    lg["posicion"] = h.get("posicion_logo", "arriba_izquierda")
    lg["tamano_texto"] = float(h.get("tamano_marquita", 0.17))
    return nuevo


LARGO = """VIDEO LARGO HORIZONTAL (~5 minutos, YouTube): estructura por CAPÍTULOS.
- 0:00-0:15 GANCHO fuerte: la promesa del video y lo más impactante.
- Luego una escena con grafica "tarjeta" titulada "En este video" que lista los capítulos.
- 3 o 4 capítulos; la PRIMERA escena de cada capítulo lleva grafica "tarjeta" con el título del
  capítulo (ej. titulo "Capítulo 2", lineas ["Su infancia en San Salvador"]).
- A la mitad, un mini gancho para que no se vayan ("pero lo más increíble viene ahora...").
- Conclusión con 3 puntos clave (grafica "tarjeta") y cierre con una pregunta para comentar.
- Usa mapas cuando se hable de lugares y gráficas cuando haya cifras.
Agrega al JSON "capitulos": [{"titulo": "...", "escena": número de escena donde empieza}].
DATOS INDISPENSABLES: si una escena muestra algo concreto que necesita su foto REAL (la casa
donde creció, un documento, un lugar exacto), pon en esa escena "dato_clave": true y en
"consultas_foto" 3 búsquedas distintas en español e inglés para encontrar esa foto."""


def capitulos_en_descripcion(datos: dict, duracion: float) -> str:
    """"00:00 Introducción / 01:12 Capítulo 1..." calculado con lo que dura cada escena."""
    escenas = datos.get("escenas") or []
    capitulos = datos.get("capitulos") or []
    if not escenas or not capitulos or duracion <= 0:
        return ""
    pesos = [max(1, len(e.get("texto", ""))) for e in escenas]
    total = sum(pesos)
    inicio_escena, acumulado = [], 0.0
    for p in pesos:
        inicio_escena.append(acumulado)
        acumulado += duracion * p / total
    lineas = ["00:00 Introducción"]
    for c in capitulos:
        try:
            k = int(c.get("escena", 0))
        except (TypeError, ValueError):
            continue
        if 0 < k < len(escenas):
            t = int(inicio_escena[k])
            lineas.append(f"{t // 60:02d}:{t % 60:02d} {str(c.get('titulo', '')).strip()[:60]}")
    return "\n".join(lineas) if len(lineas) >= 3 else ""


def shorts_del_largo(video: Path, datos: dict, carpeta: Path, cuantos: int = 3, segundos: float = 45) -> list[Path]:
    """Corta 3 Shorts verticales del video largo (sus mejores partes: el gancho y el inicio de
    capítulos), con fondo difuminado y el título arriba. Llevan gente al video largo."""
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    r = subprocess.run([ff, "-i", str(video)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    total = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0
    if total < segundos * 2:
        return []
    inicios = [0.0]
    desc = capitulos_en_descripcion(datos, total)
    for linea in desc.splitlines()[1:]:
        mm, ss = linea[:5].split(":")
        inicios.append(int(mm) * 60 + int(ss))
    inicios = [t for t in inicios if t + segundos <= total - 5][:cuantos]
    while len(inicios) < cuantos and total > segundos * (len(inicios) + 1):
        inicios.append(total * len(inicios) / (cuantos + 1))
    carpeta.mkdir(parents=True, exist_ok=True)
    salidas = []
    for k, inicio in enumerate(inicios[:cuantos], 1):
        salida = carpeta / f"short-{k}.mp4"
        filtro = ("[0:v]split=2[a][b];"
                  "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5,eq=brightness=-0.15[fondo];"
                  "[b]scale=1080:-2[frente];[fondo][frente]overlay=0:(H-h)/2[v]")
        try:
            subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{inicio:.2f}", "-i", str(video),
                            "-t", f"{segundos:.2f}", "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac",
                            str(salida)], check=True, timeout=900)
            salidas.append(salida)
        except Exception as e:
            logger.warning(f"Short {k} del video largo: no se pudo ({e})")
    if salidas:
        logger.info(f"Video largo: {len(salidas)} Shorts sacados")
    return salidas


def tema_del_dia(cfg: dict, historial: list[dict], trabajo: Path) -> dict:
    """El tema de hoy: el siguiente de tu lista (con su carpeta) o uno automático."""
    trabajo.mkdir(parents=True, exist_ok=True)
    texto = bajar_lista(cfg, trabajo)
    temas = leer(texto)
    elegido = siguiente(temas)
    recientes = [e.get("tema", "") for e in historial] + [t["tema"] for t in temas]
    if elegido:
        tema = {"tema": elegido["tema"], "categoria": "documental", "por_que": "de tu lista de videos horizontales",
                "numero_lista": elegido["numero"], "_lista": elegido, "_texto_lista": texto}
        if elegido.get("detalles"):
            tema["obligatorio"] = elegido["detalles"]
        if elegido.get("voz"):
            tema["voz"] = elegido["voz"]
        carpeta = carpeta_del_numero(cfg, elegido["numero"])
        if carpeta:
            tema["carpetas_fotos"] = [carpeta]
            tema["raiz_fotos"] = _remoto(cfg)
            logger.info(f"Video horizontal: tema #{elegido['numero']} con tu carpeta '{carpeta}'")
        else:
            logger.info(f"Video horizontal: tema #{elegido['numero']} (sin carpeta de fotos)")
    else:
        nombre = tema_automatico(cfg, recientes)
        tema = {"tema": nombre, "categoria": "documental", "por_que": "automático (tu lista estaba vacía)",
                "_texto_lista": texto}
        logger.info(f"Video horizontal: tu lista no tiene temas pendientes; automático: {nombre}")
    try:  # datos reales del tema (Wikipedia/Wikidata), como en geografía
        from fabrica import ficha
        tema["ficha"] = ficha.datos(tema["tema"])
    except Exception:
        pass
    tema.setdefault("fuentes", [])
    try:
        from fabrica import tendencias
        tema["fuentes"] = tendencias.buscar_noticias(tema["tema"], 6)
    except Exception:
        pass
    tema["estilo"] = random.choice(["cinematografico", "realista", "explicativo", "noticiero"])
    tema["formato"] = "horizontal"
    return tema


def tachar(cfg: dict, tema: dict, trabajo: Path) -> None:
    texto = tema.get("_texto_lista", "")
    nuevo = marcar(texto, tema.get("_lista"), automatico="" if tema.get("_lista") else tema["tema"])
    subir_lista(cfg, nuevo, trabajo)
    logger.info("Video horizontal: tema tachado en temas.txt")
