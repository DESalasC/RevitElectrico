# Esquema del proceso de ruteo de conduit — RevitElectrico

**Proyecto:** RevitElectrico · T5-SantaMarta (Torre 5, plantas eléctricas)
**Versión:** v01 · 2026-11-09
**Raíz:** `D:\Work\PROJECTS\RevitElectrico`
**Alcance:** definir y automatizar el paso de "plano eléctrico 2D" a "conduits 3D en Revit 2026" para el apartamento piloto F 02, extensible al resto.

---

## 1. Premisa corregida del problema

El plano **no hay que rutearlo desde cero**. El DXF ya trae el trazado dibujado: las polilíneas de las capas `*-PIPE-*` son las tuberías, y los bloques `1FTN`, `1FTNR`, `2FT2N`, `2F2N1T1R`, etc. son los símbolos de cableado que indican cuántos conductores lleva cada tramo.

Por tanto la tarea real es de **traducción y consistencia**, no de pathfinding:

| Lo que el plano ya dice | Lo que hay que resolver |
|---|---|
| Trazado en planta (X, Y) | Elevarlo a la cota de instalación (Z) y generar bajantes |
| Cantidad de cables por símbolo | Convertirla en diámetro de conduit según material y calibre |
| Capa de la tubería | Asignar el parámetro `Servicio_Conduit` (solo color/filtro) |
| Posición de cada aparato | Verificar que el trazado nace y muere en un aparato real |

**Regla confirmada por el operador:** la tubería es siempre del mismo tipo; el diámetro depende **solo del número de cables**. El servicio (TOMAS / ILUMINACION / COMUNICACIONES / FUERZA) es una **etiqueta de visualización** que alimenta los filtros de color de la vista *Discipline → Electrical*. Nunca cambia el diámetro.

### 1.1 Decisiones del operador (2026-11-09 09:42)

| # | Decisión | Efecto en el pipeline |
|---|---|---|
| D1 | **Los tramos de tomas van como TOMAS.** Fuerza no está definida aún dentro del apartamento. | `ELEC-POWER- PIPE` mapea a **TOMAS** (antes FUERZA). Elimina 10 avisos de discrepancia. |
| D2 | La banda arranca en **2,65 m** para librar la estructura del cielorraso, con **~10 cm de holgura** hacia arriba según los cruces. | La banda es un rango 2,65–2,75 m con **reparto por servicio**: ILUMINACION 2,65 · TOMAS 2,68 · COMUNICACIONES 2,71 · FUERZA 2,74. Se valida que ninguna cota salga del rango. |
| D3 | Antes de la luminaria va una **caja de conexión hexagonal**; de allí se conecta la luminaria. Igual para el ventilador. | Los extremos sin aparato se resuelven como **caja** cuando hay un aparato del mismo sistema dentro de 2,00 m. Se emiten como artefacto propio. |
| D4 | **Sí a la herencia de cables** por segmento. | `heredar_de_polilinea_vecina_m = 1,00` queda aprobado y activo. |
| D5 | **Comunicaciones en 3/4" fijo**: los cables de voz/datos no son 12 AWG y no vienen marcados en el DXF. | Nueva excepción `diametro_fijo_por_servicio`. COMUNICACIONES ignora la cantidad de cables. |
| D6 | **Familia de caja:** `M_Caja de conexiones hexagonal` / tipo `120V`. | Se declara en `cajas_conexion.familia` y `.tipo`; el writer la usa. |
| D7 | **La conexión caja→aparato es solo cableado**, no tubería. | La tubería termina en la caja. No se genera conduit caja→aparato. |
| D8 | El **ventilador** es el bloque `ELEC-F-VENT`, capa `ELEC-APPL-ILUM`. | Se agrega a las capas/bloques destino de caja y a las alturas. |
| D9 | Hay que **poder ver** los tramos sin resolver, o marcarlos como `FUERZA` para localizarlos. | Visor 2D + visor 3D isométrico + flag `--marcar-revision`. |

### 1.2 Insumo correcto: DXF por apartamento

