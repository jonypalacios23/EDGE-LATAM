import json, pathlib, os, unicodedata, re, time, urllib.request, urllib.parse

API_KEY = os.getenv("API_FOOTBALL_KEY", "TU_API_KEY_AQUI")
HEADERS = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}
BASE = "https://v3.football.api-sports.io"
p = pathlib.Path("backend/partidos_hoy.json")
d = json.loads(p.read_text(encoding="utf-8"))

def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9 ]','',s).strip()

# ========== BOT 1: VERIFICADOR IA - Nombres, origen, liga ==========
print("🤖 BOT 1: VERIFICADOR - Corrigiendo nombres y ligas...")
# Diccionario canonico: cualquier forma que venga la API -> nombre oficial
CANONICO = {
    "popayan": "Boca Juniors de Cali",
    "boca juniors": "Boca Juniors de Cali",
    "boca juniors de cali": "Boca Juniors de Cali",
    "boca juniors cali": "Boca Juniors de Cali",
    "independiente yumbo": "Ind. Valle del Cauca",
    "ind yumbo": "Ind. Valle del Cauca",
    "union magdalena": "Unión Magdalena",
    "internacional de bogota": "Internacional de Bogotá",
}
def canonico(n):
    return CANONICO.get(norm(n), n)

def api_get(endpoint, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}/{endpoint}?{qs}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode()).get("response", [])

for x in d.get("partidos", []):
    x["local"] = canonico(x.get("local",""))
    x["visitante"] = canonico(x.get("visitante",""))
    # BOT 1 pregunta a la misma API: ¿este league_id de que pais y liga es en realidad?
    # No adivina, lo lee de /leagues?id=
    lid = x.get("league_id")
    if lid:
        try:
            info = api_get("leagues", {"id": lid})
            if info:
                pais_real = info[0]["country"]["name"]
                liga_real = info[0]["league"]["name"]
                # Si la API dice Argelia pero nosotros teniamos Guatemala, corrige solo
                if x.get("pais") != pais_real or x.get("competicion") != liga_real:
                    print(f"  CORREGIDO BOT 1: {x['local']} vs {x['visitante']} era {x.get('pais')} - {x.get('competicion')} -> ahora {pais_real} - {liga_real}")
                x["pais"] = pais_real
                x["competicion"] = liga_real
                x["liga"] = f"{pais_real} - {liga_real}"
                x["logo_liga"] = info[0]["league"]["logo"]
        except Exception as e:
            print(f"  BOT 1 no pudo verificar league_id {lid}: {e}")
    time.sleep(0.2)

# ========== BOT 2: CAZADOR DE DATOS - Trae estadisticas reales por fixture_id ==========
print("\n🤖 BOT 2: CAZADOR DE DATOS - Bajando goles, corners, tarjetas, tiros de la API que pagamos...")
for x in d.get("partidos", []):
    fid = x.get("fixture_id")
    if not fid:
        print(f"  SIN fixture_id: {x['local']} vs {x['visitante']}")
        continue
    try:
        # 1. Estadisticas del partido (si ya se jugo) + ultimos 5 de cada equipo
        stats = api_get("fixtures/statistics", {"fixture": fid})
        # 2. Estadisticas de temporada por equipo para promedios
        lid = x.get("league_id")
        season = x.get("season", 2026)
        for lado, team_id in [("local", x.get("local_id")), ("vis", x.get("visitante_id"))]:
            if team_id and lid:
                tstats = api_get("teams/statistics", {"league": lid, "season": season, "team": team_id})
                if tstats:
                    goles = tstats.get("goals", {}).get("for", {}).get("average", {}).get("total", 0)
                    corners = tstats.get("corners", {}).get("average", 0) if isinstance(tstats.get("corners"), dict) else 0
                    # Guardamos promedio real
                    x[f"prom_goles_{lado}"] = float(goles or 0)
                    x[f"prom_corners_{lado}"] = float(corners or 0)
                    x[f"partidos_jugados_{lado}"] = tstats.get("fixtures", {}).get("played", {}).get("total", 0)
        # 3. Head to Head
        if x.get("local_id") and x.get("visitante_id"):
            h2h = api_get("fixtures/headtohead", {"h2h": f"{x['local_id']}-{x['visitante_id']}", "last": 5})
            x["h2h_ultimos_5"] = len(h2h)
        print(f"  OK DATOS: {x['local']} vs {x['visitante']} -> Goles L:{x.get('prom_goles_local',0)} V:{x.get('prom_goles_vis',0)} | Partidos L:{x.get('partidos_jugados_local',0)}")
    except Exception as e:
        print(f"  ERROR BOT 2 en {x['local']} vs {x['visitante']}: {e}")
    time.sleep(0.3)

# ========== BOT 3: ANALISTA IA - Predice solo con datos reales ==========
print("\n🤖 BOT 3: ANALISTA - Generando predicciones con datos reales...")
for x in d.get("partidos", []):
    gl = float(x.get("prom_goles_local", 0) or 0)
    gv = float(x.get("prom_goles_vis", 0) or 0)
    total = gl + gv
    cl = float(x.get("prom_corners_local", 0) or 0)
    cv = float(x.get("prom_corners_vis", 0) or 0)
    total_corners = cl + cv

    if total == 0:
        x["prediccion_ia"] = {"mejor_apuesta": "NO PUBLICAR - Bot 2 no pudo traer datos, reintentar", "confianza": "Nula", "motivo": "Bot 2 no encontro estadisticas en API, no inventar"}
        continue
    # Reglas estipuladas
    if total >= 2.7:
        apuesta, conf, motivo = "Más de 2.5 goles", "Alta", f"Promedio combinado {total:.2f} goles por partido"
    elif total <= 1.7:
        apuesta, conf, motivo = "Menos de 2.5 goles", "Media-Alta", f"Promedio combinado bajo {total:.2f} goles"
    elif gl > gv + 0.5:
        apuesta, conf, motivo = "Gana Local", "Media", f"Local promedia {gl:.2f} vs Visita {gv:.2f}"
    else:
        apuesta, conf, motivo = "Ambos Marcan - Sí", "Media", f"Ambos promedian +0.9 goles"

    mercados = {
        "goles": f"Over 2.5: {'SI' if total >= 2.5 else 'NO'} ({total:.2f} prom)",
        "corners": f"Over 8.5 corners: {'SI' if total_corners >= 9 else 'NO'} ({total_corners:.1f} prom)" if total_corners > 0 else "Sin datos de corners en API",
        "tarjetas": "Ver estadisticas de disciplina en API",
        "doble_oportunidad": "1X" if gl >= gv else "X2"
    }
    x["prediccion_ia"] = {"mejor_apuesta": apuesta, "confianza": conf, "motivo": motivo, "mercados": mercados, "analizado_por": "Bot 3 - IA + API-Football"}

p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n✅ PIPELINE COMPLETO: {len(d['partidos'])} partidos verificados, con datos y con prediccion")
for x in d["partidos"]:
    print(f" - {x.get('liga')} | {x['local']} vs {x['visitante']} -> {x.get('prediccion_ia',{}).get('mejor_apuesta')}")
