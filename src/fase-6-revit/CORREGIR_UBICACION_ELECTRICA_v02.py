# -*- coding: utf-8 -*-
"""
CORREGIR_UBICACION_ELECTRICA_v02.py
===================================
Corrige la ubicacion de los dispositivos electricos del bloque piloto.
Version corregida de F6_CORREGIR_UBICACION_ELECTRICA_v01.py.

Problemas corregidos respecto a v01:
  - Se elimina el chequeo isinstance(inst, FamilyInstance) que fallaba
    con los wrappers de pyrevit.api (retornaba 0 instancias detectadas).
  - doc.Delete(eid) ahora registra siempre el ID intentado, independientemente
    del valor de retorno (en IronPython puede retornar 0 o None).
  - El JSON de entrada por defecto es apto_F_02_aplicar_mapa_v3_corregido.json
    (usa los nombres de familia sustitutos que SÍ están cargados en el RVT).

Problema que resuelve
---------------------
El reporte apto_F_02_aplicar_mapa_v3.json trae z_revit como altura LOCAL
(0.3 / 1.1 / 1.2 / 2.6 m). El script de modelado lo uso como Z ABSOLUTA, de modo
que los dispositivos quedaron a nivel de calle (Z ~0-2.6 m) mientras el "Piso 5"
del modelo arquitectonico esta a 43.3727 m. Ademas quedaron sin nivel
(LevelId = -1), por lo que no aparecen en ninguna vista de planta.

Que hace
--------
1. Lee la elevacion real del nivel destino desde el documento (no la hardcodea).
2. Detecta las instancias electricas fuera de nivel (LevelId invalido o Z muy
   por debajo del nivel).
3. En modo confirmar=False (por defecto) solo informa: no toca el modelo.
4. En modo confirmar=True: borra esas instancias y las recrea con
   Z = elevacion_nivel + altura_local, reutilizando el camino de creacion ya
   probado de RE_APLICAR_MAPA_V3_REVIT_v02.

Ejecucion dentro de Revit (pyRevit Python Shell):
    exec(open(r"D:\Work\PROJECTS\RevitElectrico\src\fase-6-revit\CORREGIR_UBICACION_ELECTRICA_v02.py").read())
    corregir_ubicacion(doc, confirmar=False)   # simulacion: solo informa
    corregir_ubicacion(doc, confirmar=True)    # aplicar: borra y recrea


Ultimos tres cambios
--------------------
1. 2026-11-08 v02: version vigente conservada tras la limpieza de duplicados;
   las versiones anteriores se archivan y se eliminan.
2. 2026-11-08: migracion del proyecto a D:\Work\PROJECTS\RevitElectrico.
3. Heredado: sin registro previo disponible.
"""
import json
import os
import sys
import traceback
import clr

# Asegurar que el directorio del script este en sys.path para importar
# modulos hermanos como RE_APLICAR_MAPA_V3_REVIT_v02 desde la shell de Revit.
try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    if _script_dir not in sys.path:
        sys.path.insert(0, _script_dir)
except NameError:
    pass
except Exception:
    pass

from Autodesk.Revit.DB import (
    BuiltInCategory,
    ElementId,
    FilteredElementCollector,
    Transaction,
)

clr.AddReference("System.Collections")
from System.Collections.Generic import List

CATEGORIAS_ELECTRICAS = [
    BuiltInCategory.OST_ElectricalFixtures,
    BuiltInCategory.OST_ElectricalEquipment,
    BuiltInCategory.OST_LightingFixtures,
    BuiltInCategory.OST_LightingDevices,
    BuiltInCategory.OST_DataDevices,
    BuiltInCategory.OST_CommunicationDevices,
    BuiltInCategory.OST_TelephoneDevices,
]

NIVEL_DESTINO = "Piso 5"
TOLERANCIA_FUERA_NIVEL_M = 0.5
METROS_A_PIES = 3.28084


# --------------------------------------------------------------------------
def _element_id_int(element_id):
    if element_id is None:
        return None
    if isinstance(element_id, (str, unicode)):  # noqa: F821
        try:
            return int(element_id)
        except Exception:
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


def _txt(valor):
    texto = None
    if isinstance(valor, unicode):  # noqa: F821
        texto = valor
    if texto is None:
        try:
            texto = unicode(valor, "utf-8")  # noqa: F821
        except Exception:
            texto = None
    if texto is None:
        try:
            texto = unicode(valor, "latin-1")  # noqa: F821
        except Exception:
            texto = None
    if texto is None:
        return "<?>"
    try:
        return texto.encode("ascii", "backslashreplace").decode("ascii")
    except Exception:
        return "<?>"


