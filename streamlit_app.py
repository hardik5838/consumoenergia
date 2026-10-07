import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
import requests
from datetime import date
from thefuzz import process

# --- Page Configuration ---
st.set_page_config(
    page_title="Informe Anual de Energía - Asepeyo",
    page_icon="💡",
    layout="wide",
    initial_sidebar_state="expanded"
)

CO2_FACTOR_ELEC = 0.19  # tCO2e / MWh
CO2_FACTOR_GAS = 0.18   # tCO2e / MWh

province_to_community = {
    'Almería': 'Andalucía', 'Cádiz': 'Andalucía', 'Córdoba': 'Andalucía', 'Granada': 'Andalucía',
    'Huelva': 'Andalucía', 'Jaén': 'Andalucía', 'Málaga': 'Andalucía', 'Sevilla': 'Andalucía',
    'Huesca': 'Aragón', 'Teruel': 'Aragón', 'Zaragoza': 'Aragón',
    'Asturias': 'Principado de Asturias', 'Balears, Illes': 'Islas Baleares',
    'Araba/Álava': 'País Vasco', 'Bizkaia': 'País Vasco', 'Gipuzkoa': 'País Vasco',
    'Las Palmas': 'Canarias', 'Santa Cruz de Tenerife': 'Canarias',
    'Cantabria': 'Cantabria', 'Ávila': 'Castilla y León', 'Burgos': 'Castilla y León',
    'León': 'Castilla y León', 'Palencia': 'Castilla y León', 'Salamanca': 'Castilla y León',
    'Segovia': 'Castilla y León', 'Soria': 'Castilla y León', 'Valladolid': 'Castilla y León',
    'Zamora': 'Castilla y León', 'Albacete': 'Castilla-La Mancha', 'Ciudad Real': 'Castilla-La Mancha',
    'Cuenca': 'Castilla-La Mancha', 'Guadalajara': 'Castilla-La Mancha', 'Toledo': 'Castilla-La Mancha',
    'Barcelona': 'Cataluña', 'Girona': 'Cataluña', 'Lleida': 'Cataluña', 'Tarragona': 'Cataluña',
    'Ceuta': 'Ceuta', 'Badajoz': 'Extremadura', 'Cáceres': 'Extremadura',
    'Coruña, A': 'Galicia', 'Lugo': 'Galicia', 'Ourense': 'Galicia', 'Pontevedra': 'Galicia',
    'Rioja, La': 'La Rioja', 'Madrid': 'Comunidad de Madrid', 'Melilla': 'Melilla',
    'Murcia': 'Región de Murcia', 'Navarra': 'Comunidad Foral de Navarra',
    'Valencia/València': 'Comunidad Valenciana', 'Alicante/Alacant': 'Comunidad Valenciana',
    'Castellón': 'Comunidad Valenciana', 'Castellón/Castelló': 'Comunidad Valenciana'
}

def clean_number(val):
    """Clean European formatted numbers (1.234,56 -> 1234.56)."""
    if pd.isna(val) or val is None or val == '':
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if '.' in s and ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except Exception:
        return 0.0

def get_voltage_type(rate):
    if str(rate) in ["6.1TD", "6.2TD", "6.3TD", "6.4TD", "6.1A"]:
        return "Alta Tensión"
    elif str(rate) in ["2.0TD", "3.0TD"]:
        return "Baja Tensión"
    return "No definido"

