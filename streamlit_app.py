# Importar librerías
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import json
import requests # Necesaria para descargar el mapa GeoJSON

# --- Configuración de la página ---
st.set_page_config(
    page_title="Informe Anual de Energía - Asepeyo",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Constantes y Mapeos ---
CO2_FACTOR = 0.19 # Factor de emisión en tCO2e por MWh. Fuente: REE (Red Eléctrica de España), valor aproximado para 2023/2024.

province_to_community = {
    'Almería': 'Andalucía', 'Cádiz': 'Andalucía', 'Córdoba': 'Andalucía', 'Granada': 'Andalucía',
    'Huelva': 'Andalucía', 'Jaén': 'Andalucía', 'Málaga': 'Andalucía', 'Sevilla': 'Andalucía',
    'Huesca': 'Aragón', 'Teruel': 'Aragón', 'Zaragoza': 'Aragón',
    'Asturias': 'Principado de Asturias',
    'Balears, Illes': 'Islas Baleares',
    'Araba/Álava': 'País Vasco', 'Bizkaia': 'País Vasco', 'Gipuzkoa': 'País Vasco',
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

# --- Carga y Procesamiento de Datos ---
@st.cache_data
def load_data(file_path):
    try:
        cols_to_use = [
            'CUPS', 'Estado de factura', 'Fecha desde', 'Provincia', 'Nombre suministro',
            'Tarifa de acceso', 'Consumo activa total (kWh)', 'Base imponible (€)',
            'Importe TE (€)', 'Importe TP (€)', 'Importe impuestos (€)', 'Importe alquiler (€)',
            'Importe otros conceptos (€)'
        ]
        df = pd.read_csv(file_path, usecols=lambda c: c.strip() in cols_to_use, parse_dates=['Fecha desde'], decimal='.', thousands=',')
        df.columns = df.columns.str.strip()
        
        df = df[df['Estado de factura'].str.upper() == 'ACTIVA']
        df.rename(columns={
            'Nombre suministro': 'Centro', 'Base imponible (€)': 'Coste Total', 'Consumo activa total (kWh)': 'Consumo Eléctrico',
            'Importe TE (€)': 'Coste Energía', 'Importe TP (€)': 'Coste Potencia', 'Importe impuestos (€)': 'Coste Impuestos',
            'Importe alquiler (€)': 'Coste Alquiler', 'Importe otros conceptos (€)': 'Coste Otros'
        }, inplace=True)
        
        numeric_cols = ['Coste Total', 'Consumo Eléctrico', 'Coste Energía', 'Coste Potencia', 'Coste Impuestos', 'Coste Alquiler', 'Coste Otros']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.fillna(0, inplace=True)
        
        df['Año'] = df['Fecha desde'].dt.year
        df['Mes'] = df['Fecha desde'].dt.month
        df['Comunidad Autónoma'] = df['Provincia'].map(province_to_community).astype('category')
        df['Tipo de Tensión'] = df['Tarifa de acceso'].apply(get_voltage_type).astype('category')
        df.dropna(subset=['Comunidad Autónoma'], inplace=True)
        return df
    except Exception as e:
        st.error(f"Error al cargar o procesar el archivo '{os.path.basename(file_path)}': {e}")
        return pd.DataFrame()

@st.cache_data
def get_geojson():
    url = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/spain-communities.geojson"
    response = requests.get(url)
    return response.json()

# --- Barra Lateral (Filtros) ---
st.sidebar.image("Logo_ASEPEYO.png", width=200)
st.sidebar.title('Filtros de Análisis')

DATA_DIR = "Data/"
df_electricidad = pd.DataFrame()
df_gas = pd.DataFrame()
df_comparativa = pd.DataFrame()

try:
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    if not files:
        st.sidebar.warning(f"No se encontraron archivos CSV en la carpeta '{DATA_DIR}'.")
        st.stop()
    
    # --- Selección de archivos ---
    st.sidebar.markdown("### 📂 Selección de Datos")
    selected_file_electricidad = st.sidebar.selectbox("Archivo de Electricidad (Año Actual)", files)
    
    # Placeholder para el archivo de gas
    # selected_file_gas = st.sidebar.selectbox("Archivo de Gas (Opcional)", [None] + files)
    
    comparar_anos = st.sidebar.toggle("Comparar con año anterior")
    if comparar_anos:
        selected_file_comparativa = st.sidebar.selectbox("Archivo de Electricidad (Año Anterior)", files)
    
    file_path_electricidad = os.path.join(DATA_DIR, selected_file_electricidad)
    with st.spinner('Cargando datos actuales...'):
        df_electricidad = load_data(file_path_electricidad)
    
    if comparar_anos and selected_file_comparativa:
        file_path_comparativa = os.path.join(DATA_DIR, selected_file_comparativa)
        with st.spinner('Cargando datos de comparación...'):
            df_comparativa = load_data(file_path_comparativa)

except FileNotFoundError:
    st.sidebar.error(f"El directorio '{DATA_DIR}' no fue encontrado.")
    st.stop()

if not df_electricidad.empty:
    st.sidebar.markdown("### 📅 Filtro Temporal")
    selected_year = st.sidebar.selectbox('Seleccionar Año', sorted(df_electricidad['Año'].unique(), reverse=True))
    time_aggregation = st.sidebar.radio("Vista Temporal", ('Mensual', 'Acumulada Anual'), horizontal=True)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🌍 Filtro Geográfico")
    
    lista_comunidades = sorted(df_electricidad['Comunidad Autónoma'].unique().tolist())
    selected_communities = st.sidebar.multiselect('Seleccionar Comunidades', lista_comunidades, default=lista_comunidades)
    
    st.sidebar.markdown("### 🔬 Filtro por Centro")
    vista_por_centro = st.sidebar.toggle('Activar filtro por Centro')
    selected_centros = []
    if vista_por_centro:
        centros_disponibles = sorted(df_electricidad[df_electricidad['Comunidad Autónoma'].isin(selected_communities)]['Centro'].unique().tolist())
        if centros_disponibles:
            selected_centros = st.sidebar.multiselect('Seleccionar Centros', centros_disponibles, default=centros_disponibles)
        else:
            st.sidebar.warning("No hay centros para las comunidades seleccionadas.")
            
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚡ Otros Filtros")
    tension_types = sorted(df_electricidad['Tipo de Tensión'].unique().tolist())
    selected_tension = st.sidebar.multiselect('Tipo de Tensión', tension_types, default=tension_types)

# --- Lógica de la Aplicación Principal ---
if not df_electricidad.empty:
    
    # Filtrado de datos del año actual
    df_filtered = df_electricidad[(df_electricidad['Año'] == selected_year) & (df_electricidad['Comunidad Autónoma'].isin(selected_communities)) & (df_electricidad['Tipo de Tensión'].isin(selected_tension))].copy()
    if vista_por_centro and selected_centros:
        df_filtered = df_filtered[df_filtered['Centro'].isin(selected_centros)]
    
    # --- KPIs ---
    st.title(f"Informe Energético Anual - {selected_year}")
    
    kwh_elec = df_filtered['Consumo Eléctrico'].sum()
    cost_elec = df_filtered['Coste Total'].sum()
    kwh_gas = 0 # Placeholder
    cost_gas = 0 # Placeholder
    total_kwh = kwh_elec + kwh_gas
    total_cost = cost_elec + cost_gas
    num_suministros = df_filtered['CUPS'].nunique()
    emisiones_co2 = (kwh_elec * CO2_FACTOR) / 1000 # tCO2e
    coste_medio = total_cost / total_kwh if total_kwh > 0 else 0

    st.subheader("Indicadores Energéticos Globales")
    kpi_main1, kpi_main2, kpi_main3, kpi_main4 = st.columns(4)
    kpi_main1.metric("Consumo Energético Total", f"{total_kwh:,.0f} kWh")
    kpi_main2.metric("Coste Energético Total", f"€ {total_cost:,.2f}")
    kpi_main3.metric("Emisiones CO₂", f"{emisiones_co2:,.2f} tCO₂e")
    kpi_main4.metric("Nº Suministros Activos", f"{num_suministros}")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    kpi_sub1, kpi_sub2, kpi_sub3, kpi_sub4, kpi_sub5 = st.columns(5)
    kpi_sub1.metric("Consumo Eléctrico", f"{kwh_elec:,.0f} kWh")
    kpi_sub2.metric("Coste Eléctrico", f"€ {cost_elec:,.2f}")
    kpi_sub3.metric("Consumo Gas", "N/A")
    kpi_sub4.metric("Coste Gas", "N/A")
    kpi_sub5.metric("Coste Medio", f"€ {coste_medio:.3f}/kWh")
    st.markdown("---")
    
    # --- Cuerpo del Dashboard ---
    if not df_filtered.empty:
        # Lógica de Agregación
        columna_agrupar = 'Centro' if vista_por_centro and selected_centros else 'Provincia'
        
        # --- Desglose de Costes y Mapa Geográfico ---
        st.subheader("Análisis de Costes y Distribución Geográfica")
        map_col, cost_col = st.columns([0.6, 0.4])
        with cost_col:
            cost_components = ['Coste Energía', 'Coste Potencia', 'Coste Impuestos', 'Coste Alquiler', 'Coste Otros']
            cost_breakdown = df_filtered[cost_components].sum().reset_index()
            cost_breakdown.columns = ['Componente', 'Coste']
            fig_cost_pie = px.pie(cost_breakdown, names='Componente', values='Coste', title='Desglose de Costes Eléctricos', hole=0.4)
            st.plotly_chart(fig_cost_pie, use_container_width=True)

         with map_col:
            geojson = get_geojson()
            df_map = df_filtered.groupby('Comunidad Autónoma')['Consumo Eléctrico'].sum().reset_index()

            # --- CÓDIGO AÑADIDO: Mapeo de nombres para el mapa ---
            # Este diccionario "traduce" nuestros nombres a los que el archivo GeoJSON espera.
            map_name_to_geojson_name = {
                "Principado de Asturias": "Asturias",
                "Islas Baleares": "Illes Balears",
                "País Vasco": "País Vasco / Euskadi",
                "Comunidad Foral de Navarra": "Navarra",
                "Comunidad Valenciana": "Comunidad Valenciana", # Aseguramos que se mantenga el nombre correcto
                "Región de Murcia": "Región de Murcia" # Aseguramos que se mantenga el nombre correcto
            }
            # Aplicamos el mapeo a la columna que usará el gráfico.
            df_map['Comunidad Autónoma'] = df_map['Comunidad Autónoma'].replace(map_name_to_geojson_name)
            # --- FIN DEL CÓDIGO AÑADIDO ---
            
            fig_map = px.choropleth_mapbox(df_map, geojson=geojson, locations='Comunidad Autónoma',
                                           featureidkey="properties.name",
                                           color='Consumo Eléctrico',
                                           color_continuous_scale="Viridis",
                                           mapbox_style="carto-positron",
                                           zoom=4.5, center = {"lat": 40.4168, "lon": -3.7038},
                                           title="Consumo Eléctrico por Comunidad Autónoma")
            st.plotly_chart(fig_map, use_container_width=True)

        st.markdown("---")

        # --- Evolución y Comparativas ---
        st.subheader(f"Análisis por {columna_agrupar} y Evolución Mensual")
        col1, col2 = st.columns(2, gap="large")
        with col1:
            df_grouped = df_filtered.groupby(columna_agrupar)[['Consumo Eléctrico', 'Coste Total']].sum().reset_index()
            fig_bar = px.bar(df_grouped.sort_values(by='Consumo Eléctrico', ascending=False),
                             x=columna_agrupar, y='Consumo Eléctrico', title=f'Consumo por {columna_agrupar}')
            st.plotly_chart(fig_bar, use_container_width=True)
            
            df_cost_unit = df_filtered.groupby('Mes')['Coste Total'].sum() / df_filtered.groupby('Mes')['Consumo Eléctrico'].sum()
            df_cost_unit = df_cost_unit.reset_index(name='Coste Medio €/kWh').sort_values('Mes')
            df_cost_unit['Mes'] = df_cost_unit['Mes'].apply(lambda x: pd.to_datetime(f'{selected_year}-{x}-01').strftime('%b'))
            fig_line_cost = px.line(df_cost_unit, x='Mes', y='Coste Medio €/kWh', title='Evolución Mensual del Coste Medio', markers=True)
            st.plotly_chart(fig_line_cost, use_container_width=True)


        with col2:
            df_monthly = df_filtered.groupby('Mes')[['Consumo Eléctrico', 'Coste Total']].sum().reset_index()
            df_monthly['Mes'] = df_monthly['Mes'].apply(lambda x: pd.to_datetime(f'{selected_year}-{x}-01').strftime('%b'))
            
            fig_line = go.Figure()
            fig_line.add_trace(go.Bar(x=df_monthly['Mes'], y=df_monthly['Consumo Eléctrico'], name='Consumo (kWh)', marker_color='lightblue'))
            fig_line.add_trace(go.Scatter(x=df_monthly['Mes'], y=df_monthly['Coste Total'], name='Coste (€)', mode='lines+markers', yaxis='y2', marker_color='orange'))
            fig_line.update_layout(title="Evolución Mensual (Consumo vs Coste)", yaxis=dict(title='Consumo (kWh)'), yaxis2=dict(title='Coste (€)', overlaying='y', side='right'), template="plotly_white")
            st.plotly_chart(fig_line, use_container_width=True)
            
            st.markdown("##### Top 10 Centros con Mayor Impacto")
            sort_by = st.radio("Ordenar por:", ('Consumo', 'Coste'), horizontal=True, key="top10_sort")
            sort_col = 'Consumo Eléctrico' if sort_by == 'Consumo' else 'Coste Total'
            top_10 = df_filtered.groupby('Centro')[sort_col].sum().nlargest(10).sort_values(ascending=True).reset_index()
            fig_top10 = px.bar(top_10, x=sort_col, y='Centro', orientation='h', text_auto=True)
            fig_top10.update_layout(yaxis={'categoryorder':'total ascending'}, yaxis_title=None)
            st.plotly_chart(fig_top10, use_container_width=True)
        
        # --- Sección de Comparativa Anual (si aplica) ---
        if comparar_anos and not df_comparativa.empty:
            st.markdown("---")
            st.subheader("Comparativa Anual")
            df_comp_filtered = df_comparativa[
                (df_comparativa['Comunidad Autónoma'].isin(selected_communities)) & 
                (df_comparativa['Tipo de Tensión'].isin(selected_tension))
            ]
            if vista_por_centro and selected_centros:
                df_comp_filtered = df_comp_filtered[df_comp_filtered['Centro'].isin(selected_centros)]

            if not df_comp_filtered.empty:
                df_current_year = df_filtered.groupby('Mes')['Consumo Eléctrico'].sum().reset_index()
                df_current_year['Año'] = str(selected_year)
                
                prev_year = df_comp_filtered['Año'].unique()[0]
                df_prev_year = df_comp_filtered.groupby('Mes')['Consumo Eléctrico'].sum().reset_index()
                df_prev_year['Año'] = str(prev_year)
                
                df_comparison = pd.concat([df_current_year, df_prev_year])
                df_comparison['Mes'] = df_comparison['Mes'].apply(lambda x: pd.to_datetime(f'2024-{x}-01').strftime('%b'))

                fig_comp = px.bar(df_comparison, x='Mes', y='Consumo Eléctrico', color='Año', barmode='group',
                                  title=f'Comparativa de Consumo Mensual: {selected_year} vs. {prev_year}')
                st.plotly_chart(fig_comp, use_container_width=True)
            else:
                st.warning("No hay datos de comparación disponibles para los filtros seleccionados.")

    else:
        st.warning("No hay datos disponibles para la selección de filtros actual.")
else:
    st.error("No se pudo cargar el archivo de datos principal. Por favor, revisa la configuración en la barra lateral.")
