"""
Tests del fallback de partidos huérfanos en motor.descargar_resultados.

Cubre los 3 escenarios pedidos por la especificación:
  1. Huérfano con resultado FT en API-Football  → se guarda con _fuente='api_football_fallback'.
  2. Huérfano sin resultado en API-Football    → queda como 'pendiente'.
  3. Partido dentro de ventana (no huérfano)   → no usa fallback (lo deja intacto).
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from motor.descargar_resultados import (
    UMBRAL_HUERFANO_DEFAULT,
    _aplicar_fallback_huerfanos,
    _build_match_dir_index,
    _build_nombre_map,
)


# ── Fixtures de calendario y mapas ────────────────────────────────────────────

AHORA = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

# Fechas elegidas para que cada partido caiga en un día UTC distinto, lo que nos
# permite distinguir qué fechas pide el fallback (clave para los tests).
#   Partido 1: 2026-06-13 19:00  → huérfano (~41 h, > 4 h)
#   Partido 2: 2026-06-14 19:00  → huérfano (~17 h, > 4 h)
#   Partido 3: 2026-06-15 10:00  → NO huérfano (2 h, en ventana)
CALENDARIO = {
    "partidos": [
        {"id": 1, "fase": "grupos", "jornada": "J1", "grupo": "A",
         "local": "Mexico", "visitante": "South Africa",
         "fecha_hora_utc": "2026-06-13T19:00:00Z"},
        {"id": 2, "fase": "grupos", "jornada": "J1", "grupo": "B",
         "local": "Canada", "visitante": "Bosnia-Herzegovina",
         "fecha_hora_utc": "2026-06-14T19:00:00Z"},
        {"id": 3, "fase": "grupos", "jornada": "J1", "grupo": "C",
         "local": "Brazil", "visitante": "Morocco",
         "fecha_hora_utc": "2026-06-15T10:00:00Z"},
    ]
}

EQUIVALENCIAS = {
    "selecciones": [
        {"nombre_openfootball": "Mexico", "nombre_excel": "México", "aliases_es": []},
        {"nombre_openfootball": "South Africa", "nombre_excel": "Sudáfrica", "aliases_es": []},
        {"nombre_openfootball": "Canada", "nombre_excel": "Canadá", "aliases_es": []},
        {"nombre_openfootball": "Bosnia-Herzegovina", "nombre_excel": "Bosnia y Herzegovina",
         "aliases_es": ["Bosnia & Herzegovina"]},
        {"nombre_openfootball": "Brazil", "nombre_excel": "Brasil", "aliases_es": []},
        {"nombre_openfootball": "Morocco", "nombre_excel": "Marruecos", "aliases_es": []},
    ]
}

MATCH_DIR_IDX = _build_match_dir_index(CALENDARIO)
NOMBRE_MAP    = _build_nombre_map(EQUIVALENCIAS)


def fixture_ft(home: str, away: str, gh: int, ga: int) -> dict:
    """Construye un fixture de API-Football en estado FT con marcador dado."""
    return {
        "fixture": {"status": {"short": "FT"}},
        "teams":   {"home": {"name": home}, "away": {"name": away}},
        "goals":   {"home": gh, "away": ga},
    }


def fixture_live(home: str, away: str, gh: int, ga: int) -> dict:
    """Fixture en juego (no debería ser tratado como huérfano resuelto)."""
    return {
        "fixture": {"status": {"short": "2H"}},
        "teams":   {"home": {"name": home}, "away": {"name": away}},
        "goals":   {"home": gh, "away": ga},
    }


def marcador_pendiente(match_id: int) -> dict:
    return {"match_id": match_id, "estado": "pendiente"}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_huerfano_con_resultado_en_api_se_guarda():
    """
    Partido 1 lleva 6 h pendiente; API-Football devuelve Mexico 3-1 South Africa (FT).
    → marcador 1 queda 'finalizado' 3-1 con _fuente='api_football_fallback'.
    """
    marcadores = [marcador_pendiente(1), marcador_pendiente(2), marcador_pendiente(3)]

    llamadas: list[tuple[str, str]] = []
    def fetch_dia_stub(api_key: str, fecha: str) -> list[dict]:
        llamadas.append((api_key, fecha))
        # Sólo respondemos para la fecha del partido 1 (06-13)
        if fecha == "2026-06-13":
            return [fixture_ft("Mexico", "South Africa", 3, 1)]
        return []

    nuevos, n_huerfanos, n_encontrados = _aplicar_fallback_huerfanos(
        marcadores, CALENDARIO, MATCH_DIR_IDX, NOMBRE_MAP,
        api_key="dummy", ahora=AHORA, fetch_dia=fetch_dia_stub,
        log=lambda *_: None,
    )

    # 2 huérfanos (matches 1 y 2), 1 encontrado (match 1)
    assert n_huerfanos == 2
    assert n_encontrados == 1

    m1 = next(m for m in nuevos if m["match_id"] == 1)
    assert m1["estado"]          == "finalizado"
    assert m1["goles_local"]     == 3
    assert m1["goles_visitante"] == 1
    assert m1["_fuente"]         == "api_football_fallback"

    # Partidos 2 y 3 intactos
    m2 = next(m for m in nuevos if m["match_id"] == 2)
    m3 = next(m for m in nuevos if m["match_id"] == 3)
    assert m2["estado"] == "pendiente" and "_fuente" not in m2
    assert m3["estado"] == "pendiente" and "_fuente" not in m3

    # Llamó a la API para las 2 fechas de huérfanos (06-13 y 06-14),
    # pero NO para la del partido 3 (06-15, dentro de ventana).
    fechas_llamadas = {f for _, f in llamadas}
    assert fechas_llamadas == {"2026-06-13", "2026-06-14"}


def test_huerfano_sin_resultado_en_api_queda_pendiente():
    """
    Partidos 1 y 2 huérfanos; la API devuelve datos pero ninguno coincide o
    ninguno está en estado FT → ambos siguen 'pendiente' y no aparece _fuente.
    """
    marcadores = [marcador_pendiente(1), marcador_pendiente(2), marcador_pendiente(3)]

    def fetch_dia_stub(api_key: str, fecha: str) -> list[dict]:
        # Devolvemos fixtures de partidos en juego (no FT) para verificar que
        # el fallback solo acepta finalizados.
        return [fixture_live("Mexico", "South Africa", 1, 0)]

    nuevos, n_huerfanos, n_encontrados = _aplicar_fallback_huerfanos(
        marcadores, CALENDARIO, MATCH_DIR_IDX, NOMBRE_MAP,
        api_key="dummy", ahora=AHORA, fetch_dia=fetch_dia_stub,
        log=lambda *_: None,
    )

    assert n_huerfanos    == 2
    assert n_encontrados  == 0

    for m in nuevos:
        assert m["estado"] == "pendiente"
        assert "_fuente"      not in m
        assert "goles_local"  not in m


def test_partido_en_ventana_no_usa_fallback():
    """
    Solo el partido 3 (empezó hace 2 h, en ventana de juego) está pendiente.
    Los 1 y 2 no están en la lista de marcadores. La API se prepara para
    devolver datos pero el fallback NO debe llamarla porque no hay huérfanos.
    """
    # Marcador en juego para el partido 3; los otros dos NO existen aún en marcadores
    marcadores = [
        {"match_id": 3, "estado": "en_juego", "goles_local": 0, "goles_visitante": 0},
    ]

    llamadas: list[tuple[str, str]] = []
    def fetch_dia_stub(api_key: str, fecha: str) -> list[dict]:
        llamadas.append((api_key, fecha))
        return [fixture_ft("Brazil", "Morocco", 2, 1)]

    nuevos, n_huerfanos, n_encontrados = _aplicar_fallback_huerfanos(
        marcadores, CALENDARIO, MATCH_DIR_IDX, NOMBRE_MAP,
        api_key="dummy", ahora=AHORA, fetch_dia=fetch_dia_stub,
        log=lambda *_: None,
    )

    assert n_huerfanos   == 0
    assert n_encontrados == 0
    assert llamadas      == []   # No se hizo NINGUNA llamada a la API

    # El marcador del partido 3 sigue 'en_juego' tal cual, sin _fuente fallback
    m3 = nuevos[0]
    assert m3["estado"] == "en_juego"
    assert "_fuente"    not in m3


# ── Edge: umbral exacto + huérfano cerca del límite ───────────────────────────

def test_huerfano_justo_en_el_limite_no_se_considera():
    """
    Un partido exactamente en el límite (AHORA - 4h) NO debe considerarse
    huérfano (criterio estricto: fecha < ahora - umbral).
    """
    cal = {
        "partidos": [
            {"id": 1, "fase": "grupos", "jornada": "J1", "grupo": "A",
             "local": "Mexico", "visitante": "South Africa",
             "fecha_hora_utc": (AHORA - UMBRAL_HUERFANO_DEFAULT).strftime("%Y-%m-%dT%H:%M:%SZ")},
        ]
    }
    midx = _build_match_dir_index(cal)
    marcadores = [marcador_pendiente(1)]

    llamadas: list[str] = []
    def fetch_dia_stub(api_key: str, fecha: str) -> list[dict]:
        llamadas.append(fecha)
        return []

    _, n_huerfanos, n_encontrados = _aplicar_fallback_huerfanos(
        marcadores, cal, midx, NOMBRE_MAP,
        api_key="dummy", ahora=AHORA, fetch_dia=fetch_dia_stub,
        log=lambda *_: None,
    )
    assert n_huerfanos   == 0
    assert n_encontrados == 0
    assert llamadas      == []


# ── Edge: respeta fechas_ya_consultadas (evita duplicar cuota) ───────────────

def test_fallback_respeta_fechas_ya_consultadas():
    """
    Si una fecha ya fue consultada por el bloque en-ventana, el fallback no la
    vuelve a pedir (preservación de cuota).
    """
    marcadores = [marcador_pendiente(1)]   # partido 1 jugó el 13-jun (huérfano)
    fecha_huerfano = "2026-06-13"

    llamadas: list[str] = []
    def fetch_dia_stub(api_key: str, fecha: str) -> list[dict]:
        llamadas.append(fecha)
        return [fixture_ft("Mexico", "South Africa", 1, 0)]

    _, n_huerfanos, n_encontrados = _aplicar_fallback_huerfanos(
        marcadores, CALENDARIO, MATCH_DIR_IDX, NOMBRE_MAP,
        api_key="dummy", ahora=AHORA, fetch_dia=fetch_dia_stub,
        fechas_ya_consultadas={fecha_huerfano},
        log=lambda *_: None,
    )
    assert n_huerfanos   == 1      # sigue contándose como huérfano
    assert n_encontrados == 0      # pero no se rescata (no se llama API)
    assert llamadas      == []     # no hubo llamada
