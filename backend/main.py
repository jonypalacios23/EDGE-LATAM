from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Union
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

if __package__:
    from .api_football import buscar_resultado_por_ids, obtener_resultados_partidos
    from .corners import analizar_corners
    from .goles import analizar_goles
    from .kelly import calcular_kelly
    from .tarjetas import analizar_tarjetas
    from .tiros import analizar_tiros
    from .valor import liquidar_picks_finalizados, seleccionar_picks_dia
else:
    from api_football import buscar_resultado_por_ids, obtener_resultados_partidos
    from corners import analizar_corners
    from goles import analizar_goles
    from kelly import calcular_kelly
    from tarjetas import analizar_tarjetas
    from tiros import analizar_tiros
    from valor import liquidar_picks_finalizados, seleccionar_picks_dia

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
    """Liquida un mercado solo con estadísticas de API-Football."""
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
            texto = "Esperando estadística oficial API-Football"
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
        return {
            "estado": estado,
            "texto": texto,
            "total_real": total,
            "linea": linea,
            "tipo": tipo,
            "fuente": "API-Football",
        }

    if resultado is None:
        return salida("PENDIENTE")
    estado_partido = str(resultado.get("estado", "")).casefold()
    if estado_partido in {"suspendido", "cancelado"}:
        return salida("ANULADO / REEMBOLSO")
    if estado_partido != "finalizado":
        return salida("PENDIENTE")

    resultado_por_tipo = {
        "corners": "corners_total",
        "corner": "corners_total",
        "tarjetas": "tarjetas_total",
        "cards": "tarjetas_total",
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
    label = {"corners": "córners", "corner": "córners", "tarjetas": "tarjetas", "cards": "tarjetas", "tiros": "tiros a puerta", "tiros_a_puerta": "tiros a puerta", "shots_on_target": "tiros a puerta"}.get(tipo, nombre.casefold())
    if estado_apuesta == "ANULADO / REEMBOLSO":
        return salida(estado_apuesta, int(total_real))
    return salida(
        estado_apuesta,
        int(total_real),
        detalle="Fuente: API-Football - {} {} - Línea {} = {}".format(
            int(total_real), label, linea, estado_apuesta
        ),
    )


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
            error_api = False
            try:
                partidos_api = [partido for partido in datos["partidos"] if isinstance(partido, dict)]
                resultados_api = obtener_resultados_partidos(partidos_api)
                error_api = False
            except Exception as error:
                print("Error API:", error)
                resultados_api = []
                error_api = True
            for partido in datos["partidos"]:
                if isinstance(partido, dict):
                    resultado_real = buscar_resultado_por_ids(
                        partido.get("local_id"),
                        partido.get("visitante_id"),
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
                    partido["datos_en_vivo"] = resultado_real is not None
                    liquidaciones = {}
                    mercados = partido.get("mercados", {})
                    if isinstance(mercados, dict):
                        for clave_mercado, datos_mercado in mercados.items():
                            if isinstance(datos_mercado, dict):
                                liquidacion = liquidar_mercado(resultado_real, datos_mercado)
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


@app.get("/api/partidos")
def obtener_partidos_api() -> Dict[str, object]:
    """Serve today's match file enriched with value picks and final results."""
    ruta_partidos = Path(__file__).resolve().parent / "partidos_hoy.json"
    try:
        with ruta_partidos.open("r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        if not isinstance(datos, dict) or not isinstance(datos.get("partidos"), list):
            return {"partidos": [], "picks_valor": []}

        partidos = [partido for partido in datos["partidos"] if isinstance(partido, dict)]
        try:
            resultados_api = obtener_resultados_partidos(partidos)
            datos["error_api"] = False
        except Exception as error:
            print("Error API:", error)
            resultados_api = []
            datos["error_api"] = True

        hoy = datetime.now(ZoneInfo("America/Bogota")).date()
        for partido in partidos:
            resultado = buscar_resultado_por_ids(
                partido.get("local_id"),
                partido.get("visitante_id"),
                resultados_api,
            )
            partido["resultado_real"] = resultado
            if resultado is not None:
                partido["datos_en_vivo"] = True
                partido["estado_api"] = resultado.get("estado_corto")
                if resultado.get("marcador_local") is not None:
                    partido["goles_local"] = resultado["marcador_local"]
                if resultado.get("marcador_visitante") is not None:
                    partido["goles_visitante"] = resultado["marcador_visitante"]

            fecha_partido = str(partido.get("fecha", "")).split("T", 1)[0]
            try:
                fecha_vencida = datetime.strptime(fecha_partido, "%Y-%m-%d").date() < hoy
            except ValueError:
                fecha_vencida = False
            estado_api = str((resultado or {}).get("estado", "")).casefold()
            estado_api_corto = str((resultado or {}).get("estado_corto", "")).upper()
            estado_guardado = str(partido.get("estado", "")).upper()
            finalizado = (
                fecha_vencida
                or estado_api == "finalizado"
                or estado_api_corto in {"FT", "AET", "PEN"}
                or estado_guardado in {"FT", "AET", "PEN", "FINISHED", "FINALIZADO"}
            )
            partido["es_finalizado"] = finalizado
            if finalizado:
                partido["estado"] = "FINALIZADO"
                goles_local = partido.get("goles_local")
                goles_visitante = partido.get("goles_visitante")
                if goles_local is not None and goles_visitante is not None:
                    partido["marcador_final"] = "{}-{}".format(goles_local, goles_visitante)
                    pronostico = str(
                        partido.get("prediccion")
                        or (partido.get("prediccion_ia") or {}).get("mejor_apuesta", "")
                    ).casefold()
                    if "doble oportunidad 1x" in pronostico or pronostico.strip() == "1x":
                        partido["resultado_prediccion"] = "GANADO" if float(goles_local) >= float(goles_visitante) else "PERDIDO"
                    elif "gana local" in pronostico or "victoria local" in pronostico:
                        partido["resultado_prediccion"] = "GANADO" if float(goles_local) > float(goles_visitante) else "PERDIDO"
                    elif "gana visitante" in pronostico or "victoria visitante" in pronostico:
                        partido["resultado_prediccion"] = "GANADO" if float(goles_visitante) > float(goles_local) else "PERDIDO"
                    else:
                        partido["resultado_prediccion"] = "PENDIENTE"
            elif resultado is not None:
                partido["estado"] = resultado.get("estado_texto") or resultado.get("estado", "PENDIENTE")

        total_picks = seleccionar_picks_dia(partidos)
        for partido in partidos:
            if partido.get("es_finalizado"):
                liquidar_picks_finalizados(partido, partido.get("resultado_real"))
        datos["partidos"] = partidos
        datos["picks_valor"] = [
            pick
            for partido in partidos
            for pick in partido.get("picks_valor", [])
            if not partido.get("es_finalizado")
        ]
        datos["picks_valor"].sort(key=lambda pick: pick["edge"], reverse=True)
        datos["total_picks_valor"] = len(datos["picks_valor"])
        datos["total_partidos_analizados"] = len(partidos)
        return datos
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"partidos": [], "picks_valor": [], "total_picks_valor": 0}


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
