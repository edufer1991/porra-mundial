#!/usr/bin/env python3
"""
puntuar_v2.py — Motor matejero de la Porra Mundial 2026.

Sistema:
  · Grupos por partido:  signo=5  diferencia=2 (si signo)  exacto=8 (si diferencia)
  · Posición exacta 1-4 en su grupo: 5 c/u
  · Eliminatoria por partido: signo=5  diferencia=2  exacto=8
  · Clasificados:  1/16→10  1/8→12  1/4→14  semis→16  final→20
  · Honor:  campeon=25  sub=20  3º=15  4º=10
  · Premios:  goleador=15  MVP=15  portero=15
  · Desempate: puntos_eliminatoria = clasificados + honor (SIN marcadores
    de eliminatoria, SIN grupos, SIN premios). Sólo cuentan equipos
    clasificados por ronda y posiciones de honor.

  NOTA: se retiró (2026-07-03) el bono "clasificado a 1/16 desde
  posiciones_grupo" (+5 extra por equipo pronosticado 1º/2º/mejor-tercero
  que clasificaba). Duplicaba el acierto que ya paga "clasificados" (ronda
  1/16, +10 c/u, sin depender del orden — regla oficial de matejero).

Empate en 90' (penaltis):
  · signo=X puntúa si el marcador real terminó en X.
  · Diferencia 0 = 0, así que cualquier predicción X con cualquier resultado X
    suma diferencia. El exacto requiere goles iguales.
  · El equipo que pasa por penaltis aparece en resultados.clasificados[ronda+1],
    así que la sección "clasificados" lo recoge automáticamente.

Interfaz:
  puntuar_participante(pronostico, resultados, calendario=None, alias_jugadores=None)
    → dict con total / puntos_eliminatoria / desglose.

NOTA: este motor NO está conectado al pipeline todavía. v1 sigue siendo el oficial.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from motor.tabla_grupo import calcular_tabla_grupos
from motor.clasif_real import clasificados_reales

BASE        = Path(__file__).resolve().parent.parent
CALENDARIO  = BASE / "datos" / "calendario.json"
PRONOSTICOS = BASE / "datos" / "pronosticos"
ALIAS_JUGAD = BASE / "datos" / "alias_jugadores.json"  # opcional


# ── Reglas del sistema matejero (valores fijos del enunciado) ────────────────
REGLAS_V2: dict = {
    "grupos_partido": {"signo": 5, "diferencia": 2, "exacto": 8},
    "posicion_exacta": 5,
    "elim_partido":   {"signo": 5, "diferencia": 2, "exacto": 8},
    "clasificados": {
        "1/16":  10,
        "1/8":   12,
        "1/4":   14,
        "semis": 16,
        "final": 20,
    },
    "honor":   {"campeon": 25, "subcampeon": 20, "tercero": 15, "cuarto": 10},
    "premios": {"goleador": 15, "mvp": 15, "portero": 15},
}


# ── Helpers ──────────────────────────────────────────────────────────────────
def norm(t) -> str:
    if not t:
        return ""
    s = unicodedata.normalize("NFD", str(t))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip().lower()


def signo_de(gl: int, gv: int) -> str:
    if gl > gv: return "1"
    if gl < gv: return "2"
    return "X"


def _pair_key(a, b) -> frozenset:
    return frozenset({norm(a), norm(b)})


def _cargar_calendario() -> list[dict]:
    with open(CALENDARIO, encoding="utf-8") as f:
        return json.load(f)["partidos"]


# ── Marcador (lógica acumulativa signo → diferencia → exacto) ────────────────
def _puntuar_marcador(pred: dict | None,
                      gl_real: int,
                      gv_real: int,
                      reglas_m: dict) -> tuple[int, dict]:
    """
    Devuelve (puntos, niveles) donde niveles = {signo, diferencia, exacto}.
    Acumulativo: diferencia sólo si signo OK; exacto sólo si diferencia OK.
    Para X, diferencia = 0 - 0 = 0, así que toda X|x-x acumula diferencia.
    """
    niveles = {"signo": False, "diferencia": False, "exacto": False}
    if pred is None:
        return 0, niveles

    p_signo = pred.get("signo")
    p_gl    = pred.get("gl", pred.get("goles_local"))
    p_gv    = pred.get("gv", pred.get("goles_visitante"))

    pts = 0
    if p_signo == signo_de(gl_real, gv_real):
        niveles["signo"] = True
        pts += reglas_m["signo"]

        if p_gl is not None and p_gv is not None:
            if (p_gl - p_gv) == (gl_real - gv_real):
                niveles["diferencia"] = True
                pts += reglas_m["diferencia"]

                if p_gl == gl_real and p_gv == gv_real:
                    niveles["exacto"] = True
                    pts += reglas_m["exacto"]
    return pts, niveles


# ── Sección: marcadores de fase de grupos ────────────────────────────────────
def _puntuar_grupos_partidos(grupos_pred: list[dict],
                             marc_por_id: dict[int, dict]) -> dict:
    detalle: list[dict] = []
    total = 0
    R = REGLAS_V2["grupos_partido"]
    for p in grupos_pred:
        pred = p.get("prediccion")
        m    = marc_por_id.get(p.get("match_id"))
        if not pred or not m or m.get("estado") != "finalizado":
            continue
        pts, niveles = _puntuar_marcador(pred, m["goles_local"], m["goles_visitante"], R)
        if pts > 0:
            detalle.append({
                "match_id": p["match_id"],
                "partido":  f"{p.get('local')}-{p.get('visitante')}",
                "pred":     f"{pred['signo']}|{pred['goles_local']}-{pred['goles_visitante']}",
                "real":     f"{signo_de(m['goles_local'], m['goles_visitante'])}|{m['goles_local']}-{m['goles_visitante']}",
                "niveles":  niveles,
                "pts":      pts,
            })
            total += pts
    return {"total": total, "detalle": detalle}


# ── Sección: posiciones de grupo derivadas del pronóstico de marcadores ──────
def _derivar_posiciones_grupo(grupos_pred: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Deriva la tabla de grupo (1º-4º) que se desprende de los marcadores que el
    participante pronosticó para los 72 partidos de grupos, usando el mismo
    algoritmo de clasificación (puntos/DG/GF/enfrentamiento directo) que se
    usa para la tabla real.

    Se usa como ÚNICA fuente para "posiciones_grupo" cuando el pronóstico no
    trae el bloque explícito (p. ej. porque el Excel de origen está corrupto
    y no se puede reparsear): el marcador partido a partido SÍ está intacto
    en el JSON ya parseado, así que de ahí se puede reconstruir de forma
    determinista qué tabla esperaba el participante, sin inventar nada.
    """
    por_grupo: dict[str, list[tuple[str, str, int, int]]] = {}
    for p in grupos_pred or []:
        pred  = p.get("prediccion")
        grupo = p.get("grupo")
        local, visit = p.get("local"), p.get("visitante")
        if not (pred and grupo and local and visit):
            continue
        gl = pred.get("goles_local")
        gv = pred.get("goles_visitante")
        if gl is None or gv is None:
            continue
        por_grupo.setdefault(grupo, []).append((local, visit, gl, gv))
    return calcular_tabla_grupos(por_grupo, min_partidos=6)


