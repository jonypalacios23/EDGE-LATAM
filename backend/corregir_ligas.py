import json, pathlib
p = pathlib.Path("backend/partidos_hoy.json")
d = json.loads(p.read_text(encoding="utf-8"))
# league_id de API-Football -> Liga oficial que ve el usuario
# Si la API manda un ID de Argelia pero nosotros lo teniamos como Guatemala, esto lo corrige
LIGAS_CANONICAS = {
    # Colombia - estos si estan bien
    239: "Colombia - Primera A",
    240: "Colombia - Primera B",
    241: "Colombia - Copa Colombia",
    # Brasil, Uruguay, Mexico, etc. - agregar los IDs reales de tu actualizar_dia.py
}
# Regla: si el equipo es de Argelia, no puede ser Guatemala
EQUIPOS_NO_GUATEMALA = ["Paradou", "JSM Skikda", "WA Tlemcen", "RC Arba", "JS Jijel", "CR Beni Thour"]
for x in d.get("partidos", []):
    if any(e in x.get("local","") or e in x.get("visitante","") for e in EQUIPOS_NO_GUATEMALA):
        print(f"ALERTA LIGA MAL: {x['liga']} | {x['local']} vs {x['visitante']} -> Esto es Argelia, no Guatemala. Lo marco para revisar")
        x["liga"] = "Argelia - Ligue 1 / Ligue 2 - VERIFICAR"
        x["revisar_liga"] = True
    print(f" - {x['liga']} | {x['local']} vs {x['visitante']}")
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
