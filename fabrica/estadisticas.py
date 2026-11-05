"""Lo que funciona en tu canal: lee las vistas de tus videos de YouTube (gratis, con una
clave de la API de YouTube) y ajusta la mezcla de temas hacia las categorías que más vistas
tienen, sin dejar de hacer las demás. También le da a la IA ejemplos de tus videos que mejor
funcionaron para que elija temas parecidos.

Se configura con el secreto YOUTUBE_API_KEY y la variable YOUTUBE_CANAL (tu @usuario o el ID)."""

import json
from datetime import datetime, timedelta

import requests
from loguru import logger

from fabrica.config import RAIZ, secreto

ARCHIVO = RAIZ / "estado" / "rendimiento.json"
API = "https://www.googleapis.com/youtube/v3"


def _get(ruta: str, **params) -> dict:
    params["key"] = secreto("YOUTUBE_API_KEY")
    r = requests.get(f"{API}/{ruta}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def videos_del_canal(canal: str, maximo: int = 100) -> list[dict]:
    """[{titulo, vistas, likes, fecha}] de los últimos videos del canal."""
    if canal.startswith("@"):
        datos = _get("channels", part="contentDetails", forHandle=canal)
    else:
        datos = _get("channels", part="contentDetails", id=canal)
    items = datos.get("items", [])
    if not items:
        raise RuntimeError(f"no encontré el canal {canal}")
    subidos = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, pagina = [], None
    while len(ids) < maximo:
        lista = _get("playlistItems", part="contentDetails", playlistId=subidos, maxResults=50,
                     **({"pageToken": pagina} if pagina else {}))
        ids += [i["contentDetails"]["videoId"] for i in lista.get("items", [])]
        pagina = lista.get("nextPageToken")
        if not pagina:
            break
    videos = []
    for k in range(0, len(ids[:maximo]), 50):
        for v in _get("videos", part="snippet,statistics", id=",".join(ids[k:k + 50])).get("items", []):
            e = v.get("statistics", {})
            videos.append({"titulo": v["snippet"]["title"], "fecha": v["snippet"]["publishedAt"][:10],
                           "vistas": int(e.get("viewCount", 0)), "likes": int(e.get("likeCount", 0))})
    return videos


def calcular(historial: list[dict], videos: list[dict]) -> dict:
    """Une cada video de YouTube con su categoría (por el título) y saca un factor por categoría."""
    from fabrica.mezcla import parecido

    por_categoria: dict[str, list[int]] = {}
    unidos = []
    for v in videos:
        mejor = max(historial, key=lambda e: parecido(v["titulo"], e.get("titulo", "")), default=None)
        if mejor and mejor.get("mezcla") and parecido(v["titulo"], mejor.get("titulo", "")) >= 0.6:
            por_categoria.setdefault(mejor["mezcla"], []).append(v["vistas"])
            unidos.append({**v, "mezcla": mejor["mezcla"]})
    todos = [x for lista in por_categoria.values() for x in lista]
    promedio = sum(todos) / len(todos) if todos else 0
    factores = {}
    for cat, vistas in por_categoria.items():
        if len(vistas) >= 3 and promedio > 0:
            # Entre 0.7 y 1.4: lo que funciona sube, lo demás baja un poco pero nunca desaparece.
            factores[cat] = round(max(0.7, min(1.4, (sum(vistas) / len(vistas)) / promedio)), 2)
    mejores = sorted(unidos, key=lambda v: -v["vistas"])[:8]
    return {"fecha": datetime.now().isoformat(timespec="minutes"), "factores": factores,
            "mejores": [{"titulo": v["titulo"], "vistas": v["vistas"], "mezcla": v["mezcla"]} for v in mejores],
            "videos_unidos": len(unidos)}


def actualizar(cfg: dict, historial: list[dict]) -> dict:
    """Lee YouTube como mucho una vez al día y guarda el resultado en estado/rendimiento.json."""
    import os
    guardado = json.loads(ARCHIVO.read_text(encoding="utf-8")) if ARCHIVO.exists() else {}
    canal = os.environ.get("YOUTUBE_CANAL", "").strip() or cfg.get("estadisticas", {}).get("canal", "")
    if not (secreto("YOUTUBE_API_KEY") and canal):
        return guardado
    try:
        if guardado and datetime.fromisoformat(guardado["fecha"]) > datetime.now() - timedelta(hours=20):
            return guardado
    except (KeyError, ValueError):
        pass
    try:
        nuevo = calcular(historial, videos_del_canal(canal))
        ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVO.write_text(json.dumps(nuevo, ensure_ascii=False, indent=1), encoding="utf-8")
        logger.info(f"Estadísticas: {nuevo['videos_unidos']} videos con datos; factores {nuevo['factores']}")
        return nuevo
    except Exception as e:
        logger.warning(f"Estadísticas: no se pudo leer YouTube ({e})")
        return guardado


def leer() -> dict:
    return json.loads(ARCHIVO.read_text(encoding="utf-8")) if ARCHIVO.exists() else {}
