# -*- coding: utf-8 -*-
"""
Macro pyRevit: REVIT6_CREAR_TIPOS_CONDUIT
Crea/verifica tipos de Conduit (3/4", 1", 1-1/4", 2", 3") en el documento activo.
Si el documento es arquitectonico sin categoria MEP Conduit, crea un conducto de
prueba para registrar OST_Conduit y luego crea los tipos.
"""

__title__ = "6.3 Tipos de Conduit"
__author__ = "RevitElectrico / T5-SantaMarta"
__doc__ = "Crea 5 tipos de conducto de diferentes diametros"

from pyrevit import revit, DB, forms, script
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import os
import json
from datetime import datetime

TIPO_CONDUIT_MAP = [
    ("Conduit 3/4\"",   3,   4, "3/4\"",   19.05),
    ("Conduit 1\"",     5,   6, "1\"",     25.40),
    ("Conduit 1-1/4\"", 7,   8, "1-1/4\"", 31.75),
    ("Conduit 2\"",     9,  11, "2\"",     50.80),
    ("Conduit 3\"",    12,  15, "3\"",     76.20),
]
JSON_OUT = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\crear_tipos_conduit_resultado.json"


def _mm_a_pies(mm):
    try:
        return DB.UnitUtils.ConvertToInternalUnits(mm, DB.UnitTypeId.Millimeters)
    except Exception:
        return mm / 304.8


def _nombre_tipo_conduit(tipo_conduit):
    try:
        n = tipo_conduit.Name
        if n:
            return n
    except Exception:
        pass
    try:
        p = tipo_conduit.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None:
            v = p.AsString()
            if v:
                return v
    except Exception:
        pass
    return "?"


def _obtener_primer_nivel(doc):
    niveles = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()
    return niveles[0] if niveles else None


def _crear_conducto_de_prueba(doc):
    """Crea un conducto de prueba para registrar la categoria OST_Conduit."""
    try:
        Conduit = DB.Conduit
    except Exception:
        Conduit = None
    if Conduit is None:
        return False, "Clase Conduit no disponible en la API Revit"

    nivel = _obtener_primer_nivel(doc)
    if nivel is None:
        return False, "No se encontro nivel para colocar el conducto de prueba"

    try:
        symbol = None
        try:
            ConduitType = DB.ConduitType
            tipos = DB.FilteredElementCollector(doc).OfClass(ConduitType).ToElements()
            if tipos:
                symbol = tipos[0]
        except Exception:
            symbol = None

        if symbol is not None:
            punto = DB.XYZ(0, 0, nivel.Elevation)
            inst = doc.Create.NewFamilyInstance(nivel, punto, symbol, DB.Structure.StructuralType.NonStructural)
            if inst is not None:
                return True, "Conducto de prueba creado como FamilyInstance basado en nivel"
        else:
            try:
                curva = DB.Line.CreateBound(DB.XYZ(0, 0, 0), DB.XYZ(10, 0, 0))
                inst = Conduit.Create(doc, DB.ElementId.InvalidElementId, curva, nivel.Id)
                if inst is not None:
                    return True, "Conducto de prueba creado como Curve"
            except Exception:
                pass

        return False, "No se pudo crear el conducto de prueba (sin tipo base disponible)"
    except Exception as exc:
        return False, "Error creando conducto de prueba: {}".format(exc)


