import json, pathlib, os, time, urllib.request, urllib.parse

# Lee la clave del .env, no del export
env_path = pathlib.Path("backend/.env")
for line in env_path.read_text().splitlines():
    if line.startswith("API_FOOTBALL_KEY="):
        os.environ["API_FOOTBALL_KEY"] = line.split("=",1)[1].strip()

API_KEY = os.getenv("API_FOOTBALL_KEY")
print("API_FOOTBALL_KEY cargada" if API_KEY else "Falta API_FOOTBALL_KEY")
if not API_KEY or "PEGA_AQUI" in API_KEY:
    print("❌ AUN TIENES PEGA_AQUI en backend/.env. Ve al paso 1 y pon tu clave real del dashboard.")
    exit(1)

HEADERS = {"x-apisports-key": API_KEY}
BASE = "https://v3.football.api-sports.io"
def api_get(endpoint, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}/{endpoint}?{qs}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode())
        if "errors" in data and data["errors"]:
            print(f"  ERROR API: {data['errors']}")
        return data.get("response", [])

p = pathlib.Path("backend/partidos_hoy.json")
d = json.loads(p.read_text(encoding="utf-8"))

# --- BOT 1: Arregla IDs por fixture_id ---
print("\n🤖 BOT 1: Arreglando IDs por fixture_id...")
for x in d["partidos"]:
    if x.get("fixture_id") and (not x.get("local_id") or not x.get("visitante_id")):
        res = api_get("fixtures", {"id": x["fixture_id"]})
        if res:
            f = res[0]
            x["local_id"] = f["teams"]["home"]["id"]
            x["visitante_id"] = f["teams"]["away"]["id"]
            x["league_id"] = f["league"]["id"]
            x["season"] = f["league"]["season"]
            print(f"  ✅ {x['local']} vs {x['visitante']} -> local_id={x['local_id']} vis_id={x['visitante_id']} liga={f['league']['name']}")
        time.sleep(0.2)

# --- BOT 2: 10 AÑOS ---
print("\n🤖 BOT 2: 10 AÑOS (2016-2026)...")
CACHE_PATH = pathlib.Path("backend/cache_10anos.json")
cache = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
def analisis_10anos(team_id):
    if str(team_id) in cache:
        print(f"  -> Equipo {team_id} en cache, usando cache")
        return cache[str(team_id)]
    print(f"  -> Bajando 10 años equipo {team_id}...")
    tot=gf_tot=gc_tot=btts=o15=o25=o35=cero=vic=0
    goles_casa=[]; goles_fuera=[]; ultimos=[]
    for season in range(2016, 2027):
        try:
            fixtures = api_get("fixtures", {"team": team_id, "season": season, "status": "FT"})
            for f in fixtures:
                es_casa = f["teams"]["home"]["id"] == team_id
                gf = f["goals"]["home"] if es_casa else f["goals"]["away"]
                gc = f["goals"]["away"] if es_casa else f["goals"]["home"]
                if gf is None: continue
                tot+=1; gf_tot+=gf; gc_tot+=gc
                if es_casa: goles_casa.append(gf)
                else: goles_fuera.append(gf)
                if gf>0 and gc>0: btts+=1
                if gf+gc>1.5: o15+=1
                if gf+gc>2.5: o25+=1
                if gf+gc>3.5: o35+=1
                if gc==0: cero+=1
                if gf>gc: vic+=1
                ultimos.append({"gf":gf,"fecha":f["fixture"]["date"]})
            time.sleep(0.2)
        except Exception as e: print(f"    Error {season}: {e}")
    ultimos = sorted(ultimos, key=lambda x: x["fecha"])[-10:]
    gf_rec = sum(x["gf"] for x in ultimos)/len(ultimos) if ultimos else 0
    n = tot or 1
    res = {
        "total_partidos_10anos": tot,
        "prom_goles_favor_10anos": round(gf_tot/n,2),
        "prom_goles_casa_10anos": round(sum(goles_casa)/len(goles_casa),2) if goles_casa else 0,
        "prom_goles_fuera_10anos": round(sum(goles_fuera)/len(goles_fuera),2) if goles_fuera else 0,
        "btts_pct_10anos": round(btts/n*100,1),
        "over25_pct": round(o25/n*100,1),
        "over15_pct": round(o15/n*100,1),
        "over35_pct": round(o35/n*100,1),
        "porteria_cero_pct": round(cero/n*100,1),
        "prom_goles_ponderado": round((gf_tot/n)*0.7 + gf_rec*0.3,2),
    }
    cache[str(team_id)] = res
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    -> {tot} partidos 10 años | Goles {res['prom_goles_favor_10anos']} | BTTS {res['btts_pct_10anos']}% | Over2.5 {res['over25_pct']}%")
    return res

for x in d["partidos"]:
    if not x.get("local_id"): continue
    print(f"\n{x['local']} vs {x['visitante']}")
    x["analisis_10anos_local"] = analisis_10anos(x["local_id"])
    x["analisis_10anos_vis"] = analisis_10anos(x["visitante_id"])

# --- BOT 3: Prediccion con parametros de la app ---
print("\n🤖 BOT 3: Prediccion con parametros de la app + 10 años...")
for x in d["partidos"]:
    if "analisis_10anos_local" not in x: continue
    L=x["analisis_10anos_local"]; V=x["analisis_10anos_vis"]
    ge_local = L["prom_goles_casa_10anos"]*0.7 + L["prom_goles_ponderado"]*0.3 + 0.15
    ge_vis = V["prom_goles_fuera_10anos"]*0.7 + V["prom_goles_ponderado"]*0.3
    total_esp = ge_local + ge_vis
    btts_prom = (L["btts_pct_10anos"]+V["btts_pct_10anos"])/2
    over25_prom = (L["over25_pct"]+V["over25_pct"])/2
    if over25_prom>=55 and total_esp>=2.6: apuesta,conf="Más de 2.5 goles","Alta"
    elif over25_prom<=35 and total_esp<=1.9: apuesta,conf="Menos de 2.5 goles","Alta"
    elif btts_prom>=55: apuesta,conf="Ambos Marcan - Sí","Alta"
    elif ge_local>ge_vis+0.6: apuesta,conf="Gana Local","Media-Alta"
    else: apuesta,conf="Doble Oportunidad 1X","Media"
    x["prediccion_ia"] = {
        "mejor_apuesta": apuesta, "confianza": conf,
        "motivo": f"10 años: Local {L['total_partidos_10anos']} PJ {L['prom_goles_favor_10anos']} goles | Visita {V['total_partidos_10anos']} PJ {V['prom_goles_favor_10anos']} goles | Esperados {total_esp:.2f} | BTTS {btts_prom:.1f}% | Over2.5 {over25_prom:.1f}%",
        "mercados": {"goles": f"Over 2.5 {'SI' if over25_prom>=50 else 'NO'} ({over25_prom:.1f}%)", "btts": f"BTTS Sí ({btts_prom:.1f}%)", "goles_esperados": f"Local {ge_local:.2f} - Visita {ge_vis:.2f}"},
        "analizado_con": "Bot 3 - 10 años (2016-2026) + Parametros app"
    }

p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n✅ PIPELINE FINAL COMPLETO")
for x in d["partidos"]:
    print(f" - {x['local']} vs {x['visitante']} -> {x.get('prediccion_ia',{}).get('mejor_apuesta')} | {x.get('prediccion_ia',{}).get('motivo','')[:130]}")
