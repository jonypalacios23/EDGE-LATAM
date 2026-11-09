from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api_espn import buscar_resultado_partido, obtener_resultados_partidos_hoy
from corners import analizar_corners
from google_stats import buscar_estadistica_google
from goles import analizar_goles
from kelly import calcular_kelly
from tarjetas import analizar_tarjetas
from tiros import analizar_tiros

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def liquidar_mercado(
    resultado: Optional[Dict[str, object]],
    mercado: Dict[str, object],
) -> Dict[str, object]:
    """Liquida un mercado contra su estadística real y la línea guardada."""
    tipo = str(mercado.get("tipo", "")).strip().casefold()
    direccion = str(mercado.get("direccion", "mas")).strip().casefold()
    linea = mercado.get("linea")
    nombre = {
        "corners": "Córners",
        "corner": "Córners",
        "tarjetas": "Tarjetas",
        "cards": "Tarjetas",
        "goles": "Goles",
        "goals": "Goles",
        "tiros": "Tiros a puerta",
        "tiros_a_puerta": "Tiros a puerta",
        "shots_on_target": "Tiros a puerta",
    }.get(tipo, tipo.title() or "Mercado")

    def salida(estado: str, total: Optional[int] = None, detalle: Optional[str] = None) -> Dict[str, object]:
        if estado == "ANULADO / REEMBOLSO":
            if resultado and str(resultado.get("estado", "")).casefold() in {"suspendido", "cancelado"}:
                texto = "Partido suspendido o cancelado - ANULADO / REEMBOLSO"
            else:
                texto = "Finalizado - {} reales: {} - Línea: {} = ANULADO / REEMBOLSO".format(nombre, total, linea)
        elif estado == "PENDIENTE" and resultado and resultado.get("estado") == "finalizado":
            texto = "PENDIENTE - Buscando en Google..."
        elif estado == "PENDIENTE":
            texto = "PENDIENTE"
        elif estado == "GANADO" or estado == "PERDIDO":
            texto = detalle or "Finalizado - {} reales: {} - Línea: {} {} = {}".format(
                nombre,
                total,
                "Más de" if direccion in {"mas", "más", "over"} else "Menos de" if direccion in {"menos", "under"} else "",
                linea,
                estado,
            )
        else:
            texto = detalle or estado
        return {"estado": estado, "texto": texto, "total_real": total, "linea": linea, "tipo": tipo}

    if resultado is None:
        return salida("PENDIENTE")
    estado_partido = str(resultado.get("estado", "")).casefold()
    if estado_partido in {"suspendido", "cancelado"}:
        return salida("ANULADO / REEMBOLSO")
    if estado_partido != "finalizado":
        return salida("PENDIENTE")

    if tipo in {"ganador", "1x2"}:
        pronostico = str(mercado.get("pronostico", "")).strip().casefold()
        local = resultado.get("marcador_local")
        visitante = resultado.get("marcador_visitante")
        if local is None or visitante is None or pronostico not in {"local", "empate", "visitante"}:
            return salida("PENDIENTE")
        real = "local" if local > visitante else "visitante" if local < visitante else "empate"
        estado_apuesta = "GANADO" if real == pronostico else "PERDIDO"
        return salida(
            estado_apuesta,
            detalle="Finalizado - Resultado real: {} - Pronóstico: {} = {}".format(real, pronostico, estado_apuesta),
        )
    if tipo in {"ambos_marcan", "both_teams_to_score", "btts"}:
        local = resultado.get("marcador_local")
        visitante = resultado.get("marcador_visitante")
        if local is None or visitante is None:
            return salida("PENDIENTE")
        pronostico = str(mercado.get("pronostico", "si")).strip().casefold()
        ambos = int(local) > 0 and int(visitante) > 0
        acertado = ambos if pronostico in {"si", "yes", "ambos"} else not ambos
        estado_apuesta = "GANADO" if acertado else "PERDIDO"
        return salida(
            estado_apuesta,
            detalle="Finalizado - Ambos marcan: {} - Pronóstico: {} = {}".format("Sí" if ambos else "No", pronostico, estado_apuesta),
        )

    resultado_por_tipo = {
        "corners": "corners_total",
        "corner": "corners_total",
        "tarjetas": "tarjetas_total",
        "cards": "tarjetas_total",
        "goles": "goles_total",
        "goals": "goles_total",
        "tiros": "tiros_a_puerta_total",
        "tiros_a_puerta": "tiros_a_puerta_total",
        "shots_on_target": "tiros_a_puerta_total",
    }
    clave = resultado_por_tipo.get(tipo)
    total = resultado.get(clave) if clave else None
    if total is None or linea is None:
        return salida("PENDIENTE")
    try:
        total_real = float(total)
        linea_real = float(linea)
    except (TypeError, ValueError):
        return salida("PENDIENTE")

    if direccion in {"mas", "over", "más"}:
        estado_apuesta = "GANADO" if total_real > linea_real else "PERDIDO" if total_real < linea_real else "ANULADO / REEMBOLSO"
    elif direccion in {"menos", "under"}:
        estado_apuesta = "GANADO" if total_real < linea_real else "PERDIDO" if total_real > linea_real else "ANULADO / REEMBOLSO"
    else:
        return salida("PENDIENTE", detalle="Tipo de línea no reconocido")
    if estado_apuesta == "ANULADO / REEMBOLSO":
        return salida(estado_apuesta, int(total_real))
    return salida(estado_apuesta, int(total_real))