def run():
    doc = revit.doc
    output = script.get_output()
    output.print_md("# 6.3 Tipos de Conduit (5 diametros)")
    output.print_md("Fecha: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    output.print_md("Documento: {}".format(doc.Title))
    output.print_md("---")

    trans = DB.Transaction(doc, "CREAR TIPOS CONDUIT POR DIAMETRO")
    trans.Start()

    ConduitType = None
    try:
        ConduitType = DB.ConduitType
    except Exception:
        ConduitType = None

    conduit_type_disponible = ConduitType is not None
    if conduit_type_disponible:
        try:
            filtro = DB.ElementCategoryFilter(DB.BuiltInCategory.OST_ConduitType)
            tipo_existente = DB.FilteredElementCollector(doc).WherePasses(filtro).FirstElement()
            if tipo_existente is None:
                conduit_type_disponible = False
        except Exception:
            conduit_type_disponible = False

    if not conduit_type_disponible:
        output.print_md("AVISO: la categoria ConduitType no existe en este documento.")
        ok, msg = _crear_conducto_de_prueba(doc)
        if ok:
            output.print_md("  {} — categoria OST_Conduit registrada.".format(msg))
            conduit_type_disponible = True
        else:
            output.print_md("  No se pudo registrar la categoria: {}".format(msg))
            trans.Commit()
            output.print_md("## Resultado")
            output.print_md("- Creados: 0")
            output.print_md("- Existentes: 0")
            output.print_md("- Fallos: 0")
            output.print_md("**Estado: CATEGORIA CONDUIT NO DISPONIBLE**")
            return

    creados = 0
    existentes = 0
    fallos = 0
    detalle = []

    for nombre, mm_min, mm_max, pulgadas, diametro_mm in TIPO_CONDUIT_MAP:
        try:
            ya_existe = None
            for t in DB.FilteredElementCollector(doc).OfClass(ConduitType).ToElements():
                if _nombre_tipo_conduit(t) == nombre:
                    ya_existe = t
                    break

            if ya_existe is not None:
                existentes += 1
                detalle.append({"tipo": nombre, "motivo": "Ya existe"})
                output.print_md("  EXISTE {}".format(nombre))
                continue

            tipos = DB.FilteredElementCollector(doc).OfClass(ConduitType).ToElements()
            if len(tipos) > 0:
                plantilla = tipos[0]
                nuevo_id = plantilla.Duplicate(nombre)
                tipo_nuevo = doc.GetElement(nuevo_id)
            else:
                tipo_nuevo = ConduitType.Create(doc, nombre)

            if tipo_nuevo is None:
                fallos += 1
                detalle.append({"tipo": nombre, "motivo": "No se pudo crear el tipo"})
                output.print_md("  FALLO {}: no se pudo crear".format(nombre))
                continue

            try:
                param_diam = tipo_nuevo.get_Parameter(DB.BuiltInParameter.RBS_CONDUIT_DIAMETER_PARAM)
                if param_diam is not None and not param_diam.IsReadOnly:
                    diam_pies = _mm_a_pies(diametro_mm)
                    param_diam.Set(diam_pies)
                    output.print_md("  OK {} diametro={} mm".format(nombre, diametro_mm))
                else:
                    output.print_md("  AVISO {}: parametro diametro no editable".format(nombre))
            except Exception as exc:
                output.print_md("  AVISO {}: error seteando diametro: {}".format(nombre, exc))

            creados += 1
            detalle.append({"tipo": nombre, "diametro_conduit": pulgadas, "motivo": "OK — creado"})
            output.print_md("  CREADO {}".format(nombre))

        except Exception as exc:
            fallos += 1
            detalle.append({"tipo": nombre, "motivo": "Error: {}".format(exc)})
            output.print_md("  FALLO {}: {}".format(nombre, exc))

    trans.Commit()

    output.print_md("## Resultado")
    output.print_md("- **Creados: {}**".format(creados))
    output.print_md("- Existentes: {}".format(existentes))
    output.print_md("- Fallos: {}".format(fallos))
    output.print_md("Fecha ejecucion: {}".format(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    dirpath = os.path.dirname(JSON_OUT)
    if dirpath and not os.path.exists(dirpath):
        os.makedirs(dirpath)
    with open(JSON_OUT, "w") as f:
        f.write(json.dumps({
            "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "documento": doc.Title,
            "creados": creados,
            "existentes": existentes,
            "fallos": fallos,
            "detalle": detalle,
        }, indent=2, ensure_ascii=True))
    output.print_md("JSON guardado en: `{}`".format(JSON_OUT))

