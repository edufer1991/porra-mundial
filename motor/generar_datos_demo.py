"""
Genera datos sintéticos para el panel web (demo / Phase 4).
Produce standings, detalle, proximos y snapshots para las dos porras.
Ejecutar: python motor/generar_datos_demo.py
"""
import json, sys, random
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_AMIGOS  = ROOT / "web" / "data" / "amigos"
OUT_TRABAJO = ROOT / "web" / "data" / "trabajo"
OUT_SHARED  = ROOT / "web" / "data"

for d in [OUT_AMIGOS, OUT_TRABAJO, OUT_SHARED]:
    d.mkdir(parents=True, exist_ok=True)

# ── Datos compartidos ─────────────────────────────────────────────────────────

with open(ROOT / "datos" / "calendario.json", encoding="utf-8") as f:
    calendario = json.load(f)

partidos = calendario["partidos"]

# Resultados sintéticos: primeros 12 grupos finalizados, resto pendiente
# (simula que la fase de grupos está a medias)
resultados_demo = {
    "ultima_actualizacion": "2026-06-28T21:30:00Z",
    "en_juego": False,
    "marcadores": [],
    "clasificados": {
        "1/16": ["Mexico","South Africa","Germany","South Korea","Netherlands","Morocco",
                 "Brazil","Japan","France","Bosnia-Herzegovina","Ivory Coast","Senegal",
                 "England","Sweden","USA","Ecuador","Belgium","Saudi Arabia",
                 "Colombia","Croatia","Spain","Algeria","Canada","Turkey",
                 "Argentina","Uruguay","Portugal","Paraguay","Norway","Egypt",
                 "Scotland","Qatar"],
        "1/8": ["Germany","Netherlands","Brazil","France","Mexico","England",
                "Colombia","Spain","USA","Belgium","Argentina","Norway",
                "Canada","Portugal"],
        "1/4": ["Germany","Netherlands","Spain","Belgium","Brazil","England",
                "Argentina","Portugal"],
        "semis": ["Germany","Spain","Brazil","Argentina"],
        "final": ["Spain","Argentina"],
    },
    "honor": {
        "campeon": "Argentina",
        "subcampeon": "Spain",
        "tercero": "Germany",
        "cuarto": "Brazil",
    },
    "premios": {
        "goleador": "Lautaro Martinez",
        "mvp": "Lamine Yamal",
        "portero": "Emiliano Martinez",
    },
}

# marcadores para los primeros 36 partidos de grupos
scores = [
    (2,1),(0,0),(3,1),(1,2),(2,0),(1,1),(0,2),(1,0),(4,0),(2,2),
    (1,0),(0,1),(2,1),(1,3),(3,0),(0,0),(1,1),(2,0),(3,2),(1,0),
    (0,1),(2,1),(1,1),(0,0),(3,1),(2,0),(1,2),(0,3),(2,1),(1,0),
    (4,1),(0,2),(2,2),(1,1),(3,0),(0,1),
]
for i, p in enumerate(partidos[:36]):
    gl, gv = scores[i]
    resultados_demo["marcadores"].append({
        "match_id": p["id"],
        "estado": "finalizado",
        "goles_local": gl,
        "goles_visitante": gv,
    })
# partidos 37-72 pendientes
for p in partidos[36:72]:
    resultados_demo["marcadores"].append({"match_id": p["id"], "estado": "pendiente"})
# partidos eliminatorias pendientes
for p in partidos[72:]:
    resultados_demo["marcadores"].append({"match_id": p["id"], "estado": "pendiente"})

with open(OUT_SHARED / "resultados.json", "w", encoding="utf-8") as f:
    json.dump(resultados_demo, f, ensure_ascii=False, indent=2)
print("✓ resultados.json")

# Calendario: próximos 8 partidos (desde partido 37 en adelante)
proximos_cal = [p for p in partidos if p["id"] >= 37][:8]
with open(OUT_SHARED / "calendario.json", "w", encoding="utf-8") as f:
    json.dump({"torneo": calendario["torneo"], "partidos": partidos}, f, ensure_ascii=False, indent=2)
print("✓ calendario.json")


# ── Helpers ───────────────────────────────────────────────────────────────────

