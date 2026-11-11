from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Union
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

if __package__:
    from .calibracion import metricas_calibracion
    from .api_football import (
        buscar_resultado_por_ids,
        obtener_resultado_por_fixture_id,
        obtener_resultados_partidos,
    )
    from .cartelera import obtener_cartelera_diaria
    from .historico_storage import read_history, write_history
    from .corners import analizar_corners
    from .goles import analizar_goles
    from .kelly import calcular_kelly
    from .tarjetas import analizar_tarjetas
    from .tiros import analizar_tiros
    from .valor import liquidar_picks_finalizados, seleccionar_picks_dia
else:
    from calibracion import metricas_calibracion
    from api_football import (
        buscar_resultado_por_ids,
        obtener_resultado_por_fixture_id,
        obtener_resultados_partidos,
    )
    from cartelera import obtener_cartelera_diaria
    from historico_storage import read_history, write_history
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


def _ruta_historico() -> Path:
    configurada = os.environ.get("EDGE_HISTORY_FILE")
    return Path(configurada).expanduser() if configurada else Path(__file__).resolve().parent / "historico_partidos.json"


def _fecha_local_partido(partido: Dict[str, object]) -> str:
    fecha_texto = str(partido.get("fecha", ""))
    try:
        fecha = datetime.fromisoformat(fecha_texto.replace("Z", "+00:00"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=ZoneInfo("UTC"))
        return fecha.astimezone(ZoneInfo("America/Bogota")).date().isoformat()
    except ValueError:
        return fecha_texto.split("T", 1)[0]


def _clave_partido(partido: Dict[str, object]) -> str:
    fixture_id = partido.get("fixture_id")
    if fixture_id is not None:
        return "fixture:{}".format(fixture_id)
    return "{}:{}:{}:{}".format(
        _fecha_local_partido(partido), partido.get("local_id", ""), partido.get("visitante_id", ""),
        partido.get("local", ""),
    )


def _guardar_historico(partidos: list) -> None:
    """Persist original predictions and update settlements as results arrive."""
    ruta = _ruta_historico()
    try:
        contenido, etag = read_history(ruta)
        archivados = contenido.get("partidos", [])
    except Exception as error:
        print("No se pudo leer el histórico persistente:", error)
        contenido, etag, archivados = {"partidos": []}, None, []
    if not isinstance(archivados, list):
        archivados = []
    por_clave = {_clave_partido(p): p for p in archivados if isinstance(p, dict)}
    cambio = False
    for partido in partidos:
        if not isinstance(partido, dict) or not isinstance(partido.get("picks_valor"), list):
            continue
        clave = _clave_partido(partido)
        anterior = por_clave.get(clave)
        actual = {
            "fixture_id": partido.get("fixture_id"),
            "fecha": partido.get("fecha"),
            "fecha_local": _fecha_local_partido(partido),
            "liga": partido.get("liga") or partido.get("liga_api") or "",
            "pais": partido.get("pais", ""),
            "local": partido.get("local", ""),
            "visitante": partido.get("visitante", ""),
            "estado": partido.get("estado", "FINALIZADO"),
            "es_finalizado": bool(partido.get("es_finalizado")),
            "marcador_final": partido.get("marcador_final"),
            "picks_valor": partido.get("picks_valor", []),
            "actualizado_en": datetime.now(ZoneInfo("UTC")).isoformat(),
        }
        if anterior:
            picks_anteriores = {
                p.get("tipo"): dict(p)
                for p in anterior.get("picks_valor", [])
                if isinstance(p, dict)
            }
            campos_liquidacion = (
                "resultado_pick", "total_real", "total_estimado", "resultado_fuente",
                "resultado_nota", "resultado_estimado", "marcador_final",
            )
            if partido.get("es_finalizado"):
                for pick_nuevo in actual["picks_valor"]:
                    tipo = pick_nuevo.get("tipo")
                    pick_previo = picks_anteriores.get(tipo)
                    if pick_previo is None:
                        picks_anteriores[tipo] = pick_nuevo
                        continue
                    previo_oficial = pick_previo.get("resultado_pick") and not pick_previo.get("resultado_estimado")
                    nuevo_oficial = pick_nuevo.get("resultado_pick") and not pick_nuevo.get("resultado_estimado")
                    if nuevo_oficial or not previo_oficial:
                        for campo in campos_liquidacion:
                            if campo in pick_nuevo:
                                pick_previo[campo] = pick_nuevo[campo]
            actual["picks_valor"] = list(picks_anteriores.values()) or actual["picks_valor"]
            # Refresh only live score/status; preserve pre-match names and picks.
            for campo in ("marcador_final", "estado", "fecha_local", "es_finalizado"):
                if actual.get(campo):
                    anterior[campo] = actual[campo]
            anterior["picks_valor"] = actual["picks_valor"]
            anterior["actualizado_en"] = actual["actualizado_en"]
            por_clave[clave] = anterior
        else:
            por_clave[clave] = actual
        cambio = True
    if not cambio:
        return
    try:
        write_history({"partidos": list(por_clave.values())}, ruta, expected_etag=etag)
    except Exception as error:
        print("No se pudo guardar el histórico persistente:", error)


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

        hoy = datetime.now(ZoneInfo("America/Bogota")).date()
        partidos = []
        cartelera_actualizada = False
        try:
            partidos = obtener_cartelera_diaria(hoy)
            cartelera_actualizada = bool(partidos)
        except Exception as error:
            print("Error cargando cartelera diaria; usando el archivo manual:", error)
        if not cartelera_actualizada:
            partidos = [partido for partido in datos["partidos"] if isinstance(partido, dict)]
            try:
                resultados_api = obtener_resultados_partidos(partidos)
                datos["error_api"] = False
            except Exception as error:
                print("Error API:", error)
                resultados_api = []
                datos["error_api"] = True
        else:
            resultados_api = []
            datos["error_api"] = False
            datos["total_partidos_api"] = len(partidos)
            # Keep the manually selected prior-day fixtures in the settlement flow
            # so they can be archived even after the live board advances to today.
            previos_manuales = [
                partido for partido in datos["partidos"]
                if isinstance(partido, dict)
                and _fecha_local_partido(partido) < hoy.isoformat()
                and _clave_partido(partido) not in {_clave_partido(p) for p in partidos}
            ]
            if previos_manuales:
                try:
                    resultados_api = obtener_resultados_partidos(previos_manuales)
                except Exception as error:
                    print("Error actualizando partidos previos seleccionados:", error)
                partidos.extend(previos_manuales)

        for partido in partidos:
            if cartelera_actualizada and "resultado_real" in partido:
                resultado = partido.get("resultado_real")
            else:
                resultado = buscar_resultado_por_ids(
                    partido.get("local_id"), partido.get("visitante_id"), resultados_api,
                )
            # The date scoreboard can lag behind a fixture in another
            # competition. Revalidate by ID when it is live, or when today's
            # kickoff has passed but the date feed still says it is pending.
            resultado_corto = str((resultado or {}).get("estado_corto", "")).upper()
            try:
                fecha_inicio = datetime.fromisoformat(
                    str(partido.get("fecha", "")).replace("Z", "+00:00")
                )
                if fecha_inicio.tzinfo is None:
                    fecha_inicio = fecha_inicio.replace(tzinfo=ZoneInfo("UTC"))
                minutos_desde_inicio = (
                    datetime.now(ZoneInfo("UTC")) - fecha_inicio
                ).total_seconds() / 60.0
                inicio_ya_paso = (
                    fecha_inicio <= datetime.now(ZoneInfo("UTC"))
                    and _fecha_local_partido(partido) == hoy.isoformat()
                )
            except ValueError:
                inicio_ya_paso = False
                minutos_desde_inicio = None
            estados_terminales = {"FT", "AET", "PEN", "CANC", "PST", "ABD", "AWD", "WO"}
            debe_revalidar = (
                resultado_corto in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
                or (inicio_ya_paso and resultado_corto not in estados_terminales)
            )
            if debe_revalidar:
                try:
                    resultado_actualizado = obtener_resultado_por_fixture_id(partido.get("fixture_id"))
                    if resultado_actualizado is not None:
                        resultado = resultado_actualizado
                        print(
                            "API-Football fixture refresh id={} status={} elapsed={}".format(
                                partido.get("fixture_id"),
                                resultado.get("estado_corto"),
                                resultado.get("minuto"),
                            )
                        )
                    else:
                        print(
                            "API-Football fixture refresh id={} sin respuesta; se conserva el estado anterior".format(
                                partido.get("fixture_id")
                            )
                        )
                except Exception as error:
                    print(
                        "Error revalidando fixture {} por ID: {}".format(
                            partido.get("fixture_id"), error
                        )
                    )
            # Some competitions can return a frozen live minute by fixture ID.
            # If the reported live state is over 150 minutes past kickoff,
            # cross-check the same fixture through both team/date endpoints;
            # these requests include the required season parameter.
            if (
                str((resultado or {}).get("estado_corto", "")).upper()
                in {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
                and minutos_desde_inicio is not None
                and minutos_desde_inicio >= 150
            ):
                try:
                    resultados_por_equipo = obtener_resultados_partidos([partido])
                    resultado_por_equipo = buscar_resultado_por_ids(
                        partido.get("local_id"), partido.get("visitante_id"), resultados_por_equipo,
                    )
                    estado_equipo = str(
                        (resultado_por_equipo or {}).get("estado_corto", "")
                    ).upper()
                    if estado_equipo in estados_terminales:
                        resultado = resultado_por_equipo
                    print(
                        "API-Football team/date cross-check fixture={} status={}".format(
                            partido.get("fixture_id"), estado_equipo or "sin coincidencia"
                        )
                    )
                except Exception as error:
                    print(
                        "Error API-Football team/date cross-check fixture={}: {}".format(
                            partido.get("fixture_id"), error
                        )
                    )
                estado_final_cruzado = str(
                    (resultado or {}).get("estado_corto", "")
                ).upper() in {"FT", "AET", "PEN"}
                if not estado_final_cruzado:
                    # Never present a frozen live clock as current. Keep the
                    # market unsettled until API-Football supplies a terminal
                    # status and official statistics.
                    resultado = dict(resultado or {})
                    resultado["estado_original_api"] = resultado.get("estado_corto")
                    resultado["estado"] = "pendiente"
                    resultado["estado_corto"] = "TBD"
                    resultado["estado_texto"] = "Esperando confirmación de API-Football"
                    resultado["minuto"] = None
                    resultado["marcador_local"] = None
                    resultado["marcador_visitante"] = None
                    resultado["estado_atrasado"] = True
                    print(
                        "API-Football estado atrasado fixture={}; no se muestra como EN VIVO".format(
                            partido.get("fixture_id")
                        )
                    )
            partido["resultado_real"] = resultado
            if resultado is not None:
                partido["datos_en_vivo"] = True
                partido["estado_api"] = resultado.get("estado_corto")
                if resultado.get("marcador_local") is not None:
                    partido["goles_local"] = resultado["marcador_local"]
                if resultado.get("marcador_visitante") is not None:
                    partido["goles_visitante"] = resultado["marcador_visitante"]

            fecha_partido = _fecha_local_partido(partido)
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

        try:
            historial_calibracion, _ = read_history(_ruta_historico())
        except Exception as error:
            print("No se pudo cargar histórico para calibrar probabilidades:", error)
            historial_calibracion = {"partidos": []}
        total_picks = seleccionar_picks_dia(partidos, historial_calibracion.get("partidos", []))
        datos["calibracion"] = {
            "muestras_verificadas_por_mercado": metricas_calibracion(historial_calibracion.get("partidos", [])),
            "mercados_con_calibracion_validada": sorted({
                str(pick.get("tipo"))
                for partido in partidos
                for pick in partido.get("picks_valor", [])
                if pick.get("calibracion_activa")
            }),
        }
        for partido in partidos:
            if partido.get("es_finalizado"):
                liquidar_picks_finalizados(partido, partido.get("resultado_real"))
        _guardar_historico(partidos)
        datos["partidos"] = partidos
        datos["picks_valor"] = [
            pick
            for partido in partidos
            for pick in partido.get("picks_valor", [])
            if not partido.get("es_finalizado")
        ]
        datos["picks_valor"].sort(
            key=lambda pick: pick["edge"] if pick.get("edge") is not None else -1.0,
            reverse=True,
        )
        datos["total_picks_valor"] = sum(1 for pick in datos["picks_valor"] if pick.get("tiene_valor"))
        datos["total_mercados_analizados"] = sum(len(partido.get("picks_valor", [])) for partido in partidos if not partido.get("es_finalizado"))
        datos["total_mercados_sin_valor"] = sum(1 for pick in datos["picks_valor"] if not pick.get("tiene_valor"))
        datos["total_mercados_confianza_baja"] = sum(1 for pick in datos["picks_valor"] if pick.get("confianza") == "Baja")
        datos["total_partidos_analizados"] = len(partidos)
        return datos
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"partidos": [], "picks_valor": [], "total_picks_valor": 0}


@app.get("/api/historico")
def obtener_historico() -> Dict[str, object]:
    ruta = _ruta_historico()
    try:
        payload, _ = read_history(ruta)
        partidos = payload.get("partidos", []) if isinstance(payload, dict) else []
    except Exception as error:
        print("No se pudo leer el histórico persistente:", error)
        partidos = []
    partidos = [p for p in partidos if isinstance(p, dict) and p.get("es_finalizado")]
    partidos.sort(key=lambda p: str(p.get("fecha_local", p.get("fecha", ""))), reverse=True)
    picks = [pick for partido in partidos for pick in partido.get("picks_valor", []) if isinstance(pick, dict)]
    liquidados_verificados = [
        p for p in picks
        if p.get("resultado_pick") in {"GANADO", "PERDIDO"} and not p.get("resultado_estimado")
    ]
    ganados = sum(1 for p in liquidados_verificados if p.get("resultado_pick") == "GANADO")
    return {
        "partidos": partidos,
        "resumen": {
            "partidos": len(partidos),
            "picks_verificados": len(liquidados_verificados),
            "ganados": ganados,
            "perdidos": len(liquidados_verificados) - ganados,
            "porcentaje_acierto": round(100 * ganados / len(liquidados_verificados), 1) if liquidados_verificados else None,
            "picks_estimados": sum(1 for p in picks if p.get("resultado_estimado") and p.get("resultado_pick") in {"GANADO", "PERDIDO"}),
        },
    }


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
