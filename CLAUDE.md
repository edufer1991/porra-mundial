# Especificación técnica — Sistema de Porra Mundial 2026

> Documento de construcción. Pensado para entregarlo a Claude Code como brief del proyecto.
> Puedes renombrarlo a `CLAUDE.md` en la raíz del repo para que Claude Code lo lea automáticamente.

---

## 1. Objetivo

Gestionar **dos porras en paralelo** (amigos y trabajo) del Mundial 2026 a partir de una plantilla de Excel ya existente y un conjunto de reglas definido. El resultado es un **panel web público, gratuito y mobile-first** donde cualquiera consulta la clasificación, que se **actualiza sola** durante el torneo (sensación casi en directo) sin intervención manual salvo tres premios finales.

## 2. Decisiones cerradas

- Coste objetivo: **0 €**.
- Entrada de pronósticos: **todo en el Excel** (`PORRA_MUNDIAL_2026_v2.xlsx`). Incluye una pestaña nueva **`Premios`** para goleador / MVP / portero. (Se descartó el formulario complementario.)
- Actualización: automática, **captura cada 5 min** en ventanas de partido + **refresco del panel cada 30-60 s**.
- Alojamiento: **sitio estático en GitHub Pages**; cómputo en **GitHub Actions**.
- Dos porras separadas con **contraseña simple por porra** (protección ligera del lado cliente).
- Premio Seleccionador y votación de mejor nickname: **fuera de alcance** (posibles módulos futuros).

## 3. Arquitectura (base)

```
[openfootball JSON] ─┐
[API-Football]      ─┴─→ [GitHub Actions cada 5'] → motor Python →
   → standings_amigos.json / standings_trabajo.json + snapshots evolución
   → render sitio estático → commit → [GitHub Pages]
                                          ↓
                         Panel web (refresco 30-60s, marcador en vivo)
```

- Durante el Mundial el sistema corre solo. No consume modelo en ejecución.
- Cron de GitHub Actions: mínimo 5 min y puede sufrir retraso bajo carga; aceptable para este uso.
- Sondeo **adaptativo**: solo llama a la API cuando hay partido en curso (según calendario); ajusta el ritmo para no superar el límite gratuito de **100 peticiones/día** de API-Football. Una sola llamada (`fixtures?live=all`) trae todos los partidos en juego a la vez.

## 4. Estructura del repositorio

```
/datos/
  /pronosticos/amigos/*.json        # un participante por archivo
  /pronosticos/trabajo/*.json
  calendario.json                   # 104 partidos: id, fase, equipos, fecha
  equivalencias_equipos.json        # mapa nombre ES ↔ nombre API (48 selecciones)
  resultados.json                   # autoactualizado
  premios.json                      # goleador/MVP/portero (manual al final)
  /snapshots/                       # histórico de clasificación (gráfico evolución)
/config/
  reglas.json                       # TODOS los puntos, editable sin tocar código
/motor/
  parsear_excel.py                  # lee hoja Pool de cada Excel devuelto
  descargar_resultados.py           # openfootball + API-Football
  normalizar_nombres.py
  puntuar.py                        # aplica reglas.json
  generar_sitio.py                  # render del panel estático
/web/                               # salida estática publicada por Pages
.github/workflows/actualizar.yml    # cron + pipeline
```

## 5. Reglas de puntuación (exactas)

**Fase de grupos** (por cada uno de los 72 partidos; los tres conceptos son independientes):
- **+3** si el signo (1 / X / 2) coincide con el real.
- **+ (goles_local_reales + 1)** si aciertas los goles del local.
- **+ (goles_visitante_reales + 1)** si aciertas los goles del visitante.
  (Corrección aplicada: el visitante usa sus propios goles +1, simétrico al local.)

**Eliminatorias** (por selección que avanza; sin puntos por marcador):
- Por cada selección que pronosticaste en una ronda y que realmente llegó a ella:
  - Clasificada a 1/16: **+5** · 1/8: **+10** · 1/4: **+15** · semifinales: **+20** · final: **+30**

**Posiciones de honor:**
- Campeón **+50** · Subcampeón **+40** · 3º **+30** · 4º **+20**

**Premios de jugador (nuevos):**
- Máximo goleador **+25** · MVP **+25** · Portero menos goleado **+20**

**Sub-clasificación de fase previa:** suma únicamente de los puntos de fase de grupos (para el premio del 10 % al 1º de la fase previa).