El plano general `STM-T4-P4_todos_bloques_electricos.dxf` **mezcla varios apartamentos** y producía falsos positivos (6 extremos sueltos que no existen en F 02). El insumo correcto es el recorte por apartamento:

| Apartamento | Archivo | Entidades | Polilíneas | Marcadores |
|---|---|---|---|---|
| F 02 | `ArchivosBase\Apartamento Tipo F 02.dxf` | 142 | 39 | 22 |
| E 05 | `Actuales\T5-SantaMarta\3.-Proceso\ApaRtamento Tipo E 05.dxf` | — | 51 | 26 |

Con el recorte de F 02 **los 6 extremos sin resolver desaparecen**: no había nada suelto porque no lo había. El problema era del plano general.

---

## 2. Evidencia del reconocimiento (medida, no supuesta)

Sondeo sobre `ArchivosBase\STM-T4-P4_todos_bloques_electricos.dxf`:

### 2.1 Tubería dibujada

| Capa | Polilíneas | Longitud | Lectura |
|---|---|---|---|
| `ELEC-LIGHT-PIPE` | 70 | 101,5 m | Tubería de iluminación |
| `ELEC-POWER- PIPE` | 16 | 79,5 m | Tubería de fuerza / tomas |
| `ELEC-Powr-service` | 1 | — | Acometida interna |
| `ELEC-Data-Service` | 1 | 1,4 m | Comunicaciones |
| **Total** | **88** | **183,7 m** | |

### 2.2 Símbolos de cableado

| Bloque | Cables | Instancias | Desglose |
|---|---|---|---|
| `1FTNR` | 4 | 29 | 1F + 1T + 1N + 1R |
| `1FTN` | 3 | 21 | 1F + 1T + 1N |
| `1FTR` | 3 | 4 | 1F + 1T + 1R |
| `2F2N1T1R` | 6 | 4 | 2F + 2N + 1T + 1R |
| `1TNR` | 3 | 3 | 1T + 1N + 1R |
| `2FT2N` | 5 | 3 | 2F + 1T + 2N |
| **Total** | — | **64** | Rango real: 3 a 6 cables |

La nomenclatura es **parseable**: un contador opcional precede a cada letra (`F`=fase, `N`=neutro, `T`=tierra, `R`=retorno); si no hay contador, cuenta 1.

### 2.3 Calidad de la asociación

| Métrica | Valor | Interpretación |
|---|---|---|
| Distancia marcador → polilínea más cercana | mín 0,000 m · p50 0,007 m · p90 0,018 m · **máx 0,040 m** | Asociación inequívoca: ningún marcador queda lejos de su tubería |
| Polilíneas con marcador | 62 de 88 (166,4 m) | 94 % de la longitud tiene símbolo |
| Polilíneas sin marcador | 26 (17,3 m) | Tramos cortos: requieren regla de herencia o revisión |
| Extremos a ≤ 0,15 m de un aparato | 153 de 176 | 87 % del trazado nace/muere en un aparato |
| Extremos a 0,15–0,50 m | 17 | Aceptables con tolerancia |
| Extremos a > 0,50 m | 6 | Revisión manual obligatoria |
| Nodos con grado 1 | 166 de 169 | La red **no** es un árbol continuo: son tramos aparato→aparato |

### 2.4 Dos hallazgos que condicionan el diseño

1. **`ALTURA_INST` no sirve como fuente de altura.** Sus valores son `TTICS-01` (42), vacío (24), `h=1m` (20), `en muro h=2m` (15), `TTICS-02` (5). `TTICS-01/02` son identificadores de red (aparecen en la capa `Elec-Power-Iden` junto a `TZC4-01/02/03`), no cotas. Por eso las alturas se resuelven con una **tabla por capa de aparato**, editable.
2. **El JSON `apto_F_02_aplicar_mapa_v3.json` no es ground truth de coordenadas.** Al cruzarlo con el DXF dan 0/37 coincidencias y no se recupera ni por traslación (el mejor ajuste alcanza 10/37). Es un artefacto de una corrida anterior con otro recorte. La validación posicional debe hacerse **contra el RVT**, no contra ese archivo.

