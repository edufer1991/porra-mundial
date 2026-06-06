#!/usr/bin/env python3
"""
descargar_resultados.py — Descarga y normaliza resultados del Mundial.

Fuente principal : openfootball worldcup.json (JSON público, sin clave).
Respaldo         : API-Football (clave en env var API_FOOTBALL_KEY).
Premios manuales : datos/premios.json  →  se vuelca a resultados.json.

Uso:
  python motor/descargar_resultados.py                   # 2026, escribe datos/resultados.json
  python motor/descargar_resultados.py --ano 2022        # valida mecanica contra Qatar 2022
  python motor/descargar_resultados.py --archivo f.json  # usa fichero local (omite descarga)
  python motor/descargar_resultados.py --salida out.json # ruta de salida personalizada
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE         = Path(__file__).resolve().parent.parent
CALENDARIO   = BASE / "datos" / "calendario.json"
RESULTADOS   = BASE / "datos" / "resultados.json"
PREMIOS_JSON = BASE / "datos" / "premios.json"
EQUIVALENCIAS = BASE / "datos" / "equivalencias_equipos.json"

# Códigos de bracket del calendario (aún sin equipo asignado)
# Cubre: 1A, 2B, 3ABC, 3A/B/C/D/F, W73, L88, WF, LF, W34
_RE_PLACEHOLDER = re.compile(
    r'^([12][A-L]|3[A-L][/A-L]*|[WL]\d+|WF|LF|W34)$', re.IGNORECASE
)

OF_URL_TPL = (
    "https://raw.githubusercontent.com/openfootball/worldcup.json"
    "/master/{ano}/worldcup.json"
)

# Mapeo nombre de ronda openfootball → clave interna de la porra
RONDAS_2026: dict[str, str] = {
    "Round of 32":              "1/16",
    "Round of 16":              "1/8",
    "Quarter-finals":           "1/4",
    "Quarter finals":           "1/4",
    "Semi-finals":              "semis",
    "Semi finals":              "semis",
    "Final":                    "final",
    "Third-place play-off":     "tercer_puesto",
    "Third place play-off":     "tercer_puesto",
    "Play-off for third place": "tercer_puesto",
    "Match for third place":    "tercer_puesto",
}

# 2022: primera ronda eliminatoria era octavos (32 equipos → 16); la mecánica es la misma
RONDAS_2022: dict[str, str] = {
    "Round of 16":              "1/16",   # primer corte de la eliminatoria
    "Quarter-finals":           "1/4",
    "Quarter finals":           "1/4",
    "Semi-finals":              "semis",
    "Semi finals":              "semis",
    "Final":                    "final",
    "Third-place play-off":     "tercer_puesto",
    "Third place play-off":     "tercer_puesto",
    "Play-off for third place": "tercer_puesto",
    "Match for third place":    "tercer_puesto",
}

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"


# ── Utilidades ────────────────────────────────────────────────────────────────

def norm(t) -> str:
    if not t:
        return ""
    s = unicodedata.normalize("NFD", str(t))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").strip().lower()


def _es_placeholder(nombre: str) -> bool:
    """True si el nombre es un código de bracket (ej. '1A', 'W73', '3ABCD')."""
    return bool(_RE_PLACEHOLDER.match(nombre.strip()))


def _build_nombre_map(equivalencias: dict) -> dict[str, str]:
    """
    Construye {norm(variante) → nombre_openfootball} desde equivalencias_equipos.json.
    Permite resolver variantes como 'Bosnia & Herzegovina' → 'Bosnia-Herzegovina'.
    """
    mapping: dict[str, str] = {}
    for sel in equivalencias.get("selecciones", []):
        canonical = sel.get("nombre_openfootball", "")
        if not canonical:
            continue
        # El nombre canónico se mapea a sí mismo
        mapping[norm(canonical)] = canonical
        # Nombre en Excel
        excel_name = sel.get("nombre_excel", "")
        if excel_name:
            mapping[norm(excel_name)] = canonical
        # Aliases conocidos
        for alias in sel.get("aliases_es", []):
            if alias:
                mapping[norm(alias)] = canonical
    return mapping


def _fetch_json(url: str, api_key: str | None = None) -> dict | None:
    import ssl
    # Try verified SSL first; fall back to unverified (workaround para Windows con certs mal configurados)
    ssl_contexts: list = [None]
    _unverified = ssl.create_default_context()
    _unverified.check_hostname = False
    _unverified.verify_mode = ssl.CERT_NONE
    ssl_contexts.append(_unverified)

    import urllib.error

    last_exc: Exception | None = None
    for ctx in ssl_contexts:
        try:
            req = urllib.request.Request(url)
            if api_key:
                req.add_header("x-apisports-key", api_key)
            kw: dict = {"timeout": 20}
            if ctx is not None:
                kw["context"] = ctx
            with urllib.request.urlopen(req, **kw) as r:
                return json.loads(r.read().decode())
        except (ssl.SSLError, urllib.error.URLError) as exc:
            last_exc = exc
            # Solo reintentar si la causa es un error SSL
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLError):
                continue
            break
        except Exception as exc:
            last_exc = exc
            break

    print(f"  [AVISO] fetch fallido para {url}: {last_exc}", file=sys.stderr)
    return None


def _score_ft(score: dict | None) -> tuple[int, int] | None:
    """Devuelve (goles_local, goles_visitante) a tiempo reglamentario, o None."""
    if not score:
        return None
    ft = score.get("ft")
    if ft and len(ft) == 2 and ft[0] is not None and ft[1] is not None:
        return int(ft[0]), int(ft[1])
    return None


def _ganador_perdedor(match: dict) -> tuple[str | None, str | None]:
    """Devuelve (ganador, perdedor). Usa penaltis > prorroga > T.R."""
    score = match.get("score") or {}
    for clave in ("p", "et", "ft"):
        val = score.get(clave)
        if val and len(val) == 2 and val[0] is not None and val[1] is not None:
            g1, g2 = int(val[0]), int(val[1])
            if g1 > g2:
                return match["team1"], match["team2"]
            elif g2 > g1:
                return match["team2"], match["team1"]
    return None, None


def _determinar_estado(match: dict, ahora: datetime | None = None) -> str:
    if _score_ft(match.get("score")):
        return "finalizado"
    fecha = match.get("date")
    hora  = match.get("time", "00:00")
    if fecha and ahora:
        try:
            ts_str = f"{fecha}T{hora}:00Z"
            ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            diff = (ahora - ts).total_seconds()
            if 0 <= diff <= 7200:
                return "en_juego"
        except ValueError:
            pass
    return "pendiente"


def _map_ronda(ronda_str: str, rondas: dict[str, str]) -> str | None:
    if ronda_str in rondas:
        return rondas[ronda_str]
    rn = norm(ronda_str)
    for k, v in rondas.items():
        if norm(k) == rn:
            return v
    return None


# ── Índice de partidos de grupos ──────────────────────────────────────────────

def _build_grupo_index(calendario: dict) -> dict[tuple[str, str], int]:
    """
    Devuelve {(norm(local), norm(visitante)): match_id} para fase de grupos.
    Bidireccional por si openfootball invierte la asignación local/visitante.
    """
    idx: dict[tuple[str, str], int] = {}
    for p in calendario.get("partidos", []):
        if p.get("fase") == "grupos":
            k1 = (norm(p["local"]),     norm(p["visitante"]))
            k2 = (norm(p["visitante"]), norm(p["local"]))
            idx[k1] = p["id"]
            idx[k2] = p["id"]
    return idx


def _build_match_dir_index(calendario: dict) -> dict[tuple[str, str], tuple[int, bool]]:
    """
    Índice orientado para la fusión con API-Football.
    Devuelve {(norm_equipoA, norm_equipoB): (match_id, invertido)} donde
    invertido=False si equipoA es el local del calendario,
    invertido=True  si equipoA es el visitante (la API los devuelve al revés).
    Necesario porque _build_grupo_index es bidireccional y no distingue orientación.
    """
    idx: dict[tuple[str, str], tuple[int, bool]] = {}
    for p in calendario.get("partidos", []):
        if p.get("fase") == "grupos":
            nl, nv = norm(p["local"]), norm(p["visitante"])
            idx[(nl, nv)] = (p["id"], False)   # home API == local  → sin inversión
            idx[(nv, nl)] = (p["id"], True)    # home API == visitante → invertido
    return idx


# ── Parser principal ──────────────────────────────────────────────────────────

def parsear_openfootball(
    data: dict,
    grupo_idx: dict[tuple[str, str], int],
    rondas: dict[str, str],
    ahora: datetime | None = None,
    nombre_map: dict[str, str] | None = None,
) -> dict:
    """
    Convierte JSON de openfootball al esquema de resultados.json.

    nombre_map: {norm(variante) → nombre_canonico} para resolver aliases de equipos.

    Retorna dict con:
      marcadores   — partidos de grupos con match_id, estado, goles
      clasificados — equipos por ronda eliminatoria (conjuntos)
      honor        — campeon/subcampeon/tercero/cuarto
      stats        — contadores de diagnóstico
    """
    RONDAS_CLAS = {"1/16", "1/8", "1/4", "semis", "final"}

    def _resolver_nombre(nombre: str) -> str:
        """Devuelve el nombre canónico (openfootball) resolviendo aliases."""
        if not nombre_map:
            return nombre
        return nombre_map.get(norm(nombre), nombre)

    marcadores:   list[dict]          = []
    clasificados: dict[str, set[str]] = {r: set() for r in RONDAS_CLAS}
    honor = {"campeon": None, "subcampeon": None, "tercero": None, "cuarto": None}
    stats = {"grupos_encontrados": 0, "grupos_sin_id": 0, "elim_procesadas": 0}

    for match in data.get("matches", []):
        ronda_of = match.get("round", "")
        t1_raw = match.get("team1", "") or ""
        t2_raw = match.get("team2", "") or ""
        t1 = _resolver_nombre(t1_raw)
        t2 = _resolver_nombre(t2_raw)

        # ── Grupos ──────────────────────────────────────────────────────────
        if match.get("group"):
            stats["grupos_encontrados"] += 1
            mid = grupo_idx.get((norm(t1), norm(t2)))
            if mid is None:
                mid = grupo_idx.get((norm(t2), norm(t1)))
            if mid is None:
                stats["grupos_sin_id"] += 1
                continue
            estado = _determinar_estado(match, ahora)
            marc: dict = {"match_id": mid, "estado": estado}
            if estado in ("finalizado", "en_juego"):
                ft = _score_ft(match.get("score"))
                if ft:
                    marc["goles_local"], marc["goles_visitante"] = ft
            marcadores.append(marc)
            continue

        # ── Eliminatorias ───────────────────────────────────────────────────
        clave = _map_ronda(ronda_of, rondas)
        if not clave:
            continue

        stats["elim_procesadas"] += 1

        # Ignorar bracket codes (el equipo aún no está determinado)
        t1_real = t1 if t1 and not _es_placeholder(t1) else None
        t2_real = t2 if t2 and not _es_placeholder(t2) else None

        if clave == "tercer_puesto":
            if t1_real and t2_real and _score_ft(match.get("score")):
                ganador, perdedor = _ganador_perdedor(match)
                if ganador == t1_raw:
                    honor["tercero"], honor["cuarto"] = t1_real, t2_real
                else:
                    honor["tercero"], honor["cuarto"] = t2_real, t1_real
        elif clave in RONDAS_CLAS:
            if t1_real:
                clasificados[clave].add(t1_real)
            if t2_real:
                clasificados[clave].add(t2_real)
            if clave == "final" and t1_real and t2_real and _score_ft(match.get("score")):
                ganador, perdedor = _ganador_perdedor(match)
                if ganador == t1_raw:
                    honor["campeon"], honor["subcampeon"] = t1_real, t2_real
                else:
                    honor["campeon"], honor["subcampeon"] = t2_real, t1_real

    return {
        "marcadores":   sorted(marcadores, key=lambda m: m["match_id"]),
        "clasificados": {k: sorted(v) for k, v in clasificados.items()},
        "honor":        honor,
        "stats":        stats,
    }


# ── Premios manuales ──────────────────────────────────────────────────────────

def cargar_premios() -> dict:
    """Lee datos/premios.json; devuelve solo goleador/mvp/portero."""
    base = {"goleador": None, "mvp": None, "portero": None}
    if PREMIOS_JSON.exists():
        with open(PREMIOS_JSON, encoding="utf-8") as f:
            raw = json.load(f)
        for k in base:
            base[k] = raw.get(k)
    return base


# ── API-Football (respaldo / goleadores en vivo) ──────────────────────────────

def _fetch_api_football_live(key: str) -> list[dict]:
    """
    Devuelve fixtures actualmente en juego desde API-Football.
    Se usa para actualizar marcadores de grupos en tiempo real.
    """
    url  = f"{API_FOOTBALL_BASE}/fixtures?live=all"
    data = _fetch_json(url, api_key=key)
    if not data:
        return []
    return data.get("response", [])


def _fetch_api_football_goleadores(key: str, league_id: int, season: int) -> list[dict]:
    """
    Devuelve tabla de goleadores desde API-Football.
    league_id para WC 2026 a confirmar durante el torneo.
    """
    url  = f"{API_FOOTBALL_BASE}/players/topscorers?league={league_id}&season={season}"
    data = _fetch_json(url, api_key=key)
    if not data:
        return []
    return data.get("response", [])


def _fusionar_api_football(
    marcadores: list[dict],
    live_fixtures: list[dict],
    nombre_map: dict[str, str],
    match_dir_idx: dict[tuple[str, str], tuple[int, bool]],
) -> tuple[list[dict], int]:
    """
    Completa / actualiza marcadores de grupos (base openfootball) con datos de API-Football.

    match_dir_idx debe ser el resultado de _build_match_dir_index(), no de
    _build_grupo_index(): el índice orientado codifica si los equipos de la API
    están invertidos respecto al calendario, lo que determina cómo asignar los goles.

    Regla de fusión: solo modifica entradas cuyo estado actual es 'pendiente' o 'en_juego';
    nunca sobreescribe un 'finalizado' ya confirmado por openfootball.
    Devuelve (lista_actualizada, n_cambios).
    """
    STATUS_LIVE = {"1H", "HT", "2H", "ET", "BT", "P", "INT"}
    STATUS_FT   = {"FT", "AET", "PEN"}

    marc_map: dict[int, dict] = {m["match_id"]: m for m in marcadores}
    n_act = 0

    for fix in live_fixtures:
        status_short = fix.get("fixture", {}).get("status", {}).get("short", "")
        if status_short not in STATUS_LIVE | STATUS_FT:
            continue

        goals      = fix.get("goals", {})
        g_home_raw = goals.get("home")
        g_away_raw = goals.get("away")
        if g_home_raw is None or g_away_raw is None:
            continue

        home_raw = fix.get("teams", {}).get("home", {}).get("name", "")
        away_raw = fix.get("teams", {}).get("away", {}).get("name", "")
        home_can = nombre_map.get(norm(home_raw), home_raw)
        away_can = nombre_map.get(norm(away_raw), away_raw)

        # Buscar match_id y orientación usando el índice dirigido
        entry = match_dir_idx.get((norm(home_can), norm(away_can)))
        if entry is None:
            continue  # no es un partido de grupos 2026
        mid, invertido = entry

        # invertido=True → la API pone como home al equipo que en el calendario es visitante;
        # hay que cruzar los goles para que goles_local corresponda siempre al local del calendario.
        gl = int(g_away_raw) if invertido else int(g_home_raw)
        gv = int(g_home_raw) if invertido else int(g_away_raw)

        api_estado = "finalizado" if status_short in STATUS_FT else "en_juego"
        cur_estado = marc_map.get(mid, {}).get("estado", "pendiente")

        # Solo actualizar si openfootball aún no tiene el resultado definitivo
        if cur_estado in ("pendiente", "en_juego"):
            marc_map[mid] = {
                "match_id":        mid,
                "estado":          api_estado,
                "goles_local":     gl,
                "goles_visitante": gv,
                "_fuente":         "api_football",
            }
            n_act += 1

    return sorted(marc_map.values(), key=lambda m: m["match_id"]), n_act


# ── Escritura ─────────────────────────────────────────────────────────────────

def guardar_resultados(resultado: dict, path: Path = RESULTADOS) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarga resultados del Mundial desde openfootball."
    )
    parser.add_argument("--ano",     default="2026",
                        help="Ano del torneo (default: 2026)")
    parser.add_argument("--archivo", default=None,
                        help="Ruta local al JSON de openfootball (omite la descarga)")
    parser.add_argument("--salida",  default=None,
                        help="Ruta de salida (default: datos/resultados.json)")
    args = parser.parse_args()

    ano    = args.ano
    salida = Path(args.salida) if args.salida else RESULTADOS

    # Calendario 2026 (siempre se usa para resolver match_ids de grupos)
    with open(CALENDARIO, encoding="utf-8") as f:
        calendario = json.load(f)
    grupo_idx    = _build_grupo_index(calendario)
    match_dir_idx = _build_match_dir_index(calendario)

    # Mapa de nombres para resolver aliases openfootball ↔ nombre canónico
    nombre_map: dict[str, str] | None = None
    if EQUIVALENCIAS.exists():
        with open(EQUIVALENCIAS, encoding="utf-8") as f:
            nombre_map = _build_nombre_map(json.load(f))

    rondas = RONDAS_2022 if ano == "2022" else RONDAS_2026

    # Fuente openfootball
    if args.archivo:
        print(f"  Usando fichero local: {args.archivo}")
        with open(args.archivo, encoding="utf-8") as f:
            of_data = json.load(f)
    else:
        url = OF_URL_TPL.format(ano=ano)
        print(f"  Descargando {url} ...")
        of_data = _fetch_json(url)
        if of_data is None:
            print("  [ERROR] No se pudo obtener datos de openfootball. Abortando.", file=sys.stderr)
            sys.exit(1)

    ahora     = datetime.now(timezone.utc)
    resultado = parsear_openfootball(of_data, grupo_idx, rondas, ahora, nombre_map)
    stats     = resultado.pop("stats")

    # Premios manuales
    premios = cargar_premios()

    # API-Football — respaldo live: solo si algún partido ya ha comenzado (guarda de cuota)
    api_key = os.environ.get("API_FOOTBALL_KEY")
    if api_key:
        partidos_iniciados = [
            p for p in calendario.get("partidos", [])
            if p.get("fase") == "grupos"
            and datetime.fromisoformat(
                p["fecha_hora_utc"].replace("Z", "+00:00")
            ) <= ahora
        ]
        if partidos_iniciados:
            print(f"  API-Football: {len(partidos_iniciados)} partido(s) de grupo iniciado(s);"
                  f" consultando fixtures?live=all …")
            live = _fetch_api_football_live(api_key)
            if live:
                resultado["marcadores"], n_act = _fusionar_api_football(
                    resultado["marcadores"], live, nombre_map or {}, match_dir_idx
                )
                print(f"  API-Football: {n_act} marcador(es) completados/actualizados.")
            else:
                print("  API-Football: fixtures?live=all vacío"
                      " (ningún partido en curso en este momento).")
        else:
            print("  API-Football: ningún partido iniciado aún — cuota preservada (0 llamadas).")

    # Construir resultados.json
    ahora_iso = ahora.strftime("%Y-%m-%dT%H:%M:%SZ")
    salida_dict = {
        "_descripcion": (
            f"Resultados Mundial {ano}. "
            "Actualizado automaticamente por motor/descargar_resultados.py."
        ),
        "ultima_actualizacion": ahora_iso,
        "marcadores":   resultado["marcadores"],
        "clasificados": resultado["clasificados"],
        "honor":        resultado["honor"],
        "premios":      premios,
    }

    guardar_resultados(salida_dict, salida)

    # Resumen
    n_final  = sum(1 for m in resultado["marcadores"] if m.get("estado") == "finalizado")
    n_vivo   = sum(1 for m in resultado["marcadores"] if m.get("estado") == "en_juego")
    n_pend   = sum(1 for m in resultado["marcadores"] if m.get("estado") == "pendiente")
    print(f"  Partidos de grupo procesados  : {stats['grupos_encontrados']}"
          f"  (sin ID en calendario: {stats['grupos_sin_id']})")
    print(f"  Marcadores: {n_final} finalizados, {n_vivo} en juego, {n_pend} pendientes")
    print(f"  Eliminatorias procesadas      : {stats['elim_procesadas']} partidos")
    print(f"  Clasificados por ronda        : "
          + ", ".join(f"{k}={len(v)}" for k, v in resultado["clasificados"].items()))
    print(f"  Honor  : {resultado['honor']}")
    print(f"  Premios: {premios}")
    if ano != "2026":
        print(f"  [NOTA] Modo validacion {ano}: match_ids de grupos no corresponden al calendario 2026.")
    print(f"  -> {salida}")


if __name__ == "__main__":
    main()
