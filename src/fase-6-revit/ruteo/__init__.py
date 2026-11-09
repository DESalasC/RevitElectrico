# -*- coding: utf-8 -*-
"""Pipeline de ruteo de conduit para RevitElectrico.

Modulos:
    modelos         entidades del dominio (Dispositivo, Marcador, Polilinea, Tramo)
    config          carga/valida configuracion y tablas de capacidad CSV
    dxf_lector      lectura del DXF (dispositivos, marcadores, polilineas)
    servicio        resolucion del parametro Servicio_Conduit
    dimensionamiento diametro segun cantidad de cables + material + calibre
    ruteador        orquestacion: 2D + marcadores -> tramos 3D
    reporte         resumen en consola y reporte HTML
    cli             linea de comandos
"""
