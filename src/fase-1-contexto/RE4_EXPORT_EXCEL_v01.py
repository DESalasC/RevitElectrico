"""
================================================================================
RE4_EXPORT_EXCEL_v01.py — Exportación de JSON (RE1/RE2/RE3) a Excel
Proyecto: RevitElectrico / T5-SantaMarta / Fase 1
Python 3.12 Standalone (NO Revit, NO Grasshopper)
================================================================================

OBJETIVO:
  Leer los JSON intermedios generados por RE1_NORMALIZA_DXF_v01.py,
  RE2_MAPEO_BLOQUES_v01.py y RE3_LECTURA_IFC_v01.py y exportarlos a un
  libro Excel (.xlsx) con hojas temáticas para revisión y coordinación.

  Hojas del libro:
    - Resumen       : chip, conteos globales (DXF e IFC), origen de cada JSON.
    - DXF_Bloques   : detalle de bloques INSERT normalizados (nombre, capa,
                      punto reubicado, familia Revit sugerida, eléctrico).
    - DXF_Mapeo     : mapeo bloque → familia Revit (categoría, altura,
                      modelar, código de conductores, instancias).
    - DXF_Geometria : polilíneas, líneas, arcos y círculos normalizados.
    - IFC_Elementos : elementos IFC con guid, tipo, nombre y cantidades.
    - IFC_Resumen   : conteos de elementos IFC por tipo.

  Solo escritura de Excel. Requiere openpyxl.

ENTRADAS (CLI):
  --json-re1  : ruta al JSON de RE1 (normalizado DXF) — opcional
  --json-re2  : ruta al JSON de RE2 (mapeo de bloques) — opcional
  --json-ifc  : ruta al JSON de RE3 (lectura IFC) — opcional
  --xlsx-out  : ruta del Excel de salida (default: exports/<chip>_reporte.xlsx)
  --chip      : identificador del predio/lote (default: SANTAMARTA_T5)

SALIDA:
  Libro .xlsx con las hojas mencionadas, con encabezados estilo y anchos
  de columna ajustados.

HISTORIAL:
  v01.0 (2026-10-21) — versión inicial. Exportación JSON → Excel.
================================================================================
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError as exc:  # pragma: no cover - depende del entorno
    raise SystemExit(
        "openpyxl no está instalado. Instálelo con: pip install openpyxl"
    ) from exc

DEFAULT_CHIP = "SANTAMARTA_T5"

HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(color="FFFFFF", bold=True)
SEC_FILL = PatternFill("solid", fgColor="DDEBF7")
SEC_FONT = Font(bold=True, size=12)
BORDER = Border(*[Side(style="thin", color="BBBBBB")] * 4)
CENTER = Alignment(horizontal="center", vertical="center")


def _cargar_json(ruta: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Carga un archivo JSON si la ruta existe; devuelve None si no se indica o falta."""
    if not ruta:
        return None
    if not ruta.exists():
        return None
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


def _style_header(ws, row: int, ncols: int) -> None:
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = CENTER
        cell.border = BORDER


def _bordes_rango(ws, min_row: int, max_row: int, ncols: int) -> None:
    for row in ws.iter_rows(min_row=min_row, max_row=max_row, max_col=ncols):
        for cell in row:
            cell.border = BORDER


def _ajustar_anchos(ws, anchos: List[int]) -> None:
    for i, w in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _escribir_hoja(
    ws,
    titulo_seccion: str,
    filas_meta: List[List[Any]],
    headers: List[str],
    datos: List[List[Any]],
    anchos: List[int],
) -> None:
    """Escribe una hoja común: título/sección, metadatos, tabla con encabezado y datos."""
    ws.append([titulo_seccion])
    ws.cell(row=1, column=1).font = SEC_FONT
    ws.cell(row=1, column=1).fill = SEC_FILL
    ws.append([])
    for fila in filas_meta:
        ws.append(fila)
    ws.append([])
    ws.append(headers)
    _style_header(ws, ws.max_row, len(headers))
    for fila in datos:
        ws.append(fila)
    _bordes_rango(ws, ws.max_row - len(datos) + 1, ws.max_row, len(headers))
    _ajustar_anchos(ws, anchos)


