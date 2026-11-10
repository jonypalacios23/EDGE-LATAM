from __future__ import annotations

from math import exp, factorial
from typing import Dict, List, Optional, Tuple


EDGE_MINIMO = 0.08
STAKE_MINIMO = 0.01
STAKE_MAXIMO = 0.04
FRACCION_KELLY = 0.25

# Referencias orientativas cuando el archivo no trae una cuota observada.
CUOTAS_REFERENCIA = {
    "corners_over_8_5": 1.83,
    "goles_over_2_5": 2.10,
    "tarjetas_over_4_5": 1.90,
    "tiros_over_8_5": 1.85,
    "doble_oportunidad_1x": 1.30,
}

MERCADOS = (
    {"tipo": "corners_over_8_5", "etiqueta": "+8.5 Córners", "linea": 8.5, "clave": "corners", "unidad": "córners"},
    {"tipo": "goles_over_2_5", "etiqueta": "Over 2.5 Goles", "linea": 2.5, "clave": "goles", "unidad": "goles"},
    {"tipo": "tarjetas_over_4_5", "etiqueta": "Over 4.5 Tarjetas", "linea": 4.5, "clave": "tarjetas", "unidad": "tarjetas"},
    {"tipo": "tiros_over_8_5", "etiqueta": "Over 8.5 Tiros a Puerta", "linea": 8.5, "clave": "tiros_a_puerta", "unidad": "tiros a puerta"},
    {"tipo": "doble_oportunidad_1x", "etiqueta": "Doble Oportunidad 1X", "linea": None, "clave": "doble_oportunidad", "unidad": ""},
)

# Promedios base para ligas sin muestra propia; se sustituyen por datos del partido cuando existen.
PROMEDIOS_LIGA = {
    "primera a": {"corners": 9.2, "goles": 2.50, "tarjetas": 4.6, "tiros_a_puerta": 8.8, "over25": 0.46, "goles_local": 1.42, "goles_visitante": 1.08},
    "primera b": {"corners": 9.3, "goles": 2.40, "tarjetas": 5.0, "tiros_a_puerta": 8.5, "over25": 0.43, "goles_local": 1.38, "goles_visitante": 1.02},
    "jamaica": {"corners": 9.0, "goles": 2.80, "tarjetas": 3.8, "tiros_a_puerta": 8.5, "over25": 0.48, "goles_local": 1.55, "goles_visitante": 1.25},
    "default": {"corners": 9.2, "goles": 2.50, "tarjetas": 4.6, "tiros_a_puerta": 8.8, "over25": 0.45, "goles_local": 1.42, "goles_visitante": 1.08},
}


def _liga_key(partido: Dict[str, object]) -> str:
    liga = "{} {}".format(partido.get("liga", ""), partido.get("liga_api", "")).casefold()
    if "jamaica" in liga:
        return "jamaica"
    if "primera b" in liga or "categoría primera b" in liga or partido.get("league_id") == 240:
        return "primera b"
    if "primera a" in liga or partido.get("league_id") == 239:
        return "primera a"
    return "default"


def promedio_liga_mercado(partido: Dict[str, object], tipo: str) -> float:
    clave = {
        "corners_over_8_5": "corners",
        "goles_over_2_5": "goles",
        "tarjetas_over_4_5": "tarjetas",
        "tiros_over_8_5": "tiros_a_puerta",
        "doble_oportunidad_1x": "home_1x",
    }.get(tipo, "corners")
    liga = PROMEDIOS_LIGA[_liga_key(partido)]
    if clave == "home_1x":
        return probabilidad_doble_oportunidad_1x(liga["goles_local"], liga["goles_visitante"])
    return float(liga[clave])


def _perfiles(partido: Dict[str, object]) -> Tuple[Dict[str, object], Dict[str, object]]:
    local = partido.get("analisis_10anos_local", {})
    visitante = partido.get("analisis_10anos_vis", {})
    return (local if isinstance(local, dict) else {}, visitante if isinstance(visitante, dict) else {})


def _muestra(perfil: Dict[str, object]) -> int:
    valor = _numero(perfil, "total_partidos_10anos", "total_partidos", "partidos_historicos", "partidos")
    if valor is not None:
        return max(0, int(valor))
    años = _numero(perfil, "anios_historico", "años_historico", "years_of_data", "temporadas")
    return max(0, int(round((años or 0) * 25)))


def _completo(perfil: Dict[str, object]) -> bool:
    años = _numero(perfil, "anios_historico", "años_historico", "years_of_data", "temporadas") or 0
    return _muestra(perfil) >= 100 or años >= 5


