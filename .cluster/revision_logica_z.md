# REVISIÓN DE LÓGICA Z — F6_CREAR_DISPOSITIVOS_E06_v01

**Proyecto:** RevitElectrico · Apartamento E06 · Nivel "Piso 5" (elevación 13.22 m) · 44 dispositivos  
**Fecha:** 2026-11-12 · Subagent de revisión lógica geométrica  
**Archivo revisado:** `src\fase-6-revit\F6_CREAR_DISPOSITIVOS_E06_v01.py`  
**Dataset:** `data\E06_dispositivos_para_crear.json`  
**Instrucción:** No reescribir el script. Solo diagnosticar y reportar.

---

## (a) Mecanismo exacto del fallo

El reporte del usuario —*"las luminarias están todas en 0.00, el offset from host está en la medida correcta, pero el level marca -13.2200, y en vista lateral ninguno está donde el reporte dice"*— es coherente con una sola causa raíz en la API de Revit: **el parámetro `Offset from Host` de una familia host-based es un desplazamiento RELATIVO al host, no una elevación absoluta del mundo.**

### Cadena de valores en Revit (API)

| Concepto | Significado en API | ¿Es absoluto o relativo? |
|---|---|---|
| **Level.Elevation** | Elevación del nivel respecto al origen del proyecto (0.00 del mundo). | Absoluta (mundo) |
| **Location.Point.Z** | Coordenada Z del punto de inserción del elemento en el espacio del modelo. | Absoluta (mundo) |
| **Offset from Host** (`FAMILY_OFFSET_PARAM`) | Distancia del punto de inserción del elemento a la cara de referencia del host (pared/techo/suelo). | Relativa al host |
| **Elevation from Level** | Distancia del punto de inserción al plano del Level asignado. | Relativa al nivel |

Para una familia **wall-based** o **ceiling-based** (host-based):

1. Revit coloca la instancia pegada a la cara del host (pared o techo).
2. `Offset from Host` la desplaza desde esa cara.
3. El `Level` asignado se usa como referencia de cota para vistas y programación, pero **no** se suma automáticamente a `Offset from Host` para formar la Z absoluta.
4. `Location.Point.Z` = Z del punto de inserción en el mundo, que resulta de: `Z_del_host_en_ese_punto + Offset_from_Host`.

### Por qué aparecen simultáneamente: Offset correcto + Level -13.2200 + Z real 0.00

El escenario descrito por el usuario es lo que ocurre cuando:

1. **Estrategia A (`NewFamilyInstance(XYZ(x,y,z_abs), simbolo, NonStructural)`)** falla para una familia host-based (por ejemplo porque el símbolo no es activable sin host, o porque la familia requiere un host válido). Revit lanza excepción o devuelve `None`.
2. **Estrategia C (`NewFamilyInstance(XYZ(x,y,z_abs), simbolo, host_cercano, NonStructural)`)** tiene éxito pero con un host **erróneo o en el nivel 0.00** (por ejemplo un muro de cimentación en el nivel 0.00, o un techo de otro nivel).
3. Al crear sobre ese host, `Location.Point.Z` se resuelve como: `Z_del_host (0.00) + offset_correcto`. Si el offset desde el host es 0.30 m (para z_abs 13.52 m) pero el host está en Z=0.00, el elemento queda en Z=0.30 m — o si el host es un techo en otro nivel, la Z queda desplazada por la elevación del techo.
4. El `Level` asignado por Revit al elemento puede ser el nivel del host o un nivel por defecto. Si el host está en el nivel 0.00 y Revit asigna ese nivel, pero el usuario lee el parámetro `Level` del elemento y ve "-13.2200", eso indica que el elemento está asociado al nivel "Piso 5" (elev 13.22 m) **pero su Location.Point.Z está en 0.00** porque fue creado con estrategia C sobre un host en Z=0.00 y el offset no compensa la elevación del nivel.