Todos los valores viven en `config/reglas.json` y deben poder ajustarse sin tocar código.

## 6. Contrato de parseo de la hoja `Pool`

La hoja `Pool` del Excel exporta todo en su **columna C**, fila a fila (verificado sobre la plantilla). El parser lee un Excel YA RELLENADO:

| Filas (col C) | Contenido |
|---|---|
| C5 | Nickname del participante |
| C6:C77 | 72 partidos de grupos. Orden: J1 = C6:C29, J2 = C30:C53, J3 = C54:C77. Cada celda codifica signo + marcador. |
| C80:C127 | Clasificación de grupos pronosticada (12 grupos × 4 posiciones) |
| C130:C161 | 32 selecciones pronosticadas en 1/16 |
| C182:C197 | 16 selecciones pronosticadas en 1/8 |
| C210:C217 | 8 selecciones pronosticadas en 1/4 |
| C226:C229 | 4 semifinalistas pronosticados |
| C236:C237 | Equipos del partido 3º-4º |
| C240:C241 | Finalistas pronosticados |
| C250 / C251 / C252 | Campeón / Subcampeón / 3º pronosticados |

- **4º puesto pronosticado**: derivar = el semifinalista que no es finalista ni 3º.
- **Premios de jugador**: NO salen de la hoja Pool. Se leen directamente de la pestaña **`Premios`**: `Premios!B4` = máximo goleador, `Premios!B5` = MVP, `Premios!B6` = portero menos goleado (texto libre; el nombre del jugador). Validar/normalizar nombres (ver pitfall de matching).
- **Primera tarea obligatoria**: rellenar UN Excel de muestra y volcar `Pool!C` para fijar el formato exacto de codificación de cada celda (el formato del marcador de grupos y si los equipos salen como nombre o código). En la plantilla en blanco aparecen marcadores de posición; en un archivo relleno se resuelven a nombres de selección en español.

## 7. Fuentes de datos

- **openfootball/worldcup** (JSON en GitHub, sin clave): calendario y resultados. Fuente principal.
- **API-Football** (plan gratuito, 100 req/día): respaldo de resultados y **tabla de goleadores** en vivo. Datos en vivo cada ~15 s; recomendado 1 llamada/min solo con partido en curso.
- **No reimplementar las reglas de desempate de la FIFA ni el cálculo de mejores terceros reales**: leer directamente de la API qué selecciones avanzaron.
- **Tabla de equivalencias** de las 48 selecciones (nombre español del Excel ↔ nombre de la API), p. ej. "Estados Unidos" ↔ "United States". Construirla y validarla en la fase inicial; un fallo aquí rompe las comparaciones.

## 8. Determinación de los tres premios finales

- **Máximo goleador**: tabla de goleadores de API-Football durante el torneo (mostrar ranking en vivo); **confirmar el ganador a mano** al cierre.
- **MVP** y **Portero menos goleado**: premios subjetivos de la FIFA tras la final; **entrada manual** una sola vez en `datos/premios.json`.

## 9. Las dos porras y la contraseña

- Cada pronóstico lleva etiqueta de porra (`amigos` / `trabajo`). El motor calcula resultados reales una vez y los aplica a ambos conjuntos → **dos clasificaciones independientes**.
- **Contraseña por porra**, del lado cliente: los datos de cada porra van en archivos separados que solo se cargan tras introducir la contraseña correcta. Bloquea el fisgoneo casual entre porras; no es blindaje criptográfico (suficiente para este uso).

## 10. Panel web

- **Mobile-first**, una vista por porra. Refresco automático cada **30-60 s** releyendo el JSON publicado (la sensación de directo la da el frontend, desacoplado del coste de la API).
- **Indicador "en directo"** y marcador en juego durante los partidos.
- Vistas:
  1. **Clasificación general** (con sub-clasificación de fase previa).
  2. **Mi porra**: el usuario busca su nickname y ve aciertos, fallos y de dónde sale cada punto.
  3. **Evolución**: gráfico de posiciones a lo largo del torneo (a partir de `/datos/snapshots/`).
  4. **Próximos partidos**: con los pronósticos de todos para esos partidos.
  5. **Reglas**: resumen claro del sistema de puntuación (grupos, eliminatorias, honor, premios de jugador) para que los participantes lo consulten en cualquier momento.

## 11. Recogida de pronósticos

