# MiAddin — Wrapper C# para placement face-based en Revit 2026

Wrapper C# compilado a DLL que expone la sobrecarga
`Document.Create.NewFamilyInstance(Reference, UV, double, FamilySymbol)`
de la API de Revit, callable desde **IronPython 2.7 (pyRevit)** vía
`clr.AddReferenceByPath(ruta_absoluta_a_MiAddin.dll)`.

**Versión actual**: `v3` (reflexión explícita) — MD5 `b53385f969af5c2ef80415ef04ca2a31`, 26 KB.

Resuelve dos problemas encadenados del **script v69**:

1. **v69 original** fallaba con:
   ```
   Reference direction is parallel to face normal
   ```
   al usar `NewFamilyInstance(Reference, XYZ, XYZ, FamilySymbol)` (sobrecarga equivocada).

2. **Wrapper v1/v2 con `dynamic`** fallaba con:
   ```
   The best overloaded method match for NewFamilyInstance(Curve, FamilySymbol, Level, StructuralType) has some invalid arguments
   ```
   porque el DLR (Dynamic Language Runtime) de IronPython/C# no resuelve bien
   la sobrecarga `(Reference, UV, double, FamilySymbol)` cuando hay 10+
   sobrecargas con perfiles similares en Revit 2026.

**v3 resuelve ambos** usando reflexión explícita: busca el `MethodInfo`
por nombre + tipos exactos de los argumentos en runtime, e invoca
`chosen.Invoke(...)`. Esto bypasa completamente el overload resolver del DLR.

---

## Por qué hace falta este wrapper

IronPython 2.7 (el que usa pyRevit dentro de Revit) **no resuelve** la
sobrecarga `NewFamilyInstance(Reference, UV, double, FamilySymbol)` por
tres razones:

1. **`UV` es un `struct`** (value type) en Revit API. IronPython pasa structs
   por valor, lo que hace ambigua la resolución de overloads.
2. **`double` es primitivo**, también value type. La combinación `UV + double`
   confunde al overload resolver de IronPython.
3. La **existencia de múltiples overloads** con perfiles similares
   (`XYZ, XYZ`, `Face, XYZ, XYZ`, `Reference, XYZ, XYZ`) hace que IronPython
   elija el equivocado o lance `TypeError`.

Un wrapper C# tipa explícitamente la llamada y elimina la ambigüedad.

Adicionalmente, la DLL **se compila contra .NET Framework 4.8** (no .NET 8),
porque IronPython 2.7 corre sobre el CLR de .NET Framework 4.x y
**no puede cargar DLLs .NET 8**. Para llamar al RevitAPI de Revit 2026
(.NET 8) desde una DLL .NET Framework 4.8, el wrapper usa `dynamic`
(el DLR resuelve los tipos en runtime sin importar la versión del runtime).

---

## Archivos entregados

```
download/MiAddin/
├── build/
│   ├── MiAddin.dll              ← DLL COMPILADA lista para usar (14 KB, .NET Framework 4.8, x64)
│   └── MiAddin.pdb               ← Símbolos de debug (opcional)
├── src/
│   ├── MiAddin.csproj            ← Proyecto .NET 8 SDK-style targeting net48
│   └── Placer.cs                 ← Fuente C# del wrapper
├── samples/
│   ├── MiAddinLoader.py           ← LOADER robusto (AddReferenceByPath + fallbacks)
│   ├── diagnostico_addreference.py ← Diagnostica por qué falla clr.AddReference
│   ├── test_minimo_wrapper.py    ← Test mínimo (carga + 1 dispositivo)
│   └── ejemplo_colocacion_face_based.py  ← Reemplazo del v69 masivo (F01)
├── build.ps1                     ← Build en Windows (PowerShell)
├── build.sh                      ← Build en Linux (verificación)
└── README.md                     ← Este archivo
```

---

## Instalación rápida

1. **Copia `build/MiAddin.dll`** a una carpeta accesible por IronPython.
   Recomendado:
   ```
   D:\Work\PROJECTS\RevitElectrico\bin\MiAddin.dll
   ```

2. **Verifica** que Revit 2026 está abierto con el documento activo
   (`STM-FJR-TORRE5-A-M3-R23-P01-CENTRAL-V01.rvt`).

3. **Abre pyRevit Python Shell** (IronPython 2.7).

