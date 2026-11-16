# _historico — scripts y documentos retirados

Esta carpeta guarda lo que **ya no se usa pero se conserva como evidencia**.

## Qué va aquí

- Scripts sustituidos por una versión consolidada (por ejemplo, la familia `v55–v69` cuando
  `RE_F6_COLOCAR_DISPOSITIVOS.py` quede estable).
- Versiones de documento que dejan de ser vigentes por decisión explícita (D7: `V03` y
  `E06_BASE_LIMPIO_2026-11-12` respecto de `CENTRAL-V01`).
- Entregas descartadas por un error de fondo, con la nota de por qué se descartaron.

## Qué NO va aquí

- Nada que todavía se ejecute. Si un script se usa, vive en `src/`.
- Copias de seguridad masivas de `.rvt`: los RVT no se versionan (ver `.gitignore`); su
  identidad se registra por hash en `data/baseline_hashes.json`.

## Regla de retiro

1. El archivo se mueve, no se borra.
2. Cada retiro deja una línea en el `README` de la carpeta con: fecha, archivo, motivo y
   qué lo sustituye.
3. Si el retiro es por un error técnico, se escribe la lección en `50-lecciones/` del vault
   **antes** de mover el archivo.

## Retiros registrados

| Fecha | Archivo | Motivo | Sustituido por |
|---|---|---|---|
| — | (vacío) | — | — |

> Creada el 2026-11-15 durante F0 (decisión D14/D15). Se crea vacía a propósito: no se
> archiva un archivo que no existe. El `colocacion_masiva_F01_v70.py` citado en el análisis
> del 2026-11-15 **no está en este repositorio** (verificado por búsqueda recursiva y por
> `git log --all`); si aparece, no debe ejecutarse sin revisar H1.
