"""Mapas de geografía animados, como los canales de geografía: un mapa satelital donde
la cámara vuela de un lugar a otro, los países y regiones se pintan de colores, las
fronteras se dibujan con una línea brillante, aparecen preguntas en grande, iconos,
rutas y nombres.

Todo es gratis y libre:
  - mapa satelital: NASA Blue Marble (dominio público, vía NASA GIBS); si no responde,
    se dibuja un mapa propio con los contornos de Natural Earth.
  - países, estados, mares, ríos y ciudades: Natural Earth (dominio público).
  - lugares que no están ahí: OpenStreetMap (Nominatim).
  - iconos: emojis Noto (licencia libre).

Cada escena trae un "mapa" que escribe la IA del guion, por ejemplo:
  {"camara": "México",
   "resaltar": [{"lugar": "México", "color": "verde", "etiqueta": "MÉXICO"}],
   "frontera": {"entre": ["México", "Estados Unidos"], "dato": "3,169 km"},
   "regiones": [{"nombre": "Norte", "color": "rojo", "estados": ["Sonora", "Chihuahua"], "iconos": ["🏭", "🌵"]}],
   "puntos": [{"lugar": "Ciudad de México", "texto": "CDMX", "icono": "🏛️"}],
   "ruta": {"lugares": ["Sevilla, España", "Veracruz, México"], "texto": "1519"},
   "etiquetas": ["Océano Pacífico", "Golfo de México"],
   "nombres_estados": "México",
   "pregunta": "¿NORTEAMÉRICA?",
   "mantener": true}
"""
import difflib
import json
import math
import random
import re
import subprocess
import unicodedata
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import imageio_ffmpeg
import requests
from loguru import logger
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from fabrica.config import RAIZ

FPS = 30
TESELA = 256
Z_MAX = 8.4          # NASA Blue Marble llega hasta el nivel 8
ANCHO, ALTO = 720, 1280   # se dibuja aquí y ffmpeg lo agranda al tamaño final
DATOS = RAIZ / "storage" / "geo"
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{}.geojson"
CAPAS_NE = {
    "paises": "ne_50m_admin_0_countries",
    "estados": "ne_10m_admin_1_states_provinces",
    "mares": "ne_50m_geography_marine_polys",
    "rios": "ne_50m_rivers_lake_centerlines",
    "ciudades": "ne_10m_populated_places",
}
TESELAS_NASA = [
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/"
    "GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/"
    "default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/"
    "GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
]
CABECERAS = {"User-Agent": "FabricaVideos/1.0 (generador de videos; github.com/hyakiaera/fabrica-videos-latam)"}
NEGRITA = RAIZ / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"
EMOJIS = [Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
          Path("/usr/share/fonts/noto/NotoColorEmoji.ttf")]
TAMANOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
CREDITO = "NASA Blue Marble · Natural Earth"

COLORES = {
    "verde": (76, 217, 100), "rojo": (235, 64, 52), "azul": (40, 90, 230), "celeste": (90, 180, 240),
    "amarillo": (250, 210, 40), "naranja": (245, 150, 40), "morado": (170, 90, 220), "rosa": (235, 90, 200),
    "lila": (180, 150, 235), "turquesa": (40, 200, 190), "blanco": (240, 240, 240), "cafe": (160, 110, 60),
    "dorado": (230, 180, 60), "gris": (150, 150, 160),
}
ORDEN_COLORES = ["rojo", "celeste", "lila", "rosa", "naranja", "verde", "morado", "amarillo", "turquesa"]
ALIAS = {
    "eeuu": "united states of america", "ee uu": "united states of america", "usa": "united states of america",
    "estados unidos": "united states of america", "estados unidos de america": "united states of america",
    "reino unido": "united kingdom", "inglaterra": "united kingdom", "rusia": "russia",
    "republica dominicana": "dominican rep.", "rd": "dominican rep.", "corea del sur": "south korea",
    "corea del norte": "north korea", "cdmx": "ciudad de mexico", "distrito federal": "ciudad de mexico",
    "holanda": "netherlands", "paises bajos": "netherlands", "chequia": "czechia",
}


# ---------------------------------------------------------------- datos

