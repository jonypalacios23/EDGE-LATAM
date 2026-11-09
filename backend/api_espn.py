from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from html.parser import HTMLParser
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


API_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
COLOMBIA_TIMEZONE = "America/Bogota"
REQUEST_TIMEOUT_SECONDS = 10
LIGAS = {
    "col.1": "Colombia Primera A",
    "col.2": "Colombia Primera B",
    "conmebol.libertadores": "CONMEBOL Libertadores",
    "conmebol.sudamericana": "CONMEBOL Sudamericana",
    "eng.1": "Premier League",
    "esp.1": "LaLiga",
    "ita.1": "Serie A",
    "ger.1": "Bundesliga",
    "fra.1": "Ligue 1",
}


def _get_json(url: str) -> Dict[str, object]:
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "EDGE-LATAM/1.0"})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError("ESPN status {} body: {}".format(error.code, body)) from error
    except URLError as error:
        raise RuntimeError("ESPN request failed: {}".format(error)) from error
    if not body:
        return {"events": []}
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise RuntimeError("ESPN status {} body: {}".format(status_code, body)) from error
    if payload.get("error"):
        raise RuntimeError("ESPN status {} body: {}".format(status_code, body))
    return payload


def _normalizar_nombre(nombre: str) -> List[str]:
    texto = unicodedata.normalize("NFKD", nombre.casefold())
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", texto)
        if token not in {"fc", "cd", "club", "deportes"}
    ]
    if tokens and tokens[0] == "alianza":
        return ["alianza"]
    return tokens


def _nombres_coinciden(nombre_manual: str, nombre_espn: str) -> bool:
    manual = _normalizar_nombre(nombre_manual)
    espn = _normalizar_nombre(nombre_espn)
    return bool(manual and espn and manual == espn)


