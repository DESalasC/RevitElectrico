# -*- coding: utf-8 -*-
# encontrar_panel_F01_v57.py | v57.0 | Python 3
# Busca la posición del panel TF 01 en el DXF del F01
import json
import ezdxf

DXF_PATH = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo F 01.dxf"

print("=" * 78)
print("BUSCAR PANEL EN DXF F01 v57.0")
print("=" * 78)

doc = ezdxf.readfile(DXF_PATH)
msp = doc.modelspace()

print("\nBuscando 'TF 01', 'Panel' o 'Tablero' en el DXF...")

candidatos = []

for entity in msp:
    if entity.dxftype() == 'INSERT':
        name = entity.dxf.name.upper()
        if 'TF' in name or 'PANEL' in name or 'TABLERO' in name:
            candidatos.append({
                "tipo": "Bloque",
                "nombre": entity.dxf.name,
                "handle": entity.dxf.handle,
                "x": entity.dxf.insert[0],
                "y": entity.dxf.insert[1]
            })
    elif entity.dxftype() in ['TEXT', 'MTEXT']:
        text = ""
        if hasattr(entity.dxf, 'text'):
            text = entity.dxf.text.upper()
        elif hasattr(entity, 'text'):
            text = entity.text.upper()
        
        if 'TF 01' in text or 'TF01' in text:
            x = entity.dxf.insert[0] if hasattr(entity.dxf, 'insert') else 0
            y = entity.dxf.insert[1] if hasattr(entity.dxf, 'insert') else 0
            candidatos.append({
                "tipo": "Texto",
                "nombre": text.strip(),
                "handle": entity.dxf.handle,
                "x": x,
                "y": y
            })

print("\nCandidatos encontrados: %d" % len(candidatos))

for i, c in enumerate(candidatos):
    print("  [%d] %-10s | %-20s | Handle=%-5s | Pos=(%.3f, %.3f)" % (
        i+1, c["tipo"], c["nombre"], c["handle"], c["x"], c["y"]))

if len(candidatos) > 0:
    print("\n" + "=" * 78)
    print("CÁLCULO DE TRANSFORMACIÓN")
    print("=" * 78)
    
    # Asumimos que el primer candidato es el panel
    panel_dxf = candidatos[0]
    
    # Posición del panel TF 01 en Revit (del diagnóstico anterior)
    panel_revit_x = 11.59
    panel_revit_y = 7.51
    
    # Calcular offset
    # x_revit = (x_dxf + offset_x)
    # offset_x = x_revit - x_dxf
    offset_x = panel_revit_x - panel_dxf["x"]
    offset_y = panel_revit_y - panel_dxf["y"]
    
    print("Panel en DXF: (%.3f, %.3f)" % (panel_dxf["x"], panel_dxf["y"]))
    print("Panel en Revit: (%.3f, %.3f)" % (panel_revit_x, panel_revit_y))
    print("\nOffset de transformación calculado:")
    print("  ORIG_X = %.6f" % offset_x)
    print("  ORIG_Y = %.6f" % offset_y)
    
    print("\n" + "=" * 78)
    print("COPIA ESTOS VALORES PARA EL SCRIPT DE COLOCACIÓN:")
    print("  ORIG_X = %.6f" % offset_x)
    print("  ORIG_Y = %.6f" % offset_y)
    print("=" * 78)
else:
    print("\nNo se encontraron candidatos. Usaremos el origen del bloque como referencia.")
    print("  ORIG_X = 3.112690  (para alinear el origen del bloque con 0,0)")
    print("  ORIG_Y = 6.825104")