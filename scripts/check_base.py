import ezdxf

# Verificar BASE en archivo individual
path = r'D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo E 08.dxf'
doc = ezdxf.readfile(path)
print("=== Apartamento Tipo E 08.dxf ===")
print("BASE ($INSBASE):", doc.header.get('$INSBASE'))
print("EXTMIN:", doc.header.get('$EXTMIN'))
print("EXTMAX:", doc.header.get('$EXTMAX'))

# Verificar en el master DXF los bloques de apartamento
master = r'D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf'
mdoc = ezdxf.readfile(master)
print("\n=== Master DXF - Definiciones de apartamento ===")
for bname in ['Apartamento Tipo F 01', 'Apartamento Tipo F 02', 'Apartamento Tipo E 06', 'Apartamento Tipo E 07']:
    if bname in mdoc.blocks:
        b = mdoc.blocks[bname]
        print(f"\n{bname}:")
        print("  BASE ($INSBASE):", b.header.get('$INSBASE') if hasattr(b, 'header') else 'N/A (block)')
        # Buscar entidades en el bloque
        for e in b:
            if e.dxftype() == 'INSERT':
                print(f"  INSERT {e.dxf.name} @ ({e.dxf.insert.x:.4f}, {e.dxf.insert.y:.4f})")

# Verificar INSERTs en modelspace del master
print("\n=== Master DXF - Modelspace (INSERTs de apartamento) ===")
msp = mdoc.modelspace()
for e in msp.query('INSERT'):
    if 'Apartamento' in e.dxf.name and 'Tipo' in e.dxf.name:
        print(f"  {e.dxf.name} @ ({e.dxf.insert.x:.1f}, {e.dxf.insert.y:.1f})")