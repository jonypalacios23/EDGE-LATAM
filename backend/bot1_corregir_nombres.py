from __future__ import annotations

import json
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
correcciones = json.loads(
    (BACKEND_DIR / "correcciones_equipos.json").read_text(encoding="utf-8")
)["correcciones"]
mapa = {correccion["team_id"]: correccion["nombre_real"] for correccion in correcciones}
partidos_path = BACKEND_DIR / "partidos_hoy.json"
datos = json.loads(partidos_path.read_text(encoding="utf-8"))

print("🤖 BOT 1 V2: Corrigiendo nombres API -> Nombres reales en apuestas...")
for partido in datos["partidos"]:
    for campo_id, campo_nombre in (("local_id", "local"), ("visitante_id", "visitante")):
        team_id = partido.get(campo_id)
        if team_id in mapa and partido[campo_nombre] != mapa[team_id]:
            print("  🔁 {} (ID {}) -> {}".format(partido[campo_nombre], team_id, mapa[team_id]))
            partido[campo_nombre] = mapa[team_id]
        elif team_id in mapa:
            print("  ✅ {} ya está correcto".format(partido[campo_nombre]))

partidos_path.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
print("✅ BOT 1 V2 listo - El ID se mantiene, solo cambia el nombre que ve el usuario")
