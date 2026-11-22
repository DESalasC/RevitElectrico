# -*- coding: utf-8 -*-
"""
RE7_DIAG_UNIONES_V02F.py — Diagnóstico de uniones/cajas de empate en CENTRA_V02-f.

Inspecciona el modelo de referencia CENTRA_V02-f.rvt para aprender el patrón
real de cómo están modeladas las uniones/cajas de empate (conduit fittings):
  - Familias y tipos usados
  - Posiciones (XYZ)
  - Conectores y cómo se vinculan a los conductos
  - Conteo por tipo

USO (desde pyRevit Python Shell dentro de Revit 2026, con cualquier doc abierto):
  exec(open(r"D:/Work/PROJECTS/RevitElectrico/src/fase-7-ruteo/RE7_DIAG_UNIONES_V02F.py").read())
  diagnosticar_v02f(ruta_v02f=r"D:/Work/PROJECTS/RevitElectrico/ArchivosBase/E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02-f.rvt")
"""

import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")
clr.AddReference("System")

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    FamilySymbol,
    FamilyInstance,
    BuiltInCategory,
    XYZ,
    ElementId,
    Transaction,
)
from Autodesk.Revit.DB.Electrical import Conduit
from System import Int64

import json
import os
from datetime import datetime


FT_A_MM = 304.8


def _mm(valor_pies):
    return round(valor_pies * FT_A_MM, 2)


def _xyz_mm(xyz):
    if xyz is None:
        return None
    return [_mm(xyz.X), _mm(xyz.Y), _mm(xyz.Z)]


def _nombre_tipo(fs):
    try:
        return fs.Name
    except Exception:
        return "?"


def _nombre_familia(fs):
    try:
        return fs.Family.Name
    except Exception:
        return "?"


def _obtener_conectores(elemento):
    """Devuelve lista de descripciones de conectores de un elemento MEP."""
    conectores = []
    try:
        mep = elemento.MEPModel
        if mep is None:
            return conectores
        cs = mep.ConnectorSet
        for cn in cs:
            conectores.append({
                "origen_mm": _xyz_mm(cn.Origin),
                "sistema": str(cn.SystemType) if cn.SystemType else "?",
                "conectado": bool(cn.IsConnected),
                "tipo_conector": str(cn.ConnectorType) if cn.ConnectorType else "?",
            })
    except Exception:
        pass
    return conectores


