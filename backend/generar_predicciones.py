import json, pathlib
p = pathlib.Path("backend/partidos_hoy.json")
d = json.loads(p.read_text(encoding="utf-8"))

# REGLAS ESTIPULADAS - La IA solo predice si tiene datos reales
# Si no tiene datos, dice "Sin datos - No apostar", nunca inventa
for x in d.get("partidos", []):
    # Aqui el backend debe llenar estos campos desde API-Football por fixture_id
    # Por ahora los dejamos en 0 para que la IA no invente
    goles_local = x.get("prom_goles_local", 0)
    goles_vis = x.get("prom_goles_vis", 0)
    corners = x.get("prom_corners", 0)

    if goles_local == 0 and goles_vis == 0:
        x["prediccion_ia"] = {
            "mejor_apuesta": "Sin datos - No apostar",
            "confianza": "Nula",
            "motivo": "Sin estadisticas de API-Football por fixture_id. No se puede predecir sin inventar.",
            "mercados": {
                "goles": "Faltan datos",
                "corners": "Faltan datos",
                "tarjetas": "Faltan datos"
            }
        }
    else:
        total_goles = goles_local + goles_vis
        if total_goles >= 2.6:
            apuesta = "Mas de 2.5 goles"
            conf = "Alta"
        elif total_goles <= 1.8:
            apuesta = "Menos de 2.5 goles"
            conf = "Media"
        else:
            apuesta = "Ambos marcan - Si"
            conf = "Media"
        x["prediccion_ia"] = {"mejor_apuesta": apuesta, "confianza": conf, "motivo": f"Promedio combinado {total_goles:.2f} goles"}

p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Predicciones generadas con regla: sin datos = no apostar, nunca inventar")
for x in d["partidos"]:
    print(f" - {x['local']} vs {x['visitante']} -> {x['prediccion_ia']['mejor_apuesta']}")
