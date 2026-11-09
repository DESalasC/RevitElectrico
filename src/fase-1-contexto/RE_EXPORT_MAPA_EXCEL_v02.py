# -*- coding: utf-8 -*-
"""
RE_EXPORT_MAPA_EXCEL_v02.py — Genera una tabla Excel para reasignar reemplazos
de bloques DXF a componentes Revit, INCLUYENDO la jerarquía de bloques anidados
del DXF individual del apartamento (Apartamento Tipo F 02.dxf).

Tres hojas obligatorias:
  1. "Bloques DXF": TODOS los bloques distintos del DXF del piso completo,
     con o sin asignacion en Revit. Se excluyen los bloques categoria "Basura".
     Columnas para rellenar manualmente: Familia RVT NUEVA, Simbolo RVT.
  2. "Componentes Revit Libreria": TODAS las familias de Revit disponibles en
     la libreria, con nombre exacto de familia y simbolo. Para copiar y pegar
     en la hoja 1 durante la asignacion manual.
  3. "Bloques Anidados Apto F 02": Jerarquia completa del DXF individual del
     apartamento (apartamento -> componentes internos -> familia Revit sugerida).
     Sirve de referencia para entender que hay dentro de cada bloque apartamento.
  4. "Instrucciones": guia de uso.

USO (Python 3.12, fuera de Revit):
    python src\\fase-1-contexto\\RE_EXPORT_MAPA_EXCEL_v02.py

Genera: exports/Mapeo_DXF_Revit_Asignaciones_v02.xlsx
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("ERROR: openpyxl no esta instalado. Instale con: pip install openpyxl")
    raise SystemExit(1)

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

ROOT = Path(os.environ.get("REVITELECTRICO_ROOT", Path.cwd()))
MAPEO_JSON = ROOT / "data" / "stm_t4_p4_mapeo.json"
REPORTE_RESULTADO_JSON = ROOT / "data" / "apto_F_02_aplicar_mapa_v3_resultado.json"
BLOQUES_ANIDADOS_JSON = ROOT / "data" / "bloques_anidados_apto_F_02.json"
XLSX_OUT = ROOT / "exports" / "Mapeo_DXF_Revit_Asignaciones_v02.xlsx"

# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
CELL_FONT = Font(size=10)
WRAP = Alignment(wrap_text=True, vertical="top")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
BORDER = Border(
    left=Side(style="thin", color="BFBFBF"),
    right=Side(style="thin", color="BFBFBF"),
    top=Side(style="thin", color="BFBFBF"),
    bottom=Side(style="thin", color="BFBFBF"),
)

FILL_OK = PatternFill("solid", fgColor="C6EFCE")       # verde claro (mapeado)
FILL_VACIO = PatternFill("solid", fgColor="FFEB9C")    # amarillo (sin mapear)
FILL_MODELAR = PatternFill("solid", fgColor="DDEBF7")  # azul (no modelar)


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _cargar_json(ruta: Path) -> Any:
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def _extraer_componentes_revit_desde_reporte(ruta: Path) -> List[Dict[str, str]]:
    """Extrae pares (familia, simbolo) unicos del reporte de modelado resultado."""
    if not ruta.exists():
        return []
    datos = _cargar_json(ruta)
    exitos = datos.get("exitos", [])
    seen: set = set()
    componentes: List[Dict[str, str]] = []
    for e in exitos:
        clave = (e.get("familia", ""), e.get("simbolo", ""))
        if clave in seen:
            continue
        seen.add(clave)
        componentes.append({
            "familia": e.get("familia", ""),
            "simbolo": e.get("simbolo", ""),
            "nombre_bloque_origen": e.get("nombre_bloque", ""),
            "capa": e.get("capa", ""),
            "anfitrion": e.get("anfitrion", ""),
            "origen": "reporte_modelado",
        })
    return componentes


def _extraer_componentes_desde_mapeo(mapeo: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Extrae familias_revit del mapeo DXF (nombres de archivo .rfa)."""
    seen: set = set()
    componentes: List[Dict[str, str]] = []
    for m in mapeo:
        fam = m.get("familia_revit")
        if fam and fam not in seen:
            seen.add(fam)
            componentes.append({
                "familia": fam,
                "simbolo": "",
                "nombre_bloque_origen": m.get("nombre_bloque", ""),
                "capa": ", ".join(m.get("capas", [])),
                "anfitrion": "",
                "origen": "mapeo_dxf",
            })
    return componentes


