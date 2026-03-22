import streamlit as st
import biosteam as bst
import thermosteam as tmo
import pandas as pd
import google.generativeai as genai

# ==========================================================
# 1. CONFIGURACIÓN DE LA PÁGINA
# ==========================================================
st.set_page_config(
    page_title="BioSTEAM Explorer + Gemini AI",
    page_icon="🧪",
    layout="wide"
)

st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 26px; color: #02569b; }
    .stDataFrame { border-radius: 8px; }
    </style>
    """, unsafe_content_type=True)

# Configuración de IA (Gemini)
def get_ai_response(prompt_text):
    try:
        if "GEMINI_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-2.5-pro')
            response = model.generate_content(prompt_text)
            return response.text
        else:
            return "⚠️ API Key no detectada. Configura GEMINI_API_KEY en los Secrets de Streamlit."
    except Exception as e:
        return f"❌ Error de IA: {str(e)}"

# ==========================================================
# 2. MOTOR DE CÁLCULO (BIOSTEAM)
# ==========================================================
def run_simulation(w_flow, e_flow, flash_p, t_input):
    # LIMPIEZA CRÍTICA: Evita el error 'Duplicate ID' al mover sliders
    bst.main_flowsheet.clear()
    
    # Termodinámica
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    # Corrientes
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
    
    # Tanque Flash (Q=0 para cálculo adiabático seguro)
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor_Caliente", "Vinazas"), P=flash_p, Q=0)
    
    E102 = bst.HXutility("E102", ins=V1-0, outs="Producto_Final", T=25+273.15)
    
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    sys = bst.System("Planta_Etanol", path=(P100, E100, E101, V100, V1, E102, P200))
    sys.simulate()
    
    return sys, e102

# ==========================================================
# 3. INTERFAZ DE USUARIO (LAYOUT COLUMNAS)
# ==========================================================
st.title("🧪 Simulador BioSTEAM + IA Tutor")
st.markdown("---")

col_input, col_results = st.columns([1, 3], gap="large")

with col_input:
    st.header("🎛️ Controles")
    st.info("Ajusta las variables de operación:")
    
    w_in = st.slider("Agua (kmol/h)", 10.0, 100.0, 43.2)
    e_in = st.slider("Etanol (kmol/h)", 1.0, 30.0, 4.9)
    t_in = st.number_input("Temp. Entrada (°C)", value=25)
    p_fla = st.number_input("Presión Flash (Pa)", value=101325, step=5000)
    
    run_btn = st.button("🚀 Ejecutar Simulación", use_container_width=True)

if run_btn:
    with st.spinner("Resolviendo balances termodinámicos..."):
        try:
            sys, e102 = run_simulation(w_in, e_in, p_fla, t_in)
            
            with col_results:
                # --- MÉTRICAS (KPIs) ---
                m1, m2, m3 = st.columns(3)
                prod_kg = e102.outs[0].imass['Ethanol']
                frac_mol = e102.outs[0].get_molar_fraction('Ethanol')
                q_cond = abs(e102.design_results.get('Heat duty', 0)) / 1000 # MJ/h
                
                m1.metric("Producción Etanol", f"{prod_kg:.2f} kg/h")
                m2.metric("Pureza (Fracción Molar)", f"{frac_mol:.4f}")
                m3.metric("Calor a Remover (E-102)", f"{q_cond:.1f} MJ/h")
                
                st.divider()

                # --- TABLAS LADO A LADO ---
                col_mat, col_ene = st.columns(2)
                res_df = sys.get_results().T
                
                with col_mat:
                    st.subheader("📦 Balance de Materia")
                    st.dataframe(res_df[['Flow']], use_container_width=True)
                
                with col_ene:
                    st.subheader("⚡ Termodinámica")
                    st.dataframe(res_df[['Temperature', 'Pressure']], use_container_width=True)

                # --- DIAGRAMA PFD ---
                st.subheader("🖼️ Diagrama de Proceso")
                st.image(sys.diagram(), use_container_width=True)

                # --- TUTOR IA ---
                st.divider()
                st.subheader("🤖 Análisis del Tutor IA (Gemini)")
                
                prompt = f"""
                Analiza esta simulación de destilación flash en BioSTEAM. 
                Entró {e_in} kmol/h de etanol. El producto final tiene una pureza molar de {frac_mol:.4f}. 
                El flash operó a {p_fla} Pa. 
                Explica brevemente y como tutor universitario si esta operación es eficiente y qué parámetro cambiarías para aumentar la pureza.
                """
                
                with st.chat_message("assistant"):
                    respuesta = get_ai_response(prompt)
                    st.write(respuesta)

        except Exception as e:
            st.error(f"⚠️ La simulación no convergió. Error técnico: {str(e)}")
else:
    with col_results:
        st.info("👈 Configura los parámetros en el panel izquierdo y ejecuta la simulación para visualizar los resultados.")
