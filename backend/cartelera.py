from __future__ import annotations

import json
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

if __package__:
    from .api_football import _fixture_to_result, _get_json
    from .valor import PROMEDIOS_LIGA
else:
    from api_football import _fixture_to_result, _get_json
    from valor import PROMEDIOS_LIGA


ROOT = Path(__file__).resolve().parent
ZONA_LOCAL = ZoneInfo("America/Bogota")


def _normalizar(texto: object) -> str:
    valor = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return "".join(caracter for caracter in valor if not unicodedata.combining(caracter)).strip()


def _fecha_local(fecha_texto: object) -> str:
    try:
        fecha = datetime.fromisoformat(str(fecha_texto).replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=ZoneInfo("UTC"))
        return fecha.astimezone(ZONA_LOCAL).date().isoformat()
    except (TypeError, ValueError):
        return ""


def obtener_cartelera_diaria(fecha_local: Optional[date] = None) -> List[Dict[str, object]]:
    """Get every fixture in the approved leagues for a local Colombia calendar day."""
    dia = fecha_local or datetime.now(ZONA_LOCAL).date()
    dia_texto = dia.isoformat()
    ligas_data = json.loads((ROOT / "ligas_habilitadas.json").read_text(encoding="utf-8"))
    ligas = ligas_data.get("ligas_habilitadas", [])
    por_nombre = {
        (_normalizar(item.get("pais")), _normalizar(item.get("liga_api"))): item.get("liga_app", item.get("liga_api", ""))
        for item in ligas if isinstance(item, dict)
    }
    correcciones_data = json.loads((ROOT / "correcciones_equipos.json").read_text(encoding="utf-8"))
    nombres_por_id = {
        int(item["team_id"]): item["nombre_real"]
        for item in correcciones_data.get("correcciones", [])
        if isinstance(item, dict) and item.get("team_id") is not None and item.get("nombre_real")
    }
    cache_path = ROOT / "cache_10anos.json"
    try:
        historico = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        historico = {}

    payload = _get_json("fixtures", {"date": dia_texto, "timezone": "America/Bogota"})
    respuesta = payload.get("response", [])
    partidos: List[Dict[str, object]] = []
    vistos = set()
    for fila in respuesta if isinstance(respuesta, list) else []:
        if not isinstance(fila, dict):
            continue
        fixture = fila.get("fixture", {})
        equipos = fila.get("teams", {})
        liga = fila.get("league", {})
        if not isinstance(fixture, dict) or not isinstance(equipos, dict) or not isinstance(liga, dict):
            continue
        if _fecha_local(fixture.get("date")) != dia_texto:
            continue
        pais_api, liga_api = liga.get("country", ""), liga.get("name", "")
        liga_app = por_nombre.get((_normalizar(pais_api), _normalizar(liga_api)))
        if not liga_app:
            continue
        local, visitante = equipos.get("home", {}), equipos.get("away", {})
        if not isinstance(local, dict) or not isinstance(visitante, dict):
            continue
        local_id, visitante_id = local.get("id"), visitante.get("id")
        fixture_id = fixture.get("id")
        if fixture_id is None or fixture_id in vistos or local_id is None or visitante_id is None:
            continue
        vistos.add(fixture_id)
        perfil_local = historico.get(str(local_id), {}) if isinstance(historico, dict) else {}
        perfil_visitante = historico.get(str(visitante_id), {}) if isinstance(historico, dict) else {}
        if not isinstance(perfil_local, dict):
            perfil_local = {}
        if not isinstance(perfil_visitante, dict):
            perfil_visitante = {}
        estado = fixture.get("status", {})
        score = fila.get("goals", {})
        nombre_local = nombres_por_id.get(int(local_id), str(local.get("name", "")))
        nombre_visitante = nombres_por_id.get(int(visitante_id), str(visitante.get("name", "")))
        partido: Dict[str, object] = {
            "fixture_id": fixture_id,
            "fecha": fixture.get("date"),
            "estado": str((estado or {}).get("short", "NS")) if isinstance(estado, dict) else "NS",
            "local": nombre_local,
            "visitante": nombre_visitante,
            "local_id": local_id,
            "visitante_id": visitante_id,
            "liga": liga_app,
            "liga_api": liga_api,
            "pais": pais_api,
            "league_id": liga.get("id"),
            "season": liga.get("season"),
            "goles_local": score.get("home") if isinstance(score, dict) else None,
            "goles_visitante": score.get("away") if isinstance(score, dict) else None,
            "analisis_10anos_local": perfil_local,
            "analisis_10anos_vis": perfil_visitante,
            "fuente_mercados_historicos": "promedio_liga",
        }
        # Match-level category averages fall back to the configured league baselines.
        if "jamaica" in str(pais_api).casefold():
            referencia = PROMEDIOS_LIGA["jamaica"]
        elif str(liga_app).casefold() == "primera b":
            referencia = PROMEDIOS_LIGA["primera b"]
        elif str(liga_app).casefold() == "primera a":
            referencia = PROMEDIOS_LIGA["primera a"]
        else:
            referencia = PROMEDIOS_LIGA["default"]
        esperado_local = float(perfil_local.get("prom_goles_casa_10anos") or referencia["goles_local"])
        esperado_visitante = float(perfil_visitante.get("prom_goles_fuera_10anos") or referencia["goles_visitante"])
        partido["corners"] = {"promedio_total_10anos": referencia["corners"], "dato": "Promedio histórico de liga"}
        partido["goles"] = {"promedio_total_10anos": esperado_local + esperado_visitante, "dato": "Estimación con el histórico disponible"}
        partido["tarjetas"] = {"promedio_total_10anos": referencia["tarjetas"], "dato": "Promedio histórico de liga"}
        partido["tiros_a_puerta"] = {"promedio_total_10anos": referencia["tiros_a_puerta"], "dato": "Promedio histórico de liga"}
        short = str(partido["estado"]).upper()
        if short in {"1H", "HT", "2H", "ET", "P", "LIVE", "FT", "AET", "PEN"}:
            try:
                partido["resultado_real"] = _fixture_to_result(fila)
                partido["datos_en_vivo"] = True
            except Exception as error:
                partido["resultado_real"] = None
                print("Error consultando resultado fixture {}: {}".format(fixture_id, error))
        else:
            partido["resultado_real"] = None
            partido["datos_en_vivo"] = False
        partidos.append(partido)
    return partidos
