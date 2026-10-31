"""Fábrica de videos. Ejemplos:

  python -m fabrica                         # usa las perillas de fabrica.toml
  python -m fabrica --cantidad 2 --estilo caricatura
  python -m fabrica --tema "Final de la Copa" --estilo comic --salidas descargar
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


def _historial() -> list[dict]:
    if HISTORIAL.exists():
        return json.loads(HISTORIAL.read_text(encoding="utf-8"))
    return []


def _guardar_historial(entradas: list[dict]):
    HISTORIAL.parent.mkdir(parents=True, exist_ok=True)
    HISTORIAL.write_text(json.dumps(entradas[-500:], ensure_ascii=False, indent=1), encoding="utf-8")


def hacer_video(cfg: dict, tema: dict, opciones_salida: set[str]) -> Path:
    estilo = estilos.obtener(tema["estilo"])
    hoy = datetime.now().strftime("%Y-%m-%d")
    nombre = f"{datetime.now():%H%M}-{_slug(tema['tema'])}"
    trabajo = config.RAIZ / "storage" / "fabrica" / nombre
    logger.info(f"=== {tema['tema']} | {tema['categoria']} | estilo {estilo.nombre} ===")

    datos = guion.escribir(cfg, tema, estilo)
    aspecto = cfg.get("video", {}).get("aspecto", "9:16")
    fotos, creditos = [], []
    if "stock_video" not in estilo.fuentes:
        fotos, creditos = imagenes.para_escenas(cfg, datos["escenas"], estilo, aspecto, trabajo / "imagenes")

    crudo = video.armar(cfg, datos, estilo, fotos, trabajo)
    final = video.poner_logo(cfg, crudo, trabajo / f"{nombre}.mp4")
    mini = video.miniatura(final, trabajo / f"{nombre}.jpg")
    ficha = salidas.ficha_texto(datos, tema, creditos)

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
    entradas.append({"fecha": datetime.now().isoformat(timespec="minutes"), "tema": tema["tema"],
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
        temas = [{"tema": args.tema, "categoria": args.categoria or "general",
                  "estilo": estilo if estilo != estilos.ESTILO_AUTOMATICO else "caricatura",
                  "por_que": "elegido a mano",
                  "fuentes": tendencias.buscar_noticias(args.tema)}]
    else:
        candidatos = tendencias.recolectar(cfg)
        if not candidatos:
            logger.error("No se pudieron leer las tendencias (¿sin internet?)")
            return 1
        recientes = [e["tema"] for e in _historial()]
        temas = tendencias.elegir_temas(cfg, candidatos, cantidad, recientes, estilo)

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
    p.add_argument("--tema", help="hacer un video de este tema en vez de buscar tendencias")
    p.add_argument("--categoria", help="categoría del tema manual")
    p.add_argument("--salidas", help="combinación de: descargar,drive,publicar")
    p.add_argument("--voz", choices=["hombre", "mujer"], help="voz de Edge (por defecto hombre)")
    p.add_argument("--clonar-voz", choices=["si", "no"], help="convertir la voz a tu voz (StudioVoz)")
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
        return cfg

    cfg = cargar_cfg()
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