def _sanitize(valor):
    if valor is None or isinstance(valor, (int, long, float, bool)):  # noqa: F821
        return valor
    if isinstance(valor, dict):
        return dict([(_txt(k), _sanitize(v)) for k, v in valor.items()])
    if isinstance(valor, (list, tuple)):
        return [_sanitize(v) for v in valor]
    return _txt(valor)


def _obtener_root():
    env = os.environ.get("REVITELECTRICO_ROOT")
    if env:
        return env
    try:
        return os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
    except NameError:
        pass
    except Exception:
        pass
    try:
        return inputs.get("root")  # inyectado por pyrevit agent run
    except NameError:
        pass
    return os.path.abspath(".")


def _buscar_nivel(doc, nombre):
    from Autodesk.Revit.DB import Level
    for nivel in FilteredElementCollector(doc).OfClass(Level):
        if _txt(nivel.Name).strip().lower() == nombre.strip().lower():
            return nivel
    return None


def _z_elemento(inst):
    try:
        bb = inst.get_BoundingBox(None)
        if bb is not None:
            return bb.Min.Z
    except Exception:
        pass
    return None


def _instancias_electricas(doc):
    """Recopila instancias electricas sin chequeo isinstance (fallaba con
    wrappers de pyrevit.api). WhereElementIsNotElementType ya filtra tipos."""
    salida = []
    for bic in CATEGORIAS_ELECTRICAS:
        try:
            for inst in FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                salida.append(inst)
        except Exception:
            pass
    return salida


def _fuera_de_nivel(inst, elevacion_nivel):
    nivel_id = _element_id_int(inst.LevelId)
    z = _z_elemento(inst)
    motivos = []
    if nivel_id is None or nivel_id < 0:
        motivos.append("sin_nivel")
    if z is not None and z < (elevacion_nivel - TOLERANCIA_FUERA_NIVEL_M):
        motivos.append("z_bajo_nivel")
    return motivos, z, nivel_id


