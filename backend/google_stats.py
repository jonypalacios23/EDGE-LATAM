from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


GOOGLE_URL = "https://www.google.com/search"
DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
TIMEOUT_SECONDS = 12
MARKET_NAMES = {
    "corners": "cuantos corners hubo",
    "corner": "cuantos corners hubo",
    "tarjetas": "cuantas tarjetas hubo",
    "cards": "cuantas tarjetas hubo",
    "goles": "cuantos goles hubo",
    "goals": "cuantos goles hubo",
}


def construir_consulta(partido: Dict[str, object], mercado: Dict[str, object]) -> Optional[str]:
    tipo = str(mercado.get("tipo", "")).strip().casefold()
    if tipo not in MARKET_NAMES:
        return None
    prefix = MARKET_NAMES[tipo]
    fecha = str(partido.get("fecha", "")).strip()
    local = str(partido.get("local", "")).strip()
    visitante = str(partido.get("visitante", "")).strip()
    if not local or not visitante:
        return None
    consulta = "{} en {} vs {}".format(prefix, local, visitante)
    if fecha:
        consulta += " {}".format(fecha)
    return consulta


class _DuckDuckGoParser(HTMLParser):
    """Lee el primer resultado orgánico y su snippet de DuckDuckGo HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._current: Optional[Dict[str, str]] = None
        self._capture: Optional[str] = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attributes = dict(attrs)
        classes = str(attributes.get("class", "")).split()
        if tag == "div" and "result" in classes and self._current is None:
            self._current = {"title": "", "text": "", "url": ""}
            self._depth = 1
        elif self._current is not None and tag == "div":
            self._depth += 1
        if self._current is None:
            return
        if tag == "a" and "result__a" in classes:
            self._capture = "title"
            self._current["url"] = str(attributes.get("href", ""))
        elif tag in {"a", "div"} and "result__snippet" in classes:
            self._capture = "text"

    def handle_data(self, data: str) -> None:
        if self._current is not None and self._capture:
            self._current[self._capture] += data

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return
        if tag in {"a", "div"}:
            self._capture = None
        if tag == "div":
            self._depth -= 1
            if self._depth <= 0:
                if self._current.get("url"):
                    self.results.append(self._current)
                self._current = None


def _plain(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _menciona_partido(text: str, partido: Dict[str, object]) -> bool:
    normal = _plain(text)
    equipos = [str(partido.get("local", "")), str(partido.get("visitante", ""))]
    for equipo in equipos:
        tokens = [token for token in re.findall(r"[a-z0-9]+", _plain(equipo)) if token not in {"deportes", "club", "fc", "cd", "valledupar"}]
        if not tokens or not any(re.search(r"\b{}\b".format(re.escape(token)), normal) for token in tokens):
            return False
    return True


def _total_tarjetas(text: str) -> Optional[int]:
    normalized = _plain(text)
    # A total explicitly stated as cards takes precedence over component counts.
    explicit = re.search(r"(?:total(?:\s+de)?\s+)(\d+)\s+(?:tarjetas|cards)\b", normalized)
    if explicit:
        return int(explicit.group(1))
    # Generic "5 tarjetas" is a total when it is not a team-by-team breakdown.
    counts = re.findall(r"\b(\d+)\s+(?:tarjetas|cards)\b", normalized)
    if counts and len(counts) == 1:
        return int(counts[0])
    # Some result snippets give total yellows and reds separately.
    yellow = re.search(r"(\d+)\s+(?:tarjetas\s+)?(?:amarillas|amarilla|yellow cards?)\b", normalized)
    red = re.search(r"(\d+)\s+(?:tarjetas\s+)?(?:rojas|roja|red cards?)\b", normalized)
    if yellow and red:
        return int(yellow.group(1)) + int(red.group(1))
    # Match team-by-team counts only when both team names are present in the result.
    team_counts = re.findall(r"\b(\d+)\s+(?:tarjetas\s+)?(?:amarillas|amarilla|tarjetas|cards)\b", normalized)
    if len(team_counts) >= 2:
        return sum(int(value) for value in team_counts[:2])
    return None


def _total_corners(text: str, partido: Dict[str, object]) -> Optional[int]:
    normalized = _plain(text)
    if re.search(r"corners?|corner kicks?", normalized):
        context = " ".join(
            fragment for fragment in re.findall(r"[^.!?]*?(?:corners?|corner kicks?)[^.!?]*", normalized)
        )
        team_counts = []
        for team in (str(partido.get("local", "")), str(partido.get("visitante", ""))):
            tokens = [token for token in re.findall(r"[a-z0-9]+", _plain(team)) if token not in {"deportes", "club", "fc", "cd", "valledupar"}]
            found = None
            for token in tokens:
                escaped = re.escape(token)
                patterns = (
                    r"\b{}\b\s*(?::|-|had|won|tuvo|obtuvo)?\s*(\d+)\s*(?:corners?|corner kicks?)\b".format(escaped),
                    r"\b(\d+)\s*(?:corners?|corner kicks?)?\s*(?:para|for)\s+(?:deportes\s+)?\b{}\b".format(escaped),
                )
                for pattern in patterns:
                    match = re.search(pattern, context)
                    if match:
                        found = int(match.group(1))
                        break
                if found is not None:
                    break
            if found is not None:
                team_counts.append(found)
        if len(team_counts) == 2:
            return sum(team_counts)
    match = re.search(r"(?:total(?:\s+de)?\s+)?(\d+)\s+(?:corners?|corners kicks?|corner kicks?|corners? totales?|corners?)\b", normalized)
    if match:
        return int(match.group(1))
    match = re.search(r"(?:corners?|corners? totales?)\s*[:=]\s*(\d+)\b", normalized)
    return int(match.group(1)) if match else None


def _total_goles(text: str) -> Optional[int]:
    normalized = _plain(text)
    match = re.search(r"(?:total(?:\s+de)?\s+)?(\d+)\s+goles?\b", normalized)
    if match:
        return int(match.group(1))
    # Score parsing is allowed only for the goals market.
    score = re.search(r"\b(?:final\s*)?(\d+)\s*[-:]\s*(\d+)\b", normalized)
    return sum(map(int, score.groups())) if score else None


def extraer_total(texto_resultado: str, tipo: str, partido: Dict[str, object]) -> Optional[int]:
    """Extract a stated total from one result, only if it names both teams."""
    if not _menciona_partido(texto_resultado, partido):
        return None
    tipo = tipo.strip().casefold()
    if tipo in {"corners", "corner"}:
        return _total_corners(texto_resultado, partido)
    if tipo in {"tarjetas", "cards"}:
        return _total_tarjetas(texto_resultado)
    if tipo in {"goles", "goals"}:
        return _total_goles(texto_resultado)
    return None


class _GoogleParser(_DuckDuckGoParser):
    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attributes = dict(attrs)
        classes = str(attributes.get("class", "")).split()
        if tag == "div" and "MjjYud" in classes and self._current is None:
            self._current = {"title": "", "text": "", "url": ""}
            self._depth = 1
        elif self._current is not None and tag == "div":
            self._depth += 1
        if self._current is None:
            return
        href = str(attributes.get("href", ""))
        if tag == "a" and href:
            parsed = urlparse(href)
            if parsed.path == "/url":
                href = parse_qs(parsed.query).get("q", [href])[0]
            if href.startswith("http"):
                self._current["url"] = href
                self._capture = "title"

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text"] += data
            if self._capture == "title":
                self._current["title"] += data


def _consultar_html(url_base: str, consulta: str, parser: HTMLParser) -> List[Dict[str, str]]:
    url = url_base + "?" + urlencode({"q": consulta, "num": "10"})
    request = Request(
        url,
        headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0 (compatible; EDGE-LATAM/1.0)"},
    )
    with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        html = response.read().decode("utf-8", errors="replace")
    parser.feed(html)
    return getattr(parser, "results", [])


def _consultar_busqueda(consulta: str) -> List[Dict[str, str]]:
    try:
        resultados = _consultar_html(GOOGLE_URL, consulta, _GoogleParser())
        if resultados:
            for resultado in resultados:
                resultado["engine"] = "Google"
            return resultados
    except Exception as error:
        print("Google no respondió para {!r}: {}. Se prueba DuckDuckGo.".format(consulta, error))
    resultados = _consultar_html(DUCKDUCKGO_URL, consulta, _DuckDuckGoParser())
    for resultado in resultados:
        resultado["engine"] = "DuckDuckGo"
    return resultados


def buscar_estadistica_google(
    partido: Dict[str, object],
    mercado: Dict[str, object],
    searcher=None,
) -> Optional[Dict[str, object]]:
    """Search one market; return a sourced value only from the first web result."""
    consulta = construir_consulta(partido, mercado)
    if not consulta:
        return None
    try:
        resultados = (searcher or _consultar_busqueda)(consulta)
    except Exception as error:
        print("Error búsqueda Google/DuckDuckGo query={!r}: {}".format(consulta, error))
        return None
    if not resultados:
        print("Búsqueda sin resultados query={!r}".format(consulta))
        return None
    primero = resultados[0]
    texto = "{} {}".format(primero.get("title", ""), primero.get("text", "")).strip()
    tipo = str(mercado.get("tipo", ""))
    total = extraer_total(texto, tipo, partido)
    if total is None:
        print("Primer resultado sin total verificable query={!r}: {!r}".format(consulta, texto[:300]))
        return None
    source_url = str(primero.get("url", ""))
    source_name = urlparse(source_url).netloc.removeprefix("www.") or str(primero.get("engine", "Google"))
    engine = str(primero.get("engine", "Google"))
    return {
        "total": total,
        "fuente": engine,
        "fuente_url": source_url,
        "fuente_nombre": source_name,
        "consulta": consulta,
        "texto_resultado": texto,
    }