En resumen: el usuario confunde **offset from host** (relativo al host) con **elevación absoluta del mundo**. El script pasa `z_offset_m` (que es `z_abs_m - nivel_elev_m`, es decir, un valor relativo al nivel "Piso 5") como coordenada Z absoluta en la estrategia A, o como Z relativa al nivel en la estrategia B. Ninguna de las dos considera la geometría real del host cuando entra en juego la estrategia C.

### El bug del signo en el reporte del usuario

El reporte dice "level marca -13.2200". Si el nivel "Piso 5" tiene elevación +13.22 m y Revit muestra -13.2200, es señal de que el `Level` del elemento fue resuelto incorrectamente (quizás el elemento quedó asociado a un nivel invertido, o el parámetro compartido `RevitElectrico_Lote` está afectando la lectura del nivel). Esto refuerza que la asociación nivel/host está rota.

---

## (b) Tabla: Estrategia → Z resultante esperada

| Estrategia | Firma API llamada | Z que produce Location.Point.Z | ¿Es Z absoluta del mundo? | Comentario |
|---|---|---|---|---|
| **A** | `NewFamilyInstance(XYZ(x, y, z_abs), simbolo, NonStructural)` | `z_abs` tal cual se pasa | **SÍ** (si la familia lo acepta sin host) | Solo funciona para familias **no host-based** (face-based o modelo genérico sin restricción de host). Para wall-based/ceiling-based suele lanzar excepción o devolver None. |
| **B** | `NewFamilyInstance(XYZ(x, y, z_off), simbolo, nivel, NonStructural)` | `nivel.Elevation + z_off` | **SÍ**, si `z_off` = `z_abs_m - nivel.Elevation` | El XYZ pasado se interpreta como coordenada relativa al nivel. Revit suma la elevación del nivel. Si `z_off` = `z_abs - 13.22`, el resultado es `13.22 + (z_abs - 13.22) = z_abs`. **Coherente.** |
| **C** | `NewFamilyInstance(XYZ(x, y, z_abs), simbolo, host, NonStructural)` + `MoveElement` | `Z_del_host_en_(x,y) + offset_desde_host` | **NO necesariamente** | Depende de la elevación del host en el punto (x,y). Si el host está en Z=0.00 y el offset es 0.30 m, el elemento queda en Z=0.30 m, no en 13.52 m. MoveElement corrige después si se ejecuta. |

**Conclusión de la tabla:**  
- Estrategia A produce Z absoluta **solo si** la familia acepta creación sin host.  
- Estrategia B produce Z absoluta **si y solo si** el `z_off` pasado es realmente `z_abs_m - nivel.Elevation` (coherente con el dataset).  
- Estrategia C produce Z relativa al host; **no** garantiza Z absoluta sin un `MoveElement` posterior exitoso.

---

## (c) Riesgos residuales

### Riesgo 1: Familia wall-based y estrategia A falla → ¿qué pasa?

Si la familia es **wall-based** (por ejemplo un interruptor o toma que debe anclarse a una pared), la estrategia A (`NewFamilyInstance(XYZ, simbolo, NonStructural)` sin host) **fallará** en Revit porque la familia requiere un host válido. El script cae a la estrategia B (si hay nivel) o C (si hay host cercano).

- **Si cae a B con nivel correcto y `z_off = z_abs - 13.22`:** Revit coloca el elemento en `Z = 13.22 + z_off = z_abs`. **Esto da Z absoluta correcta.** Pero solo funciona si la familia acepta ser creada con un Level sin host. Algunas familias wall-based rechazan esto y exigen un muro físico.
- **Si cae a C (host cercano):** El host encontrado por `_host_cercano` busca el muro/techo más cercano en XY dentro de 8 m. Si ese host está en otro nivel (por ejemplo un techo del nivel inferior en Z=0.00, o un muro de cimentación), el elemento se ancla a ese host y su Z inicial es `Z_host + offset`. El `MoveElement` posterior intenta corregir, pero:
  - Si el host es un techo y la familia es ceiling-based, `MoveElement` en Z puede romper la restricción de host (el elemento se desancla del techo).
  - Si el host es un muro en otro nivel, el elemento puede quedar flotando o colgado de una pared incorrecta.