---

## 3. Modelo de datos

```
Dispositivo ──┐
              ├─► Tramo ──► Dimension ──► Conduit (Revit)
Marcador   ───┤
Polilinea  ───┘
```

| Entidad | Campos | Origen |
|---|---|---|
| `Dispositivo` | handle, nombre, capa, x, y, atributos | INSERT del DXF |
| `Marcador` | handle, nombre, capa, x, y, **cables**, fuente | INSERT con nomenclatura de cables |
| `Polilinea` | handle, capa, puntos[], largo | LWPOLYLINE en capas de tubería |
| `ExtremoTramo` | tipo, x, y, distancia, handle, nombre, capa, servicio, altura | Resolución geométrica |
| `Tramo` | id, servicio, cables, origen, material, calibre, diámetro, largo, cota, puntos 2D/3D, avisos | Pipeline |
| `Dimension` | cables, material, calibre, pulgadas, mm, capacidad, holgura | Tabla CSV |

Configuración separada del código: `config\ruteo_config_v01.json` (semántica) y `data\Calibre-*.csv` (capacidad física).

---

## 4. Pipeline en diez etapas

| # | Etapa | Entrada | Salida | Módulo |
|---|---|---|---|---|
| E0 | **Configuración y validación** | `ruteo_config_v01.json` + CSV | `ConfigRuteo` validado | `config.py` |
| E1 | **Extracción DXF** | `.dxf` | dispositivos, marcadores, polilíneas | `dxf_lector.py` |
| E2 | **Clasificación de marcadores** | nombre del bloque | `cables` (3…6) | `dxf_lector.cables_desde_nombre` |
| E3 | **Asociación marcador ↔ tramo** | geometría | cables + distancia | `ruteador._marcador_mas_cercano` |
| E4 | **Resolución de extremos** | polilínea + dispositivos | `ExtremoTramo` (dispositivo/libre) | `ruteador._extremo_mas_cercano` |
| E4b | **Cajas de conexión** | extremo libre + aparato del mismo sistema | `Caja` (hexagonal/octogonal) | `ruteador._resolver_caja` |
| E5 | **Servicio_Conduit** | capa + extremos | TOMAS/ILUMINACION/COMUNICACIONES/FUERZA | `servicio.py` |
| E6 | **Dimensionamiento** | cables + material + calibre | diámetro comercial | `dimensionamiento.py` |
| E7 | **Geometría 3D** | puntos 2D + cota + alturas | puntos 3D con bajantes | `ruteador._puntos_3d` |
| E7b | **Cruces en planta** | tramos de distinto sistema | lista de cruces y separación | `ruteador.detectar_cruces` |
| E8 | **Emisión** | tramos | JSON de ruteo + HTML | `reporte.py`, `cli.py` |
| E8b | **Visor** | tramos + DXF | plano SVG interactivo | `visor.py` |
| E9 | **Creación en Revit** | JSON de ruteo + ancla | conduits + `Servicio_Conduit` | `RE_RUTEAR_CONDUITS_v01.py` |
| E10 | **Validación y cierre** | modelo creado | reporte de invariantes | pendiente |

### Reglas de decisión por etapa

**E3 — asociación de cables.** Se toma el marcador cuya distancia perpendicular a la polilínea sea menor, siempre que no supere `tolerancias.asociacion_marcador_polilinea_m` (0,30 m). Si no hay ninguno:
1. hereda los cables del tramo vecino cuyos extremos estén a ≤ 1,00 m;
2. si tampoco, aplica `cables_default_sin_marcador` (3) y **marca el tramo para revisión**.

**E4 — extremos.** Aparato más cercano dentro de `asociacion_extremo_dispositivo_m` (0,50 m). Si no hay, el extremo queda como `libre` y se advierte con la distancia real.

**E4b — cajas de conexión.** Si un extremo queda libre, se busca un aparato **del mismo sistema** dentro de `cajas_conexion.radio_busqueda_m` (2,00 m). Si aparece, el extremo pasa a tipo `caja`, la tubería termina en la cota de banda y se emite una `Caja` con su posición, servicio, aparato destino y altura del aparato (para que el writer trace la bajante corta). El filtro por sistema evita cajas absurdas: un tramo de comunicaciones no genera caja de luminaria.

