# data/referencia — verdad de referencia (ground truth)

Aquí vive lo que **no se genera en una corrida**, sino que se extrae una vez del benchmark
y sirve para verificar todas las corridas posteriores.

## Diferencia con `data/`

| Carpeta | Contenido | Se regenera |
|---|---|---|
| `data/referencia/` | ground truth minado del modelo manual, capacidades de familia | solo si cambia el benchmark |
| `data/` | reportes, diffs y veredictos de cada corrida | en cada ejecución |

## Contenido previsto (F1)

| Archivo | Origen | Descripción |
|---|---|---|
| `benchmark_raw.json` | export de solo lectura de `CENTRA_V02-f.rvt` | una entrada por `FamilyInstance`: `UniqueId`, familia, símbolo, host, cara, nivel, Z, rotación |
| `capacidades_familias_v01.json` | sonda de familias + minado | `family_placement_type`, `sobrecarga`, `delta_rot_deg`, `offset_local_m`, muestras y dispersión |
| `expected_F01.json` | minado del benchmark | posición, host y rotación esperados por `handle` |
| `expected_F02.json` | idem | idem |
| `expected_E06.json` | idem | idem |

## Reglas

1. **Nunca se edita a mano.** Si un valor está mal, se vuelve a minar.
2. Todo valor lleva su origen: `medido_benchmark`, `medido_modelo` (E05/E06) o
   `pendiente_medicion`. Un valor supuesto sin marcar está prohibido.
3. Se versiona en git: es pequeño y es el contrato contra el que se valida.
4. Si el benchmark cambia de hash, esta carpeta queda invalidada y se regenera completa.

> Creada el 2026-11-15 durante F0 (decisión D15). Vacía hasta que se ejecute F1.
