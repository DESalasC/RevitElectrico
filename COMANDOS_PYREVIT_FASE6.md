# Comandos pyRevit — Fase 6 RevitElectrico (T5-SantaMarta)

Archivo consolidado con las formas de ejecutar cada etapa del pipeline. Hay **dos opciones**:

- **Opción A (rápida):** pegar bloques en la pyRevit Python Shell (no requiere instalación).
- **Opción B (recomendada, reutilizable):** instalar macros pyRevit (`.py` + `.pyrevit`) para tener botones en la cinta de Revit.

---

## Opción A — Bloques para la pyRevit Python Shell

Abre el .rvt en Revit 2026, carga pyRevit, abre la consola Python y pega el bloque correspondiente.

### Etapa 1 — Modelar FamilyInstance (37 dispositivos)
```python
exec(open(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\RE_EJECUTAR_MAPA_V01.py").read())
app = __revit__.Application
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document
ejecutar_mapa(doc)
```
Resultado esperado: **37 / 0 / 22 / 0** (éxitos / fallos / saltados / sin mapeo). Incluye `Fecha ejecucion` al inicio y al final.

JSON de salida: `data\resultado_modelado_apto_F02.json`

### Etapa 2 — Crear tipos de Conduit (5 tipos: 3/4", 1", 1-1/4", 2", 3")
```python
exec(open(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\RE_CREAR_TIPOS_CONDUIT_V01.py").read())
app = __revit__.Application
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document
ejecutar_crear_tipos_conduit(doc)
```
Si el documento es arquitectónico sin categoría MEP, el script primero crea un conducto de prueba para registrar OST_Conduit y luego crea los 5 tipos.

JSON de salida: `data\crear_tipos_conduit_resultado.json`

### Etapa 3 — Asignar RED=SI (5 dispositivos)
```python
exec(open(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\RE_ASIGNAR_RED_V01.py").read())
app = __revit__.Application
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document
ejecutar_asignar_red(doc)
```
Resultado esperado: **Exitos: 5, Fallos: 0**.

JSON de salida: `data\asignar_red_resultado.json`

### Etapa 4 — Clash Detection (placeholder)
Ver `REVIT6_CLASH_DETECTION.py` (requiere implementación de intersección de geometría real).

---

## Opción B — Macros pyRevit (recomendado, reutilizable)

