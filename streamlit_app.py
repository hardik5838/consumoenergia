# Importar librerías
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os

# --- Configuración de la página ---
st.set_page_config(
    page_title="Dashboard de Consumo Energético",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Mapeos de Datos ---
# Mapeo de provincias a comunidades autónomas para el agrupamiento geográfico.
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
    'Valencia/València': 'Comunidad Valenciana', 'Alicante/Alacant': 'Comunidad Valenciana', 'Castellón/Castelló': 'Comunidad Valenciana'
}

# Mapeo de tarifas de acceso a tipo de tensión.
def get_voltage_type(rate):
    if rate in ["6.1TD", "6.2TD", "6.3TD", "6.4TD"]:
        return "Alta Tensión"
    elif rate in ["2.0TD", "3.0TD"]:
        return "Baja Tensión"
    return "No definido"


# --- Carga y Procesamiento de Datos ---
@st.cache_data
def load_data(file_path):
    """Carga, limpia y procesa los datos de consumo energético."""
    try:
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.strip()

        # 1. Filtrar solo facturas con estado "ACTIVA"
        df = df[df['Estado de factura'].str.upper() == 'ACTIVA']

        # 2. Procesamiento de columnas
        # Renombrar columnas para facilitar el acceso
        df.rename(columns={
            'Nombre suministro': 'Centro',
            'Base imponible (€)': 'Coste',
            'Consumo activa total (kWh)': 'Consumo_kWh'
        }, inplace=True)
        
        # Convertir fechas
        df['Fecha desde'] = pd.to_datetime(df['Fecha desde'])
        df['Año'] = df['Fecha desde'].dt.year
        df['Mes'] = df['Fecha desde'].dt.month

        # Convertir a numérico y rellenar NaN
        numeric_cols = ['Coste', 'Consumo_kWh']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df[numeric_cols] = df[numeric_cols].fillna(0)

        # 3. Añadir columnas para análisis
        df['Comunidad Autónoma'] = df['Provincia'].map(province_to_community)
        df['Tipo de Tensión'] = df['Tarifa de acceso'].apply(get_voltage_type)
        
        # Eliminar filas donde no se pudo mapear la comunidad autónoma
        df.dropna(subset=['Comunidad Autónoma'], inplace=True)

        return df
    except FileNotFoundError:
        st.error(f"Error: No se encontró el archivo de datos en la ruta: {file_path}")
        return pd.DataFrame()
    except KeyError as e:
        st.error(f"Error de columna: No se encontró la columna requerida: {e}. Por favor, revisa el archivo CSV.")
        return pd.DataFrame()

# --- Barra Lateral (Filtros) ---
with st.sidebar:
    st.image("Logo_ASEPEYO.png", width=200)
    st.title('Filtros de Análisis')

    DATA_DIR = "Data/"
    try:
        files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
        if not files:
            st.warning(f"No se encontraron archivos CSV en la carpeta '{DATA_DIR}'.")
            st.stop()
        
        selected_file = st.selectbox("Seleccionar Archivo de Datos", files)
        file_path = os.path.join(DATA_DIR, selected_file)
        df_original = load_data(file_path)
    except FileNotFoundError:
        st.error(f"El directorio '{DATA_DIR}' no fue encontrado. Asegúrate de que la carpeta exista.")
        st.stop()

    if not df_original.empty:
        # --- Selección de Año y Mes ---
        st.markdown("### 📅 Filtro Temporal")
        selected_year = st.selectbox('Seleccionar Año', sorted(df_original['Año'].unique(), reverse=True))
        
        # --- Filtro de Agregación Temporal ---
        time_aggregation = st.radio(
            "Vista Temporal",
            ('Mensual', 'Acumulada Anual'),
            horizontal=True
        )

        st.markdown("---")

        # --- Filtros Geográficos ---
        st.markdown("### 🌍 Filtro Geográfico")
        
        # Inicialización de Session State
        if 'last_file_processed' not in st.session_state or st.session_state.last_file_processed != selected_file:
            st.session_state.last_file_processed = selected_file
            st.session_state.selected_communities = sorted(df_original['Comunidad Autónoma'].unique().tolist())
        
        lista_comunidades = sorted(df_original['Comunidad Autónoma'].unique().tolist())
        
        # Botón para seleccionar todas las comunidades
        if st.button("Seleccionar Todas las Comunidades", use_container_width=True):
            st.session_state.selected_communities = lista_comunidades
        
        selected_communities = st.multiselect(
            'Seleccionar Comunidades',
            lista_comunidades,
            default=st.session_state.selected_communities
        )
        st.session_state.selected_communities = selected_communities
        
        st.markdown("---")
        
        # --- Filtros Adicionales ---
        st.markdown("### ⚡ Otros Filtros")
        
        # Filtro por Tipo de Tensión
        tension_types = sorted(df_original['Tipo de Tensión'].unique().tolist())
        selected_tension = st.multiselect(
            'Tipo de Tensión',
            tension_types,
            default=tension_types
        )

