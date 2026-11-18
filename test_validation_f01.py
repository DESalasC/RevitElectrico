import json

with open('data/colocaciones/colocacion_F01_v1.0_20261117_221832.json', 'r', encoding='utf-8') as f:
    r = json.load(f)

with open('data/v02f/dispositivos_v01.json', 'r', encoding='utf-8') as f:
    v02f = json.load(f)

ref = {}
for dv in v02f:
    ref[f"{dv.get('fam')}_{dv.get('tipo')}_{round(dv.get('x',0))}_{round(dv.get('y',0))}"] = dv

offset_x = 13990.9
offset_y = 8010.6
coinc = 0
TOL_POS = 50
TOL_ALT = 20
TOL_ROT = 5

for c in [x for x in r['colocados'] if x.get('success')]:
    cx = c['x'] * 1000 + offset_x
    cy = c['y'] * 1000 + offset_y
    cz = c['z_absoluta_m'] * 1000
    best = None; bd = 1e9
    for k, r_ref in ref.items():
        dx = abs(cx - r_ref.get('x',0)); dy = abs(cy - r_ref.get('y',0)); dz = abs(cz - r_ref.get('z',0))
        d = (dx*dx+dy*dy+dz*dz)**0.5
        if d < bd and d < 1000: bd = d; best = r_ref
    if best:
        dx = abs(cx - best.get('x',0)); dy = abs(cy - best.get('y',0)); dz = abs(cz - best.get('z',0))
        drot = abs(c['rotacion_final_grados'] - best.get('rot',0)); drot = min(drot, 360-drot)
        if dx<=TOL_POS and dy<=TOL_POS and dz<=TOL_ALT and drot<=TOL_ROT:
            coinc += 1
        else:
            print(f'  NO match: {c["handle"]} dx={dx:.0f} dy={dy:.0f} dz={dz:.0f} drot={drot:.1f}')
            print(f'    placed: ({cx:.0f},{cy:.0f},{cz:.0f}) ref: ({best.get("x",0):.0f},{best.get("y",0):.0f},{best.get("z",0):.0f}) rot_p={c["rotacion_final_grados"]} rot_r={best.get("rot",0)}')
    else:
        print(f'  NO ref found: {c["handle"]} ({cx:.0f},{cy:.0f},{cz:.0f})')

ok_count = len([x for x in r['colocados'] if x.get('success')])
print(f'Coinciden: {coinc}/{ok_count} = {coinc/ok_count*100:.1f}%')