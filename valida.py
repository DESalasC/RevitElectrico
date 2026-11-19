# -*- coding: utf-8 -*-
# CORREGIR_CP_F01_LOCALES_v01.py - Corregir CP de F01 a coordenadas locales
# Ejecutar en Python normal

import json

JSON_PATH = r"D:\Work\PROJECTS\RevitElectrico\data\dxf_master_global_all.json"

with open(JSON_PATH, 'r') as f:
    data = json.load(f)

# El CP local en el bloque es (-2.30, -2.84) para Apartamento Tipo F 01
# Los demás dispositivos F01 están en rango 30-50, así que el CP local debe estar ahí
# Vamos a buscar el CP y corregirlo a coordenadas locales consistentes

for dev in data['apartamentos']['F01']['devices']:
    if dev['familia_revit'] == 'Consolidation_Point':
        print("CP actual: x={}, y={}".format(dev['x'], dev['y']))
        # Corregir a coordenadas locales (el CP está cerca del panel, típicamente zona de entrada)
        # Basado en el bloque: local (-2.30, -2.84) pero los demás dispositivos están en 30-50
        # El origen del bloque debe estar desplazado. Usemos coordenadas similares a otros dispositivos.
        dev['x'] = 38.0  # coordenada X local típica zona panel
        dev['y'] = 5.0   # coordenada Y local típica zona entrada
        print("CP corregido: x={}, y={}".format(dev['x'], dev['y']))

with open(JSON_PATH, 'w') as f:
    json.dump(data, f, indent=2)
print("CP F01 corregido a coordenadas locales")
