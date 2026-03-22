import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai
import os

# ==========================================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================================
st.set_page_config(
    page_title="BioSTEAM Explorer + Gemini AI",
    page_icon="🧪",
    layout="wide"
)

# Estilo personalizado para las métricas y contenedores
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 28px; color: #007BFF; }
    .stDataFrame { border: 1px solid #e6e9ef; border-radius: 5px; }
    </style>
    """, unsafe_content_type=True)

# Configuración de IA (Gemini)
def get_ai_response(prompt_text):
    try:
        if "GEMINI_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt_text)
            return response.text
        else:
            return "⚠️ API Key no configurada en Secrets."
    except Exception as e:
        return f"❌ Error al conectar con Gemini: {str(e)}"

# ==========================================================
# 2. MOTOR DE CÁLCULO (BIOSTEAM)
# ==========================================================
def run_simulation(w_flow, e_flow, flash_p, t_input):
    # LIMPIEZA TOTAL: Evita el error de 'Duplicate ID' en cada refresco de Streamlit
    bst.main_flowsheet.clear()
    
    # Configuración Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Definición de Corrientes
    mosto = bst.Stream("1-Mosto", Water=w_flow, Ethanol=e_flow, units="kmol/h", 
                       T=t_input + 273.15, P=101325)
    
    vinazas_retorno = bst.Stream("Vinazas-Retorno", Water=w_flow, units="kmol/h", 
                                 T=90+273.15, P=300000)

    # Equipos
    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    
    E100 = bst.HXprocess("E100", ins=(P100-0, vinazas_retorno), 
                         outs=("3-Mosto-Pre", "Drenaje"), phase0="g", phase1="L")
    E100.outs[0].T = 85 + 273.15
    
    E101 = bst.HXutility("E101", ins=E100-0, outs=("Mezcla"), T=95+273.15)
    
    V100 = bst.IsenthalpicValve("V100", ins=E101-0, outs="Mezcla-Bifasica", P=flash_p)
    
    # Tanque Flash (Manejo de energía: Q=0 para evitar errores de .duty en balance)
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor_Caliente", "Vinazas"), P=flash_p, Q=0)
    
    E102 = bst.HXutility("E102", ins=V1-0, outs="Producto_Final", T=25+273.15)
    
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    # Crear Sistema y Simular
    sys = bst.System("Planta_Etanol", path=(P100, E100, E101, V100, V1, E102, P200))
    sys.simulate()
    
    return sys, V1, E102

# ==========================================================
# 3. INTERFAZ DE USUARIO (LAYOUT)
# ==========================================================
st.title("🧪 BioSTEAM Technical Assistant")
st.markdown("---")

# Barra lateral para controles
with st.sidebar:
    st.header("🎛️ Parámetros de Proceso")
    st.info("Ajusta los flujos y condiciones para recalcular el balance.")
    
    w_in = st.slider("Flujo Agua (kmol/h)", 10.0, 100.0, 43.2)
    e_in = st.slider("Flujo Etanol (kmol/h)", 1.0, 30.0, 4.9)
    t_in = st.number_input("Temp. Alimentación (°C)", value=25)
    p_fla = st.number_input("Presión de Flash (Pa)", value=101325, step=5000)
    
    st.divider()
    run_btn = st.button("🚀 Ejecutar Simulación", use_container_width=True)

# Área principal de resultados
if run_btn:
    with st.spinner("Calculando balances de materia y energía..."):
        try:
            # Ejecutar simulación
            sys, v1, e102 = run_simulation(w_in, e_in, p_fla, t_in)
            
            # --- SECCIÓN 1: KPIs ---
            m1, m2, m3 = st.columns(3)
            prod_kg = e102.outs[0].imass['Ethanol']
            frac_mol = e102.outs[0].get_molar_fraction('Ethanol')
            # Manejo de energía seguro para el condensador
            q_cond = abs(e102.design_results.get('Heat duty', 0)) / 1000 # MJ/h
            
            m1.metric("Producción de Etanol", f"{prod_kg:.2f} kg/h")
            m2.metric("Pureza en Producto", f"{frac_mol:.2%} mol")
            m3.metric("Carga Térmica (E-102)", f"{q_cond:.1f} MJ/h")
            
            st.divider()

            # --- SECCIÓN 2: TABLAS COMPARATIVAS ---
            st.subheader("📊 Análisis de Corrientes")
            col_mat, col_ene = st.columns(2)
            
            # Formatear tablas para mejor lectura
            res_df = sys.get_results().T
            
            with col_mat:
                st.write("**Balance de Materia (Flujos)**")
                st.dataframe(res_df[['Flow']], use_container_width=True)
            
            with col_ene:
                st.write("**Parámetros Termodinámicos**")
                st.dataframe(res_df[['Temperature', 'Pressure']], use_container_width=True)

            # --- SECCIÓN 3: PFD ---
            st.subheader("🖼️ Diagrama de Flujo (PFD)")
            st.image(sys.diagram(), use_container_width=True)

            # --- SECCIÓN 4: TUTOR IA ---
            st.divider()
            st.subheader("🤖 Tutor de Ingeniería Química (Gemini)")
            
            resumen_ia = f"""
            Simulación BioSTEAM: Entrada {e_in} kmol/h etanol. 
            Salida producto: {frac_mol:.4f} fracción molar etanol. 
            Presión Flash: {p_fla} Pa. 
            ¿Cómo afecta esta presión a la volatilidad relativa y qué recomiendas para mejorar la pureza?
            """
            
            with st.chat_message("assistant"):
                respuesta_tutor = get_ai_response(resumen_ia)
                st.write(respuesta_tutor)

        except Exception as e:
            st.error(f"⚠️ Error en la simulación: {str(e)}")
else:
    st.warning("👈 Configura los parámetros en el panel izquierdo y presiona el botón para iniciar.")
