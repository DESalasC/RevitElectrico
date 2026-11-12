---
titulo: Plan de corrección de localización DXF→Revit y dispositivos faltantes
proyecto: RevitElectrico
fase: 6
fecha: 2026-11-11
version: v01
estado: propuesto
autor: AutoClaw
tags: [revit, fase-6, localizacion, dxf, dispositivos, ruteo, plan]
---

# Plan de corrección de localización DXF→Revit y dispositivos faltantes

## 1. Resumen ejecutivo

El problema **no es un offset global de coordenadas**. La transformación por ancla funciona: de los 47 dispositivos del DXF de E06, 45 tienen una instancia en Revit a **0,049 m de media y 0,118 m de máximo** con el offset `[2,3682, 9,6937] m`. Ese error es aceptable y no explica las diferencias visuales.

El problema real es la **generación de instancias**:

| Métrica E06 | Valor |
|---|---|
| INSERT del DXF | 74 (47 dispositivos + 26 marcadores de conductor + 1 panel) |
| Dispositivos físicos en el DXF | **47** |
| Instancias creadas en Revit | **95** |
| Instancias que corresponden a un dispositivo del DXF | **45** |
| Instancias sobrantes (duplicados) | **50 (53 %)** |
| Dispositivos del DXF sin instancia | **2** (`ELEC-NET-PAU` y 1 GFCI) |
| Error XY de las 45 coincidencias | media 0,049 m / máx. 0,118 m |

**Causa raíz principal:** el script de colocación no lee el inventario de INSERT del DXF. Construye la lista de dispositivos desde los **extremos de los tramos** del JSON de ruteo (`tramos[].extremos`). Cada extremo de polilínea genera una instancia, y varias polilíneas convergen en el mismo aparato con pequeñas diferencias de coordenadas. Resultado: un aparato físico se convierte en 2–7 instancias, y los aparatos que no tienen tubería dibujada nunca se crean.

A eso se suman cuatro defectos que también producen diferencias visibles:

1. **Deduplicación por coordenada exacta** (redondeo a 4 decimales) en lugar de por `handle` del INSERT o por proximidad física.
2. **Proyección a la cara del muro más cercano** con radio de 5 m: si el muro más cercano no es el muro correcto, el aparato se desplaza a otra pared.
3. **Rotación ignorada:** todos los aparatos de muro se crean con `dir_ref = XYZ(0,0,1)`. El DXF tiene rotaciones 0°, 90°, 180°, 270° y 328,7°, que no se reproducen.
4. **Techo único y cota fija:** todas las luminarias se fuerzan al techo `2766255` ya 2,60 m locales, sin verificar que ese techo cubra el recinto.

Además, el insumo DXF de E06 tiene **8 pares de INSERT del mismo bloque a menos de 0,20 m** (la mayoría a 0,14 m). Hay que decidir con el operador si son duplicados de dibujo o aparatos reales antes de normalizar.

## 2. Evidencia medida (2026-11-11)

Archivo de evidencia generado: `data/auditoria_localizacion_E06_v01.json`.

### 2.1 Insumo DXF

`ArchivosBase/Apartamento Tipo E 06.dxf`:

- 74 INSERT en total.
- 26 marcadores de conductor (`1FTN`, `2FT2N`, `1FTR`, `1FTN2R`, `1FTNR`, `1TNR`, `2F2N1T1R`).
- 1 `TB-Panel` (ancla, no se modela como dispositivo).
- **47 dispositivos eléctricos**.

### 2.2 Comparación por tipo

