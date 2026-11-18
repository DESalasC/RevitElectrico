with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "r", encoding="utf-8") as f:
    content = f.read()

old = """FAMILIAS_MURO_FACE = {
    "M_Interruptores", "M_Pulsador - Interruptor", "M_Timbre",
    "M_Toma doble", "M_Comunicaciones", "M_Climatizacion"
}
FAMILIAS_TECHO_FACE = {
    "M_Iluminacion", "M_ClimatizacionV", "Consolidation_Point"
}"""

new = """FAMILIAS_MURO_FACE = {
    "M_Toma doble",       # WorkPlaneBased - FIX v03 #2: evitar bug P3 (tomas sin host)
    "M_Comunicaciones",   # WorkPlaneBased - FIX v03 #2: mismo motivo
}
FAMILIAS_TECHO_FACE = {
    "M_Iluminacion",
    "M_ClimatizacionV",
    "Consolidation_Point",
}"""

content = content.replace(old, new)

with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed")