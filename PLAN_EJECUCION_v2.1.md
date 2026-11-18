---
proyecto: RE
tipo: plan-ejecucion
version: v2
fecha: 2026-11-18
estado: borrador-para-aprobar
norma: 2
reemplaza: PLAN_EJECUCION.md (2026-10-24)
tags: [proyecto/re, plan, ejecucion, v2, consolidado]
---

# PLAN_EJECUCION v2 — RevitElectrico (consolidado 2026-11-18)

> **Reemplaza** al `PLAN_EJECUCION.md` del 2026-10-24, que queda como histórico en `vault/PLAN_EJECUCION.md`.
>
> **Fuente de verdad:** panel + pendientes + cierres 2026-11-15/16/17 + lección `FamilyPlacementType`. Toda la sección 4 (hallazgos) y 5 (plan de acción) son **nuevas** respecto al plan anterior.

---

## 1. Contexto y alcance

El proyecto **RevitElectrico** lleva la información eléctrica 2D (circuitos, cableado, paneles, dispositivos, conexiones) de planos DXF a un modelo Revit 2026 3D para validación de interferencias y coordinación interna. Es independiente de `DiseñoParametrico` y de `T5-SantaMarta` (este último es insumo de solo lectura).

**Alcance aprobado (sin cambios desde v1):**

- Representación 3D: dispositivos + conduits.
- **Sin** cálculos RETIE/NTC 2050 (ya están en 2D).
- **Sin** unifilar.
- **Sin** POT/.gpkg (Santa Marta, no Bogotá).
- Revit 2026.4 (no 2027) como motor de ejecución.
- Documento de trabajo vigente: `STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01.rvt` (en `ArchivosBase/`).
- Benchmark de referencia (solo lectura): `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02-f.rvt`.

**Cambios de alcance respecto a v1:**

- Foco de modelado: pasa de "F02 Piso 5 piloto" a **"F01 y F02 como piloto de ruteo (conduits)"**. La colocación de dispositivos ya está probada en E05 y E06.
- Inventario consolidado: **20 unidades en Piso 5** (E, F, B, C, D), **901 aparatos** totales. El "47" es propio del tipo E.
- Piloto de colocación de dispositivos: se mueve a **E07** (no F02) porque E06 ya está modelado a mano y sirve como oráculo.
- Canal de ejecución: **MCP sobre TCP 8080** (no pyRevit directo). El plugin expone 23 herramientas con límite de 8 KB por llamada.

---

## 2. Cronología consolidada del avance

| Fecha | Sesión | Hitos clave | Suite |
|---|---|---|---|
| 2026-10-24 | PLAN_EJECUCION v1 | 37 FamilyInstance en F02 Piso 5; 42 tests | 42 |
| 2026-11-08-c | Limpieza y gobierno | 54 scripts obsoletos eliminados; 31 vigentes | — |
| 2026-11-09 | E05 definitivo | 49/49 dispositivos con host; 24 duplicados eliminados | — |
| 2026-11-11 | E06 V03 sin guardar | 47/47 representados (31 creados + 32 duplicados); D0 aplicado | — |
| 2026-11-14 | Qwen — F01 colocación | 9/35 colocados; bug `Reference direction is parallel to face normal` | — |
| 2026-11-15-b | F0 + F1 | Hashes baseline; veredicto E06 `0/44`; censo V02-f y CENTRAL-V01; catálogo 33 familias; alturas y rotaciones resueltas | 381 / 2 skipped |
| 2026-11-16-a | Canal MCP + inventario + E07 | TCP 8080 verificado (23 herramientas); 20 unidades inventariadas; E07 colocado en memoria (47/47, no guardado) | 412 / 2 skipped |
| 2026-11-17-a | Inventario + conduit + orientación | 901 aparatos en 20 unidades; contrato `conduit_creacion_v01.json`; oráculo orientación corregido (eje real 90°/270°); V02-f exportado (144/147 tramos válidos, 133,3 m) | **427 / 2 skipped** |

---

## 3. Estado actual medido (2026-11-17 cierre)

### 3.1 Documento activo

- `STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01.rvt` — `document.IsModified = false`.
- **E07 NO guardado**: 0 de 6 elementos de `colocacion_E07_v01.json` existen en el documento.
- 47 aparatos modelados a mano (E06).
- **0 instancias de conduit**, 3 tipos cargados (`Tubo` ×2, `Tubo Comunicaciones` ×1, todos EMT).
- `Servicio_Conduit` existe como parámetro de proyecto, `InstanceBinding` a Conduits + Conduit Runs + Conduit Fittings.

### 3.2 Canal MCP