| Tipo DXF | En DXF | Colocados en Revit | Emparejados | Sobrantes | Faltantes |
|---|---:|---:|---:|---:|---:|
| `ELEC-T-D-t-15A` | 10 | 20 | 10 | 10 | 0 |
| `ELEC-TEL` | 10 | 21 | 10 | 11 | 0 |
| `ELEC-T-GFCI-t-15A` | 5 | 8 | 4 | 4 | 1 |
| `Bala Stil Led 13W` | 4 | 9 | 4 | 5 | 0 |
| `ELEC-I-S-1-5A` | 3 | 4 | 3 | 1 | 0 |
| `Bala Stil Led 10W` | 3 | 8 | 3 | 5 | 0 |
| `ELEC-I-S-C1-5A` | 2 | 4 | 2 | 2 | 0 |
| `ELEC-F-VENT` | 2 | 2 | 2 | 0 | 0 |
| `Bala Stil Led 22W` | 2 | 8 | 2 | 6 | 0 |
| `ELEC-F-CONTROL` | 2 | 6 | 2 | 4 | 0 |
| `ELEC-TIMBRE` | 1 | 1 | 1 | 0 | 0 |
| `ELEC-NET-PAU` | 1 | 0 | 0 | 0 | 1 |
| `S3` | 1 | 2 | 1 | 1 | 0 |
| `ELEC-CAMPANA` | 1 | 2 | 1 | 1 | 0 |
| **Total** | **47** | **95** | **45** | **50** | **2** |

### 2.3 Duplicados geométricos

Al agrupar las 95 instancias por tipo y proximidad de 0,25 m se obtienen **43 posiciones físicas**, no 95. Ejemplos:

- `ELEC-TEL`: 7 instancias en un radio de 0,18 × 0,26 m.
- `ELEC-TEL`: 5 instancias en 0,05 × 0,25 m.
- `ELEC-T-D-t-15A`: 5 instancias en 0,11 × 0,30 m.
- `Bala Stil Led 22W`: 4 instancias en 0,40 × 0,00 m.

### 2.4 Avisos de host

Los 6 IDs reportados por el cierre de sesión (7 avisos) son todos tomas/GFCI en el borde sur del apartamento, colocados por `face`:

`5689753`, `5689774`, `5689777`, `5689822`, `5689871`, `5689881`.

La causa es que el punto nominal no cae sobre la cara del muro elegido; el API lo proyecta y emite “Instance origin does not lie on host face”.

### 2.5 Rotaciones del DXF

| Rotación | Cantidad |
|---|---:|
| 0° | 14 |
| 90° | 13 |
| 180° | 8 |
| 270° | 10 |
| 328,7° | 2 |

Ninguna se aplica en Revit: todas las instancias de muro usan la misma dirección de referencia.

### 2.6 Estado documental (crítico)

- Documento activo: `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V03.rvt`.
- Última modificación en disco: **2026-11-10 20:52**.
- Colocación de E06: **2026-11-11 20:05** (95 dispositivos).
- Conduits de E06: **2026-11-10 21:31 y 22:51** (165 conduits, dos corridas).

**Nada de E06 está guardado en disco.** La sesión de Revit tiene 95 dispositivos duplicados y 165 conduits que no existen en el `.rvt`. Antes de cualquier corrección hay que decidir si se guarda, se descarta o se reconstruye.

## 3. Diagnóstico causal

### 3.1 Traducción de lo que ve el operador

| Síntoma visual (DXF vs Revit) | Causa |
|---|---|
| Hay más aparatos en Revit que en el plano | Duplicados por extremos de polilínea (50 sobrantes en E06) |
| Faltan tomas de datos / red | Dispositivos sin tubería dibujada nunca se crean (`ELEC-NET-PAU`) |
| Placas giradas respecto al plano | Rotación del bloque DXF ignorada |
| Aparatos en una pared que no es | Proyección al muro más cercano con radio de 5 m |
| Luminarias corridas o fuera del recinto | Techo único y cota fija 2,60 m |
| Aparatos “flotando” o despegados del muro | Aviso de host face y proyección fuera de cara |

### 3.2 Causas técnicas

