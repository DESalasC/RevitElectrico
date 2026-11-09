# Plan de Acción — Desatascar RevitElectrico (T5-SantaMarta)

**Fecha:** 2026-10-24 (noche)
**Proyecto:** RevitElectrico — `D:\Work\PROJECTS\Actuales\T5-SantaMarta`
**Documento intervenido:** `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02.rvt`
**Estado:** diagnóstico cerrado con datos en vivo · corrección lista para ejecutar
**Bloqueos de ejecución:** CLI y MCP resueltos el 2026-10-24 a las 20:00 (ver §5)

---

## 1. Diagnóstico: dónde está realmente el atasco

El proyecto no está atascado en la creación de scripts: la creación funciona (37/37 instancias, 0 fallos). Está atascado en **tres capas de gobierno del modelo** que se rompieron en paralelo.

### 1.1 Evidencia recogida en vivo (Revit 2026, PID 27868)

Ejecutado con `pyrevit agent run` sobre el documento abierto. Salida completa en `data/estado_modelo_v01.json`.

| # | Hallazgo | Dato |
|---|----------|------|
| 1 | Dispositivos eléctricos en el documento | 37 (22 tomas, 8 luminarias, 6 interruptores, 1 tablero) |
| 2 | Instancias **sin nivel** (`LevelId = -1`) | **36 de 37** |
| 3 | Rango Z de los dispositivos | **−0,08 m a 2,62 m** (a nivel de calle) |
| 4 | Elevación real del nivel "Piso 5" | **43,3727 m** |
| 5 | Tablero (único bien ubicado) | Z 44,57 m, nivel Piso 5 ✅ |
| 6 | Conduits en el documento | **0** (ni tubería ni accesorios) |
| 7 | Vínculo existente | `STM-FJR-TORRE5-A-M3-R23-P01-CENTRA-prueba 01.rvt` (470 MB) |
| 8 | Vista activa | "Piso 5", FloorPlan, disciplina Electrical, corte +4,0 m, inferior +0,0 m |
| 9 | Categorías eléctricas ocultas en la vista | Ninguna (V/G correcto) |
| 10 | Archivos RVT en `3.-Proceso` | 8 copias, de 8,4 a 471 MB |

### 1.2 Causa raíz

El reporte `data/apto_F_02_aplicar_mapa_v3.json` trae `z_revit` como **altura local de montaje** (0,3 / 1,1 / 1,2 / 2,6 m). El script de modelado la usó como **Z absoluta**:

```json
{ "nombre_bloque": "ELEC-T-GFCI-t-15A", "z_revit": 0.3, "nivel_revit": "Piso 5" }
```

Con el Piso 5 a 43,3727 m, esos 0,3 m significan "planta baja". Resultado: 36 dispositivos quedaron enterrados 43 m por debajo del nivel, sin nivel asignado y fuera del rango de vista de cualquier planta. **No es un problema de visibilidad ni de V/G: es un problema de datum.**

### 1.3 Por qué nadie lo detectó antes

- `data/verificacion_instancias_revit.json` está **truncado a 25 bytes** (JSON inválido) desde el 2026-10-21.
- `data/diagnostico_visibilidad_v01.json` quedó en **0 bytes**: el script moría antes de escribir por un nombre de nivel con `Ó` (`CLASIFICACIÓN ACABADOS…`) que rompía `json.dumps` en IronPython 2.7.
- El acta de las 16:23 reportó "37 FamilyInstance verificadas" apoyándose en esos dos archivos, que nunca contenían datos válidos.
- `ASIGNAR_NIVEL_FALTANTES_v05` reportó "10 fallos face-based" cuando en realidad los 10 carecían de host y de nivel: el diagnóstico de face-based estaba invertido.

### 1.4 El bloqueo operativo que multiplicaba el costo (ya resuelto)

El CLI de pyRevit abortaba con *"You must install or update .NET"* porque `DOTNET_ROOT` apunta a la copia de AutoClaw (`C:\Program Files\AutoClaw\resources\dotnet\win-x64`), que no incluye `Microsoft.WindowsDesktop.App`. El runtime 8.0.32 **sí está instalado** en `C:\Program Files\dotnet`.

Con el override correcto, el agent host responde y el ciclo completo funciona sin copiar/pegar en el Python Shell:

```powershell
$env:DOTNET_ROOT="C:\Program Files\dotnet"
pyrevit agent status                       # -> Revit 2026 pid XXXX: responding
pyrevit agent run <script.py> --revit=2026 --mode=query --timeout=180
```

Esto convierte cada verificación de "10 minutos de clics" en 1 segundo de ejecución, y es la razón por la que el atasco se puede cerrar ahora.

---

## 2. Decisiones que necesito de ti (30 min, antes de la Fase 1)

