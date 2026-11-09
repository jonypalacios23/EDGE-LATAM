from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api_football import buscar_resultado_partido, obtener_partidos_primera_b_hoy
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


@app.get("/api/partidos")
@app.get("/partidos-hoy")
def obtener_partidos_hoy() -> Dict[str, object]:
    ruta_partidos = Path(__file__).resolve().parent / "partidos_hoy.json"
    try:
        with ruta_partidos.open("r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        if isinstance(datos, dict) and isinstance(datos.get("partidos"), list):
            try:
                resultados_api = obtener_partidos_primera_b_hoy()
            except Exception as error:
                print("Error API:", error)
                resultados_api = []
            for partido in datos["partidos"]:
                if isinstance(partido, dict):
                    resultado_real = buscar_resultado_partido(
                        str(partido.get("local", "")),
                        str(partido.get("visitante", "")),
                        resultados_api,
                    )
                    if resultados_api and resultado_real is None:
                        print(
                            "API-Football: sin coincidencia para {} vs {}".format(
                                partido.get("local", ""),
                                partido.get("visitante", ""),
                            )
                        )
                    partido["resultado_real"] = resultado_real
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