def _as_score(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _hora_inicio(fecha: object) -> Optional[str]:
    if not fecha:
        return None
    try:
        momento = datetime.fromisoformat(str(fecha).replace("Z", "+00:00"))
        return momento.astimezone(ZoneInfo(COLOMBIA_TIMEZONE)).strftime("%H:%M")
    except (TypeError, ValueError):
        return None


def _evento_a_resultado(evento: Dict[str, object], codigo_liga: str) -> Optional[Dict[str, object]]:
    competitions = evento.get("competitions", [])
    if not competitions or not isinstance(competitions[0], dict):
        return None
    competition = competitions[0]
    competitors = competition.get("competitors", [])
    if not isinstance(competitors, list):
        return None
    home = next((item for item in competitors if item.get("homeAway") == "home"), None)
    away = next((item for item in competitors if item.get("homeAway") == "away"), None)
    if home is None or away is None:
        return None

    home_team = home.get("team", {})
    away_team = away.get("team", {})
    status = evento.get("status", {})
    status_type = status.get("type", {})
    description = str(status_type.get("description", ""))
    detail = str(status_type.get("shortDetail", status_type.get("detail", "")))
    clock = str(status.get("displayClock", ""))
    state = str(status_type.get("state", "")).lower()
    status_terms = "{} {} {} {}".format(
        description,
        detail,
        status_type.get("name", ""),
        state,
    ).casefold()
    canceled = any(term in status_terms for term in ("cancel", "abandon", "postpon"))
    suspended = "suspend" in status_terms
    completed = bool(status_type.get("completed")) or state == "post"
    halftime = "half time" in status_terms or "halftime" in status_terms or detail.strip().upper() == "HT"

    minute = None
    minute_match = re.search(r"(\d+)", detail or clock)
    if minute_match:
        minute = int(minute_match.group(1))
    if canceled:
        match_state = "cancelado"
        display_state = "Cancelado"
    elif suspended:
        match_state = "suspendido"
        display_state = "Suspendido"
    elif completed:
        match_state = "finalizado"
        display_state = "Finalizado"
    elif halftime:
        match_state = "en_juego"
        display_state = "Descanso"
    elif state == "in":
        match_state = "en_juego"
        display_state = "EN VIVO{}".format(" {}'".format(minute) if minute is not None else "")
    else:
        match_state = "pendiente"
        display_state = "Programado"

    league_data = evento.get("league", {})
    league_name = str(league_data.get("name", "")) or LIGAS.get(codigo_liga, codigo_liga)
    return {
        "evento_id": evento.get("id"),
        "liga_codigo": codigo_liga,
        "liga": league_name,
        "local": str(home_team.get("displayName", home_team.get("name", ""))),
        "visitante": str(away_team.get("displayName", away_team.get("name", ""))),
        "estado": match_state,
        "estado_texto": display_state,
        "minuto": minute,
        "hora_inicio": _hora_inicio(evento.get("date")),
        "marcador_local": _as_score(home.get("score")),
        "marcador_visitante": _as_score(away.get("score")),
        "goles_total": (
            (_as_score(home.get("score")) or 0) + (_as_score(away.get("score")) or 0)
            if _as_score(home.get("score")) is not None and _as_score(away.get("score")) is not None
            else None
        ),
    }


def _fixture_names(event: Dict[str, object]) -> Optional[Tuple[str, str]]:
    result = _evento_a_resultado(event, "")
    if result is None:
        return None
    return str(result["local"]), str(result["visitante"])


STAT_ALIASES = {
    "woncorners": "corners",
    "corners": "corners",
    "cornerkicks": "corners",
    "yellowcards": "yellow_cards",
    "redcards": "red_cards",
    "shotsontarget": "shots_on_target",
    "shotsongoal": "shots_on_target",
}


def _stat_value(value: object) -> Optional[int]:
    if isinstance(value, dict):
        for key in ("displayValue", "value", "total", "statValue"):
            if key in value:
                parsed = _as_score(value[key])
                if parsed is not None:
                    return parsed
        return None
    return _as_score(value)


def _stats_from_tree(node: object) -> Dict[str, int]:
    found: Dict[str, int] = {}
    if isinstance(node, list):
        for item in node:
            found.update(_stats_from_tree(item))
        return found
    if not isinstance(node, dict):
        return found

    names = [node.get(key) for key in ("name", "label", "displayName", "abbreviation", "type")]
    for name in names:
        normalized = re.sub(r"[^a-z]", "", str(name or "").casefold())
        target = STAT_ALIASES.get(normalized)
        if target:
            value = _stat_value(node)
            if value is not None:
                found[target] = value
            break

    for key, value in node.items():
        normalized = re.sub(r"[^a-z]", "", str(key).casefold())
        target = STAT_ALIASES.get(normalized)
        if target:
            parsed = _stat_value(value)
            if parsed is not None:
                found[target] = parsed
        elif isinstance(value, (dict, list)):
            found.update(_stats_from_tree(value))
    return found


def _statistics_from_summary(payload: Dict[str, object]) -> Dict[str, Optional[int]]:
    boxscore = payload.get("boxscore", {})
    teams = boxscore.get("teams", []) if isinstance(boxscore, dict) else []
    if not isinstance(teams, list):
        teams = []
    per_team = [_stats_from_tree(team) for team in teams if isinstance(team, dict)]

    if len(per_team) < 2:
        # ESPN can place team aggregates in differently nested summary sections.
        candidates = []
        for section in (payload.get("team_stats"), payload.get("statistics"), payload.get("boxscore")):
            if isinstance(section, list):
                candidates.extend(_stats_from_tree(item) for item in section)
            elif isinstance(section, dict):
                nested = section.get("teams")
                if isinstance(nested, list):
                    candidates.extend(_stats_from_tree(item) for item in nested)
        if len(candidates) >= 2:
            per_team = candidates

    result: Dict[str, Optional[int]] = {
        "corners_total": None,
        "tarjetas_total": None,
        "tiros_a_puerta_total": None,
    }
    if len(per_team) >= 2:
        first, second = per_team[0], per_team[1]
        if "corners" in first and "corners" in second:
            result["corners_total"] = first["corners"] + second["corners"]
        card_keys = ("yellow_cards", "red_cards")
        if all(key in team for team in per_team[:2] for key in card_keys):
            result["tarjetas_total"] = sum(
                team["yellow_cards"] + team["red_cards"] for team in per_team[:2]
            )
        if "shots_on_target" in first and "shots_on_target" in second:
            result["tiros_a_puerta_total"] = first["shots_on_target"] + second["shots_on_target"]
    return result


class _GoogleResultsParser(HTMLParser):
    """Extrae texto y enlaces de resultados orgánicos de Google sin evaluar anuncios."""

    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, object]] = []
        self._active = False
        self._depth = 0
        self._text: List[str] = []
        self._links: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attributes = dict(attrs)
        if tag == "div" and "MjjYud" in str(attributes.get("class", "")).split() and not self._active:
            self._active = True
            self._depth = 1
            self._text = []
            self._links = []
        elif self._active and tag == "div":
            self._depth += 1
        if self._active and tag == "a" and attributes.get("href"):
            self._links.append(str(attributes["href"]))

    def handle_data(self, data: str) -> None:
        if self._active:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._active and tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self.results.append({"text": " ".join(self._text), "links": self._links[:]})
                self._active = False


