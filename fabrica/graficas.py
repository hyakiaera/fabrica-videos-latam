"""Gráficas animadas para escenas con datos: barras que crecen y cifras
grandes que cuentan. Solo se usan con números que vienen de las fuentes."""

import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from fabrica.config import RAIZ

FPS = 30
TAMANOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
NEGRITA = RAIZ / "resource" / "fonts" / "BeVietnamPro-Bold.ttf"
NORMAL = RAIZ / "resource" / "fonts" / "BeVietnamPro-Medium.ttf"

# Paleta por estilo: (fondo, tarjeta, texto, positivo, negativo, acento)
PALETAS = {
    "explicativo": ("#F6EFE6", "#FFFFFF", "#1E1E1E", "#2E9E5B", "#E5484D", "#F2B705"),
    "pizarra": ("#FAFAF7", "#FFFFFF", "#111111", "#2E9E5B", "#D93025", "#1A73E8"),
    "acuarela": ("#F4F1EA", "#FFFFFF", "#2B2B2B", "#4C9A6A", "#C8553D", "#7A9CC6"),
}
OSCURA = ("#0F1724", "#18233A", "#FFFFFF", "#22C55E", "#F43F5E", "#FACC15")


def _suave(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def _cabe(d: ImageDraw.ImageDraw, texto: str, letra: ImageFont.FreeTypeFont, ancho: float) -> ImageFont.FreeTypeFont:
    """La misma letra, achicada hasta que el texto quepa en el ancho (nada se sale de la tarjeta)."""
    tam = letra.size
    while tam > 18 and d.textlength(texto, font=letra) > ancho:
        tam = int(tam * 0.92)
        letra = ImageFont.truetype(letra.path, tam)
    return letra


def _numero(valor: float, unidad: str) -> str:
    texto = f"{valor:,.1f}".rstrip("0").rstrip(".") if abs(valor) < 100 else f"{valor:,.0f}"
    signo = "+" if valor > 0 and unidad == "%" else ""
    return f"{signo}{texto}{unidad}"


def _barras(d: ImageDraw.ImageDraw, g: dict, progreso: float, caja, paleta, letras):
    _, tarjeta, texto, positivo, negativo, _ = paleta
    x0, y0, x1, y1 = caja
    datos = [(str(n)[:18], float(v)) for n, v in g.get("datos", [])][:6]
    unidad = g.get("unidad", "")
    maximo = max(abs(v) for _, v in datos) or 1
    # Eje al centro solo si hay subidas y bajadas; si todo baja (o sube), barras hacia la derecha.
    mixto = any(v < 0 for _, v in datos) and any(v > 0 for _, v in datos)
    centro = x0 + 330 + ((x1 - x0 - 330) / 2 if mixto else 0)
    largo = (x1 - x0 - 330) / (2 if mixto else 1) - 170
    alto_fila = (y1 - y0) / max(1, len(datos))
    for k, (nombre, valor) in enumerate(datos):
        avance = _suave(progreso * 1.4 - k * 0.12)  # cada barra entra un poco después
        cy = y0 + alto_fila * (k + 0.5)
        d.text((x0, cy), nombre, font=_cabe(d, nombre, letras["fila"], 310), fill=texto, anchor="lm")
        ancho = largo * abs(valor) / maximo * avance
        color = negativo if valor < 0 else positivo
        izquierda = centro - ancho if (valor < 0 and mixto) else centro
        d.rounded_rectangle([izquierda, cy - alto_fila * 0.28, izquierda + max(ancho, 6), cy + alto_fila * 0.28],
                            14, fill=color)
        if avance > 0.2:
            etiqueta = _numero(valor * avance, unidad)
            if valor < 0 and mixto:
                d.text((izquierda - 14, cy), etiqueta, font=letras["valor"], fill=texto, anchor="rm")
            else:
                d.text((izquierda + ancho + 14, cy), etiqueta, font=letras["valor"], fill=texto, anchor="lm")
    d.line([centro, y0, centro, y1], fill=texto, width=3)


def _cifra(d: ImageDraw.ImageDraw, g: dict, progreso: float, caja, paleta, letras):
    _, _, texto, positivo, negativo, _ = paleta
    x0, y0, x1, y1 = caja
    valor = float(g.get("valor", (g.get("datos") or [["", 0]])[0][1]))
    color = negativo if valor < 0 else positivo
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # La cifra se mide con su valor FINAL, para que el tamaño no salte mientras cuenta.
    unidad = g.get("unidad", "")
    unidad = f" {unidad}" if unidad and unidad not in ("%", "$") and not unidad.startswith(" ") else unidad
    letra = _cabe(d, _numero(valor, unidad), letras["cifra"], x1 - x0)
    d.text((cx, cy - 40), _numero(valor * _suave(progreso * 1.3), unidad), font=letra, fill=color, anchor="mm")
    if g.get("detalle"):
        detalle = str(g["detalle"])[:60]
        d.text((cx, cy + 150), detalle, font=_cabe(d, detalle, letras["fila"], x1 - x0), fill=texto, anchor="mm")


def _tarjeta(d: ImageDraw.ImageDraw, g: dict, progreso: float, caja, paleta, letras):
    _, _, texto, _, _, acento = paleta
    x0, y0, x1, y1 = caja
    lineas = [str(l)[:34] for l in (g.get("lineas") or [])][:5]
    alto_linea = min(110, (y1 - y0) / max(1, len(lineas)))
    for k, linea in enumerate(lineas):
        aparece = _suave(progreso * 2.2 - k * 0.25)  # una línea tras otra
        if aparece <= 0:
            continue
        y = y0 + alto_linea * (k + 0.5) + (1 - aparece) * 30
        letra = letras["cifra_media"] if k == 0 and len(linea) <= 12 else letras["fila"]
        color = acento if k == 0 else texto
        d.text(((x0 + x1) / 2, y), linea, font=_cabe(d, linea, letra, x1 - x0), fill=color, anchor="mm")


def clip(g: dict, segundos: float, aspecto: str, estilo: str, salida: Path) -> Path:
    if g.get("tipo") == "mapa" and g.get("lugar"):
        # Primero el mapa satelital animado (estilo canales de geografía); si falla, el de calles.
        try:
            from fabrica import mapa_geo
            return mapa_geo.clip(mapa_geo.desde_grafica(g), segundos, aspecto, salida)
        except Exception as e:
            from loguru import logger
            logger.warning(f"Mapa satelital no disponible ({e}); se usa el mapa de calles")
        from fabrica import mapas
        return mapas.clip(g, segundos, aspecto, salida)
    if g.get("tipo") not in ("barras", "cifra", "tarjeta") or (g["tipo"] == "barras" and not g.get("datos")):
        raise ValueError("gráfica sin datos")
    ancho, alto = TAMANOS.get(aspecto, TAMANOS["9:16"])
    paleta = PALETAS.get(estilo, OSCURA)
    fondo, tarjeta, texto, _, _, acento = paleta
    letras = {"titulo": ImageFont.truetype(str(NEGRITA), 64), "fila": ImageFont.truetype(str(NEGRITA), 46),
              "valor": ImageFont.truetype(str(NORMAL), 44), "cifra": ImageFont.truetype(str(NEGRITA), 230),
              "fuente": ImageFont.truetype(str(NORMAL), 30),
              "cifra_media": ImageFont.truetype(str(NEGRITA), 120)}
    # La tarjeta queda en la parte de arriba para no chocar con los subtítulos.
    # Arriba: debajo queda el logo (centro izquierda, ~45 %) y más abajo los subtítulos (~72 %).
    tarjeta_caja = (60, alto * 0.07, ancho - 60, alto * 0.42)
    caja = (tarjeta_caja[0] + 50, tarjeta_caja[1] + 170, tarjeta_caja[2] - 50, tarjeta_caja[3] - 90)
    cuadros = max(1, round(segundos * FPS))
    proceso = subprocess.Popen(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{ancho}x{alto}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "20", "-pix_fmt", "yuv420p", str(salida)], stdin=subprocess.PIPE)
    for n in range(cuadros):
        t = n / FPS
        entrada = _suave(t / 0.5)  # la tarjeta sube y aparece en medio segundo
        img = Image.new("RGB", (ancho, alto), fondo)
        d = ImageDraw.Draw(img)
        desplazamiento = (1 - entrada) * 80
        x0, y0, x1, y1 = tarjeta_caja
        d.rounded_rectangle([x0, y0 + desplazamiento, x1, y1 + desplazamiento], 40, fill=tarjeta)
        d.rounded_rectangle([x0 + 50, y0 + 60 + desplazamiento, x0 + 70, y0 + 130 + desplazamiento], 6, fill=acento)
        titulo = str(g.get("titulo", ""))[:40]
        d.text((x0 + 95, y0 + 95 + desplazamiento), titulo, font=_cabe(d, titulo, letras["titulo"], x1 - x0 - 130),
               fill=texto, anchor="lm")
        progreso = max(0.0, (t - 0.4) / max(0.6, segundos * 0.6))
        dibujo = {"barras": _barras, "cifra": _cifra, "tarjeta": _tarjeta}[g["tipo"]]
        dibujo(d, g, progreso, (caja[0], caja[1] + desplazamiento, caja[2], caja[3] + desplazamiento),
               paleta, letras)
        if g.get("fuente"):
            d.text((x0 + 50, y1 - 45 + desplazamiento), f"Fuente: {g['fuente']}"[:60], font=letras["fuente"],
                   fill=texto)
        proceso.stdin.write(img.tobytes())
    proceso.stdin.close()
    if proceso.wait() != 0:
        raise RuntimeError("ffmpeg no pudo crear la gráfica")
    return salida
