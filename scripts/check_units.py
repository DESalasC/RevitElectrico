import ezdxf

# Check master DXF units
doc = ezdxf.readfile(r'D:\Work\PROJECTS\RevitElectrico\ArchivosBase\STM-T5-P5_bloques_electricos.dxf')
print("Master DXF INSUNITS:", doc.header.get('$INSUNITS'))
print("Master DXF MEASUREMENT:", doc.header.get('$MEASUREMENT'))

# Check individual apartment DXF units
doc2 = ezdxf.readfile(r'D:\Work\PROJECTS\RevitElectrico\ArchivosBase\Apartamento Tipo E 08.dxf')
print("\nE08 DXF INSUNITS:", doc2.header.get('$INSUNITS'))
print("E08 DXF MEASUREMENT:", doc2.header.get('$MEASUREMENT'))

# INSUNITS values: 0=unitless, 1=inches, 2=feet, 3=miles, 4=mm, 5=cm, 6=m, 7=km, 8=microinches, 9=mils, 10=microns, 11=decimeters, 12=decameters, 13=hectometers, 14=gigameters
units_map = {0:'unitless',1:'inches',2:'feet',3:'miles',4:'mm',5:'cm',6:'m',7:'km'}
print("\nMaster units:", units_map.get(doc.header.get('$INSUNITS', 0), 'unknown'))
print("E08 units:", units_map.get(doc2.header.get('$INSUNITS', 0), 'unknown'))