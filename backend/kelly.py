from __future__ import annotations

from typing import Dict


def calcular_kelly(
    probabilidad: float,
    cuota: float,
    banco: float,
    fraccion_kelly: float = 0.25,
) -> Dict[str, float]:
    """Devuelve el stake recomendado y su porcentaje del banco con Kelly fraccional."""
    if not 0 <= probabilidad <= 1:
        raise ValueError("La probabilidad debe estar entre 0 y 1.")
    if cuota <= 1:
        raise ValueError("La cuota decimal debe ser mayor que 1.")
    if banco < 0:
        raise ValueError("El banco no puede ser negativo.")
    if not 0 <= fraccion_kelly <= 1:
        raise ValueError("La fracción Kelly debe estar entre 0 y 1.")

    ventaja = probabilidad * cuota - 1
    if ventaja <= 0 or banco == 0 or fraccion_kelly == 0:
        return {"stake_recomendado": 0.0, "porcentaje_banco": 0.0}

    fraccion_optima = ventaja / (cuota - 1)
    stake = banco * fraccion_optima * fraccion_kelly
    return {
        "stake_recomendado": round(stake, 2),
        "porcentaje_banco": round(stake / banco * 100, 2),
    }
