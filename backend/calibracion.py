from __future__ import annotations

from datetime import date, datetime, timezone
from math import exp
from typing import Dict, List, Optional, Tuple


MIN_MUESTRAS = 100
MIN_ENTRENAMIENTO = 50
FUERZA_PRIOR = 30.0
ANCHO_BANDA = 0.08
VIDA_MEDIA_DIAS = 730.0


def _fecha(partido: Dict[str, object]) -> Optional[date]:
    texto = str(partido.get("fecha_local") or partido.get("fecha") or "")
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _observaciones(historial: object, mercado: str) -> List[Tuple[float, int, Optional[date]]]:
    if not isinstance(historial, list):
        return []
    observaciones = []
    for partido in historial:
        if not isinstance(partido, dict) or not partido.get("es_finalizado"):
            continue
        picks = partido.get("picks_valor", [])
        if not isinstance(picks, list):
            continue
        for pick in picks:
            if not isinstance(pick, dict) or pick.get("tipo") != mercado:
                continue
            if pick.get("resultado_estimado") or pick.get("resultado_pick") not in {"GANADO", "PERDIDO"}:
                continue
            try:
                probabilidad = float(pick.get("probabilidad_base", pick.get("probabilidad_real")))
            except (TypeError, ValueError):
                continue
            if not 0.0 < probabilidad < 1.0:
                continue
            observaciones.append((probabilidad, int(pick["resultado_pick"] == "GANADO"), _fecha(partido)))
    return observaciones


def _posterior(probabilidad: float, observaciones: List[Tuple[float, int, Optional[date]]], fecha: date) -> float:
    suma_pesos = 0.0
    suma_aciertos = 0.0
    for estimacion, acierto, fecha_observacion in observaciones:
        distancia = (estimacion - probabilidad) / ANCHO_BANDA
        peso_probabilidad = exp(-0.5 * distancia * distancia)
        edad_dias = max(0, (fecha - fecha_observacion).days) if fecha_observacion else 0
        peso_recencia = 0.5 ** (edad_dias / VIDA_MEDIA_DIAS)
        peso = peso_probabilidad * peso_recencia
        suma_pesos += peso
        suma_aciertos += peso * acierto
    if suma_pesos < 5.0:
        return probabilidad
    return min(1.0, max(0.0, (FUERZA_PRIOR * probabilidad + suma_aciertos) / (FUERZA_PRIOR + suma_pesos)))


def calibrar_probabilidad(
    probabilidad_base: float,
    mercado: str,
    historial: object,
    fecha_referencia: Optional[date] = None,
) -> Tuple[float, int, bool]:
    """Shrink raw market estimates toward verified, recent historical hit rates.

    With fewer than 50 verified outcomes this deliberately returns the raw estimate;
    a smaller sample is too easy to overfit.
    """
    p = min(1.0, max(0.0, float(probabilidad_base)))
    hoy = fecha_referencia or datetime.now(timezone.utc).date()
    muestra = [item for item in _observaciones(historial, mercado) if item[2] is None or item[2] < hoy]
    if len(muestra) < MIN_MUESTRAS:
        return p, len(muestra), False
    muestra.sort(key=lambda item: item[2] or date.min)
    corte = max(MIN_ENTRENAMIENTO, int(len(muestra) * 0.75))
    entrenamiento, evaluacion = muestra[:corte], muestra[corte:]
    if len(entrenamiento) < MIN_ENTRENAMIENTO or len(evaluacion) < 20:
        return p, len(muestra), False
    brier_base = 0.0
    brier_calibrada = 0.0
    for p_observado, acierto, fecha in evaluacion:
        referencia = fecha or hoy
        p_ajustada = _posterior(p_observado, [dato for dato in entrenamiento if dato[2] is None or dato[2] < referencia], referencia)
        brier_base += (p_observado - acierto) ** 2
        brier_calibrada += (p_ajustada - acierto) ** 2
    if brier_calibrada >= brier_base * 0.995:
        return p, len(muestra), False
    return _posterior(p, muestra, hoy), len(muestra), True


def metricas_calibracion(historial: object) -> Dict[str, int]:
    tipos = {"corners_over_8_5", "goles_over_2_5", "tarjetas_over_4_5", "tiros_over_8_5", "doble_oportunidad_1x"}
    return {tipo: len(_observaciones(historial, tipo)) for tipo in tipos}
