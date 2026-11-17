# Plan de desarrollo — Ruteo por patrón desde V02-f

Fecha: 2026-11-17 · Proyecto: RevitElectrico · Estado: propuesta para aprobación

## 1. Decisión propuesta

**Usar V02-f como patrón y corpus de calibración, no como plantilla para copiar.**

Copiar los 147 tramos resuelve F 01 y F 02 en una tarde, pero:

- solo sirve para esos dos apartamentos;
- hereda sus defectos: 3 tramos a z = 288,22 m (uno fuera del edificio), 5 tramos sin
  `Servicio_Conduit`, 1 caja a 28,9 m de altura;
- los dos documentos **no comparten coordenadas exactas**: 18 de 20 tableros coinciden dentro de
  50 mm (mediana 32 mm), pero TE 07 está a **451 mm** y TE 08 a **368 mm** del mismo tablero en
  V02-f. Una copia rígida reproduce ese desfase en los aparatos.

El patrón, en cambio, obliga a escribir las reglas que el operador aplicó a mano. Cuesta más
sesiones ahora, pero es lo único que sirve para las 18 unidades restantes.

**No propongo «aprender» del modelo con estadística.** Propongo destilar reglas explícitas
(geometría, banda de altura, cajas, diámetro por cables), escribirlas en configuración y usar el
ruteo manual solo para **medir** si el motor se parece. Un patrón sin especificación no es
verificable.

## 2. Lo que el patrón tiene que explicar

Del análisis de V02-f (medido, no supuesto):

| Magnitud | Referencia |
|---|---|
| Tramos del corpus | **139** (de 147: 3 fuera de rango + 5 sin servicio) |
| Longitud | **132,911 m** |
| Dispositivos | 84: **66 aparatos + 18 cajas** |
| Longitud por aparato | 132,911 / 66 = **2,014 m/aparato** |
| Tramos por aparato | 139 / 66 = **2,106** |
| Servicios | TOMAS 63 · ILUMINACIÓN 46 · COMUNICACIONES 17 · FUERZA 13 |
| Diámetros | 16 mm (1/2") 4 · 21 mm (3/4") 93 · 27 mm (1") 42 |
| Accesorios (fittings) | 88 |
| Altura de banda | 2,65–2,75 m (`ruteo_config_v04`) |
| Radio de curvatura | 0,15 m · separación mínima 0,05 m |

**Hueco del benchmark:** el DXF de F 01 y F 02 tiene **36 aparatos por unidad** (72 en total); el
modelo manual tiene **33 por unidad** (66). Faltan **3 aparatos por apartamento**. Es la razón
principal para crear desde el DXF y no copiar: copiar V02-f habría dejado ese hueco dentro del
corpus.

Estas cifras son el criterio de aceptación del motor, no un adorno.

## 3. Fases

### F0 — Limpiar y congelar el corpus (1 sesión)

1. Excluir los 3 tramos fuera de rango y la caja a 28,9 m.
2. Excluir los 5 tramos sin servicio (decisión del operador, 2026-11-17).
3. Congelar el corpus con hash en `data/referencia/ruteo_F01_F02_v01/`.

**Estado: hecho.** `RE_F0_CONGELAR_CORPUS_v01.py` produce 139 tramos, 132,911 m, 66 aparatos y 18
cajas, con `MANIFEST.json` y hashes SHA-256. 4 tests.

### F1 — Correspondencia entre documentos (0,5 sesión)

1. Tabla tablero V02-f ↔ CENTRAL-V01 por posición, no por nombre (los nombres cambiaron: `TD 06`
   en V02-f es `TE 06` en CENTRAL-V01).
2. Offset por apartamento; verificar que la dispersión interna es ≤ 5 mm.
3. Documentar los dos outliers (TE 07 +451 mm, TE 08 +368 mm) como paneles movidos.

**Aceptación:** cada tablero con su par y su offset; ningún pareo por nombre.

### F2 — Instalar F 01 y F 02 en CENTRAL-V01 (1 sesión)

1. Copiar los 85 dispositivos (42 + 43) desde V02-f con tipo, cota y host, aplicando el offset de
   F1. Las 19 cajas **no** se copian: las crea el ruteo.
2. Validar: conteo por familia|tipo, cota contra nivel, distancia al muro, lado respecto al host.
3. No guardar hasta que el operador lo vea.

**Aceptación:** 85/85 colocados, 0 duplicados a 0,10 m, cotas dentro de 20 mm, oráculo de lado sin
volteados.

### F3 — Motor de ruteo (3–4 sesiones)

1. Entrada: dispositivos + servicio + cantidad de cables (del marcador del DXF).
2. Salida: polilíneas ortogonales por servicio, en la banda 2,65–2,75, con bajantes verticales.
3. Reglas de `ruteo_config_v04` ya escritas: cajas en extremos sin aparato, conexión caja→aparato
   solo cableado, diámetro por cantidad de cables, separación entre servicios.
4. Tests con casos sintéticos (una toma, dos tomas enfrentadas, cruce de dos servicios, bajante).

**Aceptación:** suite del motor en verde y ejecución determinista (misma entrada, misma salida).

### F4 — Calibrar contra el corpus (1–2 sesiones)

Correr el motor sobre F 01/F 02 y comparar contra el ruteo manual:

| Métrica | Tolerancia propuesta |
|---|---|
| Cobertura (aparato con extremo ≤ 500 mm) | 100 % |
| Longitud total | ±20 % de 132,911 m |
| Tramos por aparato | 1,7 – 2,5 |
| Cruces a la misma cota | 0 |
| Diámetro por servicio | igual al de referencia en ≥ 90 % de tramos |

**Aceptación:** las cinco métricas dentro de tolerancia, o desviación explicada y aceptada por el
operador.

### F5 — E 06 como validación (1 sesión)

E 06 no tiene ruteo manual: no sirve para comparar longitud. Sirve para comprobar que el motor
respeta cotas, hosts y servicios en un apartamento distinto, y que no inventa tramos donde no hay
aparato.

**Aceptación:** 47/47 aparatos con ruta, cotas correctas, 0 tramos huérfanos, revisión visual del
operador.

## 4. Riesgos

| Riesgo | Mitigación |
|---|---|
| El motor no reproduce el criterio del operador (codos, cruces) | Calibrar con F4 antes de tocar otras unidades; el operador aprueba la tabla de métricas |
| Los paneles se mueven entre documentos | F1: offset por posición, re-medido en cada corrida; nunca por nombre |
| El patrón se sobreajusta a F 01/F 02 | Validar en E 06 (F5) antes de extender a las 18 restantes |
| Los 5 tramos sin servicio esconden una regla no escrita | Resolverlos en F0, no ignorarlos |

## 5. Lo que necesito del operador

1. Aprobar el enfoque (patrón + métricas) frente a la copia directa.
2. Decidir los 5 tramos sin servicio de V02-f.
3. Confirmar la tabla de tolerancias de F4.
4. Revisar F 01/F 02 instalados antes de guardar.

## 6. Lo que este plan no hace

- No copia los 147 tramos.
- No toca los otros 18 apartamentos hasta cerrar F4 y F5.
- No modifica V02-f: es de solo lectura y sigue siendo el benchmark.
