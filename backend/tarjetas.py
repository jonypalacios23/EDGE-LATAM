from __future__ import annotations

from math import exp, factorial
from typing import Dict, Union

from value import calcular_valor


def analizar_tarjetas(
    promedio_local_tarjetas: float,
    promedio_visitante_tarjetas: float,
    cuota_over_4_5: float,
) -> Dict[str, Union[float, str]]:
    """Estima la probabilidad de 5 o más tarjetas con una distribución Poisson."""
    if promedio_local_tarjetas < 0 or promedio_visitante_tarjetas < 0:
        raise ValueError("Los promedios de tarjetas no pueden ser negativos.")
    if cuota_over_4_5 <= 1:
        raise ValueError("La cuota decimal debe ser mayor que 1.")

    media_total = promedio_local_tarjetas + promedio_visitante_tarjetas
    probabilidad = 1 - sum(
        exp(-media_total) * media_total**k / factorial(k)
        for k in range(5)
    )
    valor = calcular_valor(probabilidad, cuota_over_4_5)

    return {
        "probabilidad": round(probabilidad, 4),
        "cuota": cuota_over_4_5,
        "valor": round(valor, 2),
        "recomendacion": "OVER 4.5" if valor > 8 else "NO HAY VALOR",
    }
