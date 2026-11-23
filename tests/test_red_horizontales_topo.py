# -*- coding: utf-8 -*-
"""Prueba local de la topologia de red (no requiere Revit)."""
import re
import io

SRC = r'D:\Work\PROJECTS\RevitElectrico\scripts\pyrevit\RE7_CREAR_HORIZONTALES_PLENUM_F17_F18_v01.py'
src = io.open(SRC, encoding='utf-8').read()


def extraer(nombre):
    m = re.search(r'^def %s\(.*?(?=^def |\Z)' % nombre, src, re.S | re.M)
    return m.group(0)


ns = {'Z_PLENUM_MM': 15930.0, 'LARGO_MIN_MM': 5.0, 'TOL_GRUPO_Y_MM': 5.0}
code = extraer('agrupar_por_y') + '\n' + extraer('construir_red')
exec(compile(code, '<test>', 'exec'), ns)
agrupar, red = ns['agrupar_por_y'], ns['construir_red']

CASOS = [
    ("F17 cp entre xs", 8685.8, 5328.3, [
        (6551.2, 3028.3), (6551.2, 3028.3),
        (10319.5, 1511.7), (10319.5, 1641.7),
        (8685.8, 5328.3), (7648.7, 1971.6),
        (6556.2, 5788.3),
    ]),
    ("cp a la izquierda", 100.0, 5328.3, [
        (6551.2, 3028.3), (10319.5, 1511.7), (8685.8, 5328.3),
    ]),
    ("cp a la derecha", 20000.0, 5328.3, [
        (6551.2, 3028.3), (10319.5, 1511.7), (8685.8, 5328.3),
    ]),
    ("datos: par separado 40mm", 8685.8, 12458.5, [
        (8685.8, 12321.0 - 20.0), (8685.8, 12321.0 + 20.0),
        (6555.2, 14650.8), (7609.0, 15684.9),
    ]),
]

ok_total = True
for nombre, cp_x, cp_y, pares in CASOS:
    risers = [{'x': x, 'y': y} for (x, y) in pares]
    tramos, grupos = red(risers, cp_x, cp_y)

    def cubierto(r):
        # (a) tramo en X a su Y que abarque su X, o
        # (b) esta sobre la X del CP y el troncal en Y lo alcanza
        for t in tramos:
            if t['tipo'] != 'X':
                continue
            y = t['a'][1]
            xa, xb = sorted([t['a'][0], t['b'][0]])
            if abs(r['y'] - y) <= 6.0 and xa - 1 <= r['x'] <= xb + 1:
                return True
        for t in tramos:
            if t['tipo'] != 'Y_troncal':
                continue
            ya, yb = sorted([t['a'][1], t['b'][1]])
            if abs(r['x'] - t['a'][0]) <= 6.0 and ya - 1 <= r['y'] <= yb + 1:
                return True
        return False

    faltan = [r for r in risers if not cubierto(r)]
    troncal = [t for t in tramos if t['tipo'] == 'Y_troncal']
    ok = len(faltan) == 0
    ok_total = ok_total and ok
    print("%-28s grupos=%d tramos=%d troncal=%s cobertura=%s faltan=%d" % (
        nombre, len(grupos), len(tramos),
        'si' if troncal else 'no',
        'OK' if ok else 'FALLA', len(faltan)))
    for t in tramos:
        print("    %-9s %s -> %s" % (t['tipo'], t['a'], t['b']))

print("")
print("RESULTADO TOPOLOGIA:", "OK" if ok_total else "FALLA")
raise SystemExit(0 if ok_total else 1)
