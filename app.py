import streamlit as st
import sys

# 1. Configuración de página (SIEMPRE PRIMERO)
st.set_page_config(page_title="BioSTEAM Hub", layout="wide")

# 2. Intento de carga de librerías con diagnóstico
try:
    import thermosteam as tmo
    import biosteam as bst
    import google.generativeai as genai
    LIB_READY = True
except Exception as e:
    LIB_READY = False
    DETALLE_ERROR = str(e)

# 3. Interfaz de Usuario
st.title("🧪 Simulación de Procesos con BioSTEAM")

if not LIB_READY:
    st.error("❌ Error de compatibilidad en el servidor")
    st.markdown(f"""
    **Detalle del error:** `{DETALLE_ERROR}`
    
    **Causa probable:** Streamlit Cloud está usando una versión de Python demasiado nueva (3.12+). 
    
    **Solución:** 1. Asegúrate de tener el archivo `.python-version` en tu GitHub con el texto `3.11`.
    2. En el panel de Streamlit Cloud, ve a **Settings** -> **Delete App** y vuelve a crearla (esto limpia el caché de Python por completo).
    """)
    st.stop()

# 4. Función de Simulación (Si las librerías cargaron)
def ejecutar_planta(w_flow, e_flow, p_flash):
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    
    # ... (Resto del código de la planta que definimos antes) ...
    mosto = bst.Stream("Mosto", Water=w_flow, Ethanol=e_flow, units="kmol/h", T=298.15)
    V100 = bst.Flash("V1", ins=mosto, outs=("Vapor", "Liquido"), P=p_flash, Q=0)
    V100.simulate()
    return V100

# 5. Controles y Resultados
col1, col2 = st.columns([1, 2])
with col1:
    f_w = st.slider("Agua", 10, 100, 43)
    f_e = st.slider("Etanol", 1, 20, 5)
    p_f = st.number_input("Presión (Pa)", value=101325)
    btn = st.button("Simular")

if btn:
    res = ejecutar_planta(f_w, f_e, p_f)
    with col2:
        st.success("Simulación Exitosa")
        st.write(f"Pureza de Etanol en Vapor: {res.outs[0].get_molar_fraction('Ethanol'):.4f}")
        st.image(bst.main_flowsheet.diagram())
