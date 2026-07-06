"""
Tests de los helpers de estado que alimentan la vista Mi Porra.

Cubren:
  - _clasificado_ronda_completa
  - _estado_clasificado (incluye regresión de Turquía en 1/8)
  - _clasificados_desglose (agregado por ronda)
  - _detalle_posiciones_grupo (acierto/fallo/pendiente por casilla)
  - _estado_elim_marcador (5 estados posibles)
  - _resolver_pairs_ronda (bracket resolver 1/8 desde 1/16 completo)
  - generar_proximos (nueva rama elim con partidos cuyo cruce ya se conoce)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from motor.generar_sitio import (
    _clasificado_ronda_completa,
    _clasificados_desglose,
    _detalle_posiciones_grupo,
    _estado_clasificado,
    _estado_elim_marcador,
    _ganador_partido,
    _resolver_pairs_ronda,
    _sin_pronostico_elim,
    generar_proximos,
)


# ── Helpers de construcción de fixtures ──────────────────────────────────────

def _clasif(n1_16=None, n1_8=None, n1_4=None, n_semis=None, n_final=None):
    """Devuelve un dict clasificados con listas del tamaño pedido."""
    def gen(n, prefijo):
        return [f"{prefijo}{i}" for i in range(n)] if n is not None else []
    return {
        "1/16":  gen(n1_16,   "R32_"),
        "1/8":   gen(n1_8,    "R16_"),
        "1/4":   gen(n1_4,    "R08_"),
        "semis": gen(n_semis, "SF_"),
        "final": gen(n_final, "F_"),
    }


# ── _clasificado_ronda_completa ──────────────────────────────────────────────

class TestRondaCompleta:
    def test_1_16_llena(self):
        assert _clasificado_ronda_completa("1/16", _clasif(n1_16=32)) is True

    def test_1_16_incompleta(self):
        assert _clasificado_ronda_completa("1/16", _clasif(n1_16=30)) is False

    def test_1_8_llena(self):
        assert _clasificado_ronda_completa("1/8", _clasif(n1_8=16)) is True

    def test_1_8_incompleta(self):
        assert _clasificado_ronda_completa("1/8", _clasif(n1_8=13)) is False

    def test_ronda_no_reconocida(self):
        assert _clasificado_ronda_completa("cuartitos", _clasif()) is False


# ── _estado_clasificado ──────────────────────────────────────────────────────

class TestEstadoClasificado:

    # ── HIT ───────────────────────────────────────────────────────────────────
    def test_acierto_en_1_16(self):
        real = {"1/16": ["Brazil", "Germany"], "1/8": [], "1/4": [], "semis": [], "final": []}
        assert _estado_clasificado("Brazil", "1/16", real) == "acierto"

    def test_acierto_ignora_tildes_y_mayusculas(self):
        real = {"1/8": ["Türkiye"], "1/16": [], "1/4": [], "semis": [], "final": []}
        assert _estado_clasificado("turkiye", "1/8", real) == "acierto"

    # ── 1/16 fallo/pendiente según lista completa o no ────────────────────────
    def test_1_16_fallo_con_lista_completa(self):
        real = _clasif(n1_16=32)  # 32 equipos, ninguno "Turkey"
        assert _estado_clasificado("Turkey", "1/16", real) == "fallo"

    def test_1_16_pendiente_con_lista_incompleta(self):
        real = _clasif(n1_16=20)
        assert _estado_clasificado("Turkey", "1/16", real) == "pendiente"

    # ── Regresión Turquía: eliminada antes de 1/16 → 1/8 debe ser fallo ───────
    def test_regresion_turquia_1_8_fallo_confirmado_aunque_ronda_abierta(self):
        """
        Turquía nunca entró en `clasificados["1/16"]` real (cayó en grupos).
        Predicha en 1/8. Aunque la lista de 1/8 esté INCOMPLETA, el estado
        debe ser fallo confirmado ya mismo: no puede llegar a algo imposible.

        Este test es la salvaguarda del bug detectado el 2026-07-05.
        """
        # 1/16 real: 32 equipos, ninguno es Turkey.
        # 1/8 real: solo 8 equipos (ronda a medio jugar).
        real = _clasif(n1_16=32, n1_8=8)
        assert _estado_clasificado("Turkey", "1/8", real) == "fallo"

    def test_regresion_turquia_1_8_fallo_tambien_con_ronda_cerrada(self):
        """Y por supuesto, si la ronda también está cerrada, también es fallo."""
        real = _clasif(n1_16=32, n1_8=16)
        assert _estado_clasificado("Turkey", "1/8", real) == "fallo"

    def test_regresion_turquia_propaga_a_1_4(self):
        """Turquía tampoco puede estar en 1/4 sin haber entrado en 1/8."""
        real = _clasif(n1_16=32, n1_8=16, n1_4=4)
        # Turkey no está en 1/8, así que aunque 1/4 no esté llena, es fallo
        assert _estado_clasificado("Turkey", "1/4", real) == "fallo"

    # ── Casos donde el equipo SÍ está en la ronda anterior ────────────────────
    def test_pendiente_prev_ok_r_abierta(self):
        """
        Brasil está en 1/16 real (llegó desde grupos). Aún no aparece en 1/8
        real (todavía no ha jugado su partido) y 1/8 no está cerrada.
        → pendiente.
        """
        real = _clasif(n1_16=32, n1_8=8)
        real["1/16"] = ["Brazil"] + real["1/16"][1:]   # Brazil presente en 1/16
        assert _estado_clasificado("Brazil", "1/8", real) == "pendiente"

    def test_fallo_prev_ok_r_cerrada(self):
        """
        Brasil está en 1/16 real, pero la lista de 1/8 ya está cerrada (16
        equipos) y Brasil no aparece → perdió su partido → fallo.
        """
        real = _clasif(n1_16=32, n1_8=16)
        real["1/16"] = ["Brazil"] + real["1/16"][1:]   # Brazil llegó a 1/16
        # 1/8 llena de otros equipos, sin Brazil → perdió
        assert _estado_clasificado("Brazil", "1/8", real) == "fallo"

    # ── Casos borde ───────────────────────────────────────────────────────────
    def test_equipo_vacio_devuelve_fallo(self):
        assert _estado_clasificado("", "1/16", _clasif(n1_16=32)) == "fallo"
        assert _estado_clasificado(None, "1/16", _clasif(n1_16=32)) == "fallo"


# ── _clasificados_desglose ───────────────────────────────────────────────────

class TestClasificadosDesglose:
    def test_conteo_aciertos_fallos_pendientes(self):
        real = _clasif(n1_16=32)
        real["1/16"] = ["Brazil", "Germany"] + [f"X{i}" for i in range(30)]

        pred = {
            "1/16": ["Brazil", "Germany", "Turkey"],
            "1/8": [], "1/4": [], "semis": [], "final": [],
        }
        d = _clasificados_desglose(pred, real)

        assert d["1/16"]["aciertos"]   == 2
        assert d["1/16"]["fallos"]     == 1   # Turkey confirmed miss (1/16 lleno)
        assert d["1/16"]["pendientes"] == 0
        assert d["1/16"]["pts"]        == 20  # 2 × 10

    def test_pendiente_cuando_ronda_no_cerrada(self):
        real = _clasif(n1_16=20)  # 1/16 abierta, 20 equipos
        pred = {
            "1/16": ["Brazil"],
            "1/8": [], "1/4": [], "semis": [], "final": [],
        }
        d = _clasificados_desglose(pred, real)
        assert d["1/16"]["pendientes"] == 1
        assert d["1/16"]["fallos"]     == 0
        assert d["1/16"]["pts"]        == 0


# ── _detalle_posiciones_grupo ────────────────────────────────────────────────

class TestPosicionesGrupo:
    def test_48_entradas_siempre(self):
        entries = _detalle_posiciones_grupo([], [], [])
        assert len(entries) == 48
        # 12 grupos × 4 posiciones
        grupos = sorted(set(e["grupo"] for e in entries))
        assert grupos == list("ABCDEFGHIJKL")

    def test_acierto_da_5_pts(self):
        pos_pred = [{"grupo": "A", "pos": 1, "equipo": "Mexico"}]
        pos_real = [{"grupo": "A", "pos": 1, "equipo": "Mexico"}]
        entries = _detalle_posiciones_grupo([], pos_pred, pos_real)
        a1 = next(e for e in entries if e["grupo"] == "A" and e["pos"] == 1)
        assert a1["estado"] == "acierto"
        assert a1["pts"] == 5

    def test_fallo_cuando_real_existe_y_no_coincide(self):
        pos_pred = [{"grupo": "A", "pos": 1, "equipo": "Mexico"}]
        pos_real = [{"grupo": "A", "pos": 1, "equipo": "South Korea"}]
        entries = _detalle_posiciones_grupo([], pos_pred, pos_real)
        a1 = next(e for e in entries if e["grupo"] == "A" and e["pos"] == 1)
        assert a1["estado"] == "fallo"
        assert a1["pts"] == 0

    def test_pendiente_cuando_no_hay_real(self):
        pos_pred = [{"grupo": "A", "pos": 1, "equipo": "Mexico"}]
        pos_real = []
        entries = _detalle_posiciones_grupo([], pos_pred, pos_real)
        a1 = next(e for e in entries if e["grupo"] == "A" and e["pos"] == 1)
        assert a1["estado"] == "pendiente"

    def test_normaliza_tildes(self):
        pos_pred = [{"grupo": "H", "pos": 1, "equipo": "España"}]
        pos_real = [{"grupo": "H", "pos": 1, "equipo": "espana"}]
        entries = _detalle_posiciones_grupo([], pos_pred, pos_real)
        h1 = next(e for e in entries if e["grupo"] == "H" and e["pos"] == 1)
        assert h1["estado"] == "acierto"


# ── _estado_elim_marcador ────────────────────────────────────────────────────

CAL_ELIM = {
    73: {"id": 73, "fase": "1/16"},
    74: {"id": 74, "fase": "1/16"},
    75: {"id": 75, "fase": "1/16"},
    89: {"id": 89, "fase": "1/8"},
}


class TestEstadoElimMarcador:
    def test_acierto_puntuo_exacto(self):
        pred = {"ronda": "1/16", "local": "Brazil", "visitante": "Japan",
                "signo": "1", "gl": 2, "gv": 1}
        marc = [{"match_id": 73, "estado": "finalizado",
                 "local": "Brazil", "visitante": "Japan",
                 "goles_local": 2, "goles_visitante": 1}]
        res = _estado_elim_marcador(pred, marc, CAL_ELIM, _clasif(n1_16=32))
        assert res["estado"] == "acierto_puntuo"
        assert res["pts"] == 15
        assert res["niveles"] == {"signo": True, "diferencia": True, "exacto": True}

    def test_acierto_puntuo_orientacion_invertida(self):
        """El par real puede venir con local/visitante invertidos vs pronóstico."""
        pred = {"ronda": "1/16", "local": "Brazil", "visitante": "Japan",
                "signo": "1", "gl": 2, "gv": 1}
        # El marcador real trae Japan como local, Brazil como visitante
        marc = [{"match_id": 73, "estado": "finalizado",
                 "local": "Japan", "visitante": "Brazil",
                 "goles_local": 1, "goles_visitante": 2}]
        res = _estado_elim_marcador(pred, marc, CAL_ELIM, _clasif(n1_16=32))
        assert res["estado"] == "acierto_puntuo"
        assert res["resultado"]["gl"] == 2   # reorientados al pronóstico
        assert res["resultado"]["gv"] == 1

    def test_acierto_no_puntuo(self):
        """Par correcto pero marcador equivocado (signo mal)."""
        pred = {"ronda": "1/16", "local": "Brazil", "visitante": "Japan",
                "signo": "1", "gl": 2, "gv": 1}
        marc = [{"match_id": 73, "estado": "finalizado",
                 "local": "Brazil", "visitante": "Japan",
                 "goles_local": 0, "goles_visitante": 2}]
        res = _estado_elim_marcador(pred, marc, CAL_ELIM, _clasif(n1_16=32))
        assert res["estado"] == "acierto_no_puntuo"
        assert res["pts"] == 0

    def test_cruce_no_ocurrio_uno_jugo_con_otro(self):
        """Brasil jugó contra Chile, no contra Japón como pronosticaste."""
        pred = {"ronda": "1/16", "local": "Brazil", "visitante": "Japan",
                "signo": "1", "gl": 2, "gv": 1}
        marc = [{"match_id": 73, "estado": "finalizado",
                 "local": "Brazil", "visitante": "Chile",
                 "goles_local": 3, "goles_visitante": 0}]
        res = _estado_elim_marcador(pred, marc, CAL_ELIM, _clasif(n1_16=32))
        assert res["estado"] == "cruce_no_ocurrio"
        assert "Japan" in res["motivo"]

    def test_cruce_no_ocurrio_uno_no_llego(self):
        """Brasil llegó, Japón no. No hay marcador con ninguno todavía."""
        pred = {"ronda": "1/16", "local": "Brazil", "visitante": "Japan",
                "signo": "1", "gl": 2, "gv": 1}
        real = _clasif(n1_16=32)
        real["1/16"] = ["Brazil"] + real["1/16"][1:]   # Japan NO
        res = _estado_elim_marcador(pred, [], CAL_ELIM, real)
        assert res["estado"] == "cruce_no_ocurrio"
        assert "Japan" in res["motivo"]

    def test_pendiente_confirmado_ambos_vivos(self):
        """Ambos equipos en R, sin marcador todavía → pendiente confirmado."""
        pred = {"ronda": "1/8", "local": "Brazil", "visitante": "France",
                "signo": "1", "gl": 1, "gv": 0}
        real = _clasif(n1_8=8)
        real["1/8"] = ["Brazil", "France"] + real["1/8"][2:]
        res = _estado_elim_marcador(pred, [], CAL_ELIM, real)
        assert res["estado"] == "pendiente_confirmado"
        assert res["pts"] == 0

    def test_pendiente_sin_confirmar_prev_no_completa(self):
        """Ninguno en R aún y la ronda no está cerrada → pendiente sin confirmar."""
        pred = {"ronda": "1/4", "local": "Brazil", "visitante": "France",
                "signo": "1", "gl": 1, "gv": 0}
        real = _clasif(n1_4=2)  # 1/4 a medio jugar (aún puede llenarse)
        res = _estado_elim_marcador(pred, [], CAL_ELIM, real)
        assert res["estado"] == "pendiente_sin_confirmar"


# ── _sin_pronostico_elim ─────────────────────────────────────────────────────

class TestSinPronosticoElim:
    def test_regresion_belgium_senegal(self):
        """
        Bug detectado 2026-07-06: si el participante no pronostica un cruce
        concreto (Belgium-Senegal), ese partido real no aparece en Mi Porra.
        La lista `sin_pronostico` debe recogerlo para poder mostrarlo.
        """
        elim_pred = [
            {"ronda": "1/16", "local": "Belgium",   "visitante": "South Korea",
             "signo": "1", "gl": 1, "gv": 0},
            {"ronda": "1/16", "local": "England",   "visitante": "Senegal",
             "signo": "1", "gl": 2, "gv": 1},
        ]
        marc = [
            # El par realmente jugado (Belgium vs Senegal) NO está entre los
            # pronósticos del participante — debe salir en la lista.
            {"match_id": 82, "estado": "finalizado",
             "local": "Belgium", "visitante": "Senegal",
             "goles_local": 3, "goles_visitante": 2},
            # Este par SÍ está entre los pronósticos → no aparece.
            {"match_id": 76, "estado": "finalizado",
             "local": "Brazil", "visitante": "Japan",
             "goles_local": 2, "goles_visitante": 1},
        ]
        cal_idx = {
            82: {"id": 82, "fase": "1/16"},
            76: {"id": 76, "fase": "1/16"},
        }
        # Añado Brazil-Japan al elim_pred para asegurar que ese sí se filtra.
        elim_pred.append({"ronda": "1/16", "local": "Brazil", "visitante": "Japan",
                          "signo": "1", "gl": 2, "gv": 1})
        out = _sin_pronostico_elim(elim_pred, marc, cal_idx)
        assert "1/16" in out
        assert len(out["1/16"]) == 1
        entry = out["1/16"][0]
        assert entry["local"] == "Belgium"
        assert entry["visitante"] == "Senegal"
        assert entry["gl"] == 3 and entry["gv"] == 2
        assert entry["signo"] == "1"

    def test_par_pronosticado_invertido_tambien_se_filtra(self):
        """Si el participante pronosticó A-B y el real fue B-A → no es sin pronóstico."""
        elim_pred = [{"ronda": "1/16", "local": "Brazil", "visitante": "Japan",
                      "signo": "2", "gl": 0, "gv": 1}]
        marc = [{"match_id": 76, "estado": "finalizado",
                 "local": "Japan", "visitante": "Brazil",
                 "goles_local": 1, "goles_visitante": 0}]
        cal_idx = {76: {"id": 76, "fase": "1/16"}}
        out = _sin_pronostico_elim(elim_pred, marc, cal_idx)
        assert out.get("1/16") in (None, [])

    def test_partidos_no_finalizados_se_ignoran(self):
        marc = [{"match_id": 82, "estado": "en_juego",
                 "local": "Belgium", "visitante": "Senegal",
                 "goles_local": 1, "goles_visitante": 0}]
        cal_idx = {82: {"id": 82, "fase": "1/16"}}
        out = _sin_pronostico_elim([], marc, cal_idx)
        assert out == {}

    def test_partidos_de_grupos_se_ignoran(self):
        """Sólo cuenta la fase eliminatoria."""
        marc = [{"match_id": 1, "estado": "finalizado",
                 "local": "Mexico", "visitante": "South Africa",
                 "goles_local": 2, "goles_visitante": 0}]
        cal_idx = {1: {"id": 1, "fase": "grupos"}}
        out = _sin_pronostico_elim([], marc, cal_idx)
        assert out == {}

    def test_agrupa_por_ronda(self):
        marc = [
            {"match_id": 82, "estado": "finalizado",
             "local": "Belgium", "visitante": "Senegal",
             "goles_local": 3, "goles_visitante": 2},
            {"match_id": 89, "estado": "finalizado",
             "local": "Paraguay", "visitante": "France",
             "goles_local": 0, "goles_visitante": 1},
        ]
        cal_idx = {
            82: {"id": 82, "fase": "1/16"},
            89: {"id": 89, "fase": "1/8"},
        }
        out = _sin_pronostico_elim([], marc, cal_idx)
        assert set(out.keys()) == {"1/16", "1/8"}
        assert out["1/16"][0]["local"] == "Belgium"
        assert out["1/8"][0]["local"] == "Paraguay"


# ── Resolutor de cuadro de eliminatoria ──────────────────────────────────────

def _cal_1_16_completo():
    """
    Devuelve (cal_idx, marc_por_id, clasificados_reales) con:
      · 16 partidos de 1/16 finalizados (marc completa la ronda anterior)
      · 8 slots de 1/8 con placeholders W{n} apuntando a esos 16 partidos
      · clasificados[1/8] con los 16 ganadores reales (para desempatar penaltis)

    Reproduce el cuadro real 2026 en el que Jordi predijo Colombia-Spain
    pero Colombia se enfrenta a Switzerland y Spain a Portugal.
    """
    ganadores = {
        73: "Canada",       74: "Paraguay",    75: "Morocco",     76: "Brazil",
        77: "France",       78: "Norway",      79: "Mexico",      80: "England",
        81: "USA",          82: "Belgium",     83: "Portugal",    84: "Spain",
        85: "Switzerland",  86: "Argentina",   87: "Colombia",    88: "Egypt",
    }
    perdedores = {
        73: "South Africa", 74: "Germany",     75: "Netherlands", 76: "Japan",
        77: "Sweden",       78: "Ivory Coast", 79: "Ecuador",     80: "DR Congo",
        81: "Bosnia-Herzegovina", 82: "Senegal", 83: "Croatia",   84: "Austria",
        85: "Algeria",      86: "Cape Verde",  87: "Ghana",       88: "Australia",
    }
    marc_por_id = {}
    for mid, ganador in ganadores.items():
        perdedor = perdedores[mid]
        # Convención: local siempre gana en este fixture (simplifica),
        # salvo los penaltis reales (74, 75, 88), donde usamos empate.
        if mid in (74, 75, 88):
            marc_por_id[mid] = {"match_id": mid, "estado": "finalizado",
                                "local": perdedor, "visitante": ganador,
                                "goles_local": 1, "goles_visitante": 1}
        else:
            marc_por_id[mid] = {"match_id": mid, "estado": "finalizado",
                                "local": ganador, "visitante": perdedor,
                                "goles_local": 2, "goles_visitante": 1}
    cal_idx = {mid: {"id": mid, "fase": "1/16"} for mid in ganadores}
    # Slots de 1/8 según el bracket real 2026.
    slots_1_8 = {
        89: ("W74", "W77"),   # Paraguay vs France
        90: ("W73", "W75"),   # Canada vs Morocco
        91: ("W76", "W78"),   # Brazil vs Norway
        92: ("W79", "W80"),   # Mexico vs England
        93: ("W83", "W84"),   # Portugal vs Spain
        94: ("W81", "W82"),   # USA vs Belgium
        95: ("W86", "W88"),   # Argentina vs Egypt
        96: ("W85", "W87"),   # Switzerland vs Colombia
    }
    for mid, (Lp, Vp) in slots_1_8.items():
        cal_idx[mid] = {"id": mid, "fase": "1/8", "local": Lp, "visitante": Vp}

    clasif = _clasif(n1_8=0)
    clasif["1/8"] = list(ganadores.values())   # 16 equipos en 1/8
    return cal_idx, marc_por_id, clasif


class TestGanadorPartido:
    def test_ganador_directo_por_goles(self):
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        # Match 87: Colombia (local) 2 - 1 Ghana → Colombia
        assert _ganador_partido(87, marc_por_id, cal_idx, clasif) == "Colombia"

    def test_ganador_por_penaltis_via_clasificados(self):
        """
        Match 74 finalizado con empate 1-1 (fue a penaltis). El ganador se
        determina cruzando con clasificados[1/8] real: Paraguay aparece,
        Germany no → Paraguay ganó los penaltis.
        """
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        assert _ganador_partido(74, marc_por_id, cal_idx, clasif) == "Paraguay"

    def test_ganador_none_si_no_finalizado(self):
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        marc_por_id[87] = {**marc_por_id[87], "estado": "pendiente"}
        assert _ganador_partido(87, marc_por_id, cal_idx, clasif) is None


class TestResolverPairsRonda:
    def test_1_8_bracket_resuelto(self):
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        pairs = _resolver_pairs_ronda("1/8", marc_por_id, cal_idx, clasif)
        assert pairs   # debe resolver
        # Colombia contra Switzerland
        assert pairs.get("colombia")   == "Switzerland"
        assert pairs.get("switzerland") == "Colombia"
        # Spain contra Portugal
        assert pairs.get("spain")    == "Portugal"
        assert pairs.get("portugal") == "Spain"
        # Brazil contra Norway
        assert pairs.get("brazil") == "Norway"
        # Mexico contra England
        assert pairs.get("mexico") == "England"

    def test_resolucion_parcial_si_falta_algun_1_16(self):
        """
        Con match 87 pendiente: el slot 96 (W85 vs W87) no puede armarse,
        pero los otros 7 slots de 1/8 sí. La resolución es POR SLOT — así
        Mi Porra y Partidos comparten criterio granular sobre cada cruce.
        """
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        marc_por_id[87] = {**marc_por_id[87], "estado": "pendiente"}
        pairs = _resolver_pairs_ronda("1/8", marc_por_id, cal_idx, clasif)
        # Los slots que sí se resuelven:
        assert pairs.get("brazil") == "Norway"
        assert pairs.get("spain")  == "Portugal"
        # Colombia (W87) y su rival Switzerland (W85) no: su slot no puede armarse.
        assert "colombia"    not in pairs
        assert "switzerland" not in pairs


class TestRegresionColombiaSpainEnOctavos:
    """
    Bug detectado 2026-07-06: 'Pendiente · ambos vivos' se mostraba para
    Colombia-Spain en Octavos porque ambos estaban en clasificados[1/8],
    aunque el bracket ya emparejaba a Colombia con Switzerland y a Spain
    con Portugal. La nueva lógica debe convertir estas predicciones en
    cruce_no_ocurrio con motivo específico.
    """
    def test_colombia_spain_deviene_cruce_no_ocurrio(self):
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        marcadores = list(marc_por_id.values())
        pred = {"ronda": "1/8", "local": "Colombia", "visitante": "Spain",
                "signo": "1", "gl": 2, "gv": 1}
        res = _estado_elim_marcador(pred, marcadores, cal_idx, clasif)
        assert res["estado"] == "cruce_no_ocurrio"
        assert "Colombia" in res["motivo"]
        assert "Switzerland" in res["motivo"]
        assert "Spain" in res["motivo"]

    def test_brazil_norway_sigue_pendiente_confirmado(self):
        """El par sí coincide con el bracket real → mantener pendiente_confirmado."""
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        marcadores = list(marc_por_id.values())
        pred = {"ronda": "1/8", "local": "Brazil", "visitante": "Norway",
                "signo": "1", "gl": 1, "gv": 0}
        res = _estado_elim_marcador(pred, marcadores, cal_idx, clasif)
        assert res["estado"] == "pendiente_confirmado"

    def test_switzerland_portugal_deviene_cruce_no_ocurrio(self):
        """Espejo de Colombia-Spain (Switzerland juega contra Colombia, no Portugal)."""
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        marcadores = list(marc_por_id.values())
        pred = {"ronda": "1/8", "local": "Switzerland", "visitante": "Portugal",
                "signo": "1", "gl": 1, "gv": 0}
        res = _estado_elim_marcador(pred, marcadores, cal_idx, clasif)
        assert res["estado"] == "cruce_no_ocurrio"
        assert "Colombia" in res["motivo"]

    def test_ambos_vivos_y_ambos_slots_sin_resolver(self):
        """
        Si NI el slot de L NI el de V están determinados (los partidos que los
        alimentan siguen pendientes) pero ambos siguen vivos en clasificados[R],
        el estado debe caer al genérico pendiente_confirmado.
        """
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        # Invalido tanto el 1/16 de Colombia (87) como el de Spain (84).
        marc_por_id[87] = {**marc_por_id[87], "estado": "pendiente"}
        marc_por_id[84] = {**marc_por_id[84], "estado": "pendiente"}
        marcadores = list(marc_por_id.values())
        pred = {"ronda": "1/8", "local": "Colombia", "visitante": "Spain",
                "signo": "1", "gl": 2, "gv": 1}
        # Ambos añadidos a clasificados[1/8] a mano — vivos, pero slots sin armar.
        clasif["1/8"] = list({*clasif["1/8"], "Colombia", "Spain"})
        res = _estado_elim_marcador(pred, marcadores, cal_idx, clasif)
        assert res["estado"] == "pendiente_confirmado"

    def test_slot_de_uno_resuelto_detecta_mismatch(self):
        """
        Si el slot de Spain SÍ está determinado (Spain-Portugal) pero el de
        Colombia no, el motor debe detectar el mismatch por el lado de Spain
        y devolver cruce_no_ocurrio con el motivo apuntando a Spain.
        """
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        marc_por_id[87] = {**marc_por_id[87], "estado": "pendiente"}   # solo Colombia sin armar
        marcadores = list(marc_por_id.values())
        pred = {"ronda": "1/8", "local": "Colombia", "visitante": "Spain",
                "signo": "1", "gl": 2, "gv": 1}
        res = _estado_elim_marcador(pred, marcadores, cal_idx, clasif)
        assert res["estado"] == "cruce_no_ocurrio"
        assert "Spain" in res["motivo"]
        assert "Portugal" in res["motivo"]


# ── generar_proximos — rama de eliminatoria ──────────────────────────────────

def _escribir_pronostico(dir_porra: Path, nick: str, elim: list) -> None:
    """Escribe un pronóstico minimal (solo elim_marcadores) en dir_porra."""
    dir_porra.mkdir(parents=True, exist_ok=True)
    (dir_porra / f"{nick}.json").write_text(json.dumps({
        "nickname": nick, "porra": "amigos",
        "pronosticos": {
            "grupos": [], "posiciones_grupo": [],
            "elim_marcadores": elim,
            "clasificados": {}, "honor": {}, "premios": {},
        },
    }, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Aísla BASE del módulo generar_sitio para poder inyectar pronósticos."""
    from motor import generar_sitio
    monkeypatch.setattr(generar_sitio, "BASE", tmp_path)
    return tmp_path


