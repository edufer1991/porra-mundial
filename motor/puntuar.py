#!/usr/bin/env python3
"""
puntuar.py — Motor de puntuación de la Porra Mundial 2026.

Lee:
  - config/reglas.json
  - datos/resultados.json
  - datos/pronosticos/<porra>/*.json

Produce: datos/standings_<porra>.json con la clasificación ordenada.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

BASE          = Path(__file__).resolve().parent.parent
REGLAS_PATH   = BASE / "config" / "reglas.json"
RESULTADOS    = BASE / "datos"  / "resultados.json"
PRONOSTICOS   = BASE / "datos"  / "pronosticos"
ALIAS_JUGAD   = BASE / "datos"  / "alias_jugadores.json"  # opcional


# ── Normalización ────────────────────────────────────────────────────────────
def norm(t) -> str:
    if not t:
        return ""
    s = unicodedata.normalize("NFD", str(t))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip().lower()


def signo_real(gl: int, gv: int) -> str:
    if gl > gv:
        return "1"
    if gl < gv:
        return "2"
    return "X"


# ── Puntuación por bloque ────────────────────────────────────────────────────
def puntuar_grupos(pronosticos_grupos: list[dict],
                   marcadores_por_id: dict[int, dict],
                   reglas: dict) -> int:
    """
    Por partido FINALIZADO con pronóstico:
      +R.acierto_signo si signo coincide
      +(goles_local_real  + R.bono_goles_local)  si goles del local aciertan
      +(goles_vis_real    + R.bono_goles_visitante) si goles del visitante aciertan
    Independientes.
    """
    R = reglas["grupos"]
    pts_signo  = R["acierto_signo"]
    bono_l     = R["bono_goles_local"]
    bono_v     = R["bono_goles_visitante"]

    total = 0
    for p in pronosticos_grupos:
        pred = p.get("prediccion")
        if not pred:
            continue
        m = marcadores_por_id.get(p["match_id"])
        if not m or m.get("estado") != "finalizado":
            continue
        gl, gv = m["goles_local"], m["goles_visitante"]
        sr     = signo_real(gl, gv)

        if pred["signo"] == sr:
            total += pts_signo
        if pred["goles_local"] == gl:
            total += gl + bono_l
        if pred["goles_visitante"] == gv:
            total += gv + bono_v
    return total


def puntuar_eliminatorias(clasif_pred: dict,
                          clasif_real: dict,
                          reglas: dict) -> int:
    """
    Acumulativo: por ronda R, +puntos_R * |pred[R] ∩ real[R]|.
    Comparación con norm() (sin tildes ni mayúsculas).
    """
    total = 0
    for ronda, puntos in reglas["eliminatorias"]["puntos_por_ronda"].items():
        pred_set = {norm(e) for e in (clasif_pred.get(ronda) or []) if e}
        real_set = {norm(e) for e in (clasif_real.get(ronda) or []) if e}
        total += puntos * len(pred_set & real_set)
    return total


def puntuar_honor(honor_pred: dict, honor_real: dict, reglas: dict) -> int:
    total = 0
    for puesto in ("campeon", "subcampeon", "tercero", "cuarto"):
        p, r = honor_pred.get(puesto), honor_real.get(puesto)
        if p and r and norm(p) == norm(r):
            total += reglas["honor"][puesto]
    return total


def puntuar_premios(premios_pred: dict,
                    premios_real: dict,
                    reglas: dict,
                    alias: dict[str, list[str]] | None = None) -> tuple[int, list[dict]]:
    """
    Compara con norm() + tabla de alias opcional.
    alias = { norm(nombre_canonico): [norm(alias1), norm(alias2), ...] }
    Devuelve (puntos, advertencias) donde advertencias es lista de no-coincidencias.
    """
    alias = alias or {}
    total = 0
    advertencias: list[dict] = []

    for premio in ("goleador", "mvp", "portero"):
        p = premios_pred.get(premio)
        r = premios_real.get(premio)
        if not p or not r:
            continue
        np, nr = norm(p), norm(r)
        if np == nr or np in alias.get(nr, []):
            total += reglas["premios"][premio]
        else:
            advertencias.append({"premio": premio, "pronosticado": p, "real": r})
    return total, advertencias


# ── Puntuación completa de un participante ───────────────────────────────────
def puntuar_participante(pronostico: dict,
                         resultados: dict,
                         reglas: dict,
                         alias_jugadores: dict | None = None) -> dict:
    marcadores_por_id = {m["match_id"]: m for m in (resultados.get("marcadores") or [])}
    pp = pronostico["pronosticos"]

    pts_g = puntuar_grupos(pp["grupos"], marcadores_por_id, reglas)
    pts_e = puntuar_eliminatorias(pp["clasificados"], resultados.get("clasificados") or {}, reglas)
    pts_h = puntuar_honor(pp["honor"], resultados.get("honor") or {}, reglas)
    pts_p, advert = puntuar_premios(pp["premios"], resultados.get("premios") or {}, reglas, alias_jugadores)

    return {
        "nickname":                  pronostico.get("nickname"),
        "porra":                     pronostico.get("porra"),
        "puntos_grupos":             pts_g,
        "puntos_eliminatorias":      pts_e,
        "puntos_honor":              pts_h,
        "puntos_premios":            pts_p,
        "puntos_fase_previa":        pts_g,
        "puntos_fase_eliminatoria":  pts_e + pts_h,
        "puntos_total":              pts_g + pts_e + pts_h + pts_p,
        "advertencias_premios":      advert,
    }


# ── Ordenación de la clasificación ───────────────────────────────────────────
def ordenar_clasificacion(participantes: list[dict]) -> list[dict]:
    """
    Ordena por puntos_total desc; desempate por puntos_fase_eliminatoria desc.
    Si persiste el empate → comparten posición, empate=True (reparto).
    También calcula posicion_fase_previa por puntos_fase_previa desc.
    """
    ordenados = sorted(
        list(participantes),
        key=lambda x: (-x["puntos_total"], -x["puntos_fase_eliminatoria"], norm(x.get("nickname")))
    )

    # Posiciones (con detección de empate persistente)
    for i, p in enumerate(ordenados):
        p["posicion"] = i + 1
        p["empate"]   = False

    i = 0
    while i < len(ordenados):
        j = i + 1
        while (j < len(ordenados)
               and ordenados[j]["puntos_total"] == ordenados[i]["puntos_total"]
               and ordenados[j]["puntos_fase_eliminatoria"] == ordenados[i]["puntos_fase_eliminatoria"]):
            j += 1
        if j - i > 1:
            for k in range(i, j):
                ordenados[k]["empate"]   = True
                ordenados[k]["posicion"] = i + 1   # comparten posición = reparto
        i = j

    # Sub-clasificación de fase previa (sobre los mismos dicts)
    by_previa = sorted(ordenados, key=lambda x: (-x["puntos_fase_previa"], norm(x.get("nickname"))))
    for i, p in enumerate(by_previa):
        p["posicion_fase_previa"] = i + 1

    return ordenados


# ── End-to-end por porra ─────────────────────────────────────────────────────
def generar_clasificacion(porra: str,
                          resultados: dict,
                          reglas: dict,
                          alias_jugadores: dict | None = None) -> list[dict]:
    dir_porra = PRONOSTICOS / porra
    if not dir_porra.exists():
        return []

    participantes: list[dict] = []
    for ruta in sorted(dir_porra.glob("*.json")):
        with open(ruta, encoding="utf-8") as f:
            pron = json.load(f)
        participantes.append(puntuar_participante(pron, resultados, reglas, alias_jugadores))

    return ordenar_clasificacion(participantes)


# ── CLI ──────────────────────────────────────────────────────────────────────
def main() -> None:
    resultados_path = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTADOS

    with open(REGLAS_PATH, encoding="utf-8") as f:
        reglas = json.load(f)
    with open(resultados_path, encoding="utf-8") as f:
        resultados = json.load(f)

    alias = None
    if ALIAS_JUGAD.exists():
        with open(ALIAS_JUGAD, encoding="utf-8") as f:
            alias = json.load(f)

    for porra in ("amigos", "trabajo"):
        clasif = generar_clasificacion(porra, resultados, reglas, alias)
        salida = BASE / "datos" / f"standings_{porra}.json"
        with open(salida, "w", encoding="utf-8") as f:
            json.dump({"porra": porra, "clasificacion": clasif}, f, ensure_ascii=False, indent=2)
        print(f"  {porra}: {len(clasif)} participantes -> {salida.name}")


if __name__ == "__main__":
    main()
