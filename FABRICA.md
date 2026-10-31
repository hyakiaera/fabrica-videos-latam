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
| `realista` | Videos de stock (el original de MoneyPrinterTurbo) | General |
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

## 6. Logo

Sube tu PNG con fondo transparente como `marca/logo.png` (en GitHub: entra a la carpeta `marca` →
**Add file → Upload files**). Si quieres usar otro logo, sube el nuevo con el mismo nombre.

En `fabrica.toml`, sección `[logo]`, eliges la posición:
`arriba_izquierda` (por defecto), `arriba_centro`, `arriba_derecha`, `centro_izquierda`,
`abajo_izquierda`, o `personalizada` con `x` / `y` en porcentaje. También se ajustan el tamaño y
la transparencia.

**Para ver cómo queda sin hacer un video:** *Run workflow* con la casilla **Solo crear imagen de
prueba del logo**, o `python -m fabrica --probar-logo` en tu PC. La imagen muestra tu logo, los
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

## 8. Logo, duración y voz desde Run workflow

- **Logo:** sube tu PNG a tu Google Drive en `Fabrica de Videos › marca` y la fábrica lo usa
  sola (el más reciente). O pega en el campo **Logo** un link de Drive compartido, o un texto
  como `@MiCanal`. La posición se elige en **Posición del logo**.
- **Duración:** 1, 1:30, 2, 2:30 o 3 minutos. Para las rondas automáticas: variable `DURACION`.
- **Voz:** hombre, mujer o **mi voz**. Con "mi voz" puedes pegar el link de tu modelo
  (.pth/.index o .zip de Drive o Hugging Face) o el nombre del modelo en StudioVoz.

Para que las rondas automáticas usen siempre lo mismo, crea **variables** (Settings → Secrets and
variables → Actions → Variables): `TEXTO_MARCA` o `LOGO_LINK`, `LOGO_POSICION`, `DURACION`,
`VOZ` (hombre/mujer/mi voz), `MODELO_VOZ_LINK`, `PUBLICAR` (si).

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

En la PC también funciona con una carpeta `mis fotos/<categoría>` dentro del proyecto.

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