| ID | Causa | Evidencia | Efecto visible |
|---|---|---|---|
| C1 | La lista de dispositivos sale de `tramos[].extremos`, no de los INSERT del DXF | 95 instancias para 47 aparatos | Duplicados y faltantes |
| C2 | Deduplicación por `(nombre, x, y, altura)` con redondeo 1e-4 | 25 grupos con duplicados; un `ELEC-TEL` con 7 copias | Aparatos repetidos y warnings “identical instances in the same place” |
| C3 | Proyección a cara de muro con búsqueda de 5 m | 7 avisos de host; desplazamientos >1 m en casos puntuales | Aparatos en la pared equivocada |
| C4 | Rotación del bloque DXF no se lee ni se aplica | 33 de 47 INSERT tienen rotación ≠ 0° | Placas giradas respecto al plano |
| C5 | Techo único `2766255` y cota fija 2,60 m | 27 luminarias al mismo techo | Luminarias fuera de recinto o a cota incorrecta |
| C6 | Insumo con pares a 0,14 m y bloques sin altura | 8 pares <0,20 m | Duplicados heredados del DXF |
| C7 | Sin baseline guardado | V03 en disco es anterior a E06 | Imposible comparar contra un estado limpio |

## 4. Objetivo y criterio de aceptación

**Objetivo:** dejar el apartamento piloto E06 en un estado “listo para ruteo”: un dispositivo de Revit por cada dispositivo físico del DXF, en la posición, cota, orientación y host correctos, sin sobrantes ni faltantes.

Criterios de aceptación (V8 reforzado):

| # | Criterio | Umbral |
|---|---|---|
| A1 | Cobertura | 100 % de los dispositivos canónicos del DXF con exactamente 1 instancia |
| A2 | Sobrantes | 0 instancias sobrantes dentro del polígono del apartamento |
| A3 | XY nominal | ≤ 0,02 m respecto de `INSERT + offset` antes del hosteo |
| A4 | XY final | ≤ 0,10 m respecto de la posición canónica, con desplazamiento solo perpendicular al muro |
| A5 | Z | igual a la tabla de alturas aprobada; techo ±0,02 m de la cara real |
| A6 | Rotación | ±2° respecto de la rotación del bloque DXF |
| A7 | Host | `Host` no nulo y categoría correcta (`Walls` / `Ceilings`) |
| A8 | Avisos | 0 “Instance origin does not lie on host face” |
| A9 | Sustrato | 100 % de los recintos del apartamento con muro perimetral y techo detectados |
| A10 | Informe | diff HTML/JSON con 100 % emparejado y firmado por el operador |
| A11 | Documento | `.rvt` guardado como V04 + commit + nota de vault |

## 5. Plan por fases

### F0 — Baseline y decisión sobre la sesión abierta (0,5 día)

1. Inventariar qué hay sin guardar en la sesión de Revit (E06 dispositivos + conduits).
2. Decidir con el operador una de tres rutas:
   - **A. Guardar como V04-WIP** y limpiar después (conserva todo, pero fija los errores en disco).
   - **B. Cerrar sin guardar E06**, reabrir V03 y reconstruir E06 desde el inventario canónico (**recomendada** si no hay otro trabajo sin guardar).
   - **C. Guardar V04-WIP**, borrar programáticamente todos los dispositivos y conduits de E06 y reconstruir.
3. Congelar F01 y F02 como intocables (verificación por polígono, no solo por rango).
4. Exportar posiciones actuales con `RE_EXPORTAR_POSICIONES_REVIT_v01.py` como línea base.
5. Crear rama/worktree y commit de respaldo.

**Salida:** decisión registrada + export de posiciones + baseline congelado.

### F1 — Inventario canónico del DXF (1–2 días)

Script nuevo: `src/fase-6-revit/RE_INVENTARIO_DISPOSITIVOS_v01.py` (Python 3, ezdxf).

Debe:

- Leer el DXF del apartamento (no el plano general).
- Clasificar INSERT en: dispositivo, marcador de conductor, panel/ancla, descartar.
- Extraer por dispositivo: `handle`, bloque, capa, `x`, `y`, `z` (si existe), rotación, atributos, altura de la tabla de equivalencias.
- Normalizar duplicados:
  - deduplicar por `handle`;
  - agrupar por proximidad ≤ 0,10 m y reportar como “candidato a duplicado”;
  - nunca colapsar automáticamente pares a 0,14 m sin decisión del operador.
