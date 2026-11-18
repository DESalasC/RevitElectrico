with open("D:/Work/PROJECTS/RevitElectrico/scripts/F6_COLOCAR_PYREVIT_v01.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix ElementId.IntegerValue -> int(ElementId)
content = content.replace('.IntegerValue', '')

# But need to be careful - only for ElementId properties, not for other .IntegerValue uses
# Let me check what uses .IntegerValue
import re
for m in re.finditer(r'\w+\.IntegerValue', content):
    print(m.group())

# Actually, let me just replace the specific known cases:
# fi.LevelId.IntegerValue -> int(fi.LevelId)
# wall.Id.IntegerValue -> int(wall.Id)
# ceiling.Id.IntegerValue -> int(ceiling.Id)
# new_inst.Id.IntegerValue -> int(new_inst.Id)
# etc.

content = content.replace('fi.LevelId.IntegerValue', 'int(fi.LevelId)')
content = content.replace('wall.Id.IntegerValue', 'int(wall.Id)')
content = content.replace('ceiling.Id.IntegerValue', 'int(ceiling.Id)')
content = content.replace('new_inst.Id.IntegerValue', 'int(new_inst.Id)')
content = content.replace('wl.Id.IntegerValue', 'int(wl.Id)')
content = content.replace('panel_obj["levelId"]', 'panel_obj["levelId"]')  # this is already int from dict
# The panel_obj["levelId"] was stored as int(fi.LevelId) so it's already fine

# Also fix any ElementId used as key in dict - they need to be int
# panel_obj["elementId"] = int(fi.Id)

with open("D:/Work/PROJECTS/RevitElectrico/scripts/F6_COLOCAR_PYREVIT_v01.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed ElementId.IntegerValue -> int()")