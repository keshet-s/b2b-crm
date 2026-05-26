"""B2B CRM — Sourcing Control Panel."""

import os
import sys
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api_client as api

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Sourcing — B2B CRM",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    #MainMenu { visibility: hidden; }
    footer     { visibility: hidden; }
    header     { visibility: hidden; }
    html, body, [class*="css"] { font-family: "Inter", "Segoe UI", sans-serif; }
    [data-testid="metric-container"] {
        background: #f8f9fa; border: 1px solid #e9ecef;
        border-radius: 8px; padding: 8px 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ─────────────────────────────────────────────────────────────

ss = st.session_state
for _k, _v in [
    ("src_session_scored", 0),    # leads scored this Streamlit session
    ("src_session_cost",   0.0),  # estimated USD spent scoring this session
]:
    if _k not in ss:
        ss[_k] = _v

# ── Constants ─────────────────────────────────────────────────────────────────

# Per-lead cost derived from claude_client._COST_INPUT_PER_1K / _COST_OUTPUT_PER_1K
# and get_scoring_cost_estimate: lead_count * 0.003 for Haiku scoring.
_COST_PER_LEAD_USD = 0.003

_STATUS_COLORS = {
    "completed": "🟢",
    "running":   "🟡",
    "failed":    "🔴",
}

# ── Cached loaders ─────────────────────────────────────────────────────────────


@st.cache_data(ttl=30)
def _get_stats() -> dict:
    return api.get_stats()


@st.cache_data(ttl=15)
def _get_scoring_stats() -> dict:
    return api.get_scoring_stats()


@st.cache_data(ttl=15)
def _get_runs(limit: int = 10) -> list:
    result = api.get_sourcing_runs(limit=limit)
    return result if isinstance(result, list) else []


@st.cache_data(ttl=60)
def _get_icp_config() -> dict:
    result = api.get_icp_config()
    return result if "error" not in result else {}


@st.cache_data(ttl=30)
def _get_data_health() -> dict:
    result = api.get_data_health()
    return result if "error" not in result else {}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _fmt_dt(s: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not s:
        return "—"
    try:
        clean = s.replace("Z", "").split("+")[0].split(".")[0]
        return datetime.fromisoformat(clean).strftime(fmt)
    except Exception:
        return s[:16] if s else "—"


def _duration(started: str | None, completed: str | None) -> str:
    if not started or not completed:
        return "—"
    try:
        s = datetime.fromisoformat(started.replace("Z", "").split("+")[0].split(".")[0])
        c = datetime.fromisoformat(completed.replace("Z", "").split("+")[0].split(".")[0])
        secs = int((c - s).total_seconds())
        return f"{secs // 60}m {secs % 60}s" if secs >= 60 else f"{secs}s"
    except Exception:
        return "—"


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🎯 B2B CRM")
    if st.button("← Pipeline", use_container_width=True):
        st.switch_page("pages/01_pipeline.py")
    st.markdown("---")

    stats = _get_stats()
    if "error" not in stats:
        c1, c2 = st.columns(2)
        c1.metric("Total Leads", sum(stats.get("counts_by_status", {}).values()))
        c2.metric("Tier A", stats.get("counts_by_tier", {}).get("A", 0))
    else:
        st.error("Backend not reachable", icon="🔴")

    st.markdown("---")
    st.markdown(f"**Session scoring cost:** `${ss.src_session_cost:.4f}`")
    st.caption(f"Leads scored this session: {ss.src_session_scored}")

# ── Page title ────────────────────────────────────────────────────────────────

st.title("⚡ Sourcing Control Panel")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 1: Run a sourcing job
# ════════════════════════════════════════════════════════════════════════════

st.header("1 · Run a Sourcing Job")

icp_cfg = _get_icp_config()

# ── Current ICP settings (read-only) ─────────────────────────────────────────

with st.expander("📋 Current ICP Settings (read-only)", expanded=False):
    if icp_cfg:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Titles**")
            for t in icp_cfg.get("ICP_TITLES", []) or ["*(none configured)*"]:
                st.markdown(f"- {t}")
            st.markdown("**Locations**")
            for l in icp_cfg.get("ICP_LOCATIONS", []) or ["*(none configured)*"]:
                st.markdown(f"- {l}")
        with c2:
            st.markdown("**Employee range**")
            st.markdown(
                f"{icp_cfg.get('ICP_EMPLOYEE_MIN', '—')} — "
                f"{icp_cfg.get('ICP_EMPLOYEE_MAX', '—')} employees"
            )
            st.markdown("**Industries**")
            for ind in icp_cfg.get("ICP_INDUSTRIES", []) or ["*(none configured)*"]:
                st.markdown(f"- {ind}")
            st.markdown("**Scoring model**")
            st.markdown(f"`{icp_cfg.get('ANTHROPIC_MODEL_SCORING', '—')}`")
    else:
        st.warning("Could not load ICP config — backend may be unreachable.")

st.markdown("---")

# ── Sourcing run form ─────────────────────────────────────────────────────────

default_titles = icp_cfg.get("ICP_TITLES") or []
default_locs   = icp_cfg.get("ICP_LOCATIONS") or []
default_emp_min = int(icp_cfg.get("ICP_EMPLOYEE_MIN") or 50)
default_emp_max = int(icp_cfg.get("ICP_EMPLOYEE_MAX") or 500)

# Multiselect needs a non-empty options list
title_options = default_titles or ["VP of Engineering", "Head of Engineering", "CTO", "Director of Engineering", "Head of Product"]
loc_options   = default_locs   or ["Israel", "Germany", "United Kingdom", "United States", "Australia", "New Zealand"]

with st.form("sourcing_form"):
    fc1, fc2 = st.columns(2)

    with fc1:
        st.markdown("**Job Titles** (deselect to exclude, or use all)")
        sel_titles = st.multiselect(
            "Titles", options=title_options, default=title_options,
            label_visibility="collapsed",
        )
        extra_title = st.text_input(
            "Add a custom title", placeholder="e.g. Training Manager"
        )

        emp_c1, emp_c2 = st.columns(2)
        emp_min = emp_c1.number_input("Employee min", min_value=1, value=default_emp_min)
        emp_max = emp_c2.number_input("Employee max", min_value=1, value=default_emp_max)

    with fc2:
        st.markdown("**Locations** (deselect to exclude, or use all)")
        sel_locs = st.multiselect(
            "Locations", options=loc_options, default=loc_options,
            label_visibility="collapsed",
        )
        extra_loc = st.text_input(
            "Add a custom location", placeholder="e.g. Singapore"
        )

        pages = st.slider(
            "Pages to fetch", min_value=1, max_value=5, value=1,
            help="1 page = up to 100 leads from Apollo",
        )
        st.info(f"📊 Estimated new leads: up to **{pages * 100}**  (pages × 100 capacity)", icon="ℹ️")

    run_btn = st.form_submit_button("🚀 Start Sourcing Run", type="primary", use_container_width=True)

if run_btn:
    all_titles = sel_titles + ([extra_title.strip()] if extra_title.strip() else [])
    all_locs   = sel_locs   + ([extra_loc.strip()]   if extra_loc.strip()   else [])

    body: dict = {"pages": pages}
    if all_titles:
        body["titles"] = all_titles
    if all_locs:
        body["locations"] = all_locs
    body["employee_min"] = int(emp_min)
    body["employee_max"] = int(emp_max)

    with st.status("Running sourcing job…", expanded=True) as status:
        st.write(f"🔍 Searching Apollo — {pages} page(s), {len(all_titles)} title(s), {len(all_locs)} location(s)…")
        result = api._post("/api/sourcing/run", json=body)

        if isinstance(result, dict) and "error" in result:
            status.update(label="Sourcing failed", state="error", expanded=True)
            st.error(f"Error: {result['error']}")
        else:
            found = result.get("leads_found", 0)
            new   = result.get("leads_new", 0)
            st.write(f"✅ Done — **{found}** leads found, **{new}** new leads added to pipeline")
            st.write(f"⏱ Run ID: `{result.get('id')}`  ·  Status: `{result.get('status')}`")
            status.update(label=f"Complete — {new} new leads", state="complete", expanded=False)
            st.cache_data.clear()

# ════════════════════════════════════════════════════════════════════════════
# SECTION 2: Recent Sourcing Runs
# ════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.header("2 · Recent Sourcing Runs")

if st.button("🔄 Refresh Runs", key="refresh_runs"):
    st.cache_data.clear()
    st.rerun()

runs = _get_runs(limit=10)

if not runs:
    st.info("No sourcing runs yet. Start one above.")
else:
    import pandas as pd

    rows = []
    for r in runs:
        status_icon = _STATUS_COLORS.get(r.get("status", ""), "⚪")
        rows.append({
            "ID":        r.get("id"),
            "Started":   _fmt_dt(r.get("started_at")),
            "Status":    f"{status_icon} {r.get('status', '—')}",
            "Found":     r.get("leads_found", 0),
            "New":       r.get("leads_new", 0),
            "Duration":  _duration(r.get("started_at"), r.get("completed_at")),
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "ID":     st.column_config.NumberColumn("ID",    width="small", format="%d"),
            "Found":  st.column_config.NumberColumn("Found", width="small"),
            "New":    st.column_config.NumberColumn("New",   width="small"),
        },
    )

    # Failed run error details
    failed = [r for r in runs if r.get("status") == "failed" and r.get("error_message")]
    if failed:
        st.markdown("**Failed Run Details**")
        for r in failed:
            with st.expander(f"Run #{r['id']} — {_fmt_dt(r.get('started_at'))}"):
                st.error(r.get("error_message", "No error message stored."))

# ════════════════════════════════════════════════════════════════════════════
# SECTION 3: Score Management
# ════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.header("3 · Score Management")

scoring_stats = _get_scoring_stats()

sc_col, chart_col = st.columns([1, 1])

with sc_col:
    scored   = scoring_stats.get("scored_count", 0)
    unscored = scoring_stats.get("unscored_count", 0)
    total    = scored + unscored
    pct      = int(scored / total * 100) if total else 0

    st.markdown(f"**Coverage:** {scored} / {total} scored ({pct}%)")
    st.progress(pct / 100)
    st.markdown("")

    score_limit = st.number_input(
        "Leads to score per run", min_value=1, max_value=500, value=50, step=10
    )

    if st.button(
        f"🤖 Score Unscored ({unscored} pending)", type="primary", use_container_width=True
    ):
        with st.spinner(f"Scoring up to {score_limit} leads with Claude…"):
            result = api.score_unscored(limit=int(score_limit))
        if isinstance(result, dict) and "error" in result:
            st.error(result["error"])
        else:
            n_scored = result.get("scored_count", 0)
            n_errors = result.get("errors_count", 0)
            ss.src_session_scored += n_scored
            ss.src_session_cost   += n_scored * _COST_PER_LEAD_USD
            st.success(f"✅ Scored **{n_scored}** leads  ·  {n_errors} errors")
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")
    st.markdown("**💰 Session Cost Tracker**")
    st.metric("Leads scored (session)", ss.src_session_scored)
    st.metric(
        "Estimated spend (session)",
        f"${ss.src_session_cost:.4f}",
        help=f"~${_COST_PER_LEAD_USD}/lead (Claude Haiku scoring)",
    )
    if ss.src_session_scored > 0 and st.button("Reset session counter", key="reset_cost"):
        ss.src_session_scored = 0
        ss.src_session_cost   = 0.0
        st.rerun()

    # Last scored timestamp
    last_scored = scoring_stats.get("last_scored_at")
    if last_scored:
        st.caption(f"Last scored: {_fmt_dt(last_scored)}")
    avg = scoring_stats.get("avg_score_tier_a")
    if avg:
        st.caption(f"Avg Tier A score: {avg}")

with chart_col:
    tier_dist: dict = scoring_stats.get("tier_distribution", {})
    # Filter out zero-value tiers so the donut is readable
    tier_data = {k: v for k, v in tier_dist.items() if v > 0}

    if tier_data:
        _TIER_COLORS = {"A": "#28a745", "B": "#007bff", "C": "#adb5bd", "D": "#dc3545"}
        labels = list(tier_data.keys())
        values = list(tier_data.values())
        colors = [_TIER_COLORS.get(t, "#6c757d") for t in labels]

        fig = go.Figure(go.Pie(
            labels=[f"Tier {t}" for t in labels],
            values=values,
            hole=0.55,
            marker_colors=colors,
            textinfo="label+percent",
            hovertemplate="<b>Tier %{label}</b><br>Count: %{value}<extra></extra>",
        ))
        fig.update_layout(
            title={"text": "Tier Distribution", "x": 0.5, "font": {"size": 14}},
            height=300,
            margin=dict(l=10, r=10, t=40, b=10),
            font=dict(family="Inter, Segoe UI, sans-serif"),
            paper_bgcolor="rgba(0,0,0,0)",
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No scored leads yet — run scoring first.")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 4: Data Health
# ════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.header("4 · Data Health")

health_col, action_col = st.columns([2, 1])

with health_col:
    dh = _get_data_health()

    if dh:
        total    = dh.get("total", 0)
        with_em  = dh.get("with_email", 0)
        without_em = dh.get("without_email", 0)
        verified = dh.get("verified_email", 0)
        scored   = dh.get("scored", 0)
        unscored = dh.get("unscored", 0)
        with_hook = dh.get("with_hook", 0)
        stale    = dh.get("stale_30d", 0)
        db_bytes = dh.get("db_size_bytes", 0)

        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        r1c1.metric("Total Leads",      total)
        r1c2.metric("With Email",        with_em,  delta=f"{int(with_em/total*100) if total else 0}%", delta_color="off")
        r1c3.metric("Verified Email",    verified)
        r1c4.metric("No Email",          without_em)

        r2c1, r2c2, r2c3, r2c4 = st.columns(4)
        r2c1.metric("Scored",            scored)
        r2c2.metric("Unscored",          unscored)
        r2c3.metric("With Hook",         with_hook)
        r2c4.metric("Stale > 30d",       stale,    delta=None if stale == 0 else f"⚠️")

        if db_bytes:
            db_mb = db_bytes / 1_048_576
            st.caption(f"Database size: {db_mb:.2f} MB")

        # Coverage bars
        if total:
            st.markdown("**Coverage at a glance**")
            prog_col1, prog_col2 = st.columns(2)
            with prog_col1:
                st.caption(f"Email coverage: {with_em}/{total}")
                st.progress(with_em / total)
                st.caption(f"Scored: {scored}/{total}")
                st.progress(scored / total)
            with prog_col2:
                st.caption(f"Verified email: {verified}/{total}")
                st.progress(verified / total)
                st.caption(f"Hook written: {with_hook}/{total}")
                st.progress(with_hook / total)
    else:
        st.warning("Could not load data health — backend may be unreachable.")

    if st.button("🔄 Refresh Health Stats", key="refresh_health"):
        st.cache_data.clear()
        st.rerun()

with action_col:
    st.markdown("**🔬 Bulk Enrichment**")
    st.markdown(
        "Enrich up to 10 Tier A leads that are missing a verified email. "
        "Consumes Apollo credits."
    )
    if st.button("🔬 Enrich Tier A (no email)", use_container_width=True, key="enrich_a"):
        with st.spinner("Enriching via Apollo…"):
            result = api.enrich_tier_a()
        if isinstance(result, dict) and "error" in result:
            st.error(result["error"])
        else:
            enriched = result.get("enriched", 0)
            ids      = result.get("leads", [])
            st.success(f"✅ Enriched {enriched} lead(s)")
            if ids:
                st.caption(f"Lead IDs: {', '.join(str(i) for i in ids[:10])}")
            st.cache_data.clear()
            st.rerun()

    st.markdown("---")
    st.markdown("**📊 Score unscored — quick**")
    if st.button("🤖 Score 10 now", use_container_width=True, key="score_10"):
        with st.spinner("Scoring…"):
            result = api.score_unscored(limit=10)
        if isinstance(result, dict) and "error" in result:
            st.error(result["error"])
        else:
            n = result.get("scored_count", 0)
            ss.src_session_scored += n
            ss.src_session_cost   += n * _COST_PER_LEAD_USD
            st.success(f"Scored {n} leads")
            st.cache_data.clear()
            st.rerun()
