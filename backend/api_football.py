from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://v3.football.api-sports.io"
API_KEY_ENV = "API_FOOTBALL_KEY"
LEAGUE_ID = 239
LEAGUE_IDS = [239, 240]  # 239 Primera A, 240 Primera B
SEASON = 2026
TIMEOUT_SECONDS = 15
FINAL_STATUSES = {"FT", "AET", "PEN"}
LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
CANCEL_STATUSES = {"PST", "CANC", "ABD", "AWD", "WO"}


def _load_api_key(env_path: Optional[Path] = None) -> Optional[str]:
    """Read the key from the process environment first, then the repo-root .env."""
    api_key = os.environ.get(API_KEY_ENV)
    if api_key:
        return api_key.strip() or None

    path = env_path or (Path(__file__).resolve().parents[1] / ".env")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("export "):
            entry = entry[len("export "):].strip()
        name, separator, value = entry.partition("=")
        if not separator or name.strip() != API_KEY_ENV:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        return value or None
    return None


def _headers() -> Dict[str, str]:
    api_key = _load_api_key()
    if not api_key:
        raise RuntimeError("Falta API_FOOTBALL_KEY en variable de entorno o archivo .env")
    return {"x-apisports-key": api_key, "Accept": "application/json"}


def _get_json_original(path: str, params: Dict[str, object]) -> Dict[str, object]:
    url = "{}/{}?{}".format(API_BASE, path.lstrip("/"), urlencode(params))
    request = Request(url, headers=_headers())
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.getcode()
            body = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError("API-Football status {} body: {}".format(error.code, body)) from error
    except URLError as error:
        raise RuntimeError("API-Football request failed: {}".format(error)) from error
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise RuntimeError("API-Football status {} body: {}".format(status, body)) from error
    if payload.get("errors"):
        raise RuntimeError("API-Football status {} errors/body: {}".format(status, json.dumps(payload, ensure_ascii=False)))
    return payload


def _stat_value(statistics: object, stat_type: str, none_is_zero: bool = False) -> Optional[int]:
    if not isinstance(statistics, list):
        return None
    for item in statistics:
        if not isinstance(item, dict) or str(item.get("type", "")).casefold() != stat_type.casefold():
            continue
        value = item.get("value")
        if value is None:
            return 0 if none_is_zero else None
        try:
            return int(float(str(value).replace("%", "")))
        except (TypeError, ValueError):
            return None
    return None


def _sum_stat(responses: object, stat_type: str, none_is_zero: bool = False) -> Optional[int]:
    if not isinstance(responses, list) or len(responses) < 2:
        return None
    values = []
    for team in responses[:2]:
        if not isinstance(team, dict):
            return None
        value = _stat_value(team.get("statistics"), stat_type, none_is_zero)
        if value is None:
            return None
        values.append(value)
    return sum(values)


def _stats_for_fixture(fixture_id: int) -> Dict[str, Optional[int]]:
    payload = _get_json("fixtures/statistics", {"fixture": fixture_id})
    responses = payload.get("response", [])
    corners = _sum_stat(responses, "Corner Kicks")
    yellow = _sum_stat(responses, "Yellow Cards")
    red = _sum_stat(responses, "Red Cards", none_is_zero=True)
    shots_on_target = _sum_stat(responses, "Shots on Goal")
    cards = yellow + red if yellow is not None and red is not None else None

    # Events are an audit signal for cards. They do not replace empty statistics.
    event_count = None
    try:
        events_payload = _get_json("fixtures/events", {"fixture": fixture_id})
        events = events_payload.get("response", [])
        if isinstance(events, list):
            event_count = sum(
                1 for event in events
                if isinstance(event, dict) and str(event.get("type", "")).casefold() == "card"
            )
    except Exception as error:
        print("API-Football events fixture={} error: {}".format(fixture_id, error))

    mismatch = cards is not None and event_count is not None and cards != event_count
    if mismatch:
        print(
            "API-Football validación de tarjetas fixture={}: statistics={} events={}".format(
                fixture_id, cards, event_count
            )
        )
    return {
        "corners_total": corners,
        "tarjetas_total": cards,
        "tarjetas_amarillas_total": yellow,
        "tarjetas_rojas_total": red,
        "tarjetas_eventos_total": event_count,
        "tarjetas_discrepancia": mismatch,
        "tiros_a_puerta_total": shots_on_target,
        "fuente_estadisticas": "API-Football",
    }


