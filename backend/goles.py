from __future__ import annotations

from math import exp, factorial
from typing import Dict, Union

if __package__:
    from .value import calcular_valor
else:
    from value import calcular_valor


def analizar_goles(
    promedio_local_goles: float,
    promedio_visitante_goles: float,
    cuota_over_2_5: float,
) -> Dict[str, Union[float, str]]:
    """Estima la probabilidad de 3 o más goles con una distribución Poisson."""
    if promedio_local_goles < 0 or promedio_visitante_goles < 0:
        raise ValueError("Los promedios de goles no pueden ser negativos.")
    if cuota_over_2_5 <= 1:
        raise ValueError("La cuota decimal debe ser mayor que 1.")

    media_total = promedio_local_goles + promedio_visitante_goles
    probabilidad = 1 - sum(
        exp(-media_total) * media_total**k / factorial(k)
        for k in range(3)
    )
    valor = calcular_valor(probabilidad, cuota_over_2_5)

    return {
        "probabilidad": round(probabilidad, 4),
        "cuota": cuota_over_2_5,
        "valor": round(valor, 2),
        "recomendacion": "OVER 2.5" if valor > 8 else "NO HAY VALOR",
    }
