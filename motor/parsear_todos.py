#!/usr/bin/env python3
"""
parsear_todos.py — Parsea en lote todos los .xlsx de datos/excels_recibidos/
y escribe los JSON en datos/pronosticos/<porra>/.

Uso:
    python -X utf8 motor/parsear_todos.py [amigos|trabajo]
    Sin argumentos procesa ambas porras.
"""

import json
import re
import sys
import traceback
from pathlib import Path

BASE   = Path(__file__).resolve().parent.parent
INBOX  = BASE / "datos" / "excels_recibidos"
OUTDIR = BASE / "datos" / "pronosticos"

# Importar la función del parser individual
sys.path.insert(0, str(Path(__file__).parent))
from parsear_excel import parsear_excel


def nick_safe(nickname: str) -> str:
    return re.sub(r"[^\w\-]", "_", nickname)


def procesar_porra(porra: str) -> dict:
    carpeta = INBOX / porra
    if not carpeta.exists():
        print(f"  [AVISO] Carpeta no encontrada: {carpeta}")
        return {"ok": [], "incompletos": [], "errores": [], "duplicados": []}

    archivos = sorted(carpeta.glob("*.xlsx"))
    if not archivos:
        print(f"  [AVISO] No hay .xlsx en {carpeta}")
        return {"ok": [], "incompletos": [], "errores": [], "duplicados": []}

    vistos: dict[str, str] = {}   # nickname_safe -> nombre archivo original
    ok, incompletos, errores, duplicados = [], [], [], []

    for ruta in archivos:
        try:
            resultado = parsear_excel(ruta, porra)
        except Exception:
            errores.append({
                "archivo": ruta.name,
                "detalle": traceback.format_exc().strip().splitlines()[-1],
            })
            continue

        nick = resultado.get("nickname") or ""
        if not nick:
            # Sin nickname no podemos nombrar el JSON, tratamos como error
            errores.append({
                "archivo": ruta.name,
                "detalle": "nickname vacío (Pool!C5 sin rellenar)",
            })
            continue

        ns = nick_safe(nick)
        if ns in vistos:
            duplicados.append({
                "archivo":    ruta.name,
                "nickname":   nick,
                "ya_guardado_de": vistos[ns],
            })
            continue

        destino = OUTDIR / porra / f"{ns}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)

        vistos[ns] = ruta.name

        if resultado["incompleto"]:
            incompletos.append({
                "archivo":      ruta.name,
                "nickname":     nick,
                "advertencias": resultado["advertencias"],
            })
        else:
            ok.append({"archivo": ruta.name, "nickname": nick})

    return {"ok": ok, "incompletos": incompletos, "errores": errores, "duplicados": duplicados}


def imprimir_resumen(porra: str, r: dict) -> None:
    total = len(r["ok"]) + len(r["incompletos"]) + len(r["errores"]) + len(r["duplicados"])
    print(f"\n{'─'*60}")
    print(f"  PORRA: {porra.upper()}  ({total} archivos procesados)")
    print(f"{'─'*60}")

    if r["ok"]:
        print(f"\n  ✓ COMPLETOS ({len(r['ok'])})")
        for e in r["ok"]:
            print(f"    {e['archivo']}  →  {e['nickname']}")

    if r["incompletos"]:
        print(f"\n  ! INCOMPLETOS ({len(r['incompletos'])})")
        for e in r["incompletos"]:
            print(f"    {e['archivo']}  →  {e['nickname']}")
            for adv in e["advertencias"]:
                print(f"        · {adv}")

    if r["duplicados"]:
        print(f"\n  ⚠ NICKNAMES DUPLICADOS ({len(r['duplicados'])})  — no guardados")
        for e in r["duplicados"]:
            print(f"    {e['archivo']}  →  nickname '{e['nickname']}' ya existe (de {e['ya_guardado_de']})")

    if r["errores"]:
        print(f"\n  ✗ ERRORES ({len(r['errores'])})")
        for e in r["errores"]:
            print(f"    {e['archivo']}")
            print(f"        {e['detalle']}")


def main() -> None:
    porras_disponibles = ("amigos", "trabajo")

    if len(sys.argv) > 1:
        porra_arg = sys.argv[1].lower()
        if porra_arg not in porras_disponibles:
            print(f"ERROR: porra debe ser 'amigos' o 'trabajo', recibido: '{porra_arg}'")
            sys.exit(1)
        porras = [porra_arg]
    else:
        porras = list(porras_disponibles)

    resultados = {}
    for porra in porras:
        print(f"\nProcesando {porra}…")
        resultados[porra] = procesar_porra(porra)
        imprimir_resumen(porra, resultados[porra])

    # Código de salida: 0 si todo OK o solo incompletos; 1 si hay errores o duplicados
    hay_problemas = any(
        r["errores"] or r["duplicados"] for r in resultados.values()
    )
    print()
    sys.exit(1 if hay_problemas else 0)


if __name__ == "__main__":
    main()
