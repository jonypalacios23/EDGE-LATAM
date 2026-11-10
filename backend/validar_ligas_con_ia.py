import json, pathlib
p = pathlib.Path("backend/partidos_hoy.json")
d = json.loads(p.read_text(encoding="utf-8"))

# LIGAS HABILITADAS - Solo estas pueden salir en la pagina.
# Formato: league_id de API-Football -> (Pais oficial, Liga oficial)
# Si la API manda un league_id que no esta aqui, NO se publica.
LIGAS_HABILITADAS = {
    239: ("Colombia", "Primera A"),
    240: ("Colombia", "Primera B"),
    241: ("Colombia", "Copa Colombia"),
    253: ("Brasil", "Serie B"),
    257: ("Uruguay", "Segunda Division"),
    258: ("Mexico", "Liga de Expansion MX"),
    259: ("Mexico", "Segunda Division MX"),
    260: ("Costa Rica", "Segunda Division"),
    261: ("Curazao", "Sekshon Paga"),
    262: ("Guatemala", "Liga Nacional"),
}

# Equipos que la IA ya sabe que NO pertenecen a esa liga - para cazar el error de Argelia
# Si aparece uno de estos, es 100% que la liga esta mal asignada
ALERTA_EQUIPOS = {
    "Paradou": "Argelia",
    "JSM Skikda": "Argelia",
    "WA Tlemcen": "Argelia",
    "RC Arba": "Argelia",
    "JS Jijel": "Argelia",
    "CR Beni Thour": "Argelia",
}

print("=== VALIDACION DE LIGAS CON IA - ANTES DE PUBLICAR ===")
validos = []
bloqueados = []
for x in d.get("partidos", []):
    lid = x.get("league_id") or x.get("liga_id")
    local = x.get("local","")
    vis = x.get("visitante","")
    # 1. Verificar si el equipo es de Argelia pero la liga dice Guatemala
    for equipo, pais_real in ALERTA_EQUIPOS.items():
        if equipo in local or equipo in vis:
            bloqueados.append(f"BLOQUEADO: {local} vs {vis} - dice {x.get('liga')} pero {equipo} es de {pais_real}")
            x["publicar"] = False
            x["motivo_bloqueo"] = f"Equipo {equipo} es de {pais_real}, no de {x.get('liga')}"
            break
    else:
        # 2. Verificar que league_id este en habilitadas
        if lid in LIGAS_HABILITADAS:
            pais, liga = LIGAS_HABILITADAS[lid]
            x["liga"] = f"{pais} - {liga}"
            x["pais"] = pais
            x["competicion"] = liga
            x["publicar"] = True
            validos.append(x)
        else:
            bloqueados.append(f"BLOQUEADO: {local} vs {vis} - league_id {lid} no esta en ligas habilitadas, no adivinar")
            x["publicar"] = False
            x["motivo_bloqueo"] = f"league_id {lid} no habilitado"

print(f"\nVALIDOS PARA PUBLICAR: {len(validos)}")
for v in validos:
    print(f"  OK: {v['liga']} | {v['local']} vs {v['visitante']}")
print(f"\nBLOQUEADOS - NO PUBLICAR HASTA VERIFICAR: {len(bloqueados)}")
for b in bloqueados:
    print(f"  {b}")

# Guardamos solo los validos en el archivo que ve el usuario, los bloqueados quedan en otro archivo para revision
d["partidos"] = validos
d["total"] = len(validos)
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
pathlib.Path("backend/partidos_bloqueados.json").write_text(json.dumps({"bloqueados": bloqueados}, ensure_ascii=False, indent=2), encoding="utf-8")
print("\nListo. La pagina solo va a mostrar los VALIDOS. Los bloqueados no salen hasta que los confirmemos con IA.")
