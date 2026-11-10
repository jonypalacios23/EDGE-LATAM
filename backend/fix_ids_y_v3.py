import json, pathlib, os, urllib.request, urllib.parse
API_KEY = os.getenv("API_FOOTBALL_KEY")
print(f"Clave que estas usando: {API_KEY[:6] if API_KEY else 'VACIA'}... largo {len(API_KEY) if API_KEY else 0}")
if not API_KEY or "PEGA_AQUI" in API_KEY:
    print("❌ ERROR: Todavia tienes PEGA_AQUI_TU_NUEVA_CLAVE. Pega tu clave real rotada antes de correr.")
    exit(1)

HEADERS = {"x-rapidapi-key": API_KEY, "x-rapidapi-host": "v3.football.api-sports.io"}
BASE = "https://v3.football.api-sports.io"
def api_get(endpoint, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}/{endpoint}?{qs}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode()).get("response", [])

p = pathlib.Path("backend/partidos_hoy.json")
d = json.loads(p.read_text(encoding="utf-8"))
print(f"\n🤖 BOT 1 V3.1: Buscando IDs que faltan para {len(d['partidos'])} partidos...")
for x in d["partidos"]:
    print(f"\n- {x.get('local')} vs {x.get('visitante')} | fixture_id={x.get('fixture_id')} local_id={x.get('local_id')} vis_id={x.get('visitante_id')}")
    # 1. La forma mas segura: por fixture_id
    if x.get("fixture_id") and (not x.get("local_id") or not x.get("visitante_id")):
        try:
            res = api_get("fixtures", {"id": x["fixture_id"]})
            if res:
                f = res[0]
                x["local_id"] = f["teams"]["home"]["id"]
                x["visitante_id"] = f["teams"]["away"]["id"]
                x["local_oficial"] = f["teams"]["home"]["name"]
                x["visitante_oficial"] = f["teams"]["away"]["name"]
                x["league_id"] = f["league"]["id"]
                x["season"] = f["league"]["season"]
                print(f"  ✅ Por fixture_id: local_id={x['local_id']} ({x['local_oficial']}) vs visitante_id={x['visitante_id']} ({x['visitante_oficial']}) | league_id={x['league_id']} season={x['season']}")
                continue
        except Exception as e:
            print(f"  ❌ Error por fixture_id: {e}")
    # 2. Si no hay fixture_id, por nombre en /teams?search=
    if not x.get("local_id"):
        try:
            res = api_get("teams", {"search": x.get("local","")})
            if res:
                x["local_id"] = res[0]["team"]["id"]
                print(f"  ✅ Por nombre local: {x['local']} -> {x['local_id']} ({res[0]['team']['name']})")
        except Exception as e: print(f"  ❌ Error buscando local: {e}")
    if not x.get("visitante_id"):
        try:
            res = api_get("teams", {"search": x.get("visitante","")})
            if res:
                x["visitante_id"] = res[0]["team"]["id"]
                print(f"  ✅ Por nombre visita: {x['visitante']} -> {x['visitante_id']} ({res[0]['team']['name']})")
        except Exception as e: print(f"  ❌ Error buscando visita: {e}")

p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("\n✅ IDs GUARDADOS. Ahora si corre el V3, ya no va a decir SIN IDs.")