def _datos_usados(partido: Dict[str, object]) -> Tuple[str, str, str, int]:
    local, visitante = _perfiles(partido)
    muestras = [_muestra(local), _muestra(visitante)]
    validas = [n for n in muestras if n >= 20]
    liga_nombre = "Primera B" if _liga_key(partido) == "primera b" else "Primera A" if _liga_key(partido) == "primera a" else "Jamaica" if _liga_key(partido) == "jamaica" else str(partido.get("liga") or "la liga")
    if _completo(local) and _completo(visitante):
        return "10 años completos", "Alta", "Datos: 10 años completos", min(muestras)
    if validas and all(n >= 20 for n in muestras):
        n = int(sum(muestras) / len(muestras))
        años = max(1, round(n / 25))
        badge = "Datos: {} años / {} partidos - Muestra parcial".format(años, n)
        return "{} años - {} partidos".format(años, n), "Media", badge, n
    rival = max(muestras)
    return "Promedio liga{}".format(" + rival" if rival >= 20 else ""), "Baja", "Datos: Sin histórico propio, usamos promedio liga {}".format(liga_nombre), rival


def _prob_liga(partido: Dict[str, object], market: Dict[str, object]) -> float:
    tipo = str(market["tipo"])
    liga = PROMEDIOS_LIGA[_liga_key(partido)]
    if tipo == "goles_over_2_5":
        return float(liga["over25"])
    if tipo == "doble_oportunidad_1x":
        return promedio_liga_mercado(partido, tipo)
    return probabilidad_poisson_over(float(liga[market["clave"]]), float(market["linea"]))


def probabilidad_poisson_over(media: float, linea: float) -> float:
    """Estima P(total > línea) con una distribución Poisson."""
    if media < 0:
        raise ValueError("La media histórica no puede ser negativa")
    ultimo_perdedor = int(linea)
    probabilidad_under_o_push = sum(
        exp(-media) * (media ** goles) / factorial(goles)
        for goles in range(ultimo_perdedor + 1)
    )
    return min(1.0, max(0.0, 1.0 - probabilidad_under_o_push))


def _poisson_probs(media: float, maximo: int = 20) -> List[float]:
    return [exp(-media) * (media ** goles) / factorial(goles) for goles in range(maximo + 1)]


def probabilidad_doble_oportunidad_1x(media_local: float, media_visitante: float) -> float:
    """Estima P(local gana o empata) a partir de goles esperados históricos."""
    local = _poisson_probs(max(0.0, media_local))
    visitante = _poisson_probs(max(0.0, media_visitante))
    return min(1.0, sum(
        p_local * p_visita
        for gl, p_local in enumerate(local)
        for gv, p_visita in enumerate(visitante)
        if gl >= gv
    ))


def _numero(datos: object, *claves: str) -> Optional[float]:
    if not isinstance(datos, dict):
        return None
    for clave in claves:
        valor = datos.get(clave)
        try:
            if valor is not None:
                return float(valor)
        except (TypeError, ValueError):
            continue
    return None


def _frecuencia_over25(partido: Dict[str, object]) -> Optional[Tuple[float, str]]:
    local = partido.get("analisis_10anos_local", {})
    visitante = partido.get("analisis_10anos_vis", {})
    porcentajes = []
    motivos = []
    for etiqueta, perfil in (("Local", local), ("Visitante", visitante)):
        if isinstance(perfil, dict) and perfil.get("over25_pct") is not None:
            porcentaje = float(perfil["over25_pct"])
            porcentajes.append(porcentaje / 100.0)
            motivos.append("{}: Over 2.5 {:.1f}% de {} partidos".format(
                etiqueta, porcentaje, perfil.get("total_partidos_10anos", "?")))
    if len(porcentajes) != 2:
        return None
    return sum(porcentajes) / len(porcentajes), " · ".join(motivos)


def _media_mercado(partido: Dict[str, object], clave: str) -> Optional[float]:
    aliases = {
        "corners": ("promedio_total_10anos", "total_corners", "promedio_total", "promedio"),
        "tarjetas": ("promedio_total_10anos", "total_tarjetas", "promedio_total", "promedio"),
        "tiros_a_puerta": ("promedio_total_10anos", "total_tiros_a_puerta", "promedio_total", "promedio"),
    }
    analisis = partido.get("analisis", {})
    media = _numero(analisis, "total_{}".format(clave), "{}_total_10anos".format(clave))
    if media is not None:
        return media
    fuente = partido.get(clave)
    if isinstance(analisis, dict) and isinstance(analisis.get(clave), dict):
        fuente = analisis[clave]
    return _numero(fuente, *aliases[clave])


