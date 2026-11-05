"""Ficha de datos REALES de un lugar (idea tomada de ficha_lugar.py): Wikipedia, Wikidata y
REST Countries. Se le pasa al guionista para que los videos de geografía cuenten datos
verificados (población, superficie, capital, vecinos, historia, por qué se llama así...)
en vez de inventarlos."""
import re

import requests
from loguru import logger

UA = {"User-Agent": "FabricaVideos/1.0 (generador de videos educativos; github.com/hyakiaera/fabrica-videos-latam)"}
SECCIONES = ["toponimia", "etimolog", "origen del nombre", "historia", "geograf", "territorio", "relieve",
             "clima", "hidrograf", "flora", "fauna", "demograf", "poblaci", "econom", "gastronom",
             "cultura", "turismo", "división", "organización territorial", "regiones", "símbolos"]


def _get(url, params, timeout=25):
    try:
        r = requests.get(url, params=params, headers=UA, timeout=timeout)
        return r.json() if r.ok else None
    except Exception as e:
        logger.warning(f"Ficha: {url.split('/')[2]} no respondió ({e})")
        return None


def _wiki(lang, **p):
    p.update(format="json", formatversion=2)
    return _get(f"https://{lang}.wikipedia.org/w/api.php", p)


def _recortar(texto: str, n: int) -> str:
    texto = re.sub(r"\n{2,}", "\n", texto).strip()
    if len(texto) <= n:
        return texto
    corte = texto[:n]
    punto = corte.rfind(". ")
    return corte[: punto + 1] if punto > n // 2 else corte


def articulo(consulta: str, lang: str = "es") -> dict | None:
    r = _wiki(lang, action="query", list="search", srsearch=consulta, srlimit=1)
    res = ((r or {}).get("query") or {}).get("search") or []
    if not res:
        return None
    r = _wiki(lang, action="query", prop="extracts|pageprops", titles=res[0]["title"], redirects=1,
              explaintext=1, ppprop="wikibase_item")
    pg = (((r or {}).get("query") or {}).get("pages") or [{}])[0]
    return {"titulo": pg.get("title", res[0]["title"]), "texto": pg.get("extract", ""),
            "qid": (pg.get("pageprops") or {}).get("wikibase_item")}


def _partes(texto: str, maximo: int = 3200) -> str:
    """La introducción y las secciones útiles para un video (historia, nombre, regiones...)."""
    trozos = re.split(r"^(={2,})\s*(.+?)\s*\1\s*$", texto, flags=re.M)
    salida = [_recortar(trozos[0], 900)]
    for i in range(1, len(trozos) - 1, 3):
        titulo, cuerpo = trozos[i + 1].strip(), trozos[i + 2].strip()
        if len(trozos[i]) == 2 and cuerpo and any(s in titulo.lower() for s in SECCIONES):
            salida.append(f"[{titulo}] {_recortar(cuerpo, 500)}")
        if sum(len(s) for s in salida) > maximo:
            break
    return "\n".join(salida)[:maximo]


def _wikidata(qid: str) -> list[str]:
    r = _get("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": qid,
                                                     "props": "claims", "format": "json"})
    ent = ((r or {}).get("entities") or {}).get(qid, {})
    claims = ent.get("claims", {})

    def valores(pid):
        lista = claims.get(pid, [])
        pref = [c for c in lista if c.get("rank") == "preferred"] or lista
        return [c["mainsnak"]["datavalue"]["value"] for c in pref if "datavalue" in c.get("mainsnak", {})]

    datos, ids = [], {}
    for pid in ("P36", "P47", "P138", "P1549", "P17"):
        ids[pid] = [v["id"] for v in valores(pid) if isinstance(v, dict) and "id" in v][:12]
    todos = [i for v in ids.values() for i in v]
    nombres = {}
    if todos:
        r = _get("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": "|".join(todos),
                                                         "props": "labels", "languages": "es|en", "format": "json"})
        for k, e in ((r or {}).get("entities") or {}).items():
            lb = e.get("labels", {})
            nombres[k] = (lb.get("es") or lb.get("en") or {}).get("value", "")
    etiquetas = {"P36": "Capital", "P47": "Limita con", "P138": "Nombrado en honor a", "P1549": "Gentilicio",
                 "P17": "País"}
    for pid, titulo in etiquetas.items():
        lista = [nombres.get(i) for i in ids[pid] if nombres.get(i)]
        if lista:
            datos.append(f"{titulo}: {', '.join(lista)}")
    poblacion = None
    for c in claims.get("P1082", []):
        try:
            cantidad = int(float(c["mainsnak"]["datavalue"]["value"]["amount"]))
            fecha = c.get("qualifiers", {}).get("P585", [{}])[0].get("datavalue", {}).get("value", {}).get("time", "+0000")
            if poblacion is None or fecha > poblacion[1]:
                poblacion = (cantidad, fecha)
        except (KeyError, ValueError, TypeError):
            continue
    if poblacion:
        datos.append(f"Habitantes: {poblacion[0]:,} (dato de {poblacion[1][1:5]})".replace(",", " "))
    area = valores("P2046")
    if area:
        try:
            datos.append(f"Superficie: {float(area[0]['amount']):,.0f} km²".replace(",", " "))
        except (KeyError, ValueError, TypeError):
            pass
    fundacion = valores("P571")
    if fundacion and isinstance(fundacion[0], dict) and fundacion[0].get("time"):
        t = fundacion[0]["time"]
        datos.append(f"Fundación/creación: {t[1:5].lstrip('0')}{' a.C.' if t.startswith('-') else ''}")
    codigo = valores("P297")
    if codigo:
        datos += _pais(codigo[0])
    return datos


def _pais(codigo: str) -> list[str]:
    r = _get(f"https://restcountries.com/v3.1/alpha/{codigo}", {})
    d = (r[0] if isinstance(r, list) and r else r) or {}
    if not d.get("name"):
        return []
    salida = [f"Región: {d.get('region', '')} / {d.get('subregion', '')}"]
    if d.get("languages"):
        salida.append(f"Idiomas: {', '.join(d['languages'].values())}")
    if d.get("currencies"):
        salida.append("Moneda: " + ", ".join(v.get("name", "") for v in d["currencies"].values()))
    if d.get("landlocked"):
        salida.append("No tiene salida al mar")
    if d.get("borders") is not None and not d.get("borders"):
        salida.append("No tiene fronteras terrestres con otros países")
    return salida


def datos(tema: str, lang: str = "es") -> str:
    """Texto con los datos reales del tema/lugar; vacío si no se encontró nada."""
    art = articulo(tema, lang)
    if not art:
        return ""
    lineas = [f"FICHA DE DATOS REALES (Wikipedia/Wikidata) — {art['titulo']}"]
    if art.get("qid"):
        lineas += _wikidata(art["qid"])
    lineas.append(_partes(art.get("texto", "")))
    texto = "\n".join(l for l in lineas if l)
    logger.info(f"Ficha: datos reales de «{art['titulo']}» ({len(texto)} letras)")
    return texto