- **Excel** (`PORRA_MUNDIAL_2026_v2.xlsx`): cada participante rellena su copia y la devuelve antes del **11 de junio, 21:00 (hora peninsular)**. El nickname está dentro del archivo (Pool!C5).
- Los **tres premios de jugador** (goleador, MVP, portero) se rellenan en la pestaña **`Premios`** del mismo Excel (texto libre con el nombre del jugador). No hay formulario aparte.
- Aviso: la pestaña `Premios` NO está enlazada al indicador "PORRA COMPLETA" de la hoja WORLDCUP (se dejó así para no romper esa lógica). El parser debe **marcar como incompletos** los archivos que devuelvan esos tres campos vacíos, y conviene recordarlo en el mensaje de envío a los participantes.

## 12. Fases de construcción y modelo recomendado

0. **Andamiaje**: repo, estructura, `calendario.json`, tabla de equivalencias — *Sonnet 4.6*.
1. **Parser del Excel** (decodificar `Pool!C`, derivar 4º) — *Opus 4.8* para la lógica fina, luego *Sonnet*.
2. **Motor de puntuación** con las reglas — *Opus 4.8* (parte crítica de corrección).
3. **Descarga de resultados** + normalización de nombres + entrada de premios — *Sonnet 4.6*.
4. **Panel web**: vistas, contraseña, gráfico, diseño móvil — *Sonnet 4.6*. **Antes de empezar, instalar el plugin oficial `frontend-design`** en Claude Code (`/plugin` → marketplace de Anthropic → frontend-design) para un diseño vistoso y no genérico. Dirección estética sugerida: tono deportivo/festivo de Mundial, color dominante potente, clasificación protagonista con micro-animaciones al cambiar de puesto. (Claude Design opcional para tantear el aspecto en lienzo.)
5. **Automatización** con GitHub Actions + publicación en Pages — *Sonnet 4.6*.
6. **Pruebas con resultados simulados** antes del 11 de junio.

(El modelo se cambia manualmente en el selector de Claude Code; conviene reservar Opus para las fases 1-2 y usar Sonnet en el resto para estirar la cuota de Pro.)

## 13. Qué debe aportar el usuario

- Cuenta de **GitHub** (gratuita) — crearla en el navegador.
- Opcional: clave de **API-Football** (registro gratuito) para el respaldo y la tabla de goleadores; openfootball funciona sin clave.
- Las **dos contraseñas** de las porras.
- Los **Excels rellenados** de los participantes (incluida la pestaña `Premios`), antes del 11 de junio.

## 14. Riesgos y decisiones abiertas (resolver antes/durante la build)

1. **Privacidad en repo público.** Pages y los minutos ilimitados de Actions son gratis solo en repos públicos; ahí los pronósticos quedarían a la vista de cualquiera. **Decisión de diseño**: las predicciones en crudo NO se publican en el repo público. Se procesan de forma privada (p. ej. repo privado o almacén aparte) y al sitio público solo se sube la **clasificación calculada** (que es información que todos pueden ver). La contraseña del sitio no protege los archivos del repo.
2. **Puntuación acumulativa de eliminatorias — CONFIRMADO.** Una selección acertada hasta la final puntúa en CADA ronda alcanzada: 5 (1/16) + 10 (1/8) + 15 (1/4) + 20 (semis) + 30 (final) = **80 pts máx por selección**. Implementación: las listas de `clasificados[ronda]` del pronóstico se cruzan con `clasificados[ronda]` del resultado real, ronda a ronda, y se suman los puntos por intersección.
3. **Matching de nombres de jugador.** Goleador/MVP/portero son texto libre; hay que normalizar variantes ("Mbappé"/"Mbappe"/"Kylian Mbappé") contra la API y contra el ganador oficial. Construir tabla de alias y revisar a mano al cierre.
4. **Empates en la clasificación de la porra — CONFIRMADO.** Desempate por **puntos de la fase eliminatoria** (rondas de eliminatorias + cuadro de honor; **sin** puntos de grupos ni premios de jugador). Si persiste el empate tras este criterio → **reparto** (los empatados comparten posición y se reparten el premio proporcional). La sub-clasificación de fase previa (solo grupos) es informativa y sirve para el premio del 10 % al 1º de grupos.
5. **Cobertura de la API para el formato 2026.** Verificar que la API expone correctamente qué selecciones avanzan (incluidos los 8 mejores terceros) para no tener que reimplementar reglas FIFA. Probar pronto.
6. **Varias porras por persona y nicknames.** Las reglas permiten múltiples participaciones; el sistema debe admitir varias entradas por persona y nicknames únicos por porra (colisión de nickname rompe el cruce).
7. **Premios subjetivos al final.** MVP y portero se introducen tras la final: la clasificación no es "definitiva" hasta ese momento.
8. **Zonas horarias.** La detección de "ventana de partido en vivo" y el cierre (21:00 peninsular) deben usar la TZ correcta (CEST en verano).
9. **Días con muchos partidos vs 100 peticiones/día.** En jornadas cargadas de grupos el sondeo se ensancha por encima de 5 min para no agotar el cupo; la frescura real esos días será algo menor.

