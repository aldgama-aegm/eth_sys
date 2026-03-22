import streamlit as st

# PARCHE DE COMPATIBILIDAD: Ejecutar antes de cualquier otro import
import sys
try:
    import altair as alt
    # Forzamos la ruta que Streamlit busca si no existe
    if not hasattr(alt, 'vegalite'):
        sys.modules['altair.vegalite.v4'] = alt
except ImportError:
    pass

import pandas as pd
import google.generativeai as genai

# ==========================================================
# 1. CONFIGURACIÓN DE PÁGINA
# ==========================================================
st.set_page_config(page_title="BioSim AI - Planta Etanol", layout="wide")

# Intentar importar BioSTEAM de forma segura
try:
    import biosteam as bst
    import thermosteam as tmo
    BIO_READY = True
except Exception as e:
    BIO_READY = False
    ERR_MSG = str(e)

# ==========================================================
# 2. LÓGICA DE SIMULACIÓN
# ==========================================================
def run_simulation(w_flow, e_flow, p_flash, t_in):
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes
    mosto = bst.Stream("1-Mosto", Water=w_flow, Ethanol=e_flow, units="kmol/h", 
                       T=t_in + 273.15, P=101325)
    v_ret = bst.Stream("Vinazas-Retorno", Water=w_flow, units="kmol/h", T=363.15, P=300000)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    E100 = bst.HXprocess("E100", ins=(P100-0, v_ret), outs=("3-Mosto-Pre", "Dren"), phase0="g", phase1="L")
    E100.outs[0].T = 358.15
    E101 = bst.HXutility("E101", ins=E100-0, outs=("Mezcla"), T=368.15)
    V100 = bst.IsenthalpicValve("V100", ins=E101-0, P=p_flash)
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor", "Vinazas"), P=p_flash, Q=0)
    E102 = bst.HXutility("E102", ins=V1-0, outs="Producto", T=298.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=v_ret, P=3*101325)

    sys_model = bst.System("Etanol_Sys", path=(P100, E100, E101, V100, V1, E102, P200))
    sys_model.simulate()
    return sys_model, E102

# ==========================================================
# 3. INTERFAZ DE USUARIO (LAYOUT COLUMNAS)
# ==========================================================
st.title("🧪 Asistente Técnico: Simulación BioSTEAM")

if not BIO_READY:
    st.error(f"Error cargando librerías científicas: {ERR_MSG}")
    st.stop()

col_ctrl, col_disp = st.columns([1, 3], gap="medium")

with col_ctrl:
    st.subheader("⚙️ Parámetros")
    w_flow = st.slider("Agua (kmol/h)", 10.0, 100.0, 43.2)
    e_flow = st.slider("Etanol (kmol/h)", 1.0, 20.0, 4.9)
    p_fla = st.number_input("Presión Flash (Pa)", value=101325)
    t_input = st.number_input("Temp. Entrada (°C)", value=25)
    
    sim_btn = st.button("🚀 Iniciar Simulación", use_container_width=True)

if sim_btn:
    with st.spinner("Simulando..."):
        try:
            res_sys, cond = run_simulation(w_flow, e_flow, p_fla, t_input)
            
            with col_disp:
                # KPIs
                k1, k2, k3 = st.columns(3)
                k1.metric("Producción Etanol", f"{cond.outs[0].imass['Ethanol']:.2f} kg/h")
                k2.metric("Pureza Molar", f"{cond.outs[0].get_molar_fraction('Ethanol'):.4f}")
                k3.metric("Energía E-102", f"{abs(cond.design_results.get('Heat duty', 0))/1000:.1f} MJ/h")
                
                st.divider()
                
                # Tablas lado a lado
                t_mat, t_ene = st.columns(2)
                res_data = res_sys.get_results().T
                
                with t_mat:
                    st.write("**Balances de Masa**")
                    st.dataframe(res_data[['Flow']], use_container_width=True)
                with t_ene:
                    st.write("**Propiedades Físicas**")
                    st.dataframe(res_data[['Temperature', 'Pressure']], use_container_width=True)
                
                # PFD
                st.subheader("🖼️ Diagrama de Proceso (PFD)")
                st.image(res_sys.diagram(), use_container_width=True)
                
                # Gemini
                if "GEMINI_API_KEY" in st.secrets:
                    st.divider()
                    st.subheader("🤖 Análisis del Tutor IA")
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    prompt = f"Explica la eficiencia de este flash a {p_fla} Pa con {e_flow} kmol/h de etanol de entrada."
                    st.info(model.generate_content(prompt).text)

        except Exception as ex:
            st.error(f"Fallo en convergencia: {ex}")
