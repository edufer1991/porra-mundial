"""
Tests unitarios para motor/descargar_resultados.py.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from motor.descargar_resultados import (
    RONDAS_2026,
    _build_elim_time_index,
    _build_match_dir_index,
    parsear_openfootball,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _calendario_elim(match_id: int, fecha_hora_utc: str) -> dict:
    """Calendario mínimo: un partido de eliminatoria con fecha concreta."""
    return {
        "partidos": [
            {
                "id": match_id,
                "fase": "1/16",
                "local": "1A",
                "visitante": "2B",
                "fecha_hora_utc": fecha_hora_utc,
            }
        ]
    }


def _of_json_elim(team1: str, team2: str, score_ft: list, date: str, time: str) -> dict:
    """JSON openfootball mínimo: un único partido de eliminatoria."""
    return {
        "matches": [
            {
                "round": "Round of 32",
                "team1": team1,
                "team2": team2,
                "score": {"ft": score_ft},
                "date": date,
                "time": time,
            }
        ]
    }


# ── Tests: _build_elim_time_index ─────────────────────────────────────────────

def test_elim_time_index_excluye_grupos():
    cal = {
        "partidos": [
            {"id": 1, "fase": "grupos",  "fecha_hora_utc": "2026-06-12T00:00:00Z"},
            {"id": 73, "fase": "1/16",   "fecha_hora_utc": "2026-06-28T19:00:00Z"},
        ]
    }
    idx = _build_elim_time_index(cal)
    assert "2026-06-12T00:00:00Z" not in idx
    assert idx["2026-06-28T19:00:00Z"] == 73


def test_elim_time_index_vacio_sin_eliminatorias():
    cal = {"partidos": [{"id": 1, "fase": "grupos", "fecha_hora_utc": "2026-06-12T00:00:00Z"}]}
    assert _build_elim_time_index(cal) == {}


# ── Tests: marcador de eliminatoria en parsear_openfootball ──────────────────

def test_elim_marcador_campos_correctos():
    """Un partido de eliminatoria finalizado genera un marcador con los 5 campos."""
    fecha = "2026-06-28T19:00:00Z"
    match_id = 73
    cal = _calendario_elim(match_id, fecha)
    of_json = _of_json_elim("Argentina", "France", [3, 1], "2026-06-28", "19:00")
    elim_idx = _build_elim_time_index(cal)
    match_dir_idx = _build_match_dir_index(cal)  # vacío (sin grupos)

    result = parsear_openfootball(
        of_json, match_dir_idx, RONDAS_2026, elim_time_idx=elim_idx
    )

    assert len(result["marcadores"]) == 1, "Debe haber exactamente un marcador"
    m = result["marcadores"][0]
    assert m["match_id"] == match_id
    assert m["estado"] == "finalizado"
    assert m["goles_local"] == 3
    assert m["goles_visitante"] == 1
    assert m["local"] == "Argentina"
    assert m["visitante"] == "France"


def test_elim_marcador_sin_idx_no_guarda():
    """Sin elim_time_idx, no se generan marcadores de eliminatoria."""
    cal = _calendario_elim(73, "2026-06-28T19:00:00Z")
    of_json = _of_json_elim("Argentina", "France", [3, 1], "2026-06-28", "19:00")
    match_dir_idx = _build_match_dir_index(cal)

    result = parsear_openfootball(of_json, match_dir_idx, RONDAS_2026)
    assert result["marcadores"] == []


def test_elim_marcador_sin_score_no_guarda():
    """Partido sin score FT no genera marcador."""
    fecha = "2026-06-28T19:00:00Z"
    cal = _calendario_elim(73, fecha)
    elim_idx = _build_elim_time_index(cal)
    of_json = {"matches": [{"round": "Round of 32", "team1": "Argentina",
                             "team2": "France", "date": "2026-06-28", "time": "19:00"}]}
    result = parsear_openfootball(of_json, {}, RONDAS_2026, elim_time_idx=elim_idx)
    assert result["marcadores"] == []


def test_elim_marcador_datetime_no_coincide_no_guarda():
    """Si la fecha del partido no está en el índice, no se guarda marcador."""
    cal = _calendario_elim(73, "2026-06-28T22:00:00Z")  # distinta hora
    elim_idx = _build_elim_time_index(cal)
    of_json = _of_json_elim("Argentina", "France", [3, 1], "2026-06-28", "19:00")
    result = parsear_openfootball(of_json, {}, RONDAS_2026, elim_time_idx=elim_idx)
    assert result["marcadores"] == []


def test_elim_marcador_placeholder_no_guarda():
    """Partido con equipos placeholder no genera marcador (aún no hay equipos reales)."""
    fecha = "2026-06-28T19:00:00Z"
    cal = _calendario_elim(73, fecha)
    elim_idx = _build_elim_time_index(cal)
    of_json = _of_json_elim("1A", "2B", [3, 1], "2026-06-28", "19:00")
    result = parsear_openfootball(of_json, {}, RONDAS_2026, elim_time_idx=elim_idx)
    assert result["marcadores"] == []
