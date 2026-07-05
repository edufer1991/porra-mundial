#!/usr/bin/env python3
"""
tabla_grupo.py — Cálculo de la tabla de un grupo (1º-4º) a partir de los
marcadores de sus 6 partidos.

Módulo compartido entre:
  · descargar_resultados.py → tabla REAL, a partir de los marcadores reales
    descargados de openfootball.
  · puntuar_v2.py → tabla IMPLÍCITA de cada participante, a partir de sus
    propios pronósticos de marcador para los 72 partidos de grupos. Se usa
    como fallback cuando el bloque explícito "posiciones de grupo
    pronosticadas" del Excel no está disponible (p. ej. Excel de origen
    corrupto / no reparseable) — en ese caso la mejor fuente de verdad que
    queda es el marcador que el propio participante predijo para cada
    partido, y de ahí se puede derivar de forma determinista qué tabla de
    grupo esperaba.

Desempate: puntos → diferencia de goles → goles a favor → enfrentamiento
directo (sólo si el empate es entre dos equipos consecutivos en la tabla).
Empates reales de 3+ equipos no se resuelven (se avisa) para no reimplementar
el reglamento completo de desempate de la FIFA (fair play, sorteo, etc.).
"""

from __future__ import annotations


def _pair_key(a: str, b: str) -> frozenset:
    return frozenset({a, b})


def calcular_tabla_grupos(
    partidos_por_grupo: dict[str, list[tuple[str, str, int, int]]],
    min_partidos: int = 6,
) -> tuple[list[dict], list[str]]:
    """
    partidos_por_grupo: {grupo: [(local, visitante, gl, gv), ...]}, sólo
    partidos con marcador conocido (gl/gv no None).

    Un grupo sólo se puntúa si tiene al menos `min_partidos` partidos con
    marcador (por defecto 6 = grupo completo de 4 equipos todos-contra-todos).

    Devuelve (posiciones, avisos):
      posiciones: [{"grupo": "A", "pos": 1, "equipo": "Mexico"}, ...]
      avisos: descripciones de empates no resueltos (informativo)
    """
    resultado: list[dict] = []
    avisos: list[str] = []

    for grupo, partidos in sorted(partidos_por_grupo.items()):
        if len(partidos) < min_partidos:
            continue

        equipos = sorted({p[0] for p in partidos} | {p[1] for p in partidos})
        tabla = {e: {"pts": 0, "gf": 0, "gc": 0} for e in equipos}
        h2h: dict[frozenset, dict[str, int]] = {}

        for local, visit, gl, gv in partidos:
            tabla[local]["gf"] += gl
            tabla[local]["gc"] += gv
            tabla[visit]["gf"] += gv
            tabla[visit]["gc"] += gl
            if gl > gv:
                tabla[local]["pts"] += 3
            elif gl < gv:
                tabla[visit]["pts"] += 3
            else:
                tabla[local]["pts"] += 1
                tabla[visit]["pts"] += 1
            h2h[_pair_key(local, visit)] = {local: gl, visit: gv}

        def clave_orden(e: str, _tabla=tabla):
            return (-_tabla[e]["pts"], -(_tabla[e]["gf"] - _tabla[e]["gc"]), -_tabla[e]["gf"])

        orden = sorted(equipos, key=clave_orden)

        i = 0
        while i < len(orden) - 1:
            a, b = orden[i], orden[i + 1]
            if clave_orden(a) == clave_orden(b):
                enfrentamiento = h2h.get(_pair_key(a, b))
                if enfrentamiento and enfrentamiento.get(a, 0) != enfrentamiento.get(b, 0):
                    if enfrentamiento.get(b, 0) > enfrentamiento.get(a, 0):
                        orden[i], orden[i + 1] = b, a
                else:
                    avisos.append(f"Grupo {grupo}: empate entre {a} y {b} no resoluble.")
            i += 1

        for pos, equipo in enumerate(orden, start=1):
            resultado.append({"grupo": grupo, "pos": pos, "equipo": equipo})

    return resultado, avisos


__all__ = ["calcular_tabla_grupos"]
