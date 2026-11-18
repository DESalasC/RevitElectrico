import json
with open('data/v02f/dispositivos_v01.json', 'r', encoding='utf-8') as f:
    v02f = json.load(f)

print('=== Posibles F01 (Y ~5000-8000) ===')
for d in v02f:
    if 4000 < d.get('y', 0) < 8500:
        print(f'  {d.get("fam")} | {d.get("tipo")} | x={d.get("x"):.0f} y={d.get("y"):.0f} z={d.get("z"):.0f} rot={d.get("rot", 0)} host={d.get("host")}')

print()
print('=== Posibles F02 (Y ~9000-12000) ===')
for d in v02f:
    if 8500 < d.get('y', 0) < 12000:
        print(f'  {d.get("fam")} | {d.get("tipo")} | x={d.get("x"):.0f} y={d.get("y"):.0f} z={d.get("z"):.0f} rot={d.get("rot", 0)} host={d.get("host")}')