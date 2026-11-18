with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "r", encoding="utf-8") as f:
    content = f.read()

old = """        x_mm = d["x"] * 1000 + offset_x
        y_mm = d["y"] * 1000 + offset_y
        z_mm = (nivel_elevacion + d["altura_local_m"]) * 1000  # Z absoluto en mm
        fam = d["familia_revit"]; tip = d["tipo_revit"]; rot = d["rotacion_final_grados"]; lvl = panel_obj["levelId"]
        alt_mm = d["altura_local_m"] * 1000

        # Elegir C# según familia
        if fam in FAMILIAS_TECHO_FACE:
            cs_template = CS_FACE_CEILING
        elif fam in FAMILIAS_MURO_FACE:
            cs_template = CS_FACE_WALL
        else:
            cs_template = CS_LEVEL_BASED"""

new = """        x_mm = d["x"] * 1000 + offset_x
        y_mm = d["y"] * 1000 + offset_y
        fam = d["familia_revit"]; tip = d["tipo_revit"]; rot = d["rotacion_final_grados"]; lvl = panel_obj["levelId"]
        alt_mm = d["altura_local_m"] * 1000

        # Elegir C# según familia - Z absoluto para face-based, relativo para level-based
        if fam in FAMILIAS_TECHO_FACE:
            cs_template = CS_FACE_CEILING
            z_mm = (nivel_elevacion + d["altura_local_m"]) * 1000  # Z absoluto para techo face-based
        elif fam in FAMILIAS_MURO_FACE:
            cs_template = CS_FACE_WALL
            z_mm = (nivel_elevacion + d["altura_local_m"]) * 1000  # Z absoluto para muro face-based
        else:
            cs_template = CS_LEVEL_BASED
            z_mm = alt_mm  # Z RELATIVO al nivel para level-based (fix: NewFamilyInstance con Level usa Z relativo)"""

content = content.replace(old, new)

with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed Z calculation for level-based families")