# ── Sección: posiciones de grupo (1º/2º/3º/4º) ───────────────────────────────
def _puntuar_posiciones_grupo(pos_pred: list[dict],
                              pos_real: list[dict]) -> dict:
    """
    Cruza (grupo, pos, equipo) entre pronóstico y resultados.
    +5 por cada coincidencia exacta.
    """
    real_idx = {(p.get("grupo"), p.get("pos")): norm(p.get("equipo")) for p in (pos_real or [])}
    detalle: list[dict] = []
    total = 0
    for p in pos_pred or []:
        clave = (p.get("grupo"), p.get("pos"))
        if real_idx.get(clave) == norm(p.get("equipo")) and p.get("equipo"):
            total += REGLAS_V2["posicion_exacta"]
            detalle.append({
                "grupo":  p["grupo"],
                "pos":    p["pos"],
                "equipo": p["equipo"],
                "pts":    REGLAS_V2["posicion_exacta"],
            })
    return {"total": total, "detalle": detalle}


# ── Sección: clasificado a 1/16 (desde posiciones_grupo) ─────────────────────
# NOTA (retirada 2026-07-03): esta sección otorgaba +5 extra por cada equipo
# pronosticado como 1º/2º/mejor-tercero que efectivamente clasificaba a 1/16.
# Se retira por duplicar el mismo acierto que ya paga la sección general
# "clasificados" (ronda "1/16", +10 c/u, no depende del orden — así lo define
# la regla oficial de matejero: "no importa el orden de clasificación").
# Mantener ambas suponía cobrar dos veces por el mismo acierto para cualquier
# equipo pronosticado en 1º/2º puesto.