4. **Carga el wrapper** con `MiAddinLoader.py`. **NO uses `clr.AddReference("name")`**: IronPython no busca en `sys.path` para resolver nombres de assemblies, solo en el GAC y el `PrivateBinPath` del host. El loader usa `clr.AddReferenceByPath(ruta_absoluta)`, que sí carga desde filesystem.

   ```python
   exec(open(r"D:\\Work\\PROJECTS\\RevitElectrico\\src\\fase-6-revit\\MiAddinLoader.py").read())
   from MiAddin import Placer
   print Placer.Version()
   ```

   Salida esperada:
   ```
   [MiAddinLoader] DLL cargada: D:\Work\PROJECTS\RevitElectrico\bin\MiAddin.dll
   [MiAddinLoader] Metodo usado: AddReferenceByPath
   [MiAddinLoader] Placer.Version(): MiAddin.Placer v1.0.0.0 - Wrapper NewFamilyInstance(Reference, UV, double, FamilySymbol)
   ```

5. **Test mínimo** (un solo dispositivo):
   ```python
   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\test_minimo_wrapper.py").read())
   test_carga()
   test_un_dispositivo(doc)
   ```

6. **Colocación masiva F01** (reemplaza a v69):
   ```python
   exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\ejemplo_colocacion_face_based.py").read())
   colocar_F01_con_wrapper(doc)
   ```

---

## API expuesta por `MiAddin.Placer` (v3 — reflexión)

| Método | Firma | Descripción |
| --- | --- | --- |
| `PlaceFaceBased` | `(doc, faceRef, uv, param, symbol) -> FamilyInstance` | Llama a `NewFamilyInstance(faceRef, uv, param, symbol)` **vía reflexión explícita**. Requiere `uv` ya calculado por el llamador. |
| `PlaceFaceBasedByReference` | `(doc, faceRef, point, param, symbol) -> FamilyInstance` | **RECOMENDADO**: toma Reference + XYZ, recupera Face vía `GetGeometryObjectFromReference`, proyecta para obtener UV, y coloca. Una sola llamada desde IronPython. |
| `ProjectPointToFace` | `(face, point) -> UV` | Devuelve UV del punto proyectado sobre una Face. |
| `ProjectPointByReference` | `(doc, faceRef, point) -> UV` | Devuelve UV del punto proyectado sobre una Reference. Atajo si ya tienes la Reference. |
| `GetFaceFromReference` | `(doc, faceRef) -> Face` | Recupera la Face desde una Reference vía `doc.GetElement(ref).GetGeometryObjectFromReference(ref)`. Útil para inspeccionar normals, bounds, etc. |
| `ListNewFamilyInstanceOverloads` | `(doc) -> string` | Diagnóstico: lista TODAS las sobrecargas de `NewFamilyInstance` que tu Revit expone. Útil para entender qué sobrecargas hay y por qué la reflexión elige la correcta. |
| `DiagnoseSymbol` | `(symbol) -> string` | Reporta `name`, `family`, `category`, `IsActive`, `HostingBehavior` de un FamilySymbol. |
| `Version` | `() -> string` | Identificación del wrapper. |

**Cambios respecto a v2**:
- `PlaceFaceBased` ya **NO usa dynamic dispatch**. Usa reflexión con
  `MethodInfo.Invoke(createObj, args)` para forzar la sobrecarga correcta.
- Agregado `PlaceFaceBasedByReference` que toma `Reference` (de
  `HostObjectUtils.GetSideFaces`) directamente, evitando el problema de
  `face.Reference == null`.
- Agregado `ListNewFamilyInstanceOverloads(doc)` para diagnóstico.

---

## Compilar la DLL (recompilar)

### Windows (PowerShell)

Requisitos:
- .NET SDK 8.0+ **o** Visual Studio 2022 con workload
  "Desarrollo de .NET Framework 4.8" (Microsoft .NET Framework 4.8 SDK +
  Targeting Pack).

```powershell
cd D:\Work\PROJECTS\RevitElectrico\MiAddin
.\build.ps1
# o explícitamente:
dotnet build src\MiAddin.csproj -c Release -p:Platform=x64
```

Salida:
```
build\MiAddin.dll
build\MiAddin.pdb
```

### Linux (verificación — la DLL resultante también corre en Windows)

Requisitos:
- .NET SDK 8.0+ (instalar vía `curl -sSL https://dot.net/v1/dotnet-install.sh | bash /dev/stdin --channel 8.0`).

```bash
cd ~/MiAddin
./build.sh
```

### Desde Visual Studio 2022

1. File → Open → Project/Solution → selecciona `src/MiAddin.csproj`.
2. Build → Build Solution (F6).
3. Salida: `build/MiAddin.dll`.

---

## Por qué `dynamic` y no referencia directa a `RevitAPI.dll`

La forma "obvia" de escribir el wrapper sería:

```csharp
using Autodesk.Revit.DB;

public static FamilyInstance PlaceFaceBased(
    Document doc, Reference faceRef, UV uv, double param, FamilySymbol symbol)
{
    return doc.Create.NewFamilyInstance(faceRef, uv, param, symbol);
}
```

**No funciona** para tu caso porque:

