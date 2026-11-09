from __future__ import annotations

from google_stats import _GoogleParser, buscar_estadistica_google, construir_consulta, extraer_total
from main import liquidar_mercado


def _buscar_con(texto: str):
    return lambda consulta: [{
        "title": "Resumen del partido Alianza vs Llaneros",
        "text": texto,
        "url": "https://www.espn.com.co/futbol/partido/_/id/123",
    }]


def probar_consultas_por_mercado():
    partido = {"fecha": "2026-11-08", "local": "Alianza", "visitante": "Llaneros"}
    assert construir_consulta(partido, {"tipo": "tarjetas"}) == (
        "cuantas tarjetas hubo en Alianza vs Llaneros 2026-11-08"
    )
    assert construir_consulta(partido, {"tipo": "corners"}) == (
        "cuantos corners hubo en Alianza vs Llaneros 2026-11-08"
    )
    assert construir_consulta(partido, {"tipo": "goles"}) == (
        "cuantos goles hubo en Alianza vs Llaneros 2026-11-08"
    )


def probar_alianza_llaneros_cinco_tarjetas():
    partido = {"fecha": "2026-11-08", "local": "Alianza", "visitante": "Llaneros"}
    mercado = {"tipo": "tarjetas", "direccion": "mas", "linea": 4.5}
    dato = buscar_estadistica_google(
        partido,
        mercado,
        _buscar_con("Alianza 1-2 Llaneros: 5 tarjetas amarillas, 0 rojas."),
    )
    assert dato and dato["total"] == 5, dato
    assert dato["fuente"] == "Google"
    resultado = {"estado": "finalizado", "tarjetas_total": dato["total"]}
    liquidacion = liquidar_mercado(resultado, mercado)
    assert liquidacion["estado"] == "GANADO", liquidacion


def probar_tolima_millonarios_corners_y_tarjetas():
    partido = {"fecha": "2026-11-08", "local": "Tolima", "visitante": "Millonarios"}
    casos = [
        ({"tipo": "corners", "direccion": "mas", "linea": 9.5}, "Tolima 2-1 Millonarios: 11 córners totales", 11, "GANADO"),
        ({"tipo": "tarjetas", "direccion": "mas", "linea": 4.5}, "Tolima 2-1 Millonarios: 4 tarjetas", 4, "PERDIDO"),
    ]
    for mercado, texto, total, esperado in casos:
        dato = buscar_estadistica_google(partido, mercado, _buscar_con(texto))
        assert dato and dato["total"] == total, dato
        resultado = {"estado": "finalizado", "corners_total": None, "tarjetas_total": None}
        resultado["corners_total" if mercado["tipo"] == "corners" else "tarjetas_total"] = dato["total"]
        liquidacion = liquidar_mercado(resultado, mercado)
        assert liquidacion["estado"] == esperado, liquidacion


def probar_no_inventa_si_sin_total():
    partido = {"local": "Tolima", "visitante": "Millonarios"}
    assert extraer_total("Tolima 2-1 Millonarios final", "corners", partido) is None
    dato = buscar_estadistica_google(
        partido,
        {"tipo": "corners"},
        lambda consulta: [{"title": "Tolima vs Millonarios", "text": "Partido finalizado 2-1", "url": "https://example.com"}],
    )
    assert dato is None


def probar_suma_los_totales_por_equipo():
    partido = {"local": "Deportes Tolima", "visitante": "Millonarios"}
    texto = "Deportes Tolima 2-1 Millonarios. Córners: 3 para Deportes Tolima y 3 para Millonarios. Tarjetas: Deportes Tolima 5 amarillas; Millonarios 4 amarillas."
    assert extraer_total(texto, "corners", partido) == 6
    assert extraer_total(texto, "tarjetas", partido) == 9


def probar_lee_el_primer_resultado_de_google():
    html = """
    <div class="MjjYud"><a href="https://stats.example/match">Tolima vs Millonarios</a>
    <div>Final: Tolima 2-1 Millonarios. Total corners: 11.</div></div>
    <div class="MjjYud"><a href="https://wrong.example">Otro partido 99 corners</a></div>
    """
    parser = _GoogleParser()
    parser.feed(html)
    assert len(parser.results) == 2, parser.results
    first = parser.results[0]
    assert first["url"] == "https://stats.example/match", first
    assert extraer_total(first["text"], "corners", {"local": "Tolima", "visitante": "Millonarios"}) == 11


def main():
    pruebas = [
        ("Consultas exactas por mercado", probar_consultas_por_mercado),
        ("Alianza vs Llaneros: 5 tarjetas", probar_alianza_llaneros_cinco_tarjetas),
        ("Tolima vs Millonarios: 11 córners y 4 tarjetas", probar_tolima_millonarios_corners_y_tarjetas),
        ("Sin estadística explícita queda pendiente", probar_no_inventa_si_sin_total),
        ("Suma de córners y tarjetas reportados por equipo", probar_suma_los_totales_por_equipo),
        ("Lectura del primer resultado de Google", probar_lee_el_primer_resultado_de_google),
    ]
    pasaron = 0
    for nombre, prueba in pruebas:
        try:
            prueba()
            pasaron += 1
            print("✅ PASÓ - {}".format(nombre))
        except Exception as error:
            print("❌ FALLÓ - {}: {}".format(nombre, error))
    print("Google Stats: {}/{} pruebas pasaron".format(pasaron, len(pruebas)))
    if pasaron != len(pruebas):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