# ── Sección: marcadores de eliminatoria ──────────────────────────────────────
def _puntuar_elim_marcadores(elim_pred: list[dict],
                             marc_por_id: dict[int, dict],
                             cal_idx_por_id: dict[int, dict]) -> dict:
    """
    Cruza pronóstico (local, visitante, ronda) con marcadores reales (vía match_id
    del calendario para identificar ronda; el marcador real debe traer 'local' y
    'visitante' canónicos para poder cruzar el par de equipos).

    Si el marcador real no incluye 'local'/'visitante', el partido queda sin puntuar
    (el descargador todavía no rellena esos campos para elim — el motor está listo).
    """
    R = REGLAS_V2["elim_partido"]
    # Índice real: pareja {local, visitante} → marcador con su ronda
    real_idx: dict[frozenset, dict] = {}
    for m in marc_por_id.values():
        if m.get("estado") != "finalizado":
            continue
        cal = cal_idx_por_id.get(m.get("match_id"))
        if not cal or cal.get("fase") in (None, "grupos"):
            continue
        l_real = m.get("local")
        v_real = m.get("visitante")
        if not l_real or not v_real:
            continue
        ronda = _fase_a_ronda(cal["fase"])
        real_idx[_pair_key(l_real, v_real)] = {
            "ronda":           ronda,
            "goles_local":     m["goles_local"],
            "goles_visitante": m["goles_visitante"],
            "local_real":      l_real,
            "visitante_real":  v_real,
        }

    detalle: list[dict] = []
    total = 0
    for p in elim_pred or []:
        local = p.get("local")
        visit = p.get("visitante")
        if not local or not visit:
            continue
        real = real_idx.get(_pair_key(local, visit))
        if not real or real["ronda"] != p.get("ronda"):
            continue

        # Orientación: el pronóstico es "local-visitante" pero el real podría
        # tener invertidos local/visitante. Realineamos los goles.
        if norm(real["local_real"]) == norm(local):
            gl_r, gv_r = real["goles_local"], real["goles_visitante"]
        else:
            gl_r, gv_r = real["goles_visitante"], real["goles_local"]

        pred = {"signo": p["signo"], "goles_local": p.get("gl"), "goles_visitante": p.get("gv")}
        pts, niveles = _puntuar_marcador(pred, gl_r, gv_r, R)
        if pts > 0:
            detalle.append({
                "ronda":   p["ronda"],
                "partido": f"{local}-{visit}",
                "pred":    f"{p['signo']}|{p.get('gl')}-{p.get('gv')}",
                "real":    f"{signo_de(gl_r, gv_r)}|{gl_r}-{gv_r}",
                "niveles": niveles,
                "pts":     pts,
            })
            total += pts
    return {"total": total, "detalle": detalle}


def _fase_a_ronda(fase: str) -> str:
    return {
        "1/16": "1/16",
        "1/8":  "1/8",
        "1/4":  "1/4",
        "semis": "semis",
        "tercer_puesto": "3-4",
        "final": "final",
    }.get(fase, fase)


