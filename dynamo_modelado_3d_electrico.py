"""
Script Dynamo para Revit 2026 — Fase 3: Modelado 3D eléctrico desde DXF.
Crea dispositivos (familias) y conductos/cableado 3D para validación de interferencias.
Entradas: STM-T4-P4_extraccion_revit.json + STM-T4-P4_geometrias_3d.json
Nivel: "Piso 4"
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
clr.AddReference('DynamoNodes')
clr.AddReference('DynamoServices')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from Autodesk.Revit.DB.Electrical import *
from Autodesk.Revit.DB.Plumbing import *
from System.Collections.Generic import List

import json
import math

# --- CONFIGURACION ---
JSON_BLOQUES = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\3.-Proceso\STM-T4-P4_extraccion_revit.json"
JSON_GEOMETRIAS = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\3.-Proceso\STM-T4-P4_geometrias_3d.json"
NOMBRE_NIVEL = "Piso 4"
DIAMETRO_CONDUIT_PULGADAS = 0.75  # Diametro default del conducto (ajustable)
ESCALA_MM_A_PIES = 1.0 / 304.8

# --- OBTENER DOCUMENTO ---
doc = DocumentManager.Instance.CurrentDBDocument

# --- CARGAR JSON ---
with open(JSON_BLOQUES, "r", encoding="utf-8") as f:
    datos_bloques = json.load(f)
with open(JSON_GEOMETRIAS, "r", encoding="utf-8") as f:
    datos_geom = json.load(f)

bloques = datos_bloques["bloques"]
polilineas = datos_geom["polilineas"]

# --- BUSCAR NIVEL "Piso 4" ---
nivel = None
collector_nivel = FilteredElementCollector(doc).OfClass(Level)
for lv in collector_nivel:
    if lv.Name.strip().lower() == NOMBRE_NIVEL.strip().lower():
        nivel = lv
        break

if nivel is None:
    niveles = [lv.Name for lv in collector_nivel]
    raise Exception(f"Nivel '{NOMBRE_NIVEL}' no encontrado. Niveles: {niveles}")

# --- BUSCAR FAMILIA DE DISPOSITIVO ELECTRICO ---
familia = None
categorias_electricas = ["Electrical Equipment", "Electrical Devices", "Lighting Fixtures",
                         "Dispositivos eléctricos", "Iluminación", "Receptacles", "Switches"]
collector_fam = FilteredElementCollector(doc).OfClass(Family)
for fam in collector_fam:
    try:
        cat = fam.FamilyCategory.Name if fam.FamilyCategory else ""
        if any(c.lower() in cat.lower() for c in categorias_electricas):
            familia = fam
            break
    except Exception:
        continue

if familia is None:
    # Fallback: cualquier familia con "electric" en el nombre
    for fam in collector_fam:
        if "electric" in fam.Name.lower() or "electrica" in fam.Name.lower():
            familia = fam
            break

if familia is None:
    raise Exception("No se encontro familia eléctrica cargada. Carga una familia primero (Insertar > Cargar familia).")

simbolos = list(familia.GetFamilySymbolIds())
if len(simbolos) == 0:
    familia.Activate()
    doc.Regenerate()
    simbolos = list(familia.GetFamilySymbolIds())
simbolo_id = simbolos[0]
simbolo = doc.GetElement(simbolo_id)
if not simbolo.IsActive:
    simbolo.Activate()
    doc.Regenerate()

# --- BUSCAR TIPO DE CONDUIT (para conductos 3D) ---
conduit_tipo = None
collector_conduit = FilteredElementCollector(doc).OfClass(ConduitType)
for ct in collector_conduit:
    conduit_tipo = ct
    break

if conduit_tipo is None:
    raise Exception("No se encontro ningun tipo de Conduit cargado. Carga un tipo de conducto eléctrico.")

# --- MAPEO PARAMETROS ---
MAPEO_PARAMETROS = {
    "RED_Sistema": "RED",
    "Circuito": "CIRCUITO",
    "Altura_Instalacion": "ALTURA_INST",
    "Acometida": "ACOMETIDA",
    "Cableado": "CABLEADO",
    "Devuelto": "DEVUELTO",
    "Tipo_Dispositivo": "TIPO",
    "Fase": "FASE",
    "Amperaje": "AMPERAJE",
    "Voltaje": "VOLTAJE",
    "Observaciones": "OBSERVACIONES",
}

# --- TRANSACCION ---
t = Transaction(doc, "Modelado 3D eléctrico desde DXF")
t.Start()

contador_dispositivos = 0
contador_conductos = 0
contador_errores = 0

# --- 1. CREAR DISPOSITIVOS ELECTRICOS (desde bloques INSERT) ---
for bloque in bloques:
    try:
        nombre = bloque["nombre_bloque"]
        x_mm, y_mm, z_mm = bloque["punto_insert"]
        punto = XYZ(x_mm * ESCALA_MM_A_PIES, y_mm * ESCALA_MM_A_PIES, z_mm * ESCALA_MM_A_PIES)

        dispositivo = doc.Create.NewFamilyInstance(punto, simbolo, nivel, Structure.StructuralType.NonStructural)

        atributos_revit = bloque.get("atributos_para_revit", {})
        for param_revit, tag_dxf in MAPEO_PARAMETROS.items():
            valor = atributos_revit.get(param_revit, "")
            if valor and str(valor).strip():
                param = dispositivo.LookupParameter(param_revit)
                if param is not None and not param.IsReadOnly:
                    try:
                        param.Set(str(valor).strip())
                    except Exception:
                        pass

        contador_dispositivos += 1
    except Exception as e:
        contador_errores += 1
        print(f"Error dispositivo '{bloque.get('nombre_bloque', '?')}': {str(e)}")

# --- 2. CREAR CONDUCTOS 3D (desde LWPOLYLINE electricas) ---
for pl in polilineas:
    if not pl["es_electrica"]:
        continue

    try:
        puntos_mm = pl["puntos"]
        if len(puntos_mm) < 2:
            continue

        # Convertir puntos a XYZ en pies
        puntos_xyz = [XYZ(p[0] * ESCALA_MM_A_PIES, p[1] * ESCALA_MM_A_PIES, p[2] * ESCALA_MM_A_PIES)
                      for p in puntos_mm]

        # Crear curva a partir de los puntos (lineas rectas entre puntos consecutivos)
        curvas = []
        for i in range(len(puntos_xyz) - 1):
            curvas.append(Line.CreateBound(puntos_xyz[i], puntos_xyz[i + 1]))

        # Si la polilinea está cerrada, unir ultimo con primero
        if pl["cerrada"] and len(puntos_xyz) > 2:
            curvas.append(Line.CreateBound(puntos_xyz[-1], puntos_xyz[0]))

        # Crear conducto para cada segmento
        for curva in curvas:
            try:
                conduit = Conduit.Create(doc, conduit_tipo.Id, nivel.Id, curva.GetEndPoint(0), curva.GetEndPoint(1))
                # Establecer diametro si el parametro existe
                param_diam = conduit.LookupParameter("Diameter")
                if param_diam is not None and not param_diam.IsReadOnly:
                    try:
                        param_diam.Set(DIAMETRO_CONDUIT_PULGADAS)
                    except Exception:
                        pass
                contador_conductos += 1
            except Exception:
                # Si Conduit.Create falla, intentar con ModelLine como fallback
                try:
                    doc.Create.NewModelCurve(curva, nivel)
                except Exception:
                    pass

    except Exception as e:
        contador_errores += 1
        print(f"Error conducto polilinea: {str(e)}")

t.Commit()

# --- RESULTADO ---
resultado = {
    "nivel_usado": nivel.Name,
    "familia_dispositivo": familia.Name,
    "tipo_conduit": conduit_tipo.Name if conduit_tipo else "N/A",
    "dispositivos_creados": contador_dispositivos,
    "conductos_creados": contador_conductos,
    "errores": contador_errores,
}

print(json.dumps(resultado, indent=2, ensure_ascii=False))
resultado