**E5 — servicio.** Gana el servicio de los aparatos de los extremos cuando ambos coinciden; si difieren, se aplica la prioridad configurada (COMUNICACIONES > TOMAS > ILUMINACION > FUERZA). Si no hay aparatos, manda la capa de la tubería. Toda discrepancia se registra como aviso, nunca se silencia.

**E6 — diámetro.** Se recorre la tabla del material/calibre de menor a mayor y se elige el primer diámetro cuya capacidad ≥ cables. Nunca se interpola ni se redondea "a ojo".

**E7 — geometría.** Modo `horizontal_con_bajantes`: la polilínea corre a la cota de banda del servicio (reparto 2,65–2,75 m) y en cada extremo baja/sube verticalmente hasta la altura del aparato. Modo `directo`: interpolación lineal entre las alturas de ambos extremos.

**E7b — cruces.** Se calculan las intersecciones en planta entre tramos de distinto sistema. El reparto de cotas debe garantizar que dos sistemas que se cruzan queden a distinta altura; si la separación es menor a 2 cm, se emite aviso global.

---

## 5. Tabla de equivalencias (fuente: CSV del operador)

Capacidad máxima de conductores por diámetro, **12 AWG**:

| Diámetro | PVC | PVC-SCH40 | EMT |
|---|---|---|---|
| 1/2" | 11 | 8 | 9 |
| 3/4" | 19 | 15 | 16 |
| 1" | 32 | 25 | 26 |
| 1-1/4" | 53 | 44 | 44 |
| 1-1/2" | 70 | 60 | 58 |
| 2" | 109 | 99 | 97 |

**Consecuencia verificada:** el máximo del apartamento son 6 cables. Con PVC + 12 AWG, **todos los tramos resultan en 1/2"**, salvo la excepción de COMUNICACIONES.

**Excepción vigente (D5):** las tuberías de **COMUNICACIONES se fijan en 3/4"** porque los cables de voz/datos no son 12 AWG y no aparecen marcados en el DXF. El dimensionamiento por cantidad de cables no aplica a ese servicio.

---

## 6. Contrato del JSON de ruteo

```json
{
  "version": "v01",
  "dxf": "...dwg|dxf",
  "zona": "apartamento",
  "material": "PVC",
  "calibre": "12 AWG",
  "nivel": "Piso 5",
  "elevacion_nivel_m": 43.3727,
  "ancla": {
    "bloque_dxf": "TB-Parcial", "capa_dxf": "ELEC-POWER-PANEL",
    "handle_dxf": "161", "x_dxf": -2.4724, "y_dxf": 0.5063,
    "nombre_en_revit": "TB-Parcial"
  },
  "resumen": {
    "tramos": 83, "tramos_con_marcador": 67, "tramos_sin_marcador": 16,
    "longitud_total_m": 316.24, "por_servicio": {}, "por_diametro": {}, "avisos": 38
  },
  "tramos": [{
    "id": "RT-0072", "handle_dxf": "A23A", "capa": "ELEC-POWER- PIPE",
    "servicio": "TOMAS", "cables": 3, "cables_origen": "marcador",
    "material": "PVC", "calibre": "12 AWG",
    "diametro_pulgadas": "1/2\"", "diametro_mm": 12.7,
    "largo_m": 15.325, "cota_m": 2.65, "z_absoluta_m": 46.0227,
    "puntos_3d": [[x, y, z], "..."],
    "extremos": [{"tipo": "dispositivo", "handle": "A238", "servicio": "TOMAS",
                  "altura_m": 0.3, "distancia_m": 0.104}],
    "marcadores": ["1FTN (3 cables, d=0.010 m)"],
    "avisos": []
  }]
}
```

`puntos_3d` está en **metros** y en **coordenadas de proyecto** (mismo sistema que el DXF local). El writer convierte a pies internos de Revit y suma la elevación del nivel para la cota absoluta.

---