@app.get("/api/partidos")
@app.get("/partidos-hoy")
def obtener_partidos_hoy(
    local: Optional[str] = None,
    visitante: Optional[str] = None,
) -> Dict[str, object]:
    ruta_partidos = Path(__file__).resolve().parent / "partidos_hoy.json"
    try:
        with ruta_partidos.open("r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        if isinstance(datos, dict) and isinstance(datos.get("partidos"), list):
            if local and visitante:
                datos["partidos"] = [
                    partido
                    for partido in datos["partidos"]
                    if isinstance(partido, dict)
                    and str(partido.get("local", "")).casefold() == local.casefold()
                    and str(partido.get("visitante", "")).casefold() == visitante.casefold()
                ]
            pares_equipos = [
                (
                    str(partido.get("local", "")),
                    str(partido.get("visitante", "")),
                    str(partido.get("liga", "")) or None,
                )
                for partido in datos["partidos"]
                if isinstance(partido, dict)
            ]
            error_api = False
            try:
                resultados_api = obtener_resultados_partidos_hoy(pares_equipos)
                error_api = False
            except Exception as error:
                print("Error API:", error)
                resultados_api = []
                error_api = True
            for partido in datos["partidos"]:
                if isinstance(partido, dict):
                    resultado_real = buscar_resultado_partido(
                        str(partido.get("local", "")),
                        str(partido.get("visitante", "")),
                        resultados_api,
                    )
                    if resultados_api and resultado_real is None:
                        print(
                            "ESPN: sin coincidencia para {} vs {}".format(
                                partido.get("local", ""),
                                partido.get("visitante", ""),
                            )
                        )
                    partido["resultado_real"] = resultado_real
                    partido["datos_en_vivo"] = resultado_real is not None
                    liquidaciones = {}
                    mercados = partido.get("mercados", {})
                    if isinstance(mercados, dict):
                        for clave_mercado, datos_mercado in mercados.items():
                            if isinstance(datos_mercado, dict):
                                liquidacion = liquidar_mercado(resultado_real, datos_mercado)
                                tipo = str(datos_mercado.get("tipo", "")).casefold()
                                if resultado_real and resultado_real.get("estado") == "finalizado" and tipo in {
                                    "corners", "corner", "tarjetas", "cards", "goles", "goals"
                                }:
                                    dato_google = buscar_estadistica_google(partido, datos_mercado)
                                    if dato_google is None:
                                        liquidacion = {
                                            "estado": "PENDIENTE",
                                            "texto": "PENDIENTE - Buscando en Google...",
                                            "total_real": None,
                                            "linea": datos_mercado.get("linea"),
                                            "tipo": tipo,
                                        }
                                    else:
                                        clave_resultado = {
                                            "corners": "corners_total",
                                            "corner": "corners_total",
                                            "tarjetas": "tarjetas_total",
                                            "cards": "tarjetas_total",
                                            "goles": "goles_total",
                                            "goals": "goles_total",
                                        }[tipo]
                                        resultado_google = dict(resultado_real)
                                        resultado_google[clave_resultado] = dato_google["total"]
                                        liquidacion = liquidar_mercado(resultado_google, datos_mercado)
                                        nombre = {
                                            "corners": "córners", "corner": "córners",
                                            "tarjetas": "tarjetas", "cards": "tarjetas",
                                            "goles": "goles", "goals": "goles",
                                        }[tipo]
                                        liquidacion["texto"] = "{}: {} {} - Línea: {} = {}".format(
                                            dato_google["fuente"], dato_google["total"], nombre,
                                            datos_mercado.get("linea"), liquidacion["estado"]
                                        )
                                        liquidacion["fuente"] = dato_google["fuente"]
                                        liquidacion["fuente_url"] = dato_google["fuente_url"]
                                        liquidacion["fuente_nombre"] = dato_google["fuente_nombre"]
                                liquidaciones[clave_mercado] = liquidacion
                    partido["liquidaciones"] = liquidaciones
            datos["error_api"] = error_api
            datos["tiene_datos_en_vivo"] = any(
                isinstance(partido, dict) and partido.get("datos_en_vivo")
                for partido in datos["partidos"]
            )
            return datos
    except (OSError, UnicodeError, json.JSONDecodeError):
        pass
    return {"partidos": []}


class AnalisisCornersRequest(BaseModel):
    promedio_local: float = Field(ge=0)
    promedio_visitante: float = Field(ge=0)
    cuota_over_9_5: float = Field(gt=1)


class AnalisisGolesRequest(BaseModel):
    promedio_local_goles: float = Field(ge=0)
    promedio_visitante_goles: float = Field(ge=0)
    cuota_over_2_5: float = Field(gt=1)


class AnalisisTarjetasRequest(BaseModel):
    promedio_local_tarjetas: float = Field(ge=0)
    promedio_visitante_tarjetas: float = Field(ge=0)
    cuota_over_4_5: float = Field(gt=1)


class AnalisisTirosRequest(BaseModel):
    promedio_local_tiros: float = Field(ge=0)
    promedio_visitante_tiros: float = Field(ge=0)
    cuota_over_8_5: float = Field(gt=1)


class CalcularKellyRequest(BaseModel):
    probabilidad: float = Field(ge=0, le=1)
    cuota: float = Field(gt=1)
    banco: float = Field(ge=0)
    fraccion_kelly: float = Field(default=0.25, ge=0, le=1)
    recomendacion: str = ""


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "project": "EDGE-LATAM"}


