with open(r'D:\Work\PROJECTS\RevitElectrico\scripts\RE6_COLOCAR_TODOS_v01.py', 'r') as f:
    content = f.read()

# Fix _load_json for IronPython 2.7 (no encoding parameter)
old_load = '''def _load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)'''

new_load = '''def _load_json(path):
    with open(path, 'r') as f:
        return json.load(f)'''

if old_load in content:
    content = content.replace(old_load, new_load)
    with open(r'D:\Work\PROJECTS\RevitElectrico\scripts\RE6_COLOCAR_TODOS_v01.py', 'w') as f:
        f.write(content)
    print("Fixed _load_json!")
else:
    print("Pattern not found")

# Also fix the report writing
old_write = '''        with open(report_path, "w", encoding='utf-8') as f:'''
new_write = '''        with open(report_path, "w") as f:'''
if old_write in content:
    content = content.replace(old_write, new_write)
    print("Fixed report write!")

old_write2 = '''    with open(cons_path, "w", encoding='utf-8') as f:'''
new_write2 = '''    with open(cons_path, "w") as f:'''
if old_write2 in content:
    content = content.replace(old_write2, new_write2)
    print("Fixed consolidated write!")

with open(r'D:\Work\PROJECTS\RevitElectrico\scripts\RE6_COLOCAR_TODOS_v01.py', 'w') as f:
    f.write(content)
print("Done")