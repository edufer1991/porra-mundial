"""
Test de integración: Mundial 2026 completo (sintético).

Construye un torneo ficticio con bracket completo (Round of 32 → Final),
lo parsea con descargar_resultados y lo puntúa con puntuar.
Verifica conjuntos por ronda, nombres canónicos y puntuación acumulativa.

Ejecutar:
  pytest tests/test_integracion_2026.py -v -s   # con desglose
  python tests/test_integracion_2026.py          # solo desglose
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from motor.descargar_resultados import (
    RONDAS_2026,
    _build_match_dir_index,
    _build_nombre_map,
    parsear_openfootball,
)
from motor.puntuar import puntuar_participante, ordenar_clasificacion


# ── Bracket sintético ─────────────────────────────────────────────────────────
# Bosnia aparece como alias para probar la resolución de nombres

R32 = [  # (team1, team2, [g1, g2])  → winner = equipo con más goles
    ("South Africa",  "Qatar",               [2, 0]),
    ("Germany",       "South Korea",          [3, 1]),
    ("Netherlands",   "Morocco",              [2, 0]),
    ("Brazil",        "Japan",                [2, 1]),
    ("France",        "Bosnia & Herzegovina", [3, 1]),  # alias → Bosnia-Herzegovina
    ("Ivory Coast",   "Senegal",              [0, 1]),
    ("Mexico",        "Scotland",             [2, 0]),
    ("England",       "Sweden",               [1, 0]),
    ("USA",           "Ecuador",              [2, 0]),
    ("Belgium",       "Saudi Arabia",         [3, 0]),
    ("Colombia",      "Croatia",              [2, 1]),
    ("Spain",         "Algeria",              [2, 0]),
    ("Canada",        "Turkey",               [1, 0]),
    ("Argentina",     "Uruguay",              [2, 1]),
    ("Portugal",      "Paraguay",             [3, 0]),
    ("Norway",        "Egypt",                [2, 1]),
]

R16 = [
    ("Germany",      "France",       [2, 1]),
    ("South Africa", "Netherlands",  [0, 2]),
    ("Brazil",       "Senegal",      [3, 0]),
    ("Mexico",       "England",      [0, 1]),
    ("Colombia",     "Spain",        [0, 2]),
    ("USA",          "Belgium",      [1, 2]),
    ("Argentina",    "Norway",       [3, 0]),
    ("Canada",       "Portugal",     [0, 2]),
]

QF = [
    ("Germany",   "Netherlands", [2, 1]),
    ("Spain",     "Belgium",     [2, 0]),
    ("Brazil",    "England",     [2, 1]),
    ("Argentina", "Portugal",    [1, 0]),
]

SF = [
    ("Germany",   "Spain",      [1, 2]),  # Spain wins
    ("Brazil",    "Argentina",  [0, 1]),  # Argentina wins
]

TERCERO = ("Germany", "Brazil", [2, 1])   # Germany 3rd

FINAL = ("Spain", "Argentina",            # Argentina wins on pens
         {"ft": [2, 2], "et": [3, 3], "p": [3, 4]})

HONOR_REAL = {
    "campeon":    "Argentina",
    "subcampeon": "Spain",
    "tercero":    "Germany",
    "cuarto":     "Brazil",
}

# Nombres canónicos esperados por ronda tras la resolución de aliases
EXPECTED_1_16 = sorted([
    "South Africa", "Qatar", "Germany", "South Korea",
    "Netherlands", "Morocco", "Brazil", "Japan",
    "France", "Bosnia-Herzegovina",          # alias resuelto
    "Ivory Coast", "Senegal", "Mexico", "Scotland",
    "England", "Sweden", "USA", "Ecuador",
    "Belgium", "Saudi Arabia", "Colombia", "Croatia",
    "Spain", "Algeria", "Canada", "Turkey",
    "Argentina", "Uruguay", "Portugal", "Paraguay",
    "Norway", "Egypt",
])

EXPECTED_1_8 = sorted([
    t1 if g1 > g2 else t2
    for t1, t2, (g1, g2) in R32
    # Bosnia alias: France won that match, Bosnia not in 1/8
])
# Correct: replace "Bosnia & Herzegovina" winner → France already listed as t1

EXPECTED_1_8 = sorted([
    "South Africa", "Germany", "Netherlands", "Brazil",
    "France", "Senegal", "Mexico", "England",
    "USA", "Belgium", "Colombia", "Spain",
    "Canada", "Argentina", "Portugal", "Norway",
])

EXPECTED_1_4 = sorted([
    t1 if g1 > g2 else t2
    for t1, t2, (g1, g2) in R16
])  # Germany, Netherlands, Brazil, England, Spain, Belgium, Argentina, Portugal

EXPECTED_SEMIS = sorted([
    t1 if g1 > g2 else t2
    for t1, t2, (g1, g2) in QF
])  # Germany, Spain, Brazil, Argentina

EXPECTED_FINAL = ["Argentina", "Spain"]


# ── Constructores de datos sintéticos ─────────────────────────────────────────

def _build_of_json(calendario: dict) -> dict:
    """Genera un JSON openfootball 2026 completo con resultados ficticios."""
    matches = []

    jornada_round = {"J1": "Matchday 1", "J2": "Matchday 2", "J3": "Matchday 3"}
    for p in calendario["partidos"]:
        if p["fase"] != "grupos":
            continue
        score = [2, 0] if p["id"] == 1 else [1, 0]
        matches.append({
            "round": jornada_round[p["jornada"]],
            "group": f"Group {p['grupo']}",
            "team1": p["local"],
            "team2": p["visitante"],
            "score": {"ft": score, "ht": [score[0] // 2, 0]},
            "date": "2026-06-15",
            "time": "20:00",
        })

    for t1, t2, score in R32:
        matches.append({
            "round": "Round of 32",
            "team1": t1, "team2": t2,
            "score": {"ft": score},
            "date": "2026-07-01",
        })
    for t1, t2, score in R16:
        matches.append({
            "round": "Round of 16",
            "team1": t1, "team2": t2,
            "score": {"ft": score},
            "date": "2026-07-05",
        })
    for t1, t2, score in QF:
        matches.append({
            "round": "Quarter-finals",
            "team1": t1, "team2": t2,
            "score": {"ft": score},
            "date": "2026-07-10",
        })
    for t1, t2, score in SF:
        matches.append({
            "round": "Semi-finals",
            "team1": t1, "team2": t2,
            "score": {"ft": score},
            "date": "2026-07-14",
        })
    t1, t2, score = TERCERO
    matches.append({
        "round": "Match for third place",
        "team1": t1, "team2": t2,
        "score": {"ft": score},
        "date": "2026-07-18",
    })
    t1, t2, score_obj = FINAL
    matches.append({
        "round": "Final",
        "team1": t1, "team2": t2,
        "score": score_obj,
        "date": "2026-07-19",
    })

    return {"name": "World Cup 2026 (sintético)", "matches": matches}


def _pron_perfecto(clasificados_real: dict) -> dict:
    """Pronóstico perfecto: acierta todos los clasificados, honor y goleador."""
    return {
        "nickname": "Perfecto",
        "porra": "amigos",
        "pronosticos": {
            "grupos": [{
                "match_id": 1, "grupo": "A", "jornada": "J1",
                "local": "Mexico", "visitante": "South Africa",
                "prediccion": {"signo": "1", "goles_local": 2, "goles_visitante": 0},
            }],
            "clasificados": {k: list(v) for k, v in clasificados_real.items()},
            "honor": HONOR_REAL.copy(),
            "premios": {"goleador": "Lautaro Martinez", "mvp": None, "portero": None},
        },
    }


def _pron_finalistas() -> dict:
    """Solo predice los dos finalistas en todas las rondas."""
    bracket = {r: ["Spain", "Argentina"]
               for r in ("1/16", "1/8", "1/4", "semis", "final")}
    return {
        "nickname": "SoloFinalistas",
        "porra": "amigos",
        "pronosticos": {
            "grupos": [],
            "clasificados": bracket,
            "honor": {"campeon": "Argentina", "subcampeon": "Spain",
                      "tercero": None, "cuarto": None},
            "premios": {"goleador": None, "mvp": None, "portero": None},
        },
    }


def _pron_semifinalistas() -> dict:
    """Predice los 4 semifinalistas en 1/16..semis; finalistas en final."""
    sf4 = ["Germany", "Spain", "Brazil", "Argentina"]
    return {
        "nickname": "SemiPerfecto",
        "porra": "amigos",
        "pronosticos": {
            "grupos": [],
            "clasificados": {
                "1/16":  sf4, "1/8": sf4, "1/4": sf4,
                "semis": sf4, "final": ["Spain", "Argentina"],
            },
            "honor": HONOR_REAL.copy(),
            "premios": {"goleador": None, "mvp": None, "portero": None},
        },
    }


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def calendario():
    with open(ROOT / "datos" / "calendario.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def equivalencias():
    with open(ROOT / "datos" / "equivalencias_equipos.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def reglas():
    with open(ROOT / "config" / "reglas.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def resultados(calendario, equivalencias):
    of_json       = _build_of_json(calendario)
    match_dir_idx = _build_match_dir_index(calendario)
    nombre_map    = _build_nombre_map(equivalencias)
    parsed        = parsear_openfootball(of_json, match_dir_idx, RONDAS_2026,
                                         nombre_map=nombre_map)
    parsed.pop("stats", None)
    parsed["premios"] = {"goleador": "Lautaro Martinez", "mvp": None, "portero": None}
    return parsed


# ── Tests: extracción de datos ────────────────────────────────────────────────

def test_marcadores_grupo_count(resultados):
    """72 partidos de grupo, todos finalizados."""
    assert len(resultados["marcadores"]) == 72
    assert all(m["estado"] == "finalizado" for m in resultados["marcadores"])


def test_marcador_match1_correcto(resultados):
    """Partido 1: Mexico 2-0 South Africa."""
    m1 = next(m for m in resultados["marcadores"] if m["match_id"] == 1)
    assert m1["goles_local"] == 2
    assert m1["goles_visitante"] == 0


def test_clasificados_counts(resultados):
    c = resultados["clasificados"]
    assert len(c["1/16"])  == 32, f"1/16 esperado 32, obtenido {len(c['1/16'])}"
    assert len(c["1/8"])   == 16, f"1/8 esperado 16, obtenido {len(c['1/8'])}"
    assert len(c["1/4"])   == 8,  f"1/4 esperado 8, obtenido {len(c['1/4'])}"
    assert len(c["semis"]) == 4,  f"semis esperado 4, obtenido {len(c['semis'])}"
    assert len(c["final"]) == 2,  f"final esperado 2, obtenido {len(c['final'])}"


def test_equipos_1_16_canonicos(resultados):
    """Los 32 equipos de 1/16 coinciden exactamente con los nombres canónicos."""
    assert sorted(resultados["clasificados"]["1/16"]) == EXPECTED_1_16


def test_equipos_1_8_canonicos(resultados):
    assert sorted(resultados["clasificados"]["1/8"]) == EXPECTED_1_8


def test_equipos_1_4_canonicos(resultados):
    assert sorted(resultados["clasificados"]["1/4"]) == sorted(EXPECTED_1_4)


def test_equipos_semis_canonicos(resultados):
    assert sorted(resultados["clasificados"]["semis"]) == sorted(EXPECTED_SEMIS)


def test_equipos_final_canonicos(resultados):
    assert sorted(resultados["clasificados"]["final"]) == sorted(EXPECTED_FINAL)


def test_bosnia_alias_resuelto(resultados):
    """'Bosnia & Herzegovina' en el JSON de openfootball → 'Bosnia-Herzegovina' canónico."""
    assert "Bosnia-Herzegovina"    in resultados["clasificados"]["1/16"]
    assert "Bosnia & Herzegovina" not in resultados["clasificados"]["1/16"]


def test_sin_placeholders_en_clasificados(resultados):
    from motor.descargar_resultados import _es_placeholder
    for ronda, teams in resultados["clasificados"].items():
        for t in teams:
            assert not _es_placeholder(t), f"Placeholder en {ronda}: {t}"


def test_honor(resultados):
    h = resultados["honor"]
    assert h["campeon"]    == "Argentina"
    assert h["subcampeon"] == "Spain"
    assert h["tercero"]    == "Germany"
    assert h["cuarto"]     == "Brazil"


# ── Tests: puntuación ─────────────────────────────────────────────────────────

def test_participante_perfecto(resultados, reglas):
    m = puntuar_participante(_pron_perfecto(resultados["clasificados"]),
                             resultados, reglas)
    # grupos: signo(+3) + local2(+3) + visitante0(+1) = 7
    assert m["puntos_grupos"]        == 7,   m["puntos_grupos"]
    # eliminatorias: 32×5 + 16×10 + 8×15 + 4×20 + 2×30 = 580
    assert m["puntos_eliminatorias"] == 580, m["puntos_eliminatorias"]
    # honor: 50+40+30+20 = 140
    assert m["puntos_honor"]         == 140, m["puntos_honor"]
    # premios: goleador correcto = 25
    assert m["puntos_premios"]       == 25,  m["puntos_premios"]
    assert m["advertencias_premios"] == []
    assert m["puntos_total"]         == 752
    assert m["puntos_fase_previa"]   == 7
    assert m["puntos_fase_eliminatoria"] == 720   # 580 + 140


def test_participante_finalistas(resultados, reglas):
    """Predice solo los 2 finalistas en todas las rondas → 2×80=160 elim + 90 honor."""
    m = puntuar_participante(_pron_finalistas(), resultados, reglas)
    assert m["puntos_grupos"]        == 0
    assert m["puntos_eliminatorias"] == 160   # 2 × (5+10+15+20+30)
    assert m["puntos_honor"]         == 90    # campeon + subcampeon
    assert m["puntos_total"]         == 250


def test_participante_semifinalistas(resultados, reglas):
    """Predice los 4 semifinalistas en todas las rondas."""
    m = puntuar_participante(_pron_semifinalistas(), resultados, reglas)
    # 4×5 + 4×10 + 4×15 + 4×20 + 2×30 = 20+40+60+80+60 = 260
    assert m["puntos_eliminatorias"] == 260
    assert m["puntos_honor"]         == 140   # acerta los 4 puestos
    assert m["puntos_total"]         == 400


def test_acumulativo_argentina(resultados, reglas):
    """Argentina llega a la final: su aportación sola = 5+10+15+20+30 = 80 pts."""
    pron = {
        "nickname": "ArgSolo", "porra": "amigos",
        "pronosticos": {
            "grupos": [],
            "clasificados": {r: ["Argentina"]
                             for r in ("1/16", "1/8", "1/4", "semis", "final")},
            "honor": {"campeon": None, "subcampeon": None,
                      "tercero": None, "cuarto": None},
            "premios": {"goleador": None, "mvp": None, "portero": None},
        },
    }
    m = puntuar_participante(pron, resultados, reglas)
    assert m["puntos_eliminatorias"] == 80   # 5+10+15+20+30


def test_clasificacion_orden(resultados, reglas):
    """Perfecto > SemiPerfecto > SoloFinalistas por puntos_total."""
    partic = [
        puntuar_participante(_pron_perfecto(resultados["clasificados"]),
                             resultados, reglas),
        puntuar_participante(_pron_semifinalistas(), resultados, reglas),
        puntuar_participante(_pron_finalistas(), resultados, reglas),
    ]
    ordenados = ordenar_clasificacion(partic)
    nicks = [p["nickname"] for p in ordenados]
    assert nicks == ["Perfecto", "SemiPerfecto", "SoloFinalistas"]
    assert ordenados[0]["posicion"] == 1
    assert ordenados[1]["posicion"] == 2
    assert ordenados[2]["posicion"] == 3


# ── Desglose legible (también ejecutable directamente) ────────────────────────

def _imprimir_desglose(resultados: dict, reglas: dict) -> None:
    c = resultados["clasificados"]
    h = resultados["honor"]

    print("\n" + "=" * 60)
    print("RESUMEN TORNEO SINTETICO 2026")
    print("=" * 60)
    print(f"  1/16  (R32) : {len(c['1/16'])} equipos")
    print(f"  1/8   (R16) : {len(c['1/8'])} equipos")
    print(f"  1/4   (QF)  : {len(c['1/4'])} equipos  {sorted(c['1/4'])}")
    print(f"  Semis       : {len(c['semis'])} equipos  {sorted(c['semis'])}")
    print(f"  Final       : {len(c['final'])} equipos  {sorted(c['final'])}")
    print(f"  Honor       : "
          f"1={h['campeon']}  2={h['subcampeon']}  "
          f"3={h['tercero']}  4={h['cuarto']}")
    print(f"  Bosnia alias: 'Bosnia & Herzegovina' -> "
          f"{'Bosnia-Herzegovina' if 'Bosnia-Herzegovina' in c['1/16'] else 'ERROR'}")

    participantes_def = [
        ("Perfecto",        _pron_perfecto(c)),
        ("SoloFinalistas",  _pron_finalistas()),
        ("SemiPerfecto",    _pron_semifinalistas()),
    ]

    for nombre, pron in participantes_def:
        m = puntuar_participante(pron, resultados, reglas)
        print(f"\n{'=' * 60}")
        print(f"PARTICIPANTE: {nombre}")
        print(f"{'=' * 60}")
        print(f"  Grupos              : {m['puntos_grupos']:>5} pts")
        R = reglas["eliminatorias"]["puntos_por_ronda"]
        pred_c = pron["pronosticos"]["clasificados"]
        for ronda in ("1/16", "1/8", "1/4", "semis", "final"):
            pred_set = {e.strip().lower() for e in pred_c.get(ronda, [])}
            real_set = {e.strip().lower() for e in c.get(ronda, [])}
            matches  = len(pred_set & real_set)
            pts      = matches * R[ronda]
            print(f"  Elim {ronda:<5} {matches:>2}/{len(real_set):<2}"
                  f" x {R[ronda]:>2}  = {pts:>4} pts")
        print(f"  Eliminatorias total : {m['puntos_eliminatorias']:>5} pts")
        print(f"  Honor               : {m['puntos_honor']:>5} pts")
        print(f"  Premios             : {m['puntos_premios']:>5} pts")
        print(f"  -----------------------------")
        print(f"  TOTAL               : {m['puntos_total']:>5} pts")
        print(f"  fase_previa         : {m['puntos_fase_previa']:>5}")
        print(f"  fase_eliminatoria   : {m['puntos_fase_eliminatoria']:>5}")

    print()


if __name__ == "__main__":
    import json as _json
    _cal  = _json.load(open(ROOT / "datos" / "calendario.json",        encoding="utf-8"))
    _eq   = _json.load(open(ROOT / "datos" / "equivalencias_equipos.json", encoding="utf-8"))
    _reg  = _json.load(open(ROOT / "config" / "reglas.json",           encoding="utf-8"))

    _of   = _build_of_json(_cal)
    _idx  = _build_match_dir_index(_cal)
    _nmap = _build_nombre_map(_eq)
    _res  = parsear_openfootball(_of, _idx, RONDAS_2026, nombre_map=_nmap)
    _res.pop("stats", None)
    _res["premios"] = {"goleador": "Lautaro Martinez", "mvp": None, "portero": None}

    _imprimir_desglose(_res, _reg)
