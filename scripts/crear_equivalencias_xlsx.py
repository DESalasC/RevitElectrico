#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crear tabla de equivalencias apartamentos Piso 5 en .xlsx"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Datos de la tabla
headers = [
    "Apartamento_JSON", "Panel_Revit", "Tipo_Apto", "Dispositivos_Total",
    "Tomas_Muro", "Comunicaciones_Muro", "Interruptores_Nivel",
    "Pulsador_Timbre_Muro", "Timbre_Nivel", "Campana_Nivel",
    "Iluminacion_Techo", "ClimatizacionV_Techo", "EA_Nivel", "CP_Muro",
    "Techo_Id", "Techo_Z_ft", "Script_Tomas_v12", "Script_Iluminacion",
    "Script_Interruptores_Pendiente", "Estado_Colocacion", "Observaciones"
]

rows = [
    ["F01", "TF 01", "F01/F02 (Piloto)", 37, 12, 10, 3, 1, 1, 1, 8, 1, 0, 1, 2764963, 51.9, "v12_OK", "v09_OK", "Pendiente", "VALIDADO 37/37 v16.2", "Piloto ruteo, techos confirmados"],
    ["F02", "TF 02", "F01/F02 (Piloto)", 37, 12, 10, 3, 1, 1, 1, 8, 1, 0, 1, 2766313, 51.9, "v12_OK", "v09_OK", "Pendiente", "VALIDADO 37/37 v16.2", "Piloto ruteo, techos confirmados"],
    ["F17", "TF 17", "Estándar", 20, 6, 4, 2, 1, 1, 1, 4, 1, 0, 1, None, None, "Pendiente", "Pendiente", "Pendiente", "Pendiente", "Ceiling mapping OK"],
    ["F18", "TF 18", "Estándar", 20, 6, 4, 2, 1, 1, 1, 4, 1, 0, 1, None, None, "Pendiente", "Pendiente", "Pendiente", "Pendiente", "Ceiling mapping OK"],
    ["F17a", "—", "Variante F17", 32, 10, 8, 3, 1, 1, 1, 6, 1, 0, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Sin ceiling mapping, requiere v12"],
    ["F18a", "—", "Variante F18", 45, 14, 11, 4, 1, 1, 1, 9, 2, 0, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Sin ceiling mapping, requiere v12"],
    ["TF_01a", "TF 01a", "Variante TF 01", 23, 8, 5, 2, 1, 1, 1, 4, 1, 1, 0, None, None, "v12_OK_23/23", "Pendiente", "Pendiente", "TOMAS_OK", "Cluster 4 datos apilados (corrección manual RE-P-071)"],
    ["TF_01b", "TF 01b", "Variante TF 01", 32, 10, 8, 3, 1, 1, 1, 6, 1, 1, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Sin ceiling mapping, requiere v12"],
    ["TF_02", "TF 02", "Estándar", 36, 11, 9, 3, 1, 1, 1, 8, 1, 1, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Panel TF 02* (verificar)"],
    ["TF_02a", "—", "Variante TF 02", 45, 14, 11, 4, 1, 1, 1, 9, 2, 1, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Sin ceiling mapping, requiere v12"],
    ["TF_02b", "—", "Variante TF 02", 34, 10, 8, 3, 1, 1, 1, 7, 1, 1, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Sin ceiling mapping, requiere v12"],
    ["E05", "—", "Tipo E", 65, 20, 16, 5, 2, 2, 2, 12, 2, 2, 2, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Requiere RE-P-059 (DXF E06)"],
    ["E06", "TE 06", "Tipo E", 65, 20, 16, 5, 2, 2, 2, 12, 2, 2, 2, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Requiere RE-P-059 re-inventario"],
    ["E07", "TE 07", "Tipo E", 45, 14, 11, 4, 1, 1, 1, 9, 2, 1, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Bloqueado por RE-P-059/060"],
    ["E07a", "—", "Variante E07", 51, 16, 12, 4, 2, 1, 1, 10, 2, 2, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Sin ceiling mapping, bloqueado RE-P-059"],
    ["E08", "TE 08", "Tipo E", 45, 14, 11, 4, 1, 1, 1, 9, 2, 1, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Bloqueado por RE-P-059/060"],
    ["E08a", "—", "Variante E08", 52, 16, 13, 4, 2, 1, 1, 10, 2, 2, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Sin ceiling mapping, bloqueado RE-P-059"],
    ["B15", "TB 15", "Tipo B", 64, 19, 15, 5, 2, 2, 2, 12, 2, 2, 2, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Ceiling mapping OK"],
    ["B16", "TB 16", "Tipo B", 65, 19, 15, 5, 2, 2, 2, 12, 2, 2, 2, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Ceiling mapping OK"],
    ["C14", "TC 14", "Tipo C", 56, 17, 13, 4, 2, 1, 1, 10, 2, 2, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Ceiling mapping OK"],
    ["D13", "TD 13", "Tipo D", 46, 14, 11, 4, 1, 1, 1, 9, 2, 1, 1, None, None, "Pendiente v12", "Pendiente", "Pendiente", "Pendiente", "Ceiling mapping OK"],
]

# Crear workbook
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Equivalencias_JSON_Panel_Script"

# Estilos
header_font = Font(bold=True, color="FFFFFF", size=11)
header_fill = PatternFill(start_color="0F6B5F", end_color="0F6B5F", fill_type="solid")
header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
thin_border = Border(
    left=Side(style="thin"),
    right=Side(style="thin"),
    top=Side(style="thin"),
    bottom=Side(style="thin")
)

validated_fill = PatternFill(start_color="E7F2EF", end_color="E7F2EF", fill_type="solid")
pending_fill = PatternFill(start_color="FFF8E7", end_color="FFF8E7", fill_type="solid")
blocked_fill = PatternFill(start_color="FDEDEC", end_color="FDEDEC", fill_type="solid")
ok_fill = PatternFill(start_color="E7F2EF", end_color="E7F2EF", fill_type="solid")

# Escribir headers
for col_idx, header in enumerate(headers, 1):
    cell = ws.cell(row=1, column=col_idx, value=header)
    cell.font = header_font
    cell.fill = header_fill
    cell.alignment = header_align
    cell.border = thin_border

# Escribir datos
for row_idx, row_data in enumerate(rows, 2):
    for col_idx, value in enumerate(row_data, 1):
        cell = ws.cell(row=row_idx, column=col_idx, value=value)
        cell.border = thin_border
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        
        # Colorear según estado (columna 20 = Estado_Colocacion)
        estado = row_data[19] if len(row_data) > 19 else ""
        if "VALIDADO" in str(estado) or "OK" in str(estado):
            if col_idx == 20:  # Solo colorear la celda de estado
                cell.fill = validated_fill
        elif "Pendiente" in str(estado):
            if col_idx == 20:
                cell.fill = pending_fill
        elif "BLOQUEADO" in str(estado).upper() or "Bloqueado" in str(estado):
            if col_idx == 20:
                cell.fill = blocked_fill

# Ajustar anchos de columna
col_widths = {
    1: 18,   # Apartamento_JSON
    2: 12,   # Panel_Revit
    3: 20,   # Tipo_Apto
    4: 16,   # Dispositivos_Total
    5: 14,   # Tomas_Muro
    6: 18,   # Comunicaciones_Muro
    7: 18,   # Interruptores_Nivel
    8: 20,   # Pulsador_Timbre_Muro
    9: 12,   # Timbre_Nivel
    10: 12,  # Campana_Nivel
    11: 16,  # Iluminacion_Techo
    12: 20,  # ClimatizacionV_Techo
    13: 10,  # EA_Nivel
    14: 10,  # CP_Muro
    15: 12,  # Techo_Id
    16: 10,  # Techo_Z_ft
    17: 18,  # Script_Tomas_v12
    18: 16,  # Script_Iluminacion
    19: 28,  # Script_Interruptores_Pendiente
    20: 22,  # Estado_Colocacion
    21: 55,  # Observaciones
}

for col_idx, width in col_widths.items():
    ws.column_dimensions[get_column_letter(col_idx)].width = width

# Freeze panes
ws.freeze_panes = "A2"

# Auto-filter
ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows)+1}"

# Guardar
output_path = r"D:\Work\PROJECTS\RevitElectrico\data\equivalencias_apartamentos_piso5.xlsx"
wb.save(output_path)
print(f"Archivo guardado en: {output_path}")
print(f"Filas: {len(rows)} apartamentos + header")
print(f"Columnas: {len(headers)}")