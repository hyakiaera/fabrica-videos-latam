"""Qué hacer con cada video terminado. Las tres opciones son independientes y
se pueden combinar: guardar para descargar, subir a Google Drive y publicar."""

import shutil
import subprocess
from pathlib import Path

from loguru import logger

from fabrica.config import secreto


def ficha_texto(datos: dict, tema: dict, creditos: list[str], conteo: dict | None = None) -> str:
    """Texto listo para copiar y pegar al publicar a mano."""
    lineas = [
        f"TÍTULO:\n{datos['titulo']}\n",
        f"DESCRIPCIÓN:\n{datos.get('descripcion', '')}\n\n{' '.join(datos.get('hashtags', []))}\n",
        f"CATEGORÍA: {tema.get('categoria', '')}   ESTILO: {tema.get('estilo', '')}",
        f"POR QUÉ ESTE TEMA: {tema.get('por_que', '')}\n",
        "FUENTES (verifica los datos antes de publicar):",
        *[f"- {t} ({f}) {u}" for t, f, u in tema.get("fuentes", [])],
    ]
    if datos.get("voz_usada", {}).get("voz"):
        v = datos["voz_usada"]
        lineas += ["", f"VOZ: {v['voz']}" + (f"\n   motivo: {v['motivo']}" if v.get("motivo") else "")]
    if datos.get("animadas"):
        lineas += [f"ESCENAS ANIMADAS CON IA: {datos['animadas']}"]
    if datos.get("musica_usada"):
        lineas += [f"MÚSICA: {datos['musica_usada']}"]
    if datos.get("credito_musica"):
        lineas += ["", "CRÉDITO OBLIGATORIO (pégalo en la descripción al publicar):", datos["credito_musica"]]
    if datos.get("nota_gancho") is not None:
        lineas += [f"GANCHO: {datos['nota_gancho']}/100 — «{datos.get('guion', '').split('.')[0][:90]}»"]
    if datos.get("nota") is not None:
        lineas += [f"NOTA PARA 'MEJOR DEL DÍA': {datos['nota']}/100" + (f" — {datos['nota_por_que']}" if datos.get("nota_por_que") else "")]
    if datos.get("avatar_usado"):
        lineas += [f"AVATAR: {datos['avatar_usado']}"]
    if conteo:
        graficas = sum(1 for e in datos.get("escenas", []) if e.get("grafica"))
        lineas += ["", f"IMÁGENES: {conteo.get('propias', 0)} tuyas, {conteo.get('ia', 0)} con IA, {conteo.get('real', 0)} fotos/logos reales, "
                       f"{conteo.get('stock', 0)} de stock, {graficas} gráficas, "
                       f"{conteo.get('rechazadas', 0)} rechazadas por no encajar, "
                       f"{conteo.get('estilizadas', 0)} fotos reales pasadas al estilo del video, "
                       f"{conteo.get('clips', 0)} clips de video reales"]
    if conteo and conteo.get("_sin_cuota"):
        lineas += [f"SIN CUOTA HOY (se usaron fotos en su lugar): {', '.join(conteo['_sin_cuota'])}"]
    if creditos:
        lineas += ["", "CRÉDITOS DE FOTOS (pégalos en la descripción):", *creditos]
    lineas += ["", "GUION:", datos["guion"]]
    return "\n".join(lineas)


def guardar_local(carpeta_dia: Path, nombre: str, video: Path, ficha: str,
                  miniatura: Path | None) -> Path:
    carpeta_dia.mkdir(parents=True, exist_ok=True)
    destino = carpeta_dia / f"{nombre}.mp4"
    shutil.copy(video, destino)
    (carpeta_dia / f"{nombre}.txt").write_text(ficha, encoding="utf-8")
    if miniatura and miniatura.exists():
        shutil.copy(miniatura, carpeta_dia / f"{nombre}.jpg")
    logger.success(f"Guardado para descargar: {destino}")
    return destino


def subir_drive(cfg: dict, carpeta_local: Path, ruta_relativa: str) -> bool:
    """Sube con rclone a la carpeta de Drive configurada. El remoto se llama
    'drive' y se configura una vez con `rclone config` (ver FABRICA.md)."""
    d = cfg.get("drive", {})
    if not shutil.which("rclone"):
        logger.error("Drive: rclone no está instalado; el video quedó solo en la carpeta local")
        return False
    destino = f"{d.get('remoto', 'drive')}:{d.get('carpeta', 'Fabrica de Videos')}/{ruta_relativa}"
    try:
        subprocess.run(["rclone", "copy", str(carpeta_local), destino], check=True, timeout=1800)
        logger.success(f"Subido a Google Drive: {destino}")
        return True
    except Exception as e:
        logger.error(f"Drive: la subida falló: {e}")
        return False


