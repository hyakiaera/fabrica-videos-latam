"""Looks de edición: cada video sale con una combinación distinta de letra, color, tamaño y
posición de subtítulos, para que el canal no se vea siempre igual. No repite los últimos."""
import json
import random

from fabrica.config import RAIZ

LOOKS = {
    "clasico": dict(font_name="BeVietnamPro-Bold.ttf", text_fore_color="#FFFFFF", stroke_color="#000000",
                    font_size=70, stroke_width=2.5, custom_position=72),
    "amarillo": dict(font_name="Montserrat-ExtraBold.ttf", text_fore_color="#FFE14D", stroke_color="#000000",
                     font_size=76, stroke_width=3.0, custom_position=70),
    "caja_negra": dict(font_name="Montserrat-Bold.ttf", text_fore_color="#FFFFFF", stroke_color="#000000",
                       font_size=62, stroke_width=0.0, custom_position=74, text_background_color="#000000",
                       rounded_subtitle_background=True),
    "verde_neon": dict(font_name="Montserrat-ExtraBold.ttf", text_fore_color="#3CFF8F", stroke_color="#0B0B0B",
                       font_size=72, stroke_width=3.0, custom_position=68),
    "grande_centro": dict(font_name="UTM Kabel KT.ttf", text_fore_color="#FFFFFF", stroke_color="#000000",
                          font_size=84, stroke_width=4.0, custom_position=62),
    "caja_roja": dict(font_name="Montserrat-Bold.ttf", text_fore_color="#FFFFFF", stroke_color="#000000",
                      font_size=60, stroke_width=0.0, custom_position=74, text_background_color="#D32F2F",
                      rounded_subtitle_background=True),
    "celeste": dict(font_name="Montserrat-ExtraBold.ttf", text_fore_color="#7FD8FF", stroke_color="#00111F",
                    font_size=74, stroke_width=3.0, custom_position=70),
}


def recientes(cuantos: int = 3) -> list[str]:
    try:
        entradas = json.loads((RAIZ / "estado" / "historial.json").read_text(encoding="utf-8"))
        return [e.get("edicion", "") for e in entradas[-cuantos:] if e.get("edicion")]
    except Exception:
        return []


def elegir(evitar: list[str] | None = None) -> tuple[str, dict]:
    evitar = set(evitar if evitar is not None else recientes())
    opciones = [k for k in LOOKS if k not in evitar] or list(LOOKS)
    nombre = random.choice(opciones)
    return nombre, dict(LOOKS[nombre])
