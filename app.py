import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

def run_simulation(flow_water, flow_eth, temp_in, pressure_flash):
    # LIMPIEZA CRÍTICA: Evita errores de ID duplicado
    bst.main_flowsheet.clear() 
    bst.settings.set_thermo(tmo.Chemicals(["Water", "Ethanol"]))

    # Definición de Corrientes dinámicas
    mosto = bst.Stream("Mosto", Water=flow_water, Ethanol=flow_eth, 
                       units="kmol/h", T=temp_in + 273.15, P=101325)
    
    vinazas_retorno = bst.Stream("Vinazas_Retorno", Water=flow_water, 
                                  T=90+273.15, P=300000)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    E100 = bst.HXprocess("E100", ins=(P100-0, vinazas_retorno), 
                         outs=("Mosto_Pre", "Drenaje"), phase0="g", phase1="L")
    E100.outs[0].T = 85 + 273.15
    
    E101 = bst.HXutility("E101", ins=E100-0, outs=("Mezcla"), T=95+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=E101-0, P=pressure_flash)
    
    # Manejo de Errores Específicos: Usamos .design_results o .results
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor", "Vinazas"), P=pressure_flash, Q=0)
    
    E102 = bst.HXutility("E102", ins=V1-0, outs="Producto", T=25+273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    sys = bst.System("Planta_Etanol", path=(P100, E100, E101, V100, V1, E102, P200))
    sys.simulate()
    
    return sys, V1, E102

# --- INTERFAZ STREAMLIT ---
st.set_page_config(page_title="BioSim AI", layout="wide")
st.title("🧪 BioSim Interactivo: Planta de Etanol")

with st.sidebar:
    st.header("Parámetros de Entrada")
    f_w = st.slider("Flujo Agua (kmol/h)", 10.0, 100.0, 43.2)
    f_e = st.slider("Flujo Etanol (kmol/h)", 1.0, 20.0, 4.9)
    t_in = st.number_input("Temp. Entrada (°C)", value=25)
    p_f = st.number_input("Presión Flash (Pa)", value=101325)

if st.button("Ejecutar Simulación"):
    sim_sys, flash_unit, condenser = run_simulation(f_w, f_e, t_in, p_f)
    
    # Mostrar PFD (Diagrama)
    st.subheader("Diagrama de Proceso (PFD)")
    # BioSTEAM genera un objeto Digraph que Streamlit puede renderizar
    st.graphviz_chart(sim_sys.diagram('png'))
    
    # Resultados
    st.success("Simulación Convergida")
    res_df = sim_sys.get_results()
    st.table(res_df)
