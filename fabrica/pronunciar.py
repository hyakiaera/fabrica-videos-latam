"""Nombres en inglés (y otros idiomas) escritos como se dicen, SOLO para la voz.
Las voces en español leen "Manchester United" letra por letra ("unite"); aquí se cambia a
"Mánchester Iunáited" antes de leerlo. Los subtítulos siguen mostrando el nombre bien escrito.

Además del diccionario de abajo, el guionista agrega en cada video los nombres extranjeros
que use (campo "pronunciacion" del guion)."""
import re

DICCIONARIO = {
    # fútbol y deportes
    "Manchester United": "Mánchester Iunáited", "Manchester City": "Mánchester Síti",
    "Liverpool": "Líverpul", "Chelsea": "Chélsi", "Tottenham": "Tótenam", "Newcastle": "Niúcasel",
    "Aston Villa": "Áston Vila", "West Ham": "Uest Jam", "Premier League": "Prémier Lig",
    "Champions League": "Chámpions Lig", "Europa League": "Europa Lig", "Bayern": "Báyern",
    "Inter Miami": "Inter Mayámi", "New York": "Niu York", "Nueva York": "Nueva York",
    "Los Angeles Galaxy": "Los Ányeles Gálaxi", "Super Bowl": "Súper Bol", "NBA": "ene be a",
    "NFL": "ene efe ele", "MLS": "eme ele ese", "MLB": "eme ele be", "UFC": "u efe ce",
    "Grand Prix": "Gran Pri", "Red Bull": "Red Bul", "McLaren": "Maclaren", "Lakers": "Léikers",
    "Warriors": "Uórriors", "Yankees": "Yánkis", "Dodgers": "Dóyers", "LeBron James": "Lebrón Yeims",
    "Stephen Curry": "Stífen Cérri", "Shohei Ohtani": "Shojei Otani",
    # marcas y tecnología
    "YouTube": "Iutiub", "Facebook": "Feisbuk", "iPhone": "Áifon", "Apple": "Ápol", "Google": "Gúgol",
    "Microsoft": "Máicrosoft", "Netflix": "Nétflix", "Spotify": "Espótifai", "WhatsApp": "Uatsap",
    "Instagram": "Ínstagram", "TikTok": "Tiktok", "OpenAI": "Open ei ai", "ChatGPT": "Chat yi pi ti",
    "Nvidia": "Envídia", "Bitcoin": "Bítcoin", "Ethereum": "Ezérium", "Binance": "Báinans",
    "Coinbase": "Cóinbeis", "Wall Street": "Uol Strit", "Nasdaq": "Násdak", "Dow Jones": "Dau Yons",
    "Black Friday": "Blak Fráidei", "Cyber Monday": "Sáiber Mándei", "Halloween": "Jálouin",
    "Amazon": "Ámazon", "Walmart": "Uólmart", "Starbucks": "Stárbacs", "McDonald's": "Macdónalds",
    "Disney": "Dísni", "PlayStation": "Pléisteishon", "Xbox": "Ecsbox", "Nintendo": "Nintendo",
    "Elon Musk": "Ílon Mosk", "Mark Zuckerberg": "Mark Súkerberg", "Donald Trump": "Dónald Tromp",
    "Joe Biden": "Yo Báiden", "Taylor Swift": "Téilor Suift", "Bad Bunny": "Bad Bóni",
    "Billboard": "Bílbord", "Grammy": "Grámi", "Hollywood": "Jólibud",
    "Wi-Fi": "uaifai", "online": "onlain", "streaming": "estríming", "podcast": "pódcast",
    "influencer": "ínfluenser", "show": "chou", "reality": "riáliti",
    # palabras en inglés o "españolizadas" que la voz leía mal
    "hackers": "jákers", "hacker": "jáker", "hackeo": "jákeo", "hackeos": "jákeos",
    "hackearon": "jakearon", "hackear": "jakear", "hackeado": "jakeado", "hackeada": "jakeada",
    "crypto": "cripto", "blockchain": "blokchéin", "wallet": "uólet", "exchange": "exchéinch",
    "trading": "tréiding", "trader": "tréider", "marketing": "márketing", "startup": "estártap",
    "software": "sóftuer", "smartphone": "esmártfon", "gamer": "guéimer", "gaming": "guéiming",
    "fans": "fans", "playoffs": "pléiofs", "playoff": "pléiof", "MVP": "eme ve pe", "VAR": "var",
    "Lionel Messi": "Lionél Mési", "Lionel": "Lionél", "Messi": "Mési", "Mbappé": "Embapé",
    "Haaland": "Jáland", "Vinicius": "Vinísius", "Bellingham": "Bélinjam", "Kane": "Kéin",
    "Lamine Yamal": "Lamín Yamal", "Cristiano Ronaldo": "Cristiano Ronaldo",
    "Rauw Alejandro": "Rau Alejandro", "Anuel AA": "Anuel doble a", "Karol G": "Károl yi",
    "J Balvin": "Yei Balvin", "Peso Pluma": "Peso Pluma", "Feid": "Féid",
}