| # | Decisión | Opciones | Recomendación |
|---|----------|----------|---------------|
| D1 | Documento canónico | (a) `E-..._V02.rvt` modelo eléctrico ligero + vínculo arquitectónico · (b) `...prueba 01.rvt` monolítico 470 MB | **(a)** V02: 10,5 MB, abre rápido, el arquitectónico entra como vínculo y el eléctrico se coordina aparte |
| D2 | Estrategia de modelado | (a) recrear con nivel y Z correctos · (b) mover +43,3727 m los 36 | **(a)** mover no asigna nivel ni corrige luminarias (están a Z≈0, no a 2,6) |
| D3 | Alcance del piloto | (a) 37 dispositivos · (b) 59 (incluye los 22 marcadores de conductores ya mapeables) | **(b)** el mapeo nuevo ya resuelve 1FTN/1TNR/1FTR/2FT2N/1FTNR |
| D4 | ¿Conduits en esta iteración? | sí / después | **sí**: sin tubería no hay clash detection real |

Si no respondes, avanzo con las recomendaciones marcadas y lo dejo escrito en el acta.

---

## 3. Plan de ejecución por fases

### Fase 0 — Gobierno documental (30 min) · bloqueante

| Tarea | Criterio de aceptación |
|-------|------------------------|
| Guardar V02 como **V03** (punto de retorno antes de tocar nada) | Archivo `E-..._V03.rvt` existe y abre |
| Declarar V03 como documento canónico único | Nota en `CLAUDE.md` + este plan |
| Congelar `prueba 01/02/03` y `_V01` como solo lectura | Renombrados a `_historico\` |
| Fijar datum: **Piso 5 = 43,3727 m** (viene del arquitectónico) | Registrado en la nota |
| Regla nueva: `z_revit` en JSON es **altura local**; la Z absoluta se calcula `nivel.Elevation + altura_local` | Regla escrita en `CLAUDE.md` |

### Fase 1 — Corregir el bloque piloto F02 (1–2 h)

Herramienta lista: [`F6_CORREGIR_UBICACION_ELECTRICA_v01.py`](D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\F6_CORREGIR_UBICACION_ELECTRICA_v01.py)

1. Simulación (ya corrida, sin tocar el modelo): 37 instancias, 36 fuera de nivel, 37 acciones preparadas.
2. Aplicar: borra las 37 y las recrea con `Z = 43,3727 + altura_local`.
3. Verificar con `DIAGNOSTICO_ESTADO_MODELO_v01.py` y el verificador de invariantes
   [`F6_VERIFICAR_INVARIANTS_v01.py`](D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\F6_VERIFICAR_INVARIANTS_v01.py).

**Aceptación:**
- 37 instancias con `nivel = Piso 5` y `nivel_id` válido (no −1).
- `z_relativo_nivel` en 0,3 / 1,1 / 1,2 / 2,6 (±0,05).
- 0 instancias con `sin_nivel`.

### Fase 2 — Completar F02 al 100 % (2–3 h)

| # | Tarea | Aceptación |
|---|-------|-----------|
| 2.1 | Modelar los 22 marcadores de conductores con el mapeo nuevo | 59/59 dispositivos |
| 2.2 | Crear conduit por diámetro según conductores (tipos ya existen: 5/5) | Conduits > 0 y accesorios coherentes |
| 2.3 | Crear vista "Piso 5 — Eléctrico" con rango propio (inferior 0,0 / corte 1,5 / superior 2,8) | Dispositivos visibles en planta sin tocar V/G global |
| 2.4 | Asignar RED / CIRCUITO / ACOMETIDA | 100 % de tomas con circuito |
| 2.5 | `CLASH_DETECTION_v01.py` en modo bbox | Reporte de interferencias emitido |
| 2.6 | Elevar el invariante a `--min-conduits 1` | Verificador en verde con conduits |

### Fase 3 — Escalar a los bloques restantes (1–2 días)

El DXF contiene **19 definiciones de apartamento** (21 pisos; algunas agrupadas: "F 17 y 03", "F 18 y 04"), no 20 bloques sueltos.

| # | Tarea | Aceptación |
|---|-------|-----------|
| 3.1 | Extraer por bloque: un JSON de dispositivos por tipo de apartamento | 19 JSON en `data/bloques/` |
| 3.2 | Runner que itera bloque → mapeo → creación → verificación | 1 comando, 1 reporte por bloque |
| 3.3 | Modelar los 19 tipos, uno por piso, con el datum por nivel del piso | 21/21 pisos con eléctrico |
| 3.4 | Reporte consolidado por piso | Tabla única de avance |

### Fase 4 — Automatización y control (transversal, 4 h)

| # | Tarea | Aceptación |
|---|-------|-----------|
| 4.1 | ~~Fijar `DOTNET_ROOT`~~ **HECHO 2026-10-24 20:00**: `env.DOTNET_ROOT` en el MCP de Claude Code + `scripts/pyrevit.cmd` | `claude mcp list` → pyrevit Connected; wrapper responde sin exportar variable |
| 4.2 | Smoke test post-cambio: corre diagnóstico y falla si hay instancias sin nivel o conduits = 0 | 1 comando verde/rojo |
| 4.3 | Tests de los scripts nuevos con `revit_db` inyectable | `pytest tests/fase-6-revit` verde |
| 4.4 | Retirar `ASIGNAR_NIVEL_FALTANTES_v05` (queda obsoleto tras Fase 1) y corregir su detección de face-based | Script archivado |

---

## 4. Secuencia recomendada (primera sesión de 3 h)

1. **15 min** — Fase 0: copia V03, congelar históricos.
2. **20 min** — Fase 1 paso 2: aplicar corrección y verificar con el diagnóstico.
3. **30 min** — Abrir vista "Piso 5", confirmar visualmente los 37 dispositivos a las alturas correctas.
4. **60 min** — Fase 2.1: los 22 marcadores.
5. **30 min** — Fase 2.3: vista eléctrica con rango propio.
6. **15 min** — Cierre: actualizar `estado-avance-revitelectrico.md` y acta.

---

## 5. Comandos listos

```powershell
$root = "D:\Work\PROJECTS\Actuales\T5-SantaMarta"
$env:DOTNET_ROOT="C:\Program Files\dotnet"   # o usar scripts\pyrevit.cmd
$exe  = "C:\Users\Dario Salas\AppData\Roaming\pyRevit-Master\bin\pyrevit.exe"

