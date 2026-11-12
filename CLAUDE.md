# CLAUDE.md — Proyecto RevitElectrico (T5-SantaMarta)

## Identidad del sistema

Proyecto independiente **RevitElectrico** (Santa Marta Torre 5 — Plantas Eléctricas).
Directorio de trabajo: `D:\Work\PROJECTS\RevitElectrico\`.

Objetivo: llevar la información eléctrica 2D (comunicaciones, circuitos, cableado, paneles, aparatos, acometidas) de los planos DWG/DXF a un modelo eléctrico 3D en Revit 2026, para validación de interferencias y coordinación interna.

**Estado Fase 6 (2026-10-24 — desarrollo desde cero sobre V00):**
- Documento origen: `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V00.rvt` (vacío, plantilla Electrical MEP métrica, niveles adecuados, referencia DXF en "Piso 5").
- Nivel "Piso 5": elevación 43.3727 m (confirmado en V00).
- 0 FamilyInstance modeladas (desde cero, sin arrastrar errores previos).
- 0 conduits creados (desde cero).
- Familias y conduits: cargados en V00 (confirmado por el operador).
- Rango de modelado inicial: N 0,00–17,70 / E –11,50 a 14,20 + zonas centrales (195 dispositivos en `data\dispositivos_rango_este_central.json`).
- Reglas de datum aplicadas desde el principio: `Z_absoluta = nivel.Elevation + altura_local` (nunca `z_revit` como Z absoluta); cada `FamilyInstance` con `LevelId` válido; tomas y luminarias con circuito asignado.
- Scripts listos para adaptar/crear: modelado desde cero (nuevo), `CREAR_TIPOS_CONDUIT_v04.py`, `ASIGNAR_RED_v05.py`, `CLASH_DETECTION_v01.py`, `DIAGNOSTICO_ESTADO_MODELO_v01.py`, `F6_VERIFICAR_INVARIANTS_v01.py`.

## Gobierno documental y rutas (Fase 0)

- **Raíz de desarrollo (única):** `D:\Work\PROJECTS\RevitElectrico`. Aquí viven scripts, pruebas, datos y salidas.
- **Insumo de dibujo:** `D:\Work\PROJECTS\Actuales\T5-SantaMarta` es un proyecto de dibujo que se usa como base. **Es de solo lectura: no se modifica nada allí.**
- **Archivos de trabajo:** `D:\Work\PROJECTS\RevitElectrico\ArchivosBase`.
- **V03 no es "documento canónico":** `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V03.rvt` es un **archivo de trabajo** y la base para trabajar proyectos distintos de T5-SantaMarta. Esa base puede cambiar de un proyecto a otro; no se declara inmutable ni se congela.
- **Datum:** `Z_absoluta = nivel.Elevation + altura_local`. El nivel "Piso 5" tiene elevación 43.3727 m.


## Hardware y entorno

- **Entorno dedicado (venv separado):** `D:\Work\PROJECTS\RevitElectrico\.venv\Scripts\python.exe` (Python 3.12, independiente del entorno de DiseñoParametrico). Todas las dependencias del proyecto (pytest, ezdxf, openpyxl, numpy, pandas, pyshp, ifcopenshell) se instalan aquí. **No reutilizar el venv de DiseñoParametrico.**
- Revit 2026 instalado en la estacion de trabajo (confirmado).
- pyRevit instalado en `C:\Users\Dario Salas\AppData\Roaming\pyRevit-Master\bin\pyrevit.exe` (plantilla de referencia en `D:\Work\Scripts\AgentKit\11-cad-bim\revit_pyrevit_template.py`).
- Los scripts de Fase 6 (IronPython 2.7) se ejecutan dentro de Revit 2026 via pyRevit Python Shell, no desde el venv de CPython.

### Variable de entorno

- `$REVITELECTRICO_ROOT` → `D:\Work\PROJECTS\RevitElectrico` (definirla en el entorno de usuario; sin guion bajo entre REVIT y ELECTRICO).
- Rutas relativas al proyecto preferidas sobre rutas absolutas de usuario. NUNCA hardcodear rutas absolutas de usuario.

### Dependencias instaladas en `.venv`

pytest, ezdxf, openpyxl, numpy, pandas, pyshp, ifcopenshell.

### Creacion del entorno (una sola vez)

```powershell
# Desde D:\Work\PROJECTS\RevitElectrico
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install pytest ezdxf openpyxl numpy pandas pyshp ifcopenshell
```

- Revit 2026 instalado en la estacion de trabajo (confirmado).
- pyRevit instalado en `C:\Users\Dario Salas\AppData\Roaming\pyRevit-Master\bin\pyrevit.exe` (plantilla de referencia en `D:\Work\Scripts\AgentKit\11-cad-bim\revit_pyrevit_template.py`).
## Coordenadas

- Origen local (0,0,0) para Revit/Rhino.
- **NO usar POT/gpkg de Bogotá**: este proyecto está en Santa Marta. Sin consulta de geobase POT, sin retiros urbanísticos de Decreto 555/2021.
- Offset de coordenadas del DXF fuente: X -991.903 m, Y -1714.822 m → reubicar a (0,0) antes de importar a Revit.
- **Regla de datum (obligatoria):** en los JSON, `z_revit` es **altura local de montaje**, nunca Z absoluta. `Z_absoluta = nivel.Elevation + z_local`.

## Reglas del modelo eléctrico

- **`LevelId = -1` es normal en componentes eléctricos.** En modelos con objetos eléctricos (familias face-based / work-plane based) Revit reporta `LevelId = -1`; no es un defecto y no debe tratarse como bloqueador. La validación de ubicación se hace por **Z absoluta contra la elevación del nivel** y por **posición X,Y**, no por `LevelId`.
- **Apartamentos F 01 y F 02 son referencia intocable.** Están modelados directamente en Revit (incluida la tubería y sus componentes) para servir de referencia válida de localización. **No se modifican, mueven, recrean ni borran.** Todo el trabajo se hace sobre los demás apartamentos.
- **Método de posicionamiento: tablero-anclaje.** El panel eléctrico ya bien ubicado de cada apartamento es el origen; los demás componentes se colocan relativos a él (ver `data/procedimiento_tablero_anclaje_apartamentos_v01.md`).
- **No mover conduits existentes** al reposicionar dispositivos; los conduits se recrean después de validar posiciones.

## Normativa

- Cálculos eléctricos (RETIE / NTC 2050): se hacen de manera independiente, ya están expresados en los planos 2D. Esta información se lleva a 3D; no se recalcula en este proyecto.
- Modelo 3D solo para validación de interferencias y coordinación interna. No es documento constructivo certificado.

## Reglas de comportamiento

### Antes de proponer cambios
1. Leer el CLAUDE.md del proyecto (este archivo).
2. Verificar los documentos de diagnóstico en `2.-Entradas/` (DIAGNOSTICO_FINAL_DWG_ELECTRICO_SANTA_MARTA.md, Plan_Consejo_CAD_a_Revit_Electrico_v01.md).
3. No inventar APIs: verificar la librería/plugin antes de asumir su API.

### Al generar código
4. **Python 3.12** para scripts externos (con type hints, ruff, mypy).
5. **IronPython 2.7** solo dentro de Revit/Dynamo si aplica (sin type hints, sin f-strings, sin requests/bs4; usar `.format()` y concatenación de strings).
6. **Convención de nombrado**: `RE_FASE_VERBO_vNN.py` (ej: `RE1_NORMALIZA_DXF_v01.py`, `RE2_MAPEO_BLOQUES_v01.py`). Para scripts de Fase 6 usar `NOMBRE_DESCRIPTIVO_vNN.py` (ej: `ASIGNAR_RED_v05.py`).
7. **Rutas**: usar variables de entorno (`$REVITELECTRICO_ROOT` — definida en el entorno, sin guion bajo entre REVIT y ELECTRICO) o rutas relativas al proyecto. NUNCA hardcodear rutas absolutas de usuario.
8. **Tests**: todo script nuevo requiere `test_<nombre>.py` con fixture JSON.

### Al trabajar con Revit
9. Revit 2026: pyRevit add-in para scripts dentro de Revit. Dynamo 3.6.x incluido.
10. BimorphNodes v6.0.0 confirmado solo hasta Revit 2026 (no 2027).
11. Sin APIs online dentro de scripts: usar archivos locales en `data/`.
12. **Parámetro Comments** (`BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS`) se usa para marcar RED=SI en dispositivos eléctricos. No crear shared parameters.
13. **ElementId** en IronPython 2.7: construir con `System.Int64(int(id_str))` para evitar ambigüedad en overloads.
14. Ejecutar scripts de Fase 6 desde pyRevit Python Shell: `exec(open(r"...\script.py").read())` luego llamar a la función principal (ej: `asignar_red(doc, reporte_json="data\\apto_F_02_aplicar_mapa_v3.json")`).

### Normativa eléctrica
12. RETIE / NTC 2050: cálculos independientes, ya en planos 2D. No se recalculan aquí.
13. Modelo 3D solo para coordinación/diseño interno, no certificado.

## Estructura de carpetas

```
RevitElectrico/
├── 2.-Entradas/        # DWG, RVT, DXF, documentos de diagnóstico, plan del Council
├── 3.-Proceso/         # Scripts Python/Dynamo, JSON de extracción, archivos RVT de prueba
├── 4.-Salidas/         # Resultados generados (Excel, IFC, reportes)`n├── ArchivosBase/       # Archivos base DXF/DWG por proyecto (configurable por proyecto)
├── src/                # Código por fase (RE_*)
│   ├── fase-1-contexto/
│   ├── fase-2-demanda/
│   ├── fase-3-masa/
│   ├── fase-4-ambiental/
│   └── fase-5-bim/     # Inyección nativa Revit (API Revit / pyRevit)
├── tests/              # Pytest + fixtures (test_<nombre>.py con fixture JSON)
├── config/             # Configuraciones (dxf-base.json, mapeos, etc.)
├── data/               # Datos intermedios (JSON, IFC)
├── exports/            # Excel y reportes finales
└── CLAUDE.md           # Este archivo
```

## Comandos disponibles

```powershell
# Variable de entorno
echo $env:REVITELECTRICO_ROOT

