"""Campañas: un tema que ocupa parte de los videos automáticos entre dos fechas, y se apaga
solo al terminar. La primera es GTA 6 (sale el 19 de noviembre de 2026):

    - 2 videos al día de GTA desde el 13 hasta el 30 de noviembre
    - el 19 de noviembre (lanzamiento) TODOS los videos del día son de GTA 6
    - noticias de lo más actual (buscadas en el momento), trucos, datos, despedida de GTA 5,
      historia de la saga y rankings
    - usa tus fotos y videos de Drive (mis fotos › gta; a los videos se les quita el audio)
      y además imágenes generadas en estilo videojuego
    - miniaturas con colores neón

Para cambiar fechas o cantidades: [campana] en fabrica.toml (ver FABRICA.md) o edita CAMPANAS.
"""
import math
import random
from datetime import date, datetime, timedelta

from loguru import logger

CAMPANAS = [
    {
        "nombre": "gta",
        "categoria": "gaming",
        "desde": "2026-11-13",
        "hasta": "2026-11-30",
        "por_dia": 2,
        "dias": {"2026-11-19": 5},          # lanzamiento: todos los videos del día
        "lanzamiento": "2026-11-19",
        "carpeta_fotos": "gta",
        "estilo": "videojuego",
        "consultas": ["GTA 6", "GTA VI Rockstar Games", "GTA 6 noticias", "GTA 6 tráiler",
                      "GTA 6 precio", "GTA 5 Online", "Rockstar Games GTA"],
        "consultas_lanzamiento": ["GTA 6 lanzamiento", "GTA 6 reseñas", "GTA 6 ventas", "GTA 6 récord",
                                  "GTA 6 problemas", "GTA 6 jugadores", "GTA 6 Vice City", "GTA VI review"],
        "enfoque": ("videojuegos: TODO sobre GTA 6 y la saga Grand Theft Auto. Noticias de lo más reciente "
                    "(fecha, precio, tráiler, filtraciones, lo que se dice en redes), trucos y claves, datos "
                    "curiosos (ventas, récords, costo), despedida de GTA 5 (lo mejor de sus años), historia de la "
                    "saga (de GTA 1 a GTA 6, ciudades reales en que se inspiran) y rankings (top 5)."),
        "enfoque_lanzamiento": ("¡GTA 6 YA SALIÓ! Lo que está pasando AHORA con el lanzamiento: primeras horas de "
                                "juego, reseñas y calificaciones, récords de ventas, filas y problemas en tiendas o "
                                "servidores, reacciones de jugadores y famosos, primeros secretos y trucos "
                                "descubiertos, comparación con GTA 5. Siempre lo más actual de las noticias."),
        "ideas": ["los mejores trucos y claves de GTA 5 que todavía funcionan",
                  "despedida de GTA 5: los momentos más icónicos de sus años",
                  "historia de la saga GTA de 1997 a GTA 6",
                  "Vice City: la Miami real detrás de GTA 6",
                  "cuánto costó hacer GTA 6 comparado con películas de Hollywood",
                  "top 5 personajes más recordados de GTA",
                  "secretos y easter eggs que casi nadie encontró en GTA 5",
                  "récords de ventas de GTA 5 que GTA 6 quiere romper",
                  "Jason y Lucía: lo que se sabe de los protagonistas de GTA 6",
                  "GTA San Andreas: por qué sigue siendo el favorito de los latinos"],
        "miniatura": {"color_1": "#FF2E88", "color_2": "#22D3EE", "marco": "#FF2E88"},
    },
]

ZONA_HORAS = -6  # hora de México / Centroamérica (los horarios de las rondas están en esa hora)
# Horas (locales) de las rondas automáticas, según el workflow.
RONDAS = {"semana": [7, 12, 16, 22], "finde": [7, 11, 15, 19, 22]}


def ahora_local() -> datetime:
    return datetime.utcnow() + timedelta(hours=ZONA_HORAS)


def activa(cfg: dict, cuando: datetime | None = None) -> dict | None:
    """La campaña que corre hoy (o None). [campana] activa = false la apaga."""
    ajustes = cfg.get("campana", {})
    if ajustes.get("activa") is False:
        return None
    hoy = (cuando or ahora_local()).date()
    for c in CAMPANAS:
        c = {**c, **{k: v for k, v in ajustes.items() if k != "activa"}}
        if date.fromisoformat(c["desde"]) <= hoy <= date.fromisoformat(c["hasta"]):
            return c
    return None


