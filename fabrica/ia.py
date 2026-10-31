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


# Modelos en orden de preferencia. Los proveedores retiran modelos seguido, así
# que si uno ya no existe (404) se pasa al siguiente y además se consulta la
# lista de modelos disponibles de la cuenta.
MODELOS_GEMINI = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest",
                  "gemini-2.5-flash-lite"]
MODELOS_GROQ = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "qwen/qwen3-32b",
                "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
_NO_CHAT = ("whisper", "tts", "guard", "embed", "vision", "image", "audio", "playai", "orpheus")


def _lista(valor, defecto: list[str]) -> list[str]:
    if isinstance(valor, str) and valor:
        return [valor] + [m for m in defecto if m != valor]
    return list(valor) if valor else list(defecto)


def _proveedores(cfg: dict) -> list[dict]:
    ia = cfg.get("ia", {})
    lista = []
    if secreto("GEMINI_API_KEY"):
        lista.append({
            "nombre": "gemini",
            "base": "https://generativelanguage.googleapis.com/v1beta/openai",
            "clave": secreto("GEMINI_API_KEY"),
            "modelos": _lista(ia.get("modelo_gemini"), MODELOS_GEMINI),
        })
    if secreto("GROQ_API_KEY"):
        lista.append({
            "nombre": "groq",
            "base": "https://api.groq.com/openai/v1",
            "clave": secreto("GROQ_API_KEY"),
            "modelos": _lista(ia.get("modelo_groq"), MODELOS_GROQ),
        })
    if ia.get("usar_pollinations_texto", True):
        lista.append({
            "nombre": "pollinations",
            "base": "https://text.pollinations.ai/openai",
            "url": "https://text.pollinations.ai/openai",
            "clave": secreto("POLLINATIONS_TOKEN"),
            "modelos": [ia.get("modelo_pollinations", "openai")],
        })
    return lista


_DISPONIBLES: dict[str, list[str]] = {}


def _modelos_de(p: dict) -> list[str]:
    """Modelos preferidos que la cuenta realmente tiene, más otros de chat como respaldo."""
    if p["nombre"] == "pollinations":
        return p["modelos"]
    if p["nombre"] not in _DISPONIBLES:
        try:
            r = requests.get(f"{p['base']}/models", timeout=20,
                             headers={"Authorization": f"Bearer {p['clave']}"})
            ids = [m["id"].removeprefix("models/") for m in r.json().get("data", [])] if r.ok else []
        except Exception:
            ids = []
        _DISPONIBLES[p["nombre"]] = ids
    ids = _DISPONIBLES[p["nombre"]]
    if not ids:
        return p["modelos"]
    preferidos = [m for m in p["modelos"] if m in ids]
    extra = [m for m in ids if m not in preferidos and not any(x in m.lower() for x in _NO_CHAT)
             and ("flash" in m or p["nombre"] != "gemini")]
    return (preferidos + extra)[:6]


def extraer_json(texto: str):
    """Saca el JSON de la respuesta aunque venga envuelto en ```json ... ```."""
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.S).strip()
    bloque = re.search(r"```(?:json)?\s*(.*?)```", texto, re.S)
    if bloque:
        texto = bloque.group(1).strip()
    inicio = min((i for i in (texto.find("{"), texto.find("[")) if i >= 0), default=-1)
    if inicio > 0:
        texto = texto[inicio:]
    return json.loads(texto)


def _pedir(p: dict, modelo: str, sistema: str, usuario: str, temperatura: float):
    cabeceras = {"Content-Type": "application/json"}
    if p["clave"]:
        cabeceras["Authorization"] = f"Bearer {p['clave']}"
    return requests.post(
        p.get("url") or f"{p['base']}/chat/completions",
        headers=cabeceras,
        json={"model": modelo, "temperature": temperatura,
              "messages": [{"role": "system", "content": sistema},
                           {"role": "user", "content": usuario}]},
        timeout=90,
    )


