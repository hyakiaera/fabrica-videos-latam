"""Cliente de IA de texto gratis con respaldo: Gemini → Groq → Pollinations.

Los tres exponen una API compatible con OpenAI, así que se usa un solo
formato de petición y se pasa al siguiente proveedor si uno falla o se
queda sin cuota."""

import json
import re
import time

import requests
from loguru import logger

from fabrica.config import secreto


def _proveedores(cfg: dict) -> list[dict]:
    ia = cfg.get("ia", {})
    lista = []
    if secreto("GEMINI_API_KEY"):
        lista.append({
            "nombre": "gemini",
            "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            "clave": secreto("GEMINI_API_KEY"),
            "modelo": ia.get("modelo_gemini", "gemini-flash-latest"),
        })
    if secreto("GROQ_API_KEY"):
        lista.append({
            "nombre": "groq",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "clave": secreto("GROQ_API_KEY"),
            "modelo": ia.get("modelo_groq", "llama-3.3-70b-versatile"),
        })
    if ia.get("usar_pollinations_texto", True):
        lista.append({
            "nombre": "pollinations",
            "url": "https://text.pollinations.ai/openai",
            "clave": secreto("POLLINATIONS_TOKEN"),
            "modelo": ia.get("modelo_pollinations", "openai"),
        })
    return lista


def extraer_json(texto: str):
    """Saca el JSON de la respuesta aunque venga envuelto en ```json ... ```."""
    texto = texto.strip()
    bloque = re.search(r"```(?:json)?\s*(.*?)```", texto, re.S)
    if bloque:
        texto = bloque.group(1).strip()
    inicio = min((i for i in (texto.find("{"), texto.find("[")) if i >= 0), default=-1)
    if inicio > 0:
        texto = texto[inicio:]
    return json.loads(texto)


def pedir_json(cfg: dict, sistema: str, usuario: str, temperatura: float = 0.7):
    proveedores = _proveedores(cfg)
    if not any(p["nombre"] in ("gemini", "groq") for p in proveedores):
        logger.warning("No hay GEMINI_API_KEY ni GROQ_API_KEY: se intenta solo con Pollinations, "
                       "que puede pedir pago. Revisa los Secrets del repositorio.")
    if not proveedores:
        raise RuntimeError("No hay ninguna IA configurada. Agrega GEMINI_API_KEY o GROQ_API_KEY.")
    errores = []
    for p in proveedores:
        for intento in range(2):
            try:
                cabeceras = {"Content-Type": "application/json"}
                if p["clave"]:
                    cabeceras["Authorization"] = f"Bearer {p['clave']}"
                r = requests.post(
                    p["url"],
                    headers=cabeceras,
                    json={
                        "model": p["modelo"],
                        "temperature": temperatura,
                        "messages": [
                            {"role": "system", "content": sistema},
                            {"role": "user", "content": usuario},
                        ],
                    },
                    timeout=120,
                )
                if r.status_code in (401, 402, 403):
                    # Clave inválida o servicio que ahora cobra: no sirve reintentar.
                    errores.append(f"{p['nombre']}: HTTP {r.status_code} {r.text[:200]}")
                    logger.warning(f"IA {p['nombre']} rechazó la petición (HTTP {r.status_code})")
                    break
                if r.status_code == 429 or r.status_code >= 500:
                    raise RuntimeError(f"HTTP {r.status_code}")
                r.raise_for_status()
                contenido = r.json()["choices"][0]["message"]["content"]
                resultado = extraer_json(contenido)
                logger.info(f"IA: respuesta de {p['nombre']} ({p['modelo']})")
                return resultado
            except Exception as e:
                errores.append(f"{p['nombre']}: {type(e).__name__}: {e}"[:300])
                logger.warning(f"IA {p['nombre']} falló (intento {intento + 1}): {e}")
                time.sleep(3 * (intento + 1))
    raise RuntimeError("Todas las IA fallaron:\n" + "\n".join(errores))
