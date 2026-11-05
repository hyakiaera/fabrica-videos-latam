"""Qué hacer con cada video terminado. Las tres opciones son independientes y
se pueden combinar: guardar para descargar, subir a Google Drive y publicar."""

import shutil
import subprocess
from pathlib import Path

from loguru import logger

from fabrica.config import secreto


def ficha_texto(datos: dict, tema: dict, creditos: list[str], conteo: dict | None = None) -> str:
    """Texto listo para copiar y pegar al publicar a mano."""
    lineas = [
        f"TÍTULO:\n{datos['titulo']}\n",
        f"DESCRIPCIÓN:\n{datos.get('descripcion', '')}\n\n{' '.join(datos.get('hashtags', []))}\n",
        f"CATEGORÍA: {tema.get('categoria', '')}   ESTILO: {tema.get('estilo', '')}",
        f"POR QUÉ ESTE TEMA: {tema.get('por_que', '')}\n",
        "FUENTES (verifica los datos antes de publicar):",
        *[f"- {t} ({f}) {u}" for t, f, u in tema.get("fuentes", [])],
    ]
    if datos.get("voz_usada", {}).get("voz"):
        v = datos["voz_usada"]
        lineas += ["", f"VOZ: {v['voz']}" + (f"\n   motivo: {v['motivo']}" if v.get("motivo") else "")]
    if datos.get("animadas"):
        lineas += [f"ESCENAS ANIMADAS CON IA: {datos['animadas']}"]
    if datos.get("musica_usada"):
        lineas += [f"MÚSICA: {datos['musica_usada']}"]
    if datos.get("credito_musica"):
        lineas += ["", "CRÉDITO OBLIGATORIO (pégalo en la descripción al publicar):", datos["credito_musica"]]
    if datos.get("nota") is not None:
        lineas += [f"NOTA PARA 'MEJOR DEL DÍA': {datos['nota']}/100" + (f" — {datos['nota_por_que']}" if datos.get("nota_por_que") else "")]
    if datos.get("avatar_usado"):
        lineas += [f"AVATAR: {datos['avatar_usado']}"]
    if conteo:
        graficas = sum(1 for e in datos.get("escenas", []) if e.get("grafica"))
        lineas += ["", f"IMÁGENES: {conteo.get('propias', 0)} tuyas, {conteo.get('ia', 0)} con IA, {conteo.get('real', 0)} fotos/logos reales, "
                       f"{conteo.get('stock', 0)} de stock, {graficas} gráficas, "
                       f"{conteo.get('rechazadas', 0)} rechazadas por no encajar, "
                       f"{conteo.get('estilizadas', 0)} fotos reales pasadas al estilo del video, "
                       f"{conteo.get('clips', 0)} clips de video reales"]
    if conteo and conteo.get("_sin_cuota"):
        lineas += [f"SIN CUOTA HOY (se usaron fotos en su lugar): {', '.join(conteo['_sin_cuota'])}"]
    if creditos:
        lineas += ["", "CRÉDITOS DE FOTOS (pégalos en la descripción):", *creditos]
    lineas += ["", "GUION:", datos["guion"]]
    return "\n".join(lineas)


def guardar_local(carpeta_dia: Path, nombre: str, video: Path, ficha: str,
                  miniatura: Path | None) -> Path:
    carpeta_dia.mkdir(parents=True, exist_ok=True)
    destino = carpeta_dia / f"{nombre}.mp4"
    shutil.copy(video, destino)
    (carpeta_dia / f"{nombre}.txt").write_text(ficha, encoding="utf-8")
    if miniatura and miniatura.exists():
        shutil.copy(miniatura, carpeta_dia / f"{nombre}.jpg")
    logger.success(f"Guardado para descargar: {destino}")
    return destino


def subir_drive(cfg: dict, carpeta_local: Path, ruta_relativa: str) -> bool:
    """Sube con rclone a la carpeta de Drive configurada. El remoto se llama
    'drive' y se configura una vez con `rclone config` (ver FABRICA.md)."""
    d = cfg.get("drive", {})
    if not shutil.which("rclone"):
        logger.error("Drive: rclone no está instalado; el video quedó solo en la carpeta local")
        return False
    destino = f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}/{ruta_relativa}"
    try:
        subprocess.run(["rclone", "copy", str(carpeta_local), destino], check=True, timeout=1800)
        logger.success(f"Subido a Google Drive: {destino}")
        return True
    except Exception as e:
        logger.error(f"Drive: la subida falló: {e}")
        return False


def publicar(cfg: dict, video: Path, datos: dict) -> dict:
    """Publica en TikTok/Instagram/YouTube Shorts con la integración Upload-Post
    que ya trae MoneyPrinterTurbo."""
    from app.services.upload_post import cross_post_video

    p = cfg.get("publicar", {})
    if not secreto("UPLOAD_POST_API_KEY"):
        logger.warning("Publicar: falta UPLOAD_POST_API_KEY; no se publicó")
        return {"success": False, "error": "sin clave"}
    cuenta = {
        "upload_post_api_key": secreto("UPLOAD_POST_API_KEY"),
        "upload_post_username": secreto("UPLOAD_POST_USERNAME") or p.get("usuario", ""),
        "upload_post_enabled": True,
    }
    titulo = f"{datos['titulo']} {' '.join(datos.get('hashtags', [])[:5])}"
    if datos.get("credito_musica"):  # obligatorio por la licencia CC BY de la música
        titulo += f"\n\n{datos['credito_musica']}"
    titulo = titulo[:2000]
    import os
    elegidas = os.environ.get("PLATAFORMAS", "").strip()
    plataformas = ([x.strip().lower() for x in elegidas.split(",") if x.strip()] if elegidas
                   else p.get("plataformas", ["tiktok", "youtube", "instagram"]))

    def subir(redes):
        return cross_post_video(str(video), titulo, platforms=redes,
                                youtube_extra={"selfDeclaredMadeForKids": False}, account=cuenta)

    resultado = subir(plataformas)
    if resultado.get("success"):
        logger.success(f"Publicado en {plataformas}")
        return resultado
    logger.error(f"Publicar falló: {resultado.get('error')}")
    if len(plataformas) > 1 and "unconfirmed" not in str(resultado.get("error", "")):
        # Si una red no está conectada en Upload-Post, se rechaza todo: se prueba una por una.
        bien = []
        for red in plataformas:
            r = subir([red])
            if r.get("success"):
                bien.append(red)
            else:
                logger.warning(f"Publicar en {red}: {r.get('error')}")
        if bien:
            logger.success(f"Publicado en {bien} (las demás redes fallaron)")
            return {"success": True, "plataformas": bien}
    return resultado
