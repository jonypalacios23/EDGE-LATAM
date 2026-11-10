from __future__ import annotations

from math import exp, factorial
from typing import Dict, Union

if __package__:
    from .value import calcular_valor
else:
    from value import calcular_valor


def analizar_tiros(
    promedio_local_tiros: float,
    promedio_visitante_tiros: float,
    cuota_over_8_5: float,
) -> Dict[str, Union[float, str]]:
    """Estima la probabilidad de 9 o más tiros a puerta con Poisson."""
    if promedio_local_tiros < 0 or promedio_visitante_tiros < 0:
        raise ValueError("Los promedios de tiros no pueden ser negativos.")
    if cuota_over_8_5 <= 1:
        raise ValueError("La cuota decimal debe ser mayor que 1.")

    media_total = promedio_local_tiros + promedio_visitante_tiros
    probabilidad = 1 - sum(
        exp(-media_total) * media_total**k / factorial(k)
        for k in range(9)
    )
    valor = calcular_valor(probabilidad, cuota_over_8_5)

    return {
        "probabilidad": round(probabilidad, 4),
        "cuota": cuota_over_8_5,
        "valor": round(valor, 2),
        "recomendacion": "OVER 8.5" if valor > 8 else "NO HAY VALOR",
    }
