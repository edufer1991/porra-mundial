#!/usr/bin/env python3
"""
clasif_real.py — Clasificados reales combinados (openfootball + resolutor de bracket).

Expone:
  clasificados_reales(ronda, resultados, cal_idx, advertencias=None)
    → set[str] de equipos confirmados en esa ronda.

  clasificados_excluidos(ronda, resultados, cal_idx)
    → set[str] de equipos que ya PERDIERON su partido de la ronda
      anterior y por tanto no pueden llegar a `ronda`.

Lógica de combinación:
  · Fuente 1 (openfootball): resultados["clasificados"][ronda].
  · Fuente 2 (resolutor):    para cada partido ya finalizado de la ronda
    anterior, el ganador se añade al conjunto de clasificados aunque
    openfootball aún no haya publicado el fixture actualizado.
  · Caso D (contradicción): un equipo está en openfootball pero el
    resolutor —con la ronda anterior 100 % cerrada— dice algo distinto.
    Se prioriza openfootball, se emite aviso a la lista `advertencias` si
    se pasa, y se imprime a stderr.

Importado por:
  motor/generar_sitio.py  — _estado_clasificado, _clasificados_desglose
  motor/puntuar_v2.py     — _puntuar_clasificados
"""
from __future__ import annotations

import re
import sys
import unicodedata


# ── Helpers básicos ───────────────────────────────────────────────────────────

def norm(t) -> str:
    if not t:
        return ""
    s = unicodedata.normalize("NFD", str(t))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip().lower()


# ── Constantes de bracket ─────────────────────────────────────────────────────

_PREV_ROUND_ELIM: dict[str, str] = {
    "1/8":   "1/16",
    "1/4":   "1/8",
    "semis": "1/4",
    "final": "semis",
    "3-4":   "semis",
}

_NEXT_ROUND_ELIM: dict[str, str] = {
    "1/16":  "1/8",
    "1/8":   "1/4",
    "1/4":   "semis",
    "semis": "final",
}

# Tamaño esperado de clasificados[R] cuando esa ronda está 100 % determinada.
EXPECTED_CLASIF_SIZE: dict[str, int] = {
    "1/16": 32, "1/8": 16, "1/4": 8, "semis": 4, "final": 2,
}

_RE_WINNER = re.compile(r"^W(\d+)$", re.IGNORECASE)
_RE_LOSER  = re.compile(r"^L(\d+)$", re.IGNORECASE)


def _fase_a_ronda(fase: str) -> str:
    return {
        "1/16": "1/16", "1/8": "1/8", "1/4": "1/4",
        "semis": "semis", "tercer_puesto": "3-4", "final": "final",
    }.get(fase, fase)


# ── Ganador / perdedor de un partido ─────────────────────────────────────────

def _ganador_partido(match_id: int, marc_por_id: dict,
                     cal_idx: dict, real_clasif: dict) -> str | None:
    """
    Ganador de un partido de eliminatoria finalizado. Si el resultado fue
    empate (fue a penaltis y nuestro marcador no lo distingue), cruza con
    la lista de clasificados de la siguiente ronda para desambiguar.
    """
    m = marc_por_id.get(match_id)
    if not m or m.get("estado") != "finalizado":
        return None
    L, V = m.get("local"), m.get("visitante")
    if not L or not V:
        return None
    gl, gv = m.get("goles_local"), m.get("goles_visitante")
    if gl is not None and gv is not None and gl != gv:
        return L if gl > gv else V
    cal = cal_idx.get(match_id)
    if not cal:
        return None
    next_r = _NEXT_ROUND_ELIM.get(_fase_a_ronda(cal.get("fase") or ""))
    if not next_r:
        return None
    real_next = {norm(t) for t in (real_clasif.get(next_r) or [])}
    if norm(L) in real_next: return L
    if norm(V) in real_next: return V
    return None


