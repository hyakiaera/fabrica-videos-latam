"""Ganchos que retienen: fórmulas probadas, calificación del gancho y limpieza de frases
"de robot". (Ideas generales tomadas del proyecto instagram-agent-skill, licencia MIT;
todo escrito aquí en español para videos latinos de noticias, deportes, finanzas y curiosidades.)

Cómo se usa en la fábrica:
  1. Por cada video se eligen 3 fórmulas al azar y el guionista escribe un gancho con cada una.
  2. Aquí se califican (0-100) y el mejor queda como primera frase del video, con su texto
     corto para la pantalla.
  3. El guion se limpia de muletillas de IA ("cabe destacar", "sumérgete", rayas largas...).
"""
import random
import re

# Fórmulas de gancho: plantilla, ejemplo, texto corto para la pantalla y la trampa a evitar.
FORMULAS = [
    {"nombre": "La cifra que duele", "plantilla": "{cifra concreta} es lo que {cosa} le costó a {quién}.",
     "ejemplo": "Treinta millones de dólares. Eso le costó al América un solo error.",
     "pantalla": "$30 MILLONES", "trampa": "una cifra inventada o vaga ('muchísimo dinero')"},
    {"nombre": "Nadie te dice", "plantilla": "Nadie te dice que {verdad incómoda del tema}.",
     "ejemplo": "Nadie te dice que el bitcoin cae justo cuando todos dicen que va a subir.",
     "pantalla": "NADIE TE LO DICE", "trampa": "una 'verdad' que todos ya saben"},
    {"nombre": "Deja de", "plantilla": "Deja de {hábito común}. Haz {alternativa}.",
     "ejemplo": "Deja de comprar en la primera tienda que ves. Esta app te muestra el precio más bajo.",
     "pantalla": "DEJA DE HACER ESTO", "trampa": "pedir que dejen algo que nadie hace"},
    {"nombre": "En medio de la acción", "plantilla": "...y justo ahí {el giro}.",
     "ejemplo": "Minuto noventa, estadio en silencio... y entonces pasó esto.",
     "pantalla": "MINUTO 90", "trampa": "no explicar el inicio antes del segundo 8"},
    {"nombre": "El dato que se repite en la cena", "plantilla": "{N}% de {grupo} {dato sorprendente}.",
     "ejemplo": "El 70 % de los mexicanos no sabe cuánto paga de comisión en su banco.",
     "pantalla": "70% NO LO SABE", "trampa": "un porcentaje sin fuente"},
    {"nombre": "Antes y ahora", "plantilla": "Antes {situación}. Hoy {situación nueva}.",
     "ejemplo": "Hace un año costaba veinte mil dólares. Hoy vale ochenta mil.",
     "pantalla": "$20K → $80K", "trampa": "un cambio que no se puede creer"},
    {"nombre": "Cara a cara", "plantilla": "{A} contra {B}. Y no estuvo ni cerca.",
     "ejemplo": "Messi contra Cristiano en la misma noche. Y uno de los dos no estuvo ni cerca.",
     "pantalla": "MESSI vs CR7", "trampa": "no decir quién ganó al final"},
    {"nombre": "Si te pasa esto", "plantilla": "Si {situación concreta del espectador}, esto te importa.",
     "ejemplo": "Si mandas dinero a tu familia desde Estados Unidos, esto te cambia todo.",
     "pantalla": "¿MANDAS DINERO?", "trampa": "una situación tan general que no le habla a nadie"},
    {"nombre": "La lista con favorito", "plantilla": "{N} {cosas} que {resultado}. La número {k} nadie la usa.",
     "ejemplo": "Cuatro trucos para ahorrar en el súper. El tercero nadie lo usa.",
     "pantalla": "#3 NADIE LO USA", "trampa": "más de siete puntos"},
    {"nombre": "La advertencia real", "plantilla": "{Cosa} cambia el {fecha}. Haz {acción} antes.",
     "ejemplo": "Desde el lunes tu banco te va a cobrar por esto. Revísalo hoy.",
     "pantalla": "ANTES DEL LUNES", "trampa": "una urgencia inventada"},
    {"nombre": "Al revés del dicho", "plantilla": "{Dicho conocido, al revés}.",
     "ejemplo": "El que se fue a la villa, sí recuperó su silla.",
     "pantalla": "SÍ LA RECUPERÓ", "trampa": "voltear un dicho que nadie usa"},
    {"nombre": "Lo que nadie vio", "plantilla": "Todos vieron {lo obvio}. Nadie vio {el detalle}.",
     "ejemplo": "Todos vieron el gol. Nadie vio lo que hizo el portero antes.",
     "pantalla": "NADIE LO VIO", "trampa": "un detalle que no es sorprendente"},
    {"nombre": "La comparación que se imagina", "plantilla": "{Algo} es tan {grande/caro} como {comparación}.",
     "ejemplo": "Esa isla es más chica que el Estadio Azteca, y aun así tiene su propio país.",
     "pantalla": "MÁS CHICA QUE UN ESTADIO", "trampa": "comparar con algo que nadie conoce"},
    {"nombre": "El final primero", "plantilla": "{Cómo terminó}. Pero empecemos por el principio.",
     "ejemplo": "Terminó llorando frente a todo el estadio. Pero empecemos por el principio.",
     "pantalla": "TERMINÓ ASÍ", "trampa": "nunca contar el principio"},
    {"nombre": "La pregunta con apuesta", "plantilla": "¿{Pregunta que obliga a tomar partido}?",
     "ejemplo": "¿Tú pagarías mil dólares por un celular que se dobla?",
     "pantalla": "¿TÚ LO PAGARÍAS?", "trampa": "una pregunta que se contesta con un 'no' y ya"},
    {"nombre": "Sabías que (con dato raro)", "plantilla": "¿Sabías que {dato muy poco conocido}?",
     "ejemplo": "¿Sabías que en El Salvador hay un volcán que se puede ver desde el mar?",
     "pantalla": "¿SABÍAS ESTO?", "trampa": "un dato que todos conocen (y no abusar de esta fórmula)"},
]

