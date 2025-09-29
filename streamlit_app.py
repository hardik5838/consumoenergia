# Importar librerías
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import json
import requests
import io
from thefuzz import process


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

@st.cache_data
def load_electricity_data(file_path):
    """Carga y procesa los datos de electricidad desde un archivo CSV o TSV."""
    try:
        separator = '\t' if file_path.endswith('.tsv') else ','
        # Para el archivo de gas, el separador podría ser ';'
        if 'gas' in os.path.basename(file_path).lower():
            separator = ';'
        
        cols_to_use = [
            'CUPS', 'Estado de factura', 'Fecha desde', 'Provincia', 'Nombre suministro',
            'Tarifa de acceso', 'Consumo activa total (kWh)', 'Base imponible (€)',
            'Importe TE (€)', 'Importe TP (€)', 'Importe impuestos (€)', 'Importe alquiler (€)',
            'Importe otros conceptos (€)'
        ]
        df = pd.read_csv(
            file_path,
            usecols=lambda c: c.strip() in cols_to_use,
            parse_dates=['Fecha desde'],
            decimal='.', thousands=',', sep=separator,
            dayfirst=True # Añadido para interpretar correctamente fechas como dd/mm/yyyy
        )

        df.columns = df.columns.str.strip()
        df = df[df['Estado de factura'].str.upper() == 'ACTIVA']
        df.rename(columns={
            'Nombre suministro': 'Centro', 'Base imponible (€)': 'Coste Total',
            'Consumo activa total (kWh)': 'Consumo_kWh', 'Importe TE (€)': 'Coste Energía',
            'Importe TP (€)': 'Coste Potencia', 'Importe impuestos (€)': 'Coste Impuestos',
            'Importe alquiler (€)': 'Coste Alquiler', 'Importe otros conceptos (€)': 'Coste Otros'
        }, inplace=True)

        numeric_cols = ['Coste Total', 'Consumo_kWh', 'Coste Energía', 'Coste Potencia',
                        'Coste Impuestos', 'Coste Alquiler', 'Coste Otros']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.fillna(0, inplace=True)

        df['Año'] = df['Fecha desde'].dt.year
        df['Mes'] = df['Fecha desde'].dt.month
        df['Comunidad Autónoma'] = df['Provincia'].map(province_to_community)
        df['Tipo de Tensión'] = df['Tarifa de acceso'].apply(get_voltage_type)
        df['Tipo de Energía'] = 'Electricidad'
        df.dropna(subset=['Comunidad Autónoma'], inplace=True)
        return df
    except Exception as e:
        st.error(f"Error procesando el archivo de electricidad '{os.path.basename(file_path)}': {e}")
        return pd.DataFrame()


