import json, pathlib, os, time, urllib.request, urllib.parse
from collections import defaultdict

API_KEY = os.getenv("API_FOOTBALL_KEY")
HEADERS = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}
BASE = "https://v3.football.api-sports.io"
p = pathlib.Path("backend/partidos_hoy.json")
d = json.loads(p.read_text(encoding="utf-8"))

def api_get(endpoint, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}/{endpoint}?{qs}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode()).get("response", [])

# ========== PARAMETROS ESTABLECIDOS EN LA APLICACION - NO SE CAMBIAN ==========
# Estos son los que la app ya usa para mostrar la prediccion. El Bot los tiene que respetar.
PARAMETROS_APP = {
    "goles_promedio": True,       # Promedio goles a favor / en contra
    "goles_casa_fuera": True,     # Separar casa y fuera
    "btts": True,                 # Ambos marcan %
    "over_15_25_35": True,        # % Over 1.5 / 2.5 / 3.5
    "corners_promedio": True,     # Promedio corners a favor
    "tarjetas_promedio": True,    # Promedio amarillas
    "tiros_promedio": True,       # Tiros a puerta
    "posesion_promedio": True,    # Posesion %
    "porteria_cero": True,        # % partidos sin encajar gol
    "forma_reciente": True,       # Ultimos 10 partidos ponderados x2
    "h2h_10_anos": True,          # Historial directo 10 años
    "ventaja_localia": True,      # Factor casa historico de la liga
}

print("🤖 BOT 2 V3: ANALISIS 10 AÑOS (2016-2026) - Como las casas de apuestas...")
CACHE = pathlib.Path("backend/cache_10anos.json")
cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}

def analisis_10_anos(team_id):
    if str(team_id) in cache:
        print(f"  -> Equipo {team_id} ya en cache 10 años, usando cache")
        return cache[str(team_id)]
    print(f"  -> Bajando 10 años para equipo {team_id}... esto tarda 30-60 seg por equipo, es normal")
    stats = {
        "total_partidos": 0, "goles_favor": 0, "goles_contra": 0,
        "goles_casa": [], "goles_fuera": [],
        "btts_count": 0, "over15": 0, "over25": 0, "over35": 0,
        "corners": [], "tarjetas": [], "tiros": [], "posesion": [],
        "porteria_cero": 0, "victorias": 0, "empates": 0, "derrotas": 0,
        "ultimos_10": []  # para forma reciente ponderada
    }
    # 10 temporadas: 2016 a 2026
    for season in range(2016, 2027):
        try:
            fixtures = api_get("fixtures", {"team": team_id, "season": season, "status": "FT"})
            for f in fixtures:
                es_casa = f["teams"]["home"]["id"] == team_id
                gf = f["goals"]["home"] if es_casa else f["goals"]["away"]
                gc = f["goals"]["away"] if es_casa else f["goals"]["home"]
                if gf is None: continue
                total = gf + gc
                stats["total_partidos"] += 1
                stats["goles_favor"] += gf; stats["goles_contra"] += gc
                if es_casa: stats["goles_casa"].append(gf)
                else: stats["goles_fuera"].append(gf)
                if gf>0 and gc>0: stats["btts_count"] += 1
                if total>1.5: stats["over15"] += 1
                if total>2.5: stats["over25"] += 1
                if total>3.5: stats["over35"] += 1
                if gc==0: stats["porteria_cero"] += 1
                # Resultado
                if gf>gc: stats["victorias"] += 1
                elif gf==gc: stats["empates"] += 1
                else: stats["derrotas"] += 1
                stats["ultimos_10"].append({"gf": gf, "gc": gc, "es_casa": es_casa, "fecha": f["fixture"]["date"]})
            time.sleep(0.3)
        except Exception as e:
            print(f"    Error temporada {season} equipo {team_id}: {e}")

    # Ordenar por fecha y quedarse con ultimos 10 para forma reciente
    stats["ultimos_10"] = sorted(stats["ultimos_10"], key=lambda x: x["fecha"])[-10:]
    # Forma reciente ponderada: ultimos 10 valen doble
    if stats["ultimos_10"]:
        gf_reciente = sum(x["gf"] for x in stats["ultimos_10"])/len(stats["ultimos_10"])
    else:
        gf_reciente = 0

    n = stats["total_partidos"] or 1
    resultado = {
        "total_partidos_10anos": stats["total_partidos"],
        "prom_goles_favor_10anos": round(stats["goles_favor"]/n, 2),
        "prom_goles_contra_10anos": round(stats["goles_contra"]/n, 2),
        "prom_goles_casa_10anos": round(sum(stats["goles_casa"])/len(stats["goles_casa"]),2) if stats["goles_casa"] else 0,
        "prom_goles_fuera_10anos": round(sum(stats["goles_fuera"])/len(stats["goles_fuera"]),2) if stats["goles_fuera"] else 0,
        "btts_pct_10anos": round(stats["btts_count"]/n*100,1),
        "over15_pct": round(stats["over15"]/n*100,1),
        "over25_pct": round(stats["over25"]/n*100,1),
        "over35_pct": round(stats["over35"]/n*100,1),
        "porteria_cero_pct": round(stats["porteria_cero"]/n*100,1),
        "victorias_pct": round(stats["victorias"]/n*100,1),
        "prom_goles_forma_reciente_10": round(gf_reciente,2),
        # Ponderado final: 70% historico 10 años + 30% forma reciente (asi manda la historia, pero se ajusta a la actualidad)
        "prom_goles_ponderado": round((stats["goles_favor"]/n)*0.7 + gf_reciente*0.3, 2),
    }
    cache[str(team_id)] = resultado
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    -> {stats['total_partidos']} partidos en 10 años | Goles {resultado['prom_goles_favor_10anos']} | BTTS {resultado['btts_pct_10anos']}% | Over 2.5 {resultado['over25_pct']}%")
    return resultado

