# -*- coding: utf-8 -*-
"""
RE_EXPORT_MAPA_EXCEL_v01.py — Genera una tabla Excel para reasignar reemplazos
de bloques DXF a componentes Revit.

Dos hojas obligatorias:
  1. "Bloques DXF": TODOS los bloques distintos del DXF, con o sin asignacion
     en Revit (si no tiene familia_revit asignada, la celda queda en blanco).
     Se EXCLUYEN completamente los bloques de categoria "Basura".
  2. "Componentes Revit": TODOS los componentes Revit disponibles en el
     documento (familia y simbolo exacto), para que el usuario copie el nombre
     exacto y lo pegue en la primera tabla durante la asignacion manual.

USO (Python 3.12, fuera de Revit):
    python src\\fase-1-contexto\\RE_EXPORT_MAPA_EXCEL_v01.py

Genera: exports/Mapeo_DXF_Revit_Asignaciones.xlsx
"""

import json
import os
from datetime import datetime

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("ERROR: openpyxl no esta instalado. Instale con: pip install openpyxl")
    raise

ROOT = os.environ.get("REVITELECTRICO_ROOT", os.getcwd())
MAPEO_JSON = os.path.join(ROOT, "data", "stm_t4_p4_mapeo.json")
REPORTE_RESULTADO_JSON = os.path.join(
    ROOT, "data", "apto_F_02_aplicar_mapa_v3_resultado.json"
)
XLSX_OUT = os.path.join(ROOT, "exports", "Mapeo_DXF_Revit_Asignaciones.xlsx")

# Estilos
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

FILL_OK = PatternFill("solid", fgColor="C6EFCE")      # verde claro (mapeado)
FILL_VACIO = PatternFill("solid", fgColor="FFEB9C")   # amarillo (sin mapear)
FILL_MODELAR = PatternFill("solid", fgColor="DDEBF7")  # azul (modelar=true)


def _cargar_json(ruta):
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def _extraer_componentes_revit_desde_reporte(ruta):
    """Extrae pares (familia, simbolo) unicos del reporte de modelado resultado."""
    if not os.path.exists(ruta):
        return []
    datos = _cargar_json(ruta)
    exitos = datos.get("exitos", [])
    seen = set()
    componentes = []
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
            "origen": "reporte_modelado",
        })
    return componentes


def _extraer_componentes_desde_mapeo(mapeo):
    """Extrae familias_revit del mapeo DXF (nombres de archivo .rfa)."""
    seen = set()
    componentes = []
    for m in mapeo:
        fam = m.get("familia_revit")
        if fam and fam not in seen:
            seen.add(fam)
            componentes.append({
                "familia": fam,
                "simbolo": "",
                "nombre_bloque_origen": m.get("nombre_bloque", ""),
                "capa": ", ".join(m.get("capas", [])),
                "origen": "mapeo_dxf",
            })
    return componentes