def _norm(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\b(the|el|la|los|las|de|del|of|rep|republica|republic)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _geojson(capa: str) -> dict:
    DATOS.mkdir(parents=True, exist_ok=True)
    ruta = DATOS / f"{CAPAS_NE[capa]}.geojson"
    if not ruta.exists():
        logger.info(f"Mapa: bajando {CAPAS_NE[capa]} (Natural Earth, una sola vez)")
        r = requests.get(NE.format(CAPAS_NE[capa]), headers=CABECERAS, timeout=180)
        r.raise_for_status()
        ruta.write_bytes(r.content)
    return json.loads(ruta.read_text(encoding="utf-8"))


def _forma(geometria: dict):
    from shapely.geometry import shape
    g = shape(geometria)
    return g if g.is_valid else g.buffer(0)


@lru_cache(maxsize=1)
def _paises() -> list[tuple[set, str, object]]:
    salida = []
    for f in _geojson("paises")["features"]:
        p = f["properties"]
        nombres = {_norm(p.get(k)) for k in ("NAME", "NAME_LONG", "ADMIN", "NAME_EN", "NAME_ES",
                                              "NAME_SORT", "NAME_ALT", "FORMAL_EN", "ISO_A3") if p.get(k)}
        salida.append((nombres - {""}, p.get("NAME_ES") or p.get("NAME"), _forma(f["geometry"])))
    return salida


@lru_cache(maxsize=1)
def _estados() -> list[tuple[set, str, str, object]]:
    """(nombres, nombre para mostrar, país normalizado, forma). Se guarda una versión
    simplificada para no leer los 40 MB cada vez."""
    from shapely.geometry import mapping, shape
    compacto = DATOS / "estados-simplificados.json"
    if not compacto.exists():
        filas = []
        for f in _geojson("estados")["features"]:
            p = f["properties"]
            if not f.get("geometry"):
                continue
            g = _forma(f["geometry"]).simplify(0.01, preserve_topology=True)
            nombres = [p.get(k) for k in ("name", "name_es", "name_en", "name_alt", "woe_name", "gn_name")
                       if p.get(k)]
            filas.append({"n": nombres, "m": p.get("name_es") or p.get("name") or "", "p": p.get("admin", ""),
                          "g": mapping(g)})
        compacto.write_text(json.dumps(filas), encoding="utf-8")
    salida = []
    for f in json.loads(compacto.read_text(encoding="utf-8")):
        nombres = set()
        for n in f["n"]:
            nombres |= {_norm(x) for x in str(n).split("|")}
        salida.append((nombres - {""}, f["m"], _norm(f["p"]), shape(f["g"])))
    return salida


@lru_cache(maxsize=1)
def _mares() -> list[tuple[set, str, object]]:
    salida = []
    for f in _geojson("mares")["features"]:
        p = f["properties"]
        nombres = {_norm(p.get(k)) for k in ("name", "name_es", "name_en", "label") if p.get(k)}
        salida.append((nombres - {""}, p.get("name_es") or p.get("name"), _forma(f["geometry"])))
    return salida


@lru_cache(maxsize=1)
def _rios() -> list[tuple[set, str, object]]:
    salida = []
    for f in _geojson("rios")["features"]:
        p = f["properties"]
        if not f.get("geometry"):
            continue
        nombres = {_norm(p.get(k)) for k in ("name", "name_es", "name_en") if p.get(k)}
        salida.append((nombres - {""}, p.get("name_es") or p.get("name"), _forma(f["geometry"])))
    return salida


@lru_cache(maxsize=1)
def _ciudades() -> list[tuple[set, str, str, float, float, float]]:
    """(nombres, nombre en español, país normalizado, población, lon, lat)."""
    compacto = DATOS / "ciudades.json"
    if not compacto.exists():
        filas = []
        for f in _geojson("ciudades")["features"]:
            p = f["properties"]
            lon, lat = f["geometry"]["coordinates"][:2]
            nombres = [p.get(k) for k in ("NAME", "NAME_ES", "NAMEASCII", "NAME_EN", "NAMEALT") if p.get(k)]
            filas.append([nombres, p.get("NAME_ES") or p.get("NAME"), p.get("ADM0NAME", ""),
                          float(p.get("POP_MAX") or 0), lon, lat])
        compacto.write_text(json.dumps(filas), encoding="utf-8")
    salida = []
    for nombres, mostrar, pais, pob, lon, lat in json.loads(compacto.read_text(encoding="utf-8")):
        conjunto = set()
        for n in nombres:
            conjunto |= {_norm(x) for x in str(n).split("|")}
        salida.append((conjunto - {""}, mostrar, _norm(pais), pob, lon, lat))
    return salida


def _nombres_de_pais(pais: str) -> set:
    """Todos los nombres de un país (para que "España" encuentre "Spain")."""
    if not pais:
        return set()
    x = _buscar_en(_paises(), pais)
    return (x[0] if x else set()) | {pais}


class Lugar:
    def __init__(self, nombre: str, forma=None, tipo: str = "punto", punto=None):
        self.nombre, self.forma, self.tipo = nombre, forma, tipo
        if punto is None and forma is not None:
            rp = forma.representative_point() if tipo != "rio" else forma.interpolate(0.5, normalized=True)
            punto = (rp.x, rp.y)
        self.punto = punto  # (lon, lat)

    def caja(self):
        if self.forma is not None:
            partes = [g for g in getattr(self.forma, "geoms", [self.forma]) if g.geom_type == "Polygon"]
            if len(partes) > 1:  # solo las partes grandes (sin Alaska, Hawái ni islas lejanas)
                mayor = max(partes, key=lambda g: g.area)
                cerca = [g for g in partes if g.area >= mayor.area * 0.5
                         or g.distance(mayor) < 4 and g.area >= mayor.area * 0.005]
                x0 = min(g.bounds[0] for g in cerca); y0 = min(g.bounds[1] for g in cerca)
                x1 = max(g.bounds[2] for g in cerca); y1 = max(g.bounds[3] for g in cerca)
                if x1 - x0 < 200:
                    return x0, y0, x1, y1
                return mayor.bounds
            return self.forma.bounds
        lon, lat = self.punto
        return lon - 1.5, lat - 1.2, lon + 1.5, lat + 1.2


def _buscar_en(lista, n: str, pais: str = ""):
    exactos = [x for x in lista if n in x[0]]
    if pais:
        del_pais = [x for x in exactos if len(x) > 3 and pais in x[2]]
        exactos = del_pais or exactos
    if exactos:
        return exactos[0]
    todos = {nombre: x for x in lista for nombre in x[0]}
    parecido = difflib.get_close_matches(n, list(todos), n=1, cutoff=0.88)
    return todos[parecido[0]] if parecido else None


@lru_cache(maxsize=256)
def buscar(texto: str) -> Lugar | None:
    """País, estado, mar, río o ciudad por su nombre (en español o inglés)."""
    if not texto:
        return None
    partes = [p.strip() for p in str(texto).split(",") if p.strip()]
    n = _norm(partes[0])
    n = ALIAS.get(n, n)
    pais = _norm(partes[-1]) if len(partes) > 1 else ""
    pais = ALIAS.get(pais, pais)
    try:
        de_pais = _nombres_de_pais(pais)
        primero_agua = re.match(r"(rio|river|oceano|ocean|mar|sea|golfo|gulf|lago|lake|canal|estrecho) ", n)
        agua = [(_rios, "rio"), (_mares, "mar")] if re.match(r"(rio|river) ", n) else [(_mares, "mar"), (_rios, "rio")]

        def en_agua():
            corto = re.sub(r"^(rio|river|oceano|ocean|mar|sea|golfo|gulf|lago|lake) ", "", n)
            for capa, tipo in agua:
                x = _buscar_en(capa(), n) or _buscar_en(capa(), corto)
                if x:
                    return Lugar(x[1], x[2], tipo)
            return None

        if primero_agua:
            hallado = en_agua()
            if hallado:
                return hallado
        if len(partes) == 1:
            x = _buscar_en(_paises(), n)
            if x:
                return Lugar(x[1], x[2], "pais")
        ciudades = [c for c in _ciudades() if n in c[0] and (not de_pais or c[2] in de_pais)]
        grande = max(ciudades, key=lambda c: c[3]) if ciudades else None
        x = _buscar_en(_estados(), n, pais)
        estado_ok = x and (not de_pais or x[2] in de_pais)
        # "Veracruz, México" es el estado; "Sevilla, España" o "Ciudad de México" son ciudades.
        if estado_ok and not (grande and grande[3] > 1_500_000 and n not in {_norm(x[1])}):
            return Lugar(x[1], x[3], "estado")
        if grande:
            return Lugar(grande[1], None, "ciudad", (grande[4], grande[5]))
        if estado_ok:
            return Lugar(x[1], x[3], "estado")
        hallado = None if primero_agua else en_agua()
        if hallado:
            return hallado
    except Exception as e:
        logger.warning(f"Mapa: datos de Natural Earth no disponibles ({e})")
    # Lo que no está en Natural Earth (municipios, ciudades, islas, parques...): su contorno de
    # OpenStreetMap (idea de ficha_lugar.py); si no tiene contorno, un punto.
    forma = contorno_osm(texto)
    if forma is not None:
        return Lugar(partes[0], forma, "estado")
    try:
        from fabrica import mapas
        lat, lon, nombre = mapas.geocodificar(texto)
        return Lugar(partes[0], None, "punto", (lon, lat))
    except Exception:
        logger.warning(f"Mapa: no encontré '{texto}'")
        return None


def contorno_osm(texto: str):
    try:
        import time
        time.sleep(1.1)  # Nominatim pide máximo una consulta por segundo
        r = requests.get("https://nominatim.openstreetmap.org/search", headers=CABECERAS, timeout=30,
                         params={"q": texto, "format": "json", "limit": 3, "polygon_geojson": 1,
                                 "polygon_threshold": 0.005, "accept-language": "es"})
        for x in (r.json() if r.ok else []):
            g = x.get("geojson") or {}
            if g.get("type") in ("Polygon", "MultiPolygon"):
                return _forma(g)
    except Exception:
        pass
    return None


def frontera(a: Lugar, b: Lugar):
    """La línea que comparten dos lugares (si no se tocan, el borde del primero)."""
    if a.forma is None:
        return None
    try:
        if b and b.forma is not None:
            linea = a.forma.boundary.intersection(b.forma.buffer(0.08))
            if not linea.is_empty and linea.length > 0.3:
                return linea
        return a.forma.boundary
    except Exception:
        return a.forma.boundary


# ---------------------------------------------------------------- mapa base

def _mundo(lon: float, lat: float, z: float) -> tuple[float, float]:
    n = TESELA * 2 ** z
    x = (lon + 180) / 360 * n
    rad = math.radians(max(-85.0, min(85.0, lat)))
    y = (1 - math.log(math.tan(rad) + 1 / math.cos(rad)) / math.pi) / 2 * n
    return x, y


def _lonlat(x: float, y: float, z: float) -> tuple[float, float]:
    n = TESELA * 2 ** z
    lon = x / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


_PLANTILLA = {"url": None, "probada": False}


def _tesela_nasa(z: int, x: int, y: int) -> Image.Image | None:
    plantillas = [_PLANTILLA["url"]] if _PLANTILLA["url"] else ([] if _PLANTILLA["probada"] else TESELAS_NASA)
    for url in plantillas:
        try:
            r = requests.get(url.format(z=z, x=x, y=y), headers=CABECERAS, timeout=20)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                _PLANTILLA["url"] = url
                return Image.open(BytesIO(r.content)).convert("RGB")
        except requests.RequestException:
            pass
    if not _PLANTILLA["url"]:
        if not _PLANTILLA["probada"]:
            logger.warning("Mapa: NASA no respondió; se dibuja el mapa con los contornos de Natural Earth")
        _PLANTILLA["probada"] = True
    return None


def _tesela_dibujada(z: int, x: int, y: int) -> Image.Image:
    """Mapa propio: océano azul con relieve suave y tierra verde/café."""
    img = Image.new("RGB", (TESELA, TESELA), (14, 52, 92))
    d = ImageDraw.Draw(img)
    for k in range(0, TESELA, 8):  # degradado leve del océano
        d.line([(0, k), (TESELA, k)], fill=(14, 52 + (k % 32) // 16, 92 + (k % 64) // 32))
    try:
        from shapely.geometry import box
        lon0, lat1 = _lonlat(x * TESELA, y * TESELA, z)
        lon1, lat0 = _lonlat((x + 1) * TESELA, (y + 1) * TESELA, z)
        caja = box(lon0 - 0.5, lat0 - 0.5, lon1 + 0.5, lat1 + 0.5)
        for _, _, forma in _paises():
            if not forma.intersects(caja):
                continue
            for poligono in getattr(forma, "geoms", [forma]):
                if not poligono.intersects(caja):
                    continue
                puntos = [(_mundo(lo, la, z)[0] - x * TESELA, _mundo(lo, la, z)[1] - y * TESELA)
                          for lo, la in poligono.exterior.coords]
                if len(puntos) > 2:
                    d.polygon(puntos, fill=(92, 122, 68), outline=(140, 160, 110))
    except Exception:
        pass
    return img


@lru_cache(maxsize=1500)
def _tesela(z: int, x: int, y: int) -> Image.Image:
    n = 2 ** z
    return _tesela_nasa(z, x % n, y) or _tesela_dibujada(z, x % n, y)


def base(cam: tuple[float, float, float]) -> Image.Image:
    """El mapa satelital que ve la cámara (lon, lat, zoom con decimales)."""
    lon, lat, z = cam
    zi = max(0, min(8, math.ceil(z - 0.15)))
    escala = 2 ** (z - zi)                       # < 1 se ve más lejos que el nivel zi
    w, h = ANCHO / escala, ALTO / escala
    cx, cy = _mundo(lon, lat, zi)
    x0, y0 = cx - w / 2, cy - h / 2
    lienzo = Image.new("RGB", (int(w) + 2, int(h) + 2), (14, 52, 92))
    for tx in range(int(x0 // TESELA), int((x0 + w) // TESELA) + 1):
        for ty in range(int(y0 // TESELA), int((y0 + h) // TESELA) + 1):
            if 0 <= ty < 2 ** zi:
                lienzo.paste(_tesela(zi, tx, ty), (int(tx * TESELA - x0), int(ty * TESELA - y0)))
    return lienzo.resize((ANCHO, ALTO), Image.BILINEAR)


# ---------------------------------------------------------------- dibujo

def _suave(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _rebote(t: float) -> float:
    """0 → 1 pasándose un poco (efecto pop)."""
    t = max(0.0, min(1.0, t))
    return 1 + 2.2 * (t - 1) ** 3 + 1.2 * (t - 1) ** 2 if t < 1 else 1.0


@lru_cache(maxsize=16)
def _letra(tam: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(NEGRITA), tam)
    except OSError:
        return ImageFont.load_default()


@lru_cache(maxsize=128)
def _emoji(caracter: str, tam: int) -> Image.Image | None:
    for ruta in EMOJIS:
        if ruta.exists():
            try:
                letra = ImageFont.truetype(str(ruta), 109)
                img = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
                ImageDraw.Draw(img).text((80, 80), caracter, font=letra, embedded_color=True, anchor="mm")
                caja = img.getbbox()
                if not caja:
                    return None
                img = img.crop(caja)
                return img.resize((tam, int(tam * img.height / img.width)), Image.LANCZOS)
            except Exception:
                return None
    return None


def _texto(capa: Image.Image, xy, texto: str, tam: int, color=(255, 255, 255), alfa=1.0,
           giro: float = 0.0, brillo=None):
    """Texto grueso con borde negro; con giro sale inclinado como en los canales de mapas."""
    if alfa <= 0.01 or tam < 6 or not texto:
        return
    letra = _letra(int(tam))
    borde = max(2, int(tam / 9))
    cuadro = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), texto, font=letra, stroke_width=borde)
    w, h = cuadro[2] - cuadro[0] + 20, cuadro[3] - cuadro[1] + 20
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    a = int(255 * alfa)
    if brillo:
        d.text((w / 2, h / 2), texto, font=letra, fill=brillo + (a,), anchor="mm", stroke_width=borde * 3,
               stroke_fill=brillo + (int(a * 0.5),))
        img = img.filter(ImageFilter.GaussianBlur(max(2, tam / 10)))
        d = ImageDraw.Draw(img)
    d.text((w / 2, h / 2), texto, font=letra, fill=color + (a,), anchor="mm", stroke_width=borde,
           stroke_fill=(10, 10, 10, a))
    if giro:
        img = img.rotate(giro, expand=True, resample=Image.BICUBIC)
    if img.width > capa.width - 16:  # nunca más ancho que la pantalla
        img = img.resize((capa.width - 16, max(1, int(img.height * (capa.width - 16) / img.width))))
    # Que no se salga por los bordes (si el lugar está en la orilla, el nombre se corre hacia adentro);
    # si el lugar está lejos de la pantalla, no se dibuja.
    if not (-img.width / 2 < xy[0] < capa.width + img.width / 2 and -img.height < xy[1] < capa.height + img.height):
        return
    x = min(max(xy[0], img.width / 2 + 8), capa.width - img.width / 2 - 8)
    y = min(max(xy[1], img.height / 2 + 8), capa.height - img.height / 2 - 8)
    capa.alpha_composite(img, (int(x - img.width / 2), int(y - img.height / 2)))


class Proyector:
    def __init__(self, cam):
        self.lon, self.lat, self.z = cam
        self.cx, self.cy = _mundo(self.lon, self.lat, self.z)

    def __call__(self, lon, lat):
        x, y = _mundo(lon, lat, self.z)
        dx = x - self.cx
        mundo = TESELA * 2 ** self.z
        if dx > mundo / 2:
            dx -= mundo
        elif dx < -mundo / 2:
            dx += mundo
        return dx + ANCHO / 2, y - self.cy + ALTO / 2

    def anillos(self, forma, minimo=1.5):
        """Contornos de la forma en pantalla (se saltan islas diminutas)."""
        for poligono in getattr(forma, "geoms", [forma]):
            if poligono.geom_type != "Polygon":
                continue
            puntos = [self(lo, la) for lo, la in poligono.exterior.coords]
            xs, ys = [p[0] for p in puntos], [p[1] for p in puntos]
            if max(xs) - min(xs) < minimo and max(ys) - min(ys) < minimo:
                continue
            if max(xs) < -50 or min(xs) > ANCHO + 50 or max(ys) < -50 or min(ys) > ALTO + 50:
                continue
            yield puntos

    def lineas(self, forma):
        for parte in getattr(forma, "geoms", [forma]):
            if parte.geom_type == "LineString":
                yield [self(lo, la) for lo, la in parte.coords]
            elif parte.geom_type == "Polygon":
                yield [self(lo, la) for lo, la in parte.exterior.coords]
            elif hasattr(parte, "geoms"):
                yield from self.lineas(parte)


def _rellenar(capa, brillo, proy, forma, color, alfa):
    d = ImageDraw.Draw(capa)
    db = ImageDraw.Draw(brillo)
    for puntos in proy.anillos(forma):
        d.polygon(puntos, fill=color + (int(150 * alfa),))
        d.line(puntos + [puntos[0]], fill=(255, 255, 255, int(220 * alfa)), width=2)
        db.line(puntos + [puntos[0]], fill=color + (int(255 * alfa),), width=6)


def _linea_parcial(puntos, fraccion):
    if fraccion >= 1 or len(puntos) < 2:
        return puntos
    largos = [math.dist(puntos[k], puntos[k + 1]) for k in range(len(puntos) - 1)]
    meta, acumulado, salida = sum(largos) * fraccion, 0.0, [puntos[0]]
    for k, l in enumerate(largos):
        if acumulado + l >= meta:
            f = (meta - acumulado) / l if l else 0
            salida.append((puntos[k][0] + (puntos[k + 1][0] - puntos[k][0]) * f,
                           puntos[k][1] + (puntos[k + 1][1] - puntos[k][1]) * f))
            return salida
        acumulado += l
        salida.append(puntos[k + 1])
    return salida


def _puntos_dentro(forma, cantidad: int, semilla: int) -> list[tuple[float, float]]:
    """Lugares para los iconos dentro de la región, separados entre sí y de la etiqueta."""
    from shapely.geometry import Point
    rnd = random.Random(semilla)
    x0, y0, x1, y1 = forma.bounds
    rp = forma.representative_point()
    etiqueta = (rp.x, rp.y)
    lado = max(x1 - x0, y1 - y0)
    salida = []
    for _ in range(cantidad * 60):
        p = (rnd.uniform(x0, x1), rnd.uniform(y0, y1))
        if (forma.contains(Point(p)) and math.dist(p, etiqueta) > lado / 5
                and all(math.dist(p, q) > lado / 6 for q in salida)):
            salida.append(p)
            if len(salida) == cantidad:
                break
    return salida or [(forma.representative_point().x, forma.representative_point().y)]


# ---------------------------------------------------------------- escenas

def _color(nombre, k=0):
    if isinstance(nombre, (list, tuple)) and len(nombre) == 3:
        return tuple(int(c) for c in nombre)
    return COLORES.get(_norm(nombre or ""), COLORES[ORDEN_COLORES[k % len(ORDEN_COLORES)]])


def preparar(m: dict) -> dict:
    """Convierte lo que escribió la IA en capas con sus formas ya buscadas."""
    capas, formas = [], []

    def item(x):
        return {"lugar": x} if isinstance(x, str) else dict(x or {})

    for k, r in enumerate(m.get("resaltar") or []):
        r = item(r)
        lugar = buscar(r.get("lugar", ""))
        if lugar and lugar.forma is not None:
            capas.append({"tipo": "relleno", "forma": lugar.forma, "color": _color(r.get("color"), k + 5),
                          "etiqueta": r.get("etiqueta") or "", "punto": lugar.punto})
            formas.append(lugar)
        elif lugar:
            capas.append({"tipo": "punto", "punto": lugar.punto, "texto": r.get("etiqueta") or lugar.nombre})
            formas.append(lugar)
    for k, reg in enumerate(m.get("regiones") or []):
        reg = item(reg)
        partes = [buscar(f"{e}, {reg.get('pais', '')}".strip(", ")) for e in reg.get("estados") or []]
        partes = [p for p in partes if p and p.forma is not None]
        if not partes:
            continue
        from shapely.ops import unary_union
        forma = unary_union([p.forma for p in partes]).buffer(0.02).buffer(-0.02)
        lugar = Lugar(reg.get("nombre", ""), forma, "region")
        capas.append({"tipo": "relleno", "forma": forma, "color": _color(reg.get("color"), k),
                      "etiqueta": reg.get("nombre", ""), "punto": lugar.punto,
                      "iconos": [(e, p) for e, p in zip(reg.get("iconos") or [],
                                                         _puntos_dentro(forma, len(reg.get("iconos") or []), k))]})
        formas.append(lugar)
    f = m.get("frontera")
    if f:
        f = {"entre": f} if isinstance(f, list) else item(f) if not isinstance(f, dict) else f
        entre = f.get("entre") or ([f["lugar"]] if f.get("lugar") else [])
        a = buscar(entre[0]) if entre else None
        b = buscar(entre[1]) if len(entre) > 1 else None
        linea = frontera(a, b) if a else None
        if linea is not None and not linea.is_empty:
            mitad = linea.interpolate(0.5, normalized=True) if hasattr(linea, "interpolate") else None
            capas.append({"tipo": "linea", "forma": linea, "color": _color(f.get("color") or "amarillo"),
                          "texto": f.get("dato") or "", "punto": (mitad.x, mitad.y) if mitad else a.punto})
            formas.append(Lugar("frontera", linea.envelope, "linea"))
    ruta = m.get("ruta")
    if ruta:
        ruta = {"lugares": ruta} if isinstance(ruta, list) else ruta
        paradas = [buscar(x) for x in ruta.get("lugares") or []]
        paradas = [p for p in paradas if p]
        if len(paradas) >= 2:
            capas.append({"tipo": "ruta", "puntos": [p.punto for p in paradas], "texto": ruta.get("texto") or "",
                          "nombres": [p.nombre for p in paradas]})
            formas += paradas
    for p in m.get("puntos") or []:
        p = item(p)
        lugar = buscar(p.get("lugar", ""))
        if lugar:
            capas.append({"tipo": "punto", "punto": lugar.punto, "texto": p.get("texto") or lugar.nombre,
                          "icono": p.get("icono") or ""})
            formas.append(lugar)
    for e in m.get("etiquetas") or []:
        e = item(e)
        lugar = buscar(e.get("lugar", ""))
        if lugar:
            capas.append({"tipo": "etiqueta", "punto": lugar.punto, "texto": e.get("texto") or lugar.nombre})
    if m.get("nombres_estados"):
        pais = _norm(ALIAS.get(_norm(m["nombres_estados"]), m["nombres_estados"]))
        try:
            pais_lugar = buscar(m["nombres_estados"])
            for nombres, mostrar, de_pais, forma in _estados():
                if pais in de_pais or (pais_lugar and pais_lugar.forma is not None
                                       and pais_lugar.forma.contains(forma.representative_point())):
                    capas.append({"tipo": "nombre", "punto": (forma.representative_point().x,
                                                              forma.representative_point().y),
                                  "texto": str(mostrar).upper(), "forma": forma})
            if pais_lugar:
                formas.append(pais_lugar)
        except Exception as e:
            logger.warning(f"Mapa: sin nombres de estados ({e})")
    camara = buscar(m["camara"]) if isinstance(m.get("camara"), str) and m.get("camara") else None
    return {"capas": capas, "formas": [camara] if camara else formas, "pregunta": m.get("pregunta") or "",
            "mantener": bool(m.get("mantener")), "zoom": m.get("zoom")}


def encuadre(formas: list[Lugar], margen: float = 0.1, zoom=None) -> tuple[float, float, float] | None:
    cajas = [f.caja() for f in formas if f]
    if not cajas:
        return None
    lon0, lat0 = min(c[0] for c in cajas), min(c[1] for c in cajas)
    lon1, lat1 = max(c[2] for c in cajas), max(c[3] for c in cajas)
    if lon1 - lon0 > 300:  # cruza el meridiano 180: se toma el mundo
        lon0, lon1 = -170, 170
    x0, y0 = _mundo(lon0, lat1, 0)
    x1, y1 = _mundo(lon1, lat0, 0)
    ancho, alto = max(x1 - x0, 1e-4), max(y1 - y0, 1e-4)
    z = math.log2(min(ANCHO * (1 - 2 * margen) / ancho, ALTO * (1 - 2 * margen) / alto))
    if zoom is not None:
        try:
            z = float(zoom)
        except (TypeError, ValueError):
            pass
    lon, lat = _lonlat((x0 + x1) / 2, (y0 + y1) / 2, 0)
    return lon, lat, max(1.2, min(Z_MAX, z))


def _volar(a, b, t):
    """Cámara de a hacia b: se aleja un poco a mitad de camino si el salto es grande."""
    e = _suave(t)
    ax, ay = _mundo(a[0], a[1], 0)
    bx, by = _mundo(b[0], b[1], 0)
    x, y = ax + (bx - ax) * e, ay + (by - ay) * e
    z = a[2] + (b[2] - a[2]) * e
    distancia = math.hypot(bx - ax, by - ay) * 2 ** min(a[2], b[2]) / ANCHO
    z -= max(0.0, min(2.5, math.log2(1 + distancia))) * math.sin(math.pi * e) * 0.8
    lon, lat = _lonlat(x, y, 0)
    return lon, lat, z


def _dibujar(cuadro: Image.Image, cam, escena: dict, t: float, segundos: float, previas: list):
    proy = Proyector(cam)
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    brillo = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    textos = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    inicio = escena.get("_inicio", 0.25)
    capas = escena["capas"]
    hueco = (0.85 - inicio) / max(1, len(capas))
    for capa_previa in previas:
        _una_capa(capa_previa, 99, capa, brillo, textos, proy, segundos)
    for k, c in enumerate(capas):
        _una_capa(c, (t - (inicio + k * hueco)) * segundos, capa, brillo, textos, proy, segundos)
    if escena.get("pregunta"):
        aparece = (t - 0.08) * segundos
        if aparece > 0:
            _texto(textos, (ANCHO / 2, ALTO * 0.2), escena["pregunta"], 74 * _rebote(aparece / 0.45),
                   alfa=min(1.0, aparece / 0.2), giro=-8)
    brillo = brillo.filter(ImageFilter.GaussianBlur(6))
    cuadro = cuadro.convert("RGBA")
    cuadro.alpha_composite(brillo)
    cuadro.alpha_composite(brillo)
    cuadro.alpha_composite(capa)
    cuadro.alpha_composite(textos)
    d = ImageDraw.Draw(cuadro)
    credito = CREDITO if _PLANTILLA["url"] else "Natural Earth"
    d.text((ANCHO - 10, ALTO - 10), credito, font=_letra(14), fill=(255, 255, 255, 150), anchor="rd")
    return cuadro.convert("RGB")


def _una_capa(c: dict, edad: float, capa, brillo, textos, proy, segundos):
    """edad = segundos desde que aparece la capa (negativo: todavía no)."""
    if edad <= 0:
        return
    alfa = min(1.0, edad / 0.45)
    tipo = c["tipo"]
    if tipo == "relleno":
        _rellenar(capa, brillo, proy, c["forma"], c["color"], alfa)
        if c.get("etiqueta"):
            x, y = proy(*c["punto"])
            tam = max(28, min(72, 520 / max(4, len(c["etiqueta"]))))
            _texto(textos, (x, y), c["etiqueta"], tam * _rebote(edad / 0.4), alfa=alfa,
                   brillo=(255, 230, 120) if c.get("iconos") is not None else None,
                   giro=-12 if c.get("iconos") is None and len(c["etiqueta"]) > 5 else 0)
        for k, (emoji, punto) in enumerate(c.get("iconos") or []):
            e = edad - 0.35 - k * 0.3
            if e > 0:
                img = _emoji(emoji, int(max(8, 64 * _rebote(e / 0.35))))
                if img:
                    x, y = proy(*punto)
                    textos.alpha_composite(img, (int(x - img.width / 2), int(y - img.height / 2)))
    elif tipo == "linea":
        fraccion = _suave(edad / 1.6)
        d, db = ImageDraw.Draw(capa), ImageDraw.Draw(brillo)
        for puntos in proy.lineas(c["forma"]):
            parcial = _linea_parcial(puntos, fraccion)
            if len(parcial) > 1:
                db.line(parcial, fill=c["color"] + (255,), width=12)
                d.line(parcial, fill=c["color"] + (255,), width=4)
        if c.get("texto") and edad > 1.2:
            x, y = proy(*c["punto"])
            _texto(textos, (x + 40, y), c["texto"], 40 * _rebote((edad - 1.2) / 0.4), color=(255, 240, 150),
                   alfa=min(1.0, (edad - 1.2) / 0.3))
    elif tipo == "ruta":
        puntos = [proy(*p) for p in c["puntos"]]
        curva = []
        for a, b in zip(puntos, puntos[1:]):
            medio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - math.dist(a, b) * 0.25)
            curva += [((1 - s) ** 2 * a[0] + 2 * (1 - s) * s * medio[0] + s * s * b[0],
                       (1 - s) ** 2 * a[1] + 2 * (1 - s) * s * medio[1] + s * s * b[1])
                      for s in [i / 30 for i in range(31)]]
        parcial = _linea_parcial(curva, _suave(edad / 2.0))
        d, db = ImageDraw.Draw(capa), ImageDraw.Draw(brillo)
        if len(parcial) > 1:
            db.line(parcial, fill=(255, 255, 255, 255), width=10)
            d.line(parcial, fill=(255, 220, 60, 255), width=5)
            x, y = parcial[-1]
            d.ellipse([x - 9, y - 9, x + 9, y + 9], fill=(255, 255, 255, 255))
        for p, nombre in zip(puntos, c.get("nombres") or []):
            d.ellipse([p[0] - 7, p[1] - 7, p[0] + 7, p[1] + 7], fill=(229, 57, 53, 255),
                      outline=(255, 255, 255, 255), width=2)
            _texto(textos, (p[0], p[1] + 30), str(nombre)[:22], 26, alfa=alfa)
        if c.get("texto") and edad > 0.6:
            x, y = curva[len(curva) // 2]
            _texto(textos, (x, y - 40), c["texto"], 46 * _rebote((edad - 0.6) / 0.4), color=(255, 240, 150))
    elif tipo == "punto":
        x, y = proy(*c["punto"])
        caida = _suave(edad / 0.35)
        py = y - (1 - caida) * 60
        pulso = (edad * 1.4) % 1
        d = ImageDraw.Draw(capa)
        d.ellipse([x - 12 - 30 * pulso, y - 6 - 12 * pulso, x + 12 + 30 * pulso, y + 6 + 12 * pulso],
                  outline=(229, 57, 53, int(200 * (1 - pulso))), width=3)
        d.ellipse([x - 13, py - 44, x + 13, py - 18], fill=(229, 57, 53, 255))
        d.polygon([(x - 11, py - 26), (x + 11, py - 26), (x, py)], fill=(229, 57, 53, 255))
        d.ellipse([x - 5, py - 36, x + 5, py - 26], fill=(255, 255, 255, 255))
        if c.get("icono"):
            img = _emoji(c["icono"], int(max(8, 56 * _rebote(edad / 0.4))))
            if img:
                textos.alpha_composite(img, (int(x - img.width / 2), int(py - 70 - img.height / 2)))
        if c.get("texto"):
            _texto(textos, (x, y + 30), c["texto"], 34 * _rebote(edad / 0.4), alfa=alfa)
    elif tipo == "etiqueta":
        x, y = proy(*c["punto"])
        _texto(textos, (x, y), c["texto"], 30, color=(255, 255, 255), alfa=alfa * 0.95)
    elif tipo == "nombre":
        x, y = proy(*c["punto"])
        if -20 < x < ANCHO + 20 and -20 < y < ALTO + 20:
            d = ImageDraw.Draw(capa)
            for puntos in proy.anillos(c["forma"], 0):
                d.line(puntos + [puntos[0]], fill=(255, 255, 255, int(150 * alfa)), width=1)
            _texto(textos, (x, y), c["texto"], 16, color=(230, 255, 230), alfa=alfa)


class Estado:
    """Lo que se arrastra de una escena a la siguiente: dónde quedó la cámara y lo pintado."""

    def __init__(self):
        self.camara = None
        self.pintado: list[dict] = []


def clip(m: dict, segundos: float, aspecto: str, salida: Path, estado: Estado | None = None) -> Path:
    estado = estado or Estado()
    escena = preparar(m)
    destino = encuadre(escena["formas"], zoom=escena.get("zoom")) or estado.camara
    if destino is None:
        raise ValueError("el mapa no tiene ningún lugar que se encuentre")
    if estado.camara is None:  # primera escena: entra desde lejos, como un dron
        origen = (destino[0], destino[1] - 4, max(1.2, destino[2] - 2.2))
    else:
        origen = estado.camara
    vuelo = 0.28 if math.dist(origen[:2], destino[:2]) > 0.5 or abs(origen[2] - destino[2]) > 0.3 else 0.0
    escena["_inicio"] = max(0.12, vuelo * 0.85)
    previas = estado.pintado if escena["mantener"] else []
    W, H = TAMANOS.get(aspecto, TAMANOS["9:16"])
    cuadros = max(1, round(segundos * FPS))
    logger.info(f"Mapa geo: {len(escena['capas'])} capas, cámara {destino[1]:.1f},{destino[0]:.1f} z{destino[2]:.1f}")
    proceso = subprocess.Popen(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-",
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(salida)],
        stdin=subprocess.PIPE)
    cam = destino
    try:
        for n in range(cuadros):
            t = n / max(1, cuadros - 1)
            if vuelo and t < vuelo:
                cam = _volar(origen, destino, t / vuelo)
            else:  # después del vuelo, un acercamiento muy lento para que nunca esté quieto
                resto = (t - vuelo) / max(0.01, 1 - vuelo)
                cam = (destino[0], destino[1], destino[2] + 0.18 * _suave(resto))
            cuadro = _dibujar(base(cam), cam, escena, t, segundos, previas)
            proceso.stdin.write(cuadro.tobytes())
    finally:
        proceso.stdin.close()
    if proceso.wait() != 0:
        raise RuntimeError("ffmpeg no pudo crear el mapa")
    estado.camara = cam
    if escena["mantener"]:
        estado.pintado = previas + [c for c in escena["capas"] if c["tipo"] in ("relleno", "linea")]
    else:
        estado.pintado = [c for c in escena["capas"] if c["tipo"] in ("relleno", "linea")]
    return salida


def desde_grafica(g: dict) -> dict:
    """La gráfica tipo "mapa" de los otros estilos ({lugar, titulo, detalle}) al formato nuevo."""
    lugar = buscar(g.get("lugar", ""))
    titulo = (g.get("titulo") or g.get("lugar", "")).split(",")[0][:24]
    if lugar and lugar.forma is not None and lugar.tipo in ("pais", "estado"):
        return {"resaltar": [{"lugar": g["lugar"], "color": "amarillo", "etiqueta": titulo.upper()}],
                "pregunta": (g.get("detalle") or "")[:26].upper()}
    return {"puntos": [{"lugar": g.get("lugar", ""), "texto": titulo}],
            "pregunta": (g.get("detalle") or "")[:26].upper(), "zoom": 6.5}
