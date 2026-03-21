#=================================================================
#Importamos las librerías
#=================================================================
import biosteam as bst                    #La librería principal para simulación de procesos con python
import thermosteam as tmo                 #Motor termodinámico (Propiedades físicas, equilibrio de fases, etc.)
import pandas as pd                       #Librería para manejar tablas
import os                                 #Librería para interactuar con el sistema operativo
from IPython.display import Image, display#Para mostrar las figuras de Biosteam

#=================================================================
#1. CONFIGURACIÓN DE LA SIMULACIÓN
#=================================================================
#Definimos los compuestos químicos a utilizar
chemicals=tmo.Chemicals(["Water","Ethanol"])

#Configuración termodinámica
#set_thermo: le dice a Biosteam-->para cualquier cálculo nuevo utiliza los compuestos que llamaste
#Por defecto Biosteam intentará usar modelos de actividad (NTRL o UNIFAC)
bst.settings.set_thermo(chemicals)

#=================================================================
#2. DEFINICIÓN DE CORRIENTES
#=================================================================
#-------------Alimentación----------------------------------------
mosto=bst.Stream("1-MOSTO",
                 Water=900, Ethanol=100, units="kg/hr",
                 T=25+273.15,
                 P=101325)

#------Corriente de reciclo---------------------------------------
vinazas_retorno=bst.Stream("Vinazas-Retorno",
                           Water=200, Ethanol=0, units="kg/hr",
                           T=95 + 273.15,
                           P=300000)

#==================================================================
#3. SELECCIÓN DE EQUIPOS
#==================================================================
#----------------------Bomba de alimentación (P-100)---------------
P100=bst.Pump("P-100", ins=mosto, P=4*101325)

#---------------------Intercambiador de calor (W-210)--------------
W210=bst.HXprocess("W-210",
                   ins=(P100-0, vinazas_retorno),
                   outs=("3-Mosto-Pre","Drenaje"),
                   phase0="l",phase1="l")

#Especificación de diseño
#Aquí ordenamos: "El mosto outs[0]" debe de salir exactamente a 85 °C
#Biosteam calculará cuánta energía se necesita y si la corriente de vinazas puede darla
W210.outs[0].T=85+273.15

#------------------Calentador auxiliar (W-220)----------------------
#Tipo: HXUtility, este método utiliza servicios externos (vapor de caldera) para calentar
W220=bst.HXutility("W-220",
                   ins=W210-0,
                   outs="Mezcla",
                   T=92+273.15)

#------------------Válvula de expansión------------------------------
V100=bst.IsenthalpicValve("V-100",
               ins=W220-0,
               outs="Mezcla-Bifásica",
               P=101325
               )

#-----------------Tanque separador (V-1)------------------------------
V1=bst.Flash("V-1",
             ins=V100-0,
             outs=("Vapor caliente", "Vinazas"),
             P=101325, Q=0)

#---------------Condensador--------------------------------------------
W310=bst.HXutility("W-310",
                   ins=V1-0,
                   outs="Producto Final",
                   T=25 + 273.15)

#-------------Bomba de reciclo-----------------------------------------
#Toma el líquido del fondo de flash y lo manda de regreso al W210
P200=bst.Pump("P-200",
              ins=V1-1,
              outs=vinazas_retorno,
              P=3*101325)

#=======================================================================
#4. SIMULACIÓN DEL PROCESO
#=======================================================================
eth_sys=bst.System("planta etanol", path=(P100,W210, W220,V100,V1, W310,P200))

print(">>>>>>>>>>Iniciando simulación del proceso.....")

try:
  #.simulate() ejecuta el método de Wegstein o Sustitución directa
  #para resolver los balances de materia y energía acoplados
  eth_sys.simulate()
  print(">>>>>>✅ !Convergencia exitosa! El balance ha finalizado.\n")
except Exception as e:
  print(f">>>>>-⚠ Advertencia: No se logró la convergencia. Error: {e}\n")