def signo(gl, gv):
    return "1" if gl > gv else ("X" if gl == gv else "2")

def pred_partido(gl, gv, off1=0, off2=0):
    """Predicción cercana al resultado real con pequeño offset."""
    return {
        "signo": signo(gl + off1, gv + off2),
        "goles_local": max(0, gl + off1),
        "goles_visitante": max(0, gv + off2),
    }


# ── Porra AMIGOS ─────────────────────────────────────────────────────────────
# 5 participantes con distintos niveles de acierto

AMIGOS = [
    {
        "nickname": "El_Profeta",
        "posicion": 1, "empate": False, "posicion_fase_previa": 2,
        "puntos_grupos": 58, "puntos_eliminatorias": 360, "puntos_honor": 140,
        "puntos_premios": 45, "puntos_fase_previa": 58, "puntos_fase_eliminatoria": 500,
        "puntos_total": 603, "advertencias_premios": [],
    },
    {
        "nickname": "LaQuiniela",
        "posicion": 2, "empate": False, "posicion_fase_previa": 1,
        "puntos_grupos": 72, "puntos_eliminatorias": 280, "puntos_honor": 90,
        "puntos_premios": 25, "puntos_fase_previa": 72, "puntos_fase_eliminatoria": 370,
        "puntos_total": 467, "advertencias_premios": [],
    },
    {
        "nickname": "Kante08",
        "posicion": 3, "empate": False, "posicion_fase_previa": 3,
        "puntos_grupos": 41, "puntos_eliminatorias": 200, "puntos_honor": 120,
        "puntos_premios": 20, "puntos_fase_previa": 41, "puntos_fase_eliminatoria": 320,
        "puntos_total": 381, "advertencias_premios": [],
    },
    {
        "nickname": "TodoAEspana",
        "posicion": 4, "empate": False, "posicion_fase_previa": 4,
        "puntos_grupos": 35, "puntos_eliminatorias": 160, "puntos_honor": 50,
        "puntos_premios": 0, "puntos_fase_previa": 35, "puntos_fase_eliminatoria": 210,
        "puntos_total": 245, "advertencias_premios": [{"premio": "goleador", "prediccion": "Morata", "real": "Lautaro Martinez"}],
    },
    {
        "nickname": "LaMaquina",
        "posicion": 5, "empate": False, "posicion_fase_previa": 5,
        "puntos_grupos": 28, "puntos_eliminatorias": 120, "puntos_honor": 30,
        "puntos_premios": 0, "puntos_fase_previa": 28, "puntos_fase_eliminatoria": 150,
        "puntos_total": 178, "advertencias_premios": [],
    },
]

standings_amigos = {
    "porra": "amigos",
    "ultima_actualizacion": resultados_demo["ultima_actualizacion"],
    "clasificacion": AMIGOS,
}
with open(OUT_AMIGOS / "standings.json", "w", encoding="utf-8") as f:
    json.dump(standings_amigos, f, ensure_ascii=False, indent=2)
print("✓ amigos/standings.json")