def pedir_json(cfg: dict, sistema: str, usuario: str, temperatura: float = 0.7):
    proveedores = _proveedores(cfg)
    if not any(p["nombre"] in ("gemini", "groq") for p in proveedores):
        logger.warning("No hay GEMINI_API_KEY ni GROQ_API_KEY: se intenta solo con Pollinations, "
                       "que puede pedir pago. Revisa los Secrets del repositorio.")
    if not proveedores:
        raise RuntimeError("No hay ninguna IA configurada. Agrega GEMINI_API_KEY o GROQ_API_KEY.")
    errores = []
    for p in proveedores:
        for modelo in _modelos_de(p):
            siguiente_proveedor = False
            for intento in range(2):
                etiqueta = f"{p['nombre']} ({modelo})"
                try:
                    r = _pedir(p, modelo, sistema, usuario, temperatura)
                except requests.RequestException as e:
                    errores.append(f"{etiqueta}: {type(e).__name__}")
                    logger.warning(f"IA {etiqueta} no respondió (intento {intento + 1}): {type(e).__name__}")
                    continue
                if r.status_code in (401, 402, 403):
                    # Clave inválida o servicio que ahora cobra: no sirve probar otros modelos.
                    errores.append(f"{etiqueta}: HTTP {r.status_code} {r.text[:200]}")
                    logger.warning(f"IA {etiqueta} rechazó la clave o pide pago (HTTP {r.status_code})")
                    siguiente_proveedor = True
                    break
                if r.status_code in (400, 404):
                    # Modelo retirado o no disponible para esta cuenta: probar el siguiente.
                    errores.append(f"{etiqueta}: HTTP {r.status_code} {r.text[:200]}")
                    logger.warning(f"IA {etiqueta} no disponible (HTTP {r.status_code}); pruebo otro modelo")
                    break
                if r.status_code == 429 or r.status_code >= 500:
                    errores.append(f"{etiqueta}: HTTP {r.status_code}")
                    logger.warning(f"IA {etiqueta} ocupada (HTTP {r.status_code}, intento {intento + 1})")
                    time.sleep(5 * (intento + 1))
                    continue
                try:
                    contenido = r.json()["choices"][0]["message"]["content"] or ""
                    resultado = extraer_json(contenido)
                except Exception as e:
                    errores.append(f"{etiqueta}: respuesta inválida ({type(e).__name__})")
                    logger.warning(f"IA {etiqueta} devolvió algo que no es JSON (intento {intento + 1})")
                    continue
                logger.info(f"IA: respuesta de {etiqueta}")
                return resultado
            if siguiente_proveedor:
                break
    raise RuntimeError("Todas las IA fallaron:\n" + "\n".join(errores[-12:]))


def imagen_encaja(cfg: dict, ruta, descripcion: str) -> bool | None:
    """Gemini mira la imagen y dice si muestra lo que pide el guion.
    Devuelve None si no se pudo revisar (sin clave, sin cuota): la imagen se acepta."""
    import base64

    clave = secreto("GEMINI_API_KEY")
    if not clave:
        return None
    modelo = cfg.get("imagenes", {}).get("modelo_revision", "gemini-flash-lite-latest")
    datos = base64.b64encode(open(ruta, "rb").read()).decode()
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            headers={"Authorization": f"Bearer {clave}"}, timeout=60,
            json={"model": modelo, "temperature": 0, "messages": [{"role": "user", "content": [
                {"type": "text", "text": "Does this image clearly show the MAIN subject and place of this "
                 f"description? Ignore art style. Description: {descripcion}\n"
                 'Answer only JSON: {"ok": true} or {"ok": false, "why": "..."}'},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{datos}"}},
            ]}]})
        if not r.ok:
            return None
        respuesta = extraer_json(r.json()["choices"][0]["message"]["content"] or "")
        if not respuesta.get("ok", True):
            logger.info(f"Revisión de imagen: no encaja ({respuesta.get('why', '')[:120]})")
        return bool(respuesta.get("ok", True))
    except Exception:
        return None


def describir_imagen(cfg: dict, ruta) -> str:
    """Descripción corta de una foto propia (qué se ve, colores, tipo de producto)."""
    import base64

    clave = secreto("GEMINI_API_KEY")
    if not clave:
        return ""
    modelo = cfg.get("imagenes", {}).get("modelo_revision", "gemini-flash-lite-latest")
    from PIL import Image
    import io

    img = Image.open(ruta).convert("RGB")
    img.thumbnail((768, 768))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    try:
        r = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            headers={"Authorization": f"Bearer {clave}"}, timeout=60,
            json={"model": modelo, "temperature": 0, "messages": [{"role": "user", "content": [
                {"type": "text", "text": "Describe en español, en máximo 20 palabras, qué se ve en esta "
                 "foto (producto, color, material, lugar). Solo la descripción."},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,"
                                                    + base64.b64encode(buf.getvalue()).decode()}},
            ]}]})
        return (r.json()["choices"][0]["message"]["content"] or "").strip()[:200] if r.ok else ""
    except Exception:
        return ""