# ── Sección: clasificados por ronda (desde pronosticos.clasificados) ─────────
def _puntuar_clasificados(clasif_pred: dict, clasif_real: dict,
                          resultados: dict | None = None,
                          cal_idx: dict | None = None) -> dict:
    """
    Con `resultados` y `cal_idx` usa clasificados_reales() (openfootball +
    resolutor de bracket). Sin ellos, solo `clasif_real` (retrocompatibilidad).
    """
    detalle: dict[str, dict] = {}
    total = 0
    for ronda, puntos in REGLAS_V2["clasificados"].items():
        pred_set = {norm(e) for e in (clasif_pred.get(ronda) or []) if e}
        if resultados is not None and cal_idx is not None:
            real_set = clasificados_reales(ronda, resultados, cal_idx)
        else:
            real_set = {norm(e) for e in (clasif_real.get(ronda) or []) if e}
        aciertos = pred_set & real_set
        n = len(aciertos)
        if n > 0:
            detalle[ronda] = {"aciertos": n, "pts": n * puntos}
            total += n * puntos
    return {"total": total, "detalle": detalle}


# ── Sección: honor ───────────────────────────────────────────────────────────
def _puntuar_honor(honor_pred: dict, honor_real: dict) -> dict:
    detalle: dict[str, dict] = {}
    total = 0
    for puesto, pts in REGLAS_V2["honor"].items():
        p = honor_pred.get(puesto)
        r = honor_real.get(puesto)
        if p and r and norm(p) == norm(r):
            detalle[puesto] = {"equipo": r, "pts": pts}
            total += pts
    return {"total": total, "detalle": detalle}


# ── Sección: premios ─────────────────────────────────────────────────────────
def _puntuar_premios(premios_pred: dict,
                     premios_real: dict,
                     alias: dict[str, list[str]] | None = None) -> tuple[dict, list[dict]]:
    alias = alias or {}
    detalle: dict[str, dict] = {}
    total = 0
    advertencias: list[dict] = []
    for premio, pts in REGLAS_V2["premios"].items():
        p = premios_pred.get(premio)
        r = premios_real.get(premio)
        if not p or not r:
            continue
        np, nr = norm(p), norm(r)
        if np == nr or np in alias.get(nr, []):
            detalle[premio] = {"jugador": r, "pts": pts}
            total += pts
        else:
            advertencias.append({"premio": premio, "pronosticado": p, "real": r})
    return {"total": total, "detalle": detalle}, advertencias


# ── Puntuación completa de un participante ───────────────────────────────────
def puntuar_participante(pronostico: dict,
                         resultados: dict,
                         calendario: list[dict] | None = None,
                         alias_jugadores: dict | None = None) -> dict:
    """
    Misma firma de entrada/salida que puntuar_v1.puntuar_participante:
    devuelve un dict con los campos planos que el pipeline ya consume
    (puntos_total, puntos_fase_eliminatoria, …) más el `desglose` detallado.

    Funciona con resultados parciales: los partidos pendientes/en_juego no
    suman, no fallan.
    """
    pp = pronostico["pronosticos"]
    cal = calendario if calendario is not None else _cargar_calendario()
    cal_idx_por_id = {p["id"]: p for p in cal}

    marc_por_id = {m["match_id"]: m for m in (resultados.get("marcadores") or [])}

    # posiciones_grupo: usar el bloque explícito del pronóstico si existe;
    # si no (Excel de origen corrupto y no reparseable), derivarlo de los
    # marcadores de grupo que el propio participante pronosticó.
    pos_pred = pp.get("posiciones_grupo") or []
    pos_pred_origen = "explicita"
    if not pos_pred:
        pos_pred, _avisos_pos = _derivar_posiciones_grupo(pp.get("grupos") or [])
        pos_pred_origen = "derivada_de_marcadores_pronosticados"

    # Secciones
    secc_grupos = _puntuar_grupos_partidos(pp.get("grupos") or [], marc_por_id)
    secc_pos    = _puntuar_posiciones_grupo(pos_pred,
                                            resultados.get("posiciones_grupo") or [])
    secc_elim   = _puntuar_elim_marcadores(pp.get("elim_marcadores") or [],
                                           marc_por_id, cal_idx_por_id)
    secc_clas   = _puntuar_clasificados(pp.get("clasificados") or {},
                                        resultados.get("clasificados") or {},
                                        resultados=resultados,
                                        cal_idx=cal_idx_por_id)
    secc_honor  = _puntuar_honor(pp.get("honor") or {}, resultados.get("honor") or {})
    secc_prem, advert = _puntuar_premios(pp.get("premios") or {},
                                         resultados.get("premios") or {},
                                         alias_jugadores)

    # Totales por bloque
    pts_grupos_totales = (
        secc_grupos["total"]
        + secc_pos["total"]
    )
    # Suma de todos los puntos de la fase eliminatoria (para el total)
    pts_fase_eliminatoria_total = (
        secc_elim["total"]
        + secc_clas["total"]
        + secc_honor["total"]
    )
    # Puntos de eliminatoria que cuentan para el DESEMPATE:
    # sólo clasificados + honor (sin marcadores de eliminatoria ni premios).
    pts_eliminatoria_desempate = secc_clas["total"] + secc_honor["total"]
    pts_premios = secc_prem["total"]

    total = pts_grupos_totales + pts_fase_eliminatoria_total + pts_premios

    return {
        # Campos planos (compatibles con el pipeline actual)
        "nickname":                  pronostico.get("nickname"),
        "porra":                     pronostico.get("porra"),
        "puntos_grupos":             pts_grupos_totales,
        "puntos_eliminatorias":      secc_elim["total"] + secc_clas["total"],
        "puntos_honor":              secc_honor["total"],
        "puntos_premios":            pts_premios,
        "puntos_fase_previa":        pts_grupos_totales,
        "puntos_fase_eliminatoria":  pts_eliminatoria_desempate,
        "puntos_total":              total,
        "advertencias_premios":      advert,

        # Campos nuevos del motor v2
        "total":                     total,
        "puntos_eliminatoria":       pts_eliminatoria_desempate,
        "desglose": {
            "grupos":            secc_grupos,
            "posiciones_grupo":  {**secc_pos, "origen": pos_pred_origen},
            "elim_marcadores":   secc_elim,
            "clasificados":      secc_clas,
            "honor":             secc_honor,
            "premios":           secc_prem,
        },
    }