def _fixture_to_result(fixture_row: Dict[str, object]) -> Optional[Dict[str, object]]:
    fixture = fixture_row.get("fixture", {})
    teams = fixture_row.get("teams", {})
    goals = fixture_row.get("goals", {})
    league = fixture_row.get("league", {})
    if not isinstance(fixture, dict) or not isinstance(teams, dict):
        return None
    home = teams.get("home", {})
    away = teams.get("away", {})
    status = fixture.get("status", {})
    if not isinstance(home, dict) or not isinstance(away, dict) or not isinstance(status, dict):
        return None
    short = str(status.get("short", "")).upper()
    if short in FINAL_STATUSES:
        state, state_text = "finalizado", "Finalizado"
    elif short in LIVE_STATUSES:
        state = "en_juego"
        elapsed = status.get("elapsed")
        state_text = "Descanso" if short == "HT" else "EN VIVO{}".format(" {}'".format(elapsed) if elapsed is not None else "")
    elif short in CANCEL_STATUSES:
        state = "cancelado" if short in {"CANC", "PST", "WO"} else "suspendido"
        state_text = "Cancelado" if state == "cancelado" else "Suspendido"
    else:
        state, state_text = "pendiente", "Programado"
    home_goals = goals.get("home") if isinstance(goals, dict) else None
    away_goals = goals.get("away") if isinstance(goals, dict) else None
    result: Dict[str, object] = {
        "fixture_id": fixture.get("id"),
        "local": str(home.get("name", "")),
        "visitante": str(away.get("name", "")),
        "local_id": home.get("id"),
        "visitante_id": away.get("id"),
        "liga": str(league.get("name", "Colombia Primera A")) if isinstance(league, dict) else "Colombia Primera A",
        "estado": state,
        "estado_corto": short,
        "estado_texto": state_text,
        "minuto": status.get("elapsed"),
        "marcador_local": home_goals,
        "marcador_visitante": away_goals,
        "hora_inicio": str(fixture.get("date", ""))[11:16] or None,
        "fuente": "API-Football",
    }
    if isinstance(fixture.get("id"), int) and state in {"en_juego", "finalizado"}:
        try:
            result.update(_stats_for_fixture(fixture["id"]))
        except Exception as error:
            result.update({
                "corners_total": None,
                "tarjetas_total": None,
                "tarjetas_amarillas_total": None,
                "tarjetas_rojas_total": None,
                "tiros_a_puerta_total": None,
                "error_estadisticas": str(error),
                "fuente_estadisticas": "API-Football",
            })
            print("Error API-Football statistics fixture={}: {}".format(fixture.get("id"), error))
    return result


def obtener_resultados_partidos(partidos: Sequence[Dict[str, object]]) -> List[Dict[str, object]]:
    """Fetch each requested fixture by team IDs and its calendar date."""
    results: List[Dict[str, object]] = []
    fixture_ids = set()
    requests_cache: Dict[tuple, List[object]] = {}
    for partido in partidos:
        fecha = str(partido.get("fecha", "")).split("T", 1)[0]
        local_id = partido.get("local_id")
        visitante_id = partido.get("visitante_id")
        if not fecha or local_id is None or visitante_id is None:
            continue
        try:
            date.fromisoformat(fecha)
        except ValueError:
            print("Fecha de partido inválida para API-Football: {!r}".format(fecha))
            continue
        requested_ids = {str(local_id), str(visitante_id)}
        fixture_rows = []
        for team_id in requested_ids:
            cache_key = (team_id, fecha)
            if cache_key not in requests_cache:
                try:
                    payload = _get_json("fixtures", {"team": team_id, "date": fecha})
                    response = payload.get("response", [])
                    requests_cache[cache_key] = response if isinstance(response, list) else []
                except Exception as error:
                    print("Error API-Football fixtures team={} date={}: {}".format(team_id, fecha, error))
                    # Keep processing the other fixtures so one failed lookup cannot blank the full slate.
                    requests_cache[cache_key] = []
            fixture_rows.extend(requests_cache[cache_key])

        seen_rows = set()
        for row in fixture_rows:
            if not isinstance(row, dict):
                continue
            fixture = row.get("fixture", {})
            teams = row.get("teams", {})
            home = teams.get("home", {}) if isinstance(teams, dict) else {}
            away = teams.get("away", {}) if isinstance(teams, dict) else {}
            if not isinstance(home, dict) or not isinstance(away, dict):
                continue
            if {str(home.get("id")), str(away.get("id"))} != requested_ids:
                continue
            fixture_id = fixture.get("id") if isinstance(fixture, dict) else None
            if fixture_id in fixture_ids or fixture_id in seen_rows:
                continue
            result = _fixture_to_result(row)
            if result is not None:
                results.append(result)
                seen_rows.add(fixture_id)
                fixture_ids.add(fixture_id)
    return results


def buscar_resultado_por_ids(
    local_id: object,
    visitante_id: object,
    resultados: Sequence[Dict[str, object]],
) -> Optional[Dict[str, object]]:
    """Match an API result using team IDs only; display names are not identifiers."""
    requested_ids = {str(local_id), str(visitante_id)}
    for result in resultados:
        result_ids = {str(result.get("local_id", "")), str(result.get("visitante_id", ""))}
        if result_ids == requested_ids:
            return result
    return None


# --- PARCHE UTC: busca fecha + dia siguiente para fixtures ---
def _get_json(endpoint, params=None):
    # Si no es fixtures o no tiene fecha, comportamiento normal
    if endpoint != "fixtures" or not params or "date" not in params:
        return _get_json_original(endpoint, params)
    try:
        from datetime import datetime, timedelta
        fecha_str = str(params.get("date"))
        fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d")
        siguiente = (fecha_obj + timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        return _get_json_original(endpoint, params)

    data1 = _get_json_original(endpoint, params)
    params2 = dict(params)
    params2["date"] = siguiente
    data2 = _get_json_original(endpoint, params2)

    # Unir respuestas sin duplicar por fixture id
    resp1 = data1.get("response", []) if isinstance(data1, dict) else []
    resp2 = data2.get("response", []) if isinstance(data2, dict) else []
    vistos = set()
    unidos = []
    for f in resp1 + resp2:
        fid = f.get("fixture", {}).get("id") if isinstance(f, dict) else None
        if fid is None or fid not in vistos:
            vistos.add(fid)
            unidos.append(f)
    resultado = dict(data1) if isinstance(data1, dict) else {}
    resultado["response"] = unidos
    return resultado
