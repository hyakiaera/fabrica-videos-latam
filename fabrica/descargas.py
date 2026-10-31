"""Descargar archivos desde un link: Google Drive (archivo, carpeta o ZIP
compartido "cualquier persona con el enlace"), Hugging Face o link directo."""

import re
import zipfile
from pathlib import Path

import requests
from loguru import logger


def _descomprimir(carpeta: Path):
    for z in list(carpeta.rglob("*.zip")):
        try:
            with zipfile.ZipFile(z) as zf:
                zf.extractall(z.with_suffix(""))
            z.unlink()
        except zipfile.BadZipFile:
            logger.warning(f"Descarga: ZIP dañado {z.name}")


def bajar(url: str, carpeta: Path) -> list[Path]:
    """Descarga el link en la carpeta y devuelve los archivos obtenidos."""
    carpeta.mkdir(parents=True, exist_ok=True)
    url = url.strip().replace("/blob/", "/resolve/")  # Hugging Face: página → archivo
    antes = set(carpeta.rglob("*"))
    if "drive.google.com" in url or "docs.google.com" in url:
        import gdown

        carpeta_id = re.search(r"/folders/([\w-]+)", url)
        archivo_id = re.search(r"/d/([\w-]+)|[?&]id=([\w-]+)", url)
        if carpeta_id:
            gdown.download_folder(id=carpeta_id.group(1), output=str(carpeta), quiet=True)
        elif archivo_id:
            gdown.download(id=archivo_id.group(1) or archivo_id.group(2), output=str(carpeta) + "/",
                           quiet=True)
    else:
        nombre = url.split("?")[0].rstrip("/").split("/")[-1] or "descarga"
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(carpeta / nombre, "wb") as f:
                for trozo in r.iter_content(1 << 20):
                    f.write(trozo)
    _descomprimir(carpeta)
    nuevos = [p for p in carpeta.rglob("*") if p.is_file() and p not in antes]
    if not nuevos:
        raise RuntimeError("No se pudo descargar el link. En Google Drive: Compartir → "
                           "'Cualquier persona con el enlace'.")
    return nuevos