### Riesgo 2: ¿Estrategia B da Z absoluta o Z relativa al nivel?

La estrategia B llama a:
```python
doc.Create.NewFamilyInstance(XYZ(x, y, z_off), simbolo, nivel, StructuralType.NonStructural)
```

Según la API de Revit, cuando se pasa un `Level` como tercer argumento, el XYZ se interpreta como **coordenada relativa al plano del nivel**. Revit calcula:

```
Location.Point.Z = nivel.Elevation + z_off (en pies)
```

Por tanto:
- Si `z_off` (en pies) = `_m_a_ft(z_abs_m - nivel_elev_m)`, entonces `Location.Point.Z = nivel.Elevation + (z_abs - nivel.Elevation) = z_abs`. **Z absoluta correcta.**
- El dataset tiene `z_offset_m = z_abs_m - nivel_elev_m`. Por ejemplo: `13.52 - 13.22 = 0.30`. Esto es **coherente** con lo que espera la API de Revit para la estrategia B.

**Sin embargo**, esto solo es válido si la familia acepta ser creada con un Level sin host. Si la familia es estrictamente host-based y Revit ignora el nivel o lo sobrescribe con el nivel del host, el resultado puede ser incorrecto.

### Riesgo 3: Cálculo `z_offset_m = z_abs_m - nivel_elev_m` — ¿coherente con la API?

**Sí, es coherente con la estrategia B.** La API `NewFamilyInstance(XYZ, symbol, level, structuralType)` espera que el Z del XYZ sea un **offset desde el nivel**, no la Z absoluta del mundo. Por lo tanto pasar `z_offset_m = z_abs - 13.22` es exactamente lo correcto para esa sobrecarga.

**El problema es la estrategia A:** En la estrategia A se pasa `z_abs` directamente como Z del XYZ sin nivel. Si la estrategia A falla y se cae a B, el `z_off` está bien calculado. Pero si la estrategia A **aparentemente** tiene éxito (devuelve un objeto no None) para una familia host-based, Revit puede haber creado el elemento sin la asociación de nivel correcta, dejando `Location.Point.Z = z_abs` pero con `Level` nulo o incorrecto, y `Offset from Host` sin sentido porque no hay host.

### Riesgo 4: Validación por `Location.Point.Z` después de crear

El script lee `Location.Point.Z` después de crear y, si difiere más de `TOL_M (0.01 m)`, hace `MoveElement`. Esto es una red de seguridad, pero:

- `MoveElement` en una familia host-based puede **romper la restricción de host** (el elemento deja de estar anclado al techo/pared y se convierte en modelo genérico flotante).
- Si la estrategia C creó el elemento en un host en Z=0.00 y el offset desde el host es 0.30 m, `Location.Point.Z` lee 0.30 m. El `MoveElement` intenta moverlo a 13.52 m (dz = 13.22 m). Si la familia es ceiling-based y está anclada a un techo, moverla 13.22 m hacia arriba la desancla del techo.
- El script marca `creados_con_correccion` si el move logra alcanzar la tolerancia, pero no verifica que el elemento siga anclado correctamente al host después del move.

### Riesgo 5: Tolerancia de 1 cm y redondeo

`TOL_M = 0.01` (1 cm) es razonable, pero `z_real` se redondea a 4 decimales en el reporte JSON. Si Revit devuelve valores en pies con precisión finita, la conversión `ft_a_m` puede introducir errores de redondeo cercanos a la tolerancia. No es crítico pero puede causar falsos negativos en `z_ok`.

---

## (d) Checklist de verificación en Revit (valores esperados concretos)

El usuario debe verificar en Revit, no confiar solo en el JSON de salida del script.

