#!/usr/bin/env python3
"""
generar_sitio.py — Genera los JSON del panel web en web/data/.

Lee:
  - datos/resultados.json
  - datos/pronosticos/{porra}/*.json
  - datos/calendario.json
  - config/reglas.json

Escribe:
  - web/data/{porra}/standings.json
  - web/data/{porra}/detalle.json
  - web/data/{porra}/proximos.json
  - web/data/{porra}/snapshots.json  (actualización incremental)
  - web/data/resultados.json
  - web/data/calendario.json

Puede ejecutarse de forma autónoma o ser importado por pipeline.py.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from motor.puntuar_v2 import (
    generar_clasificacion,
    norm,
    signo_real,
    _derivar_posiciones_grupo,
)
from motor.clasif_real import (
    clasificados_reales,
    clasificados_excluidos,
    _ganador_partido,
    _perdedor_partido,
    _PREV_ROUND_ELIM,
    _NEXT_ROUND_ELIM,
    _fase_a_ronda,
    _RE_WINNER,
    _RE_LOSER,
    EXPECTED_CLASIF_SIZE,
)


# ── Estado de clasificados / eliminatorias (para la vista Mi Porra) ───────────

_ROUND_PTS = {"1/16": 10, "1/8": 12, "1/4": 14, "semis": 16, "final": 20}


def _estado_clasificado(equipo: str, ronda: str,
                        real_clasif: dict,
                        resultados: dict | None = None,
                        cal_idx: dict | None = None,
                        advertencias: list | None = None) -> str:
    """
    Devuelve "acierto" | "fallo" | "pendiente" para un equipo pronosticado a una ronda.

    Con `resultados` y `cal_idx` usa clasificados_reales() (openfootball +
    resolutor de bracket) y clasificados_excluidos() (perdedores detectados).
    Sin ellos, cae al comportamiento previo: solo `real_clasif` (compat. tests).
    """
    if not equipo:
        return "fallo"
    ne = norm(equipo)

    def _real_r(r: str) -> set[str]:
        if resultados is not None and cal_idx is not None:
            return clasificados_reales(r, resultados, cal_idx, advertencias)
        return {norm(t) for t in (real_clasif.get(r) or [])}

    real_set = _real_r(ronda)
    if ne in real_set:
        return "acierto"

    # ¿El equipo perdió ya su partido en prev(ronda)? → fallo inmediato.
    if resultados is not None and cal_idx is not None:
        excluidos = clasificados_excluidos(ronda, resultados, cal_idx)
        if ne in excluidos:
            return "fallo"

    if ronda == "1/16":
        return "fallo" if len(_real_r("1/16")) >= 32 else "pendiente"

    prev = _PREV_ROUND_ELIM.get(ronda)
    if prev is None:
        return "pendiente"
    if ne not in _real_r(prev):
        return "fallo"   # regla Turquía: no llegó a la ronda anterior

    exp = EXPECTED_CLASIF_SIZE.get(ronda, 999)
    return "fallo" if len(real_set) >= exp else "pendiente"


def _clasificados_desglose(clasif_pred: dict, real_clasif: dict,
                            resultados: dict | None = None,
                            cal_idx: dict | None = None,
                            advertencias: list | None = None) -> dict:
    """Para cada ronda del bracket, marca cada equipo pronosticado con su estado."""
    out = {}
    for ronda in ("1/16", "1/8", "1/4", "semis", "final"):
        entries = []
        aciertos = fallos = pendientes = 0
        for equipo in (clasif_pred.get(ronda) or []):
            estado = _estado_clasificado(equipo, ronda, real_clasif,
                                         resultados, cal_idx, advertencias)
            entries.append({"equipo": equipo, "estado": estado})
            if estado == "acierto":   aciertos += 1
            elif estado == "fallo":   fallos += 1
            else:                     pendientes += 1
        out[ronda] = {
            "equipos":    entries,
            "aciertos":   aciertos,
            "fallos":     fallos,
            "pendientes": pendientes,
            "pts":        aciertos * _ROUND_PTS.get(ronda, 0),
        }
    return out


def _detalle_posiciones_grupo(grupos_pred: list,
                              pos_pred_bloque: list,
                              pos_real: list) -> list:
    """
    Devuelve 48 entradas {grupo, pos, pred, real, estado, pts}.

    Si el pronóstico no trae bloque explícito de posiciones_grupo, se deriva
    de sus 72 marcadores de grupo (misma lógica que puntuar_v2 usa para su
    "posiciones_grupo" derivada — el Excel de origen está corrupto y no se
    puede reparsear, así que reconstruimos desde los marcadores).
    """
    pos_pred = pos_pred_bloque or []
    if not pos_pred:
        pos_pred, _ = _derivar_posiciones_grupo(grupos_pred or [])
    pred_idx = {(e["grupo"], e["pos"]): e["equipo"] for e in pos_pred}
    real_idx = {(e["grupo"], e["pos"]): e["equipo"] for e in (pos_real or [])}
    entries = []
    for grupo in "ABCDEFGHIJKL":
        for pos in (1, 2, 3, 4):
            equipo_pred = pred_idx.get((grupo, pos))
            equipo_real = real_idx.get((grupo, pos))
            if equipo_real is None:
                estado, pts = "pendiente", 0
            elif equipo_pred and norm(equipo_pred) == norm(equipo_real):
                estado, pts = "acierto", 5
            else:
                estado, pts = "fallo", 0
            entries.append({
                "grupo": grupo, "pos": pos,
                "pred":  equipo_pred, "real": equipo_real,
                "estado": estado, "pts": pts,
            })
    return entries


# ── Resolutor de slot ────────────────────────────────────────────────────────


def _resolver_slot(placeholder: str, marc_por_id: dict, cal_idx: dict,
                   real_clasif: dict) -> str | None:
    """
    Resuelve un placeholder de calendario ("W73", "L102", …) al equipo real
    que ocupa ese slot. Devuelve None si aún no puede determinarse.
    Solo cubre los que necesitamos para el resolutor de rondas eliminatorias
    (W{n}, L{n}). Los placeholders de 1/16 (1A, 2B, 3ABC…) no hacen falta
    porque, para el uso de este módulo, siempre miramos la ronda SIGUIENTE a
    una ronda ya jugada.
    """
    if not placeholder:
        return None
    p = str(placeholder).strip()
    m = _RE_WINNER.match(p)
    if m:
        return _ganador_partido(int(m.group(1)), marc_por_id, cal_idx, real_clasif)
    m = _RE_LOSER.match(p)
    if m:
        return _perdedor_partido(int(m.group(1)), marc_por_id, cal_idx, real_clasif)
    return None


def _resolver_pairs_ronda(ronda: str, marc_por_id: dict, cal_idx: dict,
                          real_clasif: dict) -> dict:
    """
    Devuelve `{team_norm: opponent_name}` con los cruces resolubles de la
    ronda. Resolución POR SLOT: se incluye un par únicamente si sus dos
    slots feeder ya están determinados (partidos anteriores finalizados).

    Los slots cuyos feeders aún no están decididos simplemente no aparecen
    en el dict — así Mi Porra y la pestaña Partidos usan el mismo criterio
    para saber si un cruce concreto puede confirmarse o no.
    """
    result: dict[str, str] = {}
    for p in cal_idx.values():
        if _fase_a_ronda(p.get("fase") or "") != ronda:
            continue
        L_res = _resolver_slot(p.get("local"),     marc_por_id, cal_idx, real_clasif)
        V_res = _resolver_slot(p.get("visitante"), marc_por_id, cal_idx, real_clasif)
        if L_res and V_res:
            result[norm(L_res)] = V_res
            result[norm(V_res)] = L_res
    return result


def _puntuar_elim_marcador(pred: dict, gl_r: int, gv_r: int) -> tuple:
    """
    Puntuación del par acertado en eliminatoria. Reglas de matejero:
      signo=5, diferencia=2 (si signo OK), exacto=8 (si diferencia OK).
    Devuelve (pts, niveles) donde niveles = {signo, diferencia, exacto}.
    """
    niveles = {"signo": False, "diferencia": False, "exacto": False}
    if pred is None:
        return 0, niveles
    p_signo = pred.get("signo")
    p_gl = pred.get("gl", pred.get("goles_local"))
    p_gv = pred.get("gv", pred.get("goles_visitante"))
    pts = 0
    if p_signo == signo_real(gl_r, gv_r):
        niveles["signo"] = True
        pts += 5
        if p_gl is not None and p_gv is not None:
            if (p_gl - p_gv) == (gl_r - gv_r):
                niveles["diferencia"] = True
                pts += 2
                if p_gl == gl_r and p_gv == gv_r:
                    niveles["exacto"] = True
                    pts += 8
    return pts, niveles


def _sin_pronostico_elim(elim_pred: list,
                         marcadores: list,
                         cal_idx: dict) -> dict:
    """
    Devuelve {ronda: [{ronda, match_id, local, visitante, gl, gv, signo}]} con
    los partidos de eliminatoria FINALIZADOS cuyo par (local, visitante) NO
    aparece entre las predicciones del participante para esa ronda.

    Estos son los partidos que hoy la vista "Mi Porra" no mostraba (bug
    detectado 2026-07-06): p. ej. Belgium-Senegal en 1/16 cuando el
    participante no lo pronosticó. Es información valiosa: le dice qué se
    jugó realmente en su bracket aunque no lo hubiese anticipado.
    """
    pred_pairs: dict[str, set] = {}
    for p in elim_pred or []:
        r = p.get("ronda")
        L, V = p.get("local"), p.get("visitante")
        if r and L and V:
            pred_pairs.setdefault(r, set()).add(frozenset({norm(L), norm(V)}))

    out: dict[str, list] = {}
    for m in marcadores or []:
        if m.get("estado") != "finalizado":
            continue
        cal = cal_idx.get(m.get("match_id"))
        if not cal:
            continue
        ronda = _fase_a_ronda(cal.get("fase") or "")
        if ronda in ("", "grupos"):
            continue
        L, V = m.get("local"), m.get("visitante")
        if not L or not V:
            continue
        pair = frozenset({norm(L), norm(V)})
        if pair in pred_pairs.get(ronda, set()):
            continue
        gl, gv = m["goles_local"], m["goles_visitante"]
        out.setdefault(ronda, []).append({
            "ronda":     ronda,
            "match_id":  m["match_id"],
            "local":     L,
            "visitante": V,
            "gl":        gl,
            "gv":        gv,
            "signo":     signo_real(gl, gv),
        })
    return out


def _estado_elim_marcador(pred_entry: dict,
                          marcadores: list,
                          cal_idx: dict,
                          real_clasif: dict) -> dict:
    """
    Devuelve dict con estado + info visible. Estados posibles:

      · acierto_puntuo          — par acertado y marcador puntúa (mostrar nivel)
      · acierto_no_puntuo       — par acertado, marcador falla (0 pts)
      · cruce_no_ocurrio        — el par pronosticado nunca se jugó / no se jugará
      · pendiente_confirmado    — ambos equipos vivos en R, cruce aún sin jugar
      · pendiente_sin_confirmar — ronda anterior no completa, incierto

    Además rellena `resultado`, `niveles`, `pts` cuando aplique, y `motivo`
    para cruce_no_ocurrio.
    """
    ronda = pred_entry.get("ronda")
    L, V = pred_entry.get("local"), pred_entry.get("visitante")
    if not L or not V or not ronda:
        return {"estado": "pendiente_sin_confirmar", "pts": 0}
    nL, nV = norm(L), norm(V)

    marc_por_id = {m["match_id"]: m for m in (marcadores or []) if "match_id" in m}

    # Marcadores finalizados de esta ronda (via calendario).
    marc_ronda = []
    for m in marcadores or []:
        if m.get("estado") != "finalizado":
            continue
        cal = cal_idx.get(m.get("match_id"))
        if not cal:
            continue
        if _fase_a_ronda(cal.get("fase") or "") != ronda:
            continue
        if not m.get("local") or not m.get("visitante"):
            continue
        marc_ronda.append(m)

    # 1. ¿Se jugó exactamente este par?
    for m in marc_ronda:
        nmL, nmV = norm(m["local"]), norm(m["visitante"])
        if {nmL, nmV} == {nL, nV}:
            if nmL == nL:
                gl_r, gv_r = m["goles_local"], m["goles_visitante"]
            else:
                gl_r, gv_r = m["goles_visitante"], m["goles_local"]
            pred_score = {
                "signo": pred_entry.get("signo"),
                "gl":    pred_entry.get("gl"),
                "gv":    pred_entry.get("gv"),
            }
            pts, niveles = _puntuar_elim_marcador(pred_score, gl_r, gv_r)
            return {
                "estado":     "acierto_puntuo" if pts > 0 else "acierto_no_puntuo",
                "resultado":  {"gl": gl_r, "gv": gv_r,
                               "signo": signo_real(gl_r, gv_r)},
                "niveles":    niveles,
                "pts":        pts,
            }

    # 2. ¿Alguno de los dos ya jugó (con otro rival) en R? → cruce no ocurrió.
    for m in marc_ronda:
        nmL, nmV = norm(m["local"]), norm(m["visitante"])
        if nL in {nmL, nmV}:
            rival_real = m["visitante"] if nmL == nL else m["local"]
            return {
                "estado": "cruce_no_ocurrio", "pts": 0,
                "motivo": f"{L} jugó contra {rival_real}, no contra {V} en esta ronda",
            }
        if nV in {nmL, nmV}:
            rival_real = m["visitante"] if nmL == nV else m["local"]
            return {
                "estado": "cruce_no_ocurrio", "pts": 0,
                "motivo": f"{V} jugó contra {rival_real}, no contra {L} en esta ronda",
            }

    # 3. Ninguno ha jugado aún en R. Probamos primero el resolutor de bracket
    #    (per-slot): si el slot que ocupará L está determinado (sus dos
    #    feeders finalizados), sabemos con certeza contra quién juega.
    bracket = _resolver_pairs_ronda(ronda, marc_por_id, cal_idx, real_clasif)
    rival_L = bracket.get(nL) if bracket else None
    if rival_L is not None:
        if norm(rival_L) == nV:
            return {"estado": "pendiente_confirmado", "pts": 0}
        return {
            "estado": "cruce_no_ocurrio", "pts": 0,
            "motivo": f"{L} juega contra {rival_L}, no contra {V} en esta ronda",
        }
    rival_V = bracket.get(nV) if bracket else None
    if rival_V is not None:
        # V está en el bracket con otro rival ≠ L (si fuera L, ya habríamos
        # entrado por la rama anterior). L no está en el bracket resuelto.
        return {
            "estado": "cruce_no_ocurrio", "pts": 0,
            "motivo": f"{V} juega contra {rival_V}, no contra {L} en esta ronda",
        }

    # 4. Bracket no determina el slot de L ni de V. Caemos al criterio de
    #    "vivos en la ronda" via clasificados[R].
    real_R = {norm(t) for t in (real_clasif.get(ronda) or [])}
    L_in, V_in = nL in real_R, nV in real_R

    if L_in and V_in:
        return {"estado": "pendiente_confirmado", "pts": 0}

    if L_in != V_in:
        ausente = V if L_in else L
        return {
            "estado": "cruce_no_ocurrio", "pts": 0,
            "motivo": f"{ausente} no llegó a esta ronda",
        }

    _r_tmp = {"clasificados": real_clasif, "marcadores": marcadores or []}
    if len(clasificados_reales(ronda, _r_tmp, cal_idx)) >= EXPECTED_CLASIF_SIZE.get(ronda, 999):
        return {
            "estado": "cruce_no_ocurrio", "pts": 0,
            "motivo": f"Ni {L} ni {V} llegaron a esta ronda",
        }
    return {"estado": "pendiente_sin_confirmar", "pts": 0}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _leer(path: Path) -> dict | list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _escribir(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Detalle por participante ───────────────────────────────────────────────────

def _detalle_grupos(pronosticos_grupos: list[dict],
                    marcadores_map: dict[int, dict],
                    reglas: dict) -> list[dict]:
    """
    Para cada partido de grupos: predicción + resultado (si finalizado) + puntos.
    """
    R = reglas["grupos"]
    bono_l = R["bono_goles_local"]
    bono_v = R["bono_goles_visitante"]
    out = []
    for g in pronosticos_grupos:
        mid  = g.get("match_id")
        pred = g.get("prediccion")
        marc = marcadores_map.get(mid)
        resultado = None
        puntos = None
        ac_signo = ac_local = ac_visit = None

        if marc and marc.get("estado") == "finalizado":
            gl = marc["goles_local"]
            gv = marc["goles_visitante"]
            resultado = {"goles_local": gl, "goles_visitante": gv}
            if pred:
                sr = signo_real(gl, gv)
                ac_signo = pred["signo"] == sr
                ac_local  = pred.get("goles_local")  == gl
                ac_visit  = pred.get("goles_visitante") == gv
                puntos = 0
                if ac_signo:  puntos += R["acierto_signo"]
                if ac_local:  puntos += gl + bono_l
                if ac_visit:  puntos += gv + bono_v

        out.append({
            "match_id":          mid,
            "grupo":             g.get("grupo", ""),
            "jornada":           g.get("jornada", ""),
            "local":             g.get("local", ""),
            "visitante":         g.get("visitante", ""),
            "prediccion":        pred,
            "resultado":         resultado,
            "puntos":            puntos,
            "acierto_signo":     ac_signo,
            "acierto_local":     ac_local,
            "acierto_visitante": ac_visit,
        })
    return out


def generar_detalle(porra: str,
                    resultados: dict,
                    reglas: dict,
                    calendario: dict | None = None) -> dict:
    """Genera detalle.json por nickname para la vista Mi Porra."""
    dir_porra = BASE / "datos" / "pronosticos" / porra
    if not dir_porra.exists():
        return {}

    if calendario is None:
        calendario = _leer(BASE / "datos" / "calendario.json")
    cal_idx = {p["id"]: p for p in calendario.get("partidos", [])}

    marcadores_map  = {m["match_id"]: m for m in (resultados.get("marcadores") or [])}
    marcadores_list = list(marcadores_map.values())
    real_clasif     = resultados.get("clasificados")     or {}
    pos_real        = resultados.get("posiciones_grupo") or []

    detalle = {}
    for ruta in sorted(dir_porra.glob("*.json")):
        try:
            pron = _leer(ruta)
        except Exception as e:
            print(f"  [AVISO] {ruta.name}: {e}", file=sys.stderr)
            continue

        nick = pron.get("nickname", ruta.stem)
        pp   = pron.get("pronosticos", {})

        elim_pred = pp.get("elim_marcadores") or []
        elim_detalle = [
            {**e, **_estado_elim_marcador(e, marcadores_list, cal_idx, real_clasif)}
            for e in elim_pred
        ]

        detalle[nick] = {
            "nickname":              nick,
            "grupos":                _detalle_grupos(pp.get("grupos", []),
                                                    marcadores_map, reglas),
            "posiciones_grupo":      _detalle_posiciones_grupo(
                                        pp.get("grupos") or [],
                                        pp.get("posiciones_grupo") or [],
                                        pos_real),
            "elim_marcadores":       elim_detalle,
            "elim_sin_pronostico":   _sin_pronostico_elim(elim_pred,
                                                         marcadores_list,
                                                         cal_idx),
            "clasificados":          pp.get("clasificados", {}),
            "clasificados_desglose": _clasificados_desglose(
                                        pp.get("clasificados") or {},
                                        real_clasif,
                                        resultados=resultados,
                                        cal_idx=cal_idx),
            "honor":                 pp.get("honor", {}),
            "premios":               pp.get("premios", {}),
        }

    return detalle


# ── Próximos partidos ─────────────────────────────────────────────────────────

def generar_proximos(porra: str,
                     partidos: list[dict],
                     resultados: dict,
                     ahora: datetime,
                     n_grupos: int = 8) -> list[dict]:
    """
    Próximos partidos con las predicciones de todos. Incluye:
      · Fase de grupos: los N (n_grupos) más cercanos en el tiempo, no
        finalizados hace más de ~2 h.
      · Eliminatoria: todos los partidos cuyo cruce ya puede resolverse
        vía `_resolver_slot()`, no finalizados. Si la ronda anterior aún
        está abierta y el slot es un placeholder tipo "W89", se OMITE —
        mismo criterio que usa Mi Porra para no confirmar el cruce.
    """
    dir_porra = BASE / "datos" / "pronosticos" / porra
    marcadores_map = {m["match_id"]: m for m in (resultados.get("marcadores") or [])}
    real_clasif    = resultados.get("clasificados") or {}
    cal_idx        = {p["id"]: p for p in partidos}

    # Índices de predicciones:
    #   · Grupos: por match_id
    #   · Elim  : por (ronda, frozenset({norm(L), norm(V)}))
    preds_grupos_por_id: dict[int, list] = {}
    preds_elim_por_par:  dict[tuple, list] = {}
    if dir_porra.exists():
        for ruta in sorted(dir_porra.glob("*.json")):
            try:
                pron = _leer(ruta)
            except Exception:
                continue
            nick = pron.get("nickname", ruta.stem)
            pp = pron.get("pronosticos") or {}
            for g in pp.get("grupos", []):
                mid = g.get("match_id")
                if mid is not None:
                    preds_grupos_por_id.setdefault(mid, []).append({
                        "nickname":   nick,
                        "prediccion": g.get("prediccion"),
                    })
            for e in pp.get("elim_marcadores") or []:
                ronda = e.get("ronda")
                L, V  = e.get("local"), e.get("visitante")
                if not (ronda and L and V):
                    continue
                clave = (ronda, frozenset({norm(L), norm(V)}))
                preds_elim_por_par.setdefault(clave, []).append({
                    "nickname":   nick,
                    "prediccion": {
                        "signo":           e.get("signo"),
                        "goles_local":     e.get("gl"),
                        "goles_visitante": e.get("gv"),
                    },
                    "pred_local":     L,
                    "pred_visitante": V,
                })

    ventana_pasado = timedelta(hours=2)
    proximos: list[dict] = []
    grupos_incluidos = 0

    for p in sorted(partidos, key=lambda x: x.get("fecha_hora_utc", "")):
        try:
            inicio = datetime.fromisoformat(p["fecha_hora_utc"].replace("Z", "+00:00"))
        except Exception:
            continue

        marc  = marcadores_map.get(p["id"], {})
        estado = marc.get("estado", "pendiente")
        fase   = p.get("fase", "")

        if fase == "grupos":
            if grupos_incluidos >= n_grupos:
                continue
            if estado == "finalizado" and (ahora - inicio) > ventana_pasado:
                continue
            if estado == "pendiente" and inicio < ahora - ventana_pasado:
                continue
            proximos.append({
                "match_id":        p["id"],
                "fecha_hora_utc":  p["fecha_hora_utc"],
                "fase":            fase,
                "grupo":           p.get("grupo", ""),
                "jornada":         p.get("jornada", ""),
                "local":           p["local"],
                "visitante":       p["visitante"],
                "estado":          estado,
                "goles_local":     marc.get("goles_local"),
                "goles_visitante": marc.get("goles_visitante"),
                "predicciones":    preds_grupos_por_id.get(p["id"], []),
            })
            grupos_incluidos += 1
            continue

        # Eliminatoria (todo lo que no sea grupos, incluye tercer_puesto y final)
        if estado == "finalizado":
            # Los partidos elim ya jugados se muestran en "jugados", no aquí.
            continue
        L_res = _resolver_slot(p.get("local"),     marcadores_map, cal_idx, real_clasif)
        V_res = _resolver_slot(p.get("visitante"), marcadores_map, cal_idx, real_clasif)
        if not L_res or not V_res:
            # Mismo criterio que Mi Porra: si no podemos resolver el bracket,
            # omitimos el slot — coherencia entre ambas pestañas.
            continue
        ronda = _fase_a_ronda(fase)
        clave = (ronda, frozenset({norm(L_res), norm(V_res)}))
        preds_par = preds_elim_por_par.get(clave, [])
        # Reorientar cada predicción a la orientación del par real (para que la
        # celda visual de la web muestre "gl_del_local_real - gv_del_visit_real").
        preds_orient = []
        nL, nV = norm(L_res), norm(V_res)
        for pr in preds_par:
            npL = norm(pr["pred_local"])
            same_orient = (npL == nL)
            orig = pr["prediccion"]
            preds_orient.append({
                "nickname":   pr["nickname"],
                "prediccion": {
                    "signo":           orig.get("signo"),
                    "goles_local":     orig.get("goles_local")     if same_orient else orig.get("goles_visitante"),
                    "goles_visitante": orig.get("goles_visitante") if same_orient else orig.get("goles_local"),
                },
            })

        proximos.append({
            "match_id":        p["id"],
            "fecha_hora_utc":  p["fecha_hora_utc"],
            "fase":            ronda,
            "grupo":           "",
            "jornada":         "",
            "local":           L_res,
            "visitante":       V_res,
            "estado":          estado,
            "goles_local":     marc.get("goles_local"),
            "goles_visitante": marc.get("goles_visitante"),
            "predicciones":    preds_orient,
        })

    return proximos


# ── Snapshots ─────────────────────────────────────────────────────────────────

SNAPSHOT_MIN_INTERVALO = timedelta(hours=1)

def actualizar_snapshots(porra: str,
                         clasificacion: list[dict],
                         ahora: datetime) -> None:
    snap_path = BASE / "web" / "data" / porra / "snapshots.json"

    if snap_path.exists():
        snaps = _leer(snap_path)
    else:
        snaps = {"porra": porra, "nicknames": [], "snapshots": []}

    snaps["nicknames"] = [p["nickname"] for p in clasificacion]

    # Solo añadir si ha pasado suficiente tiempo desde el último
    if snaps["snapshots"]:
        try:
            ultimo = datetime.fromisoformat(
                snaps["snapshots"][-1]["fecha"].replace("Z", "+00:00")
            )
            if (ahora - ultimo) < SNAPSHOT_MIN_INTERVALO:
                return
        except Exception:
            pass

    snaps["snapshots"].append({
        "fecha": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "clasificacion": [
            {
                "nickname":    p["nickname"],
                "posicion":    p["posicion"],
                "puntos_total": p["puntos_total"],
            }
            for p in clasificacion
        ],
    })

    _escribir(snap_path, snaps)


# ── Función principal ─────────────────────────────────────────────────────────

def generar_sitio(porras: tuple[str, ...] = ("amigos", "trabajo"),
                  ahora: datetime | None = None) -> None:
    if ahora is None:
        ahora = datetime.now(timezone.utc)

    # Cargar datos de entrada
    resultados_path = BASE / "datos" / "resultados.json"
    if not resultados_path.exists():
        print("[AVISO] datos/resultados.json no existe; se usará estado vacío.",
              file=sys.stderr)
        resultados = {
            "ultima_actualizacion": ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "marcadores": [], "clasificados": {}, "honor": {}, "premios": {}
        }
    else:
        resultados = _leer(resultados_path)

    reglas     = _leer(BASE / "config" / "reglas.json")
    calendario = _leer(BASE / "datos"  / "calendario.json")
    partidos   = calendario.get("partidos", [])

    alias_jugadores = {}
    alias_path = BASE / "datos" / "alias_jugadores.json"
    if alias_path.exists():
        alias_jugadores = _leer(alias_path)

    # Copiar resultados y calendario a web/data/
    web_data = BASE / "web" / "data"
    _escribir(web_data / "resultados.json", resultados)
    _escribir(web_data / "calendario.json", {"torneo": calendario.get("torneo"), "partidos": partidos})
    print("  resultados.json -> web/data/")
    print("  calendario.json -> web/data/")

    for porra in porras:
        out_dir = web_data / porra
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n  [{porra}]")

        # Clasificación
        clasificacion = generar_clasificacion(porra, resultados, reglas, alias_jugadores)
        standings = {
            "porra":                porra,
            "ultima_actualizacion": resultados.get("ultima_actualizacion",
                                                   ahora.strftime("%Y-%m-%dT%H:%M:%SZ")),
            "clasificacion":        clasificacion,
        }
        _escribir(out_dir / "standings.json", standings)
        print(f"    standings.json  ({len(clasificacion)} participantes)")

        # Detalle para Mi Porra
        detalle = generar_detalle(porra, resultados, reglas, calendario)
        _escribir(out_dir / "detalle.json", detalle)
        print(f"    detalle.json    ({len(detalle)} nicknames)")

        # Próximos partidos
        proximos = generar_proximos(porra, partidos, resultados, ahora)
        _escribir(out_dir / "proximos.json", proximos)
        print(f"    proximos.json   ({len(proximos)} partidos)")

        # Snapshots
        if clasificacion:
            actualizar_snapshots(porra, clasificacion, ahora)
            print("    snapshots.json  (actualizado)")
        else:
            print("    snapshots.json  (sin clasificación, se omite)")


if __name__ == "__main__":
    print("Generando sitio web...")
    generar_sitio()
    print("\nListo.")
