# -*- coding: utf-8 -*-
"""
Macro pyRevit: REVIT6_ASIGNAR_RED
Asigna RED=SI al parametro Comments de 5 dispositivos electricos.
"""

__title__ = "6.2 Asignar RED=SI"
__author__ = "RevitElectrico / T5-SantaMarta"
__doc__ = "Marca RED=SI en el parametro Comments de 5 FamilyInstance"

from pyrevit import revit, DB, forms, script
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import os
import json
from datetime import datetime

IDS_RED = ["5554265", "5554262", "5554263", "5554264", "5554269"]
VALOR_RED = "SI"
MARCA_COMENTARIO = "RED={}".format(VALOR_RED)
JSON_OUT = r"D:\Work\PROJECTS\Actuales\T5-SantaMarta\data\asignar_red_resultado.json"


def _buscar_param_comments(inst):
    try:
        return inst.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    except Exception:
        pass
    for p in inst.Parameters:
        try:
            if p.Definition and p.Definition.Name.strip().lower() == "comments":
                return p
        except Exception:
            continue
    return None


def run():
    doc = revit.doc
    output = script.get_output()
    output.print_md("# 6.2 Asignar RED=SI (dispositivos electricos)")
    output.print_md("Fecha: {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    output.print_md("Documento: {}".format(doc.Title))
    output.print_md("---")

    trans = DB.Transaction(doc, "ASIGNAR_RED — dispositivos electricos")
    trans.Start()

    exitos = 0
    fallos = 0
    detalle = []

    for id_str in IDS_RED:
        try:
            elem_id = DB.ElementId(int(id_str))
            inst = doc.GetElement(elem_id)
            if inst is None:
                fallos += 1
                detalle.append({"id": id_str, "motivo": "Elemento no encontrado"})
                output.print_md("  FALLO id={}: no encontrado".format(id_str))
                continue

            if not isinstance(inst, DB.FamilyInstance):
                fallos += 1
                detalle.append({"id": id_str, "motivo": "No es FamilyInstance"})
                output.print_md("  FALLO id={}: no es FamilyInstance".format(id_str))
                continue

            p_comments = _buscar_param_comments(inst)
            if p_comments is None:
                fallos += 1
                detalle.append({"id": id_str, "motivo": "Parametro Comments no encontrado"})
                output.print_md("  FALLO id={}: parametro Comments no encontrado".format(id_str))
                continue

            if not p_comments.IsReadOnly:
                try:
                    actual = p_comments.AsString() or ""
                    if actual and "RED=" not in actual:
                        nuevo = actual + " | " + MARCA_COMENTARIO
                    else:
                        nuevo = MARCA_COMENTARIO
                    p_comments.Set(nuevo)
                    exitos += 1
                    detalle.append({"id": id_str, "motivo": "OK — Comments='{}'".format(nuevo)})
                    output.print_md("  OK id={} Comments='{}'".format(id_str, nuevo))
                except Exception as exc:
                    fallos += 1
                    detalle.append({"id": id_str, "motivo": "Error seteando Comments: {}".format(exc)})
                    output.print_md("  FALLO id={}: {}".format(id_str, exc))
            else:
                fallos += 1
                detalle.append({"id": id_str, "motivo": "Parametro Comments es de solo lectura"})
                output.print_md("  FALLO id={}: Comments es de solo lectura".format(id_str))

        except Exception as exc:
            fallos += 1
            detalle.append({"id": id_str, "motivo": "Error: {}".format(exc)})
            output.print_md("  FALLO id={}: {}".format(id_str, exc))

    trans.Commit()

    output.print_md("## Resultado")
    output.print_md("- **Exitos: {}**".format(exitos))
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
            "campo": "Comments (ALL_MODEL_INSTANCE_COMMENTS)",
            "valor": MARCA_COMENTARIO,
            "exitos": exitos,
            "fallos": fallos,
            "detalle": detalle,
        }, indent=2, ensure_ascii=True))
    output.print_md("JSON guardado en: `{}`".format(JSON_OUT))

