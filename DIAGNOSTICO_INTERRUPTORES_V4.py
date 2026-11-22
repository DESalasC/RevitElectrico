# -*- coding: utf-8 -*-
# DIAGNOSTICO_INTERRUPTORES_V4.py - SOLO LECTURA (sin transacciones)
# Objetivo: coordenadas REALES de todas las instancias M_Interruptores y
# M_Pulsador - Interruptor, para confirmar donde cayeron las LEVEL del v03
# y detectar clusters de timbres duplicados.
# Ejecutar en pyRevit Python Shell:
#   exec(open(r"D:\Work\PROJECTS\RevitElectrico\DIAGNOSTICO_INTERRUPTORES_V4.py").read())

import clr
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *

doc = __revit__.ActiveUIDocument.Document
MM = 304.8

interruptores = []  # M_Interruptores
pulsadores = []     # M_Pulsador - Interruptor

for e in FilteredElementCollector(doc).OfClass(FamilyInstance):
    try:
        fam_name = e.Symbol.Family.Name
    except:
        continue
    if fam_name == 'M_Interruptores':
        target = interruptores
    elif fam_name == 'M_Pulsador - Interruptor':
        target = pulsadores
    else:
        continue
    loc = e.Location
    if not isinstance(loc, LocationPoint):
        continue
    p = loc.Point
    mark_param = e.get_Parameter(BuiltInParameter.ALL_MODEL_MARK)
    mark = mark_param.AsString() if mark_param else ''
    if not mark:
        mark = '(sin mark)'
    target.append({
        'id': int(str(e.Id)),
        'x': float(p.X) * MM,
        'y': float(p.Y) * MM,
        'z': float(p.Z) * MM,
        'mark': mark
    })

# ---------------- A. M_Interruptores ----------------
print('=' * 64)
print('A. M_Interruptores EN MODELO: {}'.format(len(interruptores)))
print('=' * 64)

en_origen = [i for i in interruptores if abs(i['x']) < 10.0 and abs(i['y']) < 10.0]
en_posicion = [i for i in interruptores if not (abs(i['x']) < 10.0 and abs(i['y']) < 10.0)]

print('  En ORIGEN (X~0, Y~0): {}'.format(len(en_origen)))
if en_origen:
    zs = {}
    for i in en_origen:
        zs[round(i['z'])] = zs.get(round(i['z']), 0) + 1
    print('    Histograma Z (mm):')
    for k in sorted(zs):
        print('      Z={}mm  ->  {} instancias'.format(k, zs[k]))
    for i in en_origen[:5]:
        print('    ej: Id={} Z={}mm Mark={}'.format(i['id'], round(i['z'], 1), i['mark']))

print('  En POSICION REAL (XY != 0): {}'.format(len(en_posicion)))
for i in sorted(en_posicion, key=lambda a: (a['mark'], a['x']))[:15]:
    print('    Id={} X={} Y={} Z={} Mark={}'.format(
        i['id'], round(i['x'], 1), round(i['y'], 1), round(i['z'], 1), i['mark']))

# Marca del v03: 'Interupt_<tipo>_<x>_<y>' (familia truncada a 8 chars)
v03_marks = [i for i in interruptores
             if i['mark'].startswith('Interupt') or i['mark'].startswith('Interrupt')]
print('  Con Mark formato v03 (Interupt_/Interrupt_*): {}'.format(len(v03_marks)))
for i in v03_marks[:12]:
    print('    Id={} X={} Y={} Z={} Mark={}'.format(
        i['id'], round(i['x'], 1), round(i['y'], 1), round(i['z'], 1), i['mark']))

# ---------------- B. Timbres: clusters duplicados ----------------
print('')
print('=' * 64)
print('B. M_Pulsador - Interruptor (timbres): {}'.format(len(pulsadores)))
print('=' * 64)

TOL = 150.0  # mm
restantes = sorted(pulsadores, key=lambda a: a['id'])
clusters = []
while restantes:
    base = restantes.pop(0)
    grupo = [base]
    quedan = []
    for otro in restantes:
        if abs(otro['x'] - base['x']) <= TOL and abs(otro['y'] - base['y']) <= TOL:
            grupo.append(otro)
        else:
            quedan.append(otro)
    restantes = quedan
    clusters.append(grupo)

dup_clusters = [g for g in clusters if len(g) > 1]
extras = sum(len(g) - 1 for g in dup_clusters)
print('  Clusters totales: {} | con duplicados: {} | instancias sobrantes: {}'.format(
    len(clusters), len(dup_clusters), extras))
print('  (tolerancia cluster: {}mm en XY)'.format(TOL))
for g in dup_clusters:
    print('  DUPLICADO x{} @ X={} Y={}:'.format(
        len(g), round(g[0]['x'], 1), round(g[0]['y'], 1)))
    for i in sorted(g, key=lambda a: a['id']):
        print('    Id={} Z={}mm Mark={}'.format(i['id'], round(i['z'], 1), i['mark']))

print('')
print('DIAGNOSTICO COMPLETO - no se modifico nada')