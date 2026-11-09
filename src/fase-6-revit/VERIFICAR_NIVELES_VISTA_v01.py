
Ultimos tres cambios
--------------------
1. 2026-11-08 v01: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.


# -*- coding: utf-8 -*-
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")
from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FamilyInstance,
    Level,
    ViewPlan,
    BuiltInParameter,
    ElementId,
)
from System import Int64
import json
import os


def _nombre_nivel(elemento):
    try:
        n = elemento.Name
        if n:
            return n
    except Exception:
        pass
    try:
        p = elemento.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            v = p.AsString()
            if v:
                return v
    except Exception:
        pass
    return "?"


def _elevacion_nivel(nivel):
    try:
        p = nivel.get_Parameter(BuiltInParameter.LEVEL_ELEV)
        if p is not None:
            return p.AsDouble()
    except Exception:
        pass
    return None


def _nombre_dispositivo(inst):
    try:
        p = inst.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p is not None:
            v = p.AsString()
            if v:
                return v
    except Exception:
        pass
    return "?"


def verificar_niveles_vista(doc, json_out=None):
    print("VERIFICACION NIVELES Y VISTAS - PISO 5")
    print("=" * 60)

    # 1. Listar todos los niveles
    niveles = FilteredElementCollector(doc).OfClass(Level).ToElements()
    print("\nNIVELES EN EL DOCUMENTO:")
    nivel_piso5 = None
    for niv in niveles:
        nombre = _nombre_nivel(niv)
        elev = _elevacion_nivel(niv)
        print("  {} - elev: {:.2f} pies (ID: {})".format(nombre, elev if elev is not None else 0, niv.Id.ToString()))
        if nombre and "Piso 5" in nombre:
            nivel_piso5 = niv

    # 2. Verificar en qué nivel están los dispositivos clave
    ids_dispositivos = [
        "5554235", "5554236", "5554237", "5554238", "5554239", "5554240", "5554241",
        "5554242", "5554243", "5554244", "5554245", "5554246", "5554247", "5554248",
        "5554249", "5554250", "5554251", "5554252", "5554253", "5554254", "5554255",
        "5554256", "5554257", "5554258", "5554259", "5554260", "5554261",
        "5554262", "5554263", "5554264", "5554265", "5554266", "5554267", "5554268",
        "5554269", "5554270", "5554271",
        "5554303", "5554304", "5554305", "5554306", "5554307", "5554308", "5554309", "5554310",
    ]

    print("\nDISPOSITIVOS Y SUS NIVELES:")
    for id_str in ids_dispositivos:
        try:
            eid = ElementId(Int64(int(id_str)))
            inst = doc.GetElement(eid)
            if inst is None:
                print("  ID {}: NO ENCONTRADO".format(id_str))
                continue
            if not isinstance(inst, FamilyInstance):
                print("  ID {}: no es FamilyInstance".format(id_str))
                continue
            nivel_id = inst.LevelId
            nivel = doc.GetElement(nivel_id)
            nombre_nivel = _nombre_nivel(nivel) if nivel else "?"
            nombre_disp = _nombre_dispositivo(inst)
            print("  ID {} - {} - Nivel: {}".format(id_str, nombre_disp, nombre_nivel))
        except Exception as exc:
            print("  ID {}: ERROR {}".format(id_str, exc))

    # 3. Verificar vistas de planta "Piso 5"
    print("\nVISTAS DE PLANTA:")
    vistas = FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
    vista_piso5 = None
    for v in vistas:
        nombre = _nombre_nivel(v)
        print("  Vista: {} (ID: {})".format(nombre, v.Id.ToString()))
        if nombre and "Piso 5" in nombre:
            vista_piso5 = v

    if vista_piso5 is not None:
        print("\nVISTA 'Piso 5' ENCONTRADA - ID: {}".format(vista_piso5.Id.ToString()))
        try:
            # Verificar rango de corte (view range)
            try:
                from Autodesk.Revit.DB import ViewRange
                vr = vista_piso5.GetViewRange()
                print("  ViewRange: nivel de corte principal: {}".format(vr.GetLevelId(0).ToString() if vr else "N/D"))
            except Exception:
                pass
        except Exception as exc:
            print("  Error leyendo ViewRange: {}".format(exc))
    else:
        print("\nNO SE ENCONTRO vista de planta 'Piso 5'")

    print("=" * 60)

    if json_out:
        dirpath = os.path.dirname(json_out)
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath)
        with open(json_out, "w") as f:
            f.write(json.dumps({
                "fecha_ejecucion": __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "documento": doc.Title,
                "nivel_piso5_id": nivel_piso5.Id.ToString() if nivel_piso5 else None,
                "vista_piso5_id": vista_piso5.Id.ToString() if vista_piso5 else None,
            }, indent=2, ensure_ascii=True))
        print("JSON guardado en: {}".format(json_out))

    return {
        "nivel_piso5": nivel_piso5,
        "vista_piso5": vista_piso5,
    }