## 15. Notas de implementación (añadidas durante la build)

### Fase 2 — Motor de puntuación

- **Reglas vivas en `config/reglas.json`** (acierto_signo, bonos de goles, puntos por ronda, honor, premios, desempate). Cualquier ajuste se hace en ese fichero sin tocar código.
- **Métricas por participante**: `puntos_grupos`, `puntos_eliminatorias`, `puntos_honor`, `puntos_premios`, `puntos_fase_previa` (= grupos), `puntos_fase_eliminatoria` (= eliminatorias + honor), `puntos_total`.
- **Ordenación de clasificación**: por `puntos_total` desc; desempate por `puntos_fase_eliminatoria` desc; si persiste → `empate: true` y misma `posicion` (reparto).
- **Sub-clasificación de fase previa**: ordenación adicional por `puntos_fase_previa` desc (para el premio del 1º de grupos).
- **Matching de nombres de jugador**: normalización sin tildes ni mayúsculas + tabla de alias (campo `alias_jugadores` opcional). Los premios sin coincidencia se devuelven en `advertencias_premios` para revisión manual antes del cierre.

### Esquema esperado de `datos/resultados.json`

```json
{
  "ultima_actualizacion": "ISO8601",
  "marcadores": [
    {"match_id": 1, "estado": "finalizado|en_juego|pendiente", "goles_local": 2, "goles_visitante": 1}
  ],
  "clasificados": {
    "1/16": ["Mexico", "..."],
    "1/8":  ["..."],
    "1/4":  ["..."],
    "semis":["..."],
    "final":["..."]
  },
  "honor":   {"campeon": "...", "subcampeon": "...", "tercero": "...", "cuarto": "..."},
  "premios": {"goleador": "...", "mvp": "...", "portero": "..."}
}
```

Nombres canónicos = `nombre_openfootball` de `equivalencias_equipos.json`.

### Fase 1 — Parser del Excel: estrategia de matching de partidos

El parser de `motor/parsear_excel.py` **NO debe identificar cada predicción de grupo por posición absoluta** dentro de Pool!C6:C77. En su lugar debe:

1. Leer de la hoja Pool la columna **B** (equipo local) y columna **A** (jornada: J1/J2/J3) para cada fila del bloque de grupos.
2. Cruzar ese par `(equipo_local, jornada)` con `datos/calendario.json` usando `datos/equivalencias_equipos.json` para normalizar el nombre del Excel al nombre interno.
3. El resultado es el `id` de partido al que pertenece esa predicción.

**Por qué:** las filas del Excel no tienen por qué estar en el mismo orden que `calendario.json`. El emparejamiento por nombre + jornada es robusto frente a reordenaciones en la plantilla.

**Nombres canónicos confirmados** (lista cerrada, validada contra el Excel real):
A: México, Sudáfrica, Corea del Sur, República Checa
B: Canadá, Bosnia y Herzegovina, Catar, Suiza
C: Brasil, Marruecos, Haití, Escocia
D: Estados Unidos, Paraguay, Australia, Turquía
E: Alemania, Curazao, Costa de Marfil, Ecuador
F: Países Bajos, Japón, Suecia, Túnez
G: Bélgica, Egipto, Irán, Nueva Zelanda
H: España, Cabo Verde, Arabia Saudita, Uruguay
I: Francia, Senegal, Irak, Noruega
J: Argentina, Argelia, Austria, Jordania
K: Portugal, RD Congo, Uzbekistán, Colombia
L: Inglaterra, Croacia, Ghana, Panamá

### Fase 5 — Automatización con GitHub Actions

#### Cómo se dispara el workflow

El workflow `.github/workflows/actualizar.yml` tiene dos disparadores:

