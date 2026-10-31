import unittest
from unittest import mock

import base64
import tempfile
from pathlib import Path

from fabrica import estilos, ia, imagenes, salidas, tendencias, video, voz

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
        self.assertIn("no recognizable real people", p)

    def test_realista_requiere_clave_de_stock(self):
        realista = estilos.obtener("realista")
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(estilos.disponible(realista))
            self.assertNotIn("- realista:", estilos.resumen_para_ia())
        with mock.patch.dict("os.environ", {"PIXABAY_API_KEY": "x"}, clear=True):
            self.assertTrue(estilos.disponible(realista))

    def test_estilo_desconocido(self):
        with self.assertRaises(ValueError):
            estilos.obtener("nada")

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
            rutas, _ = imagenes.para_escenas({}, escenas, estilos.obtener("caricatura"), "9:16", self.carpeta)
        self.assertEqual(len(rutas), 2)
        self.assertEqual(rutas[0].read_bytes(), jpg)
        self.assertEqual(get.call_count, 1)  # tras el 402 no se vuelve a pedir a Pollinations

    def test_ia_no_reintenta_si_pide_pago(self):
        cobro = mock.Mock(status_code=402, text="pay")
        with mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch("requests.post", return_value=cobro) as post, mock.patch("time.sleep"):
            with self.assertRaises(RuntimeError):
                ia.pedir_json({}, "s", "u")
        self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