def _aplicar(texto: str, cambios: dict[str, str]) -> str:
    # Primero los nombres largos ("Manchester United" antes que "United").
    for original in sorted(cambios, key=len, reverse=True):
        dicho = cambios[original]
        if not original or not dicho or original == dicho:
            continue
        texto = re.sub(rf"(?<![\w]){re.escape(original)}(?![\w])", dicho, texto, flags=re.I)
    return texto


def para_voz(texto: str, extra: dict | None = None) -> str:
    """El texto que se lee en voz alta, con los nombres extranjeros escritos como suenan."""
    cambios = dict(DICCIONARIO)
    if isinstance(extra, dict):
        cambios.update({str(k): str(v) for k, v in extra.items() if k and v})
    return _aplicar(texto, cambios)


def revisar(cfg: dict, guion: str, conocidas: dict | None = None) -> dict:
    """Revisión extra con IA: cada palabra en inglés u otro idioma, marca, nombre extranjero,
    sigla o palabra "españolizada" del guion, escrita como suena en su idioma original pero con
    letras del español (para que la voz en español la diga bien). Devuelve el diccionario."""
    from fabrica import ia
    cambios = dict(conocidas or {})
    sistema = ("Eres fonetista. Escribes cómo se pronuncian palabras extranjeras usando letras del "
               "español latino, para que una voz que solo lee español las diga como en su idioma. "
               "Respondes SOLO JSON.")
    usuario = (f"Guion:\n{guion}\n\nEncuentra TODAS las palabras o nombres que una voz en español leería "
               "mal: palabras en inglés (hackers, streaming, wallet), marcas (Binance, Coinbase, Spotify), "
               "nombres de personas, equipos o lugares extranjeros (Lionel Messi, Manchester United, "
               "Haaland), siglas que se deletrean (NBA, ETF) y palabras inglesas españolizadas "
               "(hackeo, hackear). Para cada una di cómo se pronuncia, escrita con letras del español "
               "y con tilde en la sílaba fuerte (ej. 'hackers' → 'jákers', 'Binance' → 'Báinans', "
               "'Lionel Messi' → 'Lionél Mési', 'NBA' → 'ene be a', 'hackeo' → 'jákeo').\n"
               'Responde: {"pronunciacion": {"palabra tal como está en el guion": "cómo se dice"}}. '
               "No incluyas palabras normales del español.")
    try:
        r = ia.pedir_json(cfg, sistema, usuario, temperatura=0)
        nuevas = r.get("pronunciacion") if isinstance(r, dict) else None
        if isinstance(nuevas, dict):
            for k, v in nuevas.items():
                k, v = str(k).strip(), str(v).strip()
                # Solo cambios razonables: misma cantidad aproximada de palabras y que aparezca en el guion.
                if k and v and k.lower() != v.lower() and k.lower() in guion.lower() \
                        and abs(len(v.split()) - len(k.split())) <= 3:
                    cambios.setdefault(k, v)
    except Exception:
        pass
    return cambios
