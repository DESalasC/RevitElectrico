with open("D:/Work/PROJECTS/RevitElectrico/scripts/F6_COLOCAR_PYREVIT_v01.py", "r", encoding="utf-8") as f:
    content = f.read()

# Remove ezdxf import and use hardcoded offsets
old_offset = '''    # 4. Panel en DXF local
    dxf_filename = meta["origen_dxf"]["archivo"]
    dxf_path = os.path.join(ARCHIVOS_BASE_DIR, dxf_filename)
    import ezdxf
    doc_dxf = ezdxf.readfile(dxf_path)
    msp = doc_dxf.modelspace()
    panel_dxf = None
    for e in msp:
        if e.dxftype() == 'INSERT' and e.dxf.name in ('TB-Panel', 'TB-Parcial'):
            for a in e.attribs:
                if a.dxf.tag.upper() == 'TABLERO' and a.dxf.text.strip() == target_panel_name:
                    panel_dxf = (float(e.dxf.insert.x), float(e.dxf.insert.y))
                    break
    if not panel_dxf:
        print("[ERROR] Panel {} no en DXF".format(target_panel_name))
        return None
    print("[INFO] Panel DXF local: ({:.4f}, {:.4f}) m".format(panel_dxf[0], panel_dxf[1]))

    # 5. Offset dinámico
    pdmm = (panel_dxf[0] * 1000, panel_dxf[1] * 1000)
    prmm = (panel_obj["x"], panel_obj["y"])
    offset_x = prmm[0] - pdmm[0]
    offset_y = prmm[1] - pdmm[1]
    print("[INFO] Offset calculado: ({:.1f}, {:.1f}) mm".format(offset_x, offset_y))'''

new_offset = '''    # 4. Offset dinámico (pre-calculado: panel DXF local vs panel Revit)
    # F01: Panel DXF (-2.3995, -0.5048) -> Panel Revit (11591.4, 7505.8) = Offset (13990.9, 8010.6)
    # F02: Panel DXF (-2.4403, 0.5056)  -> Panel Revit (11597.1, 10160.3) = Offset (14037.4, 9654.7)
    OFFSETS = {
        "F01": (13990.9, 8010.6),
        "F02": (14037.4, 9654.7),
    }
    offset_x, offset_y = OFFSETS[apartamento]
    print("[INFO] Offset {}: ({:.1f}, {:.1f}) mm".format(apartamento, offset_x, offset_y))'''

content = content.replace(old_offset, new_offset)

with open("D:/Work/PROJECTS/RevitElectrico/scripts/F6_COLOCAR_PYREVIT_v01.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Removed ezdxf dependency, using hardcoded offsets")