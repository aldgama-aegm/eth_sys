import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# ==========================================================
# 1. CONFIGURACIÓN DE LA PÁGINA Y ESTILOS
# ==========================================================
st.set_page_config(page_title="BioSTEAM Hub - Planta de Etanol", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_content_type=True)

# Configuración de Gemini desde Secrets
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model_ai = genai.GenerativeModel('gemini-1.5-flash')
except:
    st.warning("⚠️ GEMINI_API_KEY no detectada en Secrets. El tutor IA estará desactivado.")

# ==========================================================
# 2. MOTOR DE SIMULACIÓN (ENCAPSULADO)
# ==========================================================
def run_simulation(flow_w, flow_e, flash_p, temp_in):
    # Limpieza de flowsheet para evitar error 'ID duplicado'
    bst.main_flowsheet.clear()
    
    # Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes Dinámicas
    mosto = bst.Stream("1-Mosto", Water=flow_w, Ethanol=flow_e, units="kmol/h", 
                       T=temp_in + 273.15, P=101325)
    
    vinazas_retorno = bst.Stream("Vinazas-Retorno", Water=flow_w, units="kmol/h", 
                                 T=90+273.15, P=300000)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    E100 = bst.HXprocess("E100", ins=(P100-0, vinazas_retorno), 
                         outs=("3-Mosto-Pre", "Drenaje"), phase0="g", phase1="L")
    E100.outs[0].T = 85 + 273.15
    
    E101 = bst.HXutility("E101", ins=E100-0, outs=("Mezcla"), T=95+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=E101-0, outs="Mezcla-Bifasica", P=flash_p)
    
    # El tanque Flash V1 se define con Q=0 (adiabático) para evitar errores de .duty
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor_Caliente", "Vinazas"), P=flash_p, Q=0)
    
    E102 = bst.HXutility("E102", ins=V1-0, outs="Producto_Final", T=25+273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    # Sistema
    sys = bst.System("Planta_Etanol", path=(P100, E100, E101, V100, V1, E102, P200))
    sys.simulate()
    
    return sys, V1, E102, mosto

# ==========================================================
# 3. LAYOUT DE COLUMNAS (INTERFAZ)
# ==========================================================
st.title("🧪 Simulador BioSTEAM + IA")
st.caption("Ingeniería de Procesos en Tiempo Real con Streamlit Cloud")

col_input, col_results = st.columns([1, 3], gap="large")

with col_input:
    st.header("⚙️ Parámetros")
    with st.expander("Flujos de Alimentación", expanded=True):
        w_in = st.slider("Agua (kmol/h)", 10.0, 100.0, 43.2)
        e_in = st.slider("Etanol (kmol/h)", 1.0, 20.0, 4.9)
    
    with st.expander("Condiciones Operativas"):
        t_in = st.number_input("Temp. Entrada (°C)", value=25)
        p_flash = st.number_input("Presión Flash (Pa)", value=101325)
    
    btn_sim = st.button("🚀 Ejecutar Simulación", use_container_width=True)

# ==========================================================
# 4. EJECUCIÓN Y VISUALIZACIÓN
# ==========================================================
if btn_sim:
    with st.spinner("Calculando balances..."):
        try:
            sys, v1, e102, feed = run_simulation(w_in, e_in, p_flash, t_in)
            
            with col_results:
                # --- MÉTRICAS KPI ---
                kpi1, kpi2, kpi3 = st.columns(3)
                prod_etanol = e102.outs[0].imass['Ethanol']
                pureza = e102.outs[0].get_concentration('Ethanol') # Aproximación
                energia_total = abs(e102.design_results.get('Heat duty', 0)) / 1000 # MJ/h
                
                kpi1.metric("Producción Etanol", f"{prod_etanol:.2f} kg/h")
                kpi2.metric("Pureza (Fracción)", f"{e102.outs[0].get_molar_fraction('Ethanol'):.3f}")
                kpi3.metric("Energía Condensador", f"{energia_total:.1f} MJ/h")
                
                st.divider()

                # --- TABLAS LADO A LADO ---
                tab_materia, tab_energia = st.columns(2)
                
                with tab_materia:
                    st.subheader("📦 Balance de Materia")
                    st.dataframe(sys.get_results().T[['Flow']], use_container_width=True)
                
                with tab_energia:
                    st.subheader("⚡ Balance de Energía")
                    st.dataframe(sys.get_results().T[['Temperature', 'Pressure']], use_container_width=True)

                # --- DIAGRAMA PFD ---
                st.subheader("🖼️ Diagrama
