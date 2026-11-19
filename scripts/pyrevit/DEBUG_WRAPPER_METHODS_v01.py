# -*- coding: utf-8 -*-
# Ver métodos del wrapper usando dir()
# Ejecutar en pyRevit (después de MiAddinLoader.py)

exec(open(r"D:\Work\PROJECTS\RevitElectrico\bin\MiAddinLoader.py").read())

from MiAddin import Placer

# Usar dir() para ver miembros
print("=== Placer members ===")
for attr in dir(Placer):
    if not attr.startswith('_'):
        print("  {}".format(attr))

# Ver si hay PlaceFaceBased
if hasattr(Placer, 'PlaceFaceBased'):
    import System
    method = System.Type.GetType("MiAddin.Placer").GetMethod("PlaceFaceBased")
    if method:
        print("\nPlaceFaceBased signature:")
        for p in method.GetParameters():
            print("  {}: {}".format(p.Name, p.ParameterType))
    else:
        print("\nPlaceFaceBased exists but reflection failed")

if hasattr(Placer, 'PlaceFaceBasedAtPoint'):
    method = System.Type.GetType("MiAddin.Placer").GetMethod("PlaceFaceBasedAtPoint")
    if method:
        print("\nPlaceFaceBasedAtPoint signature:")
        for p in method.GetParameters():
            print("  {}: {}".format(p.Name, p.ParameterType))