# Detalle por participante (Mi Porra)
def mk_grupos_detalle(nick, scores):
    """Genera detalle de grupos: predicciones vs resultados para los primeros 36 partidos."""
    rows = []
    for i, p in enumerate(partidos[:36]):
        gl_r, gv_r = scores[i]
        offsets = {
            "El_Profeta":    [(0,0),(0,1),(0,0),(1,0),(0,0),(0,0)],
            "LaQuiniela":    [(0,0),(0,0),(1,0),(0,1),(0,0),(1,1)],
            "Kante08":       [(1,0),(0,0),(0,1),(0,0),(1,0),(0,1)],
            "TodoAEspana":   [(1,1),(0,1),(1,0),(1,1),(0,0),(1,0)],
            "LaMaquina":     [(1,1),(1,1),(0,1),(1,0),(1,1),(0,1)],
        }
        off1, off2 = offsets.get(nick, [(0,0)]*(i%6+1))[i%6]
        pred = pred_partido(gl_r, gv_r, off1, off2)
        acierto_signo = pred["signo"] == signo(gl_r, gv_r)
        acierto_local = pred["goles_local"] == gl_r
        acierto_visit = pred["goles_visitante"] == gv_r
        pts = (3 if acierto_signo else 0) + (gl_r+1 if acierto_local else 0) + (gv_r+1 if acierto_visit else 0)
        rows.append({
            "match_id": p["id"], "grupo": p["grupo"], "jornada": p["jornada"],
            "local": p["local"], "visitante": p["visitante"],
            "resultado": {"goles_local": gl_r, "goles_visitante": gv_r},
            "prediccion": pred,
            "puntos": pts,
            "acierto_signo": acierto_signo,
            "acierto_local": acierto_local,
            "acierto_visitante": acierto_visit,
        })
    # partidos pendientes
    for p in partidos[36:72]:
        pred2 = {"signo": "1", "goles_local": 1, "goles_visitante": 0}
        rows.append({
            "match_id": p["id"], "grupo": p.get("grupo",""), "jornada": p.get("jornada","J2"),
            "local": p["local"], "visitante": p["visitante"],
            "resultado": None, "prediccion": pred2,
            "puntos": None, "acierto_signo": None,
            "acierto_local": None, "acierto_visitante": None,
        })
    return rows

