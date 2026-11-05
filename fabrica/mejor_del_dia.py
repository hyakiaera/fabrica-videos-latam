"""El mejor video del día: cada video automático recibe una nota (0 a 100) y, una vez
al día, se publica solo el que sacó la nota más alta. Los demás se quedan en Drive.

La nota junta:
  - lo que opina la IA del gancho: ¿el título y el arranque harían que un latino se
    quede viendo? (hasta 60 puntos)
  - la calidad técnica: imágenes que encajaron, voz que salió bien, avatar (hasta 40)
"""
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from fabrica import ia

SISTEMA = """Eres el editor de un canal de shorts en español para público latino.
Calificas qué tan probable es que un video se haga viral y la gente lo vea completo.
Responde SOLO JSON: {"nota": número del 1 al 10, "por_que": "una frase"}"""


def nota_de_la_ia(cfg: dict, datos: dict, tema: dict) -> float | None:
    guion = (datos.get("guion") or "")[:700]
    usuario = (f"Tema: {tema.get('tema', '')}\nCategoría: {tema.get('categoria', '')}\n"
               f"Título: {datos.get('titulo', '')}\nTexto de la miniatura: {datos.get('titulo_miniatura', '')}\n"
               f"Arranque del guion: {guion}\n\n"
               "Califica del 1 al 10: fuerza del gancho en los primeros 3 segundos, interés del tema "
               "HOY para latinos, claridad y si da ganas de comentar o compartir.")
    try:
        r = ia.pedir_json(cfg, SISTEMA, usuario, temperatura=0)
        nota = float(r.get("nota"))
        datos["nota_por_que"] = str(r.get("por_que", ""))[:200]
        return max(1.0, min(10.0, nota))
    except Exception as e:
        logger.warning(f"Mejor del día: la IA no pudo calificar ({e}); solo cuenta la calidad")
        return None


def nota_tecnica(datos: dict, conteo: dict | None) -> float:
    """Hasta 40 puntos por cosas que se notan al verlo."""
    conteo = conteo or {}
    puntos = 40.0
    usadas = sum(conteo.get(k, 0) for k in ("ia", "real", "stock", "propias", "clips"))
    rechazadas = conteo.get("rechazadas", 0)
    if usadas:
        puntos -= min(12, 12 * rechazadas / max(usadas + rechazadas, 1) * 1.5)
    if conteo.get("_sin_cuota"):
        puntos -= 4
    voz_usada = (datos.get("voz_usada") or {}).get("voz", "")
    if "falló" in voz_usada or "NO se pulió" in voz_usada or "respaldo" in voz_usada:
        puntos -= 10
    avatar_usado = str(datos.get("avatar_usado") or "")
    if avatar_usado.startswith("no —"):
        puntos -= 6
    return max(0.0, puntos)


def puntuar(cfg: dict, datos: dict, tema: dict, conteo: dict | None) -> float:
    ia_nota = nota_de_la_ia(cfg, datos, tema)
    tecnica = nota_tecnica(datos, conteo)
    if ia_nota is None:
        total = tecnica * 2.5 * 0.8  # sin opinión de la IA, un poco menos de confianza
    else:
        total = ia_nota * 6 + tecnica
    total = round(total, 1)
    datos["nota"] = total
    logger.info(f"Nota del video: {total}/100" + (f" — {datos.get('nota_por_que')}" if datos.get("nota_por_que") else ""))
    return total


def _fecha(e: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(e.get("fecha", ""))
    except ValueError:
        return None


def elegir(entradas: list[dict], ahora: datetime | None = None, horas: float = 24) -> dict | None:
    """El automático con más nota de las últimas `horas`, si hoy no se publicó otro."""
    ahora = ahora or datetime.now()
    desde = ahora - timedelta(hours=horas)
    recientes = [e for e in entradas if (_fecha(e) or datetime.min) >= desde]
    if any(e.get("publicado_mejor") for e in entradas
           if (_fecha(e) or datetime.min) >= ahora - timedelta(hours=20)):
        logger.info("Mejor del día: ya se publicó uno hoy")
        return None
    candidatos = [e for e in recientes if e.get("automatico") and e.get("drive")
                  and not e.get("publicado") and e.get("nota") is not None]
    if not candidatos:
        return None
    return max(candidatos, key=lambda e: e["nota"])


def _bajar_de_drive(cfg: dict, ruta: str, destino: Path) -> Path | None:
    if not shutil.which("rclone"):
        logger.error("Mejor del día: rclone no está instalado")
        return None
    d = cfg.get("drive", {})
    origen = f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}/{ruta}"
    archivo = destino / Path(ruta).name
    try:
        subprocess.run(["rclone", "copyto", origen, str(archivo)], check=True, timeout=900)
        return archivo if archivo.exists() else None
    except Exception as e:
        logger.error(f"Mejor del día: no se pudo bajar {origen}: {e}")
        return None


def publicar(cfg: dict, entradas: list[dict], guardar) -> bool:
    """Elige, baja de Drive y publica. `guardar(entradas)` guarda el historial marcado."""
    from fabrica import config, salidas

    mejor = elegir(entradas)
    if not mejor:
        logger.info("Mejor del día: no hay video automático para publicar")
        return False
    competidores = [e for e in entradas if e.get("automatico") and e.get("nota") is not None
                    and (_fecha(e) or datetime.min) >= datetime.now() - timedelta(hours=24)]
    logger.info("Mejor del día — notas: " + ", ".join(
        f"#{e.get('numero', '?'):03d} {e['nota']}" if isinstance(e.get("numero"), int) else f"{e['nota']}"
        for e in sorted(competidores, key=lambda e: -e["nota"])))
    video = None
    local = mejor.get("archivo")
    if local:
        ruta = Path(local) if Path(local).is_absolute() else config.RAIZ / local
        if ruta.exists():
            video = ruta
    temporal = None
    if video is None:
        temporal = Path(tempfile.mkdtemp(prefix="mejor-"))
        video = _bajar_de_drive(cfg, mejor["drive"], temporal)
    if video is None:
        return False
    logger.info(f"Mejor del día: «{mejor.get('titulo', mejor.get('tema'))}» con {mejor['nota']}/100")
    resultado = salidas.publicar(cfg, video, {"titulo": mejor.get("titulo", mejor.get("tema", "")),
                                              "hashtags": mejor.get("hashtags", []),
                                              "credito_musica": mejor.get("credito_musica", "")})
    if temporal:
        shutil.rmtree(temporal, ignore_errors=True)
    if resultado.get("success"):
        mejor["publicado"] = True
        mejor["publicado_mejor"] = True
        guardar(entradas)
        return True
    return False