# Tests (usar el venv dedicado de RevitElectrico)
cd D:\Work\PROJECTS\RevitElectrico
.venv\Scripts\python.exe -m pytest tests/

# Scripts externos (Python 3.12, venv propio de RevitElectrico)
& "$env:REVITELECTRICO_ROOT\.venv\Scripts\python.exe" src\fase-1-contexto\RE1_NORMALIZA_DXF_v01.py ...
```
## Configuración permanente de pytest

El archivo `pytest.ini` en la raíz del proyecto fija `basetemp = .pytest_temps` para evitar el
`PermissionError [WinError 5]` en el teardown de carpetas temporales de pytest en Windows
(ruta con espacios en el nombre de usuario `Dario Salas` y symlinks/junctions temporales).

Con esto, el comando de tests es permanente y estable:

```powershell
cd $env:REVITELECTRICO_ROOT
.venv\Scripts\python.exe -m pytest tests/
```

No es necesario pasar `--basetemp` ni `-p no:cacheprovider` en cada ejecución.

## Cuándo preguntar vs. decidir
- **Preguntar**: cambios arquitectónicos, nuevos plugins, modificar archivos fuente de `2.-Entradas/`, eliminar archivos.
- **Decidir**: refactors internos, nuevos tests, ajustes de naming, mejoras de documentación.

## Cuándo detenerse
- Si un script Dynamo/pyRevit crashea 2 veces seguidas: detenerse y revisar el diagnóstico en `2.-Entradas/`.
- Si Revit 2026 no responde o no está instalado: usar solo lectura IFC con ifcopenshell sin Revit.


