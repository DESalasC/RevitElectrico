# Plan de pendientes — RevitElectrico

**Raíz de desarrollo:** `D:\Work\PROJECTS\RevitElectrico`
**Insumo de dibujo (no se modifica):** `D:\Work\PROJECTS\Actuales\T5-SantaMarta`
**Archivos de trabajo:** `D:\Work\PROJECTS\RevitElectrico\ArchivosBase`
**Versión:** v03 — 2026-11-08 (decisiones del operador 21:52)
**Estado:** Fase 0 cerrada · Fase 1 activa · Fase 2 y Fase 3 en standby

---

## 0. Reglas de gobierno vigentes

| # | Regla | Implicación práctica |
|---|-------|----------------------|
| G1 | La raíz del proyecto es `D:\Work\PROJECTS\RevitElectrico`. | Todo el desarrollo, scripts y pruebas viven aquí. |
| G2 | `T5-SantaMarta` es un proyecto de dibujo usado como base. | Solo lectura. No se renombra, mueve ni edita nada allí. |
| G3 | Los archivos de trabajo están en `ArchivosBase`. | El RVT de trabajo se abre desde ahí. |
| G4 | V03 es una copia de V02 y es el archivo activo. | Es el punto de partida adecuado para continuar. No es "canónico": es archivo de trabajo y base para otros proyectos. |
| G5 | `z_revit` en JSON es **altura local de montaje**, nunca Z absoluta. | `Z_absoluta = nivel.Elevation + z_local`. |
| G6 | Los apartamentos **F 01 y F 02** están modelados directamente en Revit como referencia, incluida la tubería. | **Intocables.** No se modifican, mueven, recrean ni borran. |
| G7 | El ancla de cada apartamento es **su panel correspondiente** ya localizado en el modelo Revit. | Los componentes se colocan relativos al panel de su propio apartamento. |
| G8 | `LevelId = -1` en componentes eléctricos es normal. | No es defecto ni bloqueador; validar por Z absoluta y X,Y. |
| G9 | Tolerancias de validación | **X,Y: hasta 0,20 m.** **Z: la establecida desde el principio por los apartamentos iniciales** (0,3 / 1,1 / 1,2 / 2,6 m) y debe ser equivalente. |
| G10 | Registro interno de scripts | Toda versión vigente lleva el bloque "Ultimos tres cambios" en su docstring. Las versiones anteriores se eliminan. |

---

## Fase 0 — Gobierno y saneamiento (cerrada)

| ID | Pendiente | Resultado | Estado |
|----|-----------|-----------|--------|
| 0.1 | Documentar la raíz única | `CLAUDE.md` y este plan declaran `RevitElectrico` como raíz y `T5-SantaMarta` como insumo de solo lectura. | ✅ |
| 0.2 | Corregir el concepto de "documento canónico" | V03 pasa a archivo de trabajo / plantilla base. | ✅ |
| 0.3 | Registrar la regla de datum | `z_revit` = altura local; Z absoluta = elevación del nivel + z_local. | ✅ |
| 0.4 | Limpiar scripts duplicados | 54 archivos obsoletos archivados y luego eliminados (Papelera de reciclaje). Quedan 31 scripts vigentes, todos con registro de cambios. | ✅ |
| 0.5 | Reparar JSON de diagnóstico corruptos | Se regeneran en la primera corrida en vivo sobre V03. | ⏳ |

---

## Fase 1 — Ubicación correcta de componentes (activa)

**Procedimiento acordado (x, y, z):**

1. Localizar en el DXF del apartamento seleccionado las posiciones de sus componentes.
2. Analizarlas y normalizarlas (coordenadas locales del bloque).
3. Transferirlas al `.rvt` tomando como referencia el **panel del apartamento ya localizado correctamente en x, y, z**.
4. Validar: X,Y con tolerancia ≤ 0,20 m; Z equivalente a las alturas de los apartamentos iniciales.

| ID | Pendiente | Detalle | Criterio de aceptación | Estado |
|----|-----------|---------|------------------------|--------|
| 1.1 | Ejecutar y validar el diagnóstico sobre V03 | `DIAGNOSTICO_ESTADO_MODELO_v01.py` con Revit abierto. | Reporte emitido y legible. | ⏳ |
| 1.2 | Reposicionar los apartamentos restantes por panel-ancla | Panel de cada apartamento como origen. No tocar F 01 ni F 02. No mover conduits. | X,Y ≤ 0,20 m; Z equivalente a los apartamentos iniciales. | ⏳ |
| 1.3 | Ajustar invariantes a `LevelId = -1` | `Electrical/Lighting Fixtures` exentos; corregido bug de unidades. | Suite en verde. | ✅ |
| 1.4 | **Primera prueba: Apartamento Tipo E 05** | Inventario disponible: 49 dispositivos, 24 marcadores, panel en DXF (4,2645; −1,1448) a 1,2 m. | E05 ubicado y validado antes de escalar. | 🔄 |

---

## Fase 3 — Validación de un apartamento nuevo (standby, se activa con E05)

| ID | Pendiente | Detalle | Criterio | Estado |
|----|-----------|---------|----------|--------|
| 3.1 | Apartamento de prueba seleccionado | **Tipo E 05** (no es F 01 ni F 02). | Documentado. | ✅ |
| 3.2 | Modelar/reposicionar E05 | Con panel-ancla y datum correcto. | Componentes en su sitio. | ⏳ |
| 3.3 | Validar altura y X,Y | Contra DXF y panel de referencia. | X,Y ≤ 0,20 m; Z equivalente. | ⏳ |

> **Fase 3 en standby** hasta que E05 cumpla las condiciones de ubicación.

---

## Fase 2 — Completar el bloque piloto (standby)

| ID | Pendiente | Estado |
|----|-----------|--------|
| 2.1 | Modelar los marcadores de conductor restantes | ⏸ Standby |
| 2.2 | Crear tipos de conduit y conductos | ⏸ Standby |
| 2.3 | Vista "Piso 5 — Eléctrico" con rango propio | ⏸ Standby |
| 2.4 | Asignar RED / CIRCUITO / ACOMETIDA | ⏸ Standby |
| 2.5 | Detección de colisiones | ⏸ Standby |

---

## Orden de ejecución inmediato

1. **0.5** — regenerar los JSON de diagnóstico corruptos en la primera corrida sobre V03.
2. **1.1** — diagnóstico validado sobre V03 con Revit abierto.
3. **1.4 / 3.2** — transferir E05 desde el DXF usando su panel como ancla.
4. **3.3** — validar E05 (X,Y ≤ 0,20 m; Z equivalente).
5. Si E05 cumple, replicar el procedimiento al resto de apartamentos y retomar Fase 2.

---

## Riesgos

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Panel-ancla mal identificado en Revit | Alto | Confirmar el panel de E05 por posición y `Comments` antes de transferir. |
| Mezclar coordenadas locales del DXF con globales de Revit | Alto | Offset calculado por diferencia panel-DXF → panel-Revit. |
| Mover F 01 o F 02 por error | Alto | Exclusión explícita en scripts y verificación. |
| Mover conduits existentes | Medio | Reposicionar solo FamilyInstance; conduits se recrean después. |
| Confundir `LevelId = -1` con falta de nivel | Medio | Regla G8 aplicada en la verificación. |