def _buscar_totales_en_google(resultado: Dict[str, object]) -> Dict[str, int]:
    local = str(resultado.get("local", ""))
    visitante = str(resultado.get("visitante", ""))
    fecha = datetime.now(ZoneInfo(COLOMBIA_TIMEZONE)).strftime("%Y-%m-%d")
    query_text = (
        '"{}" "{}" {} (corners OR "corner kicks" OR cards OR tarjetas) '
        '(site:espn.com OR site:flashscore.com OR site:sofascore.com)'
    ).format(local, visitante, fecha)
    url = "https://www.google.com/search?" + urlencode({"q": query_text, "num": 10})
    request = Request(
        url,
        headers={"Accept": "text/html", "User-Agent": "Mozilla/5.0 (compatible; EDGE-LATAM/1.0)"},
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            html = response.read().decode("utf-8", errors="replace")
    except Exception as error:
        print("Búsqueda web ESPN fallback sin respuesta para {} vs {}: {}".format(local, visitante, error))
        return {}

    parser = _GoogleResultsParser()
    parser.feed(html)
    aliases = {"espn.com", "flashscore.com", "sofascore.com"}
    nombres = [_normalizar_nombre(local), _normalizar_nombre(visitante)]
    patrones = {
        "corners_total": re.compile(r"(?:total\s+(?:corner kicks|corners)|(?:corner kicks|corners)\s+total|c[oó]rners?\s+totales?)\s*[:\-]?\s*(\d+)", re.I),
        "tarjetas_total": re.compile(r"(?:total\s+cards|cards\s+total|total\s+tarjetas|tarjetas\s+totales?)\s*[:\-]?\s*(\d+)", re.I),
        "amarillas_total": re.compile(r"(?:total\s+yellow cards|yellow cards\s+total|total\s+tarjetas amarillas|tarjetas amarillas\s+totales?)\s*[:\-]?\s*(\d+)", re.I),
        "rojas_total": re.compile(r"(?:total\s+red cards|red cards\s+total|total\s+tarjetas rojas|tarjetas rojas\s+totales?)\s*[:\-]?\s*(\d+)", re.I),
    }
    output: Dict[str, int] = {}
    for item in parser.results:
        text = str(item.get("text", ""))
        normalized_text = _normalizar_nombre(text)
        if not all(any(token in normalized_text for token in equipo) for equipo in nombres):
            continue
        hosts = []
        for link in item.get("links", []):
            parsed = urlparse(str(link))
            if parsed.netloc.casefold().endswith("google.com") and parsed.path == "/url":
                target = parse_qs(parsed.query).get("q", [""])[0]
                parsed = urlparse(target)
            host = parsed.netloc.casefold().removeprefix("www.")
            if any(host == allowed or host.endswith("." + allowed) for allowed in aliases):
                hosts.append(host)
        if not hosts:
            continue
        for key, pattern in patrones.items():
            match = pattern.search(text)
            if match:
                output[key] = int(match.group(1))
    if output:
        if "tarjetas_total" not in output and "amarillas_total" in output and "rojas_total" in output:
            output["tarjetas_total"] = output["amarillas_total"] + output["rojas_total"]
        output.pop("amarillas_total", None)
        output.pop("rojas_total", None)
        print("Búsqueda web encontró totales oficiales para {} vs {}: {}".format(local, visitante, output))
    return output


def _cargar_estadisticas_espn(resultado: Dict[str, object]) -> None:
    evento_id = resultado.get("evento_id")
    liga = str(resultado.get("liga_codigo", ""))
    if not evento_id or liga not in LIGAS:
        return
    query = urlencode({"event": evento_id})
    url = "{}/{}/summary?{}".format(API_BASE, liga, query)
    try:
        payload = _get_json(url)
        estadisticas = _statistics_from_summary(payload)
        faltantes = [
            key for key, value in estadisticas.items()
            if value is None and key in {"corners_total", "tarjetas_total"}
        ]
        if faltantes:
            fallback = _buscar_totales_en_google(resultado)
            for key in faltantes:
                if key in fallback:
                    estadisticas[key] = fallback[key]
            if fallback:
                resultado["fuente_estadisticas"] = "ESPN Summary + búsqueda web en fuente oficial"
        resultado.update(estadisticas)
        resultado["fuente_estadisticas"] = "ESPN Summary"
        if not any(value is not None for value in estadisticas.values()):
            resultado["error_estadisticas"] = "Esperando estadística oficial"
            print("ESPN Summary sin estadísticas liquidables evento={}; queda PENDIENTE".format(evento_id))
        elif estadisticas.get("corners_total") is None or estadisticas.get("tarjetas_total") is None:
            resultado["error_estadisticas"] = "Esperando estadística oficial"
            print("ESPN Summary incompleto evento={}; estadísticas faltantes quedan PENDIENTE".format(evento_id))
    except Exception as error:
        print("Error ESPN Summary evento={}: {}".format(evento_id, error))
        resultado["error_estadisticas"] = "Esperando estadística oficial"


def obtener_resultados_partidos_hoy(
    partidos: Sequence[Tuple[str, str, Optional[str]]],
) -> List[Dict[str, object]]:
    """Consulta scoreboards públicos de ESPN para los partidos indicados."""
    fecha = datetime.now(ZoneInfo(COLOMBIA_TIMEZONE)).strftime("%Y%m%d")
    por_liga: Dict[str, List[Tuple[str, str]]] = {}
    for local, visitante, liga in partidos:
        ligas = [liga] if liga in LIGAS else list(LIGAS)
        for codigo in ligas:
            por_liga.setdefault(codigo, []).append((local, visitante))

    resultados: Dict[Tuple[str, str], Dict[str, object]] = {}
    for codigo_liga, equipos in por_liga.items():
        query = urlencode({"dates": fecha})
        url = "{}/{}/scoreboard?{}".format(API_BASE, codigo_liga, query)
        try:
            payload = _get_json(url)
        except Exception as error:
            print("Error ESPN liga={} fecha={}: {}".format(codigo_liga, fecha, error))
            continue
        events = payload.get("events", [])
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            resultado = _evento_a_resultado(event, codigo_liga)
            nombres = _fixture_names(event)
            if resultado is None or nombres is None:
                continue
            for local, visitante in equipos:
                mismo_orden = _nombres_coinciden(local, nombres[0]) and _nombres_coinciden(visitante, nombres[1])
                orden_inverso = _nombres_coinciden(local, nombres[1]) and _nombres_coinciden(visitante, nombres[0])
                if mismo_orden or orden_inverso:
                    resultados[(local.casefold(), visitante.casefold())] = resultado
                    print(
                        "ESPN fixture encontrado liga={} fecha={} evento={}".format(
                            codigo_liga,
                            fecha,
                            json.dumps(event, ensure_ascii=False),
                        )
                    )
    salida = list(resultados.values())
    for resultado in salida:
        if resultado.get("estado") in {"en_juego", "finalizado"}:
            _cargar_estadisticas_espn(resultado)
    return salida


def buscar_resultado_partido(
    local: str,
    visitante: str,
    resultados: List[Dict[str, object]],
) -> Optional[Dict[str, object]]:
    for resultado in resultados:
        mismo_orden = _nombres_coinciden(local, str(resultado.get("local", ""))) and _nombres_coinciden(
            visitante, str(resultado.get("visitante", ""))
        )
        orden_inverso = _nombres_coinciden(local, str(resultado.get("visitante", ""))) and _nombres_coinciden(
            visitante, str(resultado.get("local", ""))
        )
        if mismo_orden or orden_inverso:
            return resultado
    return None
