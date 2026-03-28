import streamlit as st
import pandas as pd

# --- PARCHE DE COMPATIBILIDAD ---
import sys
try:
    import altair as alt
    if not hasattr(alt, 'vegalite'):
        sys.modules['altair.vegalite.v4'] = alt
except:
    pass

# --- IMPORTACIONES CIENTÍFICAS ---
try:
    import biosteam as bst
    import thermosteam as tmo
    import google.generativeai as genai
    LIBS_OK = True
except Exception as e:
    LIBS_OK = False
    ERR_DETAIL = str(e)

# Configuración de página
st.set_page_config(page_title="BioSTEAM Hub", layout="wide")

if not LIBS_OK:
    st.error(f"Error de librerías: {ERR_DETAIL}")
    st.stop()

# --- LÓGICA DE SIMULACIÓN ---
def run_simulation(w_f, e_f, p_f):
    bst.main_flowsheet.clear()
    chemicals = tmo.Chemicals(["Water", "Ethanol"])
    bst.settings.set_thermo(chemicals)
    
    # Definición simplificada para evitar errores de convergencia rápidos
    mosto = bst.Stream("Mosto", Water=w_f, Ethanol=e_f, units="kmol/h", T=298.15)
    V1 = bst.Flash("V1", ins=mosto, outs=("Vapor", "Liquido"), P=p_f, Q=0)
    
    # Crear sistema
    sys_model = bst.System("Planta", path=(V1,))
    sys_model.simulate()
    return sys_model, V1

# --- INTERFAZ ---
st.title("🧪 Planta de Separación BioSTEAM")

col_in, col_out = st.columns([1, 2])

with col_in:
    st.header("Configuración")
    f_w = st.slider("Agua (kmol/h)", 10, 100, 43)
    f_e = st.slider("Etanol (kmol/h)", 1, 20, 5)
    pres = st.number_input("Presión (Pa)", value=101325)
    run = st.button("🚀 Ejecutar Simulación", use_container_width=True)

if run:
    try:
        sys_res, v1_res = run_simulation(f_w, f_e, pres)
        
        with col_out:
            # 1. KPIs
            k1, k2 = st.columns(2)
            k1.metric("Pureza Etanol (Vapor)", f"{v1_res.outs[0].get_molar_fraction('Ethanol'):.4f}")
            k2.metric("Flujo Vapor", f"{v1_res.outs[0].F_mass:.2f} kg/h")
            
            # 2. Diagrama (Aquí ocurría el error .format)
            st.subheader("🖼️ Diagrama de Proceso")
            try:
                # Intentamos generar el diagrama
                pfd = sys_res.diagram(display=False)
                if pfd is not None:
                    st.image(pfd)
                else:
                    st.warning("⚠️ El motor de BioSTEAM no pudo generar la imagen del diagrama.")
            except Exception as diag_err:
                st.info("ℹ️ No se pudo renderizar el PFD. Revisa si 'graphviz' está en packages.txt.")

            # 3. Tablas
            st.subheader("📊 Resultados de Corrientes")
            st.dataframe(sys_res.get_results().T, use_container_width=True)
            
    except Exception as ex:
        st.error(f"Fallo en la corrida: {ex}")
