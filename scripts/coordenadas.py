 
import ezdxf
doc_dxf = ezdxf.readfile(r"D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf")
for entity in doc_dxf.modelspace():
    if entity.dxftype() == 'INSERT' and entity.dxf.name == 'Apartamento Tipo E 06':
        print("Rotación:", entity.dxf.rotation)
        print("Posición:", entity.dxf.insert)

S