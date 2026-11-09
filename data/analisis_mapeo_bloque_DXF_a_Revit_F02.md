# Análisis de mapeo Bloque DXF → Dispositivo Revit — Piloto Apartamento Tipo F 02

**Proyecto:** RevitElectrico — T5-SantaMarta  
**Documento:** `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V01` (solo lectura)  
**Nivel destino:** Piso 5 — elevación 43,3727 m  
**Fecha:** 2026-10-28  
**Alcance:** No destructivo. Solo las 37 instancias del catálogo de intervención (bloque piloto F02).  
**Versión de mapeo:** v3 (`MAPA_BLOQUES_REVIT_v3.json` → `apto_F_02_aplicar_mapa_v3.json`)  
**Scripts de referencia:** `RE_APLICAR_MAPA_V3_REVIT_v02.py`, `F6_CORREGIR_UBICACION_ELECTRICA_v01.py`

---

## 1. Resumen ejecutivo

El bloque piloto "Apartamento Tipo F 02" del DXF fuente contiene 59 bloques eléctricos. De esos, **37 son dispositivos físicos a modelar** y **22 son marcadores de conductor que se saltan** (no son FamilyInstance ni conduit).

El reporte `apto_F_02_aplicar_mapa_v3.json` trae `z_revit` como **altura local de montaje** (0,3 / 1,1 / 1,2 / 2,6 m). El script original la usó como **Z absoluta**, dejando los 36 dispositivos no-tablero enterrados entre −0,08 m y 2,6 m (planta baja) en lugar de a 43,3727 m + altura local. Solo el tablero (TB-Parcial, orden 26) quedó bien ubicado a Z 44,57 m.

La transformación no destructiva a documentar y replicar es:

```
Z_absoluta_pies = (elevacion_nivel_m + altura_local_m) * 3,28084
```

donde `elevacion_nivel_m = 43,3727` (nivel "Piso 5") y `altura_local_m` es el `z_revit` del JSON del bloque DXF.

Ninguna instancia fuera del catálogo de intervención (37 dispositivos del piloto F02) puede ser borrada ni modificada. Quedan intactas: Medidor HS, componentes similares y cualquier otro elemento del modelo.

---

## 2. Transformación documentada por familia y altura local

Las 37 acciones de modelado se agrupan por familia, anfitrión y altura local. La Z absoluta resultante se calcula como `nivel.Elevation + altura_local`, convertida de metros a pies para Revit.

| Altura local (m) | Familias afectadas | Cantidad | Ejemplo Z absoluta (m) | Z absoluta (pies) |
|------------------|--------------------|----------|------------------------|-------------------|
| 0,3 | `M_Toma doble`, `M_Toma simple`, `M_Toma resistente a la intemperie` | 26 | 43,6727 | 143,2832 |
| 1,1 | `M_Interruptor bipolar`, `M_Interruptor` | 7 | 44,4727 | 145,9078 |
| 1,2 | `E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN` (TB-Parcial) | 1 | 44,5727 | 146,2360 |
| 2,6 | `M_Ventilador`, `COMBO MOUNTING RING` (luminarias techo), `M_Interruptor` (ELEC-CAMPANA) | 10 | 45,9727 | 150,8290 |

**Anfitrión:**
- 27 dispositivos a **muro** (`anfitrion == "muro"`): `NewFamilyInstance(level, ...)` — LevelId asignable, nivel "Piso 5".
- 10 dispositivos a **techo** (`anfitrion == "ceiling"`): `NewFamilyInstance(face, ...)` — face-based, LevelId read-only, no se les puede asignar nivel (comportamiento esperado de Revit).

**Desglose detallado de las 37 acciones (orden → bloque → familia → altura local → Z absoluta):**

| Ord | Bloque DXF | Familia Revit | Símbolo | Anfitrión | z_local (m) | Z_abs (m) | Elemento Revit creado |
|-----|------------|---------------|---------|-----------|-------------|-----------|----------------------|
| 0 | ELEC-T-GFCI-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 866982 |
| 1 | ELEC-T-D-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 866983 |
| 2 | ELEC-T-D-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 866984 |
| 3 | ELEC-T-GFCI-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 866985 |
| 4 | ELEC-T-D-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 866986 |
| 5 | ELEC-T-D-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 866987 |
| 6 | ELEC-T-D-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 866988 |
| 7 | ELEC-T-GFCI-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 866989 |
| 8 | ELEC-TIMBRE | M_Interruptor bipolar | Estándar | muro | 1,1 | 44,4727 | 866990 |
| 9 | ELEC-CAMPANA | M_Interruptor | Puerta motorizada | ceiling | 2,6 | 45,9727 | 866991 |
| 10 | ELEC-I-S-2-5A | M_Interruptor bipolar | Estándar | muro | 1,1 | 44,4727 | 866992 |
| 11 | ELEC-I-S-1-5A | M_Interruptor bipolar | Estándar | muro | 1,1 | 44,4727 | 866993 |
| 12 | ELEC-I-S-1-5A | M_Interruptor bipolar | Estándar | muro | 1,1 | 44,4727 | 866994 |
| 13 | ELEC-I-S-1-5A | M_Interruptor bipolar | Estándar | muro | 1,1 | 44,4727 | 866995 |
| 14 | ELEC-F-VENT | M_Ventilador | Estándar | ceiling | 2,6 | 45,9727 | 866996 |
| 15 | ELEC-F-CONTROL | M_Interruptor bipolar | Estándar | muro | 1,1 | 44,4727 | 866997 |
| 16 | ELEC-T-GFCI-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 866998 |
| 17 | ELEC-EXT | M_Toma resistente a la intemperie | Estándar | muro | 0,3 | 43,6727 | 866999 |
| 18 | Bala Stil Led 22W | COMBO MOUNTING RING | trimless 064-1906700 | ceiling | 2,6 | 45,9727 | 867000 |
| 19 | Bala Stil Led 22W | COMBO MOUNTING RING | trimless 064-1906700 | ceiling | 2,6 | 45,9727 | 867001 |
| 20 | Bala Stil Led 10W | COMBO MOUNTING RING | trimless 064-1906300 | ceiling | 2,6 | 45,9727 | 867002 |
| 21 | Bala Stil Led 10W | COMBO MOUNTING RING | trimless 064-1906300 | ceiling | 2,6 | 45,9727 | 867003 |
| 22 | Bala Stil Led 10W | COMBO MOUNTING RING | trimless 064-1906300 | ceiling | 2,6 | 45,9727 | 867004 |
| 23 | Bala Stil Led 10W | COMBO MOUNTING RING | trimless 064-1906300 | ceiling | 2,6 | 45,9727 | 867005 |
| 24 | Bala Stil Led 13W | COMBO MOUNTING RING | trimless 064-1906500 | ceiling | 2,6 | 45,9727 | 867006 |
| 25 | Bala Stil Led 13W | COMBO MOUNTING RING | trimless 064-1906500 | ceiling | 2,6 | 45,9727 | 867007 |
| 26 | TB-Parcial | E_Distribution Panel_MEPcontent_ABB_Protecta Compact_INT-EN | EPB25-304C | muro | 1,2 | 44,5727 | 867008 |
| 42 | ELEC-TEL | M_Toma simple | Estándar | muro | 0,3 | 43,6727 | 867009 |
| 43 | ELEC-TEL | M_Toma simple | Estándar | muro | 0,3 | 43,6727 | 867010 |
| 44 | ELEC-TEL | M_Toma simple | Estándar | muro | 0,3 | 43,6727 | 867011 |
| 45 | ELEC-NET-PAU | M_Toma simple | Estándar | muro | 0,3 | 43,6727 | 867012 |
| 46 | ELEC-TEL | M_Toma simple | Estándar | muro | 0,3 | 43,6727 | 867013 |
| 47 | ELEC-TEL | M_Toma simple | Estándar | muro | 0,3 | 43,6727 | 867014 |
| 48 | ELEC-TEL | M_Toma simple | Estándar | muro | 0,3 | 43,6727 | 867015 |
| 49 | ELEC-TEL | M_Toma simple | Estándar | muro | 0,3 | 43,6727 | 867016 |
| 50 | ELEC-T-D-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 867017 |
| 56 | ELEC-T-D-t-15A | M_Toma doble | GFCI | muro | 0,3 | 43,6727 | 867018 |

**Totales:** 37 elementos creados, 0 fallos (resultado de `apto_F_02_aplicar_mapa_v3_resultado.json`, ejecutado 2026-10-24 01:27:48).

---

## 3. Contraste con el estado actual del modelo (diagnóstico de visibilidad F02)

El archivo `data/diagnostico_visibilidad_f02.json` reporta el estado del documento `E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V01`:

| Métrica | Valor |
|---------|-------|
| Vista activa | "Piso 5" (ViewPlan, id 192513) |
| Total vistas | 123 |
| Total niveles | 24 |
| Instancias RED=SI | 37 |
| Conteo por categoría | Electrical Fixtures: 22, Lighting Fixtures: 8, Electrical Equipment: 1, Lighting Devices: 6 |

Los 37 dispositivos creados tienen `nivel_id = null` (nivel nulo) en el diagnóstico de visibilidad. Esto es esperado para los 10 dispositivos face-based (techo) — su LevelId es read-only en Revit. Los 27 de muro deberían tener nivel "Piso 5" asignable.

