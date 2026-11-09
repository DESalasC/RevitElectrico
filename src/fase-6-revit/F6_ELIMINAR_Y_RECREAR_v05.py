# -*- coding: utf-8 -*-
"""
F6_ELIMINAR_Y_RECREAR_v05.py
============================
Elimina todas las instancias eléctricas existentes y las recrea con
LevelId = Piso 5 y Z correcto.

Correcciones sobre v04:
- Importa Structure.StructuralType.NonStructural correctamente (no entero 0)
  para que LevelId se asigne al crear.
- Elimina instancias existentes antes de recrear.
- Usa BuiltInParameter.SYMBOL_NAME_PARAM para nombres de símbolo (evita
  excepcion "Name" de IronPython 2.7 en FamilySymbol.Name).


Ultimos tres cambios
--------------------
1. 2026-11-08 v05: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""
import json
import os
import unicodedata
import traceback

import clr

from Autodesk.Revit.DB import (
    BuiltInCategory,
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    Level,
    Transaction,
    XYZ,
)
from Autodesk.Revit.DB import ElementTransformUtils
from Autodesk.Revit.DB import Structure

clr.AddReference("System.Collections")
from System.Collections.Generic import List

METROS_A_PIES = 3.28084

CATEGORIAS_ELECTRICAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_ElectricalEquipment,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_LightingDevices,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_TelephoneDevices,
]


def _element_id_int(element_id):
    if element_id is None:
        return None
    for attr in ("Value", "IntegerValue"):
        try:
            return int(getattr(element_id, attr))
        except Exception:
            pass
    try:
        return int(element_id)
    except Exception:
        return None


def _safe_str(valor):
    """Convierte cualquier valor a string ASCII seguro."""
    if valor is None:
        return ""
    try:
        s = str(valor)
    except Exception:
        return "<?>"
    out = ""
    for c in s:
        try:
            c.encode("ascii")
            out += c
        except Exception:
            out += "_"
    return out


def _norm(texto):
    """Minusculas, sin acentos, sin espacios extra."""
    if texto is None:
        return ""
    t = _safe_str(texto)
    try:
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    return t.strip().lower()


def _obtener_root():
    env = os.environ.get("REVITELECTRICO_ROOT")
    if env:
        return env
    try:
        return os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
    except NameError:
        pass
    return os.path.abspath(".")


def _buscar_nivel(doc, nombre):
    for nivel in FilteredElementCollector(doc).OfClass(Level):
        try:
            if _norm(nivel.Name) == _norm(nombre):
                return nivel
        except Exception:
            pass
    return None


def _buscar_familia(doc, nombre):
    if not nombre:
        return None
    for fam in FilteredElementCollector(doc).OfClass(__import__(
            "Autodesk.Revit.DB", fromlist=["DB"]).Family).ToElements():
        try:
            if _norm(_safe_str(fam.Name)) == _norm(nombre):
                return fam
        except Exception:
            pass
    return None


def _obtener_nombre_simbolo(sym):
    """Obtiene el nombre de un FamilySymbol via parametro, evitando .Name."""
    try:
        p = sym.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None and p.AsString():
            return _safe_str(p.AsString())
    except Exception:
        pass
    try:
        p = sym.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None and p.AsString():
            return _safe_str(p.AsString())
    except Exception:
        pass
    return None


def _listar_simbolos(doc, familia):
    out = []
    for sid in familia.GetFamilySymbolIds():
        try:
            sym = doc.GetElement(sid)
            nombre = _obtener_nombre_simbolo(sym)
            if nombre:
                out.append((sid, nombre))
        except Exception:
            pass
    return out


def _buscar_simbolo_por_nombre(doc, familia, nombre_objetivo):
    """Busca un simbolo por nombre con matching tolerante."""
    if not nombre_objetivo or familia is None:
        return None, []

    objetivo = _norm(nombre_objetivo)
    simbolos = _listar_simbolos(doc, familia)

    # 1. Match exacto normalizado
    for sid, nombre in simbolos:
        if _norm(nombre) == objetivo:
            try:
                return doc.GetElement(sid), simbolos
            except Exception:
                pass

    # 2. Match contains (ambas direcciones)
    for sid, nombre in simbolos:
        n = _norm(nombre)
        if objetivo in n or n in objetivo:
            try:
                return doc.GetElement(sid), simbolos
            except Exception:
                pass

    # 3. Match startswith (ambas direcciones)
    for sid, nombre in simbolos:
        n = _norm(nombre)
        if n.startswith(objetivo) or objetivo.startswith(n):
            try:
                return doc.GetElement(sid), simbolos
            except Exception:
                pass

    return None, simbolos


def _primer_simbolo(doc, familia):
    """Devuelve el primer simbolo disponible de la familia."""
    for sid in familia.GetFamilySymbolIds():
        try:
            return doc.GetElement(sid)
        except Exception:
            pass
    return None


def eliminar_instancias_electricas(doc):
    """Elimina todas las instancias eléctricas existentes."""
    existentes = []
    for bic in CATEGORIAS_ELECTRICAS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                existentes.append(inst)
        except Exception:
            pass

    if not existentes:
        return 0, []

    t = Transaction(doc, "F6 - Eliminar eléctrico existente")
    t.Start()
    eliminadas = 0
    ids_eliminados = []
    for inst in existentes:
        try:
            ids_eliminados.append(_element_id_int(inst.Id))
            doc.Delete(inst.Id)
            eliminadas += 1
        except Exception:
            pass
    t.Commit()
    return eliminadas, ids_eliminados


def recrear_instancias(doc, confirmar=False,
                        json_in="data/apto_F_02_aplicar_mapa_v3_corregido.json",
                        nivel_destino="Piso 5"):
    root = _obtener_root()
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)

    resultado = {
        "documento": _safe_str(doc.Title),
        "modo": "aplicar" if confirmar else "simulacion",
        "nivel_destino": nivel_destino,
        "nivel_id": None,
        "elevacion_nivel_m": None,
        "instancias_eliminadas": 0,
        "instancias_existentes": 0,
        "instancias_creadas": 0,
        "usando_fallback": [],
        "fallos": [],
    }

    nivel = _buscar_nivel(doc, nivel_destino)
    if nivel is None:
        resultado["fallos"].append("Nivel no encontrado: " + nivel_destino)
        print(json.dumps(resultado, indent=2, ensure_ascii=True))
        return resultado

    resultado["nivel_id"] = _element_id_int(nivel.Id)
    elevacion_ft = nivel.Elevation
    elevacion_m = round(elevacion_ft / METROS_A_PIES, 4)
    resultado["elevacion_nivel_m"] = elevacion_m

    # Cargar acciones del JSON
    try:
        f = open(json_in, "r")
        try:
            reporte = json.load(f)
        finally:
            f.close()
    except Exception as ex:
        resultado["fallos"].append("No se pudo leer {}: {}".format(json_in, ex))
        print(json.dumps(resultado, indent=2, ensure_ascii=True))
        return resultado

    acciones = reporte.get("acciones_modelar", [])

    # Contar instancias existentes antes de eliminar
    existentes = []
    for bic in CATEGORIAS_ELECTRICAS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                existentes.append(inst)
        except Exception:
            pass
    resultado["instancias_existentes"] = len(existentes)

    if not confirmar:
        print("SIMULACION: eliminaria {0} instancias y crearia {1} nuevas".format(
            len(existentes), len(acciones)))
        print(json.dumps(resultado, indent=2, ensure_ascii=True))
        return resultado

    # Eliminar instancias existentes
    eliminadas, ids_eliminados = eliminar_instancias_electricas(doc)
    resultado["instancias_eliminadas"] = eliminadas
    print("Eliminadas: {} instancias".format(eliminadas))

    # Recrear instancias desde el JSON
    t = Transaction(doc, "F6 - Crear eléctrico corregido")
    t.Start()
    creados = 0
    fallos_lista = []

    for accion in acciones:
        try:
            fam_name = (accion.get("familia_real")
                        or accion.get("familia")
                        or accion.get("familia_original"))
            sym_name = accion.get("simbolo_real") or accion.get("simbolo")
            anfitrion = accion.get("anfitrion")
            x = float(accion.get("x_revit", 0))
            y = float(accion.get("y_revit", 0))
            z_local_m = float(accion.get("z_revit", 0))
            z_abs_ft = elevacion_ft + z_local_m * METROS_A_PIES
            rot = float(accion.get("rotacion", 0))

            familia = _buscar_familia(doc, fam_name)
            if familia is None:
                fam_name2 = accion.get("familia_original")
                if fam_name2 and fam_name2 != fam_name:
                    familia = _buscar_familia(doc, fam_name2)
                if familia is None:
                    fallos_lista.append({
                        "nombre_bloque": accion.get("nombre_bloque"),
                        "motivo": "Familia no encontrada: " + str(fam_name),
                    })
                    print("  FALLO: familia no encontrada: {}".format(fam_name))
                    continue

            simbolo, simbolos_disponibles = _buscar_simbolo_por_nombre(
                doc, familia, sym_name)
            usando_fallback = False

            if simbolo is None:
                simbolo = _primer_simbolo(doc, familia)
                if simbolo is not None:
                    usando_fallback = True
                    nombre_usado = _obtener_nombre_simbolo(simbolo) or "?"
                    print("  AVISO: simbolo '{}' no encontrado en '{}'. Fallback: '{}'".format(
                        sym_name, _safe_str(familia.Name), nombre_usado))
                else:
                    fallos_lista.append({
                        "nombre_bloque": accion.get("nombre_bloque"),
                        "motivo": "Simbolo no encontrado: {} / {}".format(
                            fam_name, sym_name),
                    })
                    print("  FALLO: simbolo no encontrado: {} / {}".format(fam_name, sym_name))
                    continue

            if usando_fallback:
                resultado["usando_fallback"].append({
                    "nombre_bloque": accion.get("nombre_bloque"),
                    "simbolo_solicitado": sym_name,
                    "simbolo_usado": _obtener_nombre_simbolo(simbolo) or "?",
                })

            if not simbolo.IsActive:
                try:
                    simbolo.Activate()
                    doc.Regenerate()
                except Exception:
                    pass

            location = XYZ(x, y, z_abs_ft)
            # StructuralType.NonStructural como enum correcto (no entero 0)
            inst = doc.Create.NewFamilyInstance(
                location, simbolo, nivel, Structure.StructuralType.NonStructural
            )

            if rot != 0:
                try:
                    param = inst.get_Parameter(BuiltInParameter.ROTATION)
                    if param is not None and not param.IsReadOnly:
                        import math
                        rad = rot * 3.141592653589793 / 180.0
                        param.Set(rad)
                except Exception:
                    pass

            # Para instancias de techo, corregir Z si es necesario
            if anfitrion == "ceiling":
                bb = inst.get_BoundingBox(None)
                if bb is not None:
                    z_actual = bb.Min.Z
                    delta_z = z_abs_ft - z_actual
                    if abs(delta_z) > 0.01:
                        ElementTransformUtils.MoveElement(doc, inst.Id, XYZ(0, 0, delta_z))

            creados += 1
            nombre_sym = _obtener_nombre_simbolo(simbolo) or "?"
            print("  OK: {} id={} z_rel={:.2f}m simbolo={}".format(
                accion.get("nombre_bloque"), inst.Id, z_local_m, nombre_sym))
        except Exception as ex:
            fallos_lista.append({
                "nombre_bloque": accion.get("nombre_bloque"),
                "motivo": "Excepcion: {}".format(_safe_str(str(ex))),
            })
            print("  ERROR creando {}: {}".format(
                accion.get("nombre_bloque"), _safe_str(str(ex))))
            traceback.print_exc()

    t.Commit()
    resultado["instancias_creadas"] = creados
    resultado["fallos"] = fallos_lista
    print("Resultado: eliminados={}, creados={}, fallos={}, fallback={}".format(
        eliminadas, creados, len(fallos_lista), len(resultado["usando_fallback"])))
    print(json.dumps(resultado, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    try:
        _confirmar = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _confirmar = False
    recrear_instancias(__revit__.ActiveUIDocument.Document, confirmar=_confirmar)  # noqa: F821
