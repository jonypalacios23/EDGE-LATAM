import json, pathlib
p = pathlib.Path("backend/partidos_hoy.json")
d = json.loads(p.read_text(encoding="utf-8"))
vistos = set()
unicos = []
for partido in d.get("partidos", []):
    fid = partido.get("fixture_id")
    if fid in vistos:
        continue
    vistos.add(fid)
    # Esto es lo que hace que salga la liga en la pagina
    partido["liga"] = f"{partido.get('pais','')} - {partido.get('competicion','')}"
    partido["buscar_en_casa"] = f"{partido.get('competicion','')} - {partido.get('local','')} vs {partido.get('visitante','')}"
    unicos.append(partido)
d["partidos"] = unicos
d["total"] = len(unicos)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Arreglado: {len(unicos)} partidos unicos, ya con liga")
for x in unicos:
    print(f" - {x['liga']} | {x['local']} vs {x['visitante']}")
