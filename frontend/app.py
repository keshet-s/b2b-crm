"""
B2B CRM — Streamlit frontend (entry point)

This file is the Streamlit app root. Run with:
    streamlit run app.py
"""

import os

import httpx
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="B2B CRM",
    page_icon="🎯",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30)
def fetch_stats() -> dict | None:
    try:
        r = httpx.get(f"{BACKEND_URL}/api/stats", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        return {"error": str(exc)}


@st.cache_data(ttl=10)
def check_health() -> bool:
    try:
        r = httpx.get(f"{BACKEND_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🎯 B2B CRM")
    st.markdown("---")

    healthy = check_health()
    if healthy:
        st.success("API connected", icon="✅")
    else:
        st.error("API unreachable", icon="🔴")

    st.markdown("---")
    st.caption(f"Backend: `{BACKEND_URL}`")

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

st.title("Pipeline Overview")

stats = fetch_stats()

if stats is None:
    st.warning("Could not load stats — backend may still be starting up.")
elif "error" in stats:
    st.error(f"Backend error: {stats['error']}")
else:
    counts_by_status: dict = stats.get("counts_by_status", {})
    counts_by_tier: dict  = stats.get("counts_by_tier", {})
    recent_activity: int  = stats.get("recent_activity_count", 0)

    total_leads = sum(counts_by_status.values())

    # --- Top-line metrics ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Leads",        total_leads)
    col2.metric("Tier A Leads",        counts_by_tier.get("A", 0))
    col3.metric("Tier B Leads",        counts_by_tier.get("B", 0))
    col4.metric("Activities (7 days)", recent_activity)

    st.markdown("---")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Leads by pipeline status")
        if counts_by_status:
            import pandas as pd
            df_status = pd.DataFrame(
                counts_by_status.items(), columns=["Status", "Count"]
            ).sort_values("Count", ascending=False)
            st.dataframe(df_status, use_container_width=True, hide_index=True)
        else:
            st.info("No leads yet — run a sourcing job to populate the pipeline.")

    with col_right:
        st.subheader("Leads by ICP tier")
        if counts_by_tier:
            import pandas as pd
            df_tier = pd.DataFrame(
                counts_by_tier.items(), columns=["Tier", "Count"]
            ).sort_values("Tier")
            st.dataframe(df_tier, use_container_width=True, hide_index=True)
        else:
            st.info("No scored leads yet — run the ICP scoring job first.")

st.markdown("---")
st.caption("More pages coming soon: Leads, Companies, Sourcing runs, Settings.")