# ---------------------------------------------------------------------------
# Hoja 1: Bloques DXF
# ---------------------------------------------------------------------------

def _escribir_hoja_bloques_dxf(ws, mapeo: List[Dict[str, Any]]) -> int:
    """Escribe la hoja 1: Bloques DXF (todos, sin basura, con o sin asignacion Revit)."""
    headers = [
        "#",
        "Nombre bloque DXF",
        "Categoria",
        "Capas",
        "Instancias",
        "Modelar?",
        "Familia RVT actual (.rfa)",
        "Familia RVT NUEVA (escribir aqui)",
        "Simbolo RVT (escribir aqui)",
        "Nota",
    ]
    ws.append(headers)
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER

    fila = 2
    for idx, m in enumerate(mapeo, start=1):
        # Excluir completamente los bloques basura
        if m.get("categoria") == "Basura":
            continue

        nombre = m.get("nombre_bloque", "")
        categoria = m.get("categoria", "")
        capas = ", ".join(m.get("capas", []))
        instancias = m.get("instancias", 0)
        modelar = m.get("modelar", False)
        familia_actual = m.get("familia_revit") or ""
        nota = m.get("nota", "")

        row = [
            idx,
            nombre,
            categoria,
            capas,
            instancias,
            "SI" if modelar else "NO",
            familia_actual,        # puede quedar vacio para rellenar
            "",                    # familia_revit_nueva (vacía para el usuario)
            "",                    # simbolo_rvt (vacía para el usuario)
            nota,
        ]
        ws.append(row)

        for col in range(1, len(headers) + 1):
            c = ws.cell(row=fila, column=col)
            c.font = CELL_FONT
            c.alignment = WRAP
            c.border = BORDER

        # Color por estado de mapeo
        if not modelar:
            fill = FILL_MODELAR
        elif modelar and not familia_actual:
            fill = FILL_VACIO
        elif modelar:
            fill = FILL_OK
        else:
            fill = None

        if fill:
            for col in range(1, len(headers) + 1):
                ws.cell(row=fila, column=col).fill = fill

        fila += 1

    anchos = [5, 40, 25, 30, 10, 8, 30, 30, 30, 50]
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    ws.freeze_panes = "A2"
    return fila - 1


# ---------------------------------------------------------------------------
# Hoja 2: Componentes Revit Libreria
# ---------------------------------------------------------------------------

def _escribir_hoja_componentes_revit(
    ws,
    componentes_reporte: List[Dict[str, str]],
    componentes_mapeo: List[Dict[str, str]],
) -> int:
    """Escribe la hoja 2: Componentes Revit disponibles en la libreria."""
    headers = [
        "#",
        "Familia Revit",
        "Simbolo",
        "Nombre bloque DXF origen",
        "Capas",
        "Anfitrion",
        "Origen",
    ]
    ws.append(headers)
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER

    fila = 2
    seen: set = set()
    todas = componentes_reporte + componentes_mapeo
    for c in todas:
        clave = (c["familia"], c["simbolo"])
        if clave in seen:
            continue
        seen.add(clave)
        row = [
            fila - 1,
            c["familia"],
            c["simbolo"],
            c["nombre_bloque_origen"],
            c["capa"],
            c["anfitrion"],
            c["origen"],
        ]
        ws.append(row)
        for col in range(1, len(headers) + 1):
            celda = ws.cell(row=fila, column=col)
            celda.font = CELL_FONT
            celda.alignment = WRAP
            celda.border = BORDER
        fila += 1

    anchos = [5, 45, 40, 40, 40, 15, 15]
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    ws.freeze_panes = "A2"
    return fila - 1


# ---------------------------------------------------------------------------
# Hoja 3: Bloques Anidados Apto F 02
# ---------------------------------------------------------------------------

