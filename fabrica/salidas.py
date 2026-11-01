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
    if conteo:
        graficas = sum(1 for e in datos.get("escenas", []) if e.get("grafica"))
        lineas += ["", f"IMÁGENES: {conteo.get('propias', 0)} tuyas, {conteo.get('ia', 0)} con IA, {conteo.get('real', 0)} fotos/logos reales, "
                       f"{conteo.get('stock', 0)} de stock, {graficas} gráficas, "
                       f"{conteo.get('rechazadas', 0)} rechazadas por no encajar"]
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
    titulo = f"{datos['titulo']} {' '.join(datos.get('hashtags', [])[:5])}"[:2000]
    resultado = cross_post_video(
        str(video), titulo, platforms=p.get("plataformas", ["tiktok", "youtube", "instagram"]),
        youtube_extra={"selfDeclaredMadeForKids": False}, account=cuenta,
    )
    if resultado.get("success"):
        logger.success(f"Publicado en {p.get('plataformas')}")
    else:
        logger.error(f"Publicar falló: {resultado.get('error')}")
    return resultado
