# -*- coding: utf-8 -*-
"""
F6_PROBE_TECHO_v01.py
=====================
Sonda de SOLO LECTURA sobre los cielorrasos que cubren una posicion XY.

Para que sirve
--------------
Las 8 lamparas de E 05 no encuentran cara de anfitrion aunque:
  * hay techos cuyo bounding box cubre el punto (22 a 43),
  * y sus cotas incluyen 15.84 m, que es la del Piso 5.
Ninguno de los cuatro intentos de busqueda funciono, incluido el que ignora el
sentido de la normal. Esta sonda abre esos cielorrasos y muestra, cara por cara,
su cota y su normal, para ver exactamente que hay ahi.

Uso
---
    exec(open(r"...\\F6_PROBE_TECHO_v01.py").read())

    # con las coordenadas de la primera lampara del JSON de transferencia
    probe(doc)

    # o con coordenadas explicitas (metros)
    probe(doc, x=5.757, y=6.822)

Salida
------
Por cada techo cuyo bbox cubre el punto:
    id, nombre, rango Z del bbox, numero de solidos y de caras,
    y las caras HORIZONTALES con su Z y el signo de la normal.
Al final, la cota objetivo y cuantas caras caen dentro de +-0.30 m.
"""
import io
import json
import os

from Autodesk.Revit.DB import (
    BuiltInCategory,
    FilteredElementCollector,
    GeometryInstance,
    Level,
    Options,
    Solid,
)

FT = 0.3048  # pies -> metros
TOL_M = 0.30

# Primera lampara del JSON de transferencia, por si no se pasan coordenadas
X_DEFECTO = 5.757
Y_DEFECTO = 6.822
Z_DEFECTO = 15.82


def _resolver_doc(doc):
    if doc is not None:
        return doc
    try:
        uidoc = __revit__.ActiveUIDocument  # noqa: F821
        return uidoc.Document if uidoc is not None else None
    except Exception:
        return None


def _safe(v):
    if v is None:
        return ""
    try:
        s = str(v)
    except Exception:
        return "?"
    out = []
    for c in s:
        try:
            c.encode("ascii")
            out.append(c)
        except Exception:
            out.append("_")
    return "".join(out)


def _clave(t):
    if t is None:
        return ""
    try:
        s = unicode(t)  # noqa: F821
    except Exception:
        s = str(t)
    import unicodedata
    try:
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    except Exception:
        pass
    return "".join(c.lower() for c in s if c.isalpha() or c.isdigit())


def _geometria(host):
    for nombre in ("get_Geometry", "GetGeometry", "get_geometry"):
        try:
            fn = getattr(host, nombre)
        except Exception:
            continue
        if not callable(fn):
            continue
        try:
            opts = Options()
            opts.ComputeReferences = True
            return fn(opts)
        except Exception:
            return None
    return None


def _caras_horizontales(host):
    """[(z_m, normal_z, dist_m)] de todas las caras horizontales del host."""
    salida = []
    geo = _geometria(host)
    if geo is None:
        return salida, 0, 0

    def tratar(sol, contador):
        try:
            for f in sol.Faces:
                contador[0] += 1
                try:
                    pr = f.Project(XYZ_REF[0])
                    if pr is None:
                        continue
                    n = f.ComputeNormal(pr.UVPoint)
                    if abs(n.Z) < 0.7:
                        continue
                    salida.append((pr.XYZPoint.Z, n.Z, pr.Distance))
                except Exception:
                    pass
        except Exception:
            pass

    solidos = 0
    contador = [0]
    try:
        for g in geo:
            if g is None:
                continue
            if isinstance(g, Solid):
                solidos += 1
                tratar(g, contador)
            elif isinstance(g, GeometryInstance):
                try:
                    for gg in g.GetInstanceGeometry():
                        if isinstance(gg, Solid):
                            solidos += 1
                            tratar(gg, contador)
                except Exception:
                    pass
    except Exception:
        pass
    return salida, solidos, contador[0]


XYZ_REF = [None]


def probe(doc=None, x=None, y=None, z=None):
    doc = _resolver_doc(doc)
    if doc is None:
        print("No hay documento activo.")
        return None

    x = X_DEFECTO if x is None else float(x)
    y = Y_DEFECTO if y is None else float(y)
    z = Z_DEFECTO if z is None else float(z)

    # construir un XYZ sin depender del import global
    from Autodesk.Revit.DB import XYZ
    punto = XYZ(x / FT, y / FT, z / FT)
    XYZ_REF[0] = punto

    print("=" * 74)
    print("PROBE TECHO  |  doc: " + _safe(doc.Title))
    print("Punto de prueba: x={:.3f}  y={:.3f}  z={:.3f} m".format(x, y, z))
    print("=" * 74)

    nivel = None
    for lv in FilteredElementCollector(doc).OfClass(Level):
        if _clave(lv.Name) == _clave("Piso 5"):
            nivel = lv
            break

    techos = list(FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Ceilings).WhereElementIsNotElementType())
    print("Techos en el documento: {}".format(len(techos)))

    cubren = []
    for t in techos:
        bb = t.get_BoundingBox(None)
        if bb is None:
            continue
        if not (bb.Min.X - 0.5 <= punto.X <= bb.Max.X + 0.5 and
                bb.Min.Y - 0.5 <= punto.Y <= bb.Max.Y + 0.5):
            continue
        cubren.append((t, bb))

    print("Techos cuyo bbox cubre el punto: {}".format(len(cubren)))

    con_cara_cerca = 0
    for t, bb in cubren:
        caras, solidos, n_caras = _caras_horizontales(t)
        zmin = round(bb.Min.Z * FT, 3)
        zmax = round(bb.Max.Z * FT, 3)
        cerca = [c for c in caras if abs(c[0] * FT - z) <= TOL_M]
        if cerca:
            con_cara_cerca += 1
        print("\n  id={}  {:.50}".format(_safe(t.Id), _safe(t.Name)))
        print("     bbox Z: {:.3f} .. {:.3f} m   solidos={} caras={} horizontales={}".format(
            zmin, zmax, solidos, n_caras, len(caras)))
        if not caras:
            print("     (ninguna cara horizontal)")
            continue
        for cz, nz, dist in sorted(caras, key=lambda c: c[0])[:8]:
            marca = "  <== objetivo +-0.30 m" if abs(cz * FT - z) <= TOL_M else ""
            print("     cara Z={:.3f} m  normalZ={:+.2f}  dist={:.3f} m{}".format(
                cz * FT, nz, dist * FT, marca))

    print("\n" + "=" * 74)
    print("RESUMEN: {} techos cubren el punto; {} tienen alguna cara horizontal "
          "dentro de +-{:.2f} m de la cota objetivo.".format(
              len(cubren), con_cara_cerca, TOL_M))
    if con_cara_cerca == 0:
        print("Ninguna cara horizontal a esa cota: el cielorraso no esta a 15.82 m")
        print("o su geometria no es accesible en esa posicion.")
    print("=" * 74)
    return {"cubren": len(cubren), "con_cara_cerca": con_cara_cerca}


if __name__ == "__main__":
    probe()