def cuota(c: dict, dia: date) -> int:
    return int(c.get("dias", {}).get(dia.isoformat(), c.get("por_dia", 2)))


def hechos_hoy(historial: list[dict], c: dict, dia: date) -> int:
    n = 0
    for e in historial[-60:]:
        if e.get("mezcla") != c["nombre"]:
            continue
        try:
            # El historial guarda la hora del servidor (UTC en GitHub): se pasa a la hora local.
            local = datetime.fromisoformat(e.get("fecha", "")) + timedelta(hours=ZONA_HORAS)
        except ValueError:
            continue
        if local.date() == dia:
            n += 1
    return n


def rondas_restantes(cuando: datetime) -> int:
    """Cuántas rondas automáticas quedan hoy contando esta (GitHub a veces se atrasa: margen de 2 h)."""
    horas = RONDAS["finde" if cuando.weekday() >= 5 else "semana"]
    return max(1, sum(1 for h in horas if h >= cuando.hour - 2))


def cuantos_ahora(cfg: dict, historial: list[dict], cuando: datetime | None = None) -> int:
    """Cuántos videos de la campaña hace ESTA ronda. Se reparten en el día; el día especial
    (lanzamiento) una ronda puede hacer 2 para llegar a la cuota."""
    cuando = cuando or ahora_local()
    c = activa(cfg, cuando)
    if not c:
        return 0
    faltan = cuota(c, cuando.date()) - hechos_hoy(historial, c, cuando.date())
    if faltan <= 0:
        return 0
    quedan = rondas_restantes(cuando)
    if faltan >= quedan:
        return min(3, math.ceil(faltan / quedan))
    return 1 if random.random() < faltan / quedan else 0


def temas(cfg: dict, c: dict, cantidad: int, historial: list[dict], cuando: datetime | None = None) -> list[dict]:
    """Temas de la campaña: noticias de AHORA y, fuera del lanzamiento, también ideas fijas
    (trucos, despedida de GTA 5, historia...). Nunca repite lo que ya se hizo."""
    from fabrica import mezcla, tendencias

    cuando = cuando or ahora_local()
    lanzado = cuando.date() >= date.fromisoformat(c.get("lanzamiento", "2999-01-01"))
    recientes = [e.get("tema", "") for e in historial]
    consultas = c["consultas_lanzamiento"] if lanzado else c["consultas"]
    enfoque = c["enfoque_lanzamiento"] if lanzado else c["enfoque"]
    elegidos: list[dict] = []
    for _ in range(cantidad):
        usar_idea = not lanzado and random.random() < 0.4
        opciones: list[dict] = []
        try:
            if usar_idea:
                idea = random.choice([i for i in c["ideas"] if not mezcla.repetido(i, historial, dias=30)]
                                     or c["ideas"])
                opciones = [{"tema": idea, "categoria": c["categoria"], "estilo": c["estilo"],
                             "por_que": "idea de la campaña", "fuentes": tendencias.buscar_noticias(idea)}]
            else:
                lista = []
                for consulta in random.sample(consultas, min(5, len(consultas))):
                    for titulo, medio, url in tendencias.buscar_noticias(consulta, 8):
                        lista.append(tendencias.Candidato(titulo=titulo, origen="news", pais="MX", idioma="es",
                                                          categoria=c["categoria"], titulares=[(titulo, medio, url)]))
                if lista:
                    opciones = tendencias.elegir_temas(cfg, lista, 3, recientes, c["estilo"], enfoque=enfoque)
        except Exception as e:
            logger.warning(f"Campaña {c['nombre']}: no se pudo elegir tema ({e})")
        for t in opciones:
            ya = historial + [{"tema": x["tema"]} for x in elegidos]
            if t.get("tema") and not mezcla.repetido(t["tema"], ya):
                t.update(mezcla=c["nombre"], categoria=c["categoria"], estilo=c["estilo"], campana=c["nombre"],
                         carpetas_fotos=[c["carpeta_fotos"]], miniatura=c.get("miniatura", {}))
                elegidos.append(t)
                recientes.append(t["tema"])
                break
    if elegidos:
        logger.info(f"Campaña {c['nombre']}: {len(elegidos)} video(s) en esta ronda — "
                    + "; ".join(t["tema"] for t in elegidos))
    return elegidos
