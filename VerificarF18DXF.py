# Verificar F18 en DXF
import ezdxf
doc = ezdxf.readfile(r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf")

# Buscar bloques F18
for block in doc.blocks:
    if 'F 18' in block.name or 'F 18' in block.name:
        print("Block: {} ({} entidades)".format(block.name, len(block)))
        for entity in block:
            if entity.dxftype() == 'INSERT' and 'NET-PAU' in entity.dxf.name:
                print("  NET-PAU: {} @ ({:.2f},{:.2f})".format(entity.dxf.name, entity.dxf.insert.x, entity.dxf.insert.y))

# Buscar instancias en modelspace
for entity in doc.modelspace():
    if entity.dxftype() == 'INSERT' and 'F 18' in entity.dxf.name:
        print("Instancia: {} @ ({:.2f},{:.2f})".format(entity.dxf.name, entity.dxf.insert.x, entity.dxf.insert.y))
