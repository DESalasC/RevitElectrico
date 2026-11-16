# Plan de Ejecución — Proyecto RevitElectrico

**Ubicación:** `D:\Work\PROJECTS\RevitElectrico\PLAN_EJECUCION.md`  
**Fecha:** 2026-10-24  
**Estado:** En ejecución (Fase 6 parcialmente completada)  
**Responsable:** Claude Code (asistente de desarrollo)

---

## 1. Contexto y alcance

El proyecto **RevitElectrico** es independiente de `DiseñoParametrico`. Su objetivo es llevar la información eléctrica 2D (comunicaciones, circuitos, cableado, paneles, dispositivos, conexiones, servicios) de planos DWG/DXF a un modelo Revit 2026 3D para validación de interferencias y coordinación interna.

**Alcance aprobado:**
- Representación 3D únicamente (dispositivos + conductos).
- **Sin** cálculos RETIE/NTC 2050 (ya están en 2D, no se recalculan aquí).
- **Sin** unifilar.
- **Sin** POT/.gpkg (Santa Marta, no Bogotá).
- **Revit 2026** confirmado instalado y activo (ruta: `C:\Program Files\Autodesk\Revit 2026\`). Revit 2027 también está instalado en la estación pero no es la versión del proyecto.
- Documento abierto en Revit: `STM-FJR-TORRE5-A-M3-R23-P01-CENTRA-prueba 01.rvt` (en `3.-Proceso\`).
- Chip por defecto: `SANTAMARTA_T5`.
- Offsets de rebase: X = -991.903, Y = -1714.822 (llevar a 0,0).
- **DXF fuente real:** `D:\Work\PROJECTS\RevitElectrico\3.-Proceso\STM-T4-P4_todos_bloques_electricos.dxf` (bloque piloto Apartamento Tipo F 02, piso 5). El edificio completo incluye 19 pisos y sótanos adicionales.

---

## 2. Estado actual de la implementación

### Fase A — Ejecutable hoy (sin Revit activo) ✅ COMPLETADA

| Script | Estado | Tests | Descripción |
|--------|--------|-------|-------------|
| `RE1_NORMALIZA_DXF_v01.py` | ✅ Creado | 5 pass | Lee DXF, reubica coordenadas a (0,0), filtra bloques basura, mapea bloques a familias Revit, salida JSON |
| `RE2_MAPEO_BLOQUES_v01.py` | ✅ Creado | 7 pass | Mapea nombres de bloques DXF a familias Revit 2026 (categoría, altura, modelar, código conductores) |
| `RE3_LECTURA_IFC_v01.py` | ✅ Creado | 5 pass | Lee IFC con ifcopenshell, extrae elementos, cantidades, Qto sets, resumen por tipo |
| `RE4_EXPORT_EXCEL_v01.py` | ✅ Creado | 6 pass | Exporta JSON de RE1/RE2/RE3 a Excel (hojas Resumen, DXF_Bloques, DXF_Mapeo, DXF_Geometria, IFC_Elementos, IFC_Resumen) |

**Total tests: 23 passed.**

### Fase 6 — Modelado eléctrico 3D en Revit 2026 🔄 EN EJECUCIÓN

**Documento abierto:** `STM-FJR-TORRE5-A-M3-R23-P01-CENTRA-prueba 01.rvt` (en `3.-Proceso\`), Revit 2026 (PID 4608).

| Script | Estado | Tests | Descripción |
|--------|--------|-------|-------------|
| `REVIT_CONEXION_VALIDA_v01.py` | ✅ Validado | — | Conexión directa con Revit 2026 vía pyRevit. |
| `CARGAR_FAMILIAS_v01.py` | ✅ Ejecutado | 5 pass | Carga 8 familias .rfa por defecto (7 exitosas, 1 omitida: M_Toma doble ya cargada). |
| `RE_MAPEAR_FAMILIAS_RVT_v01.py` | ✅ Ejecutado | 9 pass | Mapea 10 combinaciones familia+simbolo a nombres reales del RVT (3 ya_existia_activo, 3 se_activo, 4 no_disponible). |
| `RE_APLICAR_MAPA_V3_REVIT_v02.py` | ✅ Ejecutado | 14 pass | Crea 37 FamilyInstance en Revit (Apartamento Tipo F 02, Piso 5) con host fallback techo→muro. |
| `VERIFICAR_INSTANCIAS_REVIT_v02.py` | ✅ Listo | — | Verifica 37 FamilyInstance esperadas (IDs 5554235-5554271) en el documento. |
| `ASIGNAR_RED_v05.py` | ✅ Ejecutado | 11 pass | Asigna RED=SI al parametro Comments de dispositivos de red (capa ELEC-APPL-NETWORD) buscando por posicion XYZ (tolerancia 0.02 m). No depende de ElementIds fijos. Ejecutado 2026-10-24: 8 dispositivos marcados en E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V01. |
| `ASIGNAR_NIVEL_FALTANTES_v05.py` | ✅ Listo + Tests (corregido 2026-10-24) | 15 pass | Asigna nivel "Piso 5" a FamilyInstance sin nivel buscando por posicion XYZ (tolerancia 0.02 m). No depende de ElementIds fijos. Escalable a otros pisos/bloques. Corregido: `_obtener_root_proyecto()` con `__file__` fallback, busqueda de niveles con fallback `OST_Levels`, `BuiltInParameter` directo. |
| `CREAR_TIPOS_CONDUIT_v04.py` | ✅ Listo + Tests (corregido 2026-10-24) | 9 pass | Crea 5 tipos de conduit por diametro de cable (3-4mm→3/4", 5-6mm→1", 7-8mm→1-1/4", 9-11mm→2", 12-15mm→3"). Corregido: elimina `ConduitType`/`Conduit`/`Structure` (error `expected ElementId, got ConduitType`), duplica tipos existentes (`ConduitType` o `FamilySymbol` de `OST_Conduit`) y establece `RBS_CONDUIT_DIAMETER_PARAM`. Ruta resuelta contra `REVITELECTRICO_ROOT` con `__file__` fallback. |
| `DIAGNOSTICAR_VISIBILIDAD_v01.py` | ✅ Listo (corregido 2026-10-24) | — | Diagnostica FamilyInstance del documento (nivel, face-based, posicion, categoria). Para entender por qué los componentes no se ven en el Apartamento Tipo F 02. Corregido: `_obtener_root_proyecto()` con `__file__` fallback, 4 estrategias de busqueda de niveles, funcion `_to_unicode()` para evitar `UnicodeDecodeError` al guardar JSON con caracteres acentuados. |
| `RECREAR_FALTANTES_v02.py` | ✅ Listo | — | Recrea FamilyInstance faltantes (5554243-5554248, 5554250, 5554261) con nivel Piso 5. |

**Limpieza realizada (2026-10-24):**
- Eliminados 12 scripts duplicados/corruptos (v01-v03 de ASIGNAR_RED, ASIGNAR_NIVEL_FALTANTES, CREAR_TIPOS_CONDUIT, RECREAR_FALTANTES, VERIFICAR_INSTANCIAS_REVIT; RECREAR_PISO5_v02 corrupto).
- Eliminado test roto `test_RE_APLICAR_MAPA_V3_REVIT_v01.py` (referenciaba script inexistente `_v01.py`). Se conserva `test_RE_APLICAR_MAPA_V3_REVIT_v02.py`.

**Pasos pendientes de ejecución en Revit 2026 (PID 25168):**
1. Ejecutar `DIAGNOSTICAR_VISIBILIDAD_v01.py` — `diagnosticar_visibilidad(doc, json_out="data\\diagnostico_visibilidad_v01.json")` para entender por qué los componentes no se ven en el Apartamento Tipo F 02.
2. Ejecutar `ASIGNAR_NIVEL_FALTANTES_v05.py` — `asignar_nivel_faltantes(doc, reporte_json="data\\apto_F_02_aplicar_mapa_v3.json", json_out="data\\asignar_nivel_faltantes_v05_resultado.json", nivel_destino="Piso 5")`
3. Ejecutar `CREAR_TIPOS_CONDUIT_v04.py` — `crear_tipos_conduit(doc)`
4. Ejecutar `VERIFICAR_INSTANCIAS_REVIT_v02.py` — `verificar_instancias_revit(doc)` para confirmar 37 instancias

> **Nota sobre dispositivos face-based (techo):** los 10 candidatos en `apto_F_02_aplicar_mapa_v3.json` son dispositivos de techo (`anfitrion == "ceiling"`). Como son face-based, su `LevelId` es read-only y no se les puede asignar nivel — es comportamiento esperado de Revit. `ASIGNAR_NIVEL_FALTANTES_v05.py` los marca como `face_based_skip` y no falla.

**Pendiente tras Fase 6:**
- Modelado de los 20 bloques restantes del apartamento (además de los 37 ya modelados).
- Detección de colisiones (`CLASH_DETECTION_v01.py` listo).

---

## 3. Estructura de directorios

```
D:\Work\PROJECTS\RevitElectrico\
├── 2.-Entradas\           # DWG, RVT, DXF, diagnóstico, plan Council CAD→Revit
├── 3.-Proceso\            # Scripts Python, Dynamo, JSON de extracción, .rvt de prueba
├── 4.-Salidas\            # Resultados generados (Excel, JSON, IFC intermedio)
├── config\                # Configuraciones (field-whitelist, mapeos)
├── data\                  # Datos intermedios (JSON de RE1/RE2/RE3, IFC)
├── exports\               # Reportes Excel de RE4
├── src\
│   └── fase-1-contexto\   # RE1, RE2, RE3, RE4 (Python 3.12 standalone)
│   └── fase-6-revit\      # Scripts pyRevit para Revit 2026
├── tests\
│   └── fase-1-contexto\   # test_RE1..RE4 + fixtures JSON
├── CLAUDE.md              # Reglas específicas del proyecto
└── PLAN_EJECUCION.md      # Este archivo
```

---

## 4. Flujo de ejecución end-to-end

### Paso 1 — Normalizar DXF (RE1)
```powershell
python src\fase-1-contexto\RE1_NORMALIZA_DXF_v01.py `
  --dxf-in "3.-Proceso\STM-T4-P4_todos_bloques_electricos.dxf" `
  --json-out "data\SANTAMARTA_T5_dxf.json" `
  --chip SANTAMARTA_T5
```

### Paso 2 — Mapear bloques a familias Revit (RE2)
```powershell
python src\fase-1-contexto\RE2_MAPEO_BLOQUES_v01.py `
  --json-in "data\SANTAMARTA_T5_dxf.json" `
  --json-out "data\SANTAMARTA_T5_mapeo.json" `
  --chip SANTAMARTA_T5
```

### Paso 3 — Leer IFC (RE3) — si existe modelo exportado de Revit
```powershell
python src\fase-1-contexto\RE3_LECTURA_IFC_v01.py `
  --ifc "3.-Proceso\modelo_prueba.ifc" `
  --json-out "data\SANTAMARTA_T5_ifc.json" `
  --chip SANTAMARTA_T5
```

### Paso 4 — Exportar a Excel (RE4)
```powershell
python src\fase-1-contexto\RE4_EXPORT_EXCEL_v01.py `
  --json-re1 "data\SANTAMARTA_T5_dxf.json" `
  --json-re2 "data\SANTAMARTA_T5_mapeo.json" `
  --json-ifc "data\SANTAMARTA_T5_ifc.json" `
  --xlsx-out "4.-Salidas\SANTAMARTA_T5_reporte.xlsx" `
  --chip SANTAMARTA_T5
```

### Paso 5 — Validar conexión con Revit (pyRevit, Fase 6)
Requiere Revit 2026 abierto con un modelo cargado. Estado actual: conexión validada, pero `app.Documents` no devolvió documento accesible en el contexto de `pyrevit run`.
```powershell
pyrevit run "src\fase-6-revit\REVIT_CONEXION_VALIDA_v01.py"
```

### Paso 6 — Importar DXF a Revit y modelar 3D eléctrico
Vía Dynamo / BimorphNodes (piloto 1 plano), asignación manual de circuitos/panel.

---

## 5. Criterios de aceptación (Definition of Done)

- [x] Fase 1: DXF normalizado al origen (0,0), bloques basura filtrados, mapeo documentado en JSON.
- [x] Fase 2: JSON de mapeo bloques→Revit generado, con al menos 1 bloque eléctrico mapeado.
- [x] Fase 3: Lectura IFC funciona; extrae elementos, cantidades y Qto sets.
- [x] Fase 4: Excel generado con hojas Resumen, DXF_Bloques, DXF_Mapeo, DXF_Geometria, IFC_Elementos, IFC_Resumen.
- [x] Tests fase-1-contexto: 23 passed (pytest tests/fase-1-contexto/).
- [x] Fase 6: Conexión con Revit 2026 validada (pyRevit).
- [x] Fase 6: 8 familias cargadas (CARGAR_FAMILIAS_v01.py).
- [x] Fase 6: 10 combinaciones familia+simbolo mapeadas (RE_MAPEAR_FAMILIAS_RVT_v01.py).
- [x] Fase 6: 37 FamilyInstance modeladas (Apartamento Tipo F 02, Piso 5) (RE_APLICAR_MAPA_V3_REVIT_v02.py).
- [x] Fase 6: Tests fase-6-revit: 42 passed (pytest tests/fase-6-revit/).
- [x] Fase 6: Ejecutar ASIGNAR_RED_v05.py — asignar RED=SI a dispositivos de red (capa ELEC-APPL-NETWORD) en Revit 2026. (Completado 2026-10-24: 8 dispositivos marcados)
- [ ] Fase 6: Ejecutar ASIGNAR_NIVEL_FALTANTES_v05.py — asignar Piso 5 a FamilyInstance sin nivel (pendiente: 1 face-based skip, 9 no encontrados por posicion; requiere diagnostico DIAGNOSTICAR_VISIBILIDAD_v01.py).
- [ ] Fase 6: Ejecutar CREAR_TIPOS_CONDUIT_v04.py — crear 5 tipos de conduit.
- [ ] Fase 6: Ejecutar VERIFICAR_INSTANCIAS_REVIT_v02.py — confirmar 37 instancias.
- [ ] Fase 6: Modelar los 20 bloques restantes del apartamento.
- [ ] Fase 6: Detección de colisiones (CLASH_DETECTION_v01.py).
- [ ] Documentación: CLAUDE.md del proyecto actualizado.

---

## 6. Comandos disponibles

```powershell
# Variables de entorno
echo $env:REVITELECTRICO_ROOT

# Ejecutar todos los tests
cd $env:REVITELECTRICO_ROOT
pytest tests/fase-1-contexto/ -v
pytest tests/fase-6-revit/ -v

# Ejecutar un script individual (ejemplo RE4)
python src\fase-1-contexto\RE4_EXPORT_EXCEL_v01.py --json-re1 data\*.json --json-re2 data\*.json --xlsx-out 4.-Salidas\reporte.xlsx --chip SANTAMARTA_T5

# Validar conexión con Revit (requiere Revit 2026 abierto)
pyrevit run "src\fase-6-revit\REVIT_CONEXION_VALIDA_v01.py"

# Scripts de Fase 6 (ejecutar desde pyRevit Python Shell dentro de Revit 2026):
#   exec(open(r"...\src\fase-6-revit\ASIGNAR_RED_v05.py").read())
#   asignar_red(doc, reporte_json="data\\apto_F_02_aplicar_mapa_v3.json", json_out="data\\asignar_red_v05_resultado.json")
#   exec(open(r"...\src\fase-6-revit\ASIGNAR_NIVEL_FALTANTES_v05.py").read())
#   asignar_nivel_faltantes(doc, reporte_json="data\\apto_F_02_aplicar_mapa_v3.json", json_out="data\\asignar_nivel_faltantes_v05_resultado.json")
#   exec(open(r"...\src\fase-6-revit\CREAR_TIPOS_CONDUIT_v04.py").read())
#   crear_tipos_conduit(doc)
#   exec(open(r"...\src\fase-6-revit\VERIFICAR_INSTANCIAS_REVIT_v02.py").read())
#   verificar_instancias_revit(doc)

# Verificar procesos de Revit
Get-Process -Name 'Revit*' | Select-Object Name, Id, CPU, WorkingSet
```

---

## 7. Notas técnicas

- **Python 3.12** para scripts externos (type hints, ruff, mypy).
- **IronPython 2.7** para scripts dentro de Revit (sin type hints, sin f-strings, sin requests/bs4; usar .format() y concatenación).
- **openpyxl 3.1.5** para exportación Excel (RE4).
- **ifcopenshell 0.8.5** para lectura IFC (RE3).
- **ezdxf 1.4.4** para lectura DXF (RE1).
- **pyRevit v7.0.0** instalado en `C:\Users\Dario Salas\AppData\Roaming\pyRevit-Master\bin\pyrevit.exe`.
- **Revit 2026** confirmado instalado y activo (no Revit 2027 para este proyecto). Conexión vía pyRevit validada; documento abierto en Revit 2026 (PID 4608).
- **pyRevit Python Shell** es el entorno de ejecución para scripts de Fase 6 (usar `exec(open(...).read())` y llamar a la función principal).
- Las rutas usan variables de entorno o relativas al proyecto. **NUNCA hardcodear rutas absolutas de usuario.**
- Cada script nuevo requiere `test_<nombre>.py` con fixture JSON (regla global).
- **Parámetro Comments** (`ALL_MODEL_INSTANCE_COMMENTS`) se usa para marcar RED=SI, no se crean shared parameters.
- **ElementId** se construye con `System.Int64` para evitar ambigüedad en overloads de IronPython.