# Palabras que suben lo que está en juego (dinero, riesgo, récords...).
APUESTA = {
    "millones", "millon", "mil", "dolares", "pesos", "dinero", "gratis", "pierde", "perdio", "perder",
    "gana", "gano", "ganar", "record", "historico", "prohibido", "prohiben", "peligro", "muerte", "murio",
    "carcel", "multa", "despedido", "quiebra", "estafa", "robo", "secreto", "nunca", "nadie", "primera",
    "ultima", "unico", "unica", "gol", "final", "campeon", "polemica", "escandalo", "cambia", "subio",
    "cayo", "explota", "alerta", "urgente", "cobrar", "ahorrar", "precio", "caro", "barato",
}
SALUDOS = [r"^\s*hola\b", r"bienvenid", r"hoy te (voy|vamos) a", r"en este video", r"en el video de hoy",
           r"no te vayas", r"qu[eé]date hasta el final", r"dale like", r"suscr[ií]bete", r"antes de empezar"]


def _plano(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()


def elegir_formulas(cantidad: int = 3, evitar_sabias: bool = False) -> list[dict]:
    opciones = [f for f in FORMULAS if not (evitar_sabias and f["nombre"].startswith("Sabías"))]
    return random.sample(opciones, min(cantidad, len(opciones)))


def calificar(gancho: str, recientes: list[str] | None = None) -> tuple[float, list[str]]:
    """0-100: corto (se dice en ~3 s), concreto (cifras, nombres), con algo en juego,
    lo fuerte al principio y hablándole al espectador. Con 'peros' que lo hunden."""
    texto = gancho.strip()
    palabras = re.findall(r"[\wáéíóúñü$%]+", texto, flags=re.I)
    n = len(palabras)
    planas = [_plano(p) for p in palabras]
    notas = {}
    # 1) largo: ~2.5 palabras por segundo → 3 segundos son 6-12 palabras
    notas["corto"] = 100 if 5 <= n <= 12 else 75 if n <= 16 else 45 if n <= 22 else 15
    # 2) concreto: números, dinero, porcentajes o nombres propios
    concretos = len(re.findall(r"\d|\$|%", texto)) + sum(1 for p in palabras[1:] if p[:1].isupper())
    concretos += sum(1 for p in planas if p in {"mil", "millones", "cien", "dos", "tres", "cuatro", "cinco", "diez"})
    notas["concreto"] = min(100, 35 + concretos * 22)
    # 3) algo en juego
    notas["apuesta"] = min(100, 40 + sum(1 for p in planas if p in APUESTA) * 30)
    # 4) lo fuerte primero: algo concreto o en juego en las primeras 4 palabras
    inicio = palabras[:4]
    fuerte = any(re.search(r"\d|\$|%", p) or _plano(p) in APUESTA or (i > 0 and p[:1].isupper())
                 for i, p in enumerate(inicio))
    notas["al_frente"] = 100 if fuerte else 55
    # 5) le habla al espectador
    notas["contigo"] = 100 if re.search(r"\b(t[uú]|te|tu|tus|usted|ustedes|imagina)\b", texto, re.I) else 65
    total = (notas["corto"] * 0.25 + notas["concreto"] * 0.25 + notas["apuesta"] * 0.2
             + notas["al_frente"] * 0.15 + notas["contigo"] * 0.15)
    peros = []
    plano = _plano(texto)
    if any(re.search(p, plano) for p in SALUDOS):
        peros.append("saluda o anuncia el video en vez de arrancar")
        total = min(total, 20)
    if recientes:
        apertura = " ".join(plano.split()[:3])
        if apertura and any(_plano(r).startswith(apertura) for r in recientes if r):
            peros.append("empieza igual que un video reciente")
            total -= 20
    if plano.startswith("sabias que") or plano.startswith("¿sabias"):
        total -= 8  # funciona, pero ya se usó demasiado
    return max(0.0, round(total, 1)), peros


def mejor(ganchos: list, recientes: list[str] | None = None) -> dict | None:
    """El gancho con mejor nota de los que escribió el guionista."""
    calificados = []
    for g in ganchos or []:
        g = {"texto": g} if isinstance(g, str) else dict(g or {})
        if not g.get("texto"):
            continue
        g["nota"], g["peros"] = calificar(g["texto"], recientes)
        calificados.append(g)
    return max(calificados, key=lambda g: g["nota"]) if calificados else None


def primera_oracion(texto: str) -> str:
    partes = re.split(r"(?<=[.!?…])\s+", texto.strip(), maxsplit=1)
    return partes[0] if partes else ""


def aplicar(datos: dict, recientes: list[str] | None = None) -> None:
    """Si uno de los ganchos propuestos es claramente mejor que la primera frase del guion,
    se pone como primera frase (en el guion y en la primera escena)."""
    elegido = mejor(datos.get("ganchos"), recientes)
    guion = datos.get("guion", "")
    actual = primera_oracion(guion)
    nota_actual, _ = calificar(actual, recientes)
    datos["nota_gancho"] = nota_actual
    if not elegido:
        return
    if elegido["nota"] >= nota_actual + 10 and _plano(elegido["texto"]) != _plano(actual):
        resto = guion.strip()[len(actual):].lstrip()
        datos["guion"] = f"{elegido['texto'].strip()} {resto}".strip()
        escenas = datos.get("escenas") or []
        if escenas and escenas[0].get("texto", "").strip().startswith(actual[:20]):
            escenas[0]["texto"] = elegido["texto"].strip() + " " + escenas[0]["texto"].strip()[len(actual):].lstrip()
        elif escenas:
            escenas[0]["texto"] = elegido["texto"].strip() + " " + escenas[0].get("texto", "")
        datos["nota_gancho"] = elegido["nota"]
    if elegido.get("pantalla") and datos.get("escenas"):
        datos["escenas"][0].setdefault("texto_pantalla", elegido["pantalla"])


# --- frases "de robot" que delatan a la IA y aburren al oído --------------------------------
MULETILLAS = [
    (r"\bcabe (destacar|mencionar|resaltar) que\b", ""),
    (r"\bes importante (destacar|mencionar|señalar) que\b", ""),
    (r"\bsin lugar a dudas,?\s*", ""), (r"\bsin duda alguna,?\s*", ""),
    (r"\ben el mundo (actual|de hoy),?\s*", "hoy "),
    (r"\ben la era digital,?\s*", "hoy "),
    (r"\bsumérgete en\b", "mira"), (r"\bsumerjámonos en\b", "veamos"),
    (r"\ben resumen,?\s*", ""), (r"\ben conclusión,?\s*", ""),
    (r"\bfascinante\b", "increíble"), (r"\bun sinfín de\b", "muchos"),
    (r"\bdesbloquea(r)?\b", "descubre"), (r"\bpanorama\b", "situación"),
    (r"\bhoy te voy a contar\b", ""), (r"\bno te vayas\b,?\s*", ""),
]


def humanizar(texto: str) -> str:
    """Quita muletillas de IA, rayas largas y caracteres invisibles (la voz los lee raro)."""
    t = re.sub(r"[​-‏⁠﻿­]", "", texto)
    t = t.replace("—", ", ").replace("–", "-").replace("“", '"').replace("”", '"').replace("…", "...")
    for patron, cambio in MULETILLAS:
        t = re.sub(patron, cambio, t, flags=re.I)
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",\s*,", ",", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    # mayúscula al inicio de cada oración si una muletilla la dejó en minúscula
    return re.sub(r"(^|[.!?]\s+)([a-záéíóúñ])", lambda m: m.group(1) + m.group(2).upper(), t)