class TestGenerarProximosElim:
    def _bracket_resoluble(self):
        """
        Reutiliza el fixture del bracket 2026 y arma:
          · marcadores (16 de 1/16 finalizados, 2 de 1/8 ya jugados)
          · calendario con fecha_hora_utc para todos los slots de 1/8
        """
        cal_idx, marc_por_id, clasif = _cal_1_16_completo()
        # 2 partidos de 1/8 ya jugados (89 = Paraguay-France, 90 = Canada-Morocco).
        marc_por_id[89] = {"match_id": 89, "estado": "finalizado",
                           "local": "Paraguay", "visitante": "France",
                           "goles_local": 0, "goles_visitante": 1}
        marc_por_id[90] = {"match_id": 90, "estado": "finalizado",
                           "local": "Canada",   "visitante": "Morocco",
                           "goles_local": 0, "goles_visitante": 3}
        # Fechas: 1/16 en junio, 1/8 en julio.
        for mid, e in cal_idx.items():
            if e["fase"] == "1/16":
                e["fecha_hora_utc"] = "2026-06-30T20:00:00Z"
            elif e["fase"] == "1/8":
                e["fecha_hora_utc"] = "2026-07-06T20:00:00Z"
        partidos = list(cal_idx.values())
        return cal_idx, marc_por_id, clasif, partidos

    def test_incluye_futuros_1_8_con_cruce_resuelto(self, sandbox):
        cal_idx, marc_por_id, clasif, partidos = self._bracket_resoluble()
        dir_porra = sandbox / "datos" / "pronosticos" / "amigos"
        _escribir_pronostico(dir_porra, "tester", elim=[
            {"ronda": "1/8", "local": "Colombia", "visitante": "Switzerland",
             "signo": "1", "gl": 2, "gv": 1},
        ])
        resultados = {"marcadores": list(marc_por_id.values()),
                      "clasificados": clasif}
        ahora = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

        prox = generar_proximos("amigos", partidos, resultados, ahora)

        # Debe incluir los 6 slots de 1/8 aún por jugar (91-96).
        elim = [p for p in prox if p["fase"] == "1/8"]
        assert len(elim) == 6
        # Y el cruce Colombia-Switzerland debe estar (match 96).
        colombia = next((p for p in elim if p["match_id"] == 96), None)
        assert colombia is not None
        assert {colombia["local"], colombia["visitante"]} == {"Colombia", "Switzerland"}
        # Con la predicción del tester matcheada
        assert len(colombia["predicciones"]) == 1
        assert colombia["predicciones"][0]["nickname"] == "tester"

    def test_omite_1_4_si_1_8_no_completo(self, sandbox):
        """1/4 depende de 1/8. Con 1/8 a medio jugar → 1/4 se omite entero."""
        cal_idx, marc_por_id, clasif, partidos = self._bracket_resoluble()
        # Añadimos slots de 1/4 al calendario.
        cal_idx[97] = {"id": 97, "fase": "1/4",
                       "local": "W89", "visitante": "W90",
                       "fecha_hora_utc": "2026-07-10T20:00:00Z"}
        partidos = list(cal_idx.values())
        resultados = {"marcadores": list(marc_por_id.values()),
                      "clasificados": clasif}
        ahora = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

        prox = generar_proximos("amigos", partidos, resultados, ahora)
        # Match 97 depende de W89 y W90 (ambos jugados) → SÍ debería aparecer
        assert any(p["match_id"] == 97 for p in prox)
        # Ahora invalido 1/8 completo → nada de 1/4 debe salir
        marc_por_id[89] = {**marc_por_id[89], "estado": "pendiente"}
        resultados = {"marcadores": list(marc_por_id.values()),
                      "clasificados": clasif}
        prox2 = generar_proximos("amigos", partidos, resultados, ahora)
        assert not any(p["match_id"] == 97 for p in prox2)

    def test_omite_partidos_finalizados(self, sandbox):
        """Match 89 y 90 ya finalizados → no deben aparecer en 'próximos'."""
        _, marc_por_id, clasif, partidos = self._bracket_resoluble()
        resultados = {"marcadores": list(marc_por_id.values()),
                      "clasificados": clasif}
        ahora = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
        prox = generar_proximos("amigos", partidos, resultados, ahora)
        ids = {p["match_id"] for p in prox}
        assert 89 not in ids
        assert 90 not in ids

    def test_matchea_prediccion_con_par_invertido(self, sandbox):
        """El tester predijo Spain-Portugal; el par real es Portugal-Spain → match."""
        cal_idx, marc_por_id, clasif, partidos = self._bracket_resoluble()
        dir_porra = sandbox / "datos" / "pronosticos" / "amigos"
        _escribir_pronostico(dir_porra, "tester", elim=[
            {"ronda": "1/8", "local": "Spain", "visitante": "Portugal",
             "signo": "1", "gl": 3, "gv": 1},
        ])
        resultados = {"marcadores": list(marc_por_id.values()),
                      "clasificados": clasif}
        ahora = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)
        prox = generar_proximos("amigos", partidos, resultados, ahora)
        # Match 93 es W83 vs W84 = Portugal vs Spain (en ese orden en el bracket).
        m93 = next(p for p in prox if p["match_id"] == 93)
        # Debe haber matcheado y REORIENTADO la predicción al orden Portugal-Spain
        assert len(m93["predicciones"]) == 1
        pr = m93["predicciones"][0]
        # local=Portugal → los 3 goles pronosticados deben ir con Portugal (gv del pron original)
        # tester pronosticó Spain 3 - 1 Portugal → orientado: Portugal 1 - 3 Spain
        assert pr["prediccion"]["goles_local"]     == 1  # Portugal
        assert pr["prediccion"]["goles_visitante"] == 3  # Spain