def build_workbook(
    chip: str,
    re1: Optional[Dict[str, Any]],
    re2: Optional[Dict[str, Any]],
    re3: Optional[Dict[str, Any]],
) -> Workbook:
    wb = Workbook()

    # ==================================================================
    # Hoja: Resumen
    # ==================================================================
    ws = wb.active
    ws.title = "Resumen"
    ws.append(["REPORTE REVIT ELECTRICO — T5 SANTA MARTA"])
    ws.cell(row=1, column=1).font = SEC_FONT
    ws.cell(row=1, column=1).fill = SEC_FILL
    ws.append([])
    resumen_meta = [
        ["Chip", chip],
        ["JSON RE1 (DXF normalizado)", "Sí" if re1 else "No"],
        ["JSON RE2 (Mapeo bloques→Revit)", "Sí" if re2 else "No"],
        ["JSON RE3 (Lectura IFC)", "Sí" if re3 else "No"],
        ["Origen DXF", re1.get("metadatos", {}).get("origen_dxf", "-") if re1 else "-"],
        ["Origen IFC", re3.get("metadatos", {}).get("origen_ifc", "-") if re3 else "-"],
        ["Schema IFC", re3.get("metadatos", {}).get("schema", "-") if re3 else "-"],
    ]
    for k, v in resumen_meta:
        ws.append([k, v])
    _bordes_rango(ws, 4, ws.max_row, 2)
    _ajustar_anchos(ws, [38, 70])

    # Conteos globales
    ws.append([])
    ws.append(["CONTEOS GLOBALES"])
    ws.cell(row=ws.max_row, column=1).font = SEC_FONT
    ws.cell(row=ws.max_row, column=1).fill = SEC_FILL
    ws.append(["Concepto", "Valor"])
    _style_header(ws, ws.max_row, 2)

    conteos: List[List[Any]] = []
    if re1:
        r = re1.get("resumen", {})
        conteos.append(["Bloques DXF totales", r.get("bloques_total", 0)])
        conteos.append(["Bloques eléctricos", r.get("bloques_electricos", 0)])
        conteos.append(["Bloques no eléctricos", r.get("bloques_no_electricos", 0)])
        conteos.append(["Bloques basura filtrados", r.get("bloques_basura_filtrados", 0)])
        conteos.append(["Polilíneas DXF", r.get("polilineas", 0)])
        conteos.append(["Polilíneas eléctricas", r.get("polilineas_electricas", 0)])
        conteos.append(["Líneas DXF", r.get("lineas", 0)])
        conteos.append(["Arcos DXF", r.get("arcos", 0)])
        conteos.append(["Círculos DXF", r.get("circulos", 0)])
    if re2:
        r = re2.get("resumen", {})
        conteos.append(["Bloques distintos mapeados", r.get("bloques_distintos", 0)])
        conteos.append(["Instancias totales", r.get("instancias_total", 0)])
        conteos.append(["Instancias a modelar", r.get("instancias_a_modelar", 0)])
        conteos.append(["Instancias a descartar", r.get("instancias_descartar", 0)])
        conteos.append(["Instancias basura", r.get("instancias_basura", 0)])
        conteos.append(["Instancias código conductores", r.get("instancias_codigo_conductores", 0)])
    if re3:
        r = re3.get("resumen", {})
        conteos.append(["Total elementos IFC", r.get("total_elementos", 0)])
        conteos.append(["Tipos IFC distintos", r.get("total_tipos_distintos", 0)])
        conteos.append(["Qto sets IFC extraídos", r.get("total_qto_sets", 0)])

    for c, v in conteos:
        ws.append([c, v])
    _bordes_rango(ws, ws.max_row - len(conteos) + 1, ws.max_row, 2)

    # ==================================================================
    # Hoja: DXF_Bloques (desde RE1)
    # ==================================================================
    if re1:
        ws2 = wb.create_sheet("DXF_Bloques")
        headers = ["Nombre bloque", "Capa", "Es eléctrica", "Punto X", "Punto Y", "Punto Z", "Familia Revit sugerida"]
        datos: List[List[Any]] = []
        for b in re1.get("bloques", []):
            p = b.get("punto_insert", [None, None, None])
            datos.append([
                b.get("nombre_bloque", ""),
                b.get("capa", ""),
                "Sí" if b.get("es_electrica") else "No",
                p[0], p[1], p[2],
                b.get("familia_revit_sugerida", ""),
            ])
        _escribir_hoja(
            ws2, "BLOQUES DXF NORMALIZADOS", [], headers, datos,
            [26, 30, 12, 14, 14, 14, 34],
        )

    # ==================================================================
    # Hoja: DXF_Mapeo (desde RE2)
    # ==================================================================
    if re2:
        ws3 = wb.create_sheet("DXF_Mapeo")
        headers = ["Nombre bloque", "Categoría", "Familia Revit", "Altura default (m)",
                   "Modelar", "Código conductores", "Instancias", "Capas", "Nota"]
        datos = []
        for m in re2.get("mapeo", []):
            datos.append([
                m.get("nombre_bloque", ""),
                m.get("categoria", ""),
                m.get("familia_revit") or "",
                m.get("altura_default_m") or "",
                "Sí" if m.get("modelar") else "No",
                "Sí" if m.get("es_codigo_conductores") else "No",
                m.get("instancias", 0),
                ", ".join(m.get("capas", [])),
                m.get("nota", ""),
            ])
        _escribir_hoja(
            ws3, "MAPEO BLOQUE → FAMILIA REVIT", [], headers, datos,
            [28, 22, 30, 14, 10, 14, 11, 30, 40],
        )

    # ==================================================================
    # Hoja: DXF_Geometria (desde RE1)
    # ==================================================================
    if re1:
        ws4 = wb.create_sheet("DXF_Geometria")
        ws4.append(["GEOMETRÍA DXF NORMALIZADA"])
        ws4.cell(row=1, column=1).font = SEC_FONT
        ws4.cell(row=1, column=1).fill = SEC_FILL
        ws4.append([])

        # Polilíneas
        ws4.append(["Polilíneas"])
        ws4.cell(row=ws4.max_row, column=1).font = SEC_FONT
        ws4.cell(row=ws4.max_row, column=1).fill = SEC_FILL
        ws4.append(["Capa", "Es eléctrica", "Nº puntos", "Cerrada"])
        _style_header(ws4, ws4.max_row, 4)
        for p in re1.get("polilineas", []):
            pts = p.get("puntos", [])
            ws4.append([
                p.get("capa", ""),
                "Sí" if p.get("es_electrica") else "No",
                len(pts),
                "Sí" if p.get("cerrada") else "No",
            ])
        _bordes_rango(ws4, ws4.max_row - len(re1.get("polilineas", [])), ws4.max_row, 4)
        ws4.append([])

        # Líneas
        ws4.append(["Líneas"])
        ws4.cell(row=ws4.max_row, column=1).font = SEC_FONT
        ws4.cell(row=ws4.max_row, column=1).fill = SEC_FILL
        ws4.append(["Capa", "Es eléctrica", "Inicio X", "Inicio Y", "Fin X", "Fin Y"])
        _style_header(ws4, ws4.max_row, 6)
        for l in re1.get("lineas", []):
            ini = l.get("inicio", [None, None, None])
            fin = l.get("fin", [None, None, None])
            ws4.append([
                l.get("capa", ""),
                "Sí" if l.get("es_electrica") else "No",
                ini[0], ini[1], fin[0], fin[1],
            ])
        _bordes_rango(ws4, ws4.max_row - len(re1.get("lineas", [])), ws4.max_row, 6)
        ws4.append([])

        # Arcos y círculos
        ws4.append(["Arcos y Círculos"])
        ws4.cell(row=ws4.max_row, column=1).font = SEC_FONT
        ws4.cell(row=ws4.max_row, column=1).fill = SEC_FILL
        ws4.append(["Tipo", "Capa", "Es eléctrica", "Centro X", "Centro Y", "Radio"])
        _style_header(ws4, ws4.max_row, 6)
        for a in re1.get("arcos", []):
            c = a.get("centro", [None, None, None])
            ws4.append(["ARCO", a.get("capa", ""), "Sí" if a.get("es_electrica") else "No", c[0], c[1], a.get("radio", "")])
        for ci in re1.get("circulos", []):
            c = ci.get("centro", [None, None, None])
            ws4.append(["CÍRCULO", ci.get("capa", ""), "Sí" if ci.get("es_electrica") else "No", c[0], c[1], ci.get("radio", "")])
        n_arc = len(re1.get("arcos", [])) + len(re1.get("circulos", []))
        _bordes_rango(ws4, ws4.max_row - n_arc, ws4.max_row, 6)
        _ajustar_anchos(ws4, [12, 30, 12, 14, 14, 12])

    # ==================================================================
    # Hoja: IFC_Elementos (desde RE3)
    # ==================================================================
    if re3:
        ws5 = wb.create_sheet("IFC_Elementos")
        headers = ["GUID", "Tipo Ifc", "Nombre", "Cantidad", "Valor", "Unidad"]
        datos = []
        for e in re3.get("elementos", []):
            for cant in e.get("cantidades", []):
                datos.append([
                    e.get("guid", ""),
                    e.get("tipo_ifc", ""),
                    e.get("nombre", ""),
                    cant.get("nombre_cantidad", ""),
                    cant.get("valor", ""),
                    cant.get("unidad", ""),
                ])
        _escribir_hoja(
            ws5, "ELEMENTOS IFC", [], headers, datos,
            [40, 22, 30, 22, 14, 12],
        )

    # ==================================================================
    # Hoja: IFC_Resumen (desde RE3)
    # ==================================================================
    if re3:
        ws6 = wb.create_sheet("IFC_Resumen")
        headers = ["Tipo Ifc", "Conteo"]
        datos = []
        for tipo, conteo in re3.get("resumen", {}).get("conteos_por_tipo", {}).items():
            datos.append([tipo, conteo])
        _escribir_hoja(
            ws6, "RESUMEN IFC POR TIPO", [], headers, datos,
            [30, 12],
        )

    return wb


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Exporta los JSON de RE1/RE2/RE3 a un libro Excel (RevitElectrico)."
    )
    parser.add_argument("--json-re1", type=str, default="",
                        help="Ruta al JSON de RE1 (normalizado DXF)")
    parser.add_argument("--json-re2", type=str, default="",
                        help="Ruta al JSON de RE2 (mapeo bloques→Revit)")
    parser.add_argument("--json-ifc", type=str, default="",
                        help="Ruta al JSON de RE3 (lectura IFC)")
    parser.add_argument(
        "--xlsx-out", type=str, default="",
        help="Ruta del Excel de salida (default: exports/<chip>_reporte.xlsx)",
    )
    parser.add_argument(
        "--chip", type=str, default=DEFAULT_CHIP,
        help="Identificador del predio/lote (default: SANTAMARTA_T5)",
    )

    args = parser.parse_args()

    chip = args.chip or DEFAULT_CHIP

    re1 = _cargar_json(Path(args.json_re1) if args.json_re1 else None)
    re2 = _cargar_json(Path(args.json_re2) if args.json_re2 else None)
    re3 = _cargar_json(Path(args.json_ifc) if args.json_ifc else None)

    if not re1 and not re2 and not re3:
        raise SystemExit("Debe indicar al menos uno de: --json-re1, --json-re2, --json-ifc")

    wb = build_workbook(chip, re1, re2, re3)

    if args.xlsx_out:
        xlsx_out = Path(args.xlsx_out)
    else:
        root = Path(os.environ.get("REVITELECTRICO_ROOT", Path.cwd()))
        xlsx_out = root / "exports" / f"{chip}_reporte.xlsx"

    xlsx_out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(xlsx_out))

    hojas = ", ".join(wb.sheetnames)
    print("=== Exportación a Excel completada ===")
    print(f"Chip: {chip}")
    print(f"Hojas: {hojas}")
    print(f"Archivo guardado en: {xlsx_out}")


if __name__ == "__main__":
    main()

