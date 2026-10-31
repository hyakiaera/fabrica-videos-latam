"""Fábrica de videos. Ejemplos:

  python -m fabrica                         # usa las perillas de fabrica.toml
  python -m fabrica --cantidad 2 --estilo caricatura
  python -m fabrica --tema "Final de la Copa" --estilo comic --salidas descargar
  python -m fabrica --tema "quiero un video sobre el nuevo estadio del Barcelona, tono divertido"
  python -m fabrica --tema "https://www.youtube.com/watch?v=..."
  python -m fabrica --solo-tendencias       # ver qué temas elegiría, sin hacer videos
  python -m fabrica --repetir-cada 4        # modo PC: trabaja cada 4 horas mientras esté prendida
  python -m fabrica --estilos               # lista los estilos disponibles
  python -m fabrica --probar-logo           # imagen de prueba para acomodar tu logo
  python -m fabrica --voz mujer --clonar-voz si
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from loguru import logger

from fabrica import config, estilos, guion, imagenes, salidas, tendencias, video

HISTORIAL = config.RAIZ / "estado" / "historial.json"
SALIDAS_VALIDAS = {"descargar", "drive", "publicar"}


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")[:60] or "video"


def segundos(duracion: str) -> int:
    """'1' → 60, '1:30' → 90, '2.5' → 150. Entre 30 segundos y 5 minutos."""
    texto = str(duracion).strip().lower().replace("min", "").strip()
    if ":" in texto:
        minutos, seg = texto.split(":", 1)
        total = int(minutos or 0) * 60 + int(seg or 0)
    else:
        total = round(float(texto.replace(",", ".")) * 60)
    return max(30, min(300, total))


def _historial() -> list[dict]:
    if HISTORIAL.exists():
        return json.loads(HISTORIAL.read_text(encoding="utf-8"))
    return []


def _siguiente_numero() -> int:
    """Número consecutivo del video (va al final del nombre: "tema #012")."""
    entradas = _historial()
    return max((e.get("numero", 0) for e in entradas), default=0) + 1 if any(
        "numero" in e for e in entradas) else len(entradas) + 1


def _guardar_historial(entradas: list[dict]):
    HISTORIAL.parent.mkdir(parents=True, exist_ok=True)
    HISTORIAL.write_text(json.dumps(entradas[-500:], ensure_ascii=False, indent=1), encoding="utf-8")


def hacer_video(cfg: dict, tema: dict, opciones_salida: set[str]) -> Path:
    if not estilos.disponible(estilos.obtener(tema["estilo"])):
        logger.warning("El estilo realista necesita PEXELS_API_KEY o PIXABAY_API_KEY; "
                       "se usa cinematografico (imágenes IA gratis)")
        tema["estilo"] = "cinematografico"
    estilo = estilos.obtener(tema["estilo"])
    hoy = datetime.now().strftime("%Y-%m-%d")
    numero = _siguiente_numero()
    nombre = f"{_slug(tema['tema'])} #{numero:03d}"
    trabajo = config.RAIZ / "storage" / "fabrica" / nombre
    logger.info(f"=== {tema['tema']} | {tema['categoria']} | estilo {estilo.nombre} ===")

    fotos_propias = {}
    if tema.get("carpetas_fotos"):
        from fabrica import mis_fotos
        fotos_propias = mis_fotos.preparar(cfg, tema["carpetas_fotos"], trabajo)
    datos = guion.escribir(cfg, tema, estilo, fotos_propias)
    aspecto = cfg.get("video", {}).get("aspecto", "9:16")
    fotos, creditos, conteo = [], [], {}
    if "stock_video" not in estilo.fuentes:
        fotos, creditos, conteo = imagenes.para_escenas(
            cfg, datos["escenas"], estilo, aspecto, trabajo / "imagenes",
            visual_global=datos.get("visual_global", ""), tema=tema["tema"], fotos_propias=fotos_propias)

    crudo = video.armar(cfg, datos, estilo, fotos, trabajo)
    final = video.poner_logo(cfg, crudo, trabajo / f"{nombre}.mp4")
    mini = video.miniatura(final, trabajo / f"{nombre}.jpg")
    ficha = salidas.ficha_texto(datos, tema, creditos, conteo)

    ruta_relativa = f"{hoy}/{_slug(tema['categoria'])}"
    carpeta_dia = Path(cfg.get("salida", {}).get("carpeta", "salida"))
    if not carpeta_dia.is_absolute():
        carpeta_dia = config.RAIZ / carpeta_dia
    carpeta_dia = carpeta_dia / ruta_relativa
    guardado = salidas.guardar_local(carpeta_dia, nombre, final, ficha, mini)

    if "drive" in opciones_salida:
        # Se sube solo este video (y su ficha), no toda la carpeta del día.
        temporal = trabajo / "para-drive"
        temporal.mkdir(exist_ok=True)
        for ext in (".mp4", ".txt", ".jpg"):
            origen = carpeta_dia / f"{nombre}{ext}"
            if origen.exists():
                (temporal / origen.name).write_bytes(origen.read_bytes())
        salidas.subir_drive(cfg, temporal, ruta_relativa)
    if "publicar" in opciones_salida:
        salidas.publicar(cfg, guardado, datos)

    entradas = _historial()
    entradas.append({"numero": numero, "fecha": datetime.now().isoformat(timespec="minutes"), "tema": tema["tema"],
                     "categoria": tema["categoria"], "estilo": tema["estilo"], "titulo": datos["titulo"],
                     "archivo": str(guardado.relative_to(config.RAIZ)) if guardado.is_relative_to(config.RAIZ) else str(guardado)})
    _guardar_historial(entradas)
    return guardado


def una_ronda(cfg: dict, args) -> int:
    f = cfg.get("fabrica", {})
    cantidad = args.cantidad or int(f.get("videos_por_ronda", 2))
    estilo = args.estilo or f.get("estilo", estilos.ESTILO_AUTOMATICO)
    opciones = set(args.salidas.split(",")) if args.salidas else set(f.get("salidas", ["descargar"]))
    opciones = {o.strip() for o in opciones if o.strip()} | {"descargar"}
    if opciones - SALIDAS_VALIDAS:
        raise SystemExit(f"Salidas no válidas: {opciones - SALIDAS_VALIDAS}. Usa: {SALIDAS_VALIDAS}")
    if estilo != estilos.ESTILO_AUTOMATICO:
        estilos.obtener(estilo)

    if args.tema:
        from fabrica import pedidos
        temas = [pedidos.preparar(cfg, args.tema, estilo, args.categoria or "")]
    else:
        candidatos = tendencias.recolectar(cfg)
        if not candidatos:
            logger.error("No se pudieron leer las tendencias (¿sin internet?)")
            return 1
        recientes = [e["tema"] for e in _historial()]
        temas = tendencias.elegir_temas(cfg, candidatos, cantidad, recientes, estilo)

    if args.detalles:
        for t in temas:
            t["obligatorio"] = args.detalles
    for t in temas:
        logger.info(f"Tema elegido: {t['tema']} [{t['categoria']} / {t['estilo']}] — {t['por_que']}")
    if args.solo_tendencias:
        return 0

    fallos = 0
    for tema in temas:
        try:
            hacer_video(cfg, tema, opciones)
        except Exception as e:
            fallos += 1
            logger.exception(f"Falló el video '{tema['tema']}': {e}")
    logger.info(f"Ronda terminada: {len(temas) - fallos} videos listos, {fallos} fallidos")
    return 1 if fallos == len(temas) else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m fabrica", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cantidad", type=int, help="videos por ronda")
    p.add_argument("--estilo", help="auto o uno de: " + ", ".join(estilos.ESTILOS))
    p.add_argument("--tema", help="tema, pedido libre o link (YouTube, TikTok, noticia) en vez de tendencias")
    p.add_argument("--categoria", help="categoría del tema manual")
    p.add_argument("--detalles", help="datos que SÍ tienen que salir o decirse en el video")
    p.add_argument("--salidas", help="combinación de: descargar,drive,publicar")
    p.add_argument("--voz", choices=["hombre", "mujer"], help="voz de Edge (por defecto hombre)")
    p.add_argument("--clonar-voz", choices=["si", "no"], help="convertir la voz a tu voz (StudioVoz)")
    p.add_argument("--texto-marca", help='texto que va como logo si no hay marca/logo.png (ej. "@MiCanal")')
    p.add_argument("--duracion", help="duración: 1, 1:30, 2, 2:30 o 3 (minutos)")
    p.add_argument("--logo-link", help="link a tu logo PNG (Google Drive compartido o directo)")
    p.add_argument("--posicion-logo", help="arriba_izquierda, arriba_centro, arriba_derecha, ...")
    p.add_argument("--modelo-voz-link", help="link a tu modelo de voz (.pth/.index o .zip) o su nombre en StudioVoz")
    p.add_argument("--probar-logo", action="store_true", help="crear imagen de prueba del logo y salir")
    p.add_argument("--solo-tendencias", action="store_true", help="solo mostrar temas elegidos")
    p.add_argument("--repetir-cada", type=float, metavar="HORAS", help="modo PC: repetir cada N horas")
    p.add_argument("--estilos", action="store_true", help="listar estilos y salir")
    p.add_argument("--config", type=Path, help="archivo de perillas (por defecto fabrica.toml)")
    args = p.parse_args(argv)

    if args.estilos:
        for clave, e in estilos.ESTILOS.items():
            print(f"{clave:16} {e.nombre} — {e.descripcion}")
        return 0

    def cargar_cfg():
        cfg = config.cargar(args.config)
        if args.clonar_voz:
            cfg.setdefault("voz", {})["clonar"] = args.clonar_voz == "si"
        if args.voz:
            cfg.setdefault("voz", {})["genero"] = args.voz
        if args.texto_marca:
            cfg.setdefault("logo", {})["texto"] = args.texto_marca
        if args.logo_link:
            cfg.setdefault("logo", {})["link"] = args.logo_link
        if args.posicion_logo:
            cfg.setdefault("logo", {})["posicion"] = args.posicion_logo
        if args.modelo_voz_link:
            # Un link descarga el modelo; un nombre usa ese modelo de StudioVoz en tu Drive.
            clave = "link_modelo" if args.modelo_voz_link.startswith("http") else "modelo"
            cfg.setdefault("voz", {})[clave] = args.modelo_voz_link
            if args.clonar_voz != "no":
                cfg["voz"]["clonar"] = True
        if args.duracion:
            cfg.setdefault("guion", {})["duracion_segundos"] = segundos(args.duracion)
        return cfg

    cfg = cargar_cfg()
    logger.info("Claves encontradas → " + config.resumen_claves())
    video.preparar_logo(cfg)
    if args.probar_logo:
        from fabrica import vista_logo
        ruta = vista_logo.generar(cfg, config.RAIZ / "salida" / "prueba-logo.jpg")
        logger.success(f"Imagen de prueba lista: {ruta}")
        return 0
    while True:
        codigo = una_ronda(cfg, args)
        if not args.repetir_cada:
            return codigo
        logger.info(f"Esperando {args.repetir_cada} horas para la próxima ronda (Ctrl+C para parar)")
        time.sleep(args.repetir_cada * 3600)
        cfg = cargar_cfg()


if __name__ == "__main__":
    sys.exit(main())
