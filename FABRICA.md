# 🎬 Fábrica de Videos LATAM

Construida sobre [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) (licencia MIT).
Todo lo original sigue funcionando (WebUI, API, stock, publicación). Esto le suma:

1. **Busca tendencias** en Google Trends y Google News (México, Colombia, Argentina, Perú, Chile,
   EE.UU. en español e inglés, España), con prioridad al público latino.
2. **La IA elige los temas** sin repetir los ya publicados y **escribe el guion** usando solo los
   hechos de los titulares (te deja las fuentes para verificar).
3. **11 estilos visuales** (la IA elige el mejor para cada tema, o lo eliges tú).
4. **Tu logo** en cada video.
5. **Salidas combinables:** descargar, subir a Google Drive y/o publicar en redes.
6. **Corre solo:** en GitHub 5 veces al día, o en tu PC mientras esté prendida.

Todo con servicios **gratis**: Gemini, Groq, Pollinations (imágenes IA), Edge TTS (voz),
Wikimedia Commons y Pexels.

## Estilos

| Clave | Estilo | Ideal para |
|---|---|---|
| `explicativo` | Infografía plana tipo diagrama | Hackeos, economía, temas serios |
| `caricatura` | Dibujo animado, colores vivos | Farándula, deportes, virales |
| `comic` | Viñeta de cómic | Deportes, historias |
| `artistico` | Pintura al óleo | Historia, curiosidades |
| `acuarela` | Acuarela suave | Salud, estilo de vida |
| `pizarra` | Dibujo a mano en pizarra | Aprendizaje, "cómo funciona" |
| `anime` | Anime | Videojuegos, entretenimiento |
| `3d` | Animación 3D | Curiosidades, tecnología |
| `cinematografico` | Foto IA cinematográfica | Noticias, misterio |
| `noticiero` | Fotos reales con licencia libre + crédito | Noticias, deportes |
| `realista` | Fotos reales de internet: productos, marcas, lugares | Compras, productos, tecnología |
| `videos_stock` | Videos de stock (el original de MoneyPrinterTurbo) | Motivación, salud, viajes |
| `auto` | La IA elige por tema | — |

Para sumar un estilo nuevo: agrega una entrada en `fabrica/estilos.py`.

> Las imágenes con IA nunca piden caras de personas reales, logos ni marcas. Para deportes se
> usan estadios, camisetas con colores de equipo, balones, etc. El estilo `noticiero` usa fotos
> reales con licencia libre de Wikimedia Commons; los créditos quedan en la ficha `.txt`.

## 1. Claves gratis (5 minutos)

| Clave | Dónde | ¿Obligatoria? |
|---|---|---|
| `GEMINI_API_KEY` | https://aistudio.google.com/app/apikey | Sí (o Groq) |
| `GROQ_API_KEY` | https://console.groq.com/keys | Respaldo recomendado |
| `PEXELS_API_KEY` | https://www.pexels.com/api/ | Opcional (estilo `realista` y fotos de respaldo) |
| `PIXABAY_API_KEY` | https://pixabay.com/api/docs/ (inicia sesión y aparece tu clave) | Opcional, reemplaza a Pexels |
| `CLOUDFLARE_ACCOUNT_ID` y `CLOUDFLARE_API_TOKEN` | https://dash.cloudflare.com → Workers AI (ver abajo) | Recomendada: imágenes IA gratis de respaldo |
| `POLLINATIONS_TOKEN` | https://enter.pollinations.ai | Opcional (más rápido, menos límites) |
| `UPLOAD_POST_API_KEY` y `UPLOAD_POST_USERNAME` | https://upload-post.com | Solo si quieres publicar automático |

**Nunca pegues las claves en el código ni en un chat.**

**Cloudflare (imágenes IA gratis):** crea una cuenta gratis en https://dash.cloudflare.com →
menú **AI → Workers AI** → **Use REST API** → **Create a Workers AI API Token**. En esa misma
página aparece tu **Account ID**. Guarda los dos como secretos.

## 2. Modo GitHub (automático, 5 veces al día)

1. En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**.
   Crea un secreto por cada clave de la tabla.
2. Sube tu logo como `marca/logo.png`.
3. (Opcional) Copia `fabrica.example.toml` como `fabrica.toml` y cambia las perillas.
4. Listo. Hace 1 video por ronda (hora de México): lunes a viernes a las 7am, 12pm, 4pm y 10pm;
   sábado y domingo a las 7am, 11am, 3pm, 7pm y 10pm.
   - **Para hacer uno a mano:** pestaña **Actions → Fabrica de videos → Run workflow**. Ahí eliges
     cantidad, estilo, tema, Drive (sí/no) y publicar (sí/no). Funciona desde el celular.
   - **Para descargar:** abre la ejecución en **Actions**; abajo aparece `videos-N` (dura 7 días).

