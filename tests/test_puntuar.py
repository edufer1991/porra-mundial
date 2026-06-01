"""
Tests del motor de puntuación (Fase 2).

Cubren:
  - Ejemplo de grupos: 2|1-2 con real 1-2 → 8 pts
  - Ejemplo de grupos: 2|1-2 con real 2-1 → 0 pts
  - Acumulado de un finalista: 5+10+15+20+30 = 80 pts
  - Honor: campeón acertado = +50
  - Desempate por fase eliminatoria
  - Reparto cuando el empate persiste
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from motor.puntuar import (
    ordenar_clasificacion,
    puntuar_eliminatorias,
    puntuar_grupos,
    puntuar_honor,
    puntuar_participante,
    puntuar_premios,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture
def reglas():
    with open(ROOT / "config" / "reglas.json", encoding="utf-8") as f:
        return json.load(f)


# ── Grupos ───────────────────────────────────────────────────────────────────
def test_grupos_ejemplo_8_pts(reglas):
    """Pronóstico 2|1-2 + real 1-2 → 3 + (1+1) + (2+1) = 8 pts."""
    pron = [{
        "match_id": 1, "grupo": "A", "jornada": "J1",
        "local": "Mexico", "visitante": "South Africa",
        "prediccion": {"signo": "2", "goles_local": 1, "goles_visitante": 2},
    }]
    marc = {1: {"match_id": 1, "estado": "finalizado", "goles_local": 1, "goles_visitante": 2}}
    assert puntuar_grupos(pron, marc, reglas) == 8


def test_grupos_ejemplo_0_pts(reglas):
    """Pronóstico 2|1-2 + real 2-1 → signo distinto, goles invertidos → 0 pts."""
    pron = [{
        "match_id": 1, "grupo": "A", "jornada": "J1",
        "local": "Mexico", "visitante": "South Africa",
        "prediccion": {"signo": "2", "goles_local": 1, "goles_visitante": 2},
    }]
    marc = {1: {"match_id": 1, "estado": "finalizado", "goles_local": 2, "goles_visitante": 1}}
    assert puntuar_grupos(pron, marc, reglas) == 0


def test_grupos_signo_correcto_goles_no(reglas):
    """Pronóstico 1|2-0 + real 3-1 → signo OK pero goles no → +3."""
    pron = [{
        "match_id": 1, "grupo": "A", "jornada": "J1",
        "local": "X", "visitante": "Y",
        "prediccion": {"signo": "1", "goles_local": 2, "goles_visitante": 0},
    }]
    marc = {1: {"match_id": 1, "estado": "finalizado", "goles_local": 3, "goles_visitante": 1}}
    assert puntuar_grupos(pron, marc, reglas) == 3


def test_grupos_solo_acierta_visitante(reglas):
    """Pronóstico 1|3-0 + real 0-0 → signo no, goles local no, goles visit sí 0==0 → +(0+1) = 1."""
    pron = [{
        "match_id": 1, "grupo": "A", "jornada": "J1",
        "local": "X", "visitante": "Y",
        "prediccion": {"signo": "1", "goles_local": 3, "goles_visitante": 0},
    }]
    marc = {1: {"match_id": 1, "estado": "finalizado", "goles_local": 0, "goles_visitante": 0}}
    assert puntuar_grupos(pron, marc, reglas) == 1


def test_grupos_no_puntua_si_pendiente(reglas):
    """Si el partido está pendiente, no puntúa aunque haya pronóstico."""
    pron = [{
        "match_id": 1, "grupo": "A", "jornada": "J1",
        "local": "X", "visitante": "Y",
        "prediccion": {"signo": "1", "goles_local": 2, "goles_visitante": 0},
    }]
    marc = {1: {"match_id": 1, "estado": "pendiente"}}
    assert puntuar_grupos(pron, marc, reglas) == 0


def test_grupos_no_puntua_si_sin_prediccion(reglas):
    """Si no hay pronóstico, no puntúa aunque el partido esté finalizado."""
    pron = [{
        "match_id": 1, "grupo": "A", "jornada": "J1",
        "local": "X", "visitante": "Y",
        "prediccion": None,
    }]
    marc = {1: {"match_id": 1, "estado": "finalizado", "goles_local": 2, "goles_visitante": 0}}
    assert puntuar_grupos(pron, marc, reglas) == 0


# ── Eliminatorias (acumulativo) ──────────────────────────────────────────────
def test_eliminatorias_finalista_80_pts(reglas):
    """Una selección que el participante pone en TODAS las rondas y que llega a la final."""
    pred = {
        "1/16":  ["Spain"], "1/8": ["Spain"], "1/4": ["Spain"],
        "semis": ["Spain"], "final": ["Spain"],
    }
    real = {
        "1/16":  ["Spain", "France", "Germany"],
        "1/8":   ["Spain", "France"],
        "1/4":   ["Spain", "France"],
        "semis": ["Spain", "France"],
        "final": ["Spain", "France"],
    }
    assert puntuar_eliminatorias(pred, real, reglas) == 80  # 5+10+15+20+30


def test_eliminatorias_solo_octavos_15_pts(reglas):
    """Equipo que solo llega a octavos: 5 (1/16) + 10 (1/8) = 15."""
    pred = {"1/16": ["Mexico"], "1/8": ["Mexico"], "1/4": ["Mexico"], "semis": [], "final": []}
    real = {"1/16": ["Mexico"], "1/8": ["Mexico"], "1/4": [], "semis": [], "final": []}
    assert puntuar_eliminatorias(pred, real, reglas) == 15


def test_eliminatorias_dos_equipos_finalistas(reglas):
    """Dos finalistas correctos: 80 + 80 = 160."""
    pred = {
        "1/16":  ["Spain", "France"], "1/8": ["Spain", "France"], "1/4": ["Spain", "France"],
        "semis": ["Spain", "France"], "final": ["Spain", "France"],
    }
    real = {
        "1/16":  ["Spain", "France"], "1/8": ["Spain", "France"], "1/4": ["Spain", "France"],
        "semis": ["Spain", "France"], "final": ["Spain", "France"],
    }
    assert puntuar_eliminatorias(pred, real, reglas) == 160


def test_eliminatorias_normaliza_tildes(reglas):
    """Comparación sin tildes ni mayúsculas."""
    pred = {"1/16": ["mexico"], "1/8": [], "1/4": [], "semis": [], "final": []}
    real = {"1/16": ["México"], "1/8": [], "1/4": [], "semis": [], "final": []}
    assert puntuar_eliminatorias(pred, real, reglas) == 5


# ── Honor ────────────────────────────────────────────────────────────────────
def test_honor_solo_campeon(reglas):
    pred = {"campeon": "Spain", "subcampeon": None, "tercero": None, "cuarto": None}
    real = {"campeon": "Spain", "subcampeon": "France", "tercero": "Argentina", "cuarto": "Brazil"}
    assert puntuar_honor(pred, real, reglas) == 50


def test_honor_todos_aciertos(reglas):
    pred = {"campeon": "Spain", "subcampeon": "France", "tercero": "Argentina", "cuarto": "Brazil"}
    real = pred.copy()
    assert puntuar_honor(pred, real, reglas) == 140  # 50+40+30+20


def test_honor_subcampeon_pero_invertido(reglas):
    """Si confundes campeón y subcampeón: 0 pts (no hay puntos por mero acierto de finalistas)."""
    pred = {"campeon": "France", "subcampeon": "Spain", "tercero": None, "cuarto": None}
    real = {"campeon": "Spain", "subcampeon": "France", "tercero": None, "cuarto": None}
    assert puntuar_honor(pred, real, reglas) == 0


# ── Premios ──────────────────────────────────────────────────────────────────
def test_premios_acierto_con_normalizacion(reglas):
    """Comparación sin tildes ni mayúsculas (Mbappé ≡ MBAPPE)."""
    pred = {"goleador": "Mbappé", "mvp": None, "portero": None}
    real = {"goleador": "MBAPPE", "mvp": None, "portero": None}
    pts, adv = puntuar_premios(pred, real, reglas)
    assert pts == 25
    assert adv == []


def test_premios_alias_jugador(reglas):
    """La tabla de alias permite reconocer variantes ortográficas."""
    pred = {"goleador": "Kylian Mbappe", "mvp": None, "portero": None}
    real = {"goleador": "Mbappé", "mvp": None, "portero": None}
    alias = {"mbappe": ["kylian mbappe"]}
    pts, adv = puntuar_premios(pred, real, reglas, alias=alias)
    assert pts == 25
    assert adv == []


def test_premios_advertencia_no_coincidencia(reglas):
    """No-coincidencia genera advertencia para revisión manual."""
    pred = {"goleador": "Haaland", "mvp": None, "portero": None}
    real = {"goleador": "Mbappé", "mvp": None, "portero": None}
    pts, adv = puntuar_premios(pred, real, reglas)
    assert pts == 0
    assert len(adv) == 1
    assert adv[0]["premio"] == "goleador"


# ── Desempate ────────────────────────────────────────────────────────────────
def _participante(nick, total, fase_elim, fase_previa=None):
    """Helper para construir entradas de clasificación con métricas fijas."""
    if fase_previa is None:
        fase_previa = max(0, total - fase_elim)
    return {
        "nickname": nick,
        "porra": "amigos",
        "puntos_grupos":              fase_previa,
        "puntos_eliminatorias":       0,
        "puntos_honor":               0,
        "puntos_premios":             total - fase_previa - fase_elim,
        "puntos_fase_previa":         fase_previa,
        "puntos_fase_eliminatoria":   fase_elim,
        "puntos_total":               total,
        "advertencias_premios":       [],
    }


def test_desempate_por_fase_eliminatoria():
    """A: 100 total (50 grupos + 50 elim). B: 100 total (80 grupos + 20 elim). Gana A."""
    A = _participante("Ana",  total=100, fase_elim=50, fase_previa=50)
    B = _participante("Beto", total=100, fase_elim=20, fase_previa=80)
    ordenados = ordenar_clasificacion([B, A])
    assert ordenados[0]["nickname"] == "Ana"
    assert ordenados[0]["posicion"] == 1
    assert ordenados[0]["empate"] is False
    assert ordenados[1]["nickname"] == "Beto"
    assert ordenados[1]["posicion"] == 2
    assert ordenados[1]["empate"] is False


def test_desempate_persistente_reparto():
    """Mismo total y misma fase eliminatoria → reparto (empate=True, misma posición)."""
    A = _participante("Ana",  total=100, fase_elim=40, fase_previa=60)
    B = _participante("Beto", total=100, fase_elim=40, fase_previa=60)
    ordenados = ordenar_clasificacion([A, B])
    assert ordenados[0]["empate"] is True
    assert ordenados[1]["empate"] is True
    assert ordenados[0]["posicion"] == ordenados[1]["posicion"] == 1


def test_sub_clasificacion_fase_previa():
    """La sub-clasificación de fase previa va por puntos_fase_previa desc, independiente del total."""
    A = _participante("Ana",  total=100, fase_elim=80, fase_previa=20)
    B = _participante("Beto", total=90,  fase_elim=10, fase_previa=80)
    ordenados = ordenar_clasificacion([A, B])
    # Por puntos_total Ana es primera, pero en fase previa Beto la supera
    assert ordenados[0]["nickname"] == "Ana"
    assert ordenados[0]["posicion_fase_previa"] == 2
    assert ordenados[1]["nickname"] == "Beto"
    assert ordenados[1]["posicion_fase_previa"] == 1


# ── Integración: participante completo ───────────────────────────────────────
def test_participante_completo_con_resultados_prueba(reglas):
    """
    Smoke test: un pronóstico mínimo + resultados_prueba.json.
    Solo verifica que la suma de bloques == puntos_total.
    """
    with open(ROOT / "datos" / "resultados_prueba.json", encoding="utf-8") as f:
        resultados = json.load(f)

    pronostico = {
        "nickname": "Tester",
        "porra": "amigos",
        "pronosticos": {
            "grupos": [{
                "match_id": 1, "grupo": "A", "jornada": "J1",
                "local": "Mexico", "visitante": "South Africa",
                "prediccion": {"signo": "2", "goles_local": 1, "goles_visitante": 2},
            }],
            "clasificados": {
                "1/16":  ["Spain", "France"],
                "1/8":   ["Spain", "France"],
                "1/4":   ["Spain"],
                "semis": ["Spain"],
                "final": ["Spain"],
            },
            "honor":   {"campeon": "Spain", "subcampeon": "France", "tercero": None, "cuarto": None},
            "premios": {"goleador": "Mbappe", "mvp": None, "portero": None},
        },
    }
    m = puntuar_participante(pronostico, resultados, reglas)
    # Grupos: partido 1 acierta exacto → 8
    assert m["puntos_grupos"] == 8
    # Eliminatorias: Spain en TODAS las rondas reales (1/16,1/8,1/4,semis,final)=80
    #                France en 1/16,1/8 reales y SOLO 1/16,1/8 pronosticados =5+10=15 → 95
    assert m["puntos_eliminatorias"] == 95
    # Honor: campeón Spain ✓ (+50), subcampeón France ✓ (+40) → 90
    assert m["puntos_honor"] == 90
    # Premios: no coincide "Mbappe" con "Kylian Mbappe" → 0 + advertencia
    assert m["puntos_premios"] == 0
    assert any(a["premio"] == "goleador" for a in m["advertencias_premios"])
    # Total
    assert m["puntos_total"] == 8 + 95 + 90 + 0
    assert m["puntos_fase_previa"] == 8
    assert m["puntos_fase_eliminatoria"] == 95 + 90
