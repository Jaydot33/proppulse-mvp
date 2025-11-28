import streamlit as st
import requests
import os

st.set_page_config(page_title="PropPulse", layout="wide")

# Config
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:5000")

st.title("🦈 PropPulse - NBA Props w/ X Edge")
st.markdown("Live player props adjusted by beat writer tweets. Freemium: Premium for alerts.")

# Fetch props
@st.cache_data(ttl=300)  # 5min cache
def load_props():
    try:
        resp = requests.get(f"{BACKEND_URL}/nba/props")
        return resp.json()
    except:
        return [{"player": "Error", "prop": "Loading...", "line": 0, "adjusted_prob": 0}]

props = load_props()

if st.button("🔄 Refresh Props"):
    st.cache_data.clear()
    st.rerun()

cols = st.columns(2)
for i, prop in enumerate(props[:6]):
    with cols[i % 2]:
        st.metric(
            label=f"{prop['player']} {prop['prop'].title()}",
            value=f"{prop['line']}",
            delta=f"{prop['adjusted_prob']:.1f}% Adj. Prob"
        )
        if prop['risk_score'] > 10:
            st.warning(f"🚨 Risk: {prop['risk_score']:.1f}% (Injury vibes)")
        st.write("**Recent Tweets:**")
        for t in prop['tweets'][:2]:
            st.caption(f"• {t['text']} (Risk: {t['score']:.2f})")

# Arb Section
st.header("🔍 Arb Opportunities")
arbs = st.button("Scan for Arbs")  # Stub—integrate later
if arbs:
    st.info("No arbs detected—check back soon!")

# Discord CTA
st.markdown("---")
st.info("Join [Sharp Sharks Discord](https://discord.gg/your-link) for VIP alerts via Launchpass!")
