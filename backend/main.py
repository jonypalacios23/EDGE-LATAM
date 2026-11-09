from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api_espn import buscar_resultado_partido, obtener_resultados_partidos_hoy
from corners import analizar_corners
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


def liquidar_pronostico(resultado: Optional[Dict[str, object]], pronostico: str) -> Dict[str, object]:
    """Liquida el pronóstico 1X2 guardado cuando ESPN confirma el estado final."""
    pronostico_normalizado = str(pronostico or "").strip().casefold()
    if resultado is None:
        return {"estado": "PENDIENTE", "pronostico": pronostico_normalizado}

    estado = str(resultado.get("estado", "")).casefold()
    if estado in {"suspendido", "cancelado"}:
        return {
            "estado": "ANULADO / REEMBOLSO",
            "pronostico": pronostico_normalizado,
            "marcador_local": resultado.get("marcador_local"),
            "marcador_visitante": resultado.get("marcador_visitante"),
        }
    if estado != "finalizado":
        return {
            "estado": "PENDIENTE",
            "pronostico": pronostico_normalizado,
            "marcador_local": resultado.get("marcador_local"),
            "marcador_visitante": resultado.get("marcador_visitante"),
        }

    if pronostico_normalizado not in {"local", "empate", "visitante"}:
        return {"estado": "PRONÓSTICO NO CONFIGURADO", "pronostico": pronostico_normalizado}

    goles_local = resultado.get("marcador_local")
    goles_visitante = resultado.get("marcador_visitante")
    if goles_local is None or goles_visitante is None:
        return {"estado": "RESULTADO NO DISPONIBLE", "pronostico": pronostico_normalizado}
    goles_local = int(goles_local)
    goles_visitante = int(goles_visitante)
    if goles_local > goles_visitante:
        resultado_real = "local"
    elif goles_local < goles_visitante:
        resultado_real = "visitante"
    else:
        resultado_real = "empate"
    estado_liquidacion = "GANADO" if pronostico_normalizado == resultado_real else "PERDIDO"
    return {
        "estado": estado_liquidacion,
        "pronostico": pronostico_normalizado,
        "resultado_real": resultado_real,
        "marcador_local": goles_local,
        "marcador_visitante": goles_visitante,
    }


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
                    partido["liquidacion"] = liquidar_pronostico(
                        resultado_real,
                        str(partido.get("pronostico_resultado", "")),
                    )
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
