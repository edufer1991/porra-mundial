"""
Tests del motor matejero puntuar_v2.

Cubren (27 tests en total):
  - Grupos marcador: solo signo / signo+dif / exacto / signo fallado / pendiente
  - Posiciones de grupo: acierto / fallo / 12 terceros con 8 que pasan
  - Eliminatoria marcador: solo signo / signo+dif / exacto / signo fallado / penaltis
  - Clasificados por ronda: 1/16, 1/8, 1/4, semis, final (ok y fallado)
  - Honor: cada puesto individual + los cuatro juntos
  - Premios: los tres juntos + fallo
  - Desempate: clasificados+honor mandan; elim_marcadores no cuentan
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from motor.puntuar_v1 import ordenar_clasificacion
from motor.puntuar_v2 import puntuar_participante


# ── Fixtures de calendario mínimo ────────────────────────────────────────────
CAL = [
    {"id": 1,  "fase": "grupos",        "jornada": "J1", "grupo": "A", "local": "Mexico",    "visitante": "South Africa"},
    {"id": 2,  "fase": "grupos",        "jornada": "J1", "grupo": "A", "local": "Argentina", "visitante": "Spain"},
    {"id": 3,  "fase": "grupos",        "jornada": "J1", "grupo": "A", "local": "Brazil",    "visitante": "Germany"},
    {"id": 90, "fase": "1/16",          "jornada": None, "grupo": None, "local": "?", "visitante": "?"},
    {"id": 91, "fase": "1/8",           "jornada": None, "grupo": None, "local": "?", "visitante": "?"},
    {"id": 92, "fase": "1/4",           "jornada": None, "grupo": None, "local": "?", "visitante": "?"},
    {"id": 93, "fase": "semis",         "jornada": None, "grupo": None, "local": "?", "visitante": "?"},
    {"id": 94, "fase": "final",         "jornada": None, "grupo": None, "local": "?", "visitante": "?"},
    {"id": 95, "fase": "tercer_puesto", "jornada": None, "grupo": None, "local": "?", "visitante": "?"},
]

CLAS_VACIAS = {"1/16": [], "1/8": [], "1/4": [], "semis": [], "final": []}


def pron(**kw):
    """Construye un pronóstico mínimo válido."""
    return {
        "nickname": kw.get("nickname", "tester"),
        "porra": "amigos",
        "pronosticos": {
            "grupos":          kw.get("grupos", []),
            "posiciones_grupo": kw.get("posiciones_grupo", []),
            "elim_marcadores": kw.get("elim_marcadores", []),
            "clasificados":    kw.get("clasificados", CLAS_VACIAS.copy()),
            "honor":           kw.get("honor", {}),
            "premios":         kw.get("premios", {}),
        },
    }


def res(**kw):
    """Construye un resultado mínimo válido."""
    return {
        "marcadores":      kw.get("marcadores", []),
        "posiciones_grupo": kw.get("posiciones_grupo", []),
        "clasificados":    kw.get("clasificados", CLAS_VACIAS.copy()),
        "honor":           kw.get("honor", {}),
        "premios":         kw.get("premios", {}),
    }


def calcular(p, r):
    return puntuar_participante(p, r, calendario=CAL)


def grp_detalle(r):
    return r["desglose"]["grupos"]


def pos_detalle(r):
    return r["desglose"]["posiciones_grupo"]


def elim_detalle(r):
    return r["desglose"]["elim_marcadores"]


def clas_detalle(r):
    return r["desglose"]["clasificados"]


def honor_detalle(r):
    return r["desglose"]["honor"]


def premios_detalle(r):
    return r["desglose"]["premios"]


# ── Grupos: marcador ─────────────────────────────────────────────────────────

def test_grupo_solo_signo():
    """Pred 1|3-0, real 1|1-0 → signo OK, diferencia falla → 5 pts."""
    p = pron(grupos=[{"match_id": 1, "local": "Mexico", "visitante": "South Africa",
                      "prediccion": {"signo": "1", "goles_local": 3, "goles_visitante": 0}}])
    r = res(marcadores=[{"match_id": 1, "estado": "finalizado", "goles_local": 1, "goles_visitante": 0}])
    result = calcular(p, r)
    assert grp_detalle(result)["total"] == 5


def test_grupo_signo_mas_diferencia():
    """Pred 1|2-1, real 1|3-2 → signo OK, diferencia OK (1==1), exacto falla → 7 pts."""
    p = pron(grupos=[{"match_id": 1, "local": "Mexico", "visitante": "South Africa",
                      "prediccion": {"signo": "1", "goles_local": 2, "goles_visitante": 1}}])
    r = res(marcadores=[{"match_id": 1, "estado": "finalizado", "goles_local": 3, "goles_visitante": 2}])
    result = calcular(p, r)
    assert grp_detalle(result)["total"] == 7


def test_grupo_exacto():
    """Pred X|1-1, real X|1-1 → pleno (signo+dif+exacto) → 15 pts."""
    p = pron(grupos=[{"match_id": 1, "local": "Mexico", "visitante": "South Africa",
                      "prediccion": {"signo": "X", "goles_local": 1, "goles_visitante": 1}}])
    r = res(marcadores=[{"match_id": 1, "estado": "finalizado", "goles_local": 1, "goles_visitante": 1}])
    result = calcular(p, r)
    assert grp_detalle(result)["total"] == 15


def test_grupo_signo_fallado_diferencia_coincide():
    """Pred 1|3-0, real 2|0-3 → signo falla, aunque la magnitud coincida → 0 pts."""
    p = pron(grupos=[{"match_id": 1, "local": "Mexico", "visitante": "South Africa",
                      "prediccion": {"signo": "1", "goles_local": 3, "goles_visitante": 0}}])
    r = res(marcadores=[{"match_id": 1, "estado": "finalizado", "goles_local": 0, "goles_visitante": 3}])
    result = calcular(p, r)
    assert grp_detalle(result)["total"] == 0


def test_grupo_partido_pendiente():
    """Partido sin resultado ('pendiente') → 0 pts, sin error."""
    p = pron(grupos=[{"match_id": 1, "local": "Mexico", "visitante": "South Africa",
                      "prediccion": {"signo": "1", "goles_local": 2, "goles_visitante": 0}}])
    r = res(marcadores=[{"match_id": 1, "estado": "pendiente"}])
    result = calcular(p, r)
    assert grp_detalle(result)["total"] == 0


# ── Posiciones de grupo ──────────────────────────────────────────────────────

def test_posicion_grupo_acertada():
    """Pronóstico: México 1º del grupo A, real igual → 5 pts."""
    p = pron(posiciones_grupo=[{"grupo": "A", "pos": 1, "equipo": "Mexico"}])
    r = res(posiciones_grupo=[{"grupo": "A", "pos": 1, "equipo": "Mexico"}])
    result = calcular(p, r)
    assert pos_detalle(result)["total"] == 5


def test_posicion_grupo_fallada():
    """Pronóstico México 1º, real México 2º → 0 pts."""
    p = pron(posiciones_grupo=[{"grupo": "A", "pos": 1, "equipo": "Mexico"}])
    r = res(posiciones_grupo=[{"grupo": "A", "pos": 2, "equipo": "Mexico"}])
    result = calcular(p, r)
    assert pos_detalle(result)["total"] == 0


def test_mejor_tercero_no_duplica_puntuacion():
    """
    Retirada (2026-07-03) la sección 'clasificado_1_16_desde_grupos': un
    mejor-tercero acertado (posición Y clasificación real) ya no suma un +5
    extra aparte de "posiciones_grupo" y "clasificados". La sección ya no
    existe en el desglose.
    """
    teams = [f"Team{i}" for i in range(12)]
    pos_pred = [{"grupo": chr(65 + i), "pos": 3, "equipo": t, "mejor_tercero": True}
                for i, t in enumerate(teams)]
    clasificados_real = {"1/16": teams[:8], "1/8": [], "1/4": [], "semis": [], "final": []}

    p = pron(posiciones_grupo=pos_pred, clasificados=CLAS_VACIAS.copy())
    r = res(clasificados=clasificados_real)
    result = calcular(p, r)
    assert "clasificado_1_16_desde_grupos" not in result["desglose"]


# ── Eliminatoria: marcador ───────────────────────────────────────────────────

def _elim_res(match_id, fase_id, gl, gv, local="Brazil", visitante="Spain"):
    """Genera calendario + marcadores reales para un test de elim."""
    cal_extra = [{"id": fase_id, "fase": "1/4", "jornada": None, "grupo": None,
                  "local": "?", "visitante": "?"}]
    marcadores = [{"match_id": fase_id, "estado": "finalizado",
                   "goles_local": gl, "goles_visitante": gv,
                   "local": local, "visitante": visitante}]
    return cal_extra, marcadores


def test_elim_solo_signo():
    """Pred 1|3-0, real 1|1-0 en 1/4 → signo OK, diferencia falla → 5 pts."""
    p = pron(elim_marcadores=[{"ronda": "1/4", "local": "Brazil", "visitante": "Spain",
                                "signo": "1", "gl": 3, "gv": 0}])
    r = res(marcadores=[{"match_id": 92, "estado": "finalizado",
                         "goles_local": 1, "goles_visitante": 0,
                         "local": "Brazil", "visitante": "Spain"}])
    result = calcular(p, r)
    assert elim_detalle(result)["total"] == 5


def test_elim_signo_mas_diferencia():
    """Pred 1|2-1, real 1|3-2 en 1/4 → signo OK, dif OK, exacto falla → 7 pts."""
    p = pron(elim_marcadores=[{"ronda": "1/4", "local": "Brazil", "visitante": "Spain",
                                "signo": "1", "gl": 2, "gv": 1}])
    r = res(marcadores=[{"match_id": 92, "estado": "finalizado",
                         "goles_local": 3, "goles_visitante": 2,
                         "local": "Brazil", "visitante": "Spain"}])
    result = calcular(p, r)
    assert elim_detalle(result)["total"] == 7


def test_elim_exacto():
    """Pred 1|1-0, real 1|1-0 en 1/4 → pleno → 15 pts."""
    p = pron(elim_marcadores=[{"ronda": "1/4", "local": "Brazil", "visitante": "Spain",
                                "signo": "1", "gl": 1, "gv": 0}])
    r = res(marcadores=[{"match_id": 92, "estado": "finalizado",
                         "goles_local": 1, "goles_visitante": 0,
                         "local": "Brazil", "visitante": "Spain"}])
    result = calcular(p, r)
    assert elim_detalle(result)["total"] == 15


def test_elim_signo_fallado():
    """Pred 2|0-1, real 1|1-0 en 1/4 → signo falla → 0 pts."""
    p = pron(elim_marcadores=[{"ronda": "1/4", "local": "Brazil", "visitante": "Spain",
                                "signo": "2", "gl": 0, "gv": 1}])
    r = res(marcadores=[{"match_id": 92, "estado": "finalizado",
                         "goles_local": 1, "goles_visitante": 0,
                         "local": "Brazil", "visitante": "Spain"}])
    result = calcular(p, r)
    assert elim_detalle(result)["total"] == 0


def test_elim_empate_penaltis():
    """
    Pred X|0-0, real X|0-0 en 1/4 (penaltis, Brasil pasa a semis).
    Marcador: signo+dif+exacto → 15 pts.
    Clasificado Brasil a semis → +16 pts.
    """
    p = pron(
        elim_marcadores=[{"ronda": "1/4", "local": "Brazil", "visitante": "Spain",
                          "signo": "X", "gl": 0, "gv": 0}],
        clasificados={"1/16": [], "1/8": [], "1/4": [], "semis": ["Brazil"], "final": []},
    )
    r = res(
        marcadores=[{"match_id": 92, "estado": "finalizado",
                     "goles_local": 0, "goles_visitante": 0,
                     "local": "Brazil", "visitante": "Spain"}],
        clasificados={"1/16": [], "1/8": [], "1/4": [], "semis": ["Brazil"], "final": []},
    )
    result = calcular(p, r)
    assert elim_detalle(result)["total"] == 15
    assert clas_detalle(result)["total"] == 16


# ── Clasificados por ronda ───────────────────────────────────────────────────

@pytest.mark.parametrize("ronda,pts_esperados", [
    ("1/16", 10),
    ("1/8",  12),
    ("1/4",  14),
    ("semis", 16),
    ("final", 20),
])
def test_clasificado_por_ronda_ok(ronda, pts_esperados):
    """Un equipo acertado en cada ronda da los puntos correctos."""
    p = pron(clasificados={r: (["Brazil"] if r == ronda else [])
                            for r in ("1/16", "1/8", "1/4", "semis", "final")})
    r = res(clasificados={r: (["Brazil"] if r == ronda else [])
                           for r in ("1/16", "1/8", "1/4", "semis", "final")})
    result = calcular(p, r)
    assert clas_detalle(result)["total"] == pts_esperados


def test_clasificado_fallado():
    """Equipo pronosticado que no llega → 0 pts."""
    p = pron(clasificados={"1/16": ["Brazil"], "1/8": [], "1/4": [], "semis": [], "final": []})
    r = res(clasificados={"1/16": ["Spain"], "1/8": [], "1/4": [], "semis": [], "final": []})
    result = calcular(p, r)
    assert clas_detalle(result)["total"] == 0


# ── Honor ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("puesto,pts_esperados", [
    ("campeon",    25),
    ("subcampeon", 20),
    ("tercero",    15),
    ("cuarto",     10),
])
def test_honor_puesto_individual(puesto, pts_esperados):
    """Cada posición de honor acertada da el bono correcto."""
    p = pron(honor={puesto: "Brazil"})
    r = res(honor={puesto: "Brazil"})
    result = calcular(p, r)
    assert honor_detalle(result)["total"] == pts_esperados


def test_honor_todos_acertados():
    """Los cuatro puestos acertados suman 25+20+15+10 = 70 pts."""
    honor = {"campeon": "Brazil", "subcampeon": "Spain",
             "tercero": "France", "cuarto": "Germany"}
    p = pron(honor=honor)
    r = res(honor=honor)
    result = calcular(p, r)
    assert honor_detalle(result)["total"] == 70


def test_honor_fallado():
    """Campeón fallado → 0 pts."""
    p = pron(honor={"campeon": "Brazil"})
    r = res(honor={"campeon": "Spain"})
    result = calcular(p, r)
    assert honor_detalle(result)["total"] == 0


# ── Premios ──────────────────────────────────────────────────────────────────

def test_premios_todos_acertados():
    """Goleador+MVP+portero acertados → 15+15+15 = 45 pts."""
    premios = {"goleador": "Mbappe", "mvp": "Messi", "portero": "Courtois"}
    p = pron(premios=premios)
    r = res(premios=premios)
    result = calcular(p, r)
    assert premios_detalle(result)["total"] == 45


def test_premios_fallados():
    """Premios incorrectos → 0 pts."""
    p = pron(premios={"goleador": "Mbappe", "mvp": "Messi", "portero": "Courtois"})
    r = res(premios={"goleador": "Vinicius", "mvp": "Yamal", "portero": "Flekken"})
    result = calcular(p, r)
    assert premios_detalle(result)["total"] == 0


# ── Desempate ────────────────────────────────────────────────────────────────

def test_desempate_clasificados_ganan_sobre_marcadores():
    """
    Participante A: total igual que B, pero A tiene más pts de clasificados+honor.
    Participante B: total igual que A, pero B tiene más pts de elim_marcadores.
    Resultado: A.puntos_eliminatoria > B.puntos_eliminatoria → A gana el desempate.
    """
    # A: acierta clasificado a semis (+16) y campeón (+25) = 41 pts_eliminatoria
    #    sin marcadores de elim
    pron_a = pron(
        nickname="A",
        clasificados={"1/16": [], "1/8": [], "1/4": [], "semis": ["Brazil"], "final": []},
        honor={"campeon": "Brazil"},
    )
    # B: acierta 4 marcadores exactos de elim (+15×4=60 pts en marcadores)
    #    pero no acierta ningún clasificado ni honor → pts_eliminatoria = 0
    elim_b = [
        {"ronda": "1/4", "local": "Brazil", "visitante": "Spain",   "signo": "X", "gl": 0, "gv": 0},
        {"ronda": "1/8", "local": "France", "visitante": "Germany", "signo": "1", "gl": 1, "gv": 0},
        {"ronda": "1/16","local": "Mexico", "visitante": "Italy",   "signo": "2", "gl": 0, "gv": 1},
        {"ronda": "semis","local": "Brazil","visitante": "France",  "signo": "1", "gl": 2, "gv": 1},
    ]
    pron_b = pron(nickname="B", elim_marcadores=elim_b)

    resultados_comunes = res(
        marcadores=[
            {"match_id": 92, "estado": "finalizado", "goles_local": 0, "goles_visitante": 0,
             "local": "Brazil", "visitante": "Spain"},
            {"match_id": 91, "estado": "finalizado", "goles_local": 1, "goles_visitante": 0,
             "local": "France", "visitante": "Germany"},
            {"match_id": 90, "estado": "finalizado", "goles_local": 0, "goles_visitante": 1,
             "local": "Mexico", "visitante": "Italy"},
            {"match_id": 93, "estado": "finalizado", "goles_local": 2, "goles_visitante": 1,
             "local": "Brazil", "visitante": "France"},
        ],
        clasificados={"1/16": [], "1/8": [], "1/4": [], "semis": ["Brazil"], "final": []},
        honor={"campeon": "Brazil"},
    )

    ra = puntuar_participante(pron_a, resultados_comunes, calendario=CAL)
    rb = puntuar_participante(pron_b, resultados_comunes, calendario=CAL)

    # B tiene más pts totales gracias a los marcadores exactos
    assert rb["puntos_total"] > ra["puntos_total"]

    # Pero A gana el desempate (puntos_eliminatoria = clasificados + honor)
    assert ra["puntos_eliminatoria"] == 41   # 16 (semis) + 25 (campeón)
    assert rb["puntos_eliminatoria"] == 0    # B no tiene predicciones de clasificados ni honor


def test_desempate_marcadores_elim_no_cuentan():
    """
    Validación directa: puntos_eliminatoria NO incluye elim_marcadores.
    Un participante que solo acierte marcadores de elim tiene puntos_eliminatoria = 0.
    """
    p = pron(elim_marcadores=[{"ronda": "1/4", "local": "Brazil", "visitante": "Spain",
                                "signo": "1", "gl": 1, "gv": 0}])
    r = res(marcadores=[{"match_id": 92, "estado": "finalizado",
                         "goles_local": 1, "goles_visitante": 0,
                         "local": "Brazil", "visitante": "Spain"}])
    result = calcular(p, r)
    assert elim_detalle(result)["total"] == 15   # sí suma al total
    assert result["puntos_eliminatoria"] == 0    # pero NO al desempate
