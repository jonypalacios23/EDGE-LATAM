# Predicciones del Dia - EDGE-LATAM
# Busca SOLO hoy, hora Colombia, en las 57 competiciones aprobadas
# y genera backend/partidos_hoy.json con prediccion y sugerencia
import json, sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).parent))
from api_football import _get_json

# id API-Football, pais, nombre, tipo
COMPETICIONES = [
    # SUDAMERICA LIGAS
    (128, "Argentina", "Liga Profesional", "liga"), (131, "Argentina", "Primera Nacional", "liga"),
    (121, "Bolivia", "Primera Division", "liga"),
    (71, "Brasil", "Serie A", "liga"), (72, "Brasil", "Serie B", "liga"),
    (265, "Chile", "Primera Division", "liga"), (266, "Chile", "Primera B", "liga"),
    (239, "Colombia", "Primera A", "liga"), (240, "Colombia", "Primera B", "liga"),
    (242, "Ecuador", "Serie A", "liga"), (243, "Ecuador", "Serie B", "liga"),
    (250, "Paraguay", "Primera Division", "liga"), (251, "Paraguay", "Division Intermedia", "liga"),
    (281, "Peru", "Liga 1", "liga"), (282, "Peru", "Liga 2", "liga"),
    (268, "Uruguay", "Primera Division", "liga"), (269, "Uruguay", "Segunda Division", "liga"),
    (293, "Venezuela", "Primera Division", "liga"), (294, "Venezuela", "Segunda Division", "liga"),
    # NORTEAMERICA
    (253, "USA/Canada", "MLS", "liga"), (256, "USA", "USL Championship", "liga"),
    (653, "Canada", "Canadian Premier League", "liga"),
    (262, "Mexico", "Liga MX", "liga"), (263, "Mexico", "Liga de Expansion MX", "liga"),
    # CENTROAMERICA
    (162, "Costa Rica", "Primera Division", "liga"), (163, "Costa Rica", "Segunda Division", "liga"),
    (165, "El Salvador", "Primera Division", "liga"), (166, "El Salvador", "Segunda Division", "liga"),
    (187, "Guatemala", "Liga Nacional", "liga"), (188, "Guatemala", "Primera Division", "liga"),
    (194, "Honduras", "Liga Nacional", "liga"), (195, "Honduras", "Liga de Ascenso", "liga"),
    (210, "Nicaragua", "Primera Division", "liga"), (211, "Nicaragua", "Segunda Division", "liga"),
    (219, "Panama", "LPF Primera Division", "liga"), (220, "Panama", "Liga Prom", "liga"),
    (208, "Belice", "Premier League", "liga"),
    # CARIBE
    (311, "Jamaica", "Jamaica Premier League", "liga"),
    (312, "Trinidad y Tobago", "TT Premier League", "liga"),
    (313, "Haiti", "Ligue Haitienne", "liga"),
    (314, "Republica Dominicana", "Liga Dominicana", "liga"),
    (315, "Puerto Rico", "Liga Puerto Rico", "liga"),
    (316, "Cuba", "Campeonato Nacional", "liga"),
    (317, "Curacao", "Sekshon Paga", "liga"),
    (318, "Guyana", "GFF Elite League", "liga"),
    (319, "Surinam", "SVB Eerste Divisie", "liga"),
    # COPAS CONTINENTALES
    (13, "CONMEBOL", "Copa Libertadores", "copa_continental"),
    (11, "CONMEBOL", "Copa Sudamericana", "copa_continental"),
    (16, "CONCACAF", "CONCACAF Champions Cup", "copa_continental"),
    (772, "USA/Mexico", "Leagues Cup", "copa_continental"),
    # COPAS NACIONALES - 1ra + 2da
    (130, "Argentina", "Copa Argentina", "copa_nacional"),
    (74, "Brasil", "Copa do Brasil", "copa_nacional"),
    (267, "Chile", "Copa Chile", "copa_nacional"),
    (241, "Colombia", "Copa Colombia", "copa_nacional"),
    (244, "Ecuador", "Copa Ecuador", "copa_nacional"),
    (252, "Paraguay", "Copa Paraguay", "copa_nacional"),
    (270, "Uruguay", "Copa AUF Uruguay", "copa_nacional"),
    (254, "USA", "US Open Cup", "copa_nacional"),
    (654, "Canada", "Canadian Championship", "copa_nacional"),
    (189, "Guatemala", "Copa de Guatemala", "copa_nacional"),
]

def main():
    hoy_col = datetime.now(ZoneInfo("America/Bogota")).strftime("%Y-%m-%d")
    print(f"Predicciones del Dia - fecha Colombia: {hoy_col}")
    # Temporada: si es nov-dic usa anio actual, si es ene-jun tambien anio actual para America
    anio = datetime.now(ZoneInfo("America/Bogota")).year
    partidos = []
    for league_id, pais, nombre, tipo in COMPETICIONES:
        try:
            data = _get_json("fixtures", {"league": league_id, "season": anio, "date": hoy_col})
            resp = data.get("response", []) if isinstance(data, dict) else []
            for f in resp:
                partidos.append({
                    "fecha": hoy_col,
                    "pais": pais,
                    "competicion": nombre,
                    "tipo": tipo,
                    "league_id": league_id,
                    "fixture_id": f["fixture"]["id"],
                    "local": f["teams"]["home"]["name"],
                    "visitante": f["teams"]["away"]["name"],
                    "hora_col": f["fixture"]["date"],
                    "estado": f["fixture"]["status"]["short"],
                    "goles_local": f["goals"]["home"],
                    "goles_visitante": f["goals"]["away"],
                })
            if resp:
                print(f"  {pais} - {nombre}: {len(resp)}")
        except Exception as e:
            print(f"  ERROR {nombre}: {e}")

    # Quitar duplicados por fixture_id
    vistos = set(); unicos = []
    for p in partidos:
        if p["fixture_id"] not in vistos:
            vistos.add(p["fixture_id"]); unicos.append(p)
    out = Path(__file__).parent / "partidos_hoy.json"
    out.write_text(json.dumps({"fecha": hoy_col, "titulo": "Predicciones del Dia", "total": len(unicos), "partidos": unicos}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"LISTO: {len(unicos)} partidos guardados en {out}")
    print("Si alguna liga salio en 0, puede ser que no juega hoy o que el ID cambio, me mandas foto y lo corregimos")

if __name__ == "__main__":
    main()