@app.post("/analizar-corners")
def analizar_corners_endpoint(request: AnalisisCornersRequest) -> Dict[str, Union[float, str]]:
    try:
        return analizar_corners(
            request.promedio_local,
            request.promedio_visitante,
            request.cuota_over_9_5,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/analizar-goles")
def analizar_goles_endpoint(request: AnalisisGolesRequest) -> Dict[str, Union[float, str]]:
    try:
        return analizar_goles(
            request.promedio_local_goles,
            request.promedio_visitante_goles,
            request.cuota_over_2_5,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/analizar-tarjetas")
def analizar_tarjetas_endpoint(request: AnalisisTarjetasRequest) -> Dict[str, Union[float, str]]:
    try:
        return analizar_tarjetas(
            request.promedio_local_tarjetas,
            request.promedio_visitante_tarjetas,
            request.cuota_over_4_5,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/analizar-tiros")
def analizar_tiros_endpoint(request: AnalisisTirosRequest) -> Dict[str, Union[float, str]]:
    try:
        return analizar_tiros(
            request.promedio_local_tiros,
            request.promedio_visitante_tiros,
            request.cuota_over_8_5,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/calcular-kelly")
def calcular_kelly_endpoint(request: CalcularKellyRequest) -> Dict[str, float]:
    if request.recomendacion == "NO HAY VALOR":
        return {"stake_recomendado": 0.0, "porcentaje_banco": 0.0}
    try:
        return calcular_kelly(
            request.probabilidad,
            request.cuota,
            request.banco,
            request.fraccion_kelly,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