def _escribir_hoja_bloques_anidados(ws, datos_anidados: Dict[str, Any]) -> int:
    """Escribe la hoja 3: Jerarquia de bloques anidados del apto F 02."""
    headers = [
        "#",
        "Nombre bloque DXF (apartamento)",
        "Capa",
        "Punto X",
        "Punto Y",
        "Punto Z",
        "Rotacion",
        "Es electrica?",
        "Familia Revit sugerida",
        "Total componentes internos",
        "Componente interno #",
        "Tipo componente",
        "Capa componente",
        "Punto interno X",
        "Punto interno Y",
        "Punto interno Z",
        "Nota componente",
    ]
    ws.append(headers)
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=i)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER

    fila = 2
    idx_global = 1
    bloques = datos_anidados.get("bloques_apartamento", [])
    for b in bloques:
        nombre_bloque = b.get("nombre_bloque", "")
        capa = b.get("capa", "")
        punto = b.get("punto_insert", [0, 0, 0])
        rotacion = b.get("rotacion", 0)
        es_electrica = b.get("es_electrica", False)
        familia_sugerida = b.get("familia_revit_sugerida", "")
        total_comp = b.get("total_componentes", 0)
        componentes = b.get("componentes_internos", [])

        if not componentes:
            # Bloque sin componentes internos: una fila
            row = [
                idx_global,
                nombre_bloque,
                capa,
                punto[0] if len(punto) > 0 else "",
                punto[1] if len(punto) > 1 else "",
                punto[2] if len(punto) > 2 else "",
                rotacion,
                "SI" if es_electrica else "NO",
                familia_sugerida,
                total_comp,
                "", "", "", "", "", "",
                "Sin componentes internos",
            ]
            ws.append(row)
            for col in range(1, len(headers) + 1):
                c = ws.cell(row=fila, column=col)
                c.font = CELL_FONT
                c.alignment = WRAP
                c.border = BORDER
            fila += 1
            idx_global += 1
        else:
            for j, c in enumerate(componentes, start=1):
                nota = ""
                if c.get("tipo") == "CIRCLE":
                    nota = "centro={} radio={}".format(c.get("centro"), c.get("radio"))
                elif c.get("tipo") == "LWPOLYLINE":
                    nota = "puntos={} cerrada={}".format(
                        c.get("puntos"), c.get("cerrada"))
                elif c.get("tipo") == "ARC":
                    nota = "centro={} radio={} ang={}-{}".format(
                        c.get("centro"), c.get("radio"),
                        c.get("angulo_inicio"), c.get("angulo_fin"))
                elif c.get("tipo") == "TEXT":
                    nota = "texto='{}' altura={}".format(c.get("texto"), c.get("altura"))
                elif c.get("tipo") == "INSERT":
                    nota = "bloque={}".format(c.get("nombre_bloque"))

                punto_comp = c.get("centro") or c.get("punto") or c.get("punto_insert") or [0, 0, 0]

                row = [
                    idx_global,
                    nombre_bloque,
                    capa,
                    punto[0] if len(punto) > 0 else "",
                    punto[1] if len(punto) > 1 else "",
                    punto[2] if len(punto) > 2 else "",
                    rotacion,
                    "SI" if es_electrica else "NO",
                    familia_sugerida,
                    total_comp,
                    j,
                    c.get("tipo", ""),
                    c.get("capa", ""),
                    punto_comp[0] if isinstance(punto_comp, list) and len(punto_comp) > 0 else "",
                    punto_comp[1] if isinstance(punto_comp, list) and len(punto_comp) > 1 else "",
                    punto_comp[2] if isinstance(punto_comp, list) and len(punto_comp) > 2 else "",
                    nota,
                ]
                ws.append(row)
                for col in range(1, len(headers) + 1):
                    celda = ws.cell(row=fila, column=col)
                    celda.font = CELL_FONT
                    celda.alignment = WRAP
                    celda.border = BORDER
                fila += 1
            idx_global += 1

    anchos = [5, 35, 20, 10, 10, 10, 10, 10, 30, 12, 8, 20, 20, 12, 12, 12, 50]
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    ws.freeze_panes = "A2"
    return fila - 1


# ---------------------------------------------------------------------------
# Hoja 4: Instrucciones
# ---------------------------------------------------------------------------

