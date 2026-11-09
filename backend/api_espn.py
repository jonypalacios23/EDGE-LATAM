from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
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
    return list(resultados.values())


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