HONOR_PRED = {
    "El_Profeta":  {"campeon":"Argentina","subcampeon":"Spain","tercero":"Germany","cuarto":"Brazil"},
    "LaQuiniela":  {"campeon":"Argentina","subcampeon":"France","tercero":"Spain","cuarto":"Germany"},
    "Kante08":     {"campeon":"Spain","subcampeon":"Argentina","tercero":"Brazil","cuarto":"Germany"},
    "TodoAEspana": {"campeon":"Spain","subcampeon":"France","tercero":"Germany","cuarto":"Brazil"},
    "LaMaquina":   {"campeon":"Brazil","subcampeon":"France","tercero":"Germany","cuarto":"Spain"},
}
CLASIF_PRED = {
    "El_Profeta":  {"1/16":["Argentina","Spain","Germany","Brazil","France","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],
                   "1/8":["Argentina","Spain","Germany","Brazil","France","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa"],
                   "1/4":["Argentina","Spain","Germany","Brazil","France","Netherlands","England","Portugal"],
                   "semis":["Argentina","Spain","Germany","Brazil"],
                   "final":["Argentina","Spain"]},
    "LaQuiniela":  {"1/16":["Argentina","Spain","Germany","Brazil","France","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],
                   "1/8":["Argentina","France","Germany","Brazil","Netherlands","England","Portugal","Spain","Colombia","USA","Belgium","Japan","Morocco","South Africa","Ivory Coast","Mexico"],
                   "1/4":["Argentina","France","Germany","Brazil","Netherlands","England","Portugal","Spain"],
                   "semis":["Argentina","Germany","France","Brazil"],
                   "final":["Argentina","France"]},
    "Kante08":     {"1/16":["Spain","Argentina","Germany","Brazil","France","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],
                   "1/8":["Spain","Argentina","Germany","Brazil","France","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium"],
                   "1/4":["Spain","Argentina","Germany","Brazil","France","Netherlands","England","Portugal"],
                   "semis":["Spain","Argentina","Germany","Brazil"],
                   "final":["Spain","Argentina"]},
    "TodoAEspana": {"1/16":["Spain","France","Germany","Brazil","Argentina","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],
                   "1/8":["Spain","France","Germany","Brazil","Argentina","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium"],
                   "1/4":["Spain","France","Germany","Brazil","Netherlands","England"],
                   "semis":["Spain","France","Germany","Brazil"],
                   "final":["Spain","France"]},
    "LaMaquina":   {"1/16":["Brazil","France","Germany","Spain","Argentina","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],
                   "1/8":["Brazil","France","Germany","Spain","Argentina","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium"],
                   "1/4":["Brazil","France","Germany","Spain","Netherlands","England"],
                   "semis":["Brazil","France","Germany","Spain"],
                   "final":["Brazil","France"]},
}
PREMIOS_PRED = {
    "El_Profeta":  {"goleador":"Lautaro Martinez","mvp":"Lamine Yamal","portero":"Emiliano Martinez"},
    "LaQuiniela":  {"goleador":"Lautaro Martinez","mvp":"Mbappe","portero":"Unai Simon"},
    "Kante08":     {"goleador":"Vinicius Jr","mvp":"Lamine Yamal","portero":"Emiliano Martinez"},
    "TodoAEspana": {"goleador":"Morata","mvp":None,"portero":None},
    "LaMaquina":   {"goleador":"Vinicius Jr","mvp":"Mbappe","portero":None},
}

detalle_amigos = {}
for part in AMIGOS:
    nick = part["nickname"]
    detalle_amigos[nick] = {
        "nickname": nick,
        "grupos": mk_grupos_detalle(nick, scores),
        "clasificados": CLASIF_PRED[nick],
        "honor": HONOR_PRED[nick],
        "premios": PREMIOS_PRED[nick],
    }

with open(OUT_AMIGOS / "detalle.json", "w", encoding="utf-8") as f:
    json.dump(detalle_amigos, f, ensure_ascii=False, indent=2)
print("✓ amigos/detalle.json")

# Próximos partidos con predicciones (partidos 37-44)
proximos_amigos = []
for p in partidos[36:44]:
    preds = []
    for part in AMIGOS:
        nick = part["nickname"]
        gl = random.randint(0, 3); gv = random.randint(0, 3)
        pred = {"signo": signo(gl, gv), "goles_local": gl, "goles_visitante": gv}
        preds.append({"nickname": nick, "prediccion": pred})
    proximos_amigos.append({
        "match_id": p["id"],
        "fecha_hora_utc": p["fecha_hora_utc"],
        "fase": p["fase"],
        "grupo": p.get("grupo",""),
        "jornada": p.get("jornada",""),
        "local": p["local"],
        "visitante": p["visitante"],
        "predicciones": preds,
    })

with open(OUT_AMIGOS / "proximos.json", "w", encoding="utf-8") as f:
    json.dump(proximos_amigos, f, ensure_ascii=False, indent=2)
print("✓ amigos/proximos.json")

# Snapshots (evolución temporal — 6 puntos históricos)
def mk_snapshot(fecha, clasif_data):
    return {"fecha": fecha, "clasificacion": clasif_data}

snap_fechas = [
    "2026-06-14T22:00:00Z",  # tras J1 parcial
    "2026-06-19T22:00:00Z",  # tras J1 completo
    "2026-06-24T22:00:00Z",  # tras J2 parcial
    "2026-06-29T22:00:00Z",  # tras J2 completo + J3 inicio
    "2026-07-05T22:00:00Z",  # tras J3 completo
    "2026-06-28T21:30:00Z",  # actual (durante elim)
]
# simulamos posiciones cambiando orden con el tiempo
snap_evoluciones = [
    # fecha1: LaQuiniela lidera en grupos
    [("LaQuiniela",1),("El_Profeta",2),("Kante08",3),("TodoAEspana",4),("LaMaquina",5)],
    [("LaQuiniela",1),("El_Profeta",2),("Kante08",3),("TodoAEspana",4),("LaMaquina",5)],
    [("El_Profeta",1),("LaQuiniela",2),("Kante08",3),("LaMaquina",4),("TodoAEspana",5)],
    [("El_Profeta",1),("Kante08",2),("LaQuiniela",3),("TodoAEspana",4),("LaMaquina",5)],
    [("El_Profeta",1),("LaQuiniela",2),("Kante08",3),("TodoAEspana",4),("LaMaquina",5)],
    [("El_Profeta",1),("LaQuiniela",2),("Kante08",3),("TodoAEspana",4),("LaMaquina",5)],
]
snap_pts = [
    {"LaQuiniela":45,"El_Profeta":32,"Kante08":28,"TodoAEspana":22,"LaMaquina":18},
    {"LaQuiniela":72,"El_Profeta":58,"Kante08":41,"TodoAEspana":35,"LaMaquina":28},
    {"El_Profeta":178,"LaQuiniela":162,"Kante08":141,"LaMaquina":118,"TodoAEspana":105},
    {"El_Profeta":318,"Kante08":261,"LaQuiniela":252,"TodoAEspana":185,"LaMaquina":158},
    {"El_Profeta":418,"LaQuiniela":342,"Kante08":321,"TodoAEspana":215,"LaMaquina":178},
    {"El_Profeta":603,"LaQuiniela":467,"Kante08":381,"TodoAEspana":245,"LaMaquina":178},
]

snapshots_amigos = {
    "porra": "amigos",
    "nicknames": [p["nickname"] for p in AMIGOS],
    "snapshots": [],
}
for i, fecha in enumerate(snap_fechas):
    clas = []
    for nick, pos in snap_evoluciones[i]:
        clas.append({"nickname": nick, "posicion": pos, "puntos_total": snap_pts[i][nick]})
    snapshots_amigos["snapshots"].append({"fecha": fecha, "clasificacion": clas})

with open(OUT_AMIGOS / "snapshots.json", "w", encoding="utf-8") as f:
    json.dump(snapshots_amigos, f, ensure_ascii=False, indent=2)
print("✓ amigos/snapshots.json")


# ── Porra TRABAJO ─────────────────────────────────────────────────────────────

TRABAJO = [
    {
        "nickname": "Txema_Boss",
        "posicion": 1, "empate": False, "posicion_fase_previa": 1,
        "puntos_grupos": 65, "puntos_eliminatorias": 320, "puntos_honor": 140,
        "puntos_premios": 45, "puntos_fase_previa": 65, "puntos_fase_eliminatoria": 460,
        "puntos_total": 570, "advertencias_premios": [],
    },
    {
        "nickname": "AnalisisProfundo",
        "posicion": 2, "empate": False, "posicion_fase_previa": 3,
        "puntos_grupos": 44, "puntos_eliminatorias": 310, "puntos_honor": 110,
        "puntos_premios": 25, "puntos_fase_previa": 44, "puntos_fase_eliminatoria": 420,
        "puntos_total": 489, "advertencias_premios": [],
    },
    {
        "nickname": "Proba_Stats",
        "posicion": 3, "empate": False, "posicion_fase_previa": 2,
        "puntos_grupos": 55, "puntos_eliminatorias": 220, "puntos_honor": 90,
        "puntos_premios": 20, "puntos_fase_previa": 55, "puntos_fase_eliminatoria": 310,
        "puntos_total": 385, "advertencias_premios": [],
    },
    {
        "nickname": "Aleatoria99",
        "posicion": 4, "empate": True, "posicion_fase_previa": 4,
        "puntos_grupos": 31, "puntos_eliminatorias": 130, "puntos_honor": 50,
        "puntos_premios": 0, "puntos_fase_previa": 31, "puntos_fase_eliminatoria": 180,
        "puntos_total": 211, "advertencias_premios": [],
    },
    {
        "nickname": "Iker_Jr",
        "posicion": 4, "empate": True, "posicion_fase_previa": 5,
        "puntos_grupos": 29, "puntos_eliminatorias": 130, "puntos_honor": 50,
        "puntos_premios": 0, "puntos_fase_previa": 29, "puntos_fase_eliminatoria": 180,
        "puntos_total": 211, "advertencias_premios": [],
    },
    {
        "nickname": "PorriPorri",
        "posicion": 6, "empate": False, "posicion_fase_previa": 6,
        "puntos_grupos": 18, "puntos_eliminatorias": 80, "puntos_honor": 20,
        "puntos_premios": 0, "puntos_fase_previa": 18, "puntos_fase_eliminatoria": 100,
        "puntos_total": 118, "advertencias_premios": [],
    },
]

standings_trabajo = {
    "porra": "trabajo",
    "ultima_actualizacion": resultados_demo["ultima_actualizacion"],
    "clasificacion": TRABAJO,
}
with open(OUT_TRABAJO / "standings.json", "w", encoding="utf-8") as f:
    json.dump(standings_trabajo, f, ensure_ascii=False, indent=2)
print("✓ trabajo/standings.json")

# proximos trabajo
proximos_trabajo = []
for p in partidos[36:44]:
    preds = []
    for part in TRABAJO:
        nick = part["nickname"]
        gl = random.randint(0, 3); gv = random.randint(0, 3)
        pred = {"signo": signo(gl, gv), "goles_local": gl, "goles_visitante": gv}
        preds.append({"nickname": nick, "prediccion": pred})
    proximos_trabajo.append({
        "match_id": p["id"],
        "fecha_hora_utc": p["fecha_hora_utc"],
        "fase": p["fase"],
        "grupo": p.get("grupo",""),
        "jornada": p.get("jornada",""),
        "local": p["local"],
        "visitante": p["visitante"],
        "predicciones": preds,
    })

with open(OUT_TRABAJO / "proximos.json", "w", encoding="utf-8") as f:
    json.dump(proximos_trabajo, f, ensure_ascii=False, indent=2)
print("✓ trabajo/proximos.json")

# snapshots trabajo
snapshots_trabajo = {
    "porra": "trabajo",
    "nicknames": [p["nickname"] for p in TRABAJO],
    "snapshots": [],
}
snap_pts_t = [
    {"Txema_Boss":50,"Proba_Stats":42,"AnalisisProfundo":35,"Aleatoria99":20,"Iker_Jr":18,"PorriPorri":12},
    {"Txema_Boss":65,"Proba_Stats":55,"AnalisisProfundo":44,"Aleatoria99":31,"Iker_Jr":29,"PorriPorri":18},
    {"Txema_Boss":195,"AnalisisProfundo":174,"Proba_Stats":165,"Aleatoria99":111,"Iker_Jr":109,"PorriPorri":68},
    {"Txema_Boss":315,"AnalisisProfundo":284,"Proba_Stats":265,"Aleatoria99":171,"Iker_Jr":169,"PorriPorri":88},
    {"Txema_Boss":415,"AnalisisProfundo":374,"Proba_Stats":305,"Aleatoria99":201,"Iker_Jr":201,"PorriPorri":108},
    {"Txema_Boss":570,"AnalisisProfundo":489,"Proba_Stats":385,"Aleatoria99":211,"Iker_Jr":211,"PorriPorri":118},
]
snap_ord_t = [
    [("Txema_Boss",1),("Proba_Stats",2),("AnalisisProfundo",3),("Aleatoria99",4),("Iker_Jr",5),("PorriPorri",6)],
    [("Txema_Boss",1),("Proba_Stats",2),("AnalisisProfundo",3),("Aleatoria99",4),("Iker_Jr",5),("PorriPorri",6)],
    [("Txema_Boss",1),("AnalisisProfundo",2),("Proba_Stats",3),("Aleatoria99",4),("Iker_Jr",5),("PorriPorri",6)],
    [("Txema_Boss",1),("AnalisisProfundo",2),("Proba_Stats",3),("Aleatoria99",4),("Iker_Jr",5),("PorriPorri",6)],
    [("Txema_Boss",1),("AnalisisProfundo",2),("Proba_Stats",3),("Aleatoria99",4),("Iker_Jr",4),("PorriPorri",6)],
    [("Txema_Boss",1),("AnalisisProfundo",2),("Proba_Stats",3),("Aleatoria99",4),("Iker_Jr",4),("PorriPorri",6)],
]
for i, fecha in enumerate(snap_fechas):
    clas = []
    for nick, pos in snap_ord_t[i]:
        clas.append({"nickname": nick, "posicion": pos, "puntos_total": snap_pts_t[i][nick]})
    snapshots_trabajo["snapshots"].append({"fecha": fecha, "clasificacion": clas})

with open(OUT_TRABAJO / "snapshots.json", "w", encoding="utf-8") as f:
    json.dump(snapshots_trabajo, f, ensure_ascii=False, indent=2)
print("✓ trabajo/snapshots.json")

# detalle trabajo (simplificado — solo honor/premios/clasificados, grupos ligero)
detalle_trabajo = {}
t_honor = {
    "Txema_Boss":       {"campeon":"Argentina","subcampeon":"Spain","tercero":"Germany","cuarto":"Brazil"},
    "AnalisisProfundo": {"campeon":"Argentina","subcampeon":"Germany","tercero":"Spain","cuarto":"Brazil"},
    "Proba_Stats":      {"campeon":"Spain","subcampeon":"Argentina","tercero":"Germany","cuarto":"France"},
    "Aleatoria99":      {"campeon":"Argentina","subcampeon":"France","tercero":"Brazil","cuarto":"Germany"},
    "Iker_Jr":          {"campeon":"Spain","subcampeon":"France","tercero":"Brazil","cuarto":"Germany"},
    "PorriPorri":       {"campeon":"Brazil","subcampeon":"Germany","tercero":"France","cuarto":"Spain"},
}
t_premios = {
    "Txema_Boss":       {"goleador":"Lautaro Martinez","mvp":"Lamine Yamal","portero":"Emiliano Martinez"},
    "AnalisisProfundo": {"goleador":"Lautaro Martinez","mvp":"Vinicius Jr","portero":"Emiliano Martinez"},
    "Proba_Stats":      {"goleador":"Mbappe","mvp":"Lamine Yamal","portero":"Emiliano Martinez"},
    "Aleatoria99":      {"goleador":"Haaland","mvp":None,"portero":None},
    "Iker_Jr":          {"goleador":"Mbappe","mvp":None,"portero":None},
    "PorriPorri":       {"goleador":None,"mvp":None,"portero":None},
}
t_clasif = {
    "Txema_Boss":       {"1/16":["Argentina","Spain","Germany","Brazil","France","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],"1/8":["Argentina","Spain","Germany","Brazil","France","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa"],"1/4":["Argentina","Spain","Germany","Brazil","France","Netherlands","England","Portugal"],"semis":["Argentina","Spain","Germany","Brazil"],"final":["Argentina","Spain"]},
    "AnalisisProfundo": {"1/16":["Argentina","Germany","France","Brazil","Spain","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],"1/8":["Argentina","Germany","France","Brazil","Spain","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium"],"1/4":["Argentina","Germany","France","Brazil","Spain","Netherlands"],"semis":["Argentina","Germany","Spain","Brazil"],"final":["Argentina","Germany"]},
    "Proba_Stats":      {"1/16":["Spain","Argentina","Germany","France","Brazil","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],"1/8":["Spain","Argentina","Germany","France","Brazil","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium"],"1/4":["Spain","Argentina","Germany","France","Brazil","Netherlands"],"semis":["Spain","Argentina","Germany","France"],"final":["Spain","Argentina"]},
    "Aleatoria99":      {"1/16":["Argentina","France","Germany","Brazil","Spain","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],"1/8":["Argentina","France","Germany","Brazil","Netherlands","England"],"1/4":["Argentina","France","Germany","Brazil"],"semis":["Argentina","France"],"final":["Argentina","France"]},
    "Iker_Jr":          {"1/16":["Spain","France","Germany","Brazil","Argentina","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],"1/8":["Spain","France","Germany","Brazil","Netherlands","England"],"1/4":["Spain","France","Germany","Brazil"],"semis":["Spain","France"],"final":["Spain","France"]},
    "PorriPorri":       {"1/16":["Brazil","France","Germany","Spain","Argentina","Netherlands","England","Portugal","Mexico","Colombia","USA","Belgium","Croatia","Japan","Morocco","South Africa","Ivory Coast","Senegal","Norway","Sweden","Canada","Turkey","South Korea","Ecuador","Algeria","Qatar","Saudi Arabia","Switzerland","Uruguay","Paraguay","Uzbekistan","Austria"],"1/8":["Brazil","France","Germany","Spain"],"1/4":["Brazil","France"],"semis":["Brazil","France"],"final":["Brazil","France"]},
}
for part in TRABAJO:
    nick = part["nickname"]
    detalle_trabajo[nick] = {
        "nickname": nick,
        "grupos": mk_grupos_detalle(nick if nick in ["El_Profeta","LaQuiniela","Kante08","TodoAEspana","LaMaquina"] else "Kante08", scores),
        "clasificados": t_clasif[nick],
        "honor": t_honor[nick],
        "premios": t_premios[nick],
    }

with open(OUT_TRABAJO / "detalle.json", "w", encoding="utf-8") as f:
    json.dump(detalle_trabajo, f, ensure_ascii=False, indent=2)
print("✓ trabajo/detalle.json")

print("\nTodos los datos generados en web/data/")
