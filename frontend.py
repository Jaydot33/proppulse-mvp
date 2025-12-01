import streamlit as st
import requests
import os

st.set_page_config(page_title="PropPulse", layout="wide", initial_sidebar_state="expanded")

# Custom CSS for HQ look (dark theme, pulse animation)
st.markdown("""
<style>
    .main {background-color: #001F3F; color: #7FDBFF;}
    .stMetric > label {color: #7FDBFF; font-family: 'Arial', sans-serif; font-weight: bold; font-size: 1.1em;}
    .stMetric > .stMetricValue {color: #FF4500; font-size: 2.5em;}
    .risk-warning {background-color: #FF851B; padding: 10px; border-radius: 5px; color: white; font-weight: bold;}
    .pulse-line {animation: pulse 2s infinite;}
    @keyframes pulse {0% {opacity: 1;} 50% {opacity: 0.5;} 100% {opacity: 1;}}
    .stExpander > div > label {color: #7FDBFF !important;}
    .stCaption {color: #7FDBFF !important;}
</style>
""", unsafe_allow_html=True)

# Sidebar for sport switch and refresh
st.sidebar.title("🦈 PropPulse Controls")
sport = st.sidebar.selectbox("Sport", ["nba", "ncaab"], index=0)
refresh = st.sidebar.button("🔄 Refresh Props")

# Config
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000")

st.title("🦈 PropPulse - NBA Props w/ X Edge")
st.markdown("Live player props adjusted by beat writer tweets. Freemium: Premium for alerts.")

# Fetch props with cache
@st.cache_data(ttl=300)  # 5min cache
def load_props(sport):
    try:
        resp = requests.get(f"{BACKEND_URL}/{sport}/props", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"Backend error: {e}")
        return [{"player": "Error", "prop": "Loading...", "line": 0, "adjusted_prob": 0, "risk_score": 0, "tweets": []}]

props = load_props(sport)
if refresh:
    st.cache_data.clear()
    st.rerun()

if not props or props[0].get('player') == "Error":
    st.error("Backend unavailable—check connection. Defaulting to demo props.")
    props = [{"player": "SGA", "prop": "points", "line": 28.5, "adjusted_prob": 52.1, "risk_score": 0.6, "tweets": [{"text": "SGA full practice - OKC writer", "score": 0.02}]} for _ in range(6)]  # Demo for error state

# HQ Metrics Grid (2 cols, icons, animations)
cols = st.columns(2)
for i, prop in enumerate(props[:6]):
    with cols[i % 2]:
        icon = "🔴" if prop.get('risk_score', 0) > 10 else "🟢"
        st.metric(
            label=f"{icon} {prop.get('player', 'Unknown')} {prop.get('prop', 'Prop').title()}",
            value=f"{prop.get('line', 0)}",
            delta=f"{prop.get('adjusted_prob', 0):.1f}% Adj. Prob"
        )
        risk = prop.get('risk_score', 0)
        if risk > 10:
            st.markdown('<div class="risk-warning">🚨 Risk: {:.1f}% (Injury vibes)</div>'.format(risk), unsafe_allow_html=True)
        with st.expander("Recent Tweets", expanded=risk > 10):  # Expanded for high risk
            for t in prop.get('tweets', [])[:2]:
                st.caption(f"• {t.get('text', 'No text')} (Score: {t.get('score', 0):.2f})")

# Arb Section (Stub with placeholder chart)
st.header("🔍 Arb Opportunities")
if st.button("Scan for Arbs"):
    st.info("No arbs detected—check back soon! (VIP: Full scan + alerts)")
    # Placeholder pie for sentiment (use pd for demo)
    import pandas as pd
    demo_data = pd.DataFrame({'Sentiment': ['Positive', 'Negative'], 'Value': [60, 40]})
    st.bar_chart(demo_data.set_index('Sentiment'))

# Discord CTA
st.markdown("---")
st.info("Join [Sharp Sharks Discord](https://discord.gg/your-link) for VIP alerts via Launchpass!")

# Footer
st.markdown("---")
st.caption("*Powered by FastAPI & Streamlit | Data: TheOddsAPI | Sentiment: HuggingFace*")