- Calcular la envolvente del apartamento y excluir el panel ancla.
- Emitir `data/inventario_dispositivos_E06_v01.json` + reporte HTML.

**Salida:** inventario canónico + lista de decisiones de insumo (8 pares de E06).

### F2 — Auditoría de Revit y diff (1–2 días)

Dos piezas:

1. `src/fase-6-revit/RE_AUDITAR_DISPOSITIVOS_v01.py` (pyRevit/IronPython 2.7):
   - exporta toda `FamilyInstance` dentro del polígono del apartamento;
   - `ElementId`, familia, símbolo, XYZ en pies y metros, `Host` y categoría, `FacingOrientation`, `HandOrientation`, nivel, `Comments` / `Servicio_Conduit`;
   - no usa `str(ElementId)` para reconstruir IDs (lección RE-2026-11-09).
2. `src/fase-6-revit/RE_COMPARAR_INVENTARIO_v01.py` (Python 3):
   - empareja inventario canónico vs export de Revit por tipo y distancia (greedy o Hungarian);
   - clasifica: `OK`, `DUPLICADO`, `FALTANTE`, `DESPLAZADO`, `ROTADO`, `HOST_INCORRECTO`, `TIPO_INCORRECTO`;
   - emite JSON + HTML con tabla y croquis.

**Salida:** diff completo de E06 (y reutilizable para E05 y el resto).

#### F2.1 — Auditoría del sustrato (muros y techos)

Antes de corregir dispositivos hay que verificar que el modelo arquitectónico del apartamento esté completo, porque el hosteo depende de él:

- contar muros del nivel `Piso 5` dentro de la envolvente del apartamento y detectar vanos o faltantes;
- verificar que cada recinto tenga techo (no confiar en un único `ElementId`);
- detectar muros duplicados o solapados que puedan capturar el hosteo;
- reportar recintos sin techo o sin muro perimetral.

**Salida:** `data/auditoria_sustrato_E06_v01.json` + lista de huecos arquitectónicos a corregir antes de F3.

### F3 — Motor de corrección (2–3 días)

Script nuevo: `src/fase-6-revit/RE_CORREGIR_DISPOSITIVOS_v01.py` (pyRevit).

Modos: `dry_run=True` obligatorio, luego `False` con aprobación explícita.

Acciones por registro:

- **DUPLICADO:** conservar la instancia más cercana al canónico; borrar las demás. Nunca tocar F01/F02.
- **FALTANTE:** crear con `Face` del muro/techo correcto, punto proyectado, rotación del DXF y altura de la tabla.
- **DESPLAZADO:** si el error > A4, mover con `ElementTransformUtils.MoveElement` (solo XY) o recrear si el host es incorrecto.
- **ROTADO:** recrear o ajustar orientación; no dejar placas giradas.
- **HOST_INCORRECTO:** borrar y recrear sobre el host correcto.
- **TIPO_INCORRECTO:** borrar y recrear con la familia/símbolo del mapa.

Reglas de seguridad:

- Transacción única por apartamento, con checkpoint antes y después.
- Exclusión explícita de F01/F02 y del panel ancla.
- No tocar conduits existentes; se recrean después.
- Reporte por elemento: `element_id`, acción, antes/después, motivo.

**Salida:** modelo corregido + reporte de acciones.

### F4 — Validación y gate visual (1 día)

1. Re-exportar posiciones y correr el diff de F2.
2. Verificar A1–A8.
3. Generar overlay DXF vs Revit (planta) y visor 3D de dispositivos.
4. El operador compara visualmente y firma el gate.

**Salida:** informe de aceptación firmado.

### F5 — Baseline y congelamiento (0,5 día)

1. Guardar como `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V04.rvt`.
2. Commit + tag `e06-localizacion-ok`.
3. Actualizar `config/equivalencias_dxf_revit_v02.json` con las alturas y rotaciones aprobadas.
4. Registrar en el vault y en el backlog.

