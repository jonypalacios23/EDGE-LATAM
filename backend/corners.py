from __future__ import annotations

from math import exp, factorial
from typing import Dict, Union

if __package__:
    from .value import calcular_valor
else:
    from value import calcular_valor


def analizar_corners(
    promedio_local: float,
    promedio_visitante: float,
    cuota_over_9_5: float,
) -> Dict[str, Union[float, str]]:
    """Estima la probabilidad de 10 o más córners con una distribución Poisson."""
    if promedio_local < 0 or promedio_visitante < 0:
        raise ValueError("Los promedios de córners no pueden ser negativos.")
    if cuota_over_9_5 <= 1:
        raise ValueError("La cuota decimal debe ser mayor que 1.")

    media_total = promedio_local + promedio_visitante
    probabilidad = 1 - sum(
        exp(-media_total) * media_total**k / factorial(k)
        for k in range(10)
    )
    valor = calcular_valor(probabilidad, cuota_over_9_5)

    return {
        "probabilidad": round(probabilidad, 4),
        "cuota": cuota_over_9_5,
        "valor": round(valor, 2),
        "recomendacion": "OVER 9.5" if valor >= 8 else "NO HAY VALOR",
    }