## 7. Validaciones y criterios de aceptación

| ID | Validación | Criterio | Automatizable |
|---|---|---|---|
| V1 | Configuración coherente | servicios mapeados ⊆ permitidos; material con tabla | Sí |
| V2 | Tabla de capacidad | sin huecos ni valores no numéricos | Sí |
| V3 | Asociación de marcadores | 100 % con distancia ≤ 0,30 m | Sí |
| V4 | Cobertura de cables | ≥ 90 % de la longitud con marcador propio o heredado | Sí |
| V5 | Extremos conectados | ≥ 95 % de extremos a ≤ 0,50 m de un aparato | Sí |
| V6 | Diámetro dentro de tabla | ningún tramo fuera de capacidad | Sí |
| V7 | Servicio válido | todo tramo en los 4 valores permitidos | Sí |
| V8 | Posición en Revit | aparatos a ≤ 0,20 m de su posición en el RVT | Contra RVT |
| V9 | Sin colisiones | 0 choques con estructura/HVAC/plomería | Contra RVT |
| V10 | `Servicio_Conduit` poblado | 100 % de conduits con valor | Contra RVT |

**Estado de V1–V7:** implementadas y verdes (43 tests + corrida real).
**Estado de V8–V10:** pendientes; requieren Revit abierto.

---

## 8. Resultados de las corridas reales

### 8.1 Apartamento F 02 (DXF propio, config v04)

```
Entidades: 142   Polilíneas: 39   Dispositivos: 37   Marcadores: 22   Cables: [3, 4, 5]
Tramos: 38   (con marcador 31 | sin marcador 7)
Cajas de conexión: 0      Extremos sin resolver: 0
Cruces en planta: 2       (a la misma cota: 0)
Longitud total: 179,01 m
TOMAS 16 · 82,42 m       ILUMINACION 12 · 47,81 m       COMUNICACIONES 10 · 48,77 m
Diámetro: 1/2" 28 tramos · 3/4" 10 tramos (todas las comunicaciones)
Ancla: TB-Parcial en (-2,4724, 0,5063)
```

### 8.2 Apartamento E 05 (prueba del caso ventilador)

```
Polilíneas: 51   Dispositivos: 48   Marcadores: 26   Cables: [3, 4, 5, 6]
Tramos: 49        Cajas de conexión: 2
Cruces en planta: 4   (a la misma cota: 0)
Longitud total: 226,04 m
TOMAS 20 · 105,38 m      ILUMINACION 18 · 58,02 m      COMUNICACIONES 11 · 62,64 m
Diámetro: 1/2" 38 · 3/4" 11
```

Las **2 cajas** de E 05 apuntan a `ELEC-APPL-ILUM`, que es la capa del bloque `ELEC-F-VENT`: el caso del ventilador queda cubierto y verificado end-to-end.

### 8.3 Avisos

| Tipo | F 02 | E 05 | Acción |
|---|---|---|---|
| Diámetro fijo por servicio (informativo) | 10 | 11 | Ninguna; es D5 |
| Servicio fijado por capa (informativo) | 3 | — | Ninguna; es la regla de comunicaciones |
| Sin marcador propio, hereda de vecino | 7 | 18 | Aceptable (D4) |
| Extremos con servicios distintos | 5 | — | Revisar en el visor |
| Caja resuelta (informativo) | 0 | 2 | Ninguna |
| Tramos < 0,05 m omitidos | — | — | Esperado |

---

## 9. Estado de implementación

### Implementado y probado

