import json, pathlib, unicodedata, re
p = pathlib.Path("backend/partidos_hoy.json")
d = json.loads(p.read_text(encoding="utf-8"))

def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','',s)

vistos_partido = set()
equipos_ya_usados = set()
limpios = []
eliminados = []

for partido in d.get("partidos", []):
    local = partido.get("local","")
    vis = partido.get("visitante","")
    key = tuple(sorted([norm(local), norm(vis)]))
    # 1. Mismo partido repetido
    if key in vistos_partido:
        eliminados.append(f"{local} vs {vis} - repetido")
        continue
    # 2. Mismo equipo en 2 partidos el mismo dia = imposible, nos quedamos con el primero
    if norm(local) in equipos_ya_usados or norm(vis) in equipos_ya_usados:
        eliminados.append(f"{local} vs {vis} - equipo ya juega hoy, descartado")
        continue
    vistos_partido.add(key)
    equipos_ya_usados.add(norm(local))
    equipos_ya_usados.add(norm(vis))
    partido["liga"] = f"{partido.get('pais','')} - {partido.get('competicion','')}"
    limpios.append(partido)

d["partidos"] = limpios
d["total"] = len(limpios)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"ANTES: 21 - AHORA: {len(limpios)} partidos limpios")
print("ELIMINADOS:")
for e in eliminados:
    print(" -", e)
print("\nQUEDAN:")
for x in limpios:
    print(f" - {x['liga']} | {x['local']} vs {x['visitante']}")