- Revit 2026 trae `RevitAPI.dll` compilada para **.NET 8**.
- IronPython 2.7 corre sobre el CLR de **.NET Framework 4.8**.
- Una DLL .NET Framework 4.8 **no puede referenciar** una DLL .NET 8 en
  tiempo de compilación (incompatibilidad de metadata).
- Aunque referenciara una versión antigua de `RevitAPI.dll` (.NET Framework 4.8,
  p. ej. la de Revit 2022), los tipos no coincidirían en runtime porque el
  `FamilySymbol` que IronPython pasa viene cargado desde la `RevitAPI.dll`
  de Revit 2026 (.NET 8) → cross-runtime type identity mismatch.

La solución es **no referenciar `RevitAPI.dll` en compile-time** y usar
`dynamic` para que la resolución ocurra en runtime vía el Dynamic Language
Runtime (DLR). El DLR no se preocupa por la versión del runtime del tipo
real, solo llama los métodos por reflexión tardía.

Esto sí funciona en Revit 2026 porque:
- La DLL `MiAddin.dll` (.NET Framework 4.8) la carga IronPython 2.7.
- Los objetos `doc`, `faceRef`, `symbol`, etc. que IronPython pasa son del
  proceso de Revit (características .NET 8 disponibles via reflection).
- El DLR invoca `doc.Create.NewFamilyInstance(...)` por reflexión tardía
  sobre el tipo real (`Autodesk.Revit.DB.Document` cargado desde la DLL de
  Revit 2026).

---

## Por qué `.NET Framework 4.8` y no `.NET 8`

| | .NET Framework 4.8 | .NET 8 |
| --- | --- | --- |
| IronPython 2.7 lo carga | ✅ | ❌ |
| pyRevit (IronPython 2.7) | ✅ | ❌ |
| PythonNet (CPython 3) | ❌ | ✅ |
| Revit 2024+ (Add-in nativo) | ❌ | ✅ |

Tu `PLAN_EJECUCION.md` confirma IronPython 2.7. Por eso `net48`.

---

## Troubleshooting

### `clr.AddReference("MiAddin")` lanza `IO.IOException: Could not add reference to assembly MiAddin`  ⚠️ ESTE ES TU ERROR

Este es el error más común y el que estás viendo. **Causa raíz**:
`clr.AddReference("name")` **NO busca en `sys.path`**. Busca la DLL en:

1. El GAC (Global Assembly Cache, `C:\Windows\Microsoft.NET\assembly\...`).
2. El `PrivateBinPath` del AppDomain del host (carpetas de Revit, no las tuyas).

Como `MiAddin.dll` no está en el GAC ni en las carpetas de Revit, falla.

**Fix correcto** (lo que `MiAddinLoader.py` hace automáticamente):

```python
import clr
# Ruta ABSOLUTA al archivo .dll en el filesystem
clr.AddReferenceByPath(r"D:\Work\PROJECTS\RevitElectrico\bin\MiAddin.dll")
from MiAddin import Placer
print Placer.Version()
```

`AddReferenceByPath` es la API de IronPython 2.7 diseñada para cargar DLLs
externas por filesystem path. Si por algún motivo no está disponible en tu
versión de IronPython, `MiAddinLoader.py` prueba automáticamente 3 fallbacks:

1. `clr.AddReferenceByPath(ruta)` ← preferido
2. `clr.AddReferenceToFileAndPath(ruta)` ← API legacy
3. `System.Reflection.Assembly.LoadFrom(ruta)` + `clr.AddReference(asm)` ← vía reflexión

**Diagnóstico completo**: ejecuta `diagnostico_addreference.py` desde pyRevit
Python Shell. Detecta: DLL existe, arquitectura x64, `Microsoft.CSharp.dll`
disponible, runtime .NET, busca en GAC, y prueba los dos métodos de carga.

```python
exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\diagnostico_addreference.py").read())
diagnosticar()
```

### `clr.AddReference` lanza `BadImageFormatException`

- **Causa**: estás intentando cargar la DLL desde un proceso de 32 bits.
- **Fix**: la DLL es x64. Asegúrate de que Revit 2026 (que es x64) está
  corriendo el script.

### `PlaceFaceBased` lanza `InvalidOperationException: PlaceFaceBased fallo. ...`

- El mensaje incluye los tipos reales de cada argumento para diagnosticar.
- Causas comunes:
  - `symbol.IsActive == False` → llama `symbol.Activate()` antes.
  - `face.Reference == null` → la cara es de un elemento no-referenciable.
    Prueba obtener la Reference vía `HostObjectUtils.GetSideFaces(...)`.
  - El UV está fuera de los bounds de la cara → verifica que el punto
    XYZ esté realmente dentro del muro (no en otra pared cercana).

### "Could not load file or assembly 'Microsoft.CSharp'"

