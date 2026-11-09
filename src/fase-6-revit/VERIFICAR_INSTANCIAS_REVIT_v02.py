# -*- coding: utf-8 -*-
"""
VERIFICAR_INSTANCIAS_REVIT_v02.py — Versión simplificada para shell interactiva de Revit.
Verifica cuántas FamilyInstance existen en el documento activo.

USO (desde pyRevit Python Shell dentro de Revit):
  exec(open(r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\src\fase-6-revit\VERIFICAR_INSTANCIAS_REVIT_v02.py").read())


Ultimos tres cambios
--------------------
1. 2026-11-08 v02: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""

import json
import os
from datetime import datetime

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FamilyInstance,
    BuiltInCategory,
    Level,
    BuiltInParameter,
)


def _nombre_elemento(elemento):
    try:
        nombre = getattr(elemento, "Name", None)
        if nombre:
            return nombre
    except Exception:
        pass
    try:
        p = elemento.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            valor = p.AsString()
            if valor:
                return valor
    except Exception:
        pass
    return None


def _nombre_nivel(nivel):
    try:
        nombre = getattr(nivel, "Name", None)
        if nombre:
            return nombre
    except Exception:
        pass
    try:
        p = nivel.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            valor = p.AsString()
            if valor:
                return valor
    except Exception:
        pass
    return "Sin nivel"


def verificar_instancias_revit(doc, json_out=None):
    FilteredElementCollector
    niveles = {}
    try:
        colector_niveles = FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Levels).OfClass(Level)
        for niv in colector_niveles.ToElements():
            niveles[niv.Id.ToString()] = _nombre_nivel(niv)
    except Exception:
        pass

    categorias = [
        BuiltInCategory.OST_GenericModel,
        BuiltInCategory.OST_ElectricalEquipment,
        BuiltInCategory.OST_LightingFixtures,
        BuiltInCategory.OST_ElectricalFixtures,
    ]

    instancias = []
    for cat in categorias:
        try:
            colector = FilteredElementCollector(doc).OfCategory(cat)
            for inst in colector.ToElements():
                if not isinstance(inst, FamilyInstance):
                    continue
                try:
                    simbolo = inst.Symbol
                    nombre_fam = _nombre_elemento(simbolo) if simbolo is not None else "?"
                    nombre_sim = _nombre_elemento(inst) or "?"
                except Exception:
                    nombre_fam = "?"
                    nombre_sim = "?"
                try:
                    nivel_id = inst.LevelId.ToString()
                except Exception:
                    nivel_id = None
                nombre_nivel = niveles.get(nivel_id, "Sin nivel")
                try:
                    punto = inst.Location.Point
                    xyz = (round(punto.X, 4), round(punto.Y, 4), round(punto.Z, 4))
                except Exception:
                    xyz = None
                instancias.append({
                    "id": inst.Id.ToString(),
                    "familia": nombre_fam,
                    "simbolo": nombre_sim,
                    "nivel": nombre_nivel,
                    "nivel_id": nivel_id,
                    "xyz": xyz,
                    "categoria": str(cat),
                })
        except Exception:
            pass

    por_familia = {}
    for inst in instancias:
        fam = inst["familia"]
        if fam not in por_familia:
            por_familia[fam] = []
        por_familia[fam].append(inst)

    print("=" * 70)
    print("VERIFICACIÓN DE FamilyInstance EN REVIT")
    print("Documento: {}".format(doc.Title))
    print("=" * 70)
    print("Total FamilyInstance encontradas: {}".format(len(instancias)))
    print("\nPor familia:")
    for fam in sorted(por_familia.keys()):
        lista = por_familia[fam]
        print("  {} : {} instancia(s)".format(fam, len(lista)))
        for inst in lista[:5]:
            print("    - id={} | simbolo={} | nivel={} | xyz={}".format(
                inst["id"], inst["simbolo"], inst["nivel"], inst["xyz"]))
        if len(lista) > 5:
            print("    ... y {} más".format(len(lista) - 5))

    print("\nPor nivel:")
    por_nivel = {}
    for inst in instancias:
        niv = inst["nivel"]
        if niv not in por_nivel:
            por_nivel[niv] = []
        por_nivel[niv].append(inst)
    for niv in sorted(por_nivel.keys()):
        print("  {} : {}".format(niv, len(por_nivel[niv])))

    ids_esperados = [
        "5554235", "5554236", "5554237", "5554238", "5554239", "5554240",
        "5554241", "5554242", "5554243", "5554244", "5554245", "5554246",
        "5554247", "5554248", "5554249", "5554250", "5554251", "5554252",
        "5554253", "5554254", "5554255", "5554256", "5554257", "5554258",
        "5554259", "5554260", "5554261", "5554262", "5554263", "5554264",
        "5554265", "5554266", "5554267", "5554268", "5554269", "5554270",
        "5554271",
    ]
    ids_creados = set(inst["id"] for inst in instancias)
    encontrados = [eid for eid in ids_esperados if eid in ids_creados]
    print("\nElementos del bloque F 02 (IDs del reporte):")
    print("  Esperados: {}".format(len(ids_esperados)))
    print("  Encontrados en documento: {}".format(len(encontrados)))
    faltantes = [eid for eid in ids_esperados if eid not in ids_creados]
    if faltantes:
        print("  FALTANTES: {}".format(faltantes))

    if json_out:
        datos = {
            "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "documento": doc.Title,
            "total_instancias": len(instancias),
            "por_familia": {k: len(v) for k, v in sorted(por_familia.items())},
            "por_nivel": {k: len(v) for k, v in sorted(por_nivel.items())},
            "instancias": instancias,
            "verificacion_bloque_f02": {
                "esperados": len(ids_esperados),
                "encontrados": len(encontrados),
                "faltantes": faltantes,
            },
        }
        dirpath = os.path.dirname(json_out)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath)
        with open(json_out, "w") as f:
            json.dump(datos, f, indent=2)
        print("\nJSON guardado en: {}".format(json_out))

    print("=" * 70)
    return {
        "total": len(instancias),
        "por_familia": {k: len(v) for k, v in sorted(por_familia.items())},
        "por_nivel": {k: len(v) for k, v in sorted(por_nivel.items())},
        "instancias": instancias,
        "encontrados_f02": len(encontrados),
        "faltantes_f02": faltantes,
    }
