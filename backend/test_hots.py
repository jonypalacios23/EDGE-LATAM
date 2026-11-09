from __future__ import annotations

from typing import Callable, List, Optional, Tuple

from corners import analizar_corners
from goles import analizar_goles
from kelly import calcular_kelly
from main import CalcularKellyRequest, calcular_kelly_endpoint
from tarjetas import analizar_tarjetas
from tiros import analizar_tiros


def ejecutar_prueba(nombre: str, prueba: Callable[[], None]) -> bool:
    try:
        prueba()
    except Exception as error:
        print("❌ FALLÓ - {}: {}".format(nombre, error))
        return False

    print("✅ PASÓ - {}".format(nombre))
    return True


def comprobar_recomendacion(
    analisis: dict,
    recomendacion_esperada: str,
    valor_minimo: Optional[float] = None,
) -> None:
    assert set(analisis) == {"probabilidad", "cuota", "valor", "recomendacion"}
    assert 0 <= analisis["probabilidad"] <= 1
    assert analisis["recomendacion"] == recomendacion_esperada, analisis
    if valor_minimo is not None:
        assert analisis["valor"] > valor_minimo, analisis


def probar_corners_sin_valor() -> None:
    analisis = analizar_corners(5.8, 4.2, 1.90)
    comprobar_recomendacion(analisis, "NO HAY VALOR")


def probar_corners_con_valor() -> None:
    analisis = analizar_corners(6.5, 5.5, 2.40)
    comprobar_recomendacion(analisis, "OVER 9.5", valor_minimo=8)


def probar_goles_primer_caso() -> None:
    analisis = analizar_goles(1.4, 1.2, 1.80)
    comprobar_recomendacion(analisis, "NO HAY VALOR")


def probar_goles_segundo_caso() -> None:
    analisis = analizar_goles(1.8, 1.6, 2.20)
    comprobar_recomendacion(analisis, "OVER 2.5", valor_minimo=8)


def probar_tarjetas_primer_caso() -> None:
    analisis = analizar_tarjetas(2.1, 2.3, 1.90)
    comprobar_recomendacion(analisis, "NO HAY VALOR")


def probar_tarjetas_segundo_caso() -> None:
    analisis = analizar_tarjetas(2.8, 2.9, 2.30)
    comprobar_recomendacion(analisis, "OVER 4.5", valor_minimo=8)


def probar_tiros_sin_valor() -> None:
    analisis = analizar_tiros(3.8, 3.5, 2.20)
    comprobar_recomendacion(analisis, "NO HAY VALOR")
    kelly = calcular_kelly(analisis["probabilidad"], analisis["cuota"], 1000)
    assert kelly["stake_recomendado"] == 0, kelly
    assert kelly["porcentaje_banco"] == 0, kelly


def probar_tiros_con_valor() -> None:
    analisis = analizar_tiros(5.0, 4.8, 2.20)
    comprobar_recomendacion(analisis, "OVER 8.5", valor_minimo=8)


def probar_kelly_stake_positivo() -> None:
    resultado = calcular_kelly(0.60, 2.0, 1000)
    assert resultado == {"stake_recomendado": 50.0, "porcentaje_banco": 5.0}, resultado


def probar_kelly_sin_valor() -> None:
    resultado = calcular_kelly(0.40, 2.0, 1000)
    assert resultado == {"stake_recomendado": 0.0, "porcentaje_banco": 0.0}, resultado


def comprobar_kelly_sin_recomendacion(
    analisis: dict,
) -> None:
    resultado = calcular_kelly_endpoint(
        CalcularKellyRequest(
            probabilidad=analisis["probabilidad"],
            cuota=analisis["cuota"],
            banco=1000,
            recomendacion=analisis["recomendacion"],
        )
    )
    assert resultado == {"stake_recomendado": 0.0, "porcentaje_banco": 0.0}, resultado


def probar_kelly_corners_sin_valor() -> None:
    comprobar_kelly_sin_recomendacion(analizar_corners(5.8, 4.2, 1.90))


def probar_kelly_goles_sin_valor() -> None:
    comprobar_kelly_sin_recomendacion(analizar_goles(1.4, 1.2, 1.80))


def probar_kelly_tarjetas_sin_valor() -> None:
    comprobar_kelly_sin_recomendacion(analizar_tarjetas(2.1, 2.3, 1.90))


def probar_cuota_invalida() -> None:
    try:
        analizar_corners(5.0, 5.0, 0)
    except ValueError:
        return
    raise AssertionError("La cuota 0 debía producir un ValueError controlado.")


def main() -> None:
    pruebas: List[Tuple[str, Callable[[], None]]] = [
        ("Córners (5.8, 4.2, 1.90): NO HAY VALOR", probar_corners_sin_valor),
        ("Córners (6.5, 5.5, 2.40): OVER 9.5 y valor > 8", probar_corners_con_valor),
        ("Goles (1.4, 1.2, 1.80)", probar_goles_primer_caso),
        ("Goles (1.8, 1.6, 2.20)", probar_goles_segundo_caso),
        ("Tarjetas (2.1, 2.3, 1.90)", probar_tarjetas_primer_caso),
        ("Tarjetas (2.8, 2.9, 2.30)", probar_tarjetas_segundo_caso),
        ("Tiros a puerta: NO HAY VALOR", probar_tiros_sin_valor),
        ("Tiros a puerta: OVER 8.5 y valor > 8", probar_tiros_con_valor),
        ("Kelly: stake fraccional y porcentaje del banco", probar_kelly_stake_positivo),
        ("Kelly: sin valor devuelve stake 0", probar_kelly_sin_valor),
        ("Kelly en Córners: sin valor devuelve stake 0", probar_kelly_corners_sin_valor),
        ("Kelly en Goles: sin valor devuelve stake 0", probar_kelly_goles_sin_valor),
        ("Kelly en Tarjetas: sin valor devuelve stake 0", probar_kelly_tarjetas_sin_valor),
        ("Cuota inválida: error controlado", probar_cuota_invalida),
    ]
    aprobadas = sum(ejecutar_prueba(nombre, prueba) for nombre, prueba in pruebas)
    print("HOTS EDGE: {}/{} pruebas pasaron".format(aprobadas, len(pruebas)))


if __name__ == "__main__":
    main()