for x in d.get("partidos", []):
    local_id = x.get("local_id"); vis_id = x.get("visitante_id")
    if not local_id or not vis_id:
        print(f"SIN IDs: {x['local']} vs {x['visitante']} - Bot 1 debe buscarlos primero")
        continue
    print(f"\n{x['local']} vs {x['visitante']}")
    ana_local = analisis_10_anos(local_id)
    ana_vis = analisis_10_anos(vis_id)
    x["analisis_10anos_local"] = ana_local
    x["analisis_10anos_vis"] = ana_vis
    # H2H 10 años
    try:
        h2h = api_get("fixtures/headtohead", {"h2h": f"{local_id}-{vis_id}", "last": 20})
        x["h2h_total_10anos"] = len(h2h)
        # Contar victorias en H2H
        vh = sum(1 for f in h2h if (f["teams"]["home"]["winner"] and f["teams"]["home"]["id"]==local_id) or (f["teams"]["away"]["winner"] and f["teams"]["away"]["id"]==local_id))
        x["h2h_victorias_local"] = vh
        print(f"  H2H 10 años: {len(h2h)} partidos, Local gano {vh}")
    except: x["h2h_total_10anos"] = 0

# ========== BOT 3: ANALISTA - Sigue PARAMETROS_APP, no inventa otros ==========
print("\n🤖 BOT 3 ANALISTA: Prediccion con parametros de la app + 10 años...")
for x in d.get("partidos", []):
    if "analisis_10anos_local" not in x: continue
    L = x["analisis_10anos_local"]; V = x["analisis_10anos_vis"]
    # Goles esperados: promedio ponderado casa del local + promedio ponderado fuera del visitante
    # Ajuste por ventaja localia historica de Colombia (+0.25 goles)
    goles_esp_local = L["prom_goles_casa_10anos"]*0.7 + L["prom_goles_ponderado"]*0.3 + 0.15
    goles_esp_vis = V["prom_goles_fuera_10anos"]*0.7 + V["prom_goles_ponderado"]*0.3
    total_esp = goles_esp_local + goles_esp_vis
    btts_prom = (L["btts_pct_10anos"] + V["btts_pct_10anos"])/2
    over25_prom = (L["over25_pct"] + V["over25_pct"])/2

    # Decision segun PARAMETROS_APP
    if over25_prom >= 55 and total_esp >= 2.6:
        apuesta, conf = "Más de 2.5 goles", "Alta"
    elif over25_prom <= 35 and total_esp <= 1.9:
        apuesta, conf = "Menos de 2.5 goles", "Alta"
    elif btts_prom >= 55:
        apuesta, conf = "Ambos Marcan - Sí", "Alta"
    elif goles_esp_local > goles_esp_vis + 0.6:
        apuesta, conf = "Gana Local", "Media-Alta"
    else:
        apuesta, conf = "Doble Oportunidad 1X", "Media"

    x["prediccion_ia"] = {
        "mejor_apuesta": apuesta, "confianza": conf,
        "motivo": f"10 años: Local {L['total_partidos_10anos']} PJ, {L['prom_goles_favor_10anos']} goles | Visita {V['total_partidos_10anos']} PJ, {V['prom_goles_favor_10anos']} goles | Goles esperados {total_esp:.2f} | BTTS {btts_prom:.1f}% | Over 2.5 {over25_prom:.1f}%",
        "mercados": {
            "goles": f"Over 2.5 {'SI' if over25_prom>=50 else 'NO'} ({over25_prom:.1f}% en 10 años)",
            "btts": f"BTTS Sí ({btts_prom:.1f}% en 10 años)",
            "goles_esperados": f"Local {goles_esp_local:.2f} - Visita {goles_esp_vis:.2f}",
            "h2h_10anos": f"{x.get('h2h_total_10anos',0)} partidos, Local ganó {x.get('h2h_victorias_local',0)}",
            "porteria_cero": f"Local {L['porteria_cero_pct']}% - Visita {V['porteria_cero_pct']}%",
        },
        "analizado_con": "Bot 3 - 10 años (2016-2026) + Parametros de la app",
        "parametros_usados": list(PARAMETROS_APP.keys())
    }

p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n✅ PIPELINE V3 COMPLETO - 10 AÑOS")
for x in d["partidos"]:
    print(f" - {x['local']} vs {x['visitante']} -> {x.get('prediccion_ia',{}).get('mejor_apuesta')} | {x.get('prediccion_ia',{}).get('motivo','')[:120]}")