Cada etapa tiene un par de archivos en:
`src\fase-6-revit\macros\`

| Macro | `.py` (lógica) | `.pyrevit` (manifiesto) |
|-------|---------------|------------------------|
| 6.1 Modelar mapa (F02) | `REVIT6_MODELO_MAPA.py` | `REVIT6_MODELO_MAPA.pyrevit` |
| 6.2 Asignar RED=SI | `REVIT6_ASIGNAR_RED.py` | `REVIT6_ASIGNAR_RED.pyrevit` |
| 6.3 Tipos de Conduit | `REVIT6_CREAR_TIPOS_CONDUIT.py` | `REVIT6_CREAR_TIPOS_CONDUIT.pyrevit` |
| 6.4 Clash Detection | `REVIT6_CLASH_DETECTION.py` | `REVIT6_CLASH_DETECTION.pyrevit` |

### Cómo instalar las macros en pyRevit

1. Copiar la carpeta `macros/` a la carpeta de extensiones de pyRevit de tu usuario, por ejemplo:
   ```
   C:\Users\Work\AppData\Roaming\pyRevit\extensions\RevitElectrico\
   ```
   (crear la carpeta si no existe).

2. Reiniciar Revit / recargar pyRevit.

3. Las macros aparecerán como botones en la pestaña de pyRevit de la cinta de Revit 2026:
   - **6.1 Modelar mapa (F02)**
   - **6.2 Asignar RED=SI**
   - **6.3 Tipos de Conduit**
   - **6.4 Clash Detection**

Cada macro imprime su resultado directamente en la salida de pyRevit y guarda un JSON en `data\`.

> Nota: si la carpeta `extensions/` no existe bajo tu versión de Revit (p. ej. `pyRevit\2026\extensions\`), créala manualmente. En este equipo está instalado pyRevit para Revit 2027 en `pyRevit\2027\`; para Revit 2026 usa `pyRevit\2026\extensions\`.

---

## Archivos de script en disco (lógica base)

| Script | Ruta | Propósito |
|--------|------|-----------|
| RE_EJECUTAR_MAPA_V01.py | `src\fase-6-revit\RE_EJECUTAR_MAPA_V01.py` | Wrapper para la Etapa 1 (usa `imp.load_source` para evitar scope issues) |
| RE_ASIGNAR_RED_V01.py | `src\fase-6-revit\RE_ASIGNAR_RED_V01.py` | Wrapper para la Etapa 3 |
| RE_CREAR_TIPOS_CONDUIT_V01.py | `src\fase-6-revit\RE_CREAR_TIPOS_CONDUIT_V01.py` | Wrapper para la Etapa 2 |
| RE_APLICAR_MAPA_V3_REVIT_v02.py | `src\fase-6-revit\RE_APLICAR_MAPA_V3_REVIT_v02.py` | Lógica base: crea FamilyInstance en Revit 2026 (37/0/22/0 validado) |
| ASIGNAR_RED_v04.py | `src\fase-6-revit\ASIGNAR_RED_v04.py` | Lógica base: asigna RED=SI via Comments |
| CREAR_TIPOS_CONDUIT_v04.py | `src\fase-6-revit\CREAR_TIPOS_CONDUIT_v04.py` | Lógica base: conducto de prueba + 5 tipos de Conduit |
| CLASH_DETECTION_v01.py | `src\fase-6-revit\CLASH_DETECTION_v01.py` | Detección de interferencias (pendiente de implementar intersección real) |

---

## JSON de entrada y salida

| Archivo | Ruta | Descripción |
|---------|------|-------------|
| reporte_bloques_todos.json | `data\reporte_bloques_todos.json` | Entrada: 37 a modelar, 22 a saltar (marcadores), 0 sin mapeo. Altura cieloraso: 15.82 m |
| resultado_modelado_apto_F02.json | `data\resultado_modelado_apto_F02.json` | Salida Etapa 1: **37 / 0 / 22 / 0** validado 2026-10-22 23:20:07 |
| asignar_red_resultado.json | `data\asignar_red_resultado.json` | Salida Etapa 3: RED=SI a 5 dispositivos |
| crear_tipos_conduit_resultado.json | `data\crear_tipos_conduit_resultado.json` | Salida Etapa 2: 5 tipos de Conduit |
| clash_detection_resultado.json | `data\clash_detection_resultado.json` | Salida Etapa 4 (placeholder) |

---

## RVT base

Archivo: `D:\Work\PROJECTS\Actuales\T5-SantaMarta\3.-Proceso\STM-FJR-TORRE5-A-M3-R23-P01-CENTRA-prueba 01.rvt`

> Nota: tras el crash de Revit del 2026-10-22, el RVT debe reabrirse antes de ejecutar cualquier etapa. Las instancias de familia se guardan con el .rvt; persisten entre sesiones si guardas el archivo.

---

## Próximos pasos pendientes

1. ✅ Etapa 1 — Modelar 37 dispositivos: **37 / 0 / 22 / 0 confirmado** (2026-10-22 23:20:07)
2. ⏳ Etapa 2 — Crear 5 tipos de Conduit (3/4", 1", 1-1/4", 2", 3")
3. ⏳ Etapa 3 — Asignar RED=SI a 5 dispositivos
4. ⏳ Etapa 4 — Clash Detection (implementar intersección de geometría real)
5. ⏳ Modelar los 22 bloques restantes → estos son **marcadores de conductor** (1FTN, 1TNR, etc.) que se saltan por diseño (`mapear:false`), no generan FamilyInstance. Los 37 dispositivos físicos ya están modelados.
