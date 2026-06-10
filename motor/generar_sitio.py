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
)

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
                    reglas: dict) -> dict:
    """Genera detalle.json por nickname para la vista Mi Porra."""
    dir_porra = BASE / "datos" / "pronosticos" / porra
    if not dir_porra.exists():
        return {}

    marcadores_map = {m["match_id"]: m for m in (resultados.get("marcadores") or [])}
    detalle = {}

    for ruta in sorted(dir_porra.glob("*.json")):
        try:
            pron = _leer(ruta)
        except Exception as e:
            print(f"  [AVISO] {ruta.name}: {e}", file=sys.stderr)
            continue

        nick = pron.get("nickname", ruta.stem)
        pp   = pron.get("pronosticos", {})

        detalle[nick] = {
            "nickname":      nick,
            "grupos":        _detalle_grupos(pp.get("grupos", []), marcadores_map, reglas),
            "elim_marcadores": pp.get("elim_marcadores", []),
            "clasificados":  pp.get("clasificados", {}),
            "honor":         pp.get("honor", {}),
            "premios":       pp.get("premios", {}),
        }

    return detalle


# ── Próximos partidos ─────────────────────────────────────────────────────────

def generar_proximos(porra: str,
                     partidos: list[dict],
                     resultados: dict,
                     ahora: datetime,
                     n: int = 8) -> list[dict]:
    """
    Próximos N partidos de grupos (no finalizados) con las predicciones de todos.
    """
    dir_porra = BASE / "datos" / "pronosticos" / porra
    marcadores_map = {m["match_id"]: m for m in (resultados.get("marcadores") or [])}

    # Construir mapa match_id → lista de predicciones por nickname
    preds_por_id: dict[int, list] = {}
    if dir_porra.exists():
        for ruta in sorted(dir_porra.glob("*.json")):
            try:
                pron = _leer(ruta)
            except Exception:
                continue
            nick = pron.get("nickname", ruta.stem)
            for g in pron.get("pronosticos", {}).get("grupos", []):
                mid = g.get("match_id")
                if mid is None:
                    continue
                preds_por_id.setdefault(mid, []).append({
                    "nickname":   nick,
                    "prediccion": g.get("prediccion"),
                })

    ventana_pasado = timedelta(hours=2)
    proximos = []

    for p in sorted(partidos, key=lambda x: x.get("fecha_hora_utc", "")):
        if p.get("fase") != "grupos":
            continue
        try:
            inicio = datetime.fromisoformat(
                p["fecha_hora_utc"].replace("Z", "+00:00")
            )
        except Exception:
            continue

        marc = marcadores_map.get(p["id"], {})
        estado = marc.get("estado", "pendiente")

        # Excluir ya finalizados desde hace más de ventana_pasado
        if estado == "finalizado" and (ahora - inicio) > ventana_pasado:
            continue
        if estado == "pendiente" and inicio < ahora - ventana_pasado:
            continue

        proximos.append({
            "match_id":       p["id"],
            "fecha_hora_utc": p["fecha_hora_utc"],
            "fase":           p.get("fase", ""),
            "grupo":          p.get("grupo", ""),
            "jornada":        p.get("jornada", ""),
            "local":          p["local"],
            "visitante":      p["visitante"],
            "estado":         estado,
            "goles_local":    marc.get("goles_local"),
            "goles_visitante": marc.get("goles_visitante"),
            "predicciones":   preds_por_id.get(p["id"], []),
        })

        if len(proximos) >= n:
            break

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
        detalle = generar_detalle(porra, resultados, reglas)
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