# --- ¡FUNCIÓN ACTUALIZADA! ---
@st.cache_data
def load_gas_data(file_path):
    """Carga y procesa los datos de gas desde un único archivo CSV, de forma similar a la electricidad."""
    try:
        # Detecta el separador, asumiendo que puede ser coma, punto y coma o tabulador.
        with open(file_path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
            if ';' in first_line:
                separator = ';'
            elif ',' in first_line:
                separator = ','
            else:
                separator = '\t'

        # Columnas relevantes para el gas. 'Consumo' es el nombre genérico.
        cols_to_use = [
            'CUPS', 'Estado de factura', 'Fecha desde', 'Provincia', 'Nombre suministro',
            'Consumo', 'Base imponible (€)'
        ]
        df = pd.read_csv(
            file_path,
            usecols=lambda c: c.strip() in cols_to_use,
            parse_dates=['Fecha desde'],
            decimal=',', # A menudo los CSV españoles usan coma decimal
            thousands='.', # Y punto para los miles
            sep=separator,
            dayfirst=True # Importante para formato de fecha dd/mm/yyyy
        )

        df.columns = df.columns.str.strip()
        
        # Filtra por facturas activas
        if 'Estado de factura' in df.columns:
            df = df[df['Estado de factura'].str.upper() == 'ACTIVA']
            
        # Renombra columnas para estandarizar
        df.rename(columns={
            'Nombre suministro': 'Centro',
            'Base imponible (€)': 'Coste Total',
            'Consumo': 'Consumo_kWh' # Asume que la columna 'Consumo' está en kWh
        }, inplace=True)

        # Convierte a numérico y rellena NAs
        numeric_cols = ['Coste Total', 'Consumo_kWh']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace('.', '', regex=False).str.replace(',', '.', regex=False), errors='coerce')
        df.fillna(0, inplace=True)

        # Crea columnas adicionales
        df['Año'] = df['Fecha desde'].dt.year
        df['Mes'] = df['Fecha desde'].dt.month
        df['Comunidad Autónoma'] = df['Provincia'].map(province_to_community)
        df['Tipo de Energía'] = 'Gas'
        
        # Elimina filas sin comunidad autónoma asignada
        df.dropna(subset=['Comunidad Autónoma'], inplace=True)
        
        # Selecciona las columnas finales para mantener la consistencia
        final_cols = ['Fecha desde', 'Centro', 'Provincia', 'Comunidad Autónoma', 
                      'Consumo_kWh', 'Coste Total', 'Tipo de Energía', 'Año', 'Mes', 'CUPS']
        return df[final_cols]

    except Exception as e:
        st.error(f"Error procesando el archivo de gas '{os.path.basename(file_path)}': {e}")
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
    # Comprueba si el directorio de datos existe, si no, lo crea
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    files = [f for f in os.listdir(DATA_DIR) if f.endswith(('.csv', '.tsv'))]
    
    if not files:
        st.sidebar.warning(f"No se encontraron archivos CSV o TSV en la carpeta '{DATA_DIR}'.")
        st.info("Por favor, sube tus archivos de datos en la carpeta 'Data' para comenzar el análisis.")
        st.stop()
    
    # --- ¡SECCIÓN ACTUALIZADA! ---
    st.sidebar.markdown("### 📂 Selección de Datos")
    col1, col2 = st.sidebar.columns(2)
    selected_file_electricidad = col1.selectbox("Electricidad (Actual)", files, index=0 if files else None)
    
    # Selector único para el archivo de gas
    selected_file_gas = col1.selectbox("Gas (Actual)", [None] + files)
    
    comparar_anos = st.sidebar.toggle("Comparar con año anterior")
    if comparar_anos:
        selected_file_comparativa = col2.selectbox("Electricidad (Anterior)", files, index=0 if files else None)
    
    # --- ¡SECCIÓN ACTUALIZADA! ---
    # --- Carga de datos ---
    with st.spinner('Cargando datos...'):
        if selected_file_electricidad:
            path_elec = os.path.join(DATA_DIR, selected_file_electricidad)
            df_electricidad = load_electricity_data(path_elec)
        
        # Lógica de carga actualizada para gas
        if selected_file_gas:
            path_gas = os.path.join(DATA_DIR, selected_file_gas)
            df_gas = load_gas_data(path_gas)
        
        if comparar_anos and 'selected_file_comparativa' in locals() and selected_file_comparativa:
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
    # Solo muestra el filtro de tensión si hay datos de electricidad
    if not df_electricidad.empty:
        st.sidebar.markdown("### ⚡ Filtro de Tensión (Electricidad)")
        tension_types = sorted(df_electricidad['Tipo de Tensión'].unique().tolist())
        selected_tension = st.sidebar.multiselect('Tipo de Tensión', tension_types, default=tension_types)
    else:
        selected_tension = []