# --- Lógica de la Aplicación Principal ---
if 'df_original' in locals() and not df_original.empty:

    # Aplicar filtros a los datos
    df_filtered = df_original[
        (df_original['Año'] == selected_year) &
        (df_original['Comunidad Autónoma'].isin(selected_communities)) &
        (df_original['Tipo de Tensión'].isin(selected_tension))
    ].copy()

    # --- Título del Dashboard ---
    st.title(f"Dashboard de Consumo Energético - {selected_year}")
    st.markdown(f"**Archivo de datos:** `{selected_file}`")
    st.markdown("---")

    # --- KPIs Principales ---
    if not df_filtered.empty:
        total_kwh = df_filtered['Consumo_kWh'].sum()
        total_cost = df_filtered['Coste'].sum()

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric(label="Consumo Total de Electricidad", value=f"{total_kwh:,.0f} kWh")
        kpi2.metric(label="Coste Total de Electricidad", value=f"€ {total_cost:,.2f}")
        # Placeholder para el consumo de gas
        kpi3.metric(label="Consumo Total de Gas", value="N/A", help="Datos de gas no disponibles en el archivo actual.")
        st.markdown("---")
        
        # --- Lógica de Agregación ---
        if time_aggregation == 'Mensual':
            df_agg = df_filtered.groupby(['Mes', 'Provincia', 'Tipo de Tensión'])[['Consumo_kWh', 'Coste']].sum().reset_index()
            time_label = "Mensual"
        else: # Acumulada Anual
            df_agg = df_filtered.copy()
            df_agg['Mes'] = 12 # Para agrupar todo el año
            df_agg = df_agg.groupby(['Mes', 'Provincia', 'Tipo de Tensión'])[['Consumo_kWh', 'Coste']].sum().reset_index()
            time_label = "Acumulado Anual"
        
        # --- Visualizaciones ---
        col1, col2 = st.columns(2, gap="large")

        with col1:
            st.subheader(f"Consumo y Coste por Provincia ({time_label})")
            df_prov = df_agg.groupby('Provincia')[['Consumo_kWh', 'Coste']].sum().reset_index().sort_values(by='Consumo_kWh', ascending=False)
            
            fig1 = go.Figure()
            fig1.add_trace(go.Bar(
                x=df_prov['Provincia'],
                y=df_prov['Consumo_kWh'],
                name='Consumo (kWh)',
                marker_color='blue'
            ))
            fig1.add_trace(go.Scatter(
                x=df_prov['Provincia'],
                y=df_prov['Coste'],
                name='Coste (€)',
                mode='lines+markers',
                yaxis='y2',
                marker_color='red'
            ))
            fig1.update_layout(
                template="plotly_white",
                yaxis=dict(title='Consumo (kWh)'),
                yaxis2=dict(title='Coste (€)', overlaying='y', side='right'),
                legend_title_text='Métrica',
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig1, use_container_width=True)

            st.subheader(f"Distribución por Tipo de Tensión ({time_label})")
            df_tension = df_agg.groupby('Tipo de Tensión')[['Consumo_kWh', 'Coste']].sum().reset_index()
            fig_pie_consumo = px.pie(df_tension, names='Tipo de Tensión', values='Consumo_kWh', title='Distribución del Consumo (kWh)')
            st.plotly_chart(fig_pie_consumo, use_container_width=True)
            

        with col2:
            st.subheader(f"Evolución Mensual del Consumo y Coste")
            if time_aggregation == 'Mensual':
                df_monthly = df_filtered.groupby('Mes')[['Consumo_kWh', 'Coste']].sum().reset_index()
                df_monthly['Mes'] = df_monthly['Mes'].apply(lambda x: pd.to_datetime(f'{selected_year}-{x}-01').strftime('%b'))

                fig2 = go.Figure()
                fig2.add_trace(go.Bar(
                    x=df_monthly['Mes'],
                    y=df_monthly['Consumo_kWh'],
                    name='Consumo (kWh)',
                    marker_color='lightblue'
                ))
                fig2.add_trace(go.Scatter(
                    x=df_monthly['Mes'],
                    y=df_monthly['Coste'],
                    name='Coste (€)',
                    mode='lines+markers',
                    yaxis='y2',
                    marker_color='orange'
                ))
                fig2.update_layout(
                    template="plotly_white",
                    yaxis=dict(title='Consumo (kWh)'),
                    yaxis2=dict(title='Coste (€)', overlaying='y', side='right'),
                    legend_title_text='Métrica',
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("La vista de evolución mensual solo está disponible en la agregación 'Mensual'.")
            
            fig_pie_coste = px.pie(df_tension, names='Tipo de Tensión', values='Coste', title='Distribución del Coste (€)')
            st.plotly_chart(fig_pie_coste, use_container_width=True)

        # --- Tabla de Datos Detallados ---
        st.markdown("---")
        st.header("Tabla de Datos Detallados")
        
        with st.expander("Mostrar/Ocultar Tabla de Datos"):
            columnas_a_mostrar = [
                'Fecha desde', 'Centro', 'Provincia', 'Comunidad Autónoma',
                'Tipo de Tensión', 'Consumo_kWh', 'Coste'
            ]
            
            # Formateo de las columnas
            st.dataframe(
                df_filtered[columnas_a_mostrar],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Fecha desde": st.column_config.DateColumn("Fecha Factura", format="DD/MM/YYYY"),
                    "Consumo_kWh": st.column_config.NumberColumn("Consumo (kWh)", format="%d kWh"),
                    "Coste": st.column_config.NumberColumn("Coste (€)", format="€ %.2f"),
                }
            )

    else:
        st.warning("No hay datos disponibles para la selección de filtros actual. Por favor, ajusta los filtros.")

else:
    st.warning("No se pudieron cargar los datos. Por favor, revisa la configuración del archivo.")
