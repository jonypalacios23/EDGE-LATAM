from __future__ import annotations

import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


API_BASE = "https://v3.football.api-sports.io"
COLOMBIA_TIMEZONE = "America/Bogota"
REQUEST_TIMEOUT_SECONDS = 5
FINISHED_STATUSES = {"FT", "AET", "PEN", "AWD", "WO"}
LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "INT"}


def _get_json(endpoint: str, parameters: Dict[str, object], api_key: str) -> Dict[str, object]:
    query = urlencode(parameters)
    request = Request(
        "{}/{}?{}".format(API_BASE, endpoint, query),
        headers={"x-apisports-key": api_key, "Accept": "application/json"},
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        content = response.read()
    if not content:
        return {"response": []}
    payload = json.loads(content.decode("utf-8"))
    if payload.get("errors"):
        raise ValueError("API-Football devolvió un error")
    return payload


def _league_id(api_key: str, season: int) -> Optional[int]:
    payload = _get_json(
        "leagues",
        {"country": "Colombia", "season": season},
        api_key,
    )
    for entry in payload.get("response", []):
        league = entry.get("league", {})
        country = entry.get("country", {})
        if (
            str(league.get("name", "")).strip().casefold() == "primera b"
            and str(country.get("name", "")).strip().casefold() == "colombia"
        ):
            try:
                return int(league["id"])
            except (KeyError, TypeError, ValueError):
                return None
    return None


def _as_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _team_statistics(statistics: List[Dict[str, object]]) -> Dict[str, Optional[int]]:
    output: Dict[str, Optional[int]] = {
        "corners": None,
        "yellow_cards": None,
        "red_cards": None,
        "shots_on_goal": None,
    }
    names = {
        "Corner Kicks": "corners",
        "Yellow Cards": "yellow_cards",
        "Red Cards": "red_cards",
        "Shots on Goal": "shots_on_goal",
    }
    for item in statistics:
        key = names.get(str(item.get("type", "")))
        if key:
            output[key] = _as_int(item.get("value"))
    return output


def _statistics_for_fixture(api_key: str, fixture_id: int) -> List[Dict[str, object]]:
    payload = _get_json("fixtures/statistics", {"fixture": fixture_id}, api_key)
    response = payload.get("response", [])
    if not isinstance(response, list):
        return []
    return response


def _pair_total(home: Optional[int], away: Optional[int]) -> Optional[int]:
    if home is None or away is None:
        return None
    return home + away


def _fixture_record(
    fixture: Dict[str, object],
    statistics: List[Dict[str, object]],
) -> Dict[str, object]:
    teams = fixture.get("teams", {})
    home_name = str(teams.get("home", {}).get("name", ""))
    away_name = str(teams.get("away", {}).get("name", ""))

    home_stats: Dict[str, Optional[int]] = {}
    away_stats: Dict[str, Optional[int]] = {}
    for team_data in statistics:
        team_name = str(team_data.get("team", {}).get("name", ""))
        parsed = _team_statistics(team_data.get("statistics", []))
        if team_name.casefold() == home_name.casefold():
            home_stats = parsed
        elif team_name.casefold() == away_name.casefold():
            away_stats = parsed
    if not home_stats and len(statistics) > 0:
        home_stats = _team_statistics(statistics[0].get("statistics", []))
    if not away_stats and len(statistics) > 1:
        away_stats = _team_statistics(statistics[1].get("statistics", []))

    fixture_info = fixture.get("fixture", {})
    status_short = str(fixture_info.get("status", {}).get("short", "")).upper()
    if status_short in FINISHED_STATUSES:
        match_state = "finalizado"
    elif status_short in LIVE_STATUSES:
        match_state = "en_juego"
    else:
        match_state = "pendiente"

    goals = fixture.get("goals", {})
    home_goals = _as_int(goals.get("home"))
    away_goals = _as_int(goals.get("away"))
    cards_home = home_stats.get("yellow_cards")
    cards_away = away_stats.get("yellow_cards")
    red_home = home_stats.get("red_cards") or 0
    red_away = away_stats.get("red_cards") or 0
    cards_total = None
    if cards_home is not None and cards_away is not None:
        cards_total = cards_home + cards_away + red_home + red_away

    return {
        "fixture_id": fixture_info.get("id"),
        "local": home_name,
        "visitante": away_name,
        "estado": match_state,
        "marcador_local": home_goals,
        "marcador_visitante": away_goals,
        "marcador_final": _pair_total(home_goals, away_goals),
        "corners_total": _pair_total(home_stats.get("corners"), away_stats.get("corners")),
        "goles_total": _pair_total(home_goals, away_goals),
        "tarjetas_total": cards_total,
        "tiros_a_puerta_total": _pair_total(
            home_stats.get("shots_on_goal"),
            away_stats.get("shots_on_goal"),
        ),
    }


def obtener_partidos_primera_b_hoy() -> List[Dict[str, object]]:
    """Devuelve fixtures y estadísticas de Primera B para hoy, o [] si falla la API."""
    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        return []

    try:
        today = datetime.now(ZoneInfo(COLOMBIA_TIMEZONE)).date()
        season = today.year
        league_id = _league_id(api_key, season)
        if league_id is None:
            return []

        payload = _get_json(
            "fixtures",
            {
                "date": today.isoformat(),
                "league": league_id,
                "season": season,
                "timezone": COLOMBIA_TIMEZONE,
            },
            api_key,
        )
        fixtures = payload.get("response", [])
        if not isinstance(fixtures, list) or not fixtures:
            return []

        fixture_ids = []
        for item in fixtures:
            try:
                fixture_ids.append(int(item["fixture"]["id"]))
            except (KeyError, TypeError, ValueError):
                fixture_ids.append(None)

        # Solo se consultan estadísticas cuando el fixture terminó; para el
        # resto basta su estado y evitamos llamadas de estadísticas innecesarias.
        finished_ids = set()
        for item, fixture_id in zip(fixtures, fixture_ids):
            status = str(item.get("fixture", {}).get("status", {}).get("short", "")).upper()
            if fixture_id is not None and status in FINISHED_STATUSES:
                finished_ids.add(fixture_id)

        stats_by_id: Dict[int, List[Dict[str, object]]] = {}
        valid_ids = [fixture_id for fixture_id in fixture_ids if fixture_id in finished_ids]
        if valid_ids:
            with ThreadPoolExecutor(max_workers=min(8, len(valid_ids))) as executor:
                futures = {
                    fixture_id: executor.submit(_statistics_for_fixture, api_key, fixture_id)
                    for fixture_id in valid_ids
                }
                for fixture_id, future in futures.items():
                    try:
                        stats_by_id[fixture_id] = future.result()
                    except Exception as error:
                        print("Error API:", error)
                        stats_by_id[fixture_id] = []

        output = []
        for item, fixture_id in zip(fixtures, fixture_ids):
            statistics = stats_by_id.get(fixture_id, []) if fixture_id is not None else []
            output.append(_fixture_record(item, statistics))
        return output
    except Exception as error:
        print("Error API:", error)
        return []


def _normalizar_nombre(nombre: str) -> List[str]:
    texto = unicodedata.normalize("NFKD", nombre.casefold())
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return [token for token in re.findall(r"[a-z0-9]+", texto) if token not in {"fc", "cd", "club"}]


def _nombres_coinciden(nombre_manual: str, nombre_api: str) -> bool:
    manual = _normalizar_nombre(nombre_manual)
    api = _normalizar_nombre(nombre_api)
    return bool(manual and api and manual == api)


def buscar_resultado_partido(
    local: str,
    visitante: str,
    resultados: List[Dict[str, object]],
) -> Optional[Dict[str, object]]:
    for resultado in resultados:
        mismos_equipos = _nombres_coinciden(local, str(resultado.get("local", ""))) and _nombres_coinciden(
            visitante,
            str(resultado.get("visitante", "")),
        )
        equipos_invertidos = _nombres_coinciden(local, str(resultado.get("visitante", ""))) and _nombres_coinciden(
            visitante,
            str(resultado.get("local", "")),
        )
        if mismos_equipos or equipos_invertidos:
            return resultado
    return None
