from __future__ import annotations

from unittest.mock import patch

from api_football import _sum_stat, buscar_resultado_partido, _fixture_to_result
from main import liquidar_mercado


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
        "teams": {"home": {"name": "Deportes Tolima"}, "away": {"name": "Millonarios"}},
        "goals": {"home": 2, "away": 1},
        "league": {"name": "Liga BetPlay"},
    }
    with patch("api_football._stats_for_fixture", return_value={"corners_total": 6, "tarjetas_total": 6}):
        result = _fixture_to_result(fixture)
    assert result and result["estado"] == "finalizado", result
    assert result["fixture_id"] == 12345
    assert buscar_resultado_partido("Tolima", "Millonarios", [result]) == result


def probar_api_key_solo_desde_entorno():
    from api_football import _headers

    with patch.dict("os.environ", {}, clear=True):
        try:
            _headers()
        except RuntimeError as error:
            assert str(error) == "Falta API_FOOTBALL_KEY en el entorno"
            return
    raise AssertionError("Debía exigir API_FOOTBALL_KEY del entorno")


def main():
    pruebas = [
        ("Suma córners y tarjetas de ambos equipos", probar_suma_estadisticas_por_equipo),
        ("Estadísticas vacías quedan sin total", probar_no_hay_total_si_statistics_vacio),
        ("Liquida por estadísticas; ignora el marcador", probar_liquidacion_usa_estadisticas_y_no_marcador),
        ("Reconoce el fixture y sus equipos", probar_fixture_y_coincidencia),
        ("Lee la clave solo del entorno", probar_api_key_solo_desde_entorno),
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