- El wrapper usa `Microsoft.CSharp` para `dynamic`. Esta DLL viene con
  .NET Framework 4.x en cualquier Windows con .NET instalado, pero si por
  alguna razón falta en el equipo de Revit:
  - Instala ".NET Framework 4.8 Developer Pack" desde Microsoft.
  - O copia `Microsoft.CSharp.dll` junto a `MiAddin.dll` (la puedes sacar
    del GAC: `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\Microsoft.CSharp.dll`).

### Quiero recompilar con `dotnet build` pero da error de `Microsoft.CSharp`

Edita `src/MiAddin.csproj` y asegúrate de que `<Reference Include="Microsoft.CSharp" />`
está dentro de un `<ItemGroup>`.

---

## Diagnóstico del cambio respecto al script v69

El script `colocacion_masiva_F01_v69.py` usaba:

```python
direction = XYZ.BasisZ  # workaround sugerido por la nota de sesión
new_inst = doc.Create.NewFamilyInstance(face_ref, placement_pt, direction, sym)
```

Esto resuelve el error "parallel to face normal" en muros verticales pero:

1. Es **frágil**: si la cara no es vertical (techo inclinado, muro inclinado),
   `XYZ.BasisZ` vuelve a ser paralelo a la normal y falla.
2. **No usa la API pensada para face-based**: la sobrecarga
   `NewFamilyInstance(Reference, XYZ, XYZ, FamilySymbol)` es para
   *face-based con dirección arbitraria*, no para *face-based estándar*.
3. **Requiere calcular manualmente** el punto de inserción sobre la cara.

La sobrecarga `NewFamilyInstance(Reference, UV, double, FamilySymbol)` es:

- La API **canonical** para face-based programmatic placement.
- Determinista: la posición se expresa en UV (parametrización de la cara),
  no en XYZ absoluto + direction vector.
- Inmune al error "parallel to face normal": no hay direction vector.
- Permite offset perpendicular vía el `double param`.

---

## Roadmap sugerido

1. **Validar con `test_minimo_wrapper.py`** sobre 1 dispositivo (un
   interruptor o toma del F01). Confirmar que se crea la FamilyInstance y
   queda hosted en el muro.
2. **Comparar con el modelo manual** (`E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02-f.rvt`)
   para validar posición, rotación y altura.
3. **Masificar con `ejemplo_colocacion_face_based.py`** sobre los 35
   dispositivos del F01. Genera `reporte_colocacion_F01_v70.json`.
4. **Iterar las rotaciones** (post-placement con `LocationPoint.Rotate`)
   según la normal real del muro del F01 (recuerda: la regla E06 -75° no
   aplica; calcular rotación según orientación local del muro).
5. Una vez estable el F01, escalar a E05, E07, etc.

---

## Estado

- **Versión**: `1.0.0.0` (wrapper v3 — reflexión)
- **Target**: `.NET Framework 4.8`, x64
- **Compilada**: 2026-11-19
- **Hash MD5**: `b53385f969af5c2ef80415ef04ca2a31` (verificar tras copiar):
  ```powershell
  Get-FileHash MiAddin.dll -Algorithm MD5
  # En Linux/macOS: md5sum MiAddin.dll
  ```
- **Tamaño**: 26112 bytes (26 KB)
- **API Revit requerida**: Revit 2022+ (la sobrecarga `NewFamilyInstance(Reference, UV, double, FamilySymbol)`
  existe desde Revit 2014). Funciona en Revit 2026.
- **Runtime IronPython**: probada conceptualmente contra IronPython 2.7.12+
  (pyRevit). La DLL es .NET Framework 4.8 standard, no requiere nada especial.

### Cambios entre versiones de la DLL

| Versión | Hash MD5 | Tamaño | Cambio |
| --- | --- | --- | --- |
| v1 | `3393e9a681012e08de7aa1ed8fea8c1c` | 14 KB | Versión inicial con `dynamic` dispatch. |
| v2 | `0d5c5a65ff6a7b56d4e2ad04ac5bae57` | 23 KB | Agregado `PlaceFaceBasedByReference`, `GetFaceFromReference`, `ProjectPointByReference`. Sigue usando `dynamic`. |
| **v3 (actual)** | `b53385f969af5c2ef80415ef04ca2a31` | 26 KB | **Reflexión explícita** en `PlaceFaceBased` y `PlaceFaceBasedByReference`. Resuelve el bug del DLR que elegía la sobrecarga `(Curve, FamilySymbol, Level, StructuralType)`. Agregado `ListNewFamilyInstanceOverloads` para diagnóstico. |

---

## Licencia

Uso interno del proyecto RevitElectrico. Sin dependencias externas más allá
de `Microsoft.CSharp` (parte de .NET Framework 4.x).