def _cuota_partido(partido: Dict[str, object], market: Dict[str, object]) -> Optional[float]:
    tipo = str(market["tipo"])
    keys = {
        "corners_over_8_5": ("corners_over_8_5", "cuota_over_8_5_corners", "cuota_corners_8_5"),
        "goles_over_2_5": ("goles_over_2_5", "cuota_over_2_5", "cuota_goles_2_5"),
        "tarjetas_over_4_5": ("tarjetas_over_4_5", "cuota_over_4_5", "cuota_tarjetas_4_5"),
        "tiros_over_8_5": ("tiros_over_8_5", "cuota_over_8_5_tiros", "cuota_tiros_8_5"),
        "doble_oportunidad_1x": ("doble_oportunidad_1x", "cuota_1x", "1x"),
    }[tipo]
    for raiz in (partido.get("odds"), partido.get("cuotas"), partido.get("mercados")):
        if not isinstance(raiz, dict):
            continue
        for key in (tipo,) + keys:
            valor = raiz.get(key)
            if isinstance(valor, dict):
                valor = valor.get("cuota") or valor.get("odd")
            try:
                if valor is not None and float(valor) > 1:
                    return float(valor)
            except (TypeError, ValueError):
                pass
    return None


def _probabilidad_mercado(partido: Dict[str, object], market: Dict[str, object]) -> Tuple[float, str, bool]:
    tipo = market["tipo"]
    local, visitante = _perfiles(partido)
    n_local, n_visitante = _muestra(local), _muestra(visitante)
    datos_validos = [n for n in (n_local, n_visitante) if n >= 20]
    p_liga = _prob_liga(partido, market)
    if tipo == "goles_over_2_5":
        porcentajes = [float(p["over25_pct"]) / 100 for p, n in ((local, n_local), (visitante, n_visitante)) if n >= 20 and p.get("over25_pct") is not None]
        p_equipo = sum(porcentajes) / len(porcentajes) if porcentajes else p_liga
        motivo = "Frecuencia histórica Over 2.5: {:.1f}%".format(p_equipo * 100)
        estimada = False
    elif tipo == "doble_oportunidad_1x":
        media_local = _numero(local, "prom_goles_casa_10anos", "prom_goles_ponderado") or PROMEDIOS_LIGA[_liga_key(partido)]["goles_local"]
        media_visitante = _numero(visitante, "prom_goles_fuera_10anos", "prom_goles_ponderado") or PROMEDIOS_LIGA[_liga_key(partido)]["goles_visitante"]
        p_equipo = probabilidad_doble_oportunidad_1x(media_local, media_visitante)
        motivo = "Probabilidad 1X con goles esperados {:.2f}-{:.2f}".format(media_local, media_visitante)
        estimada = True
    else:
        media = _media_mercado(partido, str(market["clave"]))
        if media is None:
            media = float(PROMEDIOS_LIGA[_liga_key(partido)][market["clave"]])
        p_equipo = probabilidad_poisson_over(media, float(market["linea"]))
        fuente = partido.get(str(market["clave"]), {})
        if isinstance(partido.get("analisis"), dict):
            fuente = partido["analisis"].get(str(market["clave"]), fuente)
        dato = fuente.get("dato") if isinstance(fuente, dict) else None
        motivo = "Media base {:.2f} {}; probabilidad estimada con Poisson".format(media, market["unidad"])
        if dato:
            motivo += " · {}".format(dato)
        estimada = True

    # Histórico parcial: prior de liga con 30 partidos equivalentes.
    if n_local >= 20 and n_visitante >= 20 and not (_completo(local) and _completo(visitante)):
        n_equipo = (n_local + n_visitante) / 2
        probabilidad = (n_equipo * p_equipo + 30 * p_liga) / (n_equipo + 30)
        motivo += " · Shrinkage: {} partidos + prior de 30 de liga".format(int(n_equipo))
    # Si solo un equipo tiene muestra, su estimación pesa 70%; el prior de liga, 30%.
    elif datos_validos and (n_local < 20 or n_visitante < 20):
        probabilidad = 0.70 * p_equipo + 0.30 * p_liga
        motivo += " · Rival con histórico ponderado 70/30 frente al promedio de liga"
    elif datos_validos:
        probabilidad = p_equipo
    else:
        probabilidad = p_liga
        motivo = "Promedio de liga aplicado por falta de histórico propio. " + motivo
        estimada = True
    return min(1.0, max(0.0, probabilidad)), motivo, estimada


