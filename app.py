import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import altair as alt
from streamlit_confetti import confetti
import requests
import pandas as pd
import time
import os
from dotenv import load_dotenv

load_dotenv()

# Config: Point to your Vercel backend
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000/api")  # Adjust for Vercel: /api/nba/props

# Custom CSS: Ultra-modern theme (teal/coral, Inter font, shadows, responsiveness)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
    .stApp { background: linear-gradient(135deg, #1F2937 0%, #0D9488 100%); font-family: 'Inter', sans-serif; }
    .hero { background: radial-gradient(circle, #F3F4F6 0%, #0D9488 100%); padding: 2rem; text-align: center; color: white; border-radius: 0 0 20px 20px; }
    .card { background: #1F2937; border-radius: 12px; padding: 1.5rem; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); margin: 1rem 0; transition: all 0.3s ease; color: #F3F4F6; }
    .card:hover { transform: translateY(-4px); box-shadow: 0 20px 25px -5px rgba(13,148,136,0.3); }
    .btn-gradient { background: linear-gradient(45deg, #0D9488, #F87171); color: white; border: none; border-radius: 8px; padding: 0.75rem 1.5rem; transition: 0.2s; cursor: pointer; }
    .btn-gradient:hover { background: linear-gradient(45deg, #F87171, #0D9488); }
    .toast { position: fixed; bottom: 20px; right: 20px; padding: 1rem; border-radius: 8px; color: white; z-index: 1000; background: #F87171; }
    .dark-mode { background-color: #1F2937; color: #F3F4F6; }
    @media (max-width: 768px) { .card { margin: 0.5rem; padding: 1rem; } .stButton > button { width: 100%; } }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="dark-mode">', unsafe_allow_html=True)

# Hero Header: Premium feel with NBA vibe
st.markdown("""
    <div class="hero">
        <h1 style="font-weight:700; font-size:3rem; margin:0;">PropPulse</h1>
        <p style="font-size:1.2rem; margin:0.5rem 0;">Live NBA Props + X Beat Writer Edge</p>
        <p style="font-size:1rem; opacity:0.9;">Adjusted risks, arbs, and alerts—powered by ML & Woj/Shams intel</p>
    </div>
""", unsafe_allow_html=True)

# Sidebar: Collapsible nav with icons
with st.sidebar:
    st.markdown('<h3 style="color:#F3F4F6;">Quick Nav</h3>', unsafe_allow_html=True)
    if st.button('🏀 NBA Props', key='nba', help='Live player props with X adjustments'):
        st.session_state.page = 'nba'
    if st.button('🎓 NCAAB Props', key='ncaab', help='College hoops edges'):
        st.session_state.page = 'ncaab'
    if st.button('⚡ Arbs & Alerts', key='arbs', help='Cross-book opportunities'):
        st.session_state.page = 'arbs'
    st.divider()
    # Dark/Light Toggle (default dark for pros)
    mode = st.toggle('Dark Mode', value=True, help='Night-shift friendly')
    if not mode:
        st.markdown("""
            <style>
            .stApp { background: linear-gradient(135deg, #F3F4F6 0%, #E5E7EB 100%); color: #1F2937; }
            .card { background: #F3F4F6; color: #1F2937; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
            .hero { background: radial-gradient(circle, #FFFFFF 0%, #10B981 100%); color: #1F2937; }
            </style>
        """, unsafe_allow_html=True)
    st.divider()
    if st.button('🔧 Backend Health', key='health', help='Ping Vercel API'):
        try:
            resp = requests.get(f"{BACKEND_URL}/health")
            st.success(f"✅ Healthy! Redis: {resp.json().get('redis', False)}")
        except Exception as e:
            st.error(f"❌ API Issue: {e}")

# Init session state
if 'page' not in st.session_state:
    st.session_state.page = 'nba'

# Cached API fetch (5min TTL for live feel)
@st.cache_data(ttl=300)
def fetch_props(endpoint):
    try:
        resp = requests.get(f"{BACKEND_URL}/{endpoint}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Failed to fetch {endpoint}: {e}. Check BACKEND_URL.")
        return []

# Main Content: Responsive 3-col grid (stacks on mobile)
def render_grid(props, title, chart_type='bar'):
    if not props:
        st.info("🔄 Fetching live props... Refresh or check backend.")
        return
    df = pd.DataFrame(props)
    cols = st.columns([1, 1, 1]) if st.button('Desktop View', key='desktop') else st.columns(1)  # Sim responsive
    with cols[0] if len(cols) > 1 else cols[0]:
        st.markdown(f'<div class="card"><h2 style="color:#F87171;">{title} Overview</h2></div>', unsafe_allow_html=True)
        if chart_type == 'bar':
            fig = px.bar(df.head(8),