| Archivo | Función |
|---|---|
| `config\ruteo_config_v01.json` | Semántica editable: servicios, alturas, tolerancias, reglas |
| `src\fase-6-revit\ruteo\modelos.py` | Entidades del dominio y serialización |
| `src\fase-6-revit\ruteo\config.py` | Carga + validación + lectura de los 3 CSV |
| `src\fase-6-revit\ruteo\dxf_lector.py` | Extracción y parseo de nomenclatura |
| `src\fase-6-revit\ruteo\servicio.py` | Resolución de `Servicio_Conduit` |
| `src\fase-6-revit\ruteo\dimensionamiento.py` | Diámetro por capacidad |
| `src\fase-6-revit\ruteo\ruteador.py` | Orquestación 2D → 3D |
| `src\fase-6-revit\ruteo\reporte.py` | Resumen consola + HTML |
| `src\fase-6-revit\ruteo\visor.py` | Visor SVG interactivo del plano con tramos en revisión |
| `src\fase-6-revit\ruteo\cli.py` | Línea de comandos |
| `src\fase-6-revit\RE_RUTEAR_CONDUITS_v01.py` | Writer pyRevit con `dry_run` y offset por ancla |
| `tests\test_ruteo_v01.py` | 55 pruebas |

### Pendiente

1. **E9 en vivo:** ejecutar el writer con `dry_run=True` sobre `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V03.rvt` y revisar el reporte antes de crear.
2. **V8:** validación posicional contra el RVT (no contra el JSON viejo).
3. **Corredores:** definir EMT vs PVC-SCH40 y su cota de bandeja.
4. **Extremos libres:** decidir si los 6 extremos > 0,50 m son cajas de paso que deben modelarse o errores del plano.
5. **E10:** invariantes post-creación (V9, V10).
6. **Resto de apartamentos:** replicar con `--dxf` por bloque.

---

## 10. Decisiones

| # | Decisión | Estado |
|---|---|---|
| D1 | Servicio de los tramos de tomas | ✅ TOMAS |
| D2 | Cota de banda | ✅ 2,65 m + 10 cm con reparto por servicio |
| D3 | Extremos sin aparato | ✅ Cajas de conexión |
| D4 | Herencia de cables | ✅ Aprobada |
| D5 | Comunicaciones 3/4" | ✅ Fijado |
| D6 | Familia de caja | ✅ `M_Caja de conexiones hexagonal` / `120V` |
| D7 | Conexión caja→aparato | ✅ Solo cableado |
| D8 | Ventilador | ✅ `ELEC-F-VENT` / `ELEC-APPL-ILUM` |
| D9 | Visualización de tramos en revisión | ✅ Visor + `--marcar-revision` |
| D10 | Material y cota de **corredores** (EMT vs PVC-SCH40) | ⏳ Pendiente |
| D11 | ¿La caja se crea también cuando el trazado **sí llega** al aparato? | ⏳ Pendiente |
| D12 | Circuito/red por tramo (atributo `RED`) para agrupar en Revit | ✅ Implementado: texto de circuito (`TF-*`) leído de la capa `Elec-Power-Iden` y asociado al tramo más cercano |

---

## 11. Cómo se opera

```powershell
# 1. Generar el ruteo del apartamento (sin Revit)
& "D:\Work\PROJECTS\DiseñoParametrico\.venv\Scripts\python.exe" `
  "D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\ruteo\cli.py"

# 2. Ver el plano con los tramos resaltados
start data\visor_ruteo_F02_v03.html
start data\ruteo_apartamento_F02_v03.html

# 3. Otro apartamento, mismo pipeline
python cli.py --dxf "...\ApaRtamento Tipo E 05.dxf" `
  --out data\ruteo_E05.json --visor data\visor_E05.html

# 4. Marcar los tramos sin resolver como FUERZA para verlos en Revit
python cli.py --marcar-revision FUERZA

# 5. Simular en Revit (pyRevit Python Shell)
exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\RE_RUTEAR_CONDUITS_v01.py").read())
rutear_conduits(doc, dry_run=True)

# 6. Crear los conduits cuando el operador apruebe
rutear_conduits(doc, dry_run=False)
```

Cambiar de zona sin tocar código:

```powershell
python cli.py --zona corredor_emt --out data\ruteo_corredor_v01.json
```

### Visor

El visor dibuja el plano completo en un SVG autocontenido: tuberías por servicio, aparatos, marcadores con su número de cables y cajas. Los tramos en revisión salen en magenta con trazo animado y se listan en el panel derecho; al hacer clic en uno se hace zoom sobre él. Doble clic en el plano restaura la vista. Los filtros por servicio y el interruptor "solo revisión" permiten aislar redes.