# ── Alias de compatibilidad con v1 ───────────────────────────────────────────
signo_real = signo_de   # generar_sitio.py usa el nombre signo_real


# ── Ordenación (idéntica a v1; desempate por puntos_fase_eliminatoria) ────────
def ordenar_clasificacion(participantes: list[dict]) -> list[dict]:
    ordenados = sorted(
        list(participantes),
        key=lambda x: (-x["puntos_total"], -x["puntos_fase_eliminatoria"], norm(x.get("nickname") or "")),
    )
    for i, p in enumerate(ordenados):
        p["posicion"] = i + 1
        p["empate"]   = False

    i = 0
    while i < len(ordenados):
        j = i + 1
        while (j < len(ordenados)
               and ordenados[j]["puntos_total"]              == ordenados[i]["puntos_total"]
               and ordenados[j]["puntos_fase_eliminatoria"]  == ordenados[i]["puntos_fase_eliminatoria"]):
            j += 1
        if j - i > 1:
            for k in range(i, j):
                ordenados[k]["empate"]   = True
                ordenados[k]["posicion"] = i + 1
        i = j

    by_previa = sorted(ordenados, key=lambda x: (-x["puntos_fase_previa"], norm(x.get("nickname") or "")))
    for i, p in enumerate(by_previa):
        p["posicion_fase_previa"] = i + 1

    return ordenados


# ── End-to-end por porra (interfaz compatible con v1; reglas ignoradas en v2) ─
def generar_clasificacion(porra: str,
                          resultados: dict,
                          reglas: dict | None = None,
                          alias_jugadores: dict | None = None) -> list[dict]:
    dir_porra = PRONOSTICOS / porra
    if not dir_porra.exists():
        return []

    cal = _cargar_calendario()
    participantes: list[dict] = []
    for ruta in sorted(dir_porra.glob("*.json")):
        with open(ruta, encoding="utf-8") as f:
            pron = json.load(f)
        participantes.append(puntuar_participante(pron, resultados, calendario=cal, alias_jugadores=alias_jugadores))

    return ordenar_clasificacion(participantes)


__all__ = [
    "puntuar_participante", "generar_clasificacion", "ordenar_clasificacion",
    "REGLAS_V2", "signo_de", "signo_real", "norm",
]