#=========================================================================
#5. REPORTE DE RESULTADOS (GENERACIÓN DE TABLAS)
#=========================================================================
#Esta función toma el sistema simulado y extre los datos importantes a un DataFrame

def generar_reporte(sistema):
  #---PARTE 1: TABLA DE CORRIENTES----
  datos_mat = []
  for s in sistema.streams:
    #Filtramos corrientes vacías para no ensuciar la tabla
    if s.F_mass > 0:
      #Programamos la lógica para mostrar los resultados en un diccionario
      datos_mat.append({
          "ID Corriente":s.ID,
          "Temp (°C)": f"{s.T-273.15:.2f}", #Kelvin a Celsius
          "Presión (bar)": f"{s.P/1e5:.2f}", #Pascales a bar
          "Flujo (kg/h)": f"{s.F_mass:.2f}",
          #Cálculo de procentajes másicos
          "% Etanol": f"{s.imass["Ethanol"]/s.F_mass:.1%}",
          "% Agua": f"{s.imass["Water"]/s.F_mass:.1%}"
      })

  df_mat = pd.DataFrame(datos_mat).set_index("ID Corriente")

  #----PARTE 2: TABLA DE ENERGÍA-----
  datos_en=[]
  for u in sistema.units:
    calor_kw = 0.0
    tipo_servicio = "-"
    #Caso especial: HXProcess (No tiene servicio externo, es recuperación interna)
    #if isintance(u, bst.HXProcess): --> nos pregunta ¿Es el objeto u un intercambiador de calor?
    if isinstance(u, bst.HXprocess):
      #Calculamos el calor ganado/perdio usando Entalpía (H)
      #H está en kJ/h, dividimos entre 3600 para obtener kW (kJ/s)
      calor_kw = (u.outs[0].H-u.ins[0].H)/3600
      tipo_servicio = "Recuperación Interna"

    #Caso estándar: Equipos con duty (Calor intercambiado con servicios auxiliares)
    #hasattr nos pregunta ¿Tiene el objeto (equipo) una propiedad llamada "duty"?
    #is not None nos asegura de que tenga valor numérico
    elif hasattr(u, "duty") and u.duty is not None:
      calor_kw = u.duty/3600
      #Definimos si es calentamiento o enfriamiento según el signo
      if calor_kw > 0.01: tipo_servicio = "Calentamiento (Vapor)"
      if calor_kw < -0.01: tipo_servicio = "Enfriamiento (Agua)"

    #Potencia Eléctrica (Motores de bombas)
    potencia = 0.0

    if hasattr(u, "power_utility") and u.power_utility:
      potencia = u.power_utility.rate

    #Solo agreamos el equipo a la tabla si consume energía relevante
    if abs(calor_kw) > 0.01:
      datos_en.append({
          "ID Equipo": u.ID,
          "Función": tipo_servicio,
          "Energía Térmica (kW)": f"{calor_kw:.2f}",
      })
    if potencia > 0.01:
      datos_en.append({
          "ID Equipo":u.ID,
          "Función":"Motor bomba",
          "Energía eléctrica (kW)": f"{potencia:.2f}"

      })

  df_en=pd.DataFrame(datos_en).set_index("ID Equipo")
  return df_mat, df_en

#Ejecutamos la función y obtenemos las tablas
tabla_materia, tabla_energia = generar_reporte(eth_sys)

#Imprimimos los resultados
print("========TABLA DE BALANCE DE MATERIA=====")
print(tabla_materia)
print("\n ========TABLA DE BALANCE DE ENERGIA=====")
print(tabla_energia)

#==========================================================
#6. ESQUEMA DEL PROCESO (VISUALIZACIÓN)
#==========================================================
print("\n====Diagrama de flujo ======")
try:
  nombre_archivo = "diagrama_etanol_final"
  eth_sys.diagram(file=nombre_archivo, format="png")

  #.display() muestra esa imagen generada aquí mismo en el cuaderno de colab
  display(Image(nombre_archivo + ".png"))
except Exception as e:
  print(f"Error al generar el diagrama: {e}")