Las instancias `fuera_de_nivel` reportadas en `data/corregir_ubicacion_electrica_v01.json` (modo simulación) incluyen 130 instancias eléctricas de todo el documento (127 sin nivel, 3 con z bajo nivel, además de Medidor HS y otros). **Ninguna de esas 130 está dentro del alcance de este análisis salvo las 37 del piloto F02.** Las instancias de Medidor HS (id 1839851, 1839852, 2278155, 2278156, 2279417, 2279418, 2280679, 2280680, 3259051, 3259052, 3298063, 3298363, 3298366, 3681748, 3681749, 3689064, 3689065, 3298420) **no se tocan** — están fuera del catálogo de intervención.

---

## 4. Replicación para otros bloques "Apartamento Tipo nn"

El DXF fuente contiene 19 definiciones de apartamento (21 pisos; algunas agrupadas, p. ej. "F 17 y 03", "F 18 y 04"). Para replicar la transformación en cada bloque:

1. **Extraer por bloque:** generar un JSON de dispositivos por tipo de apartamento (`data/bloques/<tipo>.json`), con los mismos campos que `apto_F_02_aplicar_mapa_v3.json` (`nombre_bloque`, `x_revit`, `y_revit`, `z_revit`, `familia`, `simbolo`, `anfitrion`, `nivel_revit`, `metodo_instancia`).
2. **Aplicar la transformación:** para cada acción con `z_revit` definido, calcular `Z_absoluta = (nivel.Elevation_piso + z_revit) * 3,28084` (pies).
3. **Crear FamilyInstance:** muro → `NewFamilyInstance(level, ...)` con LevelId válido; techo → `NewFamilyInstance(face, ...)` face-based (sin nivel asignable).
4. **Asignar nivel:** para dispositivos de muro, asignar LevelId del nivel destino del piso correspondiente.
5. **Verificar:** `z_relativo_nivel` en {0,3, 1,1, 1,2, 2,6} ± 0,05 m; 0 instancias `sin_nivel` dentro del bloque intervenido.

**Regla de dato (datum) a documentar:** `z_revit` en el JSON es siempre altura local de montaje; nunca Z absoluta. La Z absoluta se calcula siempre como `nivel.Elevation + altura_local`.

---

## 5. Alcance y restricciones (acuerdo con el usuario)

- ✅ Solo se identifican/documentan las 37 instancias del catálogo de intervención (bloque piloto Apartamento Tipo F 02).
- ✅ No se borra ni modifica ninguna instancia fuera de esas 37.
- ✅ Medidor HS y componentes similares del sistema eléctrico: no se manipulan ni modifican salvo orden directa y específica por elemento.
- ✅ No se ejecuta modo `confirmar=True` ni `borrar_todas`/`borrar_previas` sin autorización explícita del usuario.
- ✅ Todo el trabajo es de análisis y documentación para replicar la transformación en otros apartamentos "Tipo nn".

---

## 6. Próximos pasos recomendados (pendiente de decisión del usuario)

1. Revisar este documento de análisis y validar que el mapeo bloque→dispositivo y la transformación Z son correctos.
2. Si se confirma, ejecutar `F6_CORREGIR_UBICACION_ELECTRICA_v01.py` en modo `confirmar=True` **solo sobre las 37 instancias del piloto F02** (con `borrar_todas=False` y `borrar_previas` limitado al catálogo de intervención), para colocar los 36 dispositivos mal ubicados a Z absoluta correcta con nivel "Piso 5".
3. Ejecutar `F6_VERIFICAR_INVARIANTS_v01.py` sobre el resultado para confirmar: 37 instancias con nivel Piso 5, `z_relativo_nivel` correcto, 0 `sin_nivel` dentro del piloto.
4. Extender el patrón a los otros 18 tipos de apartamento (19 definiciones, 21 pisos) siguiendo el paso 4 de este documento.

---

### Archivos de referencia utilizados

| Archivo | Contenido |
|---------|-----------|
| `data/apto_F_02_aplicar_mapa_v3.json` | 59 bloques DXF: 37 a modelar, 22 saltar, mapeo a familias Revit con altura local |
| `data/apto_F_02_aplicar_mapa_v3_resultado.json` | 37 elementos creados exitosamente en Revit (ids 866982-867018) |
| `data/corregir_ubicacion_electrica_v01.json` | Simulación: 210 instancias eléctricas, 130 fuera de nivel, 37 acciones preparadas (no se modificó el modelo) |
| `data/diagnostico_visibilidad_f02.json` | Estado de visibilidad F02: 37 RED=SI, 123 vistas, 24 niveles, categoría por tipo |
| `src/fase-6-revit/F6_CORREGIR_UBICACION_ELECTRICA_v01.py` | Script de corrección (modo simulación por defecto; aplicar requiere confirmar=True) |
| `src/fase-6-revit/RE_APLICAR_MAPA_V3_REVIT_v02.py` | Camino probado de creación: ceiling face-based, muro level-based |
