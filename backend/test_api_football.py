from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from api_football import (
    _sum_stat,
    buscar_resultado_por_ids,
    obtener_resultados_partidos,
    _fixture_to_result,
)
from main import liquidar_mercado, obtener_partidos_hoy


def probar_suma_estadisticas_por_equipo():
    response = [
        {"statistics": [
            {"type": "Corner Kicks", "value": 2},
            {"type": "Yellow Cards", "value": 3},
            {"type": "Red Cards", "value": None},
        ]},
        {"statistics": [
            {"type": "Corner Kicks", "value": 4},
            {"type": "Yellow Cards", "value": 2},
            {"type": "Red Cards", "value": 1},
        ]},
    ]
    assert _sum_stat(response, "Corner Kicks") == 6
    assert _sum_stat(response, "Yellow Cards") == 5
    assert _sum_stat(response, "Red Cards", none_is_zero=True) == 1


def probar_no_hay_total_si_statistics_vacio():
    assert _sum_stat([], "Corner Kicks") is None
    assert _sum_stat([], "Yellow Cards") is None


def probar_liquidacion_usa_estadisticas_y_no_marcador():
    final = {
        "estado": "finalizado",
        "marcador_local": 2,
        "marcador_visitante": 1,
        "corners_total": 6,
        "tarjetas_total": 6,
    }
    corners = liquidar_mercado(final, {"tipo": "corners", "direccion": "mas", "linea": 9.5})
    cards = liquidar_mercado(final, {"tipo": "tarjetas", "direccion": "mas", "linea": 4.5})
    assert corners["estado"] == "PERDIDO", corners
    assert "API-Football" in corners["texto"]
    assert cards["estado"] == "GANADO", cards
    without_stats = liquidar_mercado(
        {"estado": "finalizado", "marcador_local": 20, "marcador_visitante": 0},
        {"tipo": "corners", "direccion": "mas", "linea": 9.5},
    )
    assert without_stats["estado"] == "PENDIENTE", without_stats
    assert without_stats["texto"] == "Esperando estadística oficial API-Football"


def probar_fixture_y_coincidencia():
    fixture = {
        "fixture": {"id": 12345, "date": "2026-11-08T23:10:00+00:00", "status": {"short": "FT", "elapsed": 90}},
        "teams": {
            "home": {"id": 1111, "name": "Deportes Tolima"},
            "away": {"id": 1120, "name": "Millonarios"},
        },
        "goals": {"home": 2, "away": 1},
        "league": {"name": "Liga BetPlay"},
    }
    with patch("api_football._stats_for_fixture", return_value={"corners_total": 6, "tarjetas_total": 6}):
        result = _fixture_to_result(fixture)
    assert result and result["estado"] == "finalizado", result
    assert result["fixture_id"] == 12345
    assert buscar_resultado_por_ids(1111, 1120, [result]) == result
    assert buscar_resultado_por_ids(1111, 1460, [result]) is None


def probar_consulta_por_team_id_y_fecha_corta():
    fixture = {
        "fixture": {"id": 987, "date": "2026-11-10T20:30:00+00:00", "status": {"short": "NS"}},
        "teams": {
            "home": {"id": 1129, "name": "Envigado"},
            "away": {"id": 1460, "name": "Popayan"},
        },
        "goals": {"home": None, "away": None},
        "league": {"name": "Primera B"},
    }
    requests = []

    def fake_get_json(endpoint, params):
        requests.append((endpoint, params.copy()))
        return {"response": [fixture]}

    match = {
        "local": "Envigado",
        "visitante": "Boca Juniors de Cali",
        "local_id": 1129,
        "visitante_id": 1460,
        "fecha": "2026-11-10T20:30:00+00:00",
    }
    with patch("api_football._get_json", side_effect=fake_get_json):
        results = obtener_resultados_partidos([match])
    assert len(results) == 1, results
    assert {results[0]["local_id"], results[0]["visitante_id"]} == {1129, 1460}
    assert len(requests) == 2, requests
    assert all(endpoint == "fixtures" for endpoint, _ in requests)
    assert {params["team"] for _, params in requests} == {"1129", "1460"}
    assert all(params["date"] == "2026-11-10" for _, params in requests)


def probar_sin_coincidencia_conserva_prediccion_guardada():
    partidos_path = Path(__file__).with_name("partidos_hoy.json")
    stored = json.loads(partidos_path.read_text(encoding="utf-8"))
    boca = next(partido for partido in stored["partidos"] if partido.get("visitante_id") == 1460)
    expected_prediction = boca.get("prediccion")
    resultado_ajeno = {
        "local_id": 9991,
        "visitante_id": 9992,
        "local": "Otro local",
        "visitante": "Otro visitante",
    }
    with patch("main.obtener_resultados_partidos", return_value=[resultado_ajeno]):
        response = obtener_partidos_hoy(local=boca["local"], visitante=boca["visitante"])
    response_boca = response["partidos"][0]
    assert response_boca["resultado_real"] is None
    assert response_boca["prediccion"] == expected_prediction
    assert response_boca["analisis_10anos_vis"] == boca["analisis_10anos_vis"]


def probar_api_key_desde_entorno_o_env_local():
    from api_football import API_KEY_ENV, _headers, _load_api_key

    with tempfile.TemporaryDirectory() as temp_dir:
        env_path = Path(temp_dir) / ".env"
        env_path.write_text("# local secret\nAPI_FOOTBALL_KEY='archivo-secreto'\n", encoding="utf-8")
        with patch.dict(os.environ, {}, clear=True):
            assert _load_api_key(env_path) == "archivo-secreto"

        with patch.dict(os.environ, {API_KEY_ENV: "variable-secreta"}, clear=True):
            assert _load_api_key(env_path) == "variable-secreta"
            assert _headers()["x-apisports-key"] == "variable-secreta"

    with patch.dict(os.environ, {}, clear=True), patch(
        "api_football.Path.resolve", return_value=Path("/ruta/inexistente/backend/api_football.py")
    ):
        try:
            _headers()
        except RuntimeError as error:
            assert str(error) == "Falta API_FOOTBALL_KEY en variable de entorno o archivo .env"
            return
    raise AssertionError("Debía fallar cuando no hay clave en entorno ni en .env")


def main():
    pruebas = [
        ("Suma córners y tarjetas de ambos equipos", probar_suma_estadisticas_por_equipo),
        ("Estadísticas vacías quedan sin total", probar_no_hay_total_si_statistics_vacio),
        ("Liquida por estadísticas; ignora el marcador", probar_liquidacion_usa_estadisticas_y_no_marcador),
        ("Reconoce el fixture y sus equipos", probar_fixture_y_coincidencia),
        ("Consulta fixtures por ID y fecha YYYY-MM-DD", probar_consulta_por_team_id_y_fecha_corta),
        ("Sin coincidencia conserva pronóstico e histórico", probar_sin_coincidencia_conserva_prediccion_guardada),
        ("Lee la clave del entorno o del .env local", probar_api_key_desde_entorno_o_env_local),
    ]
    aprobadas = 0
    for nombre, prueba in pruebas:
        try:
            prueba()
            aprobadas += 1
            print("✅ PASÓ - {}".format(nombre))
        except Exception as error:
            print("❌ FALLÓ - {}: {}".format(nombre, error))
    print("API-Football: {}/{} pruebas pasaron".format(aprobadas, len(pruebas)))
    if aprobadas != len(pruebas):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