# Atajo: wrapper que ya fija DOTNET_ROOT
$py = "$root\scripts\pyrevit.cmd"
& $py agent status
& $py agent run "$root\scripts\test_agent_simple.py" --revit=2026 --timeout 30

# Estado del modelo (solo lectura)
& $exe agent run "$root\src\fase-6-revit\DIAGNOSTICO_ESTADO_MODELO_v01.py" `
  --revit=2026 --mode=query --timeout=180 `
  --inputs '{"root":"D:\Work\PROJECTS\Actuales\T5-SantaMarta"}'

# Corrección en simulación (no toca el modelo)
& $exe agent run "$root\src\fase-6-revit\F6_CORREGIR_UBICACION_ELECTRICA_v01.py" `
  --revit=2026 --mode=query --timeout=180 --workspace "$root\src\fase-6-revit" `
  --inputs '{"root":"D:\Work\PROJECTS\Actuales\T5-SantaMarta","confirmar":false}'

# Verificación de invariantes (CI, sin Revit)
python "$root\src\fase-6-revit\F6_VERIFICAR_INVARIANTS_v01.py" `
  --estado "$root\data\estado_modelo_v01.json" --nivel "Piso 5" --min-instancias 37 `
  --min-conduits 1

# Corrección aplicada (borra y recrea 37 instancias)
& $exe agent run "$root\src\fase-6-revit\F6_CORREGIR_UBICACION_ELECTRICA_v01.py" `
  --revit=2026 --mode=modify --title="F6 corregir ubicacion electrica F02" --timeout=300 `
  --workspace "$root\src\fase-6-revit" `
  --inputs '{"root":"D:\Work\PROJECTS\Actuales\T5-SantaMarta","confirmar":true}'
```

---

## 6. Riesgos

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| El arquitectónico está vinculado y el eléctrico se modela en V03: los niveles del vínculo no son hosts válidos | Medio | Usar niveles propios de V03 (existen: Piso 5 = 43,3727) y solo referenciar el vínculo para clash |
| Al recrear, las familias de techo no encuentran cara de cieloraso (está en el vínculo) | Medio | Fallback a nivel + Z absoluta (ya implementado); las luminarias quedan a 2,6 m |
| Los 43 MB de diferencia entre V02 y prueba 01 esconden geometría faltante | Medio | Fase 2.5 (clash) revelará qué falta; comparar con IFC |
| Recrear borra parámetros ya asignados (RED=SI en 8 dispositivos) | Bajo | `ASIGNAR_RED_v05.py` se re-ejecuta en 10 s (busca por posición) |
| 19 definiciones de bloque con nombres inconsistentes ("Apatamento", "Apatamentos") | Bajo | Normalizar en el extractor, con tabla de alias |

---

## 7. Definición de "atasco resuelto"

- [ ] V03 canónico declarado y históricos congelados
- [ ] 37/37 dispositivos con nivel Piso 5 y Z relativa correcta — `F6_VERIFICAR_INVARIANTS_v01.py` en verde
- [ ] Vista "Piso 5 — Eléctrico" muestra los dispositivos sin depender del rango de la vista arquitectónica
- [ ] Conduits > 0 y accesorios coherentes
- [ ] 59/59 dispositivos del bloque F02 modelados
- [ ] `pytest tests/fase-6-revit` verde (hoy: 7/7 del verificador + suite existente)
- [ ] Acta y estado de avance actualizados con evidencia enlazada

---

## 8. Deuda reconocida

- Los dos scripts nuevos (`DIAGNOSTICO_ESTADO_MODELO_v01`, `F6_CORREGIR_UBICACION_ELECTRICA_v01`) **no tienen test pytest**: dependen de la API de Revit en tiempo de importación. Quedó como tarea 4.3 con la estrategia `revit_db` inyectable que ya usan los scripts existentes.
- `ASIGNAR_NIVEL_FALTANTES_v05` y `DIAGNOSTICAR_VISIBILIDAD_v01` quedan obsoletos tras la Fase 1; se archivan, no se borran, hasta cerrar la verificación.