def diagnosticar_v02f(ruta_v02f=None, app=None, doc_activo=None):
    """
    Args:
        ruta_v02f: Ruta absoluta al archivo CENTRA_V02-f.rvt. Si es None,
                   se usa el path por defecto del proyecto.
        app: Application de Revit (para abrir el doc externo). Si es None,
             se intenta obtener de __revit__.
        doc_activo: Document activo (solo para reporte comparativo opcional).
    """
    # Resolver ruta por defecto
    if ruta_v02f is None:
        ruta_v02f = r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\E-STM-FJR-TORRE5-A-M3-R23-P01-CENTRA_V02-f.rvt"

    if not os.path.exists(ruta_v02f):
        print("ERROR: no existe el archivo V02-f: {}".format(ruta_v02f))
        return None

    # Obtener aplicación de Revit
    if app is None:
        try:
            app = __revit__.Application
        except NameError:
            print("ERROR: no se puede obtener la aplicación de Revit. Ejecuta dentro de pyRevit.")
            return None

    print("=" * 70)
    print("RE7_DIAG_UNIONES_V02F - Diagnóstico de uniones en CENTRA_V02-f")
    print("ejecutado_utc={}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("=" * 70)
    print("Archivo: {}".format(ruta_v02f))
    print("")

    # Abrir el documento V02-f
    try:
        doc_v02f = app.OpenDocumentFile(ruta_v02f)
    except Exception as ex:
        print("ERROR: no se pudo abrir V02-f: {}".format(str(ex)))
        return None

    try:
        # 1. Familias de conduit fitting cargadas en V02-f
        print("-" * 70)
        print("1. FAMILIAS DE CONDUIT FITTING CARGADAS EN V02-f")
        print("-" * 70)
        # Buscar por categoria OST_ConduitFitting en lugar de por nombre
        # (los nombres de familia pueden no contener exactamente "conduit")
        collector_cat = FilteredElementCollector(doc_v02f).OfCategory(
            BuiltInCategory.OST_ConduitFitting
        )
        simbolos_fitting = list(collector_cat.OfClass(FamilySymbol).ToElements())
        familias_fitting = {}
        for fs in simbolos_fitting:
            try:
                nom_fam = fs.Family.Name
                nom_tipo = fs.Name
            except Exception:
                continue
            clave = nom_fam
            if clave not in familias_fitting:
                familias_fitting[clave] = set()
            familias_fitting[clave].add(nom_tipo)

        if familias_fitting:
            for fam in sorted(familias_fitting.keys()):
                tipos = sorted(familias_fitting[fam])
                print("  Familia: {}".format(fam))
                for t in tipos:
                    print("      Tipo: {}".format(t))
        else:
            print("  No se encontraron familias en categoria OST_ConduitFitting.")
            # Fallback: buscar por nombre
            collector = FilteredElementCollector(doc_v02f).OfClass(FamilySymbol)
            for fs in collector:
                try:
                    nom_fam = fs.Family.Name
                except Exception:
                    continue
                if "conduit" in nom_fam.lower():
                    print("  (fallback por nombre) Familia: {}".format(nom_fam))

        # 2. Instancias de conduit fitting colocadas en V02-f
        print("")
        print("-" * 70)
        print("2. INSTANCIAS DE CONDUIT FITTING COLOCADAS EN V02-f")
        print("-" * 70)
        collector_inst = FilteredElementCollector(doc_v02f).OfCategory(
            BuiltInCategory.OST_ConduitFitting
        )
        instancias = list(collector_inst.ToElements())
        print("  Total de conduit fittings colocados: {}".format(len(instancias)))

        # Contar por tipo
        por_tipo = {}
        detalles = []
        for inst in instancias:
            try:
                sid = int(inst.Symbol.Id)
                nom_fam = inst.Symbol.Family.Name
                nom_tipo = inst.Symbol.Name
                clave = "{} | {}".format(nom_fam, nom_tipo)
                por_tipo[clave] = por_tipo.get(clave, 0) + 1
                punto = _xyz_mm(inst.Location.Point) if inst.Location and inst.Location.Point else None
                conectores = _obtener_conectores(inst)
                detalles.append({
                    "id": sid,
                    "familia": nom_fam,
                    "tipo": nom_tipo,
                    "punto_mm": punto,
                    "num_conectores": len(conectores),
                    "conectores": conectores,
                })
            except Exception as ex:
                detalles.append({"error": str(ex)})

        print("")
        print("  Por familia | tipo:")
        for clave in sorted(por_tipo.keys()):
            print("    {:<50} {:>5}".format(clave, por_tipo[clave]))

        # 3. Conductos en V02-f (para referencia de conexión)
        print("")
        print("-" * 70)
        print("3. CONDUCTOS EN V02-f (referencia)")
        print("-" * 70)
        collector_cond = FilteredElementCollector(doc_v02f).OfClass(Conduit)
        conduits = list(collector_cond.ToElements())
        print("  Total de conduits: {}".format(len(conduits)))

        # 4. Muestra los primeros 10 fittings con detalle
        print("")
        print("-" * 70)
        print("4. MUESTRA: Primeros 10 conduit fittings con detalle")
        print("-" * 70)
        for d in detalles[:10]:
            if "error" in d:
                print("  ERROR: {}".format(d["error"]))
                continue
            print("  ID={:<7} Familia={:<30} Tipo={:<20} Punto={} Conectores={}".format(
                d["id"], d["familia"][:30], d["tipo"][:20], d["punto_mm"], d["num_conectores"]))

        # 5. Guardar reporte JSON
        reporte = {
            "version": "v01",
            "script": "RE7_DIAG_UNIONES_V02F",
            "generado_utc": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "archivo": ruta_v02f,
            "familias_cargadas": {k: sorted(v) for k, v in familias_fitting.items()},
            "total_fittings_colocados": len(instancias),
            "por_tipo": por_tipo,
            "total_conduits": len(conduits),
            "detalle_fittings": detalles,
        }

        raiz = r"D:\Work\PROJECTS\RevitElectrico"
        out_path = os.path.join(raiz, "data", "f7_diagnostico_uniones_v02f_v01.json")
        with open(out_path, "w") as f:
            json.dump(reporte, f, ensure_ascii=True, indent=2)
        print("")
        print("Reporte guardado en: {}".format(out_path))
        print("=" * 70)

        return reporte

    finally:
        # Cerrar el documento V02-f sin guardar cambios
        try:
            doc_v02f.Close(False)
        except Exception:
            pass


# Si se ejecuta directamente en pyRevit
if __name__ == "__main__":
    try:
        app = __revit__.Application
        diagnosticar_v02f(app=app)
    except NameError:
        print("Este script debe ejecutarse dentro de Revit (pyRevit).")
        print("Uso: exec(open(ruta_script).read())")
        print("     diagnosticar_v02f(ruta_v02f=\"...\")")