### Paso 1: Seleccionar una muestra representativa

Seleccionar al menos un dispositivo de cada altura objetivo:
- 1 dispositivo con `z_abs_m = 13.52 m` (+0.30 sobre nivel)
- 1 dispositivo con `z_abs_m = 14.32 m` (+1.10)
- 1 dispositivo con `z_abs_m = 14.42 m` (+1.20)
- 1 dispositivo con `z_abs_m = 15.82 m` (+2.60)

### Paso 2: Verificar en vista lateral (elevación o sección)

Abrir una vista en elevación o sección que corte los dispositivos.

| Propiedad | Dónde mirar | Valor esperado |
|---|---|---|
| **Posición visual en Z** | Vista lateral / 3D | Debe estar a la altura correcta respecto al nivel "Piso 5" (no flotando en 0.00) |
| **Level (Nivel)** | Propiedades del elemento > Identity Data > Level | Debe ser "Piso 5" (no "-13.2200", no "Nivel 1", no en blanco) |
| **Offset from Host** | Propiedades > Constraints > Offset from Host | Debe coincidir con el `z_offset_m` del dataset (0.30, 1.10, 1.20 o 2.60 m) |
| **Location.Point.Z** | No está directamente en la UI de Revit; usar un nodo de Dynamo o un script de pyRevit para leerlo | Debe ser igual a `z_abs_m` (± 0.01 m) |

### Paso 3: Verificación programática (pyRevit console)

Ejecutar en la consola pyRevit:

```python
from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance
doc = __revit__.ActiveUIDocument.Document
for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
    if fi.LookupParameter("RevitElectrico_Lote") and fi.LookupParameter("RevitElectrico_Lote").AsString() == "46c3f138-025d-47d4-b24a-41cd21181a58":
        loc = fi.Location
        z_ft = loc.Point.Z if loc and hasattr(loc, 'Point') else None
        level = fi.Level
        print(f"{fi.Id}: Z={z_ft:.4f} ft ({z_ft/3.28084:.4f} m), Level={level.Name if level else 'None'}, Elev={level.Elevation if level else 'None'} ft")
```

**Valores esperados:**
- `Location.Point.Z` en metros ≈ `z_abs_m` del dataset (13.52, 14.32, 14.42 o 15.82)
- `Level.Name` = "Piso 5"
- `Level.Elevation` ≈ 13.22 m (43.3727 ft)

### Paso 4: Verificar que no hay elementos en Z=0.00

Buscar cualquier dispositivo del lote con `Location.Point.Z` cerca de 0.00 m. Si hay, el script falló para esos elementos (estrategia C con host en nivel 0.00 sin corrección exitosa).

### Paso 5: Verificar anclaje al host (si aplica)

Para dispositivos wall-based o ceiling-based, confirmar que después de cualquier `MoveElement` el elemento sigue anclado al host correcto (no flotando libremente). En vista 3D, el elemento debe tocar la cara de la pared o del techo.

---

## Resumen ejecutivo

El fallo de las 20 versiones previas y el comportamiento actual se explican por confusión entre **offset relativo al host** y **elevación absoluta del mundo**. La estrategia B del script es **teóricamente correcta** (el cálculo `z_offset_m = z_abs_m - nivel_elev_m` coincide con lo que espera la API de Revit cuando se pasa un `Level`), pero solo funciona si la familia acepta creación con nivel sin host. La estrategia C introduce el mayor riesgo: ancla a un host cercano cuya elevación puede ser 0.00, produciendo Z real incorrecta a menos que `MoveElement` corrija y no rompa el anclaje.

La verificación mínima crítica es: **abrir vista lateral, seleccionar un dispositivo, leer `Location.Point.Z` (via pyRevit/Dynamo) y confirmar que sea igual a `z_abs_m` del dataset, que `Level` sea "Piso 5", y que `Offset from Host` coincida con `z_offset_m`.**
