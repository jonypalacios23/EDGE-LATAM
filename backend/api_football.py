from __future__ import annotations

import json
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError
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
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status_code = response.getcode()
            content = response.read()
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            "API-Football status {} body: {}".format(error.code, body)
        ) from error
    if not content:
        return {"response": []}
    body = content.decode("utf-8", errors="replace")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "API-Football status {} body: {}".format(status_code, body)
        ) from error
    if payload.get("errors"):
        raise RuntimeError(
            "API-Football status {} body: {}".format(status_code, body)
        )
    return payload


def _buscar_id_equipo(api_key: str, nombre: str) -> Optional[int]:
    payload = _get_json(
        "teams",
        {"search": nombre, "country": "Colombia"},
        api_key,
    )
    for entry in payload.get("response", []):
        team = entry.get("team", {})
        if _nombres_coinciden(nombre, str(team.get("name", ""))):
            try:
                return int(team["id"])
            except (KeyError, TypeError, ValueError):
                continue
    print(
        "API-Football team search sin coincidencia: equipo={} body={}".format(
            nombre,
            json.dumps(payload, ensure_ascii=False),
        )
    )
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


def _hora_inicio_colombia(fixture_date: object) -> Optional[str]:
    if not fixture_date:
        return None
    try:
        fecha = datetime.fromisoformat(str(fixture_date).replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=ZoneInfo(COLOMBIA_TIMEZONE))
        return fecha.astimezone(ZoneInfo(COLOMBIA_TIMEZONE)).strftime("%H:%M")
    except (TypeError, ValueError):
        return None


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
    status_info = fixture_info.get("status", {})
    status_short = str(status_info.get("short", "")).upper()
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
        "estado_corto": status_short,
        "minuto": status_info.get("elapsed"),
        "hora_inicio": _hora_inicio_colombia(fixture_info.get("date")),
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


def obtener_resultados_partidos_hoy(
    pares_equipos: List[Tuple[str, str]],
) -> List[Dict[str, object]]:
    """Busca en API-Football los fixtures de hoy de los equipos manuales."""
    api_key = os.getenv("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        print("Falta KEY")
        raise RuntimeError("Falta KEY")

    try:
        today = datetime.now(ZoneInfo(COLOMBIA_TIMEZONE)).date()
        fixtures_by_id = {}
        pares_validos = [(local, visitante) for local, visitante in pares_equipos if local and visitante]
        for local, visitante in pares_validos:
            for nombre_equipo in (local, visitante):
                team_id = _buscar_id_equipo(api_key, nombre_equipo)
                if team_id is None:
                    continue
                payload = _get_json(
                    "fixtures",
                    {
                        "date": today.isoformat(),
                        "team": team_id,
                        "timezone": COLOMBIA_TIMEZONE,
                    },
                    api_key,
                )
                team_fixtures = payload.get("response", [])
                print(
                    "API-Football fixtures query: equipo={} team_id={} date={} response={}".format(
                        nombre_equipo,
                        team_id,
                        today.isoformat(),
                        json.dumps(team_fixtures, ensure_ascii=False),
                    )
                )
                if not isinstance(team_fixtures, list):
                    continue
                for fixture in team_fixtures:
                    try:
                        fixture_id = int(fixture["fixture"]["id"])
                        local_api = str(fixture.get("teams", {}).get("home", {}).get("name", ""))
                        visitante_api = str(fixture.get("teams", {}).get("away", {}).get("name", ""))
                    except (KeyError, TypeError, ValueError):
                        continue
                    equipos_esperados = (
                        _nombres_coinciden(local, local_api)
                        and _nombres_coinciden(visitante, visitante_api)
                    ) or (
                        _nombres_coinciden(local, visitante_api)
                        and _nombres_coinciden(visitante, local_api)
                    )
                    if equipos_esperados:
                        fixtures_by_id[fixture_id] = fixture
        fixtures = list(fixtures_by_id.values())
        if not fixtures:
            print("API-Football: no encontró fixture de los equipos manuales para {}".format(today.isoformat()))
            return []

        fixture_ids = []
        for item in fixtures:
            try:
                fixture_ids.append(int(item["fixture"]["id"]))
            except (KeyError, TypeError, ValueError):
                fixture_ids.append(None)

        # Consultar estadísticas tanto en vivo como al finalizar permite
        # mostrar el progreso y la liquidación de cada mercado.
        stats_fixture_ids = set()
        for item, fixture_id in zip(fixtures, fixture_ids):
            status = str(item.get("fixture", {}).get("status", {}).get("short", "")).upper()
            if fixture_id is not None and (status in FINISHED_STATUSES or status in LIVE_STATUSES):
                stats_fixture_ids.add(fixture_id)

        stats_by_id: Dict[int, List[Dict[str, object]]] = {}
        stats_errors = set()
        valid_ids = [fixture_id for fixture_id in fixture_ids if fixture_id in stats_fixture_ids]
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
                        stats_errors.add(fixture_id)

        output = []
        for item, fixture_id in zip(fixtures, fixture_ids):
            statistics = stats_by_id.get(fixture_id, []) if fixture_id is not None else []
            record = _fixture_record(item, statistics)
            record["error_estadisticas"] = fixture_id in stats_errors
            output.append(record)
        return output
    except Exception as error:
        print("Error API:", error)
        raise


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