# --------------------------------------------------------------------------
def corregir_ubicacion(doc, confirmar=False, nivel_destino=NIVEL_DESTINO,
                       json_in="data/apto_F_02_aplicar_mapa_v3_corregido.json",
                       json_out="data/corregir_ubicacion_electrica_v02.json",
                       borrar_previas=True, borrar_todas=True):
    root = _obtener_root()
    if not os.path.isabs(json_in):
        json_in = os.path.join(root, json_in)
    if not os.path.isabs(json_out):
        json_out = os.path.join(root, json_out)

    resultado = {
        "documento": _txt(doc.Title),
        "modo": "aplicar" if confirmar else "simulacion",
        "nivel_destino": nivel_destino,
        "elevacion_nivel_m": None,
        "fuera_de_nivel": [],
        "borradas": [],
        "creadas": [],
        "fallos": [],
        "resumen": {},
    }

    nivel = _buscar_nivel(doc, nivel_destino)
    if nivel is None:
        resultado["fallos"].append("Nivel no encontrado: " + nivel_destino)
        _guardar(json_out, resultado)
        print(json.dumps(_sanitize(resultado), indent=2, ensure_ascii=True))
        return resultado

    elevacion = round(nivel.Elevation, 4)
    resultado["elevacion_nivel_m"] = elevacion

    # 1. Diagnostico de instancias fuera de nivel
    instancias = _instancias_electricas(doc)
    for inst in instancias:
        motivos, z, nivel_id = _fuera_de_nivel(inst, elevacion)
        if motivos:
            resultado["fuera_de_nivel"].append({
                "id": _element_id_int(inst.Id),
                "familia": _txt(_safe(inst, "Symbol", "Family", "Name")),
                "z_min": round(z, 4) if z is not None else None,
                "nivel_id": nivel_id,
                "motivos": motivos,
            })
    resultado["resumen"]["instancias_electricas_total"] = len(instancias)
    resultado["resumen"]["a_borrar"] = len(instancias) if borrar_todas else len(resultado["fuera_de_nivel"])

    # 2. Preparar acciones con Z absoluta correcta
    try:
        f = open(json_in, "r")
        try:
            reporte = json.load(f)
        finally:
            f.close()
    except Exception:
        resultado["fallos"].append("No se pudo leer {}: {}".format(json_in, traceback.format_exc()))
        _guardar(json_out, resultado)
        print(json.dumps(_sanitize(resultado), indent=2, ensure_ascii=True))
        return resultado

    acciones = []
    for accion in reporte.get("acciones_modelar", []):
        altura_local = accion.get("z_revit")
        if altura_local is None:
            continue
        copia = dict(accion)
        copia["z_revit"] = round((elevacion + float(altura_local)) * METROS_A_PIES, 4)
        copia["nivel_revit"] = nivel_destino
        copia["z_local_original"] = altura_local
        acciones.append(copia)

    resultado["resumen"]["acciones_preparadas"] = len(acciones)
    resultado["resumen"]["instancias_fuera_nivel"] = len(resultado["fuera_de_nivel"])

    if not confirmar:
        resultado["resumen"]["nota"] = (
            "SIMULACION: no se modifico el modelo. Reejecutar con confirmar=True "
            "para borrar y recrear las instancias.")
        _guardar(json_out, resultado)
        print(json.dumps(_sanitize(resultado), indent=2, ensure_ascii=True))
        return resultado

    # 3. Borrar instancias previas (todas o solo las fuera de nivel)
    ids_borrar = []
    if borrar_todas:
        ids_borrar = [_element_id_int(i.Id) for i in instancias]
    else:
        ids_borrar = [item["id"] for item in resultado["fuera_de_nivel"]]

    if borrar_previas and ids_borrar:
        trans = Transaction(doc, "F6 - Borrar electrico previo")
        trans.Start()
        try:
            borrados = []
            for valor in ids_borrar:
                try:
                    eid = ElementId(int(valor))
                    doc.Delete(eid)
                    # Siempre registrar el ID intentado; doc.Delete puede
                    # retornar 0 o None en IronPython y no es confiable.
                    borrados.append(valor)
                except Exception:
                    pass
            resultado["borradas"] = borrados
            trans.Commit()
        except Exception:
            trans.RollBack()
            resultado["fallos"].append("Error borrando: " + traceback.format_exc())
            _guardar(json_out, resultado)
            print(json.dumps(_sanitize(resultado), indent=2, ensure_ascii=True))
            return resultado

    # 4. Recrear reutilizando el camino probado
    try:
        _mod_path = os.path.join(root, "src", "fase-6-revit", "RE_APLICAR_MAPA_V3_REVIT_v02.py")
        _ns = {}
        exec(compile(open(_mod_path).read(), _mod_path, "exec"), _ns)
        _aplicar = _ns["aplicar_mapa_revit"]
        res = _aplicar(
            doc, json_in=None, json_out=json_out.replace(".json", "_creacion.json"),
            acciones=acciones)
        resultado["resumen"]["creados"] = res.get("estadisticas", {}).get("exitos")
        resultado["resumen"]["fallos_creacion"] = res.get("estadisticas", {}).get("fallos")
        resultado["creadas"] = [
            {"id": _element_id_int(e.get("id")), "nombre": e.get("nombre_bloque")}
            for e in res.get("exitos", [])
        ]
    except Exception:
        resultado["fallos"].append("Error creando: " + traceback.format_exc())

    _guardar(json_out, resultado)
    print(json.dumps(_sanitize(resultado), indent=2, ensure_ascii=True))
    return resultado


def _safe(obj, *ruta):
    actual = obj
    for nombre in ruta:
        try:
            actual = getattr(actual, nombre)
        except Exception:
            return None
        if actual is None:
            return None
    return actual


def _guardar(ruta, datos):
    try:
        carpeta = os.path.dirname(ruta)
        if carpeta and not os.path.exists(carpeta):
            os.makedirs(carpeta)
        f = open(ruta, "w")
        try:
            f.write(json.dumps(_sanitize(datos), indent=2, ensure_ascii=True))
        finally:
            f.close()
        print("JSON guardado en: " + ruta)
    except Exception:
        print("ERROR guardando JSON: " + traceback.format_exc())


if __name__ == "__main__":
    _confirmar = False
    _borrar_todas = True
    _borrar_previas = True
    try:
        _confirmar = bool(inputs.get("confirmar", False))  # noqa: F821
    except NameError:
        _confirmar = False
    try:
        _borrar_todas = bool(inputs.get("borrar_todas", True))  # noqa: F821
    except NameError:
        _borrar_todas = True
    try:
        _borrar_previas = bool(inputs.get("borrar_previas", True))  # noqa: F821
    except NameError:
        _borrar_previas = True
    corregir_ubicacion(
        __revit__.ActiveUIDocument.Document,  # noqa: F821
        confirmar=_confirmar,
        borrar_previas=_borrar_previas,
        borrar_todas=_borrar_todas,
    )