- Plugin `mcp-servers-for-revit.addin` en `%APPDATA%\Autodesk\Revit\Addins\2026`.
- Comando `commandRegistry.json`: 25 declarados, 24 únicos (`create_dimensions` duplicado).
- **Servidor no usa WebSocket**: TCP crudo en `localhost:8080` (`net.connect`), JSON-RPC 2.0 sin delimitador.
- `send_code_to_revit` template: `Execute(Document document, object[] parameters)`. **No existe `__doc__`** (4 errores de compilación al probarlo).
- **Límite de 8 KB** por llamada; por encima, JSON truncado y respuesta con `id: null` → el cliente espera 120 s y reporta timeout.
- `list_electrical_components` existe en el plugin (declarado, habilitado) pero **no en el paquete npm 1.0.0**. Consumir por TCP.
- Incógnita resuelta: el comando **no está acotado a la vista activa**, recorre el documento.

### 3.3 Inventario cerrado

| Tipo | Unidades | Aparatos por unidad |
|---|---|---|
| E (05, 06, 07, 07a, 08, 08a) | 6 | 47 |
| F (01, 01a, 01b, 02, 02a, 02b, 17, 17a, 18, 18a) | 10 | 36 |
| B 15 / B 16 | 2 | 69 / 71 |
| C 14 | 1 | 60 |
| D 13 | 1 | 59 |

**Total: 20 unidades, 901 aparatos.** Paneles: 20 tableros con nombre único, 20/20 con su DXF.

### 3.4 Ruteo de referencia (V02-f)

