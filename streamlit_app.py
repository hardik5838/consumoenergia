# Importar librerías
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import json
import requests

# --- Configuración de la página ---
st.set_page_config(
    page_title="Informe Anual de Energía - Asepeyo",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Constantes y Mapeos ---
CO2_FACTOR = 0.19 # Factor de emisión en tCO2e por MWh (toneladas de CO2 por megavatio-hora)

province_to_community = {
    'Almería': 'Andalucía', 'Cádiz': 'Andalucía', 'Córdoba': 'Andalucía', 'Granada': 'Andalucía',
    'Huelva': 'Andalucía', 'Jaén': 'Andalucía', 'Málaga': 'Andalucía', 'Sevilla': 'Andalucía',
    'Huesca': 'Aragón', 'Teruel': 'Aragón', 'Zaragoza': 'Aragón',
    'Asturias': 'Principado de Asturias',
    'Balears, Illes': 'Islas Baleares',
    'Araba/Álava': 'País Vasco', 'Bizkaia': 'País Vasco', 'Gipkoa': 'País Vasco',
    'Las Palmas': 'Canarias', 'Santa Cruz de Tenerife': 'Canarias',
    'Cantabria': 'Cantabria',
    'Ávila': 'Castilla y León', 'Burgos': 'Castilla y León', 'León': 'Castilla y León',
    'Palencia': 'Castilla y León', 'Salamanca': 'Castilla y León', 'Segovia': 'Castilla y León',
    'Soria': 'Castilla y León', 'Valladolid': 'Castilla y León', 'Zamora': 'Castilla y León',
    'Albacete': 'Castilla-La Mancha', 'Ciudad Real': 'Castilla-La Mancha', 'Cuenca': 'Castilla-La Mancha',
    'Guadalajara': 'Castilla-La Mancha', 'Toledo': 'Castilla-La Mancha',
    'Barcelona': 'Cataluña', 'Girona': 'Cataluña', 'Lleida': 'Cataluña', 'Tarragona': 'Cataluña',
    'Ceuta': 'Ceuta',
    'Badajoz': 'Extremadura', 'Cáceres': 'Extremadura',
    'Coruña, A': 'Galicia', 'Lugo': 'Galicia', 'Ourense': 'Galicia', 'Pontevedra': 'Galicia',
    'Rioja, La': 'La Rioja',
    'Madrid': 'Comunidad de Madrid',
    'Melilla': 'Melilla',
    'Murcia': 'Región de Murcia',
    'Navarra': 'Comunidad Foral de Navarra',
    'Valencia/València': 'Comunidad Valenciana', 'Alicante/Alacant': 'Comunidad Valenciana', 'Castellón': 'Comunidad Valenciana', 'Castellón/Castelló': 'Comunidad Valenciana'
}

def get_voltage_type(rate):
    if rate in ["6.1TD", "6.2TD", "6.3TD", "6.4TD"]: return "Alta Tensión"
    elif rate in ["2.0TD", "3.0TD"]: return "Baja Tensión"
    return "No definido"

# --- Funciones de Carga de Datos ---
@st.cache_data
def load_electricity_data(file_path):
    """Carga y procesa los datos de electricidad."""
    try:
        # --- AJUSTE: Determinar separador dinámicamente ---
        # Si el archivo es .tsv, usa una tabulación ('\t'). Si no, usa una coma (',').
        separator = '\t' if file_path.endswith('.tsv') else ','

        cols_to_use = [
            'CUPS', 'Estado de factura', 'Fecha desde', 'Provincia', 'Nombre suministro',
            'Tarifa de acceso', 'Consumo activa total (kWh)', 'Base imponible (€)',
            'Importe TE (€)', 'Importe TP (€)', 'Importe impuestos (€)', 'Importe alquiler (€)',
            'Importe otros conceptos (€)'
        ]
        # Añadimos el parámetro 'sep' a la función de lectura
        df = pd.read_csv(file_path, usecols=lambda c: c.strip() in cols_to_use, 
                         parse_dates=['Fecha desde'], decimal='.', thousands=',', sep=separator)
        
        df.columns = df.columns.str.strip()
        df = df[df['Estado de factura'].str.upper() == 'ACTIVA']
        df.rename(columns={
            'Nombre suministro': 'Centro', 'Base imponible (€)': 'Coste Total', 'Consumo activa total (kWh)': 'Consumo_kWh',
            'Importe TE (€)': 'Coste Energía', 'Importe TP (€)': 'Coste Potencia', 'Importe impuestos (€)': 'Coste Impuestos',
            'Importe alquiler (€)': 'Coste Alquiler', 'Importe otros conceptos (€)': 'Coste Otros'
        }, inplace=True)
        
        numeric_cols = ['Coste Total', 'Consumo_kWh', 'Coste Energía', 'Coste Potencia', 'Coste Impuestos', 'Coste Alquiler', 'Coste Otros']
        for col in numeric_cols: df[col] = pd.to_numeric(df[col], errors='coerce')
        df.fillna(0, inplace=True)
        
        df['Año'] = df['Fecha desde'].dt.year
        df['Mes'] = df['Fecha desde'].dt.month
        df['Comunidad Autónoma'] = df['Provincia'].map(province_to_community).astype('category')
        df['Tipo de Tensión'] = df['Tarifa de acceso'].apply(get_voltage_type).astype('category')
        df['Tipo de Energía'] = 'Electricidad'
        df.dropna(subset=['Comunidad Autónoma'], inplace=True)
        return df
    except Exception as e:
        st.error(f"Error al procesar el archivo de electricidad '{os.path.basename(file_path)}': {e}")
        return pd.DataFrame()

@st.cache_data
def load_gas_data(consumos_path, importes_path, year):
    """Carga, transforma y fusiona los datos de consumo y coste de gas."""
    try:
        # --- AJUSTE: Determinar separador dinámicamente para cada archivo ---
        sep_consumos = '\t' if consumos_path.endswith('.tsv') else ';'
        sep_importes = '\t' if importes_path.endswith('.tsv') else ';'

        # Usamos los separadores definidos
        df_consumos = pd.read_csv(consumos_path, skiprows=4, sep=sep_consumos, decimal='.', thousands=',')
        df_importes = pd.read_csv(importes_path, skiprows=4, sep=sep_importes, decimal='.', thousands=',')

        df_consumos.columns = df_consumos.columns.str.strip()
        df_importes.columns = df_importes.columns.str.strip()
        
        id_vars = ['Descripción', 'CUPS', 'Provincia']
        months_cols = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sept', 'oct', 'nov', 'dic']

        consumos_long = pd.melt(df_consumos, id_vars=id_vars, value_vars=months_cols, var_name='Mes_str', value_name='Consumo_kWh')
        importes_long = pd.melt(df_importes, id_vars=id_vars, value_vars=months_cols, var_name='Mes_str', value_name='Coste Total')
        
        df_gas = pd.merge(consumos_long, importes_long, on=['Descripción', 'CUPS', 'Provincia', 'Mes_str'])
        
        df_gas['Consumo_kWh'] = pd.to_numeric(df_gas['Consumo_kWh'], errors='coerce')
        df_gas['Coste Total'] = pd.to_numeric(df_gas['Coste Total'], errors='coerce')
        df_gas.fillna(0, inplace=True)

        month_map = {name: i+1 for i, name in enumerate(months_cols)}
        df_gas['Mes'] = df_gas['Mes_str'].map(month_map)
        df_gas['Año'] = year
        
        df_gas.rename(columns={'Descripción': 'Centro'}, inplace=True)
        df_gas['Tipo de Energía'] = 'Gas'
        df_gas['Comunidad Autónoma'] = df_gas['Provincia'].map(province_to_community).astype('category')

        df_gas.dropna(subset=['Comunidad Autónoma'], inplace=True)
        df_gas = df_gas[df_gas['Consumo_kWh'] > 0] 
        df_gas['Fecha desde'] = pd.to_datetime(df_gas['Año'].astype(str) + '-' + df_gas['Mes'].astype(str) + '-01')

        return df_gas[['Fecha desde', 'Centro', 'Provincia', 'Comunidad Autónoma', 'Consumo_kWh', 'Coste Total', 'Tipo de Energía', 'Año', 'Mes', 'CUPS']]
    except Exception as e:
        st.error(f"Error al procesar los archivos de gas: {e}")
        return pd.DataFrame()

@st.cache_data
def get_geojson():
    url = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/spain-communities.geojson"
    try:
        response = requests.get(url)
        return response.json()
    except Exception as e:
        st.error(f"No se pudo descargar el mapa. Error: {e}")
        return None

# --- BARRA LATERAL (FILTROS) ---
st.sidebar.image("Logo_ASEPEYO.png", width=200)
st.sidebar.title('Filtros de Análisis')

DATA_DIR = "Data/"
df_electricidad = pd.DataFrame()
df_gas = pd.DataFrame()
df_comparativa = pd.DataFrame()


try:
    # Modificamos la condición para que busque archivos que terminen en .csv O .tsv
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(('.csv', '.tsv'))]
    
    if not files:
        # Actualizamos el mensaje de advertencia para ser más claro
        st.sidebar.warning(f"No se encontraron archivos CSV o TSV en la carpeta '{DATA_DIR}'.")
        st.stop()
    
    st.sidebar.markdown("### 📂 Selección de Datos")
    col1, col2 = st.sidebar.columns(2)
    selected_file_electricidad = col1.selectbox("Electricidad (Actual)", files)
    
    # --- AÑADIDO: Selectores para archivos de gas ---
    gas_consumos_file = col1.selectbox("Gas Consumos (Opcional)", [None] + files)
    gas_importes_file = col2.selectbox("Gas Costes (Opcional)", [None] + files)
    
    comparar_anos = st.sidebar.toggle("Comparar con año anterior")
    if comparar_anos:
        selected_file_comparativa = col2.selectbox("Electricidad (Anterior)", files)
    
    # --- Carga de datos ---
    with st.spinner('Cargando datos...'):
        if selected_file_electricidad:
            path_elec = os.path.join(DATA_DIR, selected_file_electricidad)
            df_electricidad = load_electricity_data(path_elec)
        
        if gas_consumos_file and gas_importes_file:
            path_gas_consumos = os.path.join(DATA_DIR, gas_consumos_file)
            path_gas_importes = os.path.join(DATA_DIR, gas_importes_file)
            # Asumimos que el año de los archivos de gas es el mismo que el de electricidad
            if not df_electricidad.empty:
                gas_year = df_electricidad['Año'].iloc[0]
                df_gas = load_gas_data(path_gas_consumos, path_gas_importes, gas_year)
        
        if comparar_anos and selected_file_comparativa:
            path_comp = os.path.join(DATA_DIR, selected_file_comparativa)
            df_comparativa = load_electricity_data(path_comp)