> ⏱️ GitHub da 2000 minutos gratis al mes en repositorios privados. Cada video tarda unos 3-6
> minutos. Con 5 rondas de 2 videos al día podrías pasarte; baja a 1 video por ronda o deja el
> repositorio público (las claves siguen seguras en Secrets).

## 3. Google Drive

Se usa [rclone](https://rclone.org/downloads/) (gratis).

1. Instálalo en tu PC (Windows: `winget install Rclone.Rclone`).
2. Ejecuta `rclone config`: `n` (nuevo) → nombre **drive** → tipo **drive** → deja vacío
   client_id/secret → scope **1** → acepta lo demás e inicia sesión con Google en el navegador.
3. En tu PC ya funciona. Para GitHub, ejecuta `rclone config show drive`, copia el texto que va
   después de `token = ` (empieza con `{"access_token"...`) y guárdalo como secreto
   `RCLONE_DRIVE_TOKEN`.

Los videos quedan en `Mi unidad/Fabrica de Videos/AAAA-MM-DD/categoria/`, cada uno con:
- `.mp4`: el video con tu logo
- `.txt`: título, descripción, hashtags, fuentes para verificar, créditos de fotos y guion
- `.jpg`: miniatura

## 4. Modo PC (cuando tu computadora esté prendida)

1. Instala Python 3.11 o más nuevo.
2. Copia `.env.example` como `.env` y pon tus claves.
3. Doble clic en **`iniciar-fabrica.bat`** (Windows) o ejecuta `./iniciar-fabrica.sh`.
   Hace una ronda al abrirlo y luego otra cada 4 horas. Cierra la ventana para parar.

Comandos útiles:

```bash
python -m fabrica --estilos
python -m fabrica --solo-tendencias
python -m fabrica --cantidad 3 --estilo explicativo --salidas descargar,drive
python -m fabrica --tema "Final de la Champions" --estilo comic --categoria deportes
python -m fabrica --clonar-voz si
```

Los videos quedan en la carpeta `salida/`.

## 5. Voz

**Por defecto: voz de hombre**, español latino neutro (Edge, voz mexicana estándar, la más neutra
para Latinoamérica). Para voz de mujer: `genero = "mujer"` en `fabrica.toml`, `--voz mujer`, o la
opción **Voz** al usar *Run workflow*.

### Perilla "usar mi voz" (StudioVoz)

Usa el **mismo modelo que entrenaste en tu cuaderno StudioVoz** de Colab (botón 2). No hay que
mover nada: la fábrica lo toma de `Mi unidad › StudioVoz › modelos › <modelo> › respaldo`.

1. Entrena tu modelo en StudioVoz (necesita la GPU de Colab).
2. En `fabrica.toml`, pon `modelo = "mi_voz"` (el `NOMBRE_MODELO` que usaste).
3. Actívala con `clonar = true`, `--clonar-voz si` o la casilla **Usar mi voz** en *Run workflow*.

La fábrica genera la voz con Edge y la convierte a tu voz con el mismo motor (Applio), **sin
tarjeta gráfica**. La primera vez instala el motor (~10 minutos); después queda guardado. Si
algo falla, el video sale con la voz de Edge para no perderlo. Los subtítulos se sacan del audio
final con Whisper.

Si la voz sale muy aguda o muy grave, ajusta `tono` (igual que en el botón 3 de StudioVoz).

### Voz "yo" (una IA lee imitando tu forma de hablar)

1. Sube tus audios **hablando** (no cantando) a `Mi unidad › Fabrica de Videos › mi voz`.
   Puedes ir subiendo más con el tiempo: se van juntando. Si un archivo se llama `muestra`
   (ej. `muestra.mp3`), se usa ese de ejemplo; si no, se toma un pedazo del audio más largo.
2. En **Run workflow**, elige **Voz: `yo`**.
3. La IA lectora (Chatterbox, código abierto, licencia MIT) escucha tu muestra y lee el guion
   imitando tu tono, ritmo y acento. Si tienes tu modelo (secreto `MI_VOS`), lo pule con tu timbre.

Si algo falla, el video sale con Jorge. La primera vez instala la IA lectora (~10-15 minutos) y
sin tarjeta gráfica cada video tarda varios minutos más.

## 6. Logo

Sube tu PNG con fondo transparente como `marca/logo.png` (en GitHub: entra a la carpeta `marca` →
**Add file → Upload files**). Si quieres usar otro logo, sube el nuevo con el mismo nombre.

En `fabrica.toml`, sección `[logo]`, eliges la posición:
`arriba_izquierda` (por defecto), `arriba_centro`, `arriba_derecha`, `centro_izquierda`,
`abajo_izquierda`, o `personalizada` con `x` / `y` en porcentaje. También se ajustan el tamaño y
la transparencia.

**Para ver cómo queda sin hacer un video:** *Run workflow* escribiendo `probar logo` en **Tema**,
o `python -m fabrica --probar-logo` en tu PC. La imagen muestra tu logo, los
subtítulos y en rojo las zonas que tapan los botones de TikTok/Reels/Shorts.

## 7. Videos a pedido (link o texto)

En **Run workflow**, el campo **Tema** acepta tres cosas:

- **Un tema:** `Final de la Champions`
- **Un pedido libre:** `quiero un video que explique por qué subió el dólar, tono serio`
- **Un link:** de YouTube, TikTok, Instagram, X o una noticia, y opcionalmente lo que quieres:
  `https://www.youtube.com/watch?v=... hazlo divertido y corto`

La fábrica lee el link (título, descripción y lo que se dice en el video, o el texto de la noticia),
busca más noticias del tema y escribe **su propio guion** con tus estilos. No reutiliza el video
original: así evitas reclamos de derechos de autor. En la ficha `.txt` queda el link como fuente.

## 7b. Detalles obligatorios

En **Run workflow**, la casilla **Detalles** es para lo que SÍ tiene que salir o decirse, tal cual:
`decir el top 10 en orden`, `precio $199, envío gratis`, `el partido es el sábado 8pm`.
La fábrica lo pone como obligatorio en el guion.

## 8. Logo, duración y voz desde Run workflow

- **Logo:** sube tu PNG a tu Google Drive en `Fabrica de Videos › marca` y la fábrica lo usa
  sola (el más reciente). O pega en el campo **Logo** un link de Drive compartido, o un texto
  como `@MiCanal`. La posición se elige en **Posición del logo**.
- **Duración:** 1, 1:30, 2, 2:30 o 3 minutos. Para las rondas automáticas: variable `DURACION`.
- **Voz:** hombre, mujer o **mi voz**. Con "mi voz" puedes pegar el link de tu modelo
  (.pth/.index o .zip de Drive o Hugging Face) o el nombre del modelo en StudioVoz.

Para que las rondas automáticas usen siempre lo mismo, crea **variables** (Settings → Secrets and
variables → Actions → Variables): `TEXTO_MARCA` o `LOGO_LINK`, `LOGO_POSICION`, `DURACION`,
`VOZ` (hombre/mujer/mi voz), `MODELO_VOZ_LINK`, `PUBLICAR` (mejor, manual, si).

## 8b. Texto como logo

Si no tienes logo, escribe tu marca (ej. `@MiCanal`) en **Texto como logo** al usar Run workflow.
Para que salga siempre, también en las rondas automáticas: **Settings → Secrets and variables →
Actions → pestaña Variables → New repository variable**, con nombre `TEXTO_MARCA` y tu texto.
Si subes `marca/logo.png`, se usa el logo en lugar del texto.

## 9. Tus propias fotos (negocios, productos, lugares)

En tu Drive: `Mi unidad › Fabrica de Videos › mis fotos › <categoría>` (ej. `muebles`,
`promociones`, `local`). Sube ahí todas las fotos que quieras, con o sin nombre.

Luego pide en **Tema** algo como:
`video de mi mueblería Resale Shop: cojines baratos, 30% off en muchos artículos, estamos en (dirección)`

La fábrica:
1. Ve que existe la carpeta `muebles` y baja esas fotos.
2. Gemini describe cada foto (solo la primera vez; guarda `descripciones.json` en esa carpeta).
3. El guion usa tus fotos en las escenas donde encajan (retocadas: contraste, color y nitidez).
4. Lo que no esté en tus fotos lo genera con IA.
5. Al final pone una tarjeta con el nombre, la oferta y la dirección, tal como los escribiste.

Se pueden usar carpetas dentro de carpetas (ej. `Comida › Comida salvadoreña`).

**Para que use tus fotos primero**, escribe en el pedido `drive`, `fotos en drive` o `mis fotos` y
el nombre de la carpeta, por ejemplo: `platos típicos de El Salvador (fotos en drive: comida)`.
Así pone tus fotos en las escenas y solo genera con IA las que falten.

En la PC también funciona con una carpeta `mis fotos/<categoría>` dentro del proyecto.

## 10. Tu avatar (Kaggle, automático)

Usa tus videos reales de la carpeta **EL HYAKO 1** y mueve tu boca con la narración del video
(LatentSync). Corre en **Kaggle** con su GPU gratis, sin que estés presente.

1. Cuenta gratis en https://www.kaggle.com con el **teléfono verificado** (para usar GPU).
2. Kaggle → tu foto → **Settings → API → Create New Token**: baja un `kaggle.json` con tu
   usuario y tu clave. Guárdalos como secretos `KAGGLE_USERNAME` y `KAGGLE_KEY`.
3. En **Run workflow**, casilla **Avatar**: `intro y cierre`, `esquina`, `dividida` o `mixto`.
   Para los automáticos: variable `AVATAR`.

Cada avatar queda guardado en `Fabrica de Videos › MIS AVATARES › <categoría>`.
Intro y cierre gasta poca GPU (~5 min); los demás modos mueven tu boca todo el video (~15-25 min).
Si algo falla, el video sale sin avatar y la ficha dice por qué.

## 11. Mezcla de temas de los videos automáticos

| Tipo | % |
|---|---|
| Tendencias del momento (el sistema de siempre) | 20 |
| Deportes (Liga MX, fútbol salvadoreño, LaLiga, MLS, Premier, selecciones, Messi, CR7, béisbol) | 17 |
| Tendencias y noticias no latinas | 9 |
| Entretenimiento latino (novelas, series, moda, maquillaje, temas de mujeres y hombres) | 18 |
| Curiosidades, consejos, motivación, ideas de negocio, tops | 18 |
| Cripto y bolsa | 10 |
| Música (latina/urbana, top 5, El Hyako Mayor, Hyakiaera Records, estudio, VST, Suno) | 8 |

Cada ronda toma la categoría que más falta según los últimos 40 videos. Se cambia en `[mezcla]`.
Además, no se repite un tema parecido a otro de los últimos 4 días.

## 12. Más vida en los videos

- **Mapas animados:** en noticias de un lugar, zoom desde lejos hasta el sitio exacto con marcador.
- **Efectos de sonido:** "whoosh" suave en cada cambio de escena (`[efectos]`).
- **Música según el tono:** pon tus canciones en `Fabrica de Videos › musica › epica / tension / alegre /
  triste / motivacion / neutral` (o una carpeta por categoría, ej. `deportes`). Si no hay, la de siempre.
- **Miniaturas llamativas:** texto grande con borde, tu cara si hay avatar y tu marca.
- **Clips de video reales** (Pixabay/Pexels) en realista, noticiero y cinematográfico.
- **Escenas animadas con IA** (LTX-Video en Kaggle): variable `ANIMAR` = `si`. Tarda 10-25 min más
  por video y gasta minutos de GitHub mientras espera; por eso viene apagado.

## 13. Lo que funciona en tu canal (estadísticas de YouTube)

1. Google Cloud Console → crea un proyecto → **APIs y servicios → Biblioteca → YouTube Data API v3 →
   Habilitar** → **Credenciales → Crear credenciales → Clave de API**.
2. Guárdala como secreto `YOUTUBE_API_KEY` y crea la variable `YOUTUBE_CANAL` con tu `@usuario`.

Una vez al día la fábrica lee las vistas de tus videos, sube un poco las categorías que más funcionan
(hasta 1.4 veces) y baja las demás (hasta 0.7 veces, nunca desaparecen). Además le pasa a la IA tus
videos más vistos como ejemplo.

## 14. Publicar automáticamente (TikTok, YouTube Shorts, Instagram)

1. Crea una cuenta en https://upload-post.com y conecta ahí tus redes.
2. Guarda los secretos `UPLOAD_POST_API_KEY` y `UPLOAD_POST_USERNAME`.
3. Crea la variable `PUBLICAR` con uno de estos valores:

| Valor | Qué publica |
|---|---|
| `mejor` | **1 al día**: el automático con mejor nota de las últimas 24 horas (se publica en la ronda de las 10pm) |
| `mejor,manual` | lo mismo, y además los que pides con Run workflow |
| `manual` | solo los que pides con Run workflow |
| `si` | todos |
| *(sin variable)* | ninguno |

**Cómo se elige el mejor:** cada video automático recibe una nota de 0 a 100. Hasta 60 puntos
los pone la IA (fuerza del gancho, interés del tema hoy para latinos, ganas de comentar) y hasta
40 la calidad (imágenes que encajaron, voz bien pulida, avatar). La nota sale en la ficha `.txt`
("NOTA PARA 'MEJOR DEL DÍA'") y en el registro de la ronda de las 10pm verás las notas de todos.

Por defecto publica en **YouTube, Facebook, X y Threads** (las redes conectadas en Upload-Post). Para cambiarlas,
crea la variable `PLATAFORMAS` (ej. `youtube,x,threads,facebook`). En X el texto va corto (280 letras).
Si una red falla, las demás se publican igual y el registro dice el motivo.

Los videos siguen llegando a Drive igual. Recomendación: activa la etiqueta de **contenido
alterado o sintético** en YouTube y la de **contenido generado con IA** en TikTok cuando el video
tenga voz clonada, avatar o imágenes realistas: lo piden las plataformas y no baja el alcance.

## 15. Estilo Geografía (mapas animados)

Como los canales de geografía: el video entero pasa sobre un **mapa satelital** (NASA Blue Marble).
La cámara vuela de un lugar a otro, los países y regiones se pintan de colores, las fronteras se
dibujan con una línea brillante y su dato ("3,169 km"), aparecen rutas (viajes, conquistas,
migraciones), mares y ríos con su nombre, iconos en cada región (🏭 🌽 🛢️ 🏖️) y preguntas
grandes inclinadas ("¿NORTEAMÉRICA?"). El mapa se va armando escena tras escena.

- **Cómo usarlo:** Run workflow → Estilo **geografia** → en Tema escribe, por ejemplo,
  "Cómo se divide México", "Por qué Chile es tan largo", "La frontera más rara de Centroamérica".
- En **automático** también puede salir: la categoría curiosidades incluye geografía e historia.
- Los **otros estilos** que necesitan un mapa (una noticia en un lugar) ahora usan este mapa
  satelital; si no carga, queda el mapa de calles de antes.
- **Mapa antiguo** (papel viejo, sepia) en las escenas de historia, y **banderas** que aparecen sobre
  los países (banderas de dominio público de flagcdn.com).
- **Pegatinas propias** (personajes y objetos tipo juguete 3D: barco, avión, castillo, volcán y
  nuestro **guía**): se crean con IA la primera vez, se les quita el fondo y se guardan en
  `Fabrica de Videos/pegatinas` en tu Drive. Puedes poner ahí tus propios PNG con fondo
  transparente (el nombre del archivo es el nombre de la pegatina; `guia.png` cambia el guía).
  El avión o el barco viaja por las rutas.
- **Música libre incluida** (Kevin MacLeod, CC BY 4.0): si tu carpeta `musica` de Drive no tiene
  nada para el tono, los videos de geografía usan «Hiding Your Reality» (curioso) o «Dark Fog»
  (misterio). El **crédito obligatorio** se agrega solo al publicar y sale en la ficha `.txt`;
  si publicas a mano, cópialo en la descripción.
- Letras libres (OFL): Montserrat en mapas y subtítulos, EB Garamond en el mapa antiguo.
- Satélite con detalle de ciudad: Sentinel-2 cloudless 2016 de EOX (CC BY 4.0, el crédito sale en el video).
- Datos: Natural Earth y NASA (libres). Si la NASA no responde, se dibuja el mapa con contornos.

**Ganchos en todos los videos:** el guion empieza con una pregunta o un dato que sorprende, mete
algo cada 2-3 frases para que no se vayan (preguntas al público, "pero aquí viene lo bueno") y
cierra con una pregunta para comentar. En los momentos clave sale un **texto grande en pantalla**
("¿POR QUÉ?", "3,169 KM").

## Recomendaciones

- **Revisa cada video antes de publicarlo.** La IA se puede equivocar con cifras o nombres, y
  la ficha `.txt` trae las fuentes.
- **Marca el contenido como hecho con IA** cuando la plataforma lo pida (avatar o voz realista).
  YouTube y TikTok lo exigen, y no marcarlo puede costarte la monetización.
- **Varía los estilos y las voces** para que el canal no se vea repetitivo.

## Próximas fases

- Estilo explicativo animado con objetos en movimiento (Remotion)
- Avatares opcionales generados en Kaggle/Colab (GPU gratis), solo en algunos videos
- Pestaña de la fábrica dentro de la WebUI