### F6 — Ruteo de conduit (1–2 días)

Solo después de F5:

1. Regenerar el ruteo de E06 con el inventario canónico (no con los extremos del JSON anterior).
2. Validar V1–V8 del esquema de ruteo.
3. Decidir el destino de los 165 conduits actuales: borrar y recrear (recomendado) o conservar como referencia.
4. `dry_run=True` del writer → revisión → `dry_run=False`.
5. Validaciones post-creación V9 (colisiones) y V10 (`Servicio_Conduit` poblado).

## 6. Decisiones que requieren al operador

| ID | Decisión | Opciones | Recomendación |
|---|---|---|---|
| D0 | Qué hacer con la sesión de Revit sin guardar | A guardar WIP / B descartar E06 / C guardar y limpiar | **B** si no hay otro trabajo sin guardar |
| D1 | Pares del DXF a 0,14 m | duplicados de dibujo / aparatos reales / revisar caso por caso | Revisar los 8 pares con el operador |
| D2 | Alturas | tabla por tipo / atributo del DXF cuando exista | Tabla por tipo, con override por atributo |
| D3 | Rotación | rotación del bloque DXF / normal al muro | **Rotación del bloque** (es lo dibujado) |
| D4 | Tolerancia XY final | 0,10 m / 0,20 m (regla G9 actual) | **0,10 m** para dispositivos |
| D5 | Conduits E06 actuales | borrar y recrear / conservar | **Borrar y recrear** tras el baseline |
| D6 | Alcance inmediato | solo E06 / E06 + E05 / todos | **E06 piloto**, luego E05 y el resto |

## 7. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Guardar la sesión con los 95 duplicados | Alto | F0 decide antes de tocar nada; V04-WIP separado |
| Borrar instancias de F01/F02 | Alto | Exclusión por polígono + lista de IDs intocables + dry_run |
| El muro “más cercano” sigue siendo el equivocado | Alto | Selección por lado del punto y recinto; validación visual |
| Duplicados del DXF sin resolver | Medio | F1 se bloquea hasta la decisión D1 |
| Revit inestable | Medio | Transacciones, checkpoints, un apartamento por corrida |
| Comparar contra JSON viejo | Alto | La verdad es el export del RVT, no el JSON de ruteo |
| Perder trabajo por no guardar | Medio | Guardar V04-WIP antes de cualquier experimento |

## 8. Entregables

- `src/fase-6-revit/RE_INVENTARIO_DISPOSITIVOS_v01.py` + test.
- `src/fase-6-revit/RE_AUDITAR_DISPOSITIVOS_v01.py` + test.
- `src/fase-6-revit/RE_COMPARAR_INVENTARIO_v01.py` + test.
- `src/fase-6-revit/RE_CORREGIR_DISPOSITIVOS_v01.py` + test.
- `data/inventario_dispositivos_E06_v01.json`.
- `data/auditoria_localizacion_E06_v01.json` (ya generado).
- `data/diff_dispositivos_E06_v01.html`.
- `ArchivosBase/E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V04.rvt`.
- Nota de vault y backlog actualizados.

## 9. Cronograma estimado

| Fase | Días |
|---|---:|
| F0 | 0,5 |
| F1 | 1–2 |
| F2 | 1–2 |
| F3 | 2–3 |
| F4 | 1 |
| F5 | 0,5 |
| F6 | 1–2 |
| **Total E06** | **7–11 días** |

Cada apartamento adicional: 1–2 días una vez estabilizado el pipeline.

## 10. Primer paso inmediato

1. Confirmar D0 (sesión abierta) y D1 (pares del DXF).
2. Guardar o descartar la sesión según D0.
3. Exportar posiciones actuales y congelar baseline.
4. Implementar F1 (`RE_INVENTARIO_DISPOSITIVOS_v01.py`) y correrlo sobre E06.

No se debe crear ni borrar nada en Revit antes de completar F0 y F1.
