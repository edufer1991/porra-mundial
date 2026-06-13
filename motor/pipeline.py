#!/usr/bin/env python3
"""
pipeline.py — Orquestador del ciclo de actualización.

Modos de uso:
  python motor/pipeline.py                    # cron: verifica ventana antes de actuar
  python motor/pipeline.py --forzar           # salta la comprobación de ventana
  python motor/pipeline.py --demo             # regenera datos sintéticos y genera sitio
  python motor/pipeline.py --solo-verificar   # sale con código 0 si hay ventana, 1 si no

Llamado por .github/workflows/actualizar.yml.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# ── Configuración de ventana ──────────────────────────────────────────────────

VENTANA_ANTES   = timedelta(hours=1)   # empieza a sondear 1 h antes del partido
VENTANA_DESPUES = timedelta(hours=3)   # sigue hasta 3 h después (tiempo extra + penaltis)


# ── Comprobación de ventana ───────────────────────────────────────────────────

def hay_ventana_activa(partidos: list[dict], ahora: datetime) -> bool:
    """True si algún partido está en curso o es inminente."""
    for p in partidos:
        try:
            inicio = datetime.fromisoformat(
                p["fecha_hora_utc"].replace("Z", "+00:00")
            )
        except Exception:
            continue
        if inicio - VENTANA_ANTES <= ahora <= inicio + VENTANA_DESPUES:
            return True
    return False


# ── Subprocesos ───────────────────────────────────────────────────────────────

def _run(args: list[str], **kwargs) -> None:
    """Ejecuta un subproceso; propaga el código de salida si falla."""
    result = subprocess.run(args, **kwargs)
    if result.returncode != 0:
        sys.exit(result.returncode)


def descargar_resultados(sin_api: bool = False) -> None:
    """
    Llama a descargar_resultados.py con el entorno actual.
    sin_api=True → pasa --sin-api: solo openfootball, sin llamar a API-Football.
    """
    script = BASE / "motor" / "descargar_resultados.py"
    salida = BASE / "datos" / "resultados.json"
    cmd = [sys.executable, str(script), "--salida", str(salida)]
    if sin_api:
        cmd.append("--sin-api")
    nota = "  (solo openfootball, sin API)" if sin_api else ""
    print(f"  descargando resultados…{nota}")
    _run(cmd, env=os.environ.copy())


def generar_datos_demo() -> None:
    """Regenera todos los datos sintéticos de prueba."""
    script = BASE / "motor" / "generar_datos_demo.py"
    print("  generando datos demo…")
    _run([sys.executable, "-X", "utf8", str(script)], env=os.environ.copy())


# ── Entrada principal ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de actualización de la porra")
    parser.add_argument("--forzar",           action="store_true",
                        help="Ignorar comprobación de ventana de partido")
    parser.add_argument("--demo",             action="store_true",
                        help="Usar datos sintéticos (no llama a la API)")
    parser.add_argument("--solo-verificar",   action="store_true",
                        help="Solo verifica si hay ventana; sale 0=sí, 1=no")
    args = parser.parse_args()

    ahora = datetime.now(timezone.utc)
    ts    = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Modo demo ────────────────────────────────────────────────────────────
    if args.demo:
        print(f"[{ts}] Modo demo: regenerando datos sintéticos.")
        generar_datos_demo()
        # En modo demo los datos ya están en web/data/; no hay que llamar a generar_sitio
        print(f"[{ts}] Demo completado.")
        return

    # ── Cargar calendario ────────────────────────────────────────────────────
    cal_path = BASE / "datos" / "calendario.json"
    try:
        with open(cal_path, encoding="utf-8") as f:
            partidos = json.load(f).get("partidos", [])
    except FileNotFoundError:
        print(f"[ERROR] No se encuentra {cal_path}", file=sys.stderr)
        sys.exit(2)

    ventana = hay_ventana_activa(partidos, ahora)

    # ── Modo solo-verificar ───────────────────────────────────────────────────
    if args.solo_verificar:
        if ventana:
            print(f"[{ts}] Ventana activa.")
            sys.exit(0)
        else:
            print(f"[{ts}] Sin ventana de partido.")
            sys.exit(1)

    en_ventana = ventana or args.forzar

    # ── Paso 1: descargar resultados ──────────────────────────────────────────
    # Siempre: openfootball (URL pública, sin clave, coste cero).
    # Solo en ventana: también la API-Football en directo (gasta cuota).
    if en_ventana:
        print(f"[{ts}] Ventana activa (forzar={args.forzar}). Pipeline completo.")
    else:
        print(f"[{ts}] Sin ventana activa — descargando openfootball para recoger "
              f"resultados pendientes (API-Football omitida).")

    descargar_resultados(sin_api=not en_ventana)

    # ── Paso 2: generar sitio (standings + detalle + proximos + snapshots) ────
    print("  generando datos web…")
    from motor.generar_sitio import generar_sitio
    generar_sitio(ahora=ahora)

    print(f"[{ts}] Pipeline completado.")


if __name__ == "__main__":
    main()
