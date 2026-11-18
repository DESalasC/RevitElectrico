#!/usr/bin/env python3
"""Fix C# templates to use JsonConvert.SerializeObject for all returns"""
import re

with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace manual JSON returns with JsonConvert.SerializeObject in CS_FACE_WALL
# Pattern: return "{\"success\":false,\"error\":\"...\" + var + \"...\"}";
# Replace with: return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "..." + var + "..." });

# Fix CS_FACE_WALL
old_wall = '''catch (Exception exPlace) { return "{\\\"success\\\":false,\\\"error\\\":\\\"NewFamilyInstance failed: \\\" + exPlace.Message}\"; }
if (inst == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"inst is null\\\"}\";'''
new_wall = '''catch (Exception exPlace) { return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "NewFamilyInstance failed: " + exPlace.Message }); }
if (inst == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "inst is null" });'''
content = content.replace(old_wall, new_wall)

old_wall2 = '''catch (Exception exRot) { return "{\\\"success\\\":false,\\\"error\\\":\\\"Rotate failed: \\\" + exRot.Message}\"; }'''
new_wall2 = '''catch (Exception exRot) { return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Rotate failed: " + exRot.Message }); }'''
content = content.replace(old_wall2, new_wall2)

old_wall3 = '''return "{\\\"success\\\":true,\\\"elementId\\\":\" + (inst?.Id.Value ?? 0) + \\",\\\"uniqueId\\\":\\\"\" + (inst?.UniqueId ?? \"\") + \"\\\",\\\"hostId\\\":\" + hId + \\",\\\"usedFace\\\":true,\\\"placementMethod\\\":\\\"wall_face_based\\\"}\";'''
new_wall3 = '''return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = true, elementId = (inst?.Id.Value ?? 0), uniqueId = (inst?.UniqueId ?? ""), hostId = hId, usedFace = true, placementMethod = "wall_face_based" });'''
content = content.replace(old_wall3, new_wall3)

# Fix CS_FACE_CEILING - similar patterns
old_ceil1 = '''if (sym == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"Symbol not found: \\\" + familia + \\\" / \\\" + tipo}\";'''
new_ceil1 = '''if (sym == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Symbol not found: " + familia + " / " + tipo });'''
content = content.replace(old_ceil1, new_ceil1)

old_ceil2 = '''if (lvl == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"Level not found\\\"}\";'''
new_ceil2 = '''if (lvl == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Level not found" });'''
content = content.replace(old_ceil2, new_ceil2)

old_ceil3 = '''if (bestC == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"No ceiling\\\"}\";'''
new_ceil3 = '''if (bestC == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "No ceiling" });'''
content = content.replace(old_ceil3, new_ceil3)

old_ceil4 = '''if (faceRef == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"No ceiling face\\\"}\";'''
new_ceil4 = '''if (faceRef == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "No ceiling face" });'''
content = content.replace(old_ceil4, new_ceil4)

old_ceil5 = '''return "{\\\"success\\\":true,\\\"elementId\\\":\" + (inst?.Id.Value ?? 0) + \\",\\\"uniqueId\\\":\\\"\" + (inst?.UniqueId ?? \"\") + \"\\\",\\\"hostId\\\":\" + hId + \\",\\\"usedFace\\\":true,\\\"placementMethod\\\":\\\"ceiling_face_based\\\"}\";'''
new_ceil5 = '''return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = true, elementId = (inst?.Id.Value ?? 0), uniqueId = (inst?.UniqueId ?? ""), hostId = hId, usedFace = true, placementMethod = "ceiling_face_based" });'''
content = content.replace(old_ceil5, new_ceil5)

# Fix CS_LEVEL_BASED
old_level1 = '''if (sym == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"Symbol not found: \\\" + familia + \\\" / \\\" + tipo}\";'''
new_level1 = '''if (sym == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Symbol not found: " + familia + " / " + tipo });'''
content = content.replace(old_level1, new_level1)

old_level2 = '''if (lvl == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"Level not found\\\"}\";'''
new_level2 = '''if (lvl == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Level not found" });'''
content = content.replace(old_level2, new_level2)

old_level3 = '''if (inst == null) return "{\\\"success\\\":false,\\\"error\\\":\\\"Create failed\\\"}\";'''
new_level3 = '''if (inst == null) return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = false, error = "Create failed" });'''
content = content.replace(old_level3, new_level3)

old_level4 = '''return "{\\\"success\\\":true,\\\"elementId\\\":\" + (inst?.Id.Value ?? 0) + \\",\\\"uniqueId\\\":\\\"\" + (inst?.UniqueId ?? \"\") + \"\\\",\\\"hostId\\\":0,\\\"usedFace\\\":false,\\\"placementMethod\\\":\\\"level_based\\\"}\";'''
new_level4 = '''return Newtonsoft.Json.JsonConvert.SerializeObject(new { success = true, elementId = (inst?.Id.Value ?? 0), uniqueId = (inst?.UniqueId ?? ""), hostId = 0, usedFace = false, placementMethod = "level_based" });'''
content = content.replace(old_level4, new_level4)

# Fix CS_GET_PANELS, CS_GET_WALLS, CS_GET_CEILINGS - they already return JsonConvert.SerializeObject(list) which is fine

with open("D:/Work/PROJECTS/RevitElectrico/F6_COLOCAR_F01_F02_v03.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed all C# template returns to use JsonConvert.SerializeObject")