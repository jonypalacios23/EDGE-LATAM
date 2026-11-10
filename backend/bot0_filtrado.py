import json, pathlib, os, urllib.request, urllib.parse, unicodedata
from datetime import date
for line in pathlib.Path("backend/.env").read_text().splitlines():
    if line.startswith("API_FOOTBALL_KEY="):
        os.environ["API_FOOTBALL_KEY"] = line.split("=",1)[1].strip()
API_KEY = os.getenv("API_FOOTBALL_KEY")
HEADERS = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}
BASE = "https://v3.football.api-sports.io"
def api_get(endpoint, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}/{endpoint}?{qs}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode()).get("response", [])
def norm(s):
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii","ignore").decode()
    return s.strip()
HOY = date.today().isoformat()
hab = json.loads(pathlib.Path("backend/ligas_habilitadas.json").read_text())["ligas_habilitadas"]
# Mapa: (pais_norm, liga_norm) -> liga_app
mapa = {(norm(x["pais"]), norm(x["liga_api"])): x["liga_app"] for x in hab}
# Caso especial: Primera Division existe en muchos paises, por eso usamos PAIS + LIGA, no solo liga
print(f"🤖 BOT 0 V3 - 57 competiciones habilitadas")
todos = api_get("fixtures", {"date": HOY})
print(f"API hoy: {len(todos)} partidos en todo el mundo")
partidos=[]; ignorados=0
for f in todos:
    pais=f["league"]["country"]; liga=f["league"]["name"]
    key=(norm(pais), norm(liga))
    if key not in mapa:
        ignorados+=1
        continue
    partidos.append({
        "fixture_id": f["fixture"]["id"], "fecha": f["fixture"]["date"], "estado": f["fixture"]["status"]["short"],
        "local": f["teams"]["home"]["name"], "visitante": f["teams"]["away"]["name"],
        "local_id": f["teams"]["home"]["id"], "visitante_id": f["teams"]["away"]["id"],
        "liga": mapa[key], "liga_api": liga, "pais": pais,
        "league_id": f["league"]["id"], "season": f["league"]["season"],
        "goles_local": f["goals"]["home"], "goles_visitante": f["goals"]["away"],
    })
print(f"✅ FILTRADO: {len(partidos)} partidos de las 57 habilitadas")
print(f"❌ IGNORADOS: {ignorados} de ligas NO habilitadas (Europa, Asia, etc.)")
from collections import Counter
for liga, cant in Counter([f"{x['pais']} - {x['liga']}" for x in partidos]).most_common():
    print(f"  - {liga}: {cant}")
pathlib.Path("backend/partidos_hoy.json").write_text(json.dumps({"fecha": HOY, "total_filtrado": len(partidos), "partidos": partidos}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n✅ Guardado backend/partidos_hoy.json con {len(partidos)} partidos")