# --- Lógica de la Aplicación Principal ---
if not df_combined.empty:
    
    # Aplicar filtros
    df_filtered = df_combined[
        (df_combined['Año'] == selected_year) &
        (df_combined['Comunidad Autónoma'].isin(selected_communities))
    ].copy()

    if selected_energy_type != 'Ambos':
        df_filtered = df_filtered[df_filtered['Tipo de Energía'] == selected_energy_type]
    
    # Aplica filtro de tensión solo a la parte de electricidad
    if selected_tension:
        df_electricidad_filtered = df_filtered[df_filtered['Tipo de Energía'] == 'Electricidad']
        df_gas_filtered = df_filtered[df_filtered['Tipo de Energía'] == 'Gas']
        
        # Filtra solo si la columna 'Tipo de Tensión' existe para evitar errores
        if 'Tipo de Tensión' in df_electricidad_filtered.columns:
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
        emisiones_co2 = (kwh_elec * CO2_FACTOR) / 1000 
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
            
            # Asegurarse de que las columnas existen antes de sumar
            cost_components_exist = [col for col in cost_components if col in df_elec_costs.columns]
            if not df_elec_costs.empty and cost_components_exist:
                cost_breakdown = df_elec_costs[cost_components_exist].sum().reset_index()
                cost_breakdown.columns = ['Componente', 'Coste']
                fig_cost_pie = px.pie(cost_breakdown, names='Componente', values='Coste', hole=0.4)
                st.plotly_chart(fig_cost_pie, use_container_width=True)
            else:
                st.info("No hay datos de costes eléctricos para mostrar.")

        with map_col:
            st.markdown(f"**Análisis Geográfico por Consumo**")
            geojson = get_geojson()
            if geojson and not df_filtered.empty:
                geojson_names = list({f['properties']['name'] for f in geojson['features']})

                df_map = df_filtered.groupby('Comunidad Autónoma')['Consumo_kWh'].sum().reset_index()
                data_names = list(df_map['Comunidad Autónoma'].unique())

                name_mapping = {}
                for data_name in data_names:
                    match = process.extractOne(data_name, geojson_names)
                    if match and match[1] > 80: # Umbral de coincidencia
                        name_mapping[data_name] = match[0]

                df_map['location_key'] = df_map['Comunidad Autónoma'].map(name_mapping)
                df_map.dropna(subset=['location_key'], inplace=True)

                if not df_map.empty:
                    fig_map = px.choropleth_mapbox(df_map,
                                                   geojson=geojson,
                                                   locations='location_key',
                                                   featureidkey="properties.name",
                                                   color='Consumo_kWh',
                                                   color_continuous_scale="Viridis",
                                                   mapbox_style="carto-positron",
                                                   zoom=4.5, center={"lat": 40.4168, "lon": -3.7038},
                                                   title="Consumo por Comunidad Autónoma")
                    st.plotly_chart(fig_map, use_container_width=True)
                else:
                    st.warning("No se pudieron mapear los datos geográficos.")

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

            tipos_energia_esperados = ['Electricidad', 'Gas']
            fechas_del_ano = pd.to_datetime([f'{selected_year}-{m}-01' for m in range(1, 13)])
            
            plantilla_completa = pd.MultiIndex.from_product(
                [fechas_del_ano, tipos_energia_esperados],
                names=['Fecha', 'Tipo de Energía']
            ).to_frame(index=False)

            df_chart_source = df_filtered[df_filtered['Año'] == selected_year].copy()

            if not df_chart_source.empty:
                df_chart_source['Fecha'] = pd.to_datetime(df_chart_source['Año'].astype(str) + '-' + df_chart_source['Mes'].astype(str) + '-01')
                df_consumo_real = df_chart_source.groupby(['Fecha', 'Tipo de Energía'])['Consumo_kWh'].sum().reset_index()

                df_to_plot = pd.merge(plantilla_completa, df_consumo_real, on=['Fecha', 'Tipo de Energía'], how='left').fillna(0)
                
                fig_line = px.line(df_to_plot,
                                   x='Fecha',
                                   y='Consumo_kWh',
                                   color='Tipo de Energía',
                                   title="Consumo Mensual por Tipo de Energía",
                                   markers=True,
                                   labels={'Fecha': 'Mes', 'Consumo_kWh': 'Consumo (kWh)'})

                fig_line.update_xaxes(dtick="M1", tickformat="%b", range=[f'{selected_year}-01-01', f'{selected_year}-12-31'])
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.warning("No hay datos de consumo para mostrar en el gráfico de evolución.")

        # --- Comparativa Anual ---
        if comparar_anos and not df_comparativa.empty and not df_filtered.empty:
            st.markdown("---")
            st.subheader("Comparativa Anual de Electricidad")
            df_comp_filtered = df_comparativa.copy()
            if selected_communities:
                df_comp_filtered = df_comp_filtered[df_comp_filtered['Comunidad Autónoma'].isin(selected_communities)]
            if selected_tension:
                df_comp_filtered = df_comp_filtered[df_comp_filtered['Tipo de Tensión'].isin(selected_tension)]
            
            if vista_por_centro and selected_centros:
                df_comp_filtered = df_comp_filtered[df_comp_filtered['Centro'].isin(selected_centros)]

            if not df_comp_filtered.empty:
                prev_year = df_comp_filtered['Año'].iloc[0]

                plantilla_meses = pd.DataFrame({'Mes': range(1, 13)})

                df_current_year_monthly = df_filtered[df_filtered['Tipo de Energía'] == 'Electricidad'].groupby('Mes')['Consumo_kWh'].sum().reset_index()
                df_prev_year_monthly = df_comp_filtered.groupby('Mes')['Consumo_kWh'].sum().reset_index()

                df_current_full = pd.merge(plantilla_meses, df_current_year_monthly, on='Mes', how='left').fillna(0)
                df_prev_full = pd.merge(plantilla_meses, df_prev_year_monthly, on='Mes', how='left').fillna(0)

                comparison_df = pd.DataFrame({
                    'Mes': plantilla_meses['Mes'],
                    str(selected_year): df_current_full['Consumo_kWh'],
                    str(prev_year): df_prev_full['Consumo_kWh']
                })
                
                months_order = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
                comparison_df['Mes_str'] = comparison_df['Mes'].apply(lambda x: months_order[x-1])

                fig_comp = px.bar(comparison_df, x='Mes_str', y=[str(selected_year), str(prev_year)], barmode='group',
                                  title=f'Comparativa de Consumo Mensual: {selected_year} vs. {prev_year}',
                                  labels={'value': 'Consumo Eléctrico (kWh)', 'Mes_str': 'Mes'},
                                  category_orders={"Mes_str": months_order})
                st.plotly_chart(fig_comp, use_container_width=True)
            else:
                st.warning(f"No hay datos de electricidad del año anterior para los filtros seleccionados.")

    else:
        st.warning("No se encontraron datos para los filtros aplicados. Por favor, ajusta tu selección.")
else:
    st.warning("No hay datos cargados para mostrar. Por favor, selecciona archivos en la barra lateral.")
