# Runbook — Reinicio limpio de dispositivos E06 (Piso 5)

**Fecha:** 2026-11-12
**Proyecto:** RevitElectrico
**Motivo:** abandono del enfoque de parches. Se relanza la etapa de creación desde un archivo base nuevo, con un solo script correcto.

> **Importante en pyRevit:** en cada bloque de la consola, define primero el documento activo antes de ejecutar nada:
> ```python
> doc = __revit__.ActiveUIDocument.Document
> ```
> Sin esa línea, `doc` no existe y todos los scripts fallan.

---

## Por qué se reinicia

Las 20 versiones previas (v09 → v20) y el puente MCP produjeron **falsos positivos**: los JSON reportaban "44 movidos, 44 con GUID" mientras en Revit las luminarias seguían en 0.00 y el Level marcaba -13.2200.

**Causa raíz:** crear `FamilyInstance` **con host** (muro o techo) hace que Revit trate la coordenada Z como *offset relativo al host*, no como coordenada absoluta mundial. `ElementTransformUtils.MoveElement` sobre esos elementos **devuelve éxito pero no persiste** la posición, porque el elemento sigue restringido a su host.

**Regla del proyecto aplicada:**
> Los errores sirven para reconocer que debemos crear en la etapa anterior y relanzar esa etapa con las correcciones adecuadas, sin tratar de "parchear" el error encontrado.

---

## Paso 0 — Cerrar el documento actual SIN guardar

En Revit, con `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V03.rvt` abierto:

1. Verifica que el documento activo sea ese (aparece en la barra de título).
2. **File → Close** y responde **No** a "Save changes?".

Esto descarta los 44 dispositivos mal posicionados de las corridas anteriores. No se pierde nada más porque el archivo base limpio ya está creado aparte.

---

## Paso 1 — Abrir el archivo base nuevo

Abre:

```
D:\Work\PROJECTS\RevitElectrico\ArchivosBase\E06_BASE_LIMPIO_2026-11-12.rvt
```

| Dato | Valor |
|---|---|
| Origen | `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V03.0014.rvt` |
| Fecha del origen | 11/11/2026 23:26 — **anterior a todas las corridas del 12/11** |
| Tamaño | 442.408.960 bytes |
| SHA256 | `0C13A20D3466E149472CF3975FD2D2592F97C95456CA5C9FFB1F10FF9BD87116` |

Este archivo **no contiene** ninguno de los 44 dispositivos creados hoy.

---

## Paso 2 — Verificar el estado de partida (solo lectura)

Abre la consola de pyRevit y ejecuta:

```python
doc = __revit__.ActiveUIDocument.Document
exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\F6_VERIFICAR_DISPOSITIVOS_E06_v01.py").read())
```

**Resultado esperado en base limpio:**

- `elementos en ventana E06` → un número bajo (mobiliario/sanitarios si existen), **no 44**
- `con GUID del lote` → **0**
- `objetivos con Z correcta` → **0 / 44**

Si `con GUID del lote` es mayor que 0, **detente**: el archivo no es base limpio.

---

## Paso 3 — Crear los 44 dispositivos desde cero

En la misma consola de pyRevit:

```python
doc = __revit__.ActiveUIDocument.Document
exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\F6_CREAR_DISPOSITIVOS_E06_v01.py").read())
```

El script arranca automáticamente en modo real. Para simular antes sin crear nada:

```python
doc = __revit__.ActiveUIDocument.Document
crear_dispositivos_e06(doc, dry_run=True)
```

### Qué hace el script

1. **Guardia de base limpio.** Si encuentra dispositivos con el GUID del lote, **aborta** y avisa. No parchea nada.
2. **Una sola transacción.** Todo o nada: si un solo dispositivo falla, hace `RollBack` completo.
3. **Estrategia de posición en cascada**, validando la Z real después de cada intento:

| Estrategia | Llamada | Z resultante |
|---|---|---|
| **A** | `NewFamilyInstance(XYZ_absoluto, símbolo, NonStructural)` | Absoluta mundial — la correcta |
| **B** | `NewFamilyInstance(XYZ_offset, símbolo, nivel, NonStructural)` | Elevación del nivel + offset |
| **C** | `NewFamilyInstance(XYZ, símbolo, host, NonStructural)` + `MoveElement` | Último recurso |

4. **Validación obligatoria.** Lee `Location.Point.Z` real. Si difiere más de **1 cm** del objetivo, corrige con `MoveElement` dentro de la misma transacción y vuelve a leer. **Nunca reporta éxito sin verificar.**
5. **GUID del lote** asignado en la misma transacción (`46c3f138-025d-47d4-b24a-41cd21181a58`).
6. **Rotación** aplicada sobre el eje vertical, no crítica.
7. Escribe `trazabilidad_E06_piso5_v01.json` con `z_objetivo_m` **y** `z_real_m` por dispositivo.

