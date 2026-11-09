from __future__ import annotations


def calcular_valor(probabilidad_ia: float, cuota_casa: float) -> float:
    """Calcula el valor esperado porcentual de una cuota decimal."""
    return (probabilidad_ia * cuota_casa - 1) * 100
