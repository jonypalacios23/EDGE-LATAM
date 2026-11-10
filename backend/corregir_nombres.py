import json, pathlib, unicodedata, re
p = pathlib.Path("backend/partidos_hoy.json")
d = json.loads(p.read_text(encoding="utf-8"))

def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii','ignore').decode().lower()
    s = re.sub(r'[^a-z0-9 ]','',s)
    s = re.sub(r'\s+',' ',s).strip()
    return s

# Todas las formas como la API lo puede escribir -> Nombre oficial que ve el usuario
# Si mañana la API ya lo pone bien, tambien cae aqui y no se duplica ni se pierde
ALIAS_CANONICO = {
    # Boca Juniors de Cali - el caso de Envigado
    "popayan": "Boca Juniors de Cali",
    "boca juniors": "Boca Juniors de Cali",
    "boca juniors de cali": "Boca Juniors de Cali",
    "boca juniors cali": "Boca Juniors de Cali",
    "boca jrs de cali": "Boca Juniors de Cali",
    "boca jrs cali": "Boca Juniors de Cali",
    "boca cali": "Boca Juniors de Cali",
    # Otros que tienen el mismo problema
    "independiente yumbo": "Ind. Valle del Cauca",
    "ind yumbo": "Ind. Valle del Cauca",
    "ind valle del cauca": "Ind. Valle del Cauca",
    "independiente valle del cauca": "Ind. Valle del Cauca",
    "union magdalena": "Unión Magdalena",
    "tigres fc": "Tigres FC",
    "tigres": "Tigres FC",
}

def canonico(nombre):
    n = norm(nombre)
    return ALIAS_CANONICO.get(n, nombre)  # si no esta en la lista, lo deja como viene

partidos = []
for x in d.get("partidos", []):
    # Normalizar siempre, venga como venga de la API
    x["local"] = canonico(x.get("local",""))
    x["visitante"] = canonico(x.get("visitante",""))
    # Envigado de hoy: sea Popayan, Boca, o Boca Juniors de Cali, siempre queda Boca Juniors de Cali
    if x.get("local") == "Envigado":
        x["visitante"] = "Boca Juniors de Cali"
        x["competicion"] = "Primera B"
        x["liga"] = "Colombia - Primera B"
        x["hora"] = "3:30 p.m."
    x["liga"] = f"{x.get('pais','')} - {x.get('competicion','')}"
    partidos.append(x)

d["partidos"] = partidos
d["total"] = len(partidos)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Listo: {len(partidos)} partidos con nombres canonicos")
for x in partidos:
    print(f" - {x['liga']} | {x['local']} vs {x['visitante']}")
print("\nPrueba de que asimila las 3 variantes:")
for prueba in ["Popayan", "Boca Juniors", "Boca Juniors de Cali"]:
    print(f"  API dice '{prueba}' -> Usuario ve '{canonico(prueba)}'")