@st.cache_data
def load_energy_data(file_path, default_energy_type="Electricidad"):
    """Loads CSV/TSV invoice datasets cleanly."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()
        
        separator = ';' if ';' in first_line else (',' if ',' in first_line else '\t')
        
        df = pd.read_csv(file_path, sep=separator, low_memory=False)
        df.columns = df.columns.str.strip()
        
        if 'Estado de factura' in df.columns:
            df = df[df['Estado de factura'].astype(str).str.upper() == 'ACTIVA']
            
        rename_dict = {
            'Nombre suministro': 'Centro',
            'Base imponible (€)': 'Coste Total',
            'Consumo activa total (kWh)': 'Consumo_kWh',
            'Consumo': 'Consumo_kWh',
            'Importe TE (€)': 'Coste Energía',
            'Importe TP (€)': 'Coste Potencia',
            'Importe impuestos (€)': 'Coste Impuestos',
            'Importe alquiler (€)': 'Coste Alquiler',
            'Importe otros conceptos (€)': 'Coste Otros'
        }
        df.rename(columns=rename_dict, inplace=True)
        
        date_col = 'Fecha desde' if 'Fecha desde' in df.columns else 'Fecha emisión'
        df['Fecha'] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
        df['Año'] = df['Fecha'].dt.year
        df['Mes'] = df['Fecha'].dt.month
        
        numeric_cols = ['Consumo_kWh', 'Coste Total', 'Coste Energía', 'Coste Potencia', 
                        'Coste Impuestos', 'Coste Alquiler', 'Coste Otros']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(clean_number)
            else:
                df[col] = 0.0
                
        if 'Provincia' in df.columns:
            df['Comunidad Autónoma'] = df['Provincia'].map(province_to_community)
        else:
            df['Comunidad Autónoma'] = 'No definido'
            
        if 'Tarifa de acceso' in df.columns:
            df['Tipo de Tensión'] = df['Tarifa de acceso'].apply(get_voltage_type)
        else:
            df['Tipo de Tensión'] = 'No definido'
            
        if 'gas' in os.path.basename(file_path).lower():
            df['Tipo de Energía'] = 'Gas'
        else:
            df['Tipo de Energía'] = default_energy_type
            
        return df
    except Exception as e:
        st.error(f"Error cargando el archivo '{os.path.basename(file_path)}': {e}")
        return pd.DataFrame()

@st.cache_data
def get_geojson():
    url = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/spain-communities.geojson"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

def create_safe_choropleth_map(df_map, geojson):
    """
    Bulletproof map renderer supporting all Plotly versions (4.x, 5.x, 6.0+).
    Tries px.choropleth_map -> px.choropleth_mapbox -> px.choropleth.
    """
    if df_map is None or df_map.empty or not geojson:
        return None

    # Priority 1: Modern Plotly 5.24+ (MapLibre backend)
    if hasattr(px, 'choropleth_map'):
        try:
            fig = px.choropleth_map(
                df_map,
                geojson=geojson,
                locations='geo_key',
                featureidkey="properties.name",
                color='Consumo_kWh',
                color_continuous_scale="Viridis",
                map_style="open-street-map",
                zoom=4.2,
                center={"lat": 40.4168, "lon": -3.7038},
                title="Consumo por Comunidad Autónoma"
            )
            fig.update_layout(margin={"r":0, "t":30, "l":0, "b":0})
            return fig
        except Exception:
            pass

    # Priority 2: Legacy Plotly Mapbox (< 5.24)
    if hasattr(px, 'choropleth_mapbox'):
        try:
            fig = px.choropleth_mapbox(
                df_map,
                geojson=geojson,
                locations='geo_key',
                featureidkey="properties.name",
                color='Consumo_kWh',
                color_continuous_scale="Viridis",
                mapbox_style="open-street-map",
                zoom=4.2,
                center={"lat": 40.4168, "lon": -3.7038},
                title="Consumo por Comunidad Autónoma"
            )
            fig.update_layout(margin={"r":0, "t":30, "l":0, "b":0})
            return fig
        except Exception:
            pass

    # Priority 3: Standard Universal Choropleth (No Mapbox/MapLibre dependency)
    try:
        fig = px.choropleth(
            df_map,
            geojson=geojson,
            locations='geo_key',
            featureidkey="properties.name",
            color='Consumo_kWh',
            color_continuous_scale="Viridis",
            title="Consumo por Comunidad Autónoma"
        )
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_layout(margin={"r":0, "t":30, "l":0, "b":0})
        return fig
    except Exception as e:
        st.warning(f"No se pudo renderizar el mapa geográfico: {e}")
        return None

# --- Sidebar Controls ---
st.sidebar.title("⚙️ Panel de Control")

DATA_DIR = "Data/"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

all_files = [f for f in os.listdir(DATA_DIR) if f.endswith(('.csv', '.tsv'))]
if not all_files:
    root_files = [f for f in os.listdir(".") if f.endswith(('.csv', '.tsv'))]
    if root_files:
        all_files = root_files
        DATA_DIR = "."

if not all_files:
    st.sidebar.warning("⚠️ Suba los archivos CSV de facturas para comenzar.")
    st.stop()

selected_file_elec = st.sidebar.selectbox("Archivo Electricidad", all_files, index=0)
selected_file_gas = st.sidebar.selectbox("Archivo Gas (Opcional)", [None] + all_files, index=0)

df_elec = load_energy_data(os.path.join(DATA_DIR, selected_file_elec), "Electricidad") if selected_file_elec else pd.DataFrame()
df_gas = load_energy_data(os.path.join(DATA_DIR, selected_file_gas), "Gas") if selected_file_gas else pd.DataFrame()

df_combined = pd.concat([df_elec, df_gas], ignore_index=True)

if df_combined.empty:
    st.warning("No hay datos válidos para procesar.")
    st.stop()

available_years = sorted(df_combined['Año'].dropna().unique().astype(int), reverse=True)
selected_year = st.sidebar.selectbox("📅 Año Objetivo", available_years, index=0)

# --- Predictive Model Parameters ---
cutoff_month = st.sidebar.slider("Mes Corte Facturas Reales", 1, 11, value=6)
weather_winter = st.sidebar.slider("Aumento Clima Invierno %", -20, 40, value=10) / 100.0
weather_summer = st.sidebar.slider("Aumento Clima Verano %", -20, 40, value=15) / 100.0
future_centers_num = st.sidebar.number_input("Nº Nuevos Centros Futuros", min_value=0, value=1)
future_centers_start = st.sidebar.slider("Mes Inicio Nuevos Centros", cutoff_month+1, 12, value=min(cutoff_month+2, 12))
future_centers_kwh = st.sidebar.number_input("kWh/Mes por Nuevo Centro", min_value=0, value=20000)

contract_limit_kwh = st.sidebar.number_input("Límite Contratado Anual (kWh)", min_value=100000, value=18000000)
contract_exp_date = st.sidebar.date_input("Vencimiento Contrato", value=date(selected_year, 12, 31))

# --- Mathematical Model Execution ---
prev_year = selected_year - 1
df_curr = df_combined[df_combined['Año'] == selected_year]
df_prev = df_combined[df_combined['Año'] == prev_year]

c_curr = df_curr[df_curr['Mes'] <= cutoff_month].groupby(['Centro', 'Mes'])['Consumo_kWh'].sum().unstack(fill_value=0)
c_prev = df_prev.groupby(['Centro', 'Mes'])['Consumo_kWh'].sum().unstack(fill_value=0)

all_cols = range(1, 13)
c_curr = c_curr.reindex(columns=all_cols, fill_value=0)
c_prev = c_prev.reindex(columns=all_cols, fill_value=0)

all_centers = sorted(list(set(c_curr.index).union(set(c_prev.index))))
unit_price = df_curr['Coste Total'].sum() / max(1, df_curr['Consumo_kWh'].sum())
if unit_price == 0: unit_price = 0.14

forecast_records = []
center_ramp_factors = {}

for c in all_centers:
    ytd_curr = c_curr.loc[c, 1:cutoff_month].sum() if c in c_curr.index else 0.0
    ytd_prev = c_prev.loc[c, 1:cutoff_month].sum() if c in c_prev.index else 0.0
    
    ramp = (ytd_curr / ytd_prev) if ytd_prev > 0 else 1.0
    center_ramp_factors[c] = ramp
    
    for m in range(1, 13):
        if m <= cutoff_month:
            kwh = c_curr.loc[c, m] if c in c_curr.index else 0.0
            is_real = True
        else:
            hist_m = c_prev.loc[c, m] if c in c_prev.index else (ytd_curr / max(1, cutoff_month))
            if hist_m == 0 and ytd_curr > 0: hist_m = ytd_curr / cutoff_month
            
            wf = (1.0 + weather_winter) if m in [1, 2, 3, 11, 12] else ((1.0 + weather_summer) if m in [6, 7, 8, 9] else 1.0)
            kwh = hist_m * ramp * wf
            is_real = False
            
        forecast_records.append({'Centro': c, 'Mes': m, 'Consumo_kWh': kwh, 'Es_Real': is_real})

if future_centers_num > 0:
    for m in range(future_centers_start, 13):
        forecast_records.append({'Centro': 'Futuros Centros', 'Mes': m, 'Consumo_kWh': future_centers_num * future_centers_kwh, 'Es_Real': False})

df_model = pd.DataFrame(forecast_records)
total_kwh_proj = df_model['Consumo_kWh'].sum()
kwh_ytd_real = df_model[df_model['Es_Real']]['Consumo_kWh'].sum()

# --- Main App Interface ---
st.title("💡 Dashboard Predictivo de Consumo Energético")
st.caption(f"Año: {selected_year} | Mes Corte: {cutoff_month} | Proyección Total: {total_kwh_proj:,.0f} kWh")
st.markdown("---")

tab1, tab2 = st.tabs(["📊 Mapa y Resumen Operativo", "🔮 Modelo Predictivo"])

with tab1:
    col_map, col_costs = st.columns([0.6, 0.4])
    
    with col_map:
        st.markdown("**Mapa de Consumo por Comunidad Autónoma**")
        geojson = get_geojson()
        if geojson and not df_curr.empty:
            df_map = df_curr.groupby('Comunidad Autónoma')['Consumo_kWh'].sum().reset_index()
            geo_names = [f['properties']['name'] for f in geojson['features']]
            
            mapping = {}
            for name in df_map['Comunidad Autónoma'].unique():
                m = process.extractOne(str(name), geo_names)
                if m and m[1] > 70:
                    mapping[name] = m[0]
                    
            df_map['geo_key'] = df_map['Comunidad Autónoma'].map(mapping)
            df_map.dropna(subset=['geo_key'], inplace=True)
            
            fig_map = create_safe_choropleth_map(df_map, geojson)
            if fig_map:
                st.plotly_chart(fig_map, use_container_width=True)
            else:
                st.info("No se pudo generar la capa visual del mapa.")
        else:
            st.info("Descargando GeoJSON o sin datos de mapa.")
            
    with col_costs:
        st.markdown("**Desglose de Costes YTD**")
        cost_cols = ['Coste Energía', 'Coste Potencia', 'Coste Impuestos', 'Coste Alquiler']
        exist_cols = [c for c in cost_cols if c in df_curr.columns]
        if exist_cols:
            cost_df = df_curr[exist_cols].sum().reset_index()
            cost_df.columns = ['Concepto', 'Coste']
            fig_pie = px.pie(cost_df, names='Concepto', values='Coste', hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

with tab2:
    st.markdown("### Trayectoria Mensual Proyectada vs. Real")
    monthly_agg = df_model.groupby(['Mes', 'Es_Real'])['Consumo_kWh'].sum().reset_index()
    fig_line = px.line(monthly_agg, x='Mes', y='Consumo_kWh', color='Es_Real', markers=True,
                       labels={'Es_Real': 'Factura Real'}, title="Evolución Mensual (kWh)")
    st.plotly_chart(fig_line, use_container_width=True)
