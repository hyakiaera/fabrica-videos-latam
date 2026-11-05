import unittest
from unittest import mock

import base64
import tempfile
from pathlib import Path

from fabrica import estilos, guion, ia, imagenes, pedidos, salidas, tendencias, video, voz

_SIN_RED = []
_ORIGINALES = {}


def setUpModule():
    # Las pruebas no deben salir a internet a buscar fotos de noticias.
    from fabrica import fotos_web
    for nombre in ("noticias", "openverse", "bing_imagenes", "imagen_wikipedia", "noticias_texto", "clips_stock"):
        _ORIGINALES[nombre] = getattr(fotos_web, nombre)
        parche = mock.patch.object(fotos_web, nombre, return_value=[])
        parche.start()
        _SIN_RED.append(parche)


def tearDownModule():
    for parche in _SIN_RED:
        parche.stop()


TRENDS_RSS = b"""<?xml version="1.0"?>
<rss xmlns:ht="https://trends.google.com/trending/rss" version="2.0"><channel>
<item><title>america vs chivas</title><ht:approx_traffic>500K+</ht:approx_traffic>
<ht:news_item><ht:news_item_title>Clasico nacional hoy</ht:news_item_title>
<ht:news_item_url>https://ej.com/a</ht:news_item_url><ht:news_item_source>Medio</ht:news_item_source></ht:news_item>
</item></channel></rss>"""