def _escribir_hoja_instrucciones(ws) -> None:
    """Escribe la hoja 4: Instrucciones de uso."""
    instrucciones = [
        ["RE_EXPORT_MAPA_EXCEL_v02 — Instrucciones", ""],
        ["", ""],
        ["Propósito",
         "Esta tabla permite reasignar los bloques del DXF a componentes de Revit, "
         "incluyendo la informacion de bloques anidados del DXF individual del apartamento."],
        ["Hoja 1 'Bloques DXF'",
         "Lista TODOS los bloques distintos del DXF del piso completo (excluye basura). "
         "Si un bloque ya tiene familia_revit asignada (columna G), aparece relleno. "
         "Si no, la columna H ('Familia RVT NUEVA') queda en blanco para que usted la complete."],
        ["Hoja 2 'Componentes Revit Libreria'",
         "Lista TODAS las familias de Revit disponibles en la libreria (familia y simbolo exactos). "
         "Copie los nombres exactos desde aqui y peguelos en la hoja 1."],
        ["Hoja 3 'Bloques Anidados Apto F 02'",
         "Jerarquia completa del DXF individual del apartamento (Apartamento Tipo F 02.dxf). "
         "Muestra cada bloque apartamento con sus componentes internos (tipo, capa, punto) "
         "y la familia de Revit sugerida. Sirve de referencia para entender que hay dentro "
         "de cada bloque apartamento y modelar correctamente en Revit."],
        ["Paso 1", "Revise cada bloque en la hoja 1 y su reemplazo actual en Revit (columna G)."],
        ["Paso 2", "Si el reemplazo es incorrecto o falta, escriba el nombre exacto de la familia en la columna H ('Familia RVT NUEVA')."],
        ["Paso 3", "Si corresponde, escriba el nombre del simbolo en la columna I ('Simbolo RVT'). Use la hoja 2 para copiar nombres exactos."],
        ["Paso 4", "Guarde el archivo y devuélvalo para que se lean y apliquen los cambios en el script de modelado."],
        ["", ""],
        ["Leyenda de colores (hoja 1)", ""],
        ["Verde claro", "Bloque modelar=SI y ya tiene familia_revit asignada."],
        ["Amarillo", "Bloque modelar=SI pero SIN familia_revit (pendiente de asignar)."],
        ["Azul claro", "Bloque modelar=NO (no se modela en Revit)."],
        ["", ""],
        ["Fuente de datos", "data/stm_t4_p4_mapeo.json (bloques distintos del DXF del piso completo)."],
        ["Familias de referencia",
         "data/apto_F_02_aplicar_mapa_v3_resultado.json (reporte de modelado) y data/bloques_anidados_apto_F_02.json (bloques anidados del apto F 02)."],
        ["Fecha de generacion", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
    ]
    for fila in instrucciones:
        ws.append(fila)
    for row in ws.iter_rows(min_row=1, max_row=len(instrucciones), max_col=2):
        for c in row:
            c.font = CELL_FONT
            c.alignment = WRAP
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 120


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    if not MAPEO_JSON.exists():
        print("ERROR: No se encontro el mapeo en: {}".format(MAPEO_JSON))
        return 1

    mapeo_raw = _cargar_json(MAPEO_JSON)
    if isinstance(mapeo_raw, dict):
        mapeo_lista = mapeo_raw.get("mapeo", [])
    else:
        mapeo_lista = mapeo_raw

    componentes_reporte = _extraer_componentes_revit_desde_reporte(REPORTE_RESULTADO_JSON)
    componentes_mapeo = _extraer_componentes_desde_mapeo(mapeo_lista)

    # Cargar datos de bloques anidados si existen
    datos_anidados: Dict[str, Any] = {}
    if BLOQUES_ANIDADOS_JSON.exists():
        datos_anidados = _cargar_json(BLOQUES_ANIDADOS_JSON)

    # Crear directorio de salida
    out_dir = XLSX_OUT.parent
    if out_dir and not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)

    wb = Workbook()

    # Hoja 1: Bloques DXF
    ws1 = wb.active
    ws1.title = "Bloques DXF"
    total_bloques = _escribir_hoja_bloques_dxf(ws1, mapeo_lista)

    # Hoja 2: Componentes Revit Libreria
    ws2 = wb.create_sheet("Componentes Revit Libreria")
    total_componentes = _escribir_hoja_componentes_revit(
        ws2, componentes_reporte, componentes_mapeo
    )

    # Hoja 3: Bloques Anidados Apto F 02
    ws3 = wb.create_sheet("Bloques Anidados Apto F 02")
    total_anidados = _escribir_hoja_bloques_anidados(ws3, datos_anidados)

    # Hoja 4: Instrucciones
    ws4 = wb.create_sheet("Instrucciones")
    _escribir_hoja_instrucciones(ws4)

    wb.save(str(XLSX_OUT))

    print("=" * 60)
    print("EXCEL GENERADO (v02 con bloques anidados)")
    print("Archivo: {}".format(XLSX_OUT))
    print("Hoja 1 'Bloques DXF': {} bloques (sin basura)".format(total_bloques))
    print("Hoja 2 'Componentes Revit Libreria': {} componentes".format(total_componentes))
    print("Hoja 3 'Bloques Anidados Apto F 02': {} filas".format(total_anidados))
    print("Hoja 4 'Instrucciones'")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