def perfil_upload_post(clave: str, escrito: str) -> str:
    """El nombre EXACTO del perfil en Upload-Post. Si el que guardaste no existe (mayúsculas,
    espacios, o pusiste el nombre de la clave en vez del perfil), se busca en tu cuenta."""
    import requests
    try:
        r = requests.get("https://api.upload-post.com/api/uploadposts/users",
                         headers={"Authorization": f"Apikey {clave}"}, timeout=30)
        datos = r.json() if r.ok else {}
    except Exception:
        return escrito
    perfiles = datos.get("profiles") or datos.get("users") or datos.get("data") or []
    nombres = [x.get("username") or x.get("name") for x in perfiles if isinstance(x, dict)]
    nombres = [n for n in nombres if n]
    if not nombres:
        return escrito
    if escrito in nombres:
        return escrito
    parecido = [n for n in nombres if n.lower().replace(" ", "") == escrito.lower().replace(" ", "")]
    if parecido:
        logger.warning(f"Upload-Post: el perfil se llama '{parecido[0]}' (guardaste '{escrito}'); uso el correcto")
        return parecido[0]
    if len(nombres) == 1:
        logger.warning(f"Upload-Post: '{escrito}' no es un perfil; tu único perfil es '{nombres[0]}' y uso ese. "
                       "Corrige el secreto UPLOAD_POST_USERNAME.")
        return nombres[0]
    logger.error(f"Upload-Post: '{escrito}' no es un perfil. Tus perfiles: {', '.join(nombres)}. "
                 "Pon uno de esos en el secreto UPLOAD_POST_USERNAME.")
    return escrito


def publicar(cfg: dict, video: Path, datos: dict) -> dict:
    """Publica en TikTok/Instagram/YouTube Shorts con la integración Upload-Post
    que ya trae MoneyPrinterTurbo."""
    from app.services.upload_post import cross_post_video

    p = cfg.get("publicar", {})
    if not secreto("UPLOAD_POST_API_KEY"):
        logger.warning("Publicar: falta UPLOAD_POST_API_KEY; no se publicó")
        return {"success": False, "error": "sin clave"}
    cuenta = {
        "upload_post_api_key": secreto("UPLOAD_POST_API_KEY").strip(),
        "upload_post_username": perfil_upload_post(secreto("UPLOAD_POST_API_KEY").strip(),
                                                   (secreto("UPLOAD_POST_USERNAME") or p.get("usuario", "")).strip()),
        "upload_post_enabled": True,
    }
    titulo = f"{datos['titulo']} {' '.join(datos.get('hashtags', [])[:5])}"
    if datos.get("credito_musica"):  # obligatorio por la licencia CC BY de la música
        titulo += f"\n\n{datos['credito_musica']}"
    titulo = titulo[:2000]
    import os
    elegidas = os.environ.get("PLATAFORMAS", "").strip()
    plataformas = ([x.strip().lower() for x in elegidas.split(",") if x.strip()] if elegidas
                   else p.get("plataformas", ["youtube", "facebook", "x", "threads"]))
    # X (Twitter) solo acepta 280 letras: va aparte, con el título corto, el crédito de la música
    # (obligatorio) y menos hashtags.
    corto = f"{datos['titulo']} {' '.join(datos.get('hashtags', [])[:2])}"
    if datos.get("credito_musica"):
        corto = f"{datos['titulo'][:90]}\n{datos['credito_musica']}"
    corto = corto[:280]

    def subir(redes):
        texto = corto if redes == ["x"] else (titulo[:500] if redes == ["threads"] else titulo)
        return cross_post_video(str(video), texto, platforms=redes,
                                youtube_extra={"selfDeclaredMadeForKids": False}, account=cuenta)

    if "x" in plataformas and len(plataformas) > 1:
        otras = [r for r in plataformas if r != "x"]
        r_otras, r_x = subir(otras), subir(["x"])
        if r_otras.get("success") and r_x.get("success"):
            logger.success(f"Publicado en {plataformas}")
            return {"success": True, "plataformas": plataformas}
        if r_otras.get("success") or r_x.get("success"):
            # una de las dos tandas salió: se reintenta solo lo que falló, red por red
            plataformas = ["x"] if r_otras.get("success") else otras
            ya = otras if r_otras.get("success") else ["x"]
            for red in plataformas:
                if subir([red]).get("success"):
                    ya.append(red)
            logger.success(f"Publicado en {ya}")
            return {"success": True, "plataformas": ya}
        resultado = r_otras
    else:
        resultado = subir(plataformas)
    if resultado.get("success"):
        logger.success(f"Publicado en {plataformas}")
        return resultado
    logger.error(f"Publicar falló: {resultado.get('error')}")
    if len(plataformas) > 1 and "unconfirmed" not in str(resultado.get("error", "")):
        # Si una red no está conectada en Upload-Post, se rechaza todo: se prueba una por una.
        bien = []
        for red in plataformas:
            r = subir([red])
            if r.get("success"):
                bien.append(red)
            else:
                logger.warning(f"Publicar en {red}: {r.get('error')}")
        if bien:
            logger.success(f"Publicado en {bien} (las demás redes fallaron)")
            return {"success": True, "plataformas": bien}
    return resultado
