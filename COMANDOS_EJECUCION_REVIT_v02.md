# Comandos de ejecución en Revit (pyRevit Python Shell) — v02

Archivo: `D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\RE_APLICAR_MAPA_V3_REVIT_v01.py`

## Paso 0: Limpieza previa (opcional)

Si hay FamilyInstance de prueba creadas manualmente (ej. ID 5554281, E_Distribution Panel en balcón), deshazlas en Revit con **Ctrl+Z** antes de ejecutar el script.

## Paso 1: Ejecutar el modelo de los 37 dispositivos

Copia y pega este bloque completo en la **pyRevit Python Shell** dentro de Revit:

```python
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

app = __revit__.Application
uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document

print("Documento: {}".format(doc.Title))

exec(open(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\RE_APLICAR_MAPA_V3_REVIT_v01.py").read())

aplicar_mapa_revit(
    doc,
    r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\reporte_bloques_todos.json",
    r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\resultado_modelado_apto_F02.json"
)
```

**Resultado esperado en consola:**

```
Documento: STM-FJR-TORRE5-A-M3-R23-P01-CENTRA-prueba 01
Diagnostico de techos/cielorasos:
...
=== Resultado ===
Total a modelar: 37
Exitos: 37
Fallos: 0
Saltados (marcador): 22
Sin mapeo: 0
JSON guardado en: D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\resultado_modelado_apto_F02.json
```

## Paso 2: Verificar que las 37 FamilyInstance existen en el documento Revit

```python
exec(open(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\VERIFICAR_INSTANCIAS_REVIT_v01.py").read())

verificar_instancias_revit(doc, json_out=r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\verificacion_instancias_revit.json")
```

Esto listará todas las FamilyInstance, verificará que los 37 IDs esperados (5554235–5554271) estén presentes y guardará el detalle en JSON.

## Paso 3: Listar todas las familias y símbolos cargados (diagnóstico opcional)

```python
exec(open(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\LISTAR_FAMILIAS_REVIT_v01.py").read())

listar_familias(doc)
```

Guarda `data\familias_cargadas_prueba01.json`.

---

## ¿Por qué falló la primera vez?

`NameError: name 'doc' is not defined` ocurre porque en la pyRevit Python Shell, `__revit__` no se define automáticamente como en RevitPythonShell. Hay que asignar `doc = __revit__.ActiveUIDocument.Document` explícitamente antes de usarlo.

## Próximas tareas después de confirmar las 37 instancias

1. **RED manual** en 5 dispositivos: `ELEC-NET-PAU` × 1 (ID 5554265) y `ELEC-TEL` × 4.
2. **Tipos de conduit** por diámetro: 3–4 mm → 3/4", 5–6 mm → 1", 7–8 mm → 1-1/4".
3. **Clash detection** contra HVAC, fontanería y estructura.
4. **Modelar los 20 bloques restantes** del apartamento.