except Exception as e:
    st.sidebar.error(f"Ocurrió un error en la carga de archivos: {e}")
    st.stop()

# --- Combinar datos de Electricidad y Gas ---
df_combined = pd.concat([df_electricidad, df_gas], ignore_index=True)

if not df_combined.empty:
    st.sidebar.markdown("### 📅 Filtro Temporal")
    selected_year = st.sidebar.selectbox('Seleccionar Año', sorted(df_combined['Año'].unique(), reverse=True))
    time_aggregation = st.sidebar.radio("Vista Temporal", ('Mensual', 'Acumulada Anual'), horizontal=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💡 Filtro de Energía")
    energy_types = ['Ambos'] + sorted(df_combined['Tipo de Energía'].unique().tolist())
    selected_energy_type = st.sidebar.selectbox("Tipo de Energía", energy_types)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🌍 Filtro Geográfico")
    lista_comunidades = sorted(df_combined['Comunidad Autónoma'].unique().tolist())
    selected_communities = st.sidebar.multiselect('Seleccionar Comunidades', lista_comunidades, default=lista_comunidades)
    
    st.sidebar.markdown("### 🔬 Filtro por Centro")
    vista_por_centro = st.sidebar.toggle('Activar filtro por Centro')
    selected_centros = []
    if vista_por_centro:
        centros_disponibles = sorted(df_combined[df_combined['Comunidad Autónoma'].isin(selected_communities)]['Centro'].unique().tolist())
        if centros_disponibles:
            selected_centros = st.sidebar.multiselect('Seleccionar Centros', centros_disponibles, default=centros_disponibles)
        else:
            st.sidebar.warning("No hay centros para las comunidades seleccionadas.")
            
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚡ Filtro de Tensión (Electricidad)")
    tension_types = sorted(df_electricidad['Tipo de Tensión'].unique().tolist())
    selected_tension = st.sidebar.multiselect('Tipo de Tensión', tension_types, default=tension_types)

# --- Lógica de la Aplicación Principal ---
if not df_combined.empty:
    
    # Aplicar filtros
    df_filtered = df_combined[
        (df_combined['Año'] == selected_year) &
        (df_combined['Comunidad Autónoma'].isin(selected_communities))
    ].copy()

    if selected_energy_type != 'Ambos':
        df_filtered = df_filtered[df_filtered['Tipo de Energía'] == selected_energy_type]
    
    # El filtro de tensión solo aplica a la electricidad
    if 'Tipo de Tensión' in df_filtered.columns:
        df_electricidad_filtered = df_filtered[df_filtered['Tipo de Energía'] == 'Electricidad']
        df_gas_filtered = df_filtered[df_filtered['Tipo de Energía'] == 'Gas']
        df_electricidad_filtered = df_electricidad_filtered[df_electricidad_filtered['Tipo de Tensión'].isin(selected_tension)]
        df_filtered = pd.concat([df_electricidad_filtered, df_gas_filtered])

    if vista_por_centro and selected_centros:
        df_filtered = df_filtered[df_filtered['Centro'].isin(selected_centros)]
    
    # --- KPIs ---
    st.title(f"Informe Energético Anual - {selected_year}")
    st.markdown("---")

    if not df_filtered.empty:
        kwh_elec = df_filtered[df_filtered['Tipo de Energía'] == 'Electricidad']['Consumo_kWh'].sum()
        cost_elec = df_filtered[df_filtered['Tipo de Energía'] == 'Electricidad']['Coste Total'].sum()
        kwh_gas = df_filtered[df_filtered['Tipo de Energía'] == 'Gas']['Consumo_kWh'].sum()
        cost_gas = df_filtered[df_filtered['Tipo de Energía'] == 'Gas']['Coste Total'].sum()
        
        total_kwh = kwh_elec + kwh_gas
        total_cost = cost_elec + cost_gas
        num_suministros = df_filtered['CUPS'].nunique()
        emisiones_co2 = (kwh_elec * CO2_FACTOR) / 1000 # Solo calculamos emisiones para electricidad
        coste_medio = total_cost / total_kwh if total_kwh > 0 else 0

        st.subheader("Indicadores Energéticos Globales")
        kpi_main1, kpi_main2, kpi_main3, kpi_main4 = st.columns(4)
        kpi_main1.metric("Consumo Energético TOTAL", f"{total_kwh:,.0f} kWh")
        kpi_main2.metric("Coste Energético TOTAL", f"€ {total_cost:,.2f}")
        kpi_main3.metric("Emisiones CO₂ (Eléctricas)", f"{emisiones_co2:,.2f} tCO₂e")
        kpi_main4.metric("Nº Suministros Activos", f"{num_suministros}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        kpi_sub1, kpi_sub2, kpi_sub3, kpi_sub4, kpi_sub5 = st.columns(5)
        kpi_sub1.metric("Consumo Eléctrico", f"{kwh_elec:,.0f} kWh")
        kpi_sub2.metric("Coste Eléctrico", f"€ {cost_elec:,.2f}")
        kpi_sub3.metric("Consumo Gas", f"{kwh_gas:,.0f} kWh")
        kpi_sub4.metric("Coste Gas", f"€ {cost_gas:,.2f}")
        kpi_sub5.metric("Coste Medio Total", f"€ {coste_medio:.3f}/kWh")
        st.markdown("---")

        # --- Cuerpo del Dashboard ---
        columna_agrupar = 'Centro' if vista_por_centro and selected_centros else 'Comunidad Autónoma'
        
        # --- Desglose de Costes y Mapa ---
        st.subheader(f"Análisis Geográfico y Desglose de Costes")
        map_col, cost_col = st.columns([0.6, 0.4])
        with cost_col:
            st.markdown(f"**Desglose de Costes Eléctricos**")
            cost_components = ['Coste Energía', 'Coste Potencia', 'Coste Impuestos', 'Coste Alquiler', 'Coste Otros']
            df_elec_costs = df_filtered[df_filtered['Tipo de Energía'] == 'Electricidad']
            cost_breakdown = df_elec_costs[cost_components].sum().reset_index()
            cost_breakdown.columns = ['Componente', 'Coste']
            fig_cost_pie = px.pie(cost_breakdown, names='Componente', values='Coste', hole=0.4)
            st.plotly_chart(fig_cost_pie, use_container_width=True)

        with map_col:
            geojson = get_geojson()
            if geojson:
                df_map = df_filtered.groupby('Comunidad Autónoma')['Consumo_kWh'].sum().reset_index()
                map_name_to_geojson_name = {"Principado de Asturias": "Asturias", "Islas Baleares": "Illes Balears", "País Vasco": "País Vasco / Euskadi", "Comunidad Foral de Navarra": "Navarra"}
                df_map['Comunidad Autónoma'] = df_map['Comunidad Autónoma'].replace(map_name_to_geojson_name)
                
                fig_map = px.choropleth_mapbox(df_map, geojson=geojson, locations='Comunidad Autónoma',
                                               featureidkey="properties.name", color='Consumo_kWh',
                                               color_continuous_scale="Viridis", mapbox_style="carto-positron",
                                               zoom=4.5, center={"lat": 40.4168, "lon": -3.7038},
                                               title="Consumo Energético Total por Comunidad Autónoma")
                st.plotly_chart(fig_map, use_container_width=True)

        st.markdown("---")

        # --- Evolución y Comparativas ---
        st.subheader("Análisis Detallado y Evolución")
        col1, col2 = st.columns(2, gap="large")
        with col1:
            st.markdown(f"**Consumo por {columna_agrupar} y Tipo de Energía**")
            df_grouped_energy = df_filtered.groupby([columna_agrupar, 'Tipo de Energía'])['Consumo_kWh'].sum().reset_index()
            fig_bar_energy = px.bar(df_grouped_energy.sort_values(by='Consumo_kWh', ascending=False),
                                    x=columna_agrupar, y='Consumo_kWh', color='Tipo de Energía', barmode='stack')
            fig_bar_energy.update_layout(xaxis={'categoryorder':'total descending'})
            st.plotly_chart(fig_bar_energy, use_container_width=True)
            
        with col2:
            st.markdown("**Evolución Mensual del Consumo**")
            df_monthly = df_filtered.groupby(['Mes', 'Tipo de Energía'])['Consumo_kWh'].sum().reset_index()
            df_monthly['Mes_str'] = df_monthly['Mes'].apply(lambda x: pd.to_datetime(f'{selected_year}-{x}-01').strftime('%b'))
            
            fig_line = px.line(df_monthly, x='Mes_str', y='Consumo_kWh', color='Tipo de Energía',
                               title="Consumo Mensual por Tipo de Energía", markers=True,
                               category_orders={"Mes_str": ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]})
            st.plotly_chart(fig_line, use_container_width=True)

        # --- Comparativa Anual ---
        if comparar_anos and not df_comparativa.empty and not df_filtered.empty:
            st.markdown("---")
            st.subheader("Comparativa Anual de Electricidad")
            df_comp_filtered = df_comparativa[(df_comparativa['Comunidad Autónoma'].isin(selected_communities)) & (df_comparativa['Tipo de Tensión'].isin(selected_tension))]
            if vista_por_centro and selected_centros:
                df_comp_filtered = df_comp_filtered[df_comp_filtered['Centro'].isin(selected_centros)]

            if not df_comp_filtered.empty:
                prev_year = df_comp_filtered['Año'].unique()[0]
                df_current_year_monthly = df_filtered[df_filtered['Tipo de Energía'] == 'Electricidad'].groupby('Mes')['Consumo Eléctrico'].sum()
                df_prev_year_monthly = df_comp_filtered.groupby('Mes')['Consumo Eléctrico'].sum()
                
                comparison_df = pd.DataFrame({
                    str(selected_year): df_current_year_monthly,
                    str(prev_year): df_prev_year_monthly
                }).reset_index()
                comparison_df['Mes'] = comparison_df['Mes'].apply(lambda x: pd.to_datetime(f'2024-{x}-01').strftime('%b'))
                
                fig_comp = px.bar(comparison_df, x='Mes', y=[str(selected_year), str(prev_year)], barmode='group',
                                  title=f'Comparativa de Consumo Mensual: {selected_year} vs. {prev_year}',
                                  labels={'value': 'Consumo Eléctrico (kWh)'})
                st.plotly_chart(fig_comp, use_container_width=True)

    else:
        st.warning("No hay datos disponibles para la selección de filtros actual.")
else:
    st.error("No se pudo cargar el archivo de datos de electricidad. Por favor, selecciona un archivo válido.")

