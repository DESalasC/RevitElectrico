# -*- coding: utf-8 -*-
# TEST_FORCE_OVERLOAD_v01.py - Forzar overload correcto con reflexión
# Ejecutar en pyRevit

import clr, math, System
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import (XYZ, UV, ElementId, BuiltInCategory, BuiltInParameter,
    FilteredElementCollector, Wall, FamilySymbol, FamilyInstance,
    Transaction, HostObjectUtils, ShellLayerType, Reference)
from Autodesk.Revit.DB.Structure import StructuralType
from System import Int64, Double, Array, Type

doc = __revit__.ActiveUIDocument.Document

# 1. Buscar símbolo M_Toma doble
s = None
for elem in FilteredElementCollector(doc).WhereElementIsElementType().ToElements():
    try:
        if isinstance(elem, FamilySymbol) and "M_Toma doble" in elem.FamilyName:
            s = elem
            break
    except: pass

if not s:
    print("Símbolo no encontrado")
else:
    # 2. Muro 5349586 - Reference interior
    wall = doc.GetElement(ElementId(Int64(5349586)))
    if not wall:
        print("Muro no encontrado")
    else:
        try:
            int_refs = HostObjectUtils.GetSideFaces(wall, ShellLayerType.Interior)
            for ref in int_refs:
                face = wall.GetGeometryObjectFromReference(ref)
                if face and abs(face.FaceNormal.Z) < 0.1:
                    print("Reference OK, Normal=({:.1f},{:.1f},{:.1f})".format(
                        face.FaceNormal.X, face.FaceNormal.Y, face.FaceNormal.Z))
                    
                    uv = UV(0.0, 1.0)
                    rot = 1.5708
                    
                    t = Transaction(doc, "Force Overload"); t.Start()
                    try:
                        if not s.IsActive: s.Activate()
                        
                        # MÉTODO 1: Usar método estático FamilyInstance.Create con tipos explícitos
                        # FamilyInstance.Create(Document, Reference, UV, double, FamilySymbol)
                        create_method = FamilyInstance.Create
                        # No funciona en IronPython...
                        
                        # MÉTODO 2: Reflection para llamar overload específico
                        doc_type = doc.GetType()
                        create_type = doc.Create.GetType()
                        
                        # Buscar NewFamilyInstance(Reference, UV, double, FamilySymbol)
                        methods = create_type.GetMethods()
                        for m in methods:
                            if m.Name == "NewFamilyInstance":
                                params = m.GetParameters()
                                if len(params) == 4:
                                    ptypes = [p.ParameterType for p in params]
                                    if (str(ptypes[0]).endswith("Reference") and 
                                        str(ptypes[1]).endswith("UV") and
                                        str(ptypes[2]).endswith("Double") and
                                        str(ptypes[3]).endswith("FamilySymbol")):
                                        print("Encontrado overload: {}".format(m))
                                        # Invocar
                                        args = Array[object]([ref, uv, Double(rot), s])
                                        inst = m.Invoke(doc.Create, args)
                                        print("SUCCESS por Reflection!")
                                        print("Inst Id: {}".format(int(inst.Id.Value)))
                                        break
                        else:
                            print("No se encontró overload 4 args")
                        
                    except Exception as e:
                        print("Error: {}".format(e))
                    t.Commit()
                    break
        except Exception as e:
            print("Error general: {}".format(e))