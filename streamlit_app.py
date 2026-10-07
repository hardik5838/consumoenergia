import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
import requests
from datetime import datetime, date
from thefuzz import process

# --- Page Configuration ---
st.set_page_config(
    page_title="Predicción Energética y Control de Contratos - Asepeyo",
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
    """Robust number cleaning for Spanish decimal/thousands formatting."""
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
    """Loads and standardizes electricity or gas invoice data."""
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
        
        # Datetime processing
        date_col = 'Fecha desde' if 'Fecha desde' in df.columns else 'Fecha emisión'
        df['Fecha'] = pd.to_datetime(df[date_col], dayfirst=True, errors='coerce')
        df['Año'] = df['Fecha'].dt.year
        df['Mes'] = df['Fecha'].dt.month
        
        # Numeric conversions
        numeric_cols = ['Consumo_kWh', 'Coste Total', 'Coste Energía', 'Coste Potencia', 
                        'Coste Impuestos', 'Coste Alquiler', 'Coste Otros']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = df[col].apply(clean_number)
            else:
                df[col] = 0.0
                
        # Fill location mappings
        if 'Provincia' in df.columns:
            df['Comunidad Autónoma'] = df['Provincia'].map(province_to_community)
        else:
            df['Comunidad Autónoma'] = 'No definido'
            
        if 'Tarifa de acceso' in df.columns:
            df['Tipo de Tensión'] = df['Tarifa de acceso'].apply(get_voltage_type)
        else:
            df['Tipo de Tensión'] = 'No definido'
            
        # Detect energy type if not provided
        if 'gas' in os.path.basename(file_path).lower():
            df['Tipo de Energía'] = 'Gas'
        else:
            df['Tipo de Energía'] = default_energy_type
            
        return df
    except Exception as e:
        st.error(f"Error cargando archivo {os.path.basename(file_path)}: {e}")
        return pd.DataFrame()

@st.cache_data
def get_geojson():
    url = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/spain-communities.geojson"
    try:
        res = requests.get(url, timeout=5)
        return res.json()
    except Exception:
        return None

# --- Sidebar Controls ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/e/e4/Logo_ASEPEYO.png", width=180)
st.sidebar.title("⚙️ Panel de Control")

DATA_DIR = "Data/"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

all_files = [f for f in os.listdir(DATA_DIR) if f.endswith(('.csv', '.tsv'))]
if not all_files:
    # Look in root directory if Data/ is empty
    root_files = [f for f in os.listdir(".") if f.endswith(('.csv', '.tsv'))]
    if root_files:
        all_files = root_files
        DATA_DIR = "."

if not all_files:
    st.sidebar.warning("⚠️ No se encontraron archivos de facturas en la carpeta.")
    st.info("Sube tus archivos de datos (.csv o .tsv) para activar el cuadro de mando.")
    st.stop()

st.sidebar.markdown("### 📁 Carga de Archivos")
selected_file_elec = st.sidebar.selectbox("Archivo Electricidad", all_files, index=0)
selected_file_gas = st.sidebar.selectbox("Archivo Gas (Opcional)", [None] + all_files, index=0)

df_elec = load_energy_data(os.path.join(DATA_DIR, selected_file_elec), "Electricidad") if selected_file_elec else pd.DataFrame()
df_gas = load_energy_data(os.path.join(DATA_DIR, selected_file_gas), "Gas") if selected_file_gas else pd.DataFrame()

df_combined = pd.concat([df_elec, df_gas], ignore_index=True)

if df_combined.empty:
    st.warning("No hay datos válidos para procesar.")
    st.stop()

available_years = sorted(df_combined['Año'].dropna().unique().astype(int), reverse=True)
selected_year = st.sidebar.selectbox("📅 Año Objetivo de Análisis", available_years, index=0)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🎛️ Parámetros del Modelo Predictivo")

# Automatic cutoff month detection
default_cutoff = 6
if selected_year in df_combined['Año'].values:
    df_curr_yr = df_combined[df_combined['Año'] == selected_year]
    monthly_counts = df_curr_yr.groupby('Mes')['Centro'].nunique()
    if not monthly_counts.empty:
        max_centers = monthly_counts.max()
        full_months = monthly_counts[monthly_counts >= max_centers * 0.7].index.tolist()
        if full_months:
            default_cutoff = max(full_months)

cutoff_month = st.sidebar.slider(
    "Mes Corte de Facturas Reales", 
    min_value=1, max_value=11, value=min(default_cutoff, 11),
    help="Meses <= al corte usan facturas reales. Meses posteriores usan el modelo predictivo."
)

st.sidebar.markdown("**🌡️ Factor Climático (Extremos Weather)**")
weather_winter = st.sidebar.slider(
    "Aumento Invierno (Calefacción/Gas) %", 
    min_value=-20, max_value=40, value=10, step=5,
    help="Afecta a meses de frío (Nov-Mar) en el periodo proyectado."
) / 100.0

weather_summer = st.sidebar.slider(
    "Aumento Verano (Climatización/AC) %", 
    min_value=-20, max_value=40, value=15, step=5,
    help="Afecta a meses de calor (Jun-Sep) en el periodo proyectado."
) / 100.0

st.sidebar.markdown("**🏬 Factor Nuevos Centros Futuros**")
future_centers_num = st.sidebar.number_input("Nº Centros Previstos a Añadir", min_value=0, max_value=20, value=1)
future_centers_start = st.sidebar.slider("Mes de Inicio del Nuevo Centro", min_value=cutoff_month+1, max_value=12, value=min(cutoff_month+2, 12))
future_centers_kwh = st.sidebar.number_input("Estimación Consumo Mensual (kWh/centro)", min_value=0, value=20000, step=2500)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📜 Parámetros de Contrato Energético")
contract_limit_kwh = st.sidebar.number_input("Límite Contratado Anual (kWh)", min_value=100000, value=18000000, step=500000)
contract_limit_cost = st.sidebar.number_input("Presupuesto Máximo Contratado (€)", min_value=10000, value=2500000, step=100000)
contract_exp_date = st.sidebar.date_input("Fecha Vencimiento del Contrato", value=date(selected_year, 12, 31))

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

# Calculate average historical unit price (€/kWh)
unit_price_elec = df_curr[df_curr['Tipo de Energía'] == 'Electricidad']['Coste Total'].sum() / max(1, df_curr[df_curr['Tipo de Energía'] == 'Electricidad']['Consumo_kWh'].sum())
if unit_price_elec == 0: unit_price_elec = 0.14

forecast_records = []
center_ramp_factors = {}

for c in all_centers:
    ytd_curr = c_curr.loc[c, 1:cutoff_month].sum() if c in c_curr.index else 0.0
    ytd_prev = c_prev.loc[c, 1:cutoff_month].sum() if c in c_prev.index else 0.0
    
    # Ramp factor calculation
    if ytd_prev > 0:
        ramp = ytd_curr / ytd_prev
    elif ytd_curr > 0:
        ramp = 1.0  # Brand new center in target year
    else:
        ramp = 1.0
        
    center_ramp_factors[c] = ramp
    
    for m in range(1, 13):
        if m <= cutoff_month:
            kwh = c_curr.loc[c, m] if c in c_curr.index else 0.0
            is_real = True
        else:
            hist_m = c_prev.loc[c, m] if c in c_prev.index else (ytd_curr / max(1, cutoff_month))
            if hist_m == 0 and ytd_curr > 0:
                hist_m = ytd_curr / cutoff_month
                
            # Apply weather factors
            if m in [1, 2, 3, 11, 12]:
                wf = 1.0 + weather_winter
            elif m in [6, 7, 8, 9]:
                wf = 1.0 + weather_summer
            else:
                wf = 1.0
                
            kwh = hist_m * ramp * wf
            is_real = False
            
        forecast_records.append({
            'Centro': c,
            'Mes': m,
            'Consumo_kWh': kwh,
            'Coste_Estimado': kwh * unit_price_elec,
            'Es_Real': is_real,
            'Tipo': 'Centro Existente'
        })

# Append future new centers
if future_centers_num > 0:
    for m in range(1, 13):
        if m >= future_centers_start:
            add_kwh = future_centers_num * future_centers_kwh
            forecast_records.append({
                'Centro': f'Nuevos Centros Futuros ({future_centers_num})',
                'Mes': m,
                'Consumo_kWh': add_kwh,
                'Coste_Estimado': add_kwh * unit_price_elec,
                'Es_Real': False,
                'Tipo': 'Nuevos Centros Planificados'
            })

df_model = pd.DataFrame(forecast_records)

# Model Summary Statistics
kwh_ytd_real = df_model[df_model['Es_Real']]['Consumo_kWh'].sum()
cost_ytd_real = df_model[df_model['Es_Real']]['Coste_Estimado'].sum()

kwh_forecast_remaining = df_model[~df_model['Es_Real']]['Consumo_kWh'].sum()
cost_forecast_remaining = df_model[~df_model['Es_Real']]['Coste_Estimado'].sum()

total_kwh_projected = kwh_ytd_real + kwh_forecast_remaining
total_cost_projected = cost_ytd_real + cost_forecast_remaining

# CO2 Emissions Projection
co2_projected = (total_kwh_projected * CO2_FACTOR_ELEC) / 1000.0

# --- Dashboard Header ---
st.title("💡 Modelo Predictivo y Control Energético Asepeyo")
st.caption(f"Año de Análisis: **{selected_year}** | Corte de Facturación Real: **Mes {cutoff_month}** | Proyección Predictiva: **Meses {cutoff_month+1} a 12**")
st.markdown("---")

# --- Top Key Performance Indicators ---
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric("Consumo Real YTD", f"{kwh_ytd_real:,.0f} kWh", f"Hasta Mes {cutoff_month}")
kpi2.metric("Proyección Anual Total", f"{total_kwh_projected:,.0f} kWh", f"{(total_kwh_projected - kwh_ytd_real):+,.0f} kWh estim.")
kpi3.metric("Coste Anual Proyectado", f"€ {total_cost_projected:,.2f}", f"Tarifa ~€{unit_price_elec:.3f}/kWh")
kpi4.metric("Emisiones CO₂ Estimadas", f"{co2_projected:,.1f} tCO₂e", "Factor 0.19 t/MWh")

# Contract usage percentage
contract_pct = (total_kwh_projected / max(1, contract_limit_kwh)) * 100
kpi5.metric("Uso de Contrato", f"{contract_pct:.1f}%", f"{contract_limit_kwh:,.0f} kWh límite", delta_color="inverse")

st.markdown("<br>", unsafe_allow_html=True)

# --- Navigation Tabs ---
tab_overview, tab_model, tab_centers, tab_contract = st.tabs([
    "📊 Resumen General", 
    "🔮 Modelo Predictivo y Escenarios", 
    "🏬 Evolución de Centros (Caso Chamartín)", 
    "📜 Alertas de Contrato y Márgenes"
])

# --- TAB 1: RESUMEN GENERAL ---
with tab_overview:
    st.subheader("Análisis Geográfico y Desglose Operativo")
    
    col_map, col_pie = st.columns([0.6, 0.4])
    
    with col_pie:
        st.markdown("**Desglose de Costes Eléctricos (Histórico YTD)**")
        cost_components = ['Coste Energía', 'Coste Potencia', 'Coste Impuestos', 'Coste Alquiler', 'Coste Otros']
        df_elec_costs = df_curr[df_curr['Tipo de Energía'] == 'Electricidad']
        existing_cols = [c for c in cost_components if c in df_elec_costs.columns]
        
        if not df_elec_costs.empty and existing_cols:
            cost_sum = df_elec_costs[existing_cols].sum().reset_index()
            cost_sum.columns = ['Componente', 'Coste']
            fig_pie = px.pie(cost_sum, names='Componente', values='Coste', hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No hay desglose detallado de costes disponible.")

    with col_map:
        st.markdown("**Consumo Real por Comunidad Autónoma**")
        geojson = get_geojson()
        if geojson and not df_curr.empty:
            df_map = df_curr.groupby('Comunidad Autónoma')['Consumo_kWh'].sum().reset_index()
            geo_names = [f['properties']['name'] for f in geojson['features']]
            
            mapping = {}
            for name in df_map['Comunidad Autónoma'].unique():
                m = process.extractOne(name, geo_names)
                if m and m[1] > 70:
                    mapping[name] = m[0]
                    
            df_map['geo_key'] = df_map['Comunidad Autónoma'].map(mapping)
            df_map.dropna(subset=['geo_key'], inplace=True)
            
            fig_map = px.choropleth_mapbox(
                df_map, geojson=geojson, locations='geo_key', featureidkey="properties.name",
                color='Consumo_kWh', color_continuous_scale="Tealgrn", mapbox_style="carto-positron",
                zoom=4.2, center={"lat": 40.4168, "lon": -3.7038}
            )
            fig_map.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
            st.plotly_chart(fig_map, use_container_width=True)
        else:
            st.info("Mapa no disponible o en carga.")

# --- TAB 2: MODELO PREDICTIVO ---
with tab_model:
    st.subheader("Trayectoria Mensual: Consumo Real vs. Modelo Predictivo")
    
    monthly_agg = df_model.groupby(['Mes', 'Es_Real'])['Consumo_kWh'].sum().reset_index()
    monthly_agg['Estado'] = monthly_agg['Es_Real'].map({True: 'Real Billed', False: 'Predictive Model'})
    
    # Plotly Line Chart
    fig_monthly = go.Figure()
    
    # Real segment
    real_data = monthly_agg[monthly_agg['Es_Real']]
    fig_monthly.add_trace(go.Scatter(
        x=real_data['Mes'], y=real_data['Consumo_kWh'],
        mode='lines+markers', name='Consumo Real Facturado',
        line=dict(color='#1f77b4', width=3), marker=dict(size=8)
    ))
    
    # Forecast segment
    forecast_data = monthly_agg[~monthly_agg['Es_Real']]
    # Connect last real month to first forecast month
    if not real_data.empty and not forecast_data.empty:
        last_real = real_data.iloc[-1:]
        forecast_data = pd.concat([last_real, forecast_data])
        
    fig_monthly.add_trace(go.Scatter(
        x=forecast_data['Mes'], y=forecast_data['Consumo_kWh'],
        mode='lines+markers', name='Predicción Modelo (Clima + Centros)',
        line=dict(color='#ff7f0e', width=3, dash='dash'), marker=dict(size=8)
    ))
    
    # Threshold Line
    monthly_contract_avg = contract_limit_kwh / 12.0
    fig_monthly.add_trace(go.Scatter(
        x=list(range(1, 13)), y=[monthly_contract_avg]*12,
        mode='lines', name='Promedio Mensual Contratado',
        line=dict(color='red', width=1.5, dash='dot')
    ))
    
    fig_monthly.update_layout(
        xaxis=dict(title='Mes', tickmode='linear', tick0=1, dtick=1),
        yaxis=dict(title='Consumo (kWh)'),
        hovermode='x unified', legend=dict(orientation="h", y=1.1)
    )
    st.plotly_chart(fig_monthly, use_container_width=True)
    
    # Scenario Table
    st.markdown("### 📋 Tabla de Consumo Mensual y Proyección")
    pivoted_monthly = df_model.groupby(['Mes', 'Es_Real'])['Consumo_kWh'].sum().unstack(fill_value=0)
    pivoted_monthly.columns = ['Proyectado (kWh)' if not col else 'Real (kWh)' for col in pivoted_monthly.columns]
    st.dataframe(pivoted_monthly.style.format("{:,.0f}"), use_container_width=True)

# --- TAB 3: EVOLUCIÓN DE CENTROS & CHAMARTÍN ---
with tab_centers:
    st.subheader("Análisis de Evolución por Centro y Ramp-Up (Caso Chamartín)")
    st.markdown("""
    El modelo evalúa automáticamente la trayectoria de cada centro. Los centros que presentan aumentos exponenciales
    o aperturas paulatinas (como el caso **Chamartín**) son ajustados mediante un multiplicador de rampa ($\alpha_c$).
    """)
    
    col_sel, col_ramp = st.columns([0.4, 0.6])
    
    with col_sel:
        selected_center = st.selectbox("Seleccionar Centro para Inspeccionar", all_centers, index=0 if 'Chamartín' not in all_centers else all_centers.index('Chamartín'))
        
        c_hist = df_combined[df_combined['Centro'] == selected_center]
        if not c_hist.empty:
            yearly_c = c_hist.groupby('Año')['Consumo_kWh'].sum().reset_index()
            fig_c_hist = px.bar(yearly_c, x='Año', y='Consumo_kWh', title=f"Evolución Histórica Anual: {selected_center}", color_discrete_sequence=['#2ca02c'])
            st.plotly_chart(fig_c_hist, use_container_width=True)
            
    with col_ramp:
        st.markdown(f"**Factor de Crecimiento Calculado ($\alpha_c$) para {selected_center}:**")
        ramp_val = center_ramp_factors.get(selected_center, 1.0)
        st.metric("Factor Multiplicador de Rampa", f"{ramp_val:.2f}x", f"{(ramp_val - 1.0)*100:+.1f}% vs Año Anterior")
        
        # Monthly detail for selected center
        df_c_model = df_model[df_model['Centro'] == selected_center]
        fig_c_monthly = px.line(df_c_model, x='Mes', y='Consumo_kWh', color='Es_Real', 
                                title=f"Proyección Mensual {selected_year} para {selected_center}",
                                markers=True, color_discrete_map={True: '#1f77b4', False: '#ff7f0e'})
        st.plotly_chart(fig_c_monthly, use_container_width=True)

    st.markdown("---")
    st.markdown("### 🏆 Top Centros con Mayor Crecimiento (Ramp-Up)")
    df_ramps = pd.DataFrame(list(center_ramp_factors.items()), columns=['Centro', 'Factor Rampa (Alpha)'])
    df_ramps = df_ramps.sort_values(by='Factor Rampa (Alpha)', ascending=False).head(10)
    st.dataframe(df_ramps.style.format({'Factor Rampa (Alpha)': '{:.2f}x'}), use_container_width=True)

# --- TAB 4: CONTROL DE CONTRATO Y ALERTAS ---
with tab_contract:
    st.subheader("📜 Control de Contratos, Márgenes y Alerta de Expiración")
    
    days_to_exp = (contract_exp_date - date.today()).days
    months_to_exp = days_to_exp / 30.0
    
    col_c1, col_c2, col_c3 = st.columns(3)
    col_c1.metric("Límite de Contrato", f"{contract_limit_kwh:,.0f} kWh")
    col_c2.metric("Proyección Anual", f"{total_kwh_projected:,.0f} kWh")
    col_c3.metric("Días para Expiración", f"{days_to_exp} días", f"~{months_to_exp:.1f} meses restantes")
    
    st.markdown("---")
    st.subheader("🚨 Alerta y Recomendación para la Dirección")
    
    # Contract Rule Engine: 50% - 75% thresholds & 3 months expiration trigger
    exceeds_75 = contract_pct >= 75.0
    exceeds_100 = contract_pct >= 100.0
    near_expiration = months_to_exp <= 3.0
    
    if exceeds_100:
        st.error(f"""
        ❌ **ALERTA CRÍTICA: Sobrepaso del Límite Contratado Detectado**
        
        La proyección anual (**{total_kwh_projected:,.0f} kWh**) supera el máximo contratado (**{contract_limit_kwh:,.0f} kWh**) en un **{contract_pct - 100:.1f}%**.
        
        **Acción Requerida:** Ejecutar de inmediato la cláusula de ampliación de margen con la comercializadora eléctrica para evitar penalizaciones por excesos de consumo.
        """)
    elif exceeds_75 or near_expiration:
        st.warning(f"""
        ⚠️ **ADVERTENCIA ESTRATÉGICA: Umbral del 50%–75% o Proximidad de Expiración**
        
        - **Uso de Contrato Proyectado:** {contract_pct:.1f}% del volumen contratado.
        - **Ventana Temprana de Expiración:** Faltan **{months_to_exp:.1f} meses** para la fecha de vencimiento ({contract_exp_date.strftime('%d/%m/%Y')}).
        
        **Recomendación de Gestión:** De acuerdo con las condiciones contractuales firmadas, se aconseja iniciar la **negociación de extensión de consumo 3 meses antes de la expiración**, ampliando el margen de gasto asignado sin incurrir en nuevas licitaciones de emergencia.
        """)
    else:
        st.success(f"""
        ✅ **ESTADO OPERATIVO CORRECTO**
        
        El consumo proyectado se encuentra dentro del margen de seguridad (**{contract_pct:.1f}%** del contrato).
        Quedan **{months_to_exp:.1f} meses** para la revisión formal del contrato.
        """)

    # Downloadable Executive Report
    st.markdown("---")
    st.markdown("### 📥 Exportar Informe Ejecutivo")
    csv_data = df_model.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📄 Descargar Proyección Completa en CSV",
        data=csv_data,
        file_name=f"Proyeccion_Energia_Asepeyo_{selected_year}.csv",
        mime="text/csv"
    )
