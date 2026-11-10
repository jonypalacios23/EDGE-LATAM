from __future__ import annotations

from math import exp, factorial
from typing import Dict, List, Optional, Tuple


EDGE_MINIMO = 0.08
STAKE_MINIMO = 0.01
STAKE_MAXIMO = 0.04
FRACCION_KELLY = 0.25
MAX_PICKS_PARTIDO = 2
MAX_PICKS_DIA = 5

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


def _probabilidad_mercado(partido: Dict[str, object], market: Dict[str, object]) -> Optional[Tuple[float, str, bool]]:
    tipo = market["tipo"]
    if tipo == "goles_over_2_5":
        frecuencia = _frecuencia_over25(partido)
        if frecuencia is None:
            return None
        return frecuencia[0], frecuencia[1], False
    if tipo == "doble_oportunidad_1x":
        local = partido.get("analisis_10anos_local", {})
        visitante = partido.get("analisis_10anos_vis", {})
        media_local = _numero(local, "prom_goles_casa_10anos", "prom_goles_ponderado")
        media_visitante = _numero(visitante, "prom_goles_fuera_10anos", "prom_goles_ponderado")
        if media_local is None or media_visitante is None:
            return None
        probabilidad = probabilidad_doble_oportunidad_1x(media_local, media_visitante)
        motivo = "Goles esperados local {:.2f} y visitante {:.2f} por histórico 10 años".format(media_local, media_visitante)
        return probabilidad, motivo, True

    media = _media_mercado(partido, str(market["clave"]))
    if media is None:
        return None
    probabilidad = probabilidad_poisson_over(media, float(market["linea"]))
    fuente = partido.get(str(market["clave"]), {})
    if isinstance(partido.get("analisis"), dict):
        fuente = partido["analisis"].get(str(market["clave"]), fuente)
    dato = fuente.get("dato") if isinstance(fuente, dict) else None
    motivo = "Media histórica {:.2f} {}; probabilidad estimada con Poisson".format(media, market["unidad"])
    if dato:
        motivo += " · {}".format(dato)
    return probabilidad, motivo, True


def calcular_picks_valor_partido(partido: Dict[str, object]) -> List[Dict[str, object]]:
    candidatos = []
    for market in MERCADOS:
        calculo = _probabilidad_mercado(partido, market)
        if calculo is None:
            continue
        probabilidad, motivo, probabilidad_estimada = calculo
        cuota = _cuota_partido(partido, market)
        cuota_estimada = cuota is None
        if cuota is None:
            cuota = CUOTAS_REFERENCIA[market["tipo"]]
        implicita = 1.0 / cuota
        edge = probabilidad - implicita
        if edge < EDGE_MINIMO:
            continue
        stake = (edge / (cuota - 1.0)) * FRACCION_KELLY
        stake_pct = min(STAKE_MAXIMO, max(STAKE_MINIMO, stake)) * 100.0
        fuente = partido.get(market["clave"], {})
        if isinstance(partido.get("analisis"), dict):
            fuente = partido["analisis"].get(market["clave"], fuente)
        confianza = fuente.get("confianza") if isinstance(fuente, dict) else None
        if not confianza and market["tipo"] == "doble_oportunidad_1x":
            prediccion = partido.get("prediccion_ia", {})
            confianza = prediccion.get("confianza") if isinstance(prediccion, dict) else None
        candidatos.append({
            "tipo": market["tipo"],
            "mercado": market["etiqueta"],
            "linea": market["linea"],
            "probabilidad_real": probabilidad,
            "probabilidad_real_pct": probabilidad * 100.0,
            "probabilidad_estimada": probabilidad_estimada,
            "probabilidad_implicita": implicita,
            "probabilidad_implicita_pct": implicita * 100.0,
            "edge": edge,
            "edge_pct": edge * 100.0,
            "cuota": cuota,
            "cuota_estimada": cuota_estimada,
            "stake_pct": stake_pct,
            "confianza": confianza or "Media",
            "motivo": motivo,
        })
    return sorted(candidatos, key=lambda pick: pick["edge"], reverse=True)[:MAX_PICKS_PARTIDO]


def seleccionar_picks_dia(partidos: List[Dict[str, object]]) -> int:
    candidatos = []
    for indice, partido in enumerate(partidos):
        for pick in calcular_picks_valor_partido(partido):
            candidatos.append((indice, pick))
    candidatos.sort(key=lambda item: item[1]["edge"], reverse=True)

    conteo_partido = {}
    cantidad = 0
    for partido in partidos:
        partido["picks_valor"] = []
    for indice, pick in candidatos:
        if cantidad >= MAX_PICKS_DIA:
            break
        if conteo_partido.get(indice, 0) >= MAX_PICKS_PARTIDO:
            continue
        partidos[indice]["picks_valor"].append(pick)
        conteo_partido[indice] = conteo_partido.get(indice, 0) + 1
        cantidad += 1
    for partido in partidos:
        partido["picks_valor"].sort(key=lambda pick: pick["edge"], reverse=True)
        if not partido["picks_valor"]:
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
        if tipo == "goles_over_2_5" and goles_local is not None and goles_visitante is not None:
            total = float(goles_local) + float(goles_visitante)
            pick["resultado_pick"] = "GANADO" if total > float(pick["linea"]) else "PERDIDO"
            pick["total_real"] = total
        elif tipo == "doble_oportunidad_1x" and goles_local is not None and goles_visitante is not None:
            pick["resultado_pick"] = "GANADO" if float(goles_local) >= float(goles_visitante) else "PERDIDO"
            pick["marcador_final"] = "{}-{}".format(goles_local, goles_visitante)
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
                pick["resultado_pick"] = "PENDIENTE - Esperando estadística oficial API-Football"
        pick["resultado_fuente"] = "API-Football"