def calcular_picks_valor_partido(partido: Dict[str, object]) -> List[Dict[str, object]]:
    # DIFERENCIACIÓN EDGE-LATAM: SIEMPRE MOSTRAR TODO
    candidatos = []
    for market in MERCADOS:
        calculo = _probabilidad_mercado(partido, market)
        cuota = _cuota_partido(partido, market)
        cuota_estimada = cuota is None
        if cuota is None:
            cuota = CUOTAS_REFERENCIA[market["tipo"]]
        implicita = 1.0 / cuota
        probabilidad, motivo, probabilidad_estimada = calculo
        edge = probabilidad - implicita
        _, confianza, badge_datos, n_muestra = _datos_usados(partido)
        stake_pct = 0.0
        if edge >= EDGE_MINIMO:
            stake = (edge / (cuota - 1.0)) * FRACCION_KELLY
            stake_pct = min(STAKE_MAXIMO, max(STAKE_MINIMO, stake)) * 100.0
            if confianza == "Baja":
                stake_pct = min(1.0, stake_pct)
        tiene_valor = edge is not None and edge >= EDGE_MINIMO
        candidatos.append({
            "tipo": market["tipo"],
            "mercado": market["etiqueta"],
            "linea": market["linea"],
            "probabilidad_real": probabilidad,
            "probabilidad_real_pct": probabilidad * 100.0 if probabilidad is not None else None,
            "probabilidad_estimada": probabilidad_estimada,
            "probabilidad_implicita": implicita,
            "probabilidad_implicita_pct": implicita * 100.0,
            "edge": edge,
            "edge_pct": edge * 100.0 if edge is not None else None,
            "tiene_valor": tiene_valor,
            "estado_valor": "VALOR" if tiene_valor else "SIN VALOR",
            "cuota": cuota,
            "cuota_estimada": cuota_estimada,
            "stake_pct": stake_pct,
            "confianza": confianza or "Media",
            "datos_usados": _datos_usados(partido)[0],
            "badge_datos": badge_datos,
            "partidos_muestra": n_muestra,
            "motivo": motivo,
        })
    return sorted(candidatos, key=lambda pick: pick["edge"] if pick["edge"] is not None else -1.0, reverse=True)


def seleccionar_picks_dia(partidos: List[Dict[str, object]]) -> int:
    cantidad = 0
    for partido in partidos:
        partido["picks_valor"] = calcular_picks_valor_partido(partido)
        cantidad += sum(1 for pick in partido["picks_valor"] if pick["tiene_valor"])
        if not any(pick["tiene_valor"] for pick in partido["picks_valor"]):
            partido["mensaje"] = "Sin valor en este partido - la casa ya lo vio"
        else:
            partido.pop("mensaje", None)
    return cantidad


def liquidar_picks_finalizados(partido: Dict[str, object], resultado: Optional[Dict[str, object]] = None) -> None:
    """Liquida por marcador o estadística oficial, solo si el partido terminó."""
    picks = partido.get("picks_valor", [])
    if not isinstance(picks, list):
        return
    fuente = resultado or {}
    estado = str(fuente.get("estado", partido.get("estado", ""))).casefold()
    estados_finales = {"finalizado", "ft", "finished", "aet", "pen"}
    if estado not in estados_finales and not partido.get("es_finalizado"):
        return
    goles_local = fuente.get("marcador_local", partido.get("goles_local"))
    goles_visitante = fuente.get("marcador_visitante", partido.get("goles_visitante"))
    for pick in picks:
        tipo = pick.get("tipo")
        liquidacion_estimada = False
        if tipo == "goles_over_2_5" and goles_local is not None and goles_visitante is not None:
            total = float(goles_local) + float(goles_visitante)
            pick["resultado_pick"] = "GANADO" if total > float(pick["linea"]) else "PERDIDO"
            pick["total_real"] = total
        elif tipo == "doble_oportunidad_1x" and goles_local is not None and goles_visitante is not None:
            pick["resultado_pick"] = "GANADO" if float(goles_local) >= float(goles_visitante) else "PERDIDO"
            pick["marcador_final"] = "{}-{}".format(goles_local, goles_visitante)
        elif tipo == "doble_oportunidad_1x":
            probabilidad_1x = promedio_liga_mercado(partido, str(tipo))
            pick["resultado_pick"] = "GANADO" if probabilidad_1x >= 0.5 else "PERDIDO"
            pick["probabilidad_estimada_1x"] = probabilidad_1x
            liquidacion_estimada = True
        else:
            clave_stats = {
                "corners_over_8_5": "corners_total",
                "tarjetas_over_4_5": "tarjetas_total",
                "tiros_over_8_5": "tiros_a_puerta_total",
            }
            clave = clave_stats.get(str(tipo))
            if clave and fuente.get(clave) is not None:
                total = float(fuente[clave])
                pick["resultado_pick"] = "GANADO" if total > float(pick["linea"]) else "PERDIDO"
                pick["total_real"] = total
            else:
                total = promedio_liga_mercado(partido, str(tipo))
                pick["resultado_pick"] = "GANADO" if total > float(pick["linea"]) else "PERDIDO"
                pick["total_estimado"] = total
                liquidacion_estimada = True
        pick["resultado_fuente"] = "Promedio liga (estimado)" if liquidacion_estimada else "API-Football"
        if liquidacion_estimada:
            pick["resultado_nota"] = "Liquidado con datos estimados - Confianza Baja"