### Salida esperada

```
 status              : OK
 creados ok          : 44
 creados + corregidos: 0
 fallidos            : 0
 con GUID            : 44
 sin GUID            : 0
```

Cada línea debe mostrar `OK` y `z_real` igual a `z_obj`:

```
 1/44 Bala Stil Led 13W   OK GUID z_obj=15.820 z_real=15.820  A_sin_host_z_absoluta
 2/44 ELEC-I-S-C1-5A      OK GUID z_obj=14.320 z_real=14.320  A_sin_host_z_absoluta
```

Si aparece `Z!` en alguna línea, esa fila tiene la Z incorrecta y el script hará `RollBack` completo.

---

## Paso 4 — Verificación independiente en Revit

### 4.1 Verificador de solo lectura

```python
doc = __revit__.ActiveUIDocument.Document
exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\F6_VERIFICAR_DISPOSITIVOS_E06_v01.py").read())
```

**Esperado:**

| Métrica | Esperado |
|---|---|
| `elementos en ventana E06` | 44 |
| `con GUID del lote` | 44 |
| `objetivos con Z correcta` | 44 / 44 |

Distribución por Z absoluta esperada:

| Z absoluta | Dispositivos | Qué son |
|---|---|---|
| 13.52 m | 7 | Comunicaciones / teléfono (+0.30) |
| 14.32 m | 22 | Tomas e interruptores (+1.10) |
| 14.42 m | 4 | Control ventilador, timbre, campana (+1.20) |
| 15.82 m | 10 | Iluminación y ventiladores (+2.60) |

> Nota: el dataset tiene 11 en 15.82 m; el verificador puede mostrar 10 o 11 según si una luminaria coincide en XY con otra.

### 4.2 Verificación visual en vista lateral

1. Abre una **Sección** o **Alzado** que corte el apartamento E06.
2. Selecciona una luminaria. En **Properties** revisa:
   - `Elevation from Level` ≈ **2.60 m**
   - `Level` = **Piso 5**
   - La cota Z debe ser **15.82 m**
3. Selecciona una toma doble. Debe marcar `Elevation from Level` ≈ **1.10 m** y Z = **14.32 m**.
4. **Ninguna luminaria debe estar a 0.00 ni con Level en -13.2200.**

Si alguna sigue en 0.00, no se toca: se reporta y se vuelve a relanzar la etapa. No se parchea.

---

## Paso 5 — Guardar como versión nueva

Solo si el Paso 4 pasa completo:

**File → Save As** →
```
D:\Work\PROJECTS\RevitElectrico\ArchivosBase\E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V04.rvt
```

No sobrescribas `E06_BASE_LIMPIO_2026-11-12.rvt`: debe quedar intacto como punto de partida reproducible.

---

## Si algo falla

| Síntoma | Significado | Acción |
|---|---|---|
| `[ABORTADO] El documento ya tiene N dispositivos...` | No es base limpio | Cerrar sin guardar, reabrir el base limpio |
| `SIN SIMBOLO (familia/tipo no existe)` | Nombre de familia o tipo cambió | Revisar el nombre exacto en el navegador de Revit y corregir el dataset |
| `[AVISO] Parámetro 'RevitElectrico_Lote' NO vinculado en: ...` | Falta vincular el parámetro compartido | Manage → Project Parameters → Add → Shared Parameter → archivo `RevitElectrico_SharedParameters.txt` |
| `status: ROLLBACK` con fallidos | Algún dispositivo no se pudo posicionar | Leer el motivo en el JSON; corregir el dataset o la familia y relanzar desde base limpio |
| Todo `OK` pero en Revit se ve en 0.00 | Revisar `z_real_m` en el JSON | Si `z_real_m` es 0.00, el reporte no miente: el problema es de la familia, no del script |

---

## Archivos de esta etapa

| Archivo | Rol |
|---|---|
| `E06_BASE_LIMPIO_2026-11-12.rvt` | Punto de partida reproducible |
| `E06_dispositivos_para_crear.json` | Dataset: 44 dispositivos con X/Y/Z y familia/símbolo |
| `F6_CREAR_DISPOSITIVOS_E06_v01.py` | Creación desde cero con validación |
| `F6_VERIFICAR_DISPOSITIVOS_E06_v01.py` | Verificación de solo lectura |
| `trazabilidad_E06_piso5_v01.json` | Resultado de la creación (se genera al ejecutar) |
| `verificacion_E06_estado_real.json` | Estado real del modelo (se genera al ejecutar) |

## Archivos obsoletos

Todo lo anterior a `v01` queda descartado y no debe ejecutarse:

`CREAR_DISPOSITIVOS_E06_FINAL_v12.py` … `v20.py`, `exportar_trazabilidad_E06_v02.py`, y los scripts MCP `mcp_e06_*.py`, `asignar_guid_e06_final.py`, `mcp_e06_final_move.py`.
