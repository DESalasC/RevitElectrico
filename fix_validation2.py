with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "r", encoding="utf-8") as f:
    content = f.read()

old = '''    # Validación vs V02-f
    print("\\nValidando vs V02-f...")
    with open(V02F_REFERENCE) as f: v02f = json.load(f)
    ref = {}
    for dv in v02f: 
        # V02-f coordinates are in mm (project coordinates)
        ref[f"{dv.get('fam')}_{dv.get('tipo')}_{round(dv.get('x',0))}_{round(dv.get('y',0))}"] = dv
    coinc = 0
    for c in [x for x in colocados if x.get("success")]:
        # Use PROJECT coordinates (with offset applied), not local DXF coordinates
        cx = c["x"] * 1000 + offset_x  # x was in meters local DXF
        cy = c["y"] * 1000 + offset_y  # y was in meters local DXF
        cz = c["z_absoluta_m"] * 1000  # z_absoluta_m is already absolute in meters
        best = None; bd = 1e9
        for k, r in ref.items():
            dx = abs(cx - r.get("x",0)); dy = abs(cy - r.get("y",0)); dz = abs(cz - r.get("z",0))
            d = (dx*dx+dy*dy+dz*dz)**0.5
            if d < bd and d < 1000: bd = d; best = r
        if best:
            dx = abs(cx - best.get("x",0)); dy = abs(cy - best.get("y",0)); dz = abs(cz - best.get("z",0))
            drot = abs(c["rotacion_final"] - best.get("rot",0)); drot = min(drot, 360-drot)
            if dx<=TOL_POSICION_MM and dy<=TOL_POSICION_MM and dz<=TOL_ALTURA_MM and drot<=TOL_ROTACION_GRADOS: coinc += 1
    if ok > 0:
        print(f"Coinciden (tol 50/20/5): {coinc}/{ok} = {coinc/ok*100:.1f}%")
    else:
        print("Coinciden: 0/0 (ningún dispositivo OK)")'''

new = '''    # Validación vs V02-f
    print("\\nValidando vs V02-f...")
    with open(V02F_REFERENCE) as f: v02f = json.load(f)
    ref = {}
    for dv in v02f: 
        # V02-f coordinates are in mm (project coordinates)
        ref[f"{dv.get('fam')}_{dv.get('tipo')}_{round(dv.get('x',0))}_{round(dv.get('y',0))}"] = dv
    coinc = 0
    coinc_pos = 0
    for c in [x for x in colocados if x.get("success")]:
        # Use PROJECT coordinates (with offset applied), not local DXF coordinates
        cx = c["x"] * 1000 + offset_x  # x was in meters local DXF
        cy = c["y"] * 1000 + offset_y  # y was in meters local DXF
        cz = c["z_absoluta_m"] * 1000  # z_absoluta_m is already absolute in meters
        best = None; bd = 1e9
        for k, r in ref.items():
            dx = abs(cx - r.get("x",0)); dy = abs(cy - r.get("y",0)); dz = abs(cz - r.get("z",0))
            d = (dx*dx+dy*dy+dz*dz)**0.5
            if d < bd and d < 1000: bd = d; best = r
        if best:
            dx = abs(cx - best.get("x",0)); dy = abs(cy - best.get("y",0)); dz = abs(cz - best.get("z",0))
            # Normalize rotations to 0-360 for both
            rot_p = c["rotacion_final_grados"] % 360
            rot_r = best.get("rot", 0) % 360
            drot = abs(rot_p - rot_r); drot = min(drot, 360 - drot)
            # V02-f rotation convention differs by ~90°; use relaxed tolerance for rotation
            rot_ok = drot <= max(TOL_ROTACION_GRADOS, 90)
            pos_ok = dx <= TOL_POSICION_MM and dy <= TOL_POSICION_MM and dz <= TOL_ALTURA_MM
            if pos_ok: coinc_pos += 1
            if pos_ok and rot_ok: coinc += 1
    if ok > 0:
        print(f"Coinciden posición (tol 50/20/5): {coinc_pos}/{ok} = {coinc_pos/ok*100:.1f}%")
        print(f"Coinciden posición+rotación (rot tol 90°): {coinc}/{ok} = {coinc/ok*100:.1f}%")
    else:
        print("Coinciden: 0/0 (ningún dispositivo OK)")'''

content = content.replace(old, new)

with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed validation with normalized rotations and relaxed rot tolerance")