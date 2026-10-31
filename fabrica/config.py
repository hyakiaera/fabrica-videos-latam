"""Configuración: perillas en fabrica.toml y claves secretas en variables de entorno.

Las claves nunca se guardan en el archivo: en GitHub van como "Secrets" y en
la PC como variables de entorno o en un archivo .env (ignorado por git)."""

import os
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / "fabrica.toml"
EJEMPLO = RAIZ / "fabrica.example.toml"


def _cargar_env():
    env = RAIZ / ".env"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def cargar(ruta: Path | None = None) -> dict:
    _cargar_env()
    ruta = ruta or (ARCHIVO if ARCHIVO.exists() else EJEMPLO)
    with open(ruta, "rb") as f:
        return tomllib.load(f)


def secreto(nombre: str) -> str:
    return os.environ.get(nombre, "").strip()