- 147 conduits exportados (138,852 m), 87 dispositivos (85 en F01/F02 + 2 sueltos).
- **144 tramos válidos** tras filtrar 3 restos a z=288.22 m (prueba, no ruteo).
- 84/87 aparatos con extremo de conduit ≤ 500 mm (63 a ≤ 100 mm).
- Por servicio: TOMAS 63 · ILUMINACIÓN 46 · COMUNICACIONES 17 · FUERZA 13 · vacío 5.
- Por diámetro: 16 mm (1/2") ×4 · 21 mm (3/4") ×93 · 27 mm (1") ×47.

### 3.5 Orientación (oráculo RE-P-060)

- **Conclusión corregida (2026-11-17):** el "7/3" era un **conteo de aparatos** (7 a 86,68°, 3 a 266,68°), no un ángulo. El desfase de 3,32° es un artefacto del cálculo del eje (centro del bbox vs punto de inserción; ancho de símbolo 24,61 mm / fondo 424,20 mm → `atan(24,61/424,20) = 3,32°`).
- **Eje real corregido: 90°/270° exactos**, coincide con el DXF.
- **No hay defecto de orientación medible en E06.**
- Implementado y probado en `RE_ORACULO_ORIENTACION_v01.py` (5 tests, fixture `oraculo_orientacion_E06_v01.json` con 36 mediciones reales).

### 3.6 Conduit (RE-P-063)

- `Conduit.Create(document, conduitTypeId, startPoint, endPoint, levelId)` es la firma correcta.
- El diámetro **no** vive en el tipo: es la instancia `RBS_CONDUIT_DIAMETER_PARAM`.
- Tamaños válidos consultables con `ConduitSizeSettings.GetConduitSizeSettings(document)`. Para EMT: 10 nominales, 0,052 pies (1/2") a 0,338 pies (4").
- Contrato en `config/conduit_creacion_v01.json`, con tests cruzados contra `equivalencias_conduit_v01.json` y `ruteo_config_v04.json`.
- Material decidido: **PVC rígido al interior, SCH40 al exterior**.

### 3.7 Alturas y rotaciones

- Alturas: base 0,30 m para tomas, 9 excepciones medidas y ancladas por **código + posición** (no por handle, que se regenera al reexportar DXF).
- Tomas de datos estandarizadas a **1,00 m** (10/10, ignorando la anotación 1,05 del DXF).
- Campana **2,40**, punto de consolidación **2,70**, timbre **1,10**.
- Rotación: heredada del host para hosted, delta `+90°` para tomas sin host (placa horizontal, práctica colombiana).
- Excepciones por apartamento: 6 unidades ancladas (E05, E06, E07, E07a, E08, E08a).

---

## 4. Hallazgos e inconsistencias detectadas (a resolver localmente)

Cada hallazgo tiene un ID `RE-H-XXX` para que puedas rastrear su resolución en `RE-00-pendientes.md`. El orden es por impacto, no por fecha.

### RE-H-001 — `PLAN_EJECUCION.md` (v1) obsoleto

- **Síntoma:** el plan del 2026-10-24 sigue listando F02 Piso 5 como foco. No menciona canal MCP, pivot a F01/F02 como piloto de ruteo, ni la decisión de conduit (PVC/SCH40). Los criterios de aceptación sección 5 ya no reflejan la realidad.
- **Causa:** el plan dejó de actualizarse cuando se introdujo el sistema de notas del vault (F0/F1, sesión 2026-11-08-c).
- **Acción:** archivar `PLAN_EJECUCION.md` como histórico (renombrar a `PLAN_EJECUCION_v1_historico.md` o mover a `vault/historico/`). El plan vivo pasa a ser este `PLAN_EJECUCION_v2.md`.
- **Verificación:** buscar referencias a `PLAN_EJECUCION.md` (sin versión) en el código, tests y notas del vault; actualizar todas.

### RE-H-002 — `RE-00-panel.md` desincronizado con el último avance

- **Síntoma:** dice "Suite: 412/412" y "Último hito (2026-11-16)". El avance del 17-nov reporta **427 passed, 2 skipped**. No hay mención de RE-P-063 (contrato conduit), RE-P-064 (re-inventario cerrado) ni RE-P-060 resuelto.
- **Acción:** propagar el cierre de la sesión 17-nov al panel:
  1. Actualizar "Último hito" con fecha 2026-11-17.
  2. Cambiar suite a "427 / 2 skipped".
  3. Añadir mención al contrato conduit y al oráculo de orientación resuelto.
  4. Actualizar el bloque "Primer paso de la próxima sesión".
- **Verificación:** `grep -n "412" RE-00-panel.md` debe devolver 0 líneas; `grep -n "427" RE-00-panel.md` debe devolver ≥1.

### RE-H-003 — Memoria "El error del script v69" superada

- **Síntoma:** la memoria recomienda `direction = XYZ.BasisZ` como solución al error `Reference direction is parallel to face normal`. La lección `RE-2026-11-15-leccion-family-placement-type` la **corrige**: la sobrecarga legal se decide por `Family.FamilyPlacementType`, no por el vector de dirección.
- **Causa:** la memoria se redactó antes de que se diagnosticara la causa raíz (FamilyPlacementType).
- **Acción:**
  1. Editar la nota de memoria (en el vault de nowledge-mem, no en Obsidian) y añadir al inicio: `> **NOTA (2026-11-18):** Superada. Ver RE-2026-11-15-leccion-family-placement-type. La solución real es discriminar por FamilyPlacementType, no por vector de dirección.`.
  2. En el vault de Obsidian, crear `50-lecciones/RE-2026-11-18-leccion-memoria-v69-superada.md` que enlace ambas notas.
- **Verificación:** buscar "XYZ.BasisZ" en el código; si aparece en algún script sin un comentario que indique "solo para WorkPlaneBased", corregir.

### RE-H-004 — `RE-00-pendientes.md` no refleja cierres del 17-nov

- **Síntoma:** RE-P-060 (oráculo orientación), RE-P-064 (re-inventario 20 unidades) y parte de RE-P-062 (export V02-f) están resueltos según el avance del 17-nov, pero siguen marcados como "Abiertos" en `RE-00-pendientes.md`.
- **Acción:** mover de "Abiertos" a "Cerrados":
  - RE-P-060 → cerrado 2026-11-17, resultado: "Eje real 90°/270° = DXF. No hay defecto. Implementado en RE_ORACULO_ORIENTACION_v01.py (5 tests)."
  - RE-P-064 → cerrado 2026-11-17, resultado: "20 unidades inventariadas en `data/inventario_unidades_v01.json`. 901 aparatos totales. Test que falla si aparece un tercer bloque sin mapear."
  - RE-P-062 → **parcialmente cerrado**: export hecho (144/147 tramos válidos en `data/v02f/`), falta la **transferencia** del ruteo a CENTRAL-V01. Reformular como RE-P-066 (transferencia de ruteo).
- **Verificación:** `grep -E "RE-P-0(60|64)" RE-00-pendientes.md` debe devolver solo filas de la tabla "Cerrados".

### RE-H-005 — Ambigüedad de tipos `Tubo`

- **Síntoma:** hay dos tipos llamados `Tubo` en CENTRAL-V01: Id=112216 (with fittings) y Id=112217 (without fittings). Seleccionar por nombre es ambiguo.
- **Causa:** el operador no renombró ninguno al cargarlos; ambos vinieron con el nombre por defecto del catálogo.
- **Acción (requiere aprobación del operador):**
  - Renombrar 112216 a `Tubo EMT c/acc` (o equivalente).
  - Renombrar 112217 a `Tubo EMT s/acc`.
  - Actualizar `config/conduit_creacion_v01.json` para referenciar por `ElementId` (más estable) o por nombre nuevo.
- **Verificación:** snippet MCP que liste los tipos de conduit y compruebe que los nombres son únicos.

### RE-H-006 — Bloques sin familia/tipo en `MAPEO_DEFAULT`

- **Síntoma:** `S3C` (solo B15/B16) y `ELEC-I-S-2-5A` (F, C, D) no tienen familia/tipo mapeado en el colocador.
- **Causa:** el mapeo se construyó para E05/E06 (tipo E) y no se extendió a B/C/D/F.
- **Acción:**
  1. Abrir `STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01.rvt` y `CENTRA_V02-f.rvt`, buscar los tipos reales asociados a esos bloques.
  2. Añadir las equivalencias a `config/catalogo_familias_CENTRAL_V01_v01.json` y a `MAPEO_DEFAULT` del colocador.
  3. Mantener el test que falla si aparece un tercer bloque sin mapear.
- **Verificación:** correr `RE_F1_INVENTARIO_UNIDADES_v01.py` sobre B15 y B16; debe dar 0 sin mapear.

### RE-H-007 — Intento F01/F02 del 17-nov descartado sin lección formal

- **Síntoma:** se crearon 70 aparatos con `NewFamilyInstance(XYZ, símbolo, nivel, NonStructural)`. Se descartaron sin guardar. Causa documentada: 11/12 familias del plan son `WorkPlaneBased` y esa sobrecarga ignora X/Y/Z. Pero no hay nota `50-lecciones/RE-2026-11-17-leccion-sobrecarga-equivocada.md` formal.
- **Causa:** se documentó dentro del avance 17-nov (sección 10), pero no se extrajo como lección independiente.
- **Acción:** crear `50-lecciones/RE-2026-11-17-leccion-sobrecarga-equivocada.md` con:
  - Contexto: intento fallido F01/F02.
  - Regla: la sobrecarga `NewFamilyInstance(XYZ, símbolo, nivel, StructuralType)` solo es válida para `OneLevelBased`. Para `WorkPlaneBased` se necesita `face_ref`.
  - Corolario: una sona previa de `FamilyPlacementType` por familia es obligatoria antes de cualquier colocación masiva.
  - Enlace a `RE-2026-11-15-leccion-family-placement-type`.
- **Verificación:** la nota debe aparecer en `RE-00-panel.md` enlazada en "Lecciones recientes".

### RE-H-008 — Commit del 17-nov no verificado

- **Síntoma:** la nota del 16-nov menciona último commit `d8834a4`. La sesión del 17-nov creó 3 scripts nuevos, 3 tests nuevos, 1 config nuevo y 2 JSON de datos. No hay evidencia de commit posterior.
- **Acción:** correr en `D:\Work\PROJECTS\RevitElectrico`:
  ```powershell
  git log --oneline -5
  git status
  ```
  - Si hay cambios sin commitear: `git add -A && git commit -m "Sesion 2026-11-17-a: inventario 20 unidades, contrato conduit, oraculo orientacion resuelto, export V02-f"`.
  - Si ya hay commit: anotar el hash en `RE-00-panel.md`.
- **Verificación:** `git status` debe devolver "nothing to commit, working tree clean".

### RE-H-009 — Discrepancia "72 aparatos" vs 85 medidos en V02-f

- **Síntoma:** el enunciado del 16-nov decía "72 aparatos" para F01/F02. La medición real del 17-nov da 85 en F01 (42) y F02 (43), o 66 si se descuentan las 19 cajas de conexiones.
- **Causa:** probablemente el "72" era una estimación visual o un conteo parcial previo.
- **Acción:** anotado, no resuelto. Decidir cuál es el conteo canónico antes de transferir el ruteo. Sugerencia: **85 (sin descontar cajas)**, porque las cajas también son parte del ruteo.
- **Verificación:** que `data/v02f/dispositivos_v01.json` tenga 87 entradas (85 F01/F02 + 2 sueltos) y la decisión quede registrada en `data/v02f/validacion_ruteo_v01.json` como `conteo_canonico: 85`.

### RE-H-010 — 5 conduits sin `Servicio_Conduit`

- **Síntoma:** en V02-f, 5 tramos válidos no tienen `Servicio_Conduit` asignado (más 3 restos descartados).
- **Acción:** antes de transferir el ruteo a CENTRAL-V01, clasificar esos 5 tramos por tipo de dispositivo extremo y asignar servicio. Documentar la asignación en `data/v02f/servicios_faltantes_v01.json`.
- **Verificación:** el conteo "vacío" en `validacion_ruteo_v01.json` debe bajar a 0.

### RE-H-011 — 5 aparatos sin host en CENTRAL-V01

- **Síntoma:** `5529846`, `5529849`, `5529855` (tomas) y `5529817`, `5529823` (datos) flotan sin host en el modelo. Las dos de datos están junto a `5529826` y `5529829` en la misma fila `x = 5080,3`.
- **Causa:** defecto del modelo E06 modelado a mano.
- **Acción:** no corregir E06 (es el oráculo). Pero al colocar E07 y los demás apartamentos, validar que ningún aparato quede sin host. El resolvedor de techo (`RE_RESOLVER_TECHO_v01.py`) y la sobrecarga correcta por `FamilyPlacementType` ya lo previenen.
- **Verificación:** el diff de E07 (cuando se recoloque) debe dar 0 sin host.

---

## 5. Plan de acción por prioridad

### Prioridad P0 — Crítico, bloquea la siguiente sesión

| ID | Acción | Responsable | Verificación |
|---|---|---|---|
| A-P0-1 | Resolver **RE-H-001**: archivar `PLAN_EJECUCION.md` v1, aprobar v2 | Operador | Commit con renombrado; references actualizadas |
| A-P0-2 | Resolver **RE-H-002**: actualizar `RE-00-panel.md` con datos del 17-nov | Operador (yo puedo redactar el diff) | `grep "412" RE-00-panel.md` = 0; `grep "427" RE-00-panel.md` ≥1 |
| A-P0-3 | Resolver **RE-H-004**: mover RE-P-060, RE-P-064 a "Cerrados" en `RE-00-pendientes.md`; crear RE-P-066 (transferencia de ruteo) | Operador (yo puedo redactar el diff) | Tabla "Cerrados" actualizada |
| A-P0-4 | Verificar/crear commit del 17-nov: `git -C "D:\\Work\\PROJECTS\\RevitElectrico" log --oneline -3`. Si hay cambios sin commitear, commit con mensaje `"Sesion 2026-11-17-a: inventario 20 unidades, contrato conduit, oraculo orientacion resuelto, export V02-f"`. Anotar el hash en `RE-00-panel.md`. | Operador | `git status` devuelve "nothing to commit, working tree clean"; hash anotado |

### Prioridad P1 — Alto, desbloquea F2 (ruteo en F01/F02)

| ID | Acción | Responsable | Verificación |
|---|---|---|---|
| A-P1-1 | Resolver **RE-H-005**: renombrar uno de los tipos `Tubo` (requiere operador en Revit) | Operador + script de renombrado MCP | Snippet MCP lista tipos únicos por nombre |
| A-P1-2 | Resolver **RE-H-006**: mapear `S3C` y `ELEC-I-S-2-5A` | Operador + script | `RE_F1_INVENTARIO_UNIDADES_v01.py` da 0 sin mapear en B15, B16, F01, C14, D13 |
| A-P1-3 | Resolver **RE-H-009**: fijar conteo canónico F01/F02 (85 sugerido) | Operador | Decisión registrada en `data/v02f/validacion_ruteo_v01.json` |
| A-P1-4 | Resolver **RE-H-010**: clasificar 5 conduits sin servicio | Operador (yo puedo generar el script de clasificación) | `vacío: 0` en `validacion_ruteo_v01.json` |
| A-P1-5 | Recolocar E07 con orientación validada (RE-P-061) y **guardar** | Operador + `RE_COLOCAR_DISPOSITIVOS_generico.py` | `colocacion_E07_v02.json` con 47/47 OK y `document.IsModified = true` antes de `Ctrl+S` |
| A-P1-6 | Crear tipos de conduit faltantes en CENTRAL-V01 (RE-P-063) | Script MCP `crear_tipos_conduit_v05.py` (nueva versión) | Snippet MCP lista tipos con diámetro correcto |

### Prioridad P2 — Medio, habilita masificación

| ID | Acción | Responsable | Verificación |
|---|---|---|---|
| A-P2-1 | Resolver **RE-H-003**: marcar memoria v69 como superada | Operador (yo redacto la nota de lección) | Nota en `50-lecciones/RE-2026-11-18-leccion-memoria-v69-superada.md` |
| A-P2-2 | Resolver **RE-H-007**: extraer lección formal del intento fallido F01/F02 | Yo redacto | Nota en `50-lecciones/RE-2026-11-17-leccion-sobrecarga-equivocada.md` |
| A-P2-3 | Transferir ruteo de V02-f a CENTRAL-V01 (RE-P-066 nuevo) | Script MCP | 144 conduits creados en CENTRAL-V01 con `Servicio_Conduit` asignado |
| A-P2-4 | Resolver **RE-H-011**: documentar los 5 aparatos sin host como defecto conocido de E06 (no corregir) | Yo redacto comentario en `RE-00-estado.md` | Anotación visible |

### Prioridad P3 — Bajo, mejora continua

| ID | Acción | Responsable | Verificación |
|---|---|---|---|
| A-P3-1 | Masificar colocación a las 19 unidades restantes (E05, E06 ya hechos; faltan 18) | Operador + script | `data/inventario_unidades_v01.json` con 901/901 colocados |
| A-P3-2 | Detección de colisiones con HVAC/estructura/fontanería (RE-P-012) | `CLASH_DETECTION_v01.py` | Reporte `clashes_v01.json` |
| A-P3-3 | Acometidas generales: tablero de piso → contadores → TB parciales (RE-P-013) | Operador + script | Alcance definido y modelado |

---

## 6. Recomendaciones técnicas

### 6.1 Sobre el canal MCP

- **Mantener el catálogo de 23 herramientas** como referencia. La premisa "falta `list_electrical_components`" (RE-P-054) es **falsa**: está en el plugin pero no en el paquete npm. Consumir por TCP crudo en `localhost:8080`.
- **Código en línea límite 8 KB.** Partir cualquier bloque de C# mayor en chunks de ~7 KB con margen. El error viaja con `id: null` y el cliente MCP lo descarta; el síntoma visible es timeout, no error.
- **No abrir `Transaction` propia** si el plugin ya abrió la suya sobre el documento activo. El estado normal durante la llamada es "transacción anidada rechazada". Solo queda atascado si una excepción sin capturar impide el commit; entonces cerrar y reabrir el documento sin guardar.
- **Seleccionar documento por título** en `Application.Documents`, no por `ActiveUIDocument.Document` (el activo cambia con el foco).

### 6.2 Sobre la colocación de dispositivos

- **Sondar `FamilyPlacementType` antes de cualquier colocación masiva.** Ya hay un JSON de capacidades que guarda el nombre real del enum más `sobrecarga ∈ {host_element, face_ref, sin_host}`. Cargarlo y respetarlo.
- **Nunca usar la sobrecarga `NewFamilyInstance(XYZ, símbolo, nivel, StructuralType)` para familias `WorkPlaneBased`.** Ignora X/Y/Z. Esto ya costó 70 aparatos descartados el 17-nov.
- **Z relativa al nivel del host**, no absoluta. Corregir con `INSTANCE_ELEVATION_PARAM` (escribible), no moviendo geometría ni asignando `LevelId` (read-only en `FamilyInstance`).
- **Rotación heredada del host** para familias hosted. Sumarle un delta calculado desde la normal **gira dos veces**. El delta por familia solo aplica cuando no hay host.
- **El handle del DXF no es identidad.** Reexportar un DXF regenera los handles. Cualquier excepción debe anclarse por **código + posición**.

### 6.3 Sobre la validación

- **Medir el punto de inserción, no el bounding box.** 57 mm de diferencia bastaron para concluir, equivocadamente, que el modelo manual no seguía el DXF.
- **La altura puede estar en una anotación de texto del plano**, no en un atributo del bloque. Buscarla antes de inventar reglas espaciales.
- **Diff por multiconjunto de alturas dentro de cada familia|tipo**, no por instancia. El emparejamiento instancia-a-instancia no es fiable cuando hay aparatos a 100-150 mm entre sí.
- **Tolerancias D10**: aceptación 0,02 m; aviso 0,05 m; dedup 0,10 m.
- **La fuente de verdad de familias es el documento donde se va a colocar**, no el benchmark. CENTRAL-V01 y V02-f difieren en familias, tipos y categorías.

### 6.4 Sobre el ruteo

- **No crear tipos de conduit nuevos con diámetro por tipo.** El diámetro es propiedad de la instancia (`RBS_CONDUIT_DIAMETER_PARAM`). El tipo solo define familia (con/sin fittings).
- **Seleccionar tipos por `ElementId`**, no por nombre, hasta resolver RE-H-005. El nombre `Tubo` es ambiguo.
- **Validar la firma de cada conduit** creado: `Servicio_Conduit` asignado, diámetro correcto, host de extremos coherente con el dispositivo.

### 6.5 Sobre la documentación

- **El plan vivo es el vault.** `PLAN_EJECUCION_v2.md` (este archivo) es el puente entre el vault y el operador. Mantener ambos sincronizados.
- **Cada sesión cierra con un `.md` en `Sesiones/`** y un append al panel. La suite de tests debe figurar en ambos.
- **Las lecciones se extraen a `50-lecciones/`**, no viven dentro de los cierres de sesión. Una lección dentro de un cierre se pierde.

---

## 7. Cómo pasarme archivos del proyecto para análisis

**Aclaración importante:** yo **no ejecuto en tu máquina Windows**. Corro en un sandbox Linux aislado, sin acceso a `D:\Work\NOTES\obsidian-vault` ni a `D:\Work\PROJECTS\RevitElectrico`. Para mí esos paths no existen. No es un problema de permisos: no hay conexión de red entre mi sandbox y tu disco.

El único mecanismo para que yo lea archivos del proyecto es **adjuntarlos al chat**. Cuando lo haces, el gateway del chat los deposita en `/home/z/my-project/upload/` dentro de mi sandbox y yo los puedo leer desde ahí.

### Tres modalidades prácticas

1. **Notas `.md` del vault**: adjuntarlas al chat directamente (como ya hiciste con las 7 de la sesión anterior). Funciona perfecto y no requiere setup.

2. **Varios archivos a la vez** (scripts `.py`, JSONs de config, tests): empaquetarlos en un `.zip` y adjuntarlos al chat. Yo los descomprimo en el sandbox y los navigo.

3. **Archivos que cambian entre sesiones**: volver a adjuntarlos. El sandbox se recicla entre mensajes y no siempre persiste lo que subiste en una sesión anterior.

### Qué adjuntar y qué no

**Sí adjuntar:**
- `.md` del vault (panel, pendientes, cierres, lecciones).
- `.py` de `src/fase-0-gobierno/`, `src/fase-1-contexto/`, `src/fase-6-revit/` (los relevantes a la sesión).
- `.json` de `config/` y `data/` (los que mencione el plan de acción).
- `tests/` con fixtures (cuando quieras que valide cobertura).
- `entregables/*.csv` recientes.
- Salida de `git log --oneline -20` pegada como texto en el chat.

**No adjuntar:**
- `.rvt`, `.ifc`, `.dwg`, `.dxf` grandes (pesan y no los puedo ejecutar/inspeccionar visualmente). Si necesito datos de ellos, pídeme un extracto JSON vía el plugin MCP.
- `node_modules/`, `__pycache__/`, `.venv/`, `.git/` (basura para el análisis).
- Backups antiguos (`*.bak`, `*_old.py`).

### Cuándo adjuntar

- **Cada vez que quieras que valide algo concreto** (un test que falla, un JSON de contrato, una sobrecarga sospechosa).
- **Antes de sesiones de colocación o ruteo**: adjuntar el script y los configs relevantes para que yo los lea antes de opinar.
- Si solo quieres decisiones de documentación, con las notas del vault basta.

---

## 8. Criterios de aceptación v2 (DoD actualizado)

Reemplaza la sección 5 del plan v1. Los `[x]` son los que ya están hechos según la evidencia del vault.

### F0 — Línea base reproducible

- [x] Hashes de los 4 documentos base en `data/baseline_hashes.json`
- [x] Veredicto E06 por `UniqueId` (RE-P-051): **0/44 instancias del lote `46c3f138-…` existen en CENTRAL-V01**
- [x] Censo V02-f: 14.331 FamilyInstances, 175 eléctricas, 147 conduits
- [x] Censo CENTRAL-V01: 130 componentes (83 equipos + 47 dispositivos)
- [x] Catálogo de familias: 33 pares familia|tipo
- [x] Decisiones D7–D15 aprobadas y registradas

### F1 — Minado del benchmark y contrato de nomenclatura

- [x] Sonda de tomas en DXF E06: 28 bloques, 0 atributos, 28 con texto cercano
- [x] Resolvedor de alturas: 47 dispositivos con `altura_local_m`, `origen_altura`, `z_absoluta_m`
- [x] Correspondencia handle ↔ ElementID: 9 filas confirmadas
- [x] Rotación horizontal de tomas: `DELTA_ROT_POR_FAMILIA = {M_Toma doble: 90}`
- [x] Inventario de 20 unidades: 901 aparatos (RE-P-064, **2026-11-17**)
- [x] Oráculo de orientación (RE-P-060, **2026-11-17**): eje real 90°/270° = DXF

### F2 — Piloto de ruteo en F01/F02

- [x] V02-f exportado por MCP (RE-P-062, **2026-11-17**): 147 conduits, 87 dispositivos
- [x] Validación de ruteo: 144 tramos válidos, 133,306 m
- [ ] **Transferencia del ruteo a CENTRAL-V01 (RE-P-066 nuevo)** ← depende de A-P1-1, A-P1-4
- [ ] Comparación con modelo manual F01/F02: posiciones, rotaciones y alturas
- [ ] Idempotencia: ejecución repetida no crea duplicados

### F6 — Modelado eléctrico 3D en Revit 2026

- [x] Conexión con Revit 2026 validada (pyRevit + MCP)
- [x] Canal MCP verificado con evidencia (TCP 8080, 23 herramientas, 8 KB, 60 s)
- [x] 8 familias cargadas (CARGAR_FAMILIAS_v01.py, 2026-10-24)
- [x] 10 combinaciones familia+símbolo mapeadas (RE_MAPEAR_FAMILIAS_RVT_v01.py)
- [x] 37 FamilyInstance modeladas en F02 Piso 5 (RE_APLICAR_MAPA_V3_REVIT_v02.py, 2026-10-24)
- [x] RED=SI asignado a 8 dispositivos (ASIGNAR_RED_v05.py, 2026-10-24)
- [x] E05 definitivo: 49/49 dispositivos con host (2026-11-09)
- [x] E06 representado en V03 sin guardar (2026-11-11): 47/47 (31 creados + 32 duplicados físicos ≤0,10 m)
- [x] E07 colocado en memoria (2026-11-16): 47/47 (39 con host, 8 de nivel) — **no guardado**
- [ ] **E07 recolocado con orientación validada y guardado** (RE-P-061) ← A-P1-5
- [ ] **Tipos de conduit creados en CENTRAL-V01** (RE-P-063) ← A-P1-6
- [ ] **Masificación a 19 unidades restantes** ← A-P3-1
- [ ] **Detección de colisiones** (RE-P-012) ← A-P3-2
- [ ] **Acometidas generales** (RE-P-013) ← A-P3-3

### Documentación

- [ ] `PLAN_EJECUCION.md` v1 archivado como histórico ← A-P0-1
- [x] `PLAN_EJECUCION_v2.md` (este archivo) creado
- [ ] `RE-00-panel.md` sincronizado con datos del 17-nov ← A-P0-2
- [ ] `RE-00-pendientes.md` con cierres del 17-nov movidos a "Cerrados" ← A-P0-3
- [ ] Lección formal de la sobrecarga equivocada F01/F02 ← A-P2-2
- [ ] Memoria "El error del script v69" marcada como superada ← A-P2-1

---

## 9. Notas técnicas (referencia rápida)

- **Python 3.12** para scripts externos (type hints, ruff, mypy).
- **IronPython 2.7** para scripts dentro de Revit (sin type hints, sin f-strings, sin requests/bs4; usar `.format()` y concatenación).
- **openpyxl 3.1.5** para exportación Excel (RE4).
- **ifcopenshell 0.8.5** para lectura IFC (RE3).
- **ezdxf 1.4.4** para lectura DXF (RE1).
- **pyRevit v7.0.0** en `C:\Users\Dario Salas\AppData\Roaming\pyRevit-Master\bin\pyrevit.exe`.
- **Revit 2026.4** (no 2027 para este proyecto).
- **MCP plugin:** `mcp-servers-for-revit.addin` en `%APPDATA%\Autodesk\Revit\Addins\2026`. TCP crudo en `localhost:8080`. Límite 8 KB. Template `Execute(Document document, object[] parameters)`.
- Las rutas usan variables de entorno o relativas al proyecto. **NUNCA hardcodear rutas absolutas de usuario.**
- Cada script nuevo requiere `test_<nombre>.py` con fixture JSON (regla global).
- **Parámetro Comments** (`ALL_MODEL_INSTANCE_COMMENTS`) para marcar `RED=SI`; **no** crear shared parameters.
- **`ElementId`** se construye con `System.Int64` para evitar ambigüedad en overloads de IronPython.
- **Trazabilidad por `UniqueId` + GUID de lote** (D12). `LevelId` es read-only.
- **Tolerancias D10:** aceptación 0,02 m; aviso 0,05 m; dedup 0,10 m.
- **Materiales de conduit:** PVC rígido al interior, SCH40 al exterior.

---

## 10. Cambios respecto a v1 (resumen ejecutivo)

| Dimensión | v1 (2026-10-24) | v2 (2026-11-18) |
|---|---|---|
| Foco de modelado | F02 Piso 5 | F01/F02 piloto de ruteo; E07 colocación |
| Inventario | 1 apartamento, 37 aparatos | 20 unidades, 901 aparatos |
| Canal de ejecución | pyRevit directo | MCP TCP 8080 (23 herramientas, 8 KB) |
| Conduit | Sin abordar | Contrato V01, 3 tipos cargados, 144 tramos V02-f |
| Orientación | Sin tratar | Oráculo resuelto (eje 90°/270° = DXF) |
| Documentación | `PLAN_EJECUCION.md` | Plan v2 + vault Obsidian estructurado |
| Tests | 42 | 427 / 2 skipped |
| Criterios DoD | Lista corta | Tres fases (F0, F1, F2, F6) con sub-ítems |
| Hallazgos | No aplicaba | 11 hallazgos con ID `RE-H-XXX` |
| Plan de acción | Implícito | 17 acciones priorizadas P0-P3 |

---

**Firma:** plan v2 redactado por Claude/Z.ai el 2026-11-18, basado en 7 notas del vault (panel, pendientes, 2 cierres, 1 avance, 1 nota MCP, 1 lección) y 3 archivos previamente cargados (`PLAN_EJECUCION.md`, memoria sesión Qwen, memoria "El error del script v69"). Pendiente de aprobación por el operador.

Una vez aprobado, los pasos inmediatos son:

1. Resolver **A-P0-1** a **A-P0-4** (operador, ~30 min).
2. Cuando quieras que valide código, contratos o tests específicos, adjuntarlos al chat (idealmente en un `.zip` si son varios). Yo los leo y redacto los diffs de `RE-00-panel.md` y `RE-00-pendientes.md` para que solo tengas que aplicarlos.
3. Sesión conjunta para **A-P1-1** (renombrar tipos `Tubo`) y **A-P1-5** (recolocar y guardar E07).
