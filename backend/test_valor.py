from __future__ import annotations

from valor import (
    calcular_picks_valor_partido,
    liquidar_picks_finalizados,
    probabilidad_poisson_over,
    seleccionar_picks_dia,
)


def partido_con_valor():
    return {
        "local": "Local",
        "visitante": "Visitante",
        "analisis_10anos_local": {
            "total_partidos_10anos": 100,
            "over25_pct": 68,
            "prom_goles_casa_10anos": 1.8,
        },
        "analisis_10anos_vis": {
            "total_partidos_10anos": 100,
            "over25_pct": 68,
            "prom_goles_fuera_10anos": 1.0,
        },
        "corners": {"promedio_total_10anos": 10.0, "confianza": "Media"},
        "goles": {"promedio_total_10anos": 2.8, "confianza": "Alta"},
        "tarjetas": {"promedio_total_10anos": 5.5, "confianza": "Media"},
        "tiros_a_puerta": {"promedio_total_10anos": 10.0, "confianza": "Media"},
        "odds": {
            "corners_over_8_5": 1.92,
            "goles_over_2_5": 1.92,
            "tarjetas_over_4_5": 1.92,
            "tiros_over_8_5": 1.92,
            "doble_oportunidad_1x": 1.92,
        },
    }


def test_poisson_and_edge_threshold():
    assert 0 < probabilidad_poisson_over(10.0, 8.5) < 1
    picks = calcular_picks_valor_partido(partido_con_valor())
    assert len(picks) == 5
    assert any(pick["tiene_valor"] for pick in picks)
    assert all(pick["tiene_valor"] == (pick["edge"] >= 0.08) for pick in picks)
    assert all(1 <= pick["stake_pct"] <= 4 for pick in picks if pick["tiene_valor"])
    assert all(not pick["cuota_estimada"] for pick in picks)


def test_estimated_odds_are_marked():
    partido = partido_con_valor()
    del partido["odds"]
    picks = calcular_picks_valor_partido(partido)
    assert len(picks) == 5
    assert all(pick["cuota_estimada"] for pick in picks)


def test_every_market_is_returned_for_every_match():
    partidos = [partido_con_valor() for _ in range(4)]
    total = seleccionar_picks_dia(partidos)
    assert total > 0
    assert all(len(partido["picks_valor"]) == 5 for partido in partidos)
    for partido in partidos:
        assert all("tiene_valor" in pick for pick in partido["picks_valor"])


def test_finalized_pick_settlement_uses_market_data():
    partido = partido_con_valor()
    partido.update({
        "estado": "FINALIZADO",
        "es_finalizado": True,
        "goles_local": 2,
        "goles_visitante": 0,
        "picks_valor": [
            {"tipo": "goles_over_2_5", "linea": 2.5},
            {"tipo": "corners_over_8_5", "linea": 8.5},
            {"tipo": "doble_oportunidad_1x", "linea": None},
        ],
    })
    liquidar_picks_finalizados(partido, {
        "estado": "finalizado",
        "marcador_local": 2,
        "marcador_visitante": 0,
        "corners_total": 11,
    })
    assert [pick["resultado_pick"] for pick in partido["picks_valor"]] == ["PERDIDO", "GANADO", "GANADO"]


def test_historico_completo_parcial_y_equipos_nuevos():
    completo = calcular_picks_valor_partido(partido_con_valor())
    assert all(pick["confianza"] == "Alta" and pick["badge_datos"] == "Datos: 10 años completos" for pick in completo)

    parcial = partido_con_valor()
    for equipo in ("analisis_10anos_local", "analisis_10anos_vis"):
        parcial[equipo]["total_partidos_10anos"] = 45
    picks_parciales = calcular_picks_valor_partido(parcial)
    assert all(pick["confianza"] == "Media" for pick in picks_parciales)
    assert all("45 partidos" in pick["badge_datos"] for pick in picks_parciales)

    nuevo = {
        "local": "Popayan", "visitante": "Rival con histórico", "local_id": 1448,
        "liga": "Primera B", "league_id": 240,
        "analisis_10anos_vis": {"total_partidos_10anos": 45, "prom_goles_fuera_10anos": 1.1, "over25_pct": 48},
    }
    picks_nuevo = calcular_picks_valor_partido(nuevo)
    assert len(picks_nuevo) == 5
    assert all(pick["confianza"] == "Baja" for pick in picks_nuevo)
    assert all("promedio liga Primera B" in pick["badge_datos"] for pick in picks_nuevo)
    assert all(pick["probabilidad_real"] is not None and pick["edge"] is not None for pick in picks_nuevo)
    assert all(pick["stake_pct"] <= 1 for pick in picks_nuevo)

    dos_nuevos = {"local": "Nuevo A", "visitante": "Nuevo B", "league_id": 240, "liga": "Primera B"}
    picks_dos_nuevos = calcular_picks_valor_partido(dos_nuevos)
    assert len(picks_dos_nuevos) == 5
    assert all(pick["confianza"] == "Baja" and "Primera B" in pick["badge_datos"] for pick in picks_dos_nuevos)
    assert all(pick["probabilidad_real"] is not None and pick["edge"] is not None for pick in picks_dos_nuevos)


def test_finalized_statistics_fall_back_to_league_estimates():
    partido = partido_con_valor()
    partido.update({"league_id": 239, "estado": "FINALIZADO", "es_finalizado": True, "goles_local": 2, "goles_visitante": 0})
    partido["picks_valor"] = [
        {"tipo": "corners_over_8_5", "mercado": "+8.5 Córners", "linea": 8.5},
        {"tipo": "tarjetas_over_4_5", "mercado": "Over 4.5 Tarjetas", "linea": 4.5},
    ]
    liquidar_picks_finalizados(partido, {"estado": "finalizado", "marcador_local": 2, "marcador_visitante": 0})
    picks = partido["picks_valor"]
    assert [pick["resultado_pick"] for pick in picks] == ["GANADO", "GANADO"]
    assert all(pick["resultado_nota"] == "Liquidado con datos estimados - Confianza Baja" for pick in picks)
    assert picks[0]["total_estimado"] == 9.2
    assert picks[1]["total_estimado"] == 4.6


if __name__ == "__main__":
    pruebas = [
        test_poisson_and_edge_threshold,
        test_estimated_odds_are_marked,
        test_every_market_is_returned_for_every_match,
        test_finalized_pick_settlement_uses_market_data,
        test_historico_completo_parcial_y_equipos_nuevos,
        test_finalized_statistics_fall_back_to_league_estimates,
    ]
    for prueba in pruebas:
        prueba()
        print("✅ PASÓ - {}".format(prueba.__name__))