def _perdedor_partido(match_id: int, marc_por_id: dict,
                      cal_idx: dict, real_clasif: dict) -> str | None:
    """Análogo a _ganador_partido para el perdedor."""
    m = marc_por_id.get(match_id)
    if not m or m.get("estado") != "finalizado":
        return None
    L, V = m.get("local"), m.get("visitante")
    if not L or not V:
        return None
    ganador = _ganador_partido(match_id, marc_por_id, cal_idx, real_clasif)
    if not ganador:
        return None
    return V if norm(ganador) == norm(L) else L


# ── Clasificados reales combinados ────────────────────────────────────────────

def clasificados_reales(ronda: str, resultados: dict, cal_idx: dict,
                        advertencias: list | None = None) -> set[str]:
    """
    Devuelve el conjunto de equipos confirmados en `ronda` combinando:
      · openfootball (resultados["clasificados"][ronda])
      · resolutor de bracket (ganadores de partidos finalizados en prev(ronda))

    Caso D — contradicción cuando la ronda anterior ya está 100 % cerrada:
      · Prioriza openfootball.
      · Añade aviso a `advertencias` (si se pasa) y también a stderr.
    """
    real_clasif = resultados.get("clasificados") or {}
    of_set: set[str] = {norm(t) for t in (real_clasif.get(ronda) or [])}

    prev = _PREV_ROUND_ELIM.get(ronda)
    if not prev:
        return of_set

    marc_por_id: dict = {m["match_id"]: m for m in (resultados.get("marcadores") or [])}

    # Derivar ganadores de cada partido finalizado de la ronda anterior.
    derived: set[str] = set()
    prev_partidos = [p for p in cal_idx.values()
                     if _fase_a_ronda(p.get("fase") or "") == prev]
    prev_completa = bool(prev_partidos) and all(
        marc_por_id.get(p["id"], {}).get("estado") == "finalizado"
        for p in prev_partidos
    )
    for p in prev_partidos:
        ganador = _ganador_partido(p["id"], marc_por_id, cal_idx, real_clasif)
        if ganador:
            derived.add(norm(ganador))

    # Caso D: con la ronda anterior completa, ambas fuentes tienen datos
    # pero no coinciden.
    if prev_completa and of_set and derived:
        of_only      = {t for t in of_set   if t not in derived}
        derived_only = {t for t in derived  if t not in of_set}
        if of_only or derived_only:
            msg = (f"[AVISO] Contradicción clasificados[{ronda}]: "
                   f"openfootball_exclusivo={sorted(of_only)}, "
                   f"resolutor_exclusivo={sorted(derived_only)}")
            print(msg, file=sys.stderr)
            if advertencias is not None:
                advertencias.append({
                    "nivel": "AVISO",
                    "tipo":  "contradiccion_clasif",
                    "ronda": ronda,
                    "mensaje": msg,
                })

    return of_set | derived   # openfootball tiene prioridad (no se elimina nada)


def clasificados_excluidos(ronda: str, resultados: dict, cal_idx: dict) -> set[str]:
    """
    Equipos que ya jugaron en prev(ronda) y PERDIERON — por tanto están
    confirmados FUERA de `ronda`, aunque la lista openfootball de esa ronda
    aún no se haya publicado y la ronda no esté 100 % completa.

    Ejemplo: Brazil perdió contra Norway en 1/8 → "fallo" en 1/4 incluso
    si clasificados["1/4"] todavía está vacío en openfootball.
    """
    prev = _PREV_ROUND_ELIM.get(ronda)
    if not prev:
        return set()
    marc_por_id: dict = {m["match_id"]: m for m in (resultados.get("marcadores") or [])}
    real_clasif = resultados.get("clasificados") or {}
    excluidos: set[str] = set()
    for p in cal_idx.values():
        if _fase_a_ronda(p.get("fase") or "") != prev:
            continue
        perdedor = _perdedor_partido(p["id"], marc_por_id, cal_idx, real_clasif)
        if perdedor:
            excluidos.add(norm(perdedor))
    return excluidos