- **`schedule` (cron `*/5 * * * *`)**: se ejecuta cada 5 minutos automáticamente. El script `motor/pipeline.py` comprueba primero si hay un partido en curso o inminente (ventana: 1 h antes – 3 h después). Si no la hay, termina sin llamar a la API. Esto protege la cuota de 100 peticiones/día de API-Football.
- **`workflow_dispatch` (manual)**: se dispara desde la pestaña *Actions* del repo → *"Run workflow"*. Parámetros:
  - `modo`: `demo` (datos sintéticos, para verificar el despliegue antes del Mundial) o `live` (pipeline real).
  - `forzar_ventana`: ignorar la comprobación de ventana cuando se usa modo `live`.

#### Cómo se publica el sitio

1. El workflow genera/actualiza los JSON en `web/data/` y hace `git commit + git push` de los cambios al repo.
2. Acto seguido, sube la carpeta `web/` como artefacto de Pages y la despliega con `actions/deploy-pages@v4`.
3. El sitio queda disponible en `https://<usuario>.github.io/<repo>/` en ≈1-2 minutos.

#### Scripts del pipeline

| Script | Rol |
|---|---|
| `motor/pipeline.py` | Orquestador. Comprueba ventana, descarga resultados, llama a `generar_sitio`. |
| `motor/generar_sitio.py` | Genera `standings.json`, `detalle.json`, `proximos.json`, `snapshots.json` para cada porra en `web/data/`. También se puede ejecutar en local. |
| `motor/descargar_resultados.py` | Descarga de openfootball + API-Football opcional. |
| `motor/generar_datos_demo.py` | Genera datos sintéticos de ejemplo (3–6 participantes por porra). |

#### Secretos necesarios en el repositorio

| Secreto | Obligatorio | Descripción |
|---|---|---|
| `API_FOOTBALL_KEY` | No | Clave de API-Football (plan gratuito). Si no existe, se usa solo openfootball. |

Para añadirlo: *Settings → Secrets and variables → Actions → New repository secret*.

#### Pasos de configuración en GitHub (los hace el usuario)

1. Crear el repositorio en GitHub (público, plan gratuito).
2. Hacer push inicial: `git init && git add . && git commit -m "init" && git remote add origin <url> && git push -u origin main`.
3. Activar GitHub Pages: *Settings → Pages → Source → **GitHub Actions***.
4. Lanzar el primer despliegue de prueba: *Actions → "Actualizar Porra Mundial 2026" → Run workflow → modo: demo → Run*.
5. En ≈2 min el sitio estará en `https://<usuario>.github.io/<repo>/`.
6. Opcionalmente añadir el secreto `API_FOOTBALL_KEY` para el respaldo de resultados en vivo.

#### Privacidad de los pronósticos en repo público

Los archivos `.xlsx` de los participantes **nunca se suben** (están en `.gitignore`). Los JSON de `datos/pronosticos/` solo deben subirse **después del cierre del plazo (11 de junio, 21:00)**, momento en que conocer las predicciones de otro participante ya no otorga ventaja. Hasta entonces, el organizador mantiene esos ficheros en local y sube solo el `web/data/` generado por `motor/generar_datos_demo.py`.

### Fase 4 — Panel web: decisiones de diseño (revisión v2)

- **Pantalla de acceso**: campo de contraseña único, sin selector de porra. La porra se detecta automáticamente según la contraseña introducida.
- **Sub-clasificación de fase previa**: `puntos_fase_previa` se sigue calculando en el motor (necesario para el premio del 10 %) pero **no se muestra** en el panel.
- **Paleta**: color de acento único `#c9921a` (ámbar). Sin rojo como color decorativo; rojo reservado exclusivamente para el indicador "En directo".
- **Tipografía**: Barlow Condensed (700/800/900) para titular de app, números de posición y totales grandes. Outfit (400/500/600/700) para todo el resto (body, chips, controles, tablas).
- **Contraste WCAG AA**: todos los textos y controles verificados ≥ 4,5:1 (texto normal) y ≥ 3:1 (texto grande / controles). `--text` ≈18:1, `--text2` ≈8:1, `--text3` ≈5:1, todos sobre `--bg #0f1218`.
- **Datos demo**: generados por `motor/generar_datos_demo.py` → `web/data/`. Ejecutar con `python -X utf8 motor/generar_datos_demo.py` para regenerar.
