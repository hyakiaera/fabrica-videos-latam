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
