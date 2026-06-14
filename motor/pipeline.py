#!/usr/bin/env python3
"""
pipeline.py — Orquestador del ciclo de actualización.

Modos de uso:
  python motor/pipeline.py          # descarga resultados y genera sitio
  python motor/pipeline.py --demo   # regenera datos sintéticos y genera sitio

Llamado por .github/workflows/actualizar.yml.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))


# ── Subprocesos ───────────────────────────────────────────────────────────────

def _run(args: list[str], **kwargs) -> None:
    """Ejecuta un subproceso; propaga el código de salida si falla."""
    result = subprocess.run(args, **kwargs)
    if result.returncode != 0:
        sys.exit(result.returncode)


def descargar_resultados() -> None:
    script = BASE / "motor" / "descargar_resultados.py"
    salida = BASE / "datos" / "resultados.json"
    cmd = [sys.executable, str(script), "--salida", str(salida)]
    print("  descargando resultados…")
    _run(cmd, env=os.environ.copy())


def generar_datos_demo() -> None:
    script = BASE / "motor" / "generar_datos_demo.py"
    print("  generando datos demo…")
    _run([sys.executable, "-X", "utf8", str(script)], env=os.environ.copy())


# ── Entrada principal ─────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de actualización de la porra")
    parser.add_argument("--demo", action="store_true",
                        help="Usar datos sintéticos (no llama a openfootball)")
    args = parser.parse_args()

    ahora = datetime.now(timezone.utc)
    ts    = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.demo:
        print(f"[{ts}] Modo demo: regenerando datos sintéticos.")
        generar_datos_demo()
        print(f"[{ts}] Demo completado.")
        return

    print(f"[{ts}] Descargando resultados y generando sitio.")
    descargar_resultados()

    print("  generando datos web…")
    from motor.generar_sitio import generar_sitio
    generar_sitio(ahora=ahora)

    print(f"[{ts}] Pipeline completado.")


if __name__ == "__main__":
    main()
