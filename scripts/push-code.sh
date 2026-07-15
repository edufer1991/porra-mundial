#!/usr/bin/env bash
# push-code.sh — Hace push de SOLO archivos de código y después sincroniza
# datos frescos en un commit separado.
#
# Uso:
#   bash scripts/push-code.sh "mensaje del commit"
#
# Propósito:
#   Garantiza que datos/resultados.json y web/data/ nunca se mezclan con
#   los commits de código, evitando que un rebase con -X theirs sobreescriba
#   los datos frescos del cron con versiones locales stale.
#   (Bug ocurrido el 2026-07-09 y 2026-07-10 — dos veces.)
#
# Flujo:
#   1. Stage solo archivos de código (motor/, tests/, web/app.js, etc.)
#   2. Commit + pull --rebase + push (sin tocar datos/)
#   3. Descarga fresca de openfootball
#   4. Regenera web/data/ con el código nuevo
#   5. Commit y push de datos solos [skip ci]

set -euo pipefail

MSG="${1:-chore: update}"

# ── Salvaguarda temprana: aviso si hay datos ya en el stage ───────────────────
STAGED_NOW=$(git diff --cached --name-only 2>/dev/null || true)
if [ -n "$STAGED_NOW" ]; then
    DATA_PRE=$(printf '%s\n' "$STAGED_NOW" | grep -E '^(datos/resultados\.json|web/data/.+\.json)$' || true)
    if [ -n "$DATA_PRE" ]; then
        echo "AVISO: hay archivos de datos ya en el stage. El script los desstageará"
        echo "para asegurar que el commit de código quede limpio:"
        printf '%s\n' "$DATA_PRE" | sed 's/^/  · /'
        git restore --staged $DATA_PRE 2>/dev/null || true
        echo ""
    fi
fi

echo "=== [1/5] Stage solo codigo (sin datos/) ==="
git add motor/ tests/ web/app.js web/style.css .github/ scripts/ 2>/dev/null || true
# Añadir otros ficheros de configuracion si existen
for f in .gitattributes .gitignore requirements.txt; do
    [ -f "$f" ] && git add "$f" || true
done

if git diff --cached --quiet; then
    echo "  Nada que commitear en codigo — saltando commit."
else
    git commit -m "${MSG}

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
    echo "  Commit de codigo creado."
fi

echo "=== [2/5] Rebase + push de codigo ==="
# Descartar datos del working tree antes del rebase: pueden existir si alguien
# ejecutó descargar_resultados.py o generar_sitio.py antes de llamar a este
# script. No importa perderlos — los volvemos a descargar en el paso 3.
# Sin esto, git pull --rebase aborta con "unstaged changes" y hay que resolver
# conflictos de datos a mano (ocurrió 2026-07-15).
git restore datos/resultados.json web/data/ 2>/dev/null || true
git pull --rebase
git push
echo "  Codigo pusheado."

echo "=== [3/5] Descarga fresca de openfootball ==="
python -X utf8 motor/descargar_resultados.py

echo "=== [4/5] Regenerar sitio con codigo nuevo y datos frescos ==="
python -X utf8 motor/generar_sitio.py

echo "=== [5/5] Push de datos frescos [skip ci] ==="
TS=$(python -X utf8 -c "import json; print(json.load(open('datos/resultados.json', encoding='utf-8'))['ultima_actualizacion'])")
git add datos/resultados.json web/data/
if git diff --cached --quiet; then
    echo "  Datos sin cambios respecto al remote — nada que pushear."
else
    git commit -m "chore: datos ${TS} [skip ci]"
    # Para datos, si hay conflicto, nuestra descarga fresca siempre gana:
    # acabamos de bajarla de openfootball, es mas reciente que el cron.
    git pull --rebase -X theirs
    git push
    echo "  Datos pusheados (${TS})."
fi

echo ""
echo "=== Done: codigo y datos pusheados de forma independiente. ==="