NEWS_RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Binance sufre ataque - Medio X</title><link>https://n.com/1</link><source>Medio X</source></item>
<item><title>Otra noticia - Medio Y</title><link>https://n.com/2</link><source>Medio Y</source></item>
</channel></rss>"""


def _respuesta(contenido):
    r = mock.Mock(content=contenido)
    r.raise_for_status = mock.Mock()
    return r


class TestIA(unittest.TestCase):
    def test_extrae_json_con_bloque_markdown(self):
        self.assertEqual(ia.extraer_json('Aquí va:\n```json\n{"a": 1}\n```'), {"a": 1})

    def test_extrae_json_con_texto_previo(self):
        self.assertEqual(ia.extraer_json('Claro! {"temas": []}'), {"temas": []})

    def test_sin_claves_usa_pollinations(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            nombres = [p["nombre"] for p in ia._proveedores({})]
        self.assertEqual(nombres, ["pollinations"])

    def test_orden_gemini_groq(self):
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "g", "GROQ_API_KEY": "q"}, clear=True):
            nombres = [p["nombre"] for p in ia._proveedores({"ia": {"usar_pollinations_texto": False}})]
        self.assertEqual(nombres, ["gemini", "groq"])


class TestTendencias(unittest.TestCase):
    def test_lee_google_trends(self):
        with mock.patch("requests.get", return_value=_respuesta(TRENDS_RSS)):
            c = tendencias.google_trends("MX", 1.0)
        self.assertEqual(c[0].titulo, "america vs chivas")
        self.assertEqual(c[0].trafico, "500K+")
        self.assertEqual(c[0].titulares[0], ("Clasico nacional hoy", "Medio", "https://ej.com/a"))

    def test_lee_google_news(self):
        edicion = {"hl": "es-419", "gl": "MX", "ceid": "MX:es-419"}
        with mock.patch("requests.get", return_value=_respuesta(NEWS_RSS)):
            c = tendencias.google_news(edicion, "tecnologia", 1.0, limite=1)
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0].categoria, "tecnologia")

    def test_elegir_temas_mapea_fuentes_y_corrige_estilo(self):
        candidatos = [tendencias.Candidato("Binance", "news", "MX", "es", titulares=[("T1", "M", "u")])]
        respuesta = {"temas": [{"indices": [0, 99], "tema": "Hackeo a Binance", "categoria": "tecnologia",
                                "estilo": "inexistente", "por_que": "viral"}]}
        with mock.patch.object(ia, "pedir_json", return_value=respuesta):
            temas = tendencias.elegir_temas({}, candidatos, 1, [])
        self.assertEqual(temas[0]["fuentes"], [("T1", "M", "u")])
        self.assertEqual(temas[0]["estilo"], "caricatura")

    def test_estilo_fijo_se_respeta(self):
        candidatos = [tendencias.Candidato("X", "news", "MX", "es")]
        respuesta = {"temas": [{"indices": [0], "tema": "X", "estilo": "anime"}]}
        with mock.patch.object(ia, "pedir_json", return_value=respuesta):
            temas = tendencias.elegir_temas({}, candidatos, 1, [], estilo="pizarra")
        self.assertEqual(temas[0]["estilo"], "pizarra")


class TestEstilosYSalidas(unittest.TestCase):
    def test_prompt_incluye_reglas(self):
        p = estilos.prompt_imagen(estilos.obtener("caricatura"), "a soccer stadium")
        self.assertIn("a soccer stadium", p)
        self.assertIn("no realistic faces of real famous people", p)
        self.assertNotIn("no logos", p)

    def test_realista_requiere_clave_de_stock(self):
        realista = estilos.obtener("videos_stock")
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(estilos.disponible(realista))
            self.assertNotIn("- videos_stock:", estilos.resumen_para_ia())
        with mock.patch.dict("os.environ", {"PIXABAY_API_KEY": "x"}, clear=True):
            self.assertTrue(estilos.disponible(realista))

    def test_estilo_desconocido(self):
        with self.assertRaises(ValueError):
            estilos.obtener("nada")

    def test_ficha_dice_que_voz_se_uso(self):
        datos = {"titulo": "T", "guion": "G", "voz_usada": {"voz": "Edge — tu voz clonada falló",
                                                         "motivo": "RuntimeError: sin .pth"}}
        ficha = salidas.ficha_texto(datos, {"fuentes": []}, [])
        self.assertIn("VOZ: Edge — tu voz clonada falló", ficha)
        self.assertIn("sin .pth", ficha)

    def test_ficha_incluye_creditos_y_fuentes(self):
        datos = {"titulo": "T", "guion": "G", "descripcion": "D", "hashtags": ["#a"]}
        tema = {"categoria": "c", "estilo": "e", "fuentes": [("Tit", "Med", "u")]}
        ficha = salidas.ficha_texto(datos, tema, ["Foto: X (CC BY)"])
        self.assertIn("Foto: X (CC BY)", ficha)
        self.assertIn("Tit (Med) u", ficha)


class TestVozYLogo(unittest.TestCase):
    def test_voz_por_defecto_hombre(self):
        self.assertEqual(voz.voz_edge({}), "es-MX-JorgeNeural-Male")

    def test_voz_mujer(self):
        self.assertEqual(voz.voz_edge({"voz": {"genero": "mujer"}}), "es-MX-DaliaNeural-Female")

    def test_genero_invalido_vuelve_a_hombre(self):
        self.assertEqual(voz.voz_edge({"voz": {"genero": "otro"}}), "es-MX-JorgeNeural-Male")

    def test_clonar_applio_no_necesita_comando(self):
        self.assertTrue(voz.clonar_activo({"voz": {"clonar": True}}))
        self.assertFalse(voz.clonar_activo({"voz": {"clonar": True, "motor": "comando"}}))

    def test_logo_personalizado(self):
        cfg = {"logo": {"posicion": "personalizada", "x": 80, "y": 10, "tamano": 0.2}}
        self.assertEqual(video.ubicacion_logo(cfg), (80.0, 10.0, 20.0))
        self.assertIn("overlay=W*0.8000-w:H*0.1000", video.filtro_logo(cfg))

    def test_logo_centro_se_centra(self):
        self.assertIn("overlay=W*0.5000-w/2", video.filtro_logo({"logo": {"posicion": "arriba_centro"}}))


class TestImagenesYRespaldo(unittest.TestCase):
    def setUp(self):
        imagenes._SIN_SERVICIO.clear()
        self.carpeta = Path(tempfile.mkdtemp())

    def test_pollinations_402_pasa_a_cloudflare(self):
        cobro = mock.Mock(status_code=402, ok=False, headers={}, content=b"")
        jpg = b"\xff\xd8" + b"0" * 6000
        cf = mock.Mock(ok=True, status_code=200)
        cf.json.return_value = {"result": {"image": base64.b64encode(jpg).decode()}}
        env = {"CLOUDFLARE_ACCOUNT_ID": "a", "CLOUDFLARE_API_TOKEN": "t"}
        escenas = [{"imagen": "stadium"}, {"imagen": "ball"}]
        with mock.patch.dict("os.environ", env, clear=True), \
             mock.patch("requests.get", return_value=cobro) as get, \
             mock.patch("requests.post", return_value=cf), mock.patch("time.sleep"):
            rutas, _, _ = imagenes.para_escenas({}, escenas, estilos.obtener("caricatura"), "9:16", self.carpeta)
        self.assertEqual(len(rutas), 2)
        self.assertEqual(rutas[0].read_bytes(), jpg)
        self.assertLessEqual(get.call_count, 2)  # tras el 402 no se insiste en cada escena

    def test_modelo_retirado_pasa_al_siguiente(self):
        ia._DISPONIBLES.clear()
        modelos = mock.Mock(ok=True)
        modelos.json.return_value = {"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "whisper-large-v3"},
                                              {"id": "openai/gpt-oss-20b"}]}
        no_existe = mock.Mock(status_code=404, text="model not found")
        bien = mock.Mock(status_code=200)
        bien.json.return_value = {"choices": [{"message": {"content": "<think>x{</think>{\"ok\": 1}"}}]}
        cfg = {"ia": {"usar_pollinations_texto": False}}
        with mock.patch.dict("os.environ", {"GROQ_API_KEY": "k"}, clear=True), \
             mock.patch("requests.get", return_value=modelos), \
             mock.patch("requests.post", side_effect=[no_existe, bien]) as post:
            self.assertEqual(ia.pedir_json(cfg, "s", "u"), {"ok": 1})
        usados = [c.kwargs["json"]["model"] for c in post.call_args_list]
        self.assertEqual(usados, ["llama-3.3-70b-versatile", "openai/gpt-oss-20b"])
        ia._DISPONIBLES.clear()

    def test_contexto_global_y_rehacer_imagen_que_no_encaja(self):
        prompts = []

        def generar(prompt, carpeta, nombre, pasos=8):
            prompts.append(prompt)
            ruta = carpeta / f"{nombre}.jpg"
            ruta.write_bytes(b"x")
            return ruta

        imagenes._SIN_SERVICIO.add("pollinations")
        escenas = [{"imagen": "a plate on a table"}]
        with mock.patch.object(imagenes, "cloudflare", side_effect=generar), \
             mock.patch.object(ia, "imagen_encaja", side_effect=[False, True]):
            rutas, _, _ = imagenes.para_escenas({}, escenas, estilos.obtener("caricatura"), "9:16",
                                             self.carpeta, visual_global="Salvadoran pupusas in El Salvador")
        self.assertEqual(rutas[0].name, "escena-00b.jpg")
        self.assertTrue(prompts[0].startswith("high quality 2D cartoon illustration of Salvadoran pupusas"))

    def test_ia_no_reintenta_si_pide_pago(self):
        cobro = mock.Mock(status_code=402, text="pay")
        with mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch("requests.post", return_value=cobro) as post, mock.patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                ia.pedir_json({}, "s", "u")
        self.assertEqual(post.call_count, 1)


class TestPedidosYMarca(unittest.TestCase):
    def test_link_de_noticia_da_contexto_y_fuentes(self):
        articulo = {"titulo": "Nuevo estadio", "autor": "Diario", "texto": "El estadio abre en 2027."}
        respuesta = {"tema": "El nuevo estadio", "consulta": "nuevo estadio", "categoria": "deportes",
                     "estilo": "comic"}
        with mock.patch.object(pedidos, "leer_articulo", return_value=articulo), \
             mock.patch.object(ia, "pedir_json", return_value=respuesta), \
             mock.patch.object(tendencias, "buscar_noticias", return_value=[("T", "M", "u")]):
            tema = pedidos.preparar({}, "https://diario.com/nota hazlo divertido", "auto")
        self.assertEqual(tema["estilo"], "comic")
        self.assertEqual(tema["contexto"], "El estadio abre en 2027.")
        self.assertEqual(tema["indicaciones"], "hazlo divertido")
        self.assertEqual(tema["fuentes"][0], ("Nuevo estadio", "Diario", "https://diario.com/nota"))

    def test_link_de_red_social_usa_lector_de_video(self):
        with mock.patch.object(pedidos, "leer_video", return_value={"titulo": "X", "autor": "", "texto": ""}) as lv, \
             mock.patch.object(ia, "pedir_json", side_effect=RuntimeError), \
             mock.patch.object(tendencias, "buscar_noticias", return_value=[]):
            tema = pedidos.preparar({}, "https://www.tiktok.com/@a/video/1", "pizarra")
        lv.assert_called_once()
        self.assertEqual((tema["tema"], tema["estilo"]), ("X", "pizarra"))

    def test_guion_incluye_contexto_e_indicaciones(self):
        datos = {"guion": "g", "escenas": [{}], "hashtags": ["a"]}
        tema = {"tema": "T", "contexto": "DATO UNICO", "indicaciones": "tono serio", "fuentes": []}
        with mock.patch.object(ia, "pedir_json", return_value=datos) as pj:
            guion.escribir({}, tema, estilos.obtener("comic"))
        prompt = pj.call_args.args[2]
        self.assertIn("DATO UNICO", prompt)
        self.assertIn("tono serio", prompt)

    def test_texto_de_marca_crea_logo(self):
        carpeta = Path(tempfile.mkdtemp())
        cfg = {"logo": {"archivo": str(carpeta / "no-existe.png"), "texto": "@MiCanal"}}
        logo = video.obtener_logo(cfg, carpeta)
        self.assertTrue(logo and logo.exists())
        self.assertIsNone(video.obtener_logo({"logo": {"archivo": str(carpeta / "x.png")}}, carpeta))


class TestOpcionesNuevas(unittest.TestCase):
    def test_duraciones(self):
        from fabrica.__main__ import segundos
        self.assertEqual([segundos(d) for d in ("1", "1:30", "2", "2:30", "3", "2.5")],
                         [60, 90, 120, 150, 180, 150])
        self.assertEqual(segundos("20"), 300)

    def test_video_largo_limita_escenas(self):
        datos = {"guion": "g", "escenas": [{}], "hashtags": []}
        cfg = {"guion": {"duracion_segundos": 180}}
        with mock.patch.object(ia, "pedir_json", return_value=datos) as pj:
            guion.escribir(cfg, {"tema": "T", "fuentes": []}, estilos.obtener("comic"))
        prompt = pj.call_args.args[2]
        self.assertIn("exactamente 24 escenas", prompt)
        self.assertIn("unas 450 palabras", prompt)
        self.assertIn("video largo", prompt)

    def test_modelo_por_link_busca_en_subcarpetas(self):
        from fabrica import voz_applio
        carpeta = Path(tempfile.mkdtemp())
        (carpeta / "zip" / "sub").mkdir(parents=True)
        (carpeta / "zip" / "sub" / "mi.pth").write_bytes(b"x")
        (carpeta / "zip" / "G_100.pth").write_bytes(b"x")
        (carpeta / "zip" / "mi.index").write_bytes(b"x")
        pth, idx = voz_applio._archivos_modelo_recursivo(carpeta)
        self.assertEqual((pth.name, idx.name), ("mi.pth", "mi.index"))


class TestMarcasYNumeros(unittest.TestCase):
    def test_encuadrar_logo_y_foto(self):
        from PIL import Image
        carpeta = Path(tempfile.mkdtemp())
        Image.new("RGBA", (300, 300), (255, 0, 0, 255)).save(carpeta / "logo.png")
        Image.new("RGB", (1600, 900), (0, 0, 255)).save(carpeta / "foto.jpg")
        for nombre in ("logo.png", "foto.jpg"):
            salida = imagenes.encuadrar(carpeta / nombre, "9:16")
            self.assertEqual(Image.open(salida).size, (1080, 1920))

    def test_foto_real_va_primero(self):
        carpeta = Path(tempfile.mkdtemp())
        logo = carpeta / "b.png"
        from PIL import Image
        Image.new("RGBA", (200, 200), (0, 0, 0, 0)).save(logo)  # logo con fondo transparente
        with mock.patch.object(imagenes, "wikimedia", return_value=(logo, "Logo: Wikimedia")) as wm, \
             mock.patch.object(imagenes, "cloudflare") as cf, \
             mock.patch.object(ia, "imagen_encaja", return_value=True):
            rutas, creditos, _ = imagenes.para_escenas(
                {}, [{"imagen": "x", "foto_real": "Binance logo"}], estilos.obtener("comic"), "9:16", carpeta)
        wm.assert_called_once()
        self.assertTrue(wm.call_args.kwargs["incluir_logos"])
        cf.assert_not_called()
        self.assertEqual(creditos, ["Logo: Wikimedia"])
        self.assertTrue(rutas[0].name.endswith("-encuadre.jpg"))

    def test_numero_consecutivo(self):
        from fabrica import __main__ as m
        with mock.patch.object(m, "_historial", return_value=[{"numero": 7}, {"numero": 12}]):
            self.assertEqual(m._siguiente_numero(), 13)
        with mock.patch.object(m, "_historial", return_value=[{}, {}]):
            self.assertEqual(m._siguiente_numero(), 3)


class TestMovimientoYGraficas(unittest.TestCase):
    def test_presupuesto_de_imagenes(self):
        escenas = [{} for _ in range(20)]
        escenas[3]["grafica"] = {"tipo": "cifra", "valor": 1}
        elegidas = imagenes._elegir_escenas(escenas, 10)
        self.assertEqual(len(elegidas), 10)
        self.assertNotIn(3, elegidas)
        self.assertIn(0, elegidas)

    def test_duraciones_segun_texto(self):
        from fabrica import movimiento
        d = movimiento.duraciones([{"texto": "a" * 10}, {"texto": "a" * 30}], 8)
        self.assertAlmostEqual(d[0], 2.0)
        self.assertAlmostEqual(d[1], 6.0)

    def test_clips_reutilizan_y_dibujan_graficas(self):
        from PIL import Image
        from fabrica import movimiento
        carpeta = Path(tempfile.mkdtemp())
        img = carpeta / "a.jpg"
        Image.new("RGB", (540, 960), (200, 50, 50)).save(img)
        escenas = [{"texto": "uno"}, {"texto": "dos"},
                   {"texto": "tres", "grafica": {"tipo": "barras", "titulo": "T", "datos": [["A", -3], ["B", 2]]}}]
        clips = movimiento.clips_de_escenas({}, escenas, [img, None, None], "explicativo", 3, carpeta / "c")
        self.assertEqual(len(clips), 3)
        self.assertTrue(all(c.exists() and c.stat().st_size > 1000 for c in clips))


class TestMisFotos(unittest.TestCase):
    def test_carpeta_local_describe_una_vez(self):
        from PIL import Image
        from fabrica import mis_fotos
        raiz = Path(tempfile.mkdtemp())
        (raiz / "muebles").mkdir()
        Image.new("RGB", (900, 1600), (120, 80, 40)).save(raiz / "muebles" / "sofa.jpg")
        trabajo = Path(tempfile.mkdtemp())
        with mock.patch.object(mis_fotos, "_local", return_value=raiz), \
             mock.patch.object(mis_fotos, "_remoto", return_value=None), \
             mock.patch.object(ia, "describir_imagen", return_value="sofá café de tela") as desc:
            self.assertEqual(mis_fotos.categorias({}), ["muebles"])
            fotos = mis_fotos.preparar({}, ["muebles"], trabajo)
        self.assertEqual(fotos["muebles/sofa.jpg"][1], "sofá café de tela")
        desc.assert_called_once()

    def test_escena_con_foto_propia_no_gasta_ia(self):
        from PIL import Image
        carpeta = Path(tempfile.mkdtemp())
        foto = carpeta / "sofa.jpg"
        Image.new("RGB", (900, 1600), (120, 80, 40)).save(foto)
        propias = {"muebles/sofa.jpg": (foto, "sofá")}
        escenas = [{"imagen": "x", "foto_propia": "muebles/sofa.jpg"}, {"imagen": "living room"}]
        with mock.patch.object(imagenes, "cloudflare", return_value=None) as cf, \
             mock.patch.object(imagenes, "pollinations", return_value=None), \
             mock.patch.object(imagenes, "pexels_foto", return_value=None), \
             mock.patch.object(imagenes, "pixabay_foto", return_value=None), \
             mock.patch.object(imagenes, "wikimedia", return_value=None):
            rutas, _, conteo = imagenes.para_escenas({}, escenas, estilos.obtener("caricatura"), "9:16",
                                                     carpeta, fotos_propias=propias)
        self.assertEqual(conteo["propias"], 1)
        self.assertEqual(Image.open(rutas[0]).size, (1080, 1920))
        self.assertIsNone(rutas[1])
        self.assertEqual(cf.call_count, 1)  # solo la escena sin foto propia pidió imagen IA

    def test_pedido_de_negocio_elige_carpeta_existente(self):
        from fabrica import mis_fotos
        respuesta = {"tema": "Promo mueblería", "consulta": "x", "categoria": "general", "estilo": "comic",
                     "carpetas_fotos": ["muebles", "no-existe"], "es_negocio": True}
        with mock.patch.object(mis_fotos, "categorias", return_value=["muebles", "comida"]), \
             mock.patch.object(ia, "pedir_json", return_value=respuesta), \
             mock.patch.object(tendencias, "buscar_noticias") as bn:
            sin_pedir = pedidos.preparar({}, "video de mi mueblería, cojines 30% off", "auto")
            tema = pedidos.preparar({}, "video de mi mueblería, cojines 30% off (fotos en drive)", "auto")
        self.assertEqual(sin_pedir["carpetas_fotos"], [])  # sin decir "drive"/"fotos" no se usan
        self.assertEqual(tema["carpetas_fotos"], ["muebles"])
        self.assertTrue(tema["es_negocio"])
        bn.assert_not_called()

    def test_tendencias_no_usan_tus_carpetas(self):
        candidatos = [tendencias.Candidato("América vs Chivas", "trends", "MX", "es")]
        respuesta = {"temas": [{"indices": [0], "tema": "Clásico", "categoria": "deportes", "estilo": "comic",
                                "carpetas_fotos": ["logos equipos"]}]}
        with mock.patch.object(ia, "pedir_json", return_value=respuesta):
            temas = tendencias.elegir_temas({}, candidatos, 1, [])
        self.assertEqual(temas[0]["carpetas_fotos"], [])

    def test_tarjeta_de_negocio(self):
        from fabrica import graficas
        salida = Path(tempfile.mkdtemp()) / "t.mp4"
        graficas.clip({"tipo": "tarjeta", "titulo": "Tienda", "lineas": ["30% OFF", "Calle 1"]}, 1, "9:16", "", salida)
        self.assertGreater(salida.stat().st_size, 1000)


class TestFotosWeb(unittest.TestCase):
    def test_banco_no_repite_y_filtra(self):
        from fabrica import fotos_web
        carpeta = Path(tempfile.mkdtemp())
        lista = [("http://x/1.jpg", "Medio A", "http://a"), ("http://x/2.jpg", "Medio B", "http://b")]

        def bajar(url, ruta):
            ruta.write_bytes(b"x" * 30000)
            return ruta

        with mock.patch.object(fotos_web, "noticias", return_value=lista), \
             mock.patch.object(fotos_web, "openverse", return_value=[]), \
             mock.patch.object(fotos_web, "_bajar", side_effect=bajar):
            banco = fotos_web.Banco(carpeta)
            primera = banco.tomar("Canelo")
            segunda = banco.tomar("Canelo", aceptar=lambda r: False)
            tercera = banco.tomar("Canelo")
        self.assertIn("Medio A", primera[1])
        self.assertIsNone(segunda)
        self.assertIsNone(tercera)  # la segunda ya se usó (rechazada) y no hay más

    def test_bing_rss_saca_url_real_y_og_image(self):
        from fabrica import fotos_web
        rss = ("<rss><channel><item><title>T</title><link>http://www.bing.com/news/apiclick.aspx?"
               "url=https%3a%2f%2fdiario.com%2fnota&amp;c=1</link><News:Source>Diario</News:Source>"
               "</item></channel></rss>")
        pagina = '<html><meta property="og:image" content="https://diario.com/foto.jpg"></html>'
        respuestas = [mock.Mock(ok=True, text=rss), mock.Mock(ok=True, text=pagina)]
        with mock.patch("requests.get", side_effect=respuestas) as get:
            r = _ORIGINALES["noticias"]("Canelo")
        self.assertEqual(r, [("https://diario.com/foto.jpg", "Diario", "https://diario.com/nota")])
        self.assertEqual(get.call_args_list[1].args[0], "https://diario.com/nota")

    def test_foto_ancha_usa_barrido(self):
        from PIL import Image
        from fabrica import movimiento
        carpeta = Path(tempfile.mkdtemp())
        Image.new("RGB", (1600, 800), (10, 120, 200)).save(carpeta / "ancha.jpg")
        with mock.patch.object(movimiento, "clip_de_barrido", return_value=carpeta / "b.mp4") as barrido:
            movimiento.clip_de_imagen(carpeta / "ancha.jpg", 2, "acercar", "9:16", carpeta / "c.mp4")
        barrido.assert_called_once()

    def test_preparar_real_no_achica_fotos(self):
        from PIL import Image
        carpeta = Path(tempfile.mkdtemp())
        Image.new("RGBA", (1600, 800), (10, 120, 200, 255)).save(carpeta / "foto.png")
        Image.new("RGBA", (400, 400), (0, 0, 0, 0)).save(carpeta / "logo.png")
        foto = imagenes.preparar_real(carpeta / "foto.png", "9:16")
        logo = imagenes.preparar_real(carpeta / "logo.png", "9:16")
        self.assertEqual(Image.open(foto).size, (1600, 800))  # la foto no se encoge
        self.assertEqual(Image.open(logo).size, (1080, 1920))  # el logo sí se centra


class TestDetallesYListas(unittest.TestCase):
    def test_fotos_propias_se_asignan_por_nombre(self):
        propias = {"Series/Amor Disfrazado.jpg": (Path("a.jpg"), "póster"),
                   "Series/Donde termina la mascara1.webp": (Path("b.webp"), "póster"),
                   "Series/Otra cosa.jpg": (Path("c.jpg"), "x")}
        escenas = [{"texto": "En el puesto uno está Donde termina la máscara"},
                   {"texto": "Y en el dos, Amor disfrazado conquista a todos"},
                   {"texto": "Cierre del video"}]
        guion.asignar_fotos_propias(escenas, propias)
        self.assertEqual(escenas[0]["foto_propia"], "Series/Donde termina la mascara1.webp")
        self.assertEqual(escenas[1]["foto_propia"], "Series/Amor Disfrazado.jpg")
        self.assertNotIn("foto_propia", escenas[2])

    def test_detalles_obligatorios_en_el_guion(self):
        datos = {"guion": "g", "escenas": [{}], "hashtags": []}
        tema = {"tema": "T", "fuentes": [], "obligatorio": "decir el top 3 en orden", "contexto": "1. A 2. B"}
        with mock.patch.object(ia, "pedir_json", return_value=datos) as pj:
            guion.escribir({}, tema, estilos.obtener("comic"))
        prompt = pj.call_args.args[2]
        self.assertIn("OBLIGATORIO", prompt)
        self.assertIn("decir el top 3 en orden", prompt)
        self.assertIn("RANKING", prompt)

    def test_pagina_de_lista_se_lee_completa(self):
        html = ("<html><head><script>var x=1;</script></head><body><h1>Top 10 series</h1>"
                "<ol><li>1. Donde termina la máscara</li><li>2. Amor disfrazado</li></ol></body></html>")
        with mock.patch("trafilatura.fetch_url", return_value=html):
            d = pedidos.leer_articulo("https://www.netflix.com/tudum/top10")
        self.assertIn("1. Donde termina la máscara", d["texto"])
        self.assertIn("2. Amor disfrazado", d["texto"])
        self.assertNotIn("var x", d["texto"])


class TestRespaldoStock(unittest.TestCase):
    def test_si_falla_el_stock_se_rehace_con_imagenes(self):
        from fabrica import __main__ as m
        datos = {"titulo": "T", "guion": "g", "escenas": [{"texto": "a"}], "hashtags": []}
        tema = {"tema": "Pupusas", "categoria": "comida", "estilo": "videos_stock", "fuentes": []}
        carpeta = Path(tempfile.mkdtemp())
        armados = []

        def armar(cfg, d, estilo, fotos, trabajo):
            armados.append(estilo.nombre)
            if "stock_video" in estilo.fuentes:
                raise RuntimeError("429")
            return carpeta / "v.mp4"

        with mock.patch.dict("os.environ", {"PIXABAY_API_KEY": "k"}), \
             mock.patch.object(m.guion, "escribir", return_value=datos), \
             mock.patch.object(m.imagenes, "para_escenas", return_value=([None], [], {})), \
             mock.patch.object(m.video, "armar", side_effect=armar), \
             mock.patch.object(m.video, "poner_logo", return_value=carpeta / "f.mp4"), \
             mock.patch.object(m.video, "miniatura", return_value=None), \
             mock.patch.object(m.salidas, "guardar_local", return_value=carpeta / "f.mp4"), \
             mock.patch.object(m, "HISTORIAL", carpeta / "h.json"):
            m.hacer_video({}, tema, {"descargar"})
        self.assertEqual(len(armados), 2)
        self.assertEqual(tema["estilo"], "cinematografico")


class TestCarpetasAnidadas(unittest.TestCase):
    def test_carpeta_mencionada_con_acentos_y_anidada(self):
        from fabrica import mis_fotos
        cats = ["Comida", "Comida/Comida salvadoreña", "Series", "muebles"]
        self.assertEqual(mis_fotos.mencionadas("video de pupusas, fotos en drive comida salvadorena", cats),
                         ["Comida"])  # la de afuera ya incluye la de adentro
        self.assertEqual(mis_fotos.mencionadas("usa la carpeta comida salvadoreña", cats[1:]),
                         ["Comida/Comida salvadoreña"])

    def test_fotos_en_subcarpetas(self):
        from PIL import Image
        from fabrica import mis_fotos
        raiz = Path(tempfile.mkdtemp())
        (raiz / "Comida" / "Comida salvadoreña").mkdir(parents=True)
        Image.new("RGB", (800, 800)).save(raiz / "Comida" / "Comida salvadoreña" / "pupusas.jpg")
        with mock.patch.object(mis_fotos, "_local", return_value=raiz), \
             mock.patch.object(mis_fotos, "_remoto", return_value=None), \
             mock.patch.object(ia, "describir_imagen", return_value="pupusas"):
            self.assertIn("Comida/Comida salvadoreña", mis_fotos.categorias({}))
            fotos = mis_fotos.preparar({}, ["Comida"], Path(tempfile.mkdtemp()))
        self.assertEqual(list(fotos), ["Comida/Comida salvadoreña/pupusas.jpg"])

    def test_pedir_fotos_llena_escenas_primero(self):
        propias = {f"Comida/f{i}.jpg": (Path(f"f{i}.jpg"), "comida") for i in range(3)}
        escenas = [{"texto": "intro"}, {"texto": "a"}, {"texto": "b", "grafica": {"tipo": "cifra"}},
                   {"texto": "c"}, {"texto": "d"}]
        guion.asignar_fotos_propias(escenas, propias, llenar=True)
        self.assertEqual([e.get("foto_propia") for e in escenas],
                         ["Comida/f0.jpg", "Comida/f1.jpg", None, "Comida/f2.jpg", None])

    def test_palabra_drive_activa_prioridad(self):
        from fabrica import mis_fotos
        respuesta = {"tema": "Comida salvadoreña", "consulta": "x", "estilo": "realista", "carpetas_fotos": []}
        with mock.patch.object(mis_fotos, "categorias", return_value=["Comida", "Comida/Comida salvadoreña"]), \
             mock.patch.object(ia, "pedir_json", return_value=respuesta), \
             mock.patch.object(tendencias, "buscar_noticias", return_value=[]):
            tema = pedidos.preparar({}, "platos típicos de El Salvador (fotos en el drive comida)", "auto")
        self.assertEqual(tema["carpetas_fotos"], ["Comida"])
        self.assertTrue(tema["prioridad_fotos_propias"])


class TestTonoYRitmo(unittest.TestCase):
    def test_ritmo_segun_tono(self):
        from fabrica import movimiento
        self.assertEqual(movimiento.ritmo_de("Triste"), "lento")
        self.assertEqual(movimiento.ritmo_de("épico"), "rapido")
        self.assertEqual(movimiento.ritmo_de("informativo"), "normal")

    def test_direccion_y_personaje_en_cada_imagen(self):
        prompts = []

        def generar(prompt, carpeta, nombre, pasos=8):
            prompts.append(prompt)
            ruta = carpeta / f"{nombre}.jpg"
            ruta.write_bytes(b"x")
            return ruta

        imagenes._SIN_SERVICIO.add("pollinations")
        with mock.patch.object(imagenes, "cloudflare", side_effect=generar), \
             mock.patch.object(ia, "imagen_encaja", return_value=True):
            imagenes.para_escenas({}, [{"imagen": "man alone at a table"}], estilos.obtener("caricatura"),
                                  "9:16", Path(tempfile.mkdtemp()), direccion="melancholic blue light",
                                  personaje="a Latino man in his 30s")
        imagenes._SIN_SERVICIO.clear()
        self.assertIn("a Latino man in his 30s", prompts[0])
        self.assertIn("melancholic blue light", prompts[0])

    def test_primera_escena_sin_golpe(self):
        from fabrica import movimiento
        z, _, _ = movimiento._expresiones("acercar", 90, 0.16, 0.0)
        self.assertNotIn("pow", z)
        z, _, _ = movimiento._expresiones("acercar", 90, 0.16, 0.12)
        self.assertIn("pow", z)


class TestModeloPorLink(unittest.TestCase):
    def test_carpeta_de_drive_solo_baja_el_modelo(self):
        from fabrica import descargas

        class Archivo:
            def __init__(self, id_, ruta):
                self.id, self.path = id_, ruta

        carpeta = Path(tempfile.mkdtemp())
        lista = [Archivo("1", "M/G_2333.pth"), Archivo("2", "M/HYAKO_285e.pth"),
                 Archivo("3", "M/added_HYAKO.index"), Archivo("4", "M/train.log")]
        bajados = []

        def bajar(id, output, quiet):
            Path(output).write_bytes(b"x")
            bajados.append(id)

        saltar = lambda n: n.startswith(("G_", "D_")) or not n.lower().endswith((".pth", ".index", ".zip"))
        with mock.patch("gdown.download_folder", return_value=lista), mock.patch("gdown.download", side_effect=bajar):
            archivos = descargas.bajar("https://drive.google.com/drive/folders/abc?usp=sharing", carpeta, saltar)
        self.assertEqual(bajados, ["2", "3"])
        self.assertEqual(sorted(p.name for p in archivos), ["HYAKO_285e.pth", "added_HYAKO.index"])


class TestFirma(unittest.TestCase):
    def test_video_firmado_con_la_marca(self):
        import json
        import subprocess
        import imageio_ffmpeg
        carpeta = Path(tempfile.mkdtemp())
        crudo = carpeta / "crudo.mp4"
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "color=c=blue:s=320x568:d=1", "-c:v", "libx264", str(crudo)], check=True)
        cfg = {"logo": {"texto": "DESVERGUEOFFICIAL", "archivo": str(carpeta / "no.png")},
               "firma": {"autor": "DESVERGUEOFFICIAL"}}
        final = video.poner_logo(cfg, crudo, carpeta / "final.mp4", titulo="Mi video")
        salida = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags", "-of", "json",
                                 str(final)], capture_output=True, text=True).stdout
        etiquetas = {k.lower(): v for k, v in json.loads(salida)["format"]["tags"].items()}
        self.assertEqual(etiquetas["artist"], "DESVERGUEOFFICIAL")
        self.assertEqual(etiquetas["title"], "Mi video")
        self.assertNotIn("Lavf", etiquetas.get("encoder", ""))


class TestModeloConRclone(unittest.TestCase):
    def test_carpeta_compartida_se_baja_con_rclone(self):
        from fabrica import descargas
        carpeta = Path(tempfile.mkdtemp())

        def correr(cmd, **kw):
            (carpeta / "respaldo").mkdir(exist_ok=True)
            (carpeta / "respaldo" / "HYAKO_285e.pth").write_bytes(b"x")
            return mock.Mock(returncode=0)

        with mock.patch("shutil.which", return_value="/usr/bin/rclone"), \
             mock.patch("subprocess.run", side_effect=correr) as run:
            archivos = descargas.bajar_con_rclone(
                "https://drive.google.com/drive/folders/1n3qMPuJXE9hTYmL5xpygo6wQxZtXFvdX?usp=sharing",
                carpeta, ["- G_*", "+ *.pth", "- *"])
        cmd = run.call_args.args[0]
        self.assertIn("--drive-root-folder-id", cmd)
        self.assertIn("1n3qMPuJXE9hTYmL5xpygo6wQxZtXFvdX", cmd)
        self.assertEqual([p.name for p in archivos], ["HYAKO_285e.pth"])


class TestFotosDeProductos(unittest.TestCase):
    def test_bing_imagenes_lee_resultados(self):
        html = ('<a class="iusc" m="{&quot;murl&quot;:&quot;https://tienda.com/nike.jpg&quot;,'
                '&quot;purl&quot;:&quot;https://tienda.com/nike&quot;}">')
        with mock.patch("requests.get", return_value=mock.Mock(ok=True, text=html)):
            r = _ORIGINALES["bing_imagenes"]("Nike Revolution 7")
        self.assertEqual(r, [("https://tienda.com/nike.jpg", "tienda.com", "https://tienda.com/nike")])

    def test_foto_de_producto_se_muestra_completa(self):
        from PIL import Image, ImageDraw
        carpeta = Path(tempfile.mkdtemp())
        img = Image.new("RGB", (1000, 1000), (255, 255, 255))
        ImageDraw.Draw(img).rectangle([200, 400, 800, 650], fill=(20, 20, 20))
        img.save(carpeta / "tenis.jpg")
        salida = imagenes.preparar_real(carpeta / "tenis.jpg", "9:16")
        self.assertEqual(Image.open(salida).size, (1080, 1920))

    def test_realista_busca_la_foto_real_de_cada_escena(self):
        consultas = []

        class BancoFalso:
            def __init__(self, carpeta):
                pass

            def mejor(self, consulta, descripcion, elegir, lote=6):
                consultas.append(consulta)
                return None

        from fabrica import fotos_web
        with mock.patch.object(fotos_web, "Banco", BancoFalso), \
             mock.patch.object(imagenes, "wikimedia", return_value=None), \
             mock.patch.object(imagenes, "pexels_foto", return_value=None), \
             mock.patch.object(imagenes, "pixabay_foto", return_value=None), \
             mock.patch.object(imagenes, "cloudflare", return_value=None), \
             mock.patch.object(imagenes, "pollinations", return_value=None), \
             self.assertRaises(RuntimeError):  # sin ninguna imagen el video no puede seguir
            imagenes.para_escenas({"imagenes": {"fotos_reales": False}},
                                  [{"imagen": "x", "foto_real": "Nike Revolution 7 tenis"}],
                                  estilos.obtener("realista"), "9:16", Path(tempfile.mkdtemp()), tema="tenis")
        self.assertEqual(consultas[0], "Nike Revolution 7 tenis")


class TestVozSigueIntentando(unittest.TestCase):
    def test_si_el_link_falla_intenta_sacar_del_checkpoint(self):
        from fabrica import descargas, voz_applio
        carpeta = Path(tempfile.mkdtemp())
        modelo = carpeta / "HYAKO_desde_checkpoint.pth"
        def extraer_falso(_carpeta):
            modelo.write_bytes(b"x")
            return modelo

        modelo = carpeta / "x" / "HYAKO_desde_checkpoint.pth"
        modelo.parent.mkdir()

        with mock.patch.object(voz_applio, "MODELOS", carpeta), \
             mock.patch.object(descargas, "bajar_con_rclone", return_value=[]), \
             mock.patch.object(descargas, "bajar", side_effect=RuntimeError("No se pudo descargar")), \
             mock.patch.object(voz_applio, "extraer_de_entrenamiento", side_effect=extraer_falso) as extraer:
            pth, idx = voz_applio.traer_modelo({"voz": {"link_modelo": "https://drive.google.com/drive/folders/x"}})
        extraer.assert_called_once()
        self.assertEqual(pth, modelo)


class TestRevisionDeFotosWeb(unittest.TestCase):
    def _banco(self, n=3):
        from fabrica import fotos_web
        banco = fotos_web.Banco(Path(tempfile.mkdtemp()))
        banco.fotos["tenis"] = [(Path(f"/x/{k}.jpg"), f"cred{k}") for k in range(n)]
        return banco

    def test_sin_revision_no_se_usa_ninguna(self):
        banco = self._banco()
        self.assertIsNone(banco.mejor("tenis", "tenis Nike", lambda rutas, d: None))
        self.assertEqual(banco.usadas, set())  # quedan libres para otra escena

    def test_usa_la_que_elige_gemini_y_libera_las_demas(self):
        banco = self._banco()
        r = banco.mejor("tenis", "tenis Nike", lambda rutas, d: [2])
        self.assertEqual(r, (Path("/x/2.jpg"), "cred2"))
        self.assertEqual(banco.usadas, {"/x/2.jpg"})

    def test_gemini_revisa_varias_en_una_llamada(self):
        from PIL import Image
        carpeta = Path(tempfile.mkdtemp())
        rutas = []
        for k in range(3):
            Image.new("RGB", (50, 50)).save(carpeta / f"{k}.jpg")
            rutas.append(carpeta / f"{k}.jpg")
        respuesta = mock.Mock(ok=True, status_code=200)
        respuesta.json.return_value = {"choices": [{"message": {"content": '{"good": [1, 7]}'}}]}
        with mock.patch.dict("os.environ", {"GEMINI_API_KEY": "k"}), \
             mock.patch("requests.post", return_value=respuesta) as post:
            self.assertEqual(ia.elegir_imagenes({}, rutas, "tenis"), [1])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(len(post.call_args.kwargs["json"]["messages"][0]["content"]), 4)


class TestModeloFinal(unittest.TestCase):
    def test_link_nuevo_baja_el_modelo_final_con_indice(self):
        from fabrica import descargas, voz_applio
        carpeta = Path(tempfile.mkdtemp())
        links = ("https://drive.google.com/drive/folders/RESPALDO "
                 "https://drive.google.com/file/d/INDEX/view")

        def rclone(link, destino, filtros, remoto):
            destino.mkdir(parents=True, exist_ok=True)
            if "RESPALDO" in link:
                (destino / "G_2333333.pth").write_bytes(b"x")
                (destino / "HYAKO_LOCUTOR_300e_9000s.pth").write_bytes(b"x")
                (destino / "HYAKO_desde_checkpoint.pth").write_bytes(b"x")
            else:
                (destino / "added_HYAKO.index").write_bytes(b"x")
            return [destino]

        with mock.patch.object(voz_applio, "MODELOS", carpeta), \
             mock.patch.object(descargas, "bajar_con_rclone", side_effect=rclone) as baja:
            pth, idx = voz_applio.traer_modelo({"voz": {"link_modelo": links}})
        self.assertEqual(pth.name, "HYAKO_LOCUTOR_300e_9000s.pth")
        self.assertEqual(idx.name, "added_HYAKO.index")
        self.assertEqual(baja.call_count, 2)


class TestVozYo(unittest.TestCase):
    def test_junta_varias_muestras(self):
        import subprocess
        import imageio_ffmpeg
        from fabrica import voz_yo
        carpeta = Path(tempfile.mkdtemp())
        for nombre in ("muestra1.mp3", "muestra2.mp3", "muestra3.mp3", "otro.mp3"):
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            "sine=f=200:d=20", str(carpeta / nombre)], check=True)
        salida = voz_yo.preparar_muestra(list(carpeta.glob("*.mp3")), carpeta / "m.wav")
        self.assertAlmostEqual(voz_yo._duracion(salida), 10, delta=0.6)

    def test_muestra_usa_archivo_muestra_si_existe(self):
        import subprocess
        import imageio_ffmpeg
        from fabrica import voz_yo
        carpeta = Path(tempfile.mkdtemp())
        for nombre, segundos in (("largo.mp3", 40), ("muestra.mp3", 12)):
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"sine=f=200:d={segundos}", str(carpeta / nombre)], check=True)
        salida = voz_yo.preparar_muestra(list(carpeta.glob("*.mp3")), carpeta / "m.wav")
        self.assertTrue(salida.exists())
        self.assertLess(voz_yo._duracion(salida), 13)

    def test_si_la_voz_yo_falla_sale_jorge(self):
        from fabrica import voz_yo
        datos = {"titulo": "T", "guion": "hola", "escenas": [{"texto": "a"}]}
        cfg = {"voz": {"lector": "yo"}}
        with mock.patch.object(voz_yo, "generar", side_effect=RuntimeError("sin grabaciones")), \
             mock.patch.object(voz, "probar_edge", return_value=None) as edge, \
             mock.patch.object(voz, "narracion_google", side_effect=RuntimeError("parar aquí")):
            with self.assertRaises(RuntimeError):
                video.armar(cfg, datos, estilos.obtener("caricatura"), [None], Path(tempfile.mkdtemp()))
        edge.assert_called_once()  # cayó a la voz normal
        self.assertIn("la voz 'yo' falló", voz.ULTIMA["voz"])


class TestLecturaYEscudos(unittest.TestCase):
    def test_guion_listo_para_leer(self):
        from fabrica.voz_yo import para_leer
        texto = para_leer("América ganó 2-1, subió 15% y cuesta $99 en EE.UU.")
        self.assertEqual(texto, "América ganó dos a uno, subió quince por ciento y cuesta noventa y nueve "
                                "dólares en Estados Unidos.")

    def test_escudo_desde_wikipedia(self):
        respuesta = mock.Mock()
        respuesta.json.return_value = {"query": {"pages": {"1": {
            "index": 1, "title": "Club América", "original": {"source": "https://upload.wikimedia.org/a.png"}}}}}
        with mock.patch("requests.get", return_value=respuesta):
            r = _ORIGINALES["imagen_wikipedia"]("Club América")
        self.assertEqual(r[0][0], "https://upload.wikimedia.org/a.png")

    def test_banco_busca_escudo_en_wikipedia_primero(self):
        from fabrica import fotos_web
        with mock.patch.object(fotos_web, "imagen_wikipedia", return_value=[]) as wiki:
            fotos_web.Banco(Path(tempfile.mkdtemp())).cargar("escudo Club América")
        wiki.assert_called_once_with("Club América")

    def test_pedido_trae_contenido_de_las_notas(self):
        from fabrica import fotos_web, mis_fotos
        notas = [("América 2-1 Pumas", "TUDN", "https://tudn.com/x", "El América venció 2-1 a Pumas...")]
        respuesta = {"tema": "Liga MX", "consulta": "resultados liga mx", "estilo": "comic"}
        with mock.patch.object(mis_fotos, "categorias", return_value=[]), \
             mock.patch.object(ia, "pedir_json", return_value=respuesta), \
             mock.patch.object(tendencias, "buscar_noticias", return_value=[]), \
             mock.patch.object(fotos_web, "noticias_texto", return_value=notas):
            tema = pedidos.preparar({}, "resultados del futbol mexicano", "auto")
        self.assertIn("venció 2-1 a Pumas", tema["contexto"])
        self.assertEqual(tema["fuentes"][0][2], "https://tudn.com/x")


class TestReferenciasPorNombre(unittest.TestCase):
    def _buscar(self, consulta):
        from fabrica import mis_fotos
        raiz = Path(tempfile.mkdtemp())
        (raiz / "logos equipos").mkdir()
        for n in ("club-america.3a4adeb2.png", "chivas-guadalajara-logo-png_seeklogo-474960.png",
                  "pumas-unam-logo-3-1.png", "Real_Madrid.png"):
            (raiz / "logos equipos" / n).write_bytes(b"x")
        mis_fotos._INDICE.clear()
        with mock.patch.object(mis_fotos, "_local", return_value=raiz), \
             mock.patch.object(mis_fotos, "_remoto", return_value=None):
            r = mis_fotos.buscar_referencia({}, consulta, Path(tempfile.mkdtemp()))
        mis_fotos._INDICE.clear()
        return r.name if r else None

    def test_escudos_por_nombre(self):
        self.assertEqual(self._buscar("escudo Club América"), "club-america.3a4adeb2.png")
        self.assertEqual(self._buscar("escudo Club Deportivo Guadalajara Chivas"),
                         "chivas-guadalajara-logo-png_seeklogo-474960.png")
        self.assertEqual(self._buscar("escudo Pumas UNAM"), "pumas-unam-logo-3-1.png")

    def test_no_confunde(self):
        self.assertIsNone(self._buscar("escudo Toluca"))
        self.assertIsNone(self._buscar("estadio Real Madrid Bernabéu"))


class TestAvatar(unittest.TestCase):
    def _clip(self, ruta, segundos, tam="1080x1920", audio=True):
        import subprocess
        import imageio_ffmpeg
        cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
               f"color=c=blue:s={tam}:d={segundos}:r=25"]
        if audio:
            cmd += ["-f", "lavfi", "-i", f"sine=f=300:d={segundos}", "-c:a", "aac", "-shortest"]
        subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(ruta)], check=True)
        return ruta

    def test_las_cuatro_formas_conservan_la_duracion(self):
        from fabrica import avatar
        c = Path(tempfile.mkdtemp())
        video = self._clip(c / "v.mp4", 14)
        completo = self._clip(c / "a.mp4", 14, "360x640", audio=False)
        corto = self._clip(c / "ic.mp4", 8.4, "360x640", audio=False)
        for modo, av in (("intro y cierre", corto), ("esquina", completo), ("dividida", completo),
                         ("mixto", completo)):
            salida = avatar.componer(video, av, modo, 4, 4, c / f"{modo}.mp4")
            self.assertAlmostEqual(avatar._duracion(salida), 14, delta=0.2)

    def test_audio_solo_intro_y_cierre(self):
        from fabrica import avatar
        c = Path(tempfile.mkdtemp())
        narracion = self._clip(c / "n.mp4", 30)
        audio, total = avatar.audio_para_avatar(narracion, "intro y cierre", 5, 5, c)
        self.assertAlmostEqual(avatar._duracion(audio), 10.4, delta=0.2)
        audio, _ = avatar.audio_para_avatar(narracion, "mixto", 5, 5, c)
        self.assertAlmostEqual(avatar._duracion(audio), 30, delta=0.2)

    def test_sin_kaggle_el_video_sale_igual(self):
        from fabrica import avatar
        c = Path(tempfile.mkdtemp())
        narracion = self._clip(c / "n.mp4", 12)
        datos = {"audio_narracion": str(narracion)}
        with mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch.object(avatar, "elegir_video_base", return_value=self._clip(c / "b.mp4", 20, "360x640")):
            r = avatar.agregar({"avatar": {"modo": "esquina"}}, c / "video.mp4", datos, "deportes", c, 1)
        self.assertEqual(r, c / "video.mp4")
        self.assertIn("KAGGLE", datos["avatar_usado"])

    def test_no_repite_el_ultimo_video_base(self):
        from fabrica import avatar
        c = Path(tempfile.mkdtemp())
        lista = mock.Mock(stdout="uno.mp4\ndos.mp4\n")
        with mock.patch.object(avatar, "HISTORIAL", c / "h.json"), \
             mock.patch("subprocess.run", return_value=lista):
            (c / "h.json").write_text('["uno.mp4"]')
            elegido = avatar.elegir_video_base({}, c / "base")
        self.assertEqual(elegido.name, "dos.mp4")


class TestFotosAlEstilo(unittest.TestCase):
    def _correr(self, estilo, foto):
        estilizadas = []

        def estilizar(ruta, prompt, aspecto, fuerza=0.55):
            estilizadas.append(prompt)
            salida = ruta.with_name("x-estilo.png")
            salida.write_bytes(b"x")
            return salida

        with mock.patch.object(imagenes, "wikimedia", return_value=(foto, "credito")), \
             mock.patch.object(imagenes, "estilizar", side_effect=estilizar), \
             mock.patch.object(ia, "imagen_encaja", return_value=True):
            rutas, _, conteo = imagenes.para_escenas(
                {"imagenes": {"fotos_web": False, "estilizar_fotos": self.estilizar}},
                [{"imagen": "stadium", "foto_real": "Estadio Azteca"}],
                estilos.obtener(estilo), "9:16", foto.parent)
        return rutas[0], estilizadas, conteo

    def _foto(self, color=(30, 120, 40), transparente=False):
        from PIL import Image
        c = Path(tempfile.mkdtemp())
        modo = "RGBA" if transparente else "RGB"
        Image.new(modo, (900, 1600), color + ((0,) if transparente else ())).save(c / "f.png")
        return c / "f.png"

    estilizar = True

    def test_por_defecto_la_foto_real_queda_limpia(self):
        self.estilizar = False
        ruta, estilizadas, conteo = self._correr("caricatura", self._foto())
        self.assertEqual(estilizadas, [])
        self.assertEqual(conteo["estilizadas"], 0)

    def test_caricatura_pasa_la_foto_al_estilo(self):
        ruta, estilizadas, conteo = self._correr("caricatura", self._foto())
        self.assertEqual(ruta.name, "x-estilo.png")
        self.assertIn("2D cartoon", estilizadas[0])
        self.assertEqual(conteo["estilizadas"], 1)

    def test_realista_y_logos_quedan_reales(self):
        _, estilizadas, _ = self._correr("realista", self._foto())
        self.assertEqual(estilizadas, [])
        ruta, estilizadas, _ = self._correr("caricatura", self._foto(transparente=True))
        self.assertEqual(estilizadas, [])
        self.assertTrue(ruta.name.endswith("-encuadre.jpg"))


class TestMezcla(unittest.TestCase):
    def test_porcentajes_suman_100(self):
        from fabrica import mezcla
        self.assertEqual(sum(mezcla._pesos({"mezcla": {"segun_vistas": False}}).values()), 100)

    def test_con_el_tiempo_respeta_los_porcentajes(self):
        from fabrica import mezcla
        historial = []
        for _ in range(200):
            historial.append({"mezcla": mezcla.elegir_categorias({}, historial, 1)[0]})
        ultimos = [e["mezcla"] for e in historial[-100:]]
        self.assertAlmostEqual(ultimos.count("general"), 20, delta=4)
        self.assertAlmostEqual(ultimos.count("deportes"), 17, delta=4)
        self.assertAlmostEqual(ultimos.count("musica"), 8, delta=3)

    def test_no_repite_jarritos(self):
        from datetime import datetime
        from fabrica import mezcla
        historial = [{"tema": "El curioso éxito de los refrescos Jarritos como bebida de lujo",
                      "fecha": datetime.now().isoformat(timespec="minutes")}]
        self.assertTrue(mezcla.repetido("Jarritos: de refresco de barrio en México a bebida de lujo", historial))
        self.assertFalse(mezcla.repetido("América vence a Chivas en el clásico", historial))

    def test_ronda_elige_tema_no_repetido(self):
        from fabrica import mezcla
        opciones = [{"tema": "Jarritos bebida de lujo", "categoria": "general", "estilo": "comic"},
                    {"tema": "Nuevo récord de Messi", "categoria": "deportes", "estilo": "comic"}]
        historial = [{"tema": "Jarritos refresco de lujo", "fecha": "2999-01-01T00:00"}]
        with mock.patch.object(mezcla, "elegir_categorias", return_value=["deportes"]), \
             mock.patch.object(mezcla, "candidatos", return_value=[tendencias.Candidato("x", "news", "MX", "es")]), \
             mock.patch.object(tendencias, "elegir_temas", return_value=opciones):
            temas = mezcla.temas_de_la_ronda({}, 1, historial, "auto")
        self.assertEqual(temas[0]["tema"], "Nuevo récord de Messi")
        self.assertEqual(temas[0]["mezcla"], "deportes")


class TestGuionSinPuntos(unittest.TestCase):
    def test_se_pide_puntuacion_si_falta(self):
        sin_puntos = " ".join(["palabra"] * 120)
        con_puntos = ". ".join(["palabra"] * 120) + "."
        with mock.patch.object(ia, "pedir_json", return_value={"texto": con_puntos}) as pj:
            self.assertEqual(guion.puntuar({}, sin_puntos), con_puntos)
        pj.assert_called_once()
        with mock.patch.object(ia, "pedir_json") as pj:
            self.assertEqual(guion.puntuar({}, con_puntos), con_puntos)
        pj.assert_not_called()

    def test_no_acepta_si_reescribe(self):
        sin_puntos = " ".join(["palabra"] * 120)
        with mock.patch.object(ia, "pedir_json", return_value={"texto": "Otra cosa totalmente distinta."}):
            self.assertEqual(guion.puntuar({}, sin_puntos), sin_puntos)


class TestLimpiarVoz(unittest.TestCase):
    def test_silencios_quedan_limpios(self):
        import subprocess
        import imageio_ffmpeg
        from fabrica import voz_yo
        c = Path(tempfile.mkdtemp())
        # 1 s de "voz", 1 s de soplido suave, 1 s de "voz"
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", "sine=f=220:d=1", "-f", "lavfi", "-i", "anoisesrc=d=1:a=0.004",
                        "-f", "lavfi", "-i", "sine=f=220:d=1", "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1",
                        str(c / "a.wav")], check=True)
        limpia = voz_yo.limpiar({}, c / "a.wav")
        self.assertTrue(limpia.name.endswith("-limpia.wav") or limpia.name.endswith("-limpia-pausas.wav"))

        def volumen(ruta, desde):
            r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-ss", str(desde), "-t", "0.6", "-i", str(ruta),
                                "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
            import re
            return float(re.search(r"mean_volume: (-?[\d.]+)", r.stderr).group(1))

        self.assertLess(volumen(limpia, 1.2), volumen(c / "a.wav", 1.2) - 10)  # el soplido bajó mucho


class TestMapas(unittest.TestCase):
    def test_mapa_animado(self):
        from PIL import Image
        from fabrica import graficas, mapas
        salida = Path(tempfile.mkdtemp()) / "m.mp4"
        with mock.patch.object(mapas, "geocodificar", return_value=(26.7, -80.05, "Palm Beach, Florida")), \
             mock.patch.object(mapas, "_tesela", return_value=Image.new("RGB", (512, 512), (200, 220, 200))):
            graficas.clip({"tipo": "mapa", "lugar": "Palm Beach", "titulo": "Palm Beach",
                           "zoom_inicio": 8, "zoom_final": 10}, 1, "9:16", "", salida)
        self.assertGreater(salida.stat().st_size, 1000)

    def test_coordenadas_en_el_mapa(self):
        from fabrica import mapas
        x, y = mapas._mundo(0, 0, 0)
        self.assertAlmostEqual(x, 256)
        self.assertAlmostEqual(y, 256)


class TestEfectos(unittest.TestCase):
    def test_whoosh_en_los_cortes(self):
        import subprocess
        import imageio_ffmpeg
        from fabrica import efectos
        c = Path(tempfile.mkdtemp())
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "color=c=blue:s=320x568:d=6:r=25", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-t", "6", "-c:v", "libx264", "-c:a", "aac", str(c / "v.mp4")], check=True)
        salida = efectos.agregar({"efectos": {"activos": True}}, c / "v.mp4", [2.0, 4.0], c / "e.mp4")
        self.assertEqual(salida, c / "e.mp4")
        r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-ss", "1.8", "-t", "0.4", "-i", str(salida),
                            "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
        import re
        self.assertGreater(float(re.search(r"max_volume: (-?[\d.]+)", r.stderr).group(1)), -40)
        self.assertAlmostEqual(efectos.duracion(salida), 6, delta=0.2)


class TestMusica(unittest.TestCase):
    def test_animo_segun_tono(self):
        from fabrica import musica
        self.assertEqual(musica.animo_de("Épico"), "epica")
        self.assertEqual(musica.animo_de("triste"), "triste")
        self.assertEqual(musica.animo_de("urgente"), "tension")
        self.assertEqual(musica.animo_de("algo raro"), "neutral")

    def test_elige_cancion_de_la_carpeta_del_animo(self):
        from fabrica import musica
        destino = Path(tempfile.mkdtemp())

        def correr(cmd, **kw):
            if cmd[1] == "lsf":
                return mock.Mock(stdout="epica/beat1.mp3\ntriste/piano.mp3\ndeportes/himno.mp3\n")
            Path(cmd[3]).write_bytes(b"x")
            return mock.Mock(returncode=0)

        with mock.patch("shutil.which", return_value="/usr/bin/rclone"), \
             mock.patch("subprocess.run", side_effect=correr):
            r = musica.elegir({}, "épico", "deportes", destino)
            r2 = musica.elegir({}, "alegre", "deportes", destino)
        self.assertEqual(r.name, "fabrica-beat1.mp3")
        self.assertEqual(r2.name, "fabrica-himno.mp3")  # no hay "alegre": usa la de la categoría


class TestMiniatura(unittest.TestCase):
    def test_miniatura_llamativa(self):
        from PIL import Image
        from fabrica import miniaturas
        c = Path(tempfile.mkdtemp())
        Image.new("RGB", (800, 800), (40, 120, 200)).save(c / "f.jpg")
        r = miniaturas.crear({"logo": {"texto": "DESVERGUEOFFICIAL"}}, {"titulo": "Un título de prueba largo"},
                             [None, c / "f.jpg"], c / "no.mp4", c / "m.jpg")
        self.assertEqual(Image.open(r).size, (1080, 1920))


class TestClipsReales(unittest.TestCase):
    def test_escena_con_clip_real(self):
        import subprocess
        import imageio_ffmpeg
        from fabrica import fotos_web, movimiento
        c = Path(tempfile.mkdtemp())
        video = c / "fuente.mp4"
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc2=s=640x360:d=2:r=25", "-c:v", "libx264", str(video)], check=True)

        def bajar(url, ruta):
            ruta.write_bytes(b"x" * 30000)
            return ruta

        escenas = [{"imagen": "ambulance", "busqueda_stock": "ambulance"}, {"imagen": "road night"}]
        with mock.patch.object(fotos_web, "clips_stock", return_value=[("http://v/1.mp4", "http://v/1.jpg", "Video: x")]), \
             mock.patch.object(fotos_web, "_bajar", side_effect=bajar), \
             mock.patch.object(ia, "elegir_imagenes", return_value=[0]), \
             mock.patch("requests.get", return_value=mock.Mock(ok=True, content=video.read_bytes())), \
             mock.patch.object(imagenes, "cloudflare", return_value=None), \
             mock.patch.object(imagenes, "pollinations", return_value=None), \
             mock.patch.object(imagenes, "wikimedia", return_value=None):
            rutas, creditos, conteo = imagenes.para_escenas(
                {"imagenes": {"clips_proporcion": 1, "fotos_web": False}}, escenas,
                estilos.obtener("realista"), "9:16", c)
        self.assertEqual(conteo["clips"], 2 if rutas[1] else 1)
        self.assertTrue(str(rutas[0]).endswith(".mp4"))
        salida = movimiento.clip_de_video(rutas[0], 3.0, "9:16", c / "out.mp4")
        from fabrica import efectos
        self.assertAlmostEqual(efectos.duracion(salida), 3.0, delta=0.15)


class TestAnimar(unittest.TestCase):
    def test_apagado_no_toca_nada(self):
        from fabrica import animar
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(animar.animar({}, [{}], ["a.jpg"], Path(tempfile.mkdtemp()), {}), ["a.jpg"])

    def test_anima_las_escenas_elegidas(self):
        from PIL import Image
        from fabrica import animar, avatar
        c = Path(tempfile.mkdtemp())
        imgs = []
        for k in range(5):
            Image.new("RGB", (100, 100)).save(c / f"i{k}.jpg")
            imgs.append(c / f"i{k}.jpg")
        escenas = [{"imagen": f"scene {k}"} for k in range(5)]

        def kaggle(entrada, script, nombre, espera):
            (entrada.parent / "r" / "clips").mkdir(parents=True)
            for e in __import__("json").loads((entrada / "escenas.json").read_text()):
                (entrada.parent / "r" / "clips" / f"{e['id']}.mp4").write_bytes(b"x" * 30000)
            return entrada.parent / "r"

        datos = {}
        with mock.patch.dict("os.environ", {"ANIMAR": "si"}), \
             mock.patch.object(avatar, "correr_en_kaggle", side_effect=kaggle):
            nuevas = animar.animar({"animar": {"escenas": 2}}, escenas, imgs, c, datos)
        self.assertEqual(datos["animadas"], "2")
        self.assertEqual(sum(1 for n in nuevas if str(n).endswith(".mp4")), 2)
        self.assertTrue(str(nuevas[0]).endswith(".mp4"))  # el gancho siempre se anima

    def test_si_kaggle_falla_quedan_las_imagenes(self):
        from PIL import Image
        from fabrica import animar, avatar
        c = Path(tempfile.mkdtemp())
        Image.new("RGB", (100, 100)).save(c / "i.jpg")
        datos = {}
        with mock.patch.dict("os.environ", {"ANIMAR": "si"}), \
             mock.patch.object(avatar, "correr_en_kaggle", side_effect=RuntimeError("ocupado")):
            r = animar.animar({}, [{"imagen": "x"}], [c / "i.jpg"], c, datos)
        self.assertEqual(r, [c / "i.jpg"])
        self.assertIn("ocupado", datos["animadas"])


class TestEstadisticas(unittest.TestCase):
    def test_factores_por_categoria(self):
        from fabrica import estadisticas
        historial = ([{"titulo": f"Gol del América número {k}", "mezcla": "deportes"} for k in range(4)]
                     + [{"titulo": f"Bitcoin sube otra vez día {k}", "mezcla": "finanzas"} for k in range(4)])
        videos = ([{"titulo": f"Gol del América número {k}", "vistas": 9000} for k in range(4)]
                  + [{"titulo": f"Bitcoin sube otra vez día {k}", "vistas": 1000} for k in range(4)])
        r = estadisticas.calcular(historial, videos)
        self.assertEqual(r["factores"]["deportes"], 1.4)
        self.assertEqual(r["factores"]["finanzas"], 0.7)
        self.assertEqual(r["mejores"][0]["mezcla"], "deportes")

    def test_la_mezcla_se_inclina_hacia_lo_que_funciona(self):
        from fabrica import estadisticas, mezcla
        with mock.patch.object(estadisticas, "leer", return_value={"factores": {"deportes": 1.4}}):
            self.assertAlmostEqual(mezcla._pesos({})["deportes"], 17 * 1.4)
        with mock.patch.object(estadisticas, "leer", return_value={}):
            self.assertEqual(mezcla._pesos({})["deportes"], 17)


if __name__ == "__main__":
    unittest.main()


class TestMejorDelDia(unittest.TestCase):
    def test_elige_el_de_mas_nota_de_las_ultimas_24_horas(self):
        from datetime import datetime
        from fabrica import mejor_del_dia
        ahora = datetime(2026, 11, 5, 22, 0)
        entradas = [
            {"numero": 1, "fecha": "2026-11-04T07:00", "automatico": True, "drive": "a.mp4", "nota": 99},
            {"numero": 2, "fecha": "2026-11-05T07:00", "automatico": True, "drive": "b.mp4", "nota": 70},
            {"numero": 3, "fecha": "2026-11-05T12:00", "automatico": True, "drive": "c.mp4", "nota": 85},
            {"numero": 4, "fecha": "2026-11-05T13:00", "automatico": False, "drive": "d.mp4", "nota": 95},
            {"numero": 5, "fecha": "2026-11-05T16:00", "automatico": True, "drive": "", "nota": 90},
        ]
        self.assertEqual(mejor_del_dia.elegir(entradas, ahora)["numero"], 3)

    def test_no_publica_dos_el_mismo_dia(self):
        from datetime import datetime
        from fabrica import mejor_del_dia
        ahora = datetime(2026, 11, 5, 22, 0)
        entradas = [
            {"numero": 1, "fecha": "2026-11-05T07:00", "automatico": True, "drive": "a.mp4", "nota": 60,
             "publicado": True, "publicado_mejor": True},
            {"numero": 2, "fecha": "2026-11-05T12:00", "automatico": True, "drive": "b.mp4", "nota": 80},
        ]
        self.assertIsNone(mejor_del_dia.elegir(entradas, ahora))

    def test_nota_baja_si_la_voz_fallo_o_hubo_rechazos(self):
        from fabrica import mejor_del_dia
        bien = mejor_del_dia.nota_tecnica({"voz_usada": {"voz": "yo (...) + tu modelo"}}, {"ia": 10})
        mal = mejor_del_dia.nota_tecnica({"voz_usada": {"voz": "Edge — la voz 'yo' falló"},
                                          "avatar_usado": "no — error"}, {"ia": 5, "rechazadas": 5})
        self.assertEqual(bien, 40)
        self.assertLess(mal, 20)

    def test_puntuar_junta_ia_y_calidad(self):
        from fabrica import mejor_del_dia
        datos = {"titulo": "x", "guion": "y"}
        with mock.patch.object(ia, "pedir_json", return_value={"nota": 8, "por_que": "buen gancho"}):
            self.assertEqual(mejor_del_dia.puntuar({}, datos, {"tema": "t"}, {"ia": 3}), 88.0)
        self.assertIn("NOTA PARA", salidas.ficha_texto({**datos, "descripcion": "", "hashtags": []},
                                                       {"tema": "t", "categoria": "c", "fuentes": []}, []))


class TestGeografia(unittest.TestCase):
    def test_estilo_geografia_existe(self):
        e = estilos.obtener("geografia")
        self.assertIn("Geografía", e.nombre)

    def test_escenas_con_mapa_no_piden_imagen(self):
        escenas = [{"texto": "a", "mapa": {"resaltar": ["México"]}}, {"texto": "b", "imagen": "x"}]
        self.assertEqual(imagenes._elegir_escenas(escenas, 10), {1})

    def test_escena_con_mapa_usa_el_mapa_animado(self):
        from fabrica import mapa_geo, movimiento
        c = Path(tempfile.mkdtemp())
        llamadas = []

        def falso(m, segundos, aspecto, salida, estado):
            llamadas.append((m, estado))
            salida.write_bytes(b"x")
            return salida

        with mock.patch.object(mapa_geo, "clip", side_effect=falso):
            clips = movimiento.clips_de_escenas(
                {}, [{"texto": "uno", "mapa": {"resaltar": ["México"]}, "texto_pantalla": "¿MÉXICO?"},
                     {"texto": "dos", "mapa": {"frontera": ["México", "Guatemala"], "mantener": True}}],
                [None, None], "geografia", 6, c)
        self.assertEqual(len(clips), 2)
        self.assertEqual(llamadas[0][0]["pregunta"], "¿MÉXICO?")
        self.assertIs(llamadas[0][1], llamadas[1][1])  # la cámara sigue de una escena a otra

    def test_grafica_mapa_de_otros_estilos(self):
        from fabrica import mapa_geo
        pais = mapa_geo.Lugar("Honduras", None, "punto", (-86.0, 14.0))
        with mock.patch.object(mapa_geo, "buscar", return_value=pais):
            m = mapa_geo.desde_grafica({"tipo": "mapa", "lugar": "Tegucigalpa, Honduras", "detalle": "aquí pasó"})
        self.assertEqual(m["puntos"][0]["lugar"], "Tegucigalpa, Honduras")
        self.assertEqual(m["pregunta"], "AQUÍ PASÓ")

    def test_texto_en_pantalla(self):
        from PIL import Image
        from fabrica import movimiento
        c = Path(tempfile.mkdtemp())
        Image.new("RGB", (600, 900), (20, 90, 30)).save(c / "a.png")
        salida = movimiento.texto_en_pantalla(c / "a.png", "¡nadie lo sabía!", "9:16", c / "t.png")
        self.assertEqual(Image.open(salida).size, (1080, 1920))

    def test_guion_geografia_pide_mapas(self):
        capturado = {}

        def pedir(cfg, sistema, usuario, temperatura=0.7):
            capturado["usuario"], capturado["sistema"] = usuario, sistema
            return {"guion": "Hola. Esto es una prueba.", "escenas": [{"texto": "x", "mapa": {}}], "hashtags": []}

        with mock.patch.object(ia, "pedir_json", side_effect=pedir), \
             mock.patch.object(guion, "puntuar", side_effect=lambda cfg, t: t):
            guion.escribir({}, {"tema": "Cómo se divide México", "categoria": "curiosidades"},
                           estilos.obtener("geografia"))
        self.assertIn("MAPA SATELITAL", capturado["usuario"])
        self.assertIn("ENTRETENER", capturado["sistema"])


class TestFicha(unittest.TestCase):
    def test_ficha_junta_wikipedia_y_wikidata(self):
        from fabrica import ficha

        def falso(url, params, timeout=25):
            if "list" in params:
                return {"query": {"search": [{"title": "México"}]}}
            if "prop" in params:
                return {"query": {"pages": [{"title": "México", "pageprops": {"wikibase_item": "Q96"},
                                             "extract": "México es un país.\n== Toponimia ==\nViene del náhuatl.\n== Deportes ==\nFútbol."}]}}
            if params.get("props") == "claims":
                return {"entities": {"Q96": {"claims": {
                    "P36": [{"mainsnak": {"datavalue": {"value": {"id": "Q1489"}}}}],
                    "P1082": [{"mainsnak": {"datavalue": {"value": {"amount": "+126014024"}}},
                               "qualifiers": {"P585": [{"datavalue": {"value": {"time": "+2020-00-00"}}}]}}]}}}}
            if params.get("props") == "labels":
                return {"entities": {"Q1489": {"labels": {"es": {"value": "Ciudad de México"}}}}}
            return None

        with mock.patch.object(ficha, "_get", side_effect=falso):
            texto = ficha.datos("Cómo se divide México")
        self.assertIn("Capital: Ciudad de México", texto)
        self.assertIn("126 014 024", texto)
        self.assertIn("[Toponimia] Viene del náhuatl.", texto)
        self.assertNotIn("Fútbol", texto)


class TestGeografiaSiempreMapa(unittest.TestCase):
    def test_escenas_sin_mapa_reciben_uno(self):
        datos = {"lugar_principal": "San Miguel, El Salvador", "escenas": [
            {"texto": "a", "mapa": {"puntos": ["San Miguel, El Salvador"]}},
            {"texto": "b", "imagen": "volcano"},
            {"texto": "c", "foto_real": "Catedral de San Miguel"},
            {"texto": "d", "grafica": {"tipo": "mapa", "lugar": "Volcán Chaparrastique", "titulo": "Volcán"}},
            {"texto": "e", "grafica": {"tipo": "cifra", "valor": 247}}]}
        guion.asegurar_mapas(datos, {"tema": "San Miguel"})
        e = datos["escenas"]
        self.assertEqual(e[1]["mapa"]["resaltar"][0]["lugar"], "San Miguel, El Salvador")
        self.assertNotIn("mapa", e[2])
        self.assertIn("_mapa_respaldo", e[2])
        self.assertEqual(e[3]["mapa"]["puntos"][0]["lugar"], "Volcán Chaparrastique")
        self.assertNotIn("mapa", e[4])

    def test_geografia_no_usa_ia_para_imagenes(self):
        self.assertNotIn("ia", estilos.obtener("geografia").fuentes)

    def test_pausas_en_silencio(self):
        import subprocess
        import imageio_ffmpeg
        from fabrica import voz_yo
        c = Path(tempfile.mkdtemp())
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=220:d=1", "-f", "lavfi", "-i",
                        "anoisesrc=d=0.8:a=0.01", "-f", "lavfi", "-i", "sine=f=300:d=1", "-filter_complex",
                        "[0][1][2]concat=n=3:v=0:a=1", str(c / "t.wav")], check=True)
        salida = voz_yo.silenciar_pausas(c / "t.wav")
        r = subprocess.run([ff, "-i", str(salida), "-af", "atrim=1.25:1.55,volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True)
        self.assertIn("max_volume: -9", r.stderr)  # silencio digital (~ -91 dB)


class TestMapaAntiguo(unittest.TestCase):
    def test_mapa_antiguo_es_sepia(self):
        from PIL import Image
        from fabrica import mapa_geo
        img = Image.new("RGB", (mapa_geo.ANCHO, mapa_geo.ALTO), (20, 80, 160))
        viejo = mapa_geo.antiguo(img)
        r, g, b = viejo.getpixel((mapa_geo.ANCHO // 2, mapa_geo.ALTO // 2))
        self.assertGreater(r, b)  # café, no azul

    def test_bandera_sin_internet_no_rompe(self):
        from fabrica import mapa_geo
        self.assertIsNone(mapa_geo.bandera("País que no existe"))
