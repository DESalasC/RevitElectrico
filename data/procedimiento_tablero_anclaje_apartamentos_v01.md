# Procedimiento Operativo — Modelado de apartamentos DXF por tablero-anclaje (Apartamento Tipo nn)

**Proyecto:** RevitElectrico — T5-SantaMarta  
**Versión:** v01  
**Fecha:** 2026-10-28  
**Alcance:** 16 bloques DXF de apartamentos separados en `3.-Proceso\`  
**Regla clave:** No destructivo. Solo se documenta y propone; no se borra ni modifica ninguna instancia existente salvo autorización expresa.

---

## 1. Estructura de datos observada

### 1.1 Los 16 archivos DXF de apartamentos (en `3.-Proceso\`)

| # | Archivo DXF | Nombre en `inserts_apartamentos_v3.json` |
|---|-------------|------------------------------------------|
| 1 | `Apartamento Tipo B 15.dxf` | Apartamento Tipo B 15 |
| 2 | `Apartamento Tipo B 16.dxf` | Apartamento Tipo B 16 |
| 3 | `Apartamento Tipo C 11.dxf` | Apartamento Tipo C 11 |
| 4 | `Apartamento Tipo D 12.dxf` | Apartamento Tipo D 12 |
| 5 | `Apartamento Tipo E 05.dxf` (escrito "Apatamento") | Apatamento Tipo E 05 |
| 6 | `Apartamento Tipo E 06.dxf` | Apartamento Tipo E 06 |
| 7 | `Apartamento Tipo E 07.dxf` | Apartamento Tipo E 07 |
| 8 | `Apartamento Tipo E 08.dxf` | Apartamento Tipo E 08 |
| 9 | `Apartamentos Tipo E 09.dxf` | Apartamentos Tipo E 09 |
| 10 | `Apatamentos Tipo E 10.dxf` (escrito "Apatamentos") | Apatamentos Tipo E 10 |
| 11 | `Apartamento Tipo E2 19.dxf` | Apartamento Tipo E2 19 |
| 12 | `Apartamento Tipo E 20.dxf` | Apartamento Tipo E 20 |
| 13 | `Apartamento Tipo E2 21.dxf` | Apartamento Tipo E2 21 |
| 14 | `Apartamento Tipo F 01.dxf` | Apartamento Tipo F 01 |
| 15 | `Apartamento Tipo F 02.dxf` (piloto) | Apartamento Tipo F 02 |
| 16 | `Apartamento Tipo F 17 y 03.dxf` / `Apartamentos Tipo F 18 y 04.dxf` | F 17 y 03 · F 18 y 04 (2 bloques en 2 archivos) |

**Nota:** hay inconsistencias de ortografía en los nombres ("Apatamento" vs "Apartamento", "Apatamentos" vs "Apartamentos"). Deben normalizarse con una tabla de alias antes de usar como clave.

**Tableros oficiales (confirmado por el usuario, 2026-10-28):** solo hay dos tableros modelados manualmente en Revit: **TF 01** (Apartamento Tipo F 01) y **TF 02** (Apartamento Tipo F 02). Los otros tres `TB-Parcial` registrados en `resultado_tb_parcial.json` (ids 898725, 898726, 898727, 898728 además del 898724) son sobrantes y se pueden eliminar. El tablero oficial del F 02 es el id **867008** (familia `E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN`, símbolo `EPB25-304C`, `z_revit=1.2` como altura local) registrado en `apto_F_02_aplicar_mapa_v3_resultado.json`.

### 1.2 Estructura interna de cada bloque DXF

Cada archivo DXF de apartamento contiene:
- Un **bloque padre** (el contenedor del apartamento) con un punto de inserción (insert_padre_x, insert_padre_y).
- **Bloques hijo** anidados dentro: tomas, interruptores, lámparas, ventiladores, tablero, marcadores de conductor, etc.
- Cada bloque hijo tiene: `nombre_bloque_hijo`, `capa`, `x_abs_dxf`, `y_abs_dxf`, `x_revit`, `y_revit`, `rotacion`, `orden`.

### 1.3 Ejemplo concreto — Apartamento Tipo F 02 (piloto)

Desde `apartamento_F_02_dispositivos.json`:
- `bloque_padre`: "Apatamento Tipo F 02"
- `inserts_padre`: {(0.0, 0.0)} — el apartamento F02 se inserta en origen local
- `dispositivos_internos`: lista de bloques hijo con coordenadas absolutas en el DXF

Desde `apto_F_02_aplicar_mapa_v3.json`:
- 59 bloques totales: 37 a modelar (dispositivos físicos), 22 a saltar (marcadores de conductor: 1FTN, 1TNR, 1FTNR, 2FT2N, 1FTN2R, 1TN2R, 1FTR)
- El tablero `TB-Parcial` está en orden 26, capa `ELEC-POWER-PANEL`, familia `E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN`, símbolo `EPB25-304C`, anfitrión muro, z_local = 1,2 m

---

## 2. Problema a resolver

1. **El tablero/panel no está necesariamente identificado como anclaje** dentro de cada bloque DXF. Puede estar mezclado con otros dispositivos hijos sin un rol especial asignado.
2. **Los bloques hijo (tomas, interruptores, lámparas, ventiladores) son entidades separadas** en el DXF. La pregunta es si se modelan por separado y luego se unifican en Revit bajo el anclaje del tablero de su apartamento.
3. **Hay un offset sistemático** entre el sistema de coordenadas local del apartamento (DXF) y el sistema global de Revit. En `reporte_desviaciones_electricas.json`: desv_x media 0,1559 m, desv_y media −1,1301 m, dist_xy media 2,69 m. Ninguno de los 59 dispositivos del F02 está dentro de 0,15 m de su posición DXF.
4. **No hay offset documentado** entre sistema local del apartamento y sistema global de Revit.

---

## 3. Propuesta de procedimiento operativo

### Principio general
Cada bloque DXF de apartamento se trata como una **unidad de modelado autocontenida**:
- El **tablero/panel** de ese apartamento es el **punto de anclaje (origin)** dentro de Revit.
- Todos los demás componentes (tomas, interruptores, lámparas, ventiladores) se posicionan **relativamente al tablero** de su mismo apartamento.
- Los marcadores de conductor no se modelan como FamilyInstance; solo se usan para calcular conduits.

### Paso 0 — Inventario y normalización (no destructivo, solo lectura)

1. Leer los 16 archivos DXF de apartamentos de `3.-Proceso\`.
2. Para cada uno, extraer:
   - Nombre del bloque padre (normalizar ortografía: "Apatamento" → "Apartamento").
   - Punto de inserción del bloque padre (insert_padre_x, insert_padre_y).
   - Lista de bloques hijo con nombre, capa, coordenadas, rotación.
3. Identificar el **bloque hijo del tablero/panel** en cada apartamento (capa `ELEC-POWER-PANEL` o nombre `TB-Parcial`, `TB-`, `Panel`, etc.).
4. Generar un JSON maestro: `data/inventario_apartamentos_v01.json` con la estructura definida en §5.

### Paso 1 — Colocación del tablero-anclaje en Revit (manual, una vez por apartamento)

Para cada uno de los 16 apartamentos:

1. Localizar el tablero en el modelo Revit existente (o colocarlo manualmente si no existe).
2. Verificar que tenga:
   - Familia de panel eléctrico (categoría `Electrical Equipment`).
   - Símbolo identificable (p. ej. `EPB25-304C` para el F02).
   - `LevelId` válido (nivel del piso correspondiente).
   - `Comments` con identificador único: `TAB-<tipo>-<nro>-P<piso>` (ej: `TAB-F-02-P5`).
   - `RED=SI` en `Comments` si es dispositivo de red.
3. Registrar su posición real en Revit: `x_tablero_revit`, `y_tablero_revit`, `z_tablero_revit` (absoluta, pies).
4. **No mover ni modificar ningún otro componente** salvo el tablero de este apartamento.

### Paso 2 — Cálculo de offset relativo por apartamento

Para cada apartamento, calcular el offset entre el sistema local del DXF y la posición real del tablero en Revit:

```
offset_x = x_tablero_revit - x_tablero_dxf
offset_y = y_tablero_revit - y_tablero_dxf
offset_z = z_tablero_revit - z_tablero_dxf   (siempre 0 si mismo nivel)
```

Dado que el DXF usa sistema local (origen en esquina del bloque) y Revit usa sistema global, este offset absorbe la desviación sistemática observada (desv_x ~0,06 m, desv_y ~−2,02 m en el F02).

### Paso 3 — Posicionamiento de componentes internos (relativo al tablero)

Para cada bloque hijo del apartamento (excepto el tablero y los marcadores de conductor):

```
x_revit = x_tablero_revit + (x_hijo_dxf - x_tablero_dxf) + offset_x
y_revit = y_tablero_revit + (y_hijo_dxf - y_tablero_dxf) + offset_y
z_revit = nivel.Elevation + z_local_hijo   (altura local de montaje)
```

Esto equivale a: **posición relativa al tablero en DXF, trasladada a la posición real del tablero en Revit**.

### Paso 4 — Tratamiento de componentes internos: separados luego unificados

**Respuesta a la pregunta del usuario:** Sí, los bloques hijo (tomas, interruptores, lámparas, ventiladores) deben tratarse como **entidades separadas** durante la lectura del DXF (cada uno con su propia familia, símbolo, altura, rotación), y luego **unificarse en Revit** bajo el mismo apartamento mediante:
- Mismo `LevelId` (nivel del piso).
- Mismo identificador de apartamento en `Comments` (ej: `APT-F-02-P5`).
- Posicionamiento relativo al tablero-anclaje de ese apartamento.

Esto permite:
- Rastrear cada componente hasta su bloque hijo DXF de origen.
- Verificar que todos los componentes de un apartamento compartan el mismo tablero-anclaje.
- Detectar componentes huérfanos (sin tablero de referencia en su apartamento).

### Paso 5 — Registro de desviaciones (auditoría)

Para cada dispositivo modelado, registrar en su `Comments` o en un reporte JSON paralelo:

| Campo | Descripción |
|-------|-------------|
| `desv_x` | x_modelo − x_dxf_esperado (m) |
| `desv_y` | y_modelo − y_dxf_esperado (m) |
| `desv_z` | z_modelo − z_dxf_esperado (m) |
| `dist_xy` | distancia planar total de desviación |
| `match` | cómo se emparejó: `nombre`, `capa`, `posicion_relativa_tablero` |
| `origen` | `DXF_<archivo>`, `manual`, `anclaje_tablero` |
| `tablero_ancla` | `TAB-<tipo>-<nro>-P<piso>` |
| `apartamento` | `APT-<tipo>-<nro>-P<piso>` |

Esto permite auditar qué tan lejos quedó cada componente de su posición teórica en el DXF.

### Paso 6 — Repetir para los 16 apartamentos

Iterar sobre los 16 archivos DXF, aplicando los pasos 0–5 a cada uno. Generar un reporte consolidado por apartamento.

---

## 4. Estructura de datos propuesta (JSON maestro)

Archivo: `data/inventario_apartamentos_v01.json`

```json
{
  "version": "v01",
  "proyecto": "RevitElectrico - T5-SantaMarta",
  "fecha_analisis": "2026-10-28",
  "total_apartamentos": 16,
  "apartamentos": [
    {
      "nombre_normalizado": "Apartamento Tipo F 02",
      "nombre_dxf_original": "Apartamento Tipo F 02.dxf",
      "piso": 5,
      "nivel_revit": "Piso 5",
      "elevacion_nivel_m": 43.3727,
      "insert_padre_dxf": {"x": 0.0, "y": 0.0},
      "tablero": {
        "nombre_bloque_hijo": "TB-Parcial",
        "capa": "ELEC-POWER-PANEL",
        "familia_revit": "E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN",
        "simbolo": "EPB25-304C",
        "x_dxf": 3.8547,
        "y_dxf": 2.7172,
        "z_local_m": 1.2,
        "z_absoluta_m": 44.5727,
        "elemento_id_revit": "867008",
        "identificador_ancla": "TAB-F-02-P5"
      },
      "dispositivos_hijos": [
        {
          "nombre_bloque_hijo": "ELEC-T-GFCI-t-15A",
          "capa": "ELEC-APPL-TOMAS",
          "familia_revit": "M_Toma doble",
          "simbolo": "GFCI",
          "x_dxf": 2.822,
          "y_dxf": 8.7015,
          "z_local_m": 0.3,
          "anfitrion": "muro",
          "rotacion": 0,
          "orden": 0
        }
      ],
      "marcadores_conductor": [
        {"nombre_bloque_hijo": "1FTN", "capa": "ELEC-Powr-Pipe-Idem Piso", "x_dxf": 6.1119, "y_dxf": 4.038}
      ],
      "offset_calculado": {"offset_x": null, "offset_y": null, "nota": "pendiente de colocación manual del tablero en Revit"}
    }
  ]
}
```

---

## 5. Reglas de nombrado y metadatos

- **Identificador de apartamento:** `APT-<tipo>-<nro>-P<piso>` (ej: `APT-F-02-P5`). Se guarda en `Comments` de cada dispositivo del apartamento.
- **Identificador de tablero-ancla:** `TAB-<tipo>-<nro>-P<piso>` (ej: `TAB-F-02-P5`). Se guarda en `Comments` del tablero y se referencia en cada dispositivo hijo.
- **RED=SI:** se mantiene en `Comments` para dispositivos de red (capa `ELEC-APPL-NETWORD`), sin crear shared parameters (regla CLAUDE.md).
- **z_revit en JSON:** siempre altura local de montaje (m), nunca Z absoluta. La Z absoluta se calcula como `nivel.Elevation + z_local`.
- **Coordenadas DXF:** sistema local del apartamento (origen en esquina del bloque).
- **Coordenadas Revit:** sistema global del edificio (pies). Se usa offset relativo desde el tablero.

---

## 6. Script propuesto (no destructivo)

Se recomienda crear un script externo (Python 3.12, sin Revit) para generar el inventario y los offsets:

`src/fase-1-contexto/RE_INVENTARIO_APARTAMENTOS_v01.py`

Funciones:
1. `extraer_bloques_dxf(ruta_dxf)` → lee un DXF de apartamento, identifica bloque padre, tablero, dispositivos hijo, marcadores.
2. `normalizar_nombre(nombre)` → corrige "Apatamento" → "Apartamento", etc.
3. `calcular_offset_relativo(tablero_dxf, tablero_revit)` → devuelve offset_x, offset_y.
4. `generar_inventario(lista_dxf, mapeo_inserts)` → produce `data/inventario_apartamentos_v01.json`.

Este script **no toca el modelo Revit**; solo genera el plan de modelado. La colocación real del tablero en Revit es manual (Paso 1) y la creación de FamilyInstance se haría con un script de Fase 6 posterior, autorizado por usted.

---

## 7. Próximos pasos (pendiente de su decisión)

1. ¿Está de acuerdo con este procedimiento de tablero-anclaje y tratamiento de componentes internos como entidades separadas luego unificadas?
2. ¿Quiere que cree el script `RE_INVENTARIO_APARTAMENTOS_v01.py` para leer los 16 DXF y generar el inventario JSON (solo lectura, no destructivo)?
3. ¿Quiere que defina primero cuál es el tablero correcto de cada apartamento (hay 4 instancias de `TB-Parcial` en `resultado_tb_parcial.json` para el F02; hay que confirmar cuál es el anclaje oficial)?

Quedo a la espera de su indicación antes de escribir cualquier script o tocar el modelo.
