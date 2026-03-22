import streamlit as st
import pandas as pd
import os

# ==========================================================
# 1. CONFIGURACIÓN DE LA PÁGINA (Debe ser la primera línea)
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

# ==========================================================
# 2. CARGA SEGURA DE DEPENDENCIAS CIENTÍFICAS
# ==========================================================
# Envolvemos las importaciones pesadas para evitar que la app colapse 
# si hay errores de compilación en el servidor de Streamlit.
try:
    import thermosteam as tmo
    import biosteam as bst
    LIBS_OK = True
except Exception as e:
    LIBS_OK = False
    ERROR_DETALLE = str(e)

try:
    import google.generativeai as genai
    IA_OK = True
except:
    IA_OK = False

# Función del Tutor IA
def get_ai_response(prompt_text):
    if not IA_OK:
        return "⚠️ Librería de Google no instalada."
    try:
        if "GEMINI_API_KEY" in st.secrets:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt_text)
            return response.text
        else:
            return "⚠️ API Key no detectada. Configura GEMINI_API_KEY en los Secrets."
    except Exception as e:
        return f"❌ Error de IA: {str(e)}"

# ==========================================================
# 3. INTERFAZ PRINCIPAL
# ==========================================================
st.title("🧪 Simulador BioSTEAM + IA Tutor")
st.markdown("---")

# Si las librerías fallaron, mostramos el error elegante y detenemos la ejecución
if not LIBS_OK:
    st.error("🚨 Error crítico al cargar el motor termodinámico de BioSTEAM.")
    st.warning("Esto suele deberse a la versión de Python en Streamlit Cloud.")
    st.code(f"Detalle técnico del servidor:\n{ERROR_DETALLE}", language="bash")
    st.stop() # Detiene la ejecución aquí para no mostrar errores de código más abajo

# ==========================================================
# 4. MOTOR DE CÁLCULO (Solo se ejecuta si las librerías cargaron bien)
# ==========================================================
def run_simulation(w_flow, e_flow, flash_p, t_input):
    bst.main_flowsheet.clear()
    
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)

    mosto = bst.Stream("1-Mosto", Water=w_flow, Ethanol=e_flow, units="kmol/h", 
                       T=t_input + 273.15, P=101325)
    vinazas_retorno = bst.Stream("Vinazas-Retorno", Water=w_flow, units="kmol/h", 
                                 T=90+273.15, P=300000)

    P100 = bst.Pump("P100", ins=mosto, P=4*101325)
    E100 = bst.HXprocess("E100", ins=(P100-0, vinazas_retorno), 
                         outs=("3-Mosto-Pre", "Drenaje"), phase0="g", phase1="L")
    E100.outs[0].T = 85 + 273.15
    E101 = bst.HXutility("E101", ins=E100-0, outs=("Mezcla"), T=95+273.15)
    V100 = bst.IsenthalpicValve("V100", ins=E101-0, outs="Mezcla-Bifasica", P=flash_p)
    V1 = bst.Flash("V1", ins=V100-0, outs=("Vapor_Caliente", "Vinazas"), P=flash_p, Q=0)
    E102 = bst.HXutility("E102", ins=V1-0, outs="Producto_Final", T=25+273.15)
    P200 = bst.Pump("P200", ins=V1-1, outs=vinazas_retorno, P=3*101325)

    sys = bst.System("Planta_Etanol", path=(P100, E100, E101, V100, V1, E102, P200))
    sys.simulate()
    
    return sys, e102

# ==========================================================
# 5. LAYOUT COLUMNAS Y RESULTADOS
# ==========================================================
col_input, col_results = st.columns([1, 3], gap="large")

with col_input:
    st.header("🎛️ Controles")
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
                m1, m2, m3 = st.columns(3)
                prod_kg = e102.outs[0].imass['Ethanol']
                frac_mol = e102.outs[0].get_molar_fraction('Ethanol')
                q_cond = abs(e102.design_results.get('Heat duty', 0)) / 1000
                
                m1.metric("Producción Etanol", f"{prod_kg:.2f} kg/h")
                m2.metric("Pureza (Frac. Molar)", f"{frac_mol:.4f}")
                m3.metric("Calor a Remover", f"{q_cond:.1f} MJ/h")
                
                st.divider()
                col_mat, col_ene = st.columns(2)
                res_df = sys.get_results().T
                
                with col_mat:
                    st.subheader("📦 Balance de Materia")
                    st.dataframe(res_df[['Flow']], use_container_width=True)
                with col_ene:
                    st.subheader("⚡ Termodinámica")
                    st.dataframe(res_df[['Temperature', 'Pressure']], use_container_width=True)

                st.subheader("🖼️ Diagrama de Proceso")
                st.image(sys.diagram(), use_container_width=True)

                st.divider()
                st.subheader("🤖 Análisis del Tutor IA (Gemini)")
                prompt = f"Analiza esta destilación flash. Entró {e_in} kmol/h de etanol. El producto tiene pureza {frac_mol:.4f} operando a {p_fla} Pa. ¿Es eficiente y qué cambiarías para aumentar la pureza?"
                
                with st.chat_message("assistant"):
                    st.write(get_ai_response(prompt))

        except Exception as e:
            st.error(f"⚠️ La simulación falló: {str(e)}")
else:
    with col_results:
        st.info("👈 Configura los parámetros y ejecuta la simulación.")