def _escribir_hoja_bloques_dxf(ws, mapeo):
    """Escribe la hoja 1: Bloques DXF (todos, sin basura, con o sin asignacion Revit)."""
    headers = [
        "#",
        "Nombre bloque DXF",
        "Categoria",
        "Capas",
        "Instancias",
        "Modelar?",
        "Familia RVT actual (archivo .rfa)",
        "Altura default (m)",
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
        altura = m.get("altura_default_m")
        altura_str = str(altura) if altura is not None else ""
        nota = m.get("nota", "")

        row = [
            idx,
            nombre,
            categoria,
            capas,
            instancias,
            "SI" if modelar else "NO",
            familia_actual,        # si esta vacio, se deja en blanco para rellenar
            altura_str,
            "",                    # familia_revit_nueva (vacía para que el usuario rellene)
            "",                    # simbolo_rvt (vacía para que el usuario rellene)
            nota,
        ]
        ws.append(row)

        # Estilo de celda
        for col in range(1, len(headers) + 1):
            c = ws.cell(row=fila, column=col)
            c.font = CELL_FONT
            c.alignment = WRAP
            c.border = BORDER

        # Color por estado de mapeo
        if not modelar:
            fill = FILL_MODELAR  # azul: no se modela
        elif modelar and not familia_actual:
            fill = FILL_VACIO    # amarillo: sin familia_revit asignada
        elif modelar:
            fill = FILL_OK       # verde: mapeado y listo
        else:
            fill = None

        if fill:
            for col in range(1, len(headers) + 1):
                ws.cell(row=fila, column=col).fill = fill

        fila += 1

    anchos = [5, 35, 25, 30, 10, 8, 30, 12, 30, 30, 50]
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    ws.freeze_panes = "A2"
    return fila - 1


def _escribir_hoja_componentes_revit(ws, componentes_reporte, componentes_mapeo):
    """Escribe la hoja 2: Componentes Revit disponibles (familia + simbolo exacto)."""
    headers = [
        "#",
        "Familia Revit",
        "Simbolo",
        "Nombre bloque DXF origen",
        "Capas",
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
    seen = set()
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
            c["origen"],
        ]
        ws.append(row)
        for col in range(1, len(headers) + 1):
            celda = ws.cell(row=fila, column=col)
            celda.font = CELL_FONT
            celda.alignment = WRAP
            celda.border = BORDER
        fila += 1

    anchos = [5, 45, 40, 40, 40, 15]
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    ws.freeze_panes = "A2"
    return fila - 1


def _escribir_hoja_instrucciones(ws):
    """Escribe la hoja 3: Instrucciones de uso."""
    instrucciones = [
        ["RE_EXPORT_MAPA_EXCEL_v01 — Instrucciones", ""],
        ["", ""],
        ["Propósito", "Esta tabla permite reasignar los bloques del DXF a componentes de Revit."],
        ["Hoja 1 'Bloques DXF'", "Lista TODOS los bloques distintos del DXF (excluye basura). Si un bloque ya tiene familia_revit asignada (columna G), aparece relleno. Si no, la celda queda en blanco para que usted la complete."],
        ["Hoja 2 'Componentes Revit'", "Lista TODOS los componentes Revit disponibles en el documento (familia y símbolo exactos). Copie los nombres exactos desde aquí y péguelos en la hoja 1."],
        ["Paso 1", "Revise cada bloque en la hoja 1 y su reemplazo actual en Revit (columna G)."],
        ["Paso 2", "Si el reemplazo es incorrecto o falta, escriba el nombre exacto de la familia en la columna I ('Familia RVT NUEVA')."],
        ["Paso 3", "Si corresponde, escriba el nombre del símbolo en la columna J ('Simbolo RVT'). Use la hoja 2 para copiar nombres exactos."],
        ["Paso 4", "Guarde el archivo y devuélvalo para que se lean y apliquen los cambios en el script de modelado."],
        ["", ""],
        ["Leyenda de colores", ""],
        ["Verde claro", "Bloque modelar=SI y ya tiene familia_revit asignada."],
        ["Amarillo", "Bloque modelar=SI pero SIN familia_revit (pendiente de asignar)."],
        ["Azul claro", "Bloque modelar=NO (no se modela en Revit)."],
        ["", ""],
        ["Fuente de datos", "data/stm_t4_p4_mapeo.json (bloques distintos del DXF)."],
        ["Familias de referencia", "Extraídas de data/apto_F_02_aplicar_mapa_v3_resultado.json (reporte de modelado)."],
        ["Fecha de generacion", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
    ]
    for fila in instrucciones:
        ws.append(fila)
    for row in ws.iter_rows(min_row=1, max_row=len(instrucciones), max_col=2):
        for c in row:
            c.font = CELL_FONT
            c.alignment = WRAP
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 90


def main():
    if not os.path.exists(MAPEO_JSON):
        print("ERROR: No se encontro el mapeo en: {}".format(MAPEO_JSON))
        return 1

    mapeo = _cargar_json(MAPEO_JSON)
    if isinstance(mapeo, dict):
        mapeo_lista = mapeo.get("mapeo", [])
    else:
        mapeo_lista = mapeo

    componentes_reporte = _extraer_componentes_revit_desde_reporte(REPORTE_RESULTADO_JSON)
    componentes_mapeo = _extraer_componentes_desde_mapeo(mapeo_lista)

    # Crear directorio de salida
    out_dir = os.path.dirname(XLSX_OUT)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir)

    wb = Workbook()

    # Hoja 1: Bloques DXF
    ws1 = wb.active
    ws1.title = "Bloques DXF"
    total_bloques = _escribir_hoja_bloques_dxf(ws1, mapeo_lista)

    # Hoja 2: Componentes Revit
    ws2 = wb.create_sheet("Componentes Revit")
    total_componentes = _escribir_hoja_componentes_revit(
        ws2, componentes_reporte, componentes_mapeo
    )

    # Hoja 3: Instrucciones
    ws3 = wb.create_sheet("Instrucciones")
    _escribir_hoja_instrucciones(ws3)

    wb.save(XLSX_OUT)

    print("=" * 60)
    print("EXCEL GENERADO")
    print("Archivo: {}".format(XLSX_OUT))
    print("Hoja 1 'Bloques DXF': {} bloques (sin basura)".format(total_bloques))
    print("Hoja 2 'Componentes Revit': {} componentes".format(total_componentes))
    print("Hoja 3 'Instrucciones'")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

