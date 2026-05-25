"""
B2B CRM — Streamlit frontend (entry point)

Run with:
    streamlit run app.py
"""

import streamlit as st

import api_client as api

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="B2B CRM",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Global CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    /* Hide default Streamlit chrome */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Base font */
    html, body, [class*="css"] {
        font-family: "Inter", "Segoe UI", sans-serif;
    }

    /* Metric card subtlety */
    [data-testid="metric-container"] {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 12px 16px;
    }

    /* Tier badge helpers — applied via st.markdown */
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 600;
        letter-spacing: 0.04em;
    }
    .badge-A { background: #d4edda; color: #155724; }
    .badge-B { background: #cce5ff; color: #004085; }
    .badge-C { background: #e2e3e5; color: #383d41; }
    .badge-D { background: #f8d7da; color: #721c24; }

    /* Sidebar section header */
    .sidebar-section {
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        color: #6c757d;
        text-transform: uppercase;
        margin: 12px 0 4px;
    }

    /* Connection error banner */
    .error-banner {
        background: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 6px;
        padding: 10px 16px;
        color: #721c24;
        margin-bottom: 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PAGES = [
    ("📊 Pipeline", "pipeline"),
    ("🔍 Lead Detail", "lead_detail"),
    ("⚡ Sourcing", "sourcing"),
    ("📈 Analytics", "analytics"),
    ("⚙️ Settings", "settings"),
]

TIER_COLORS = {"A": "badge-A", "B": "badge-B", "C": "badge-C", "D": "badge-D"}


def tier_badge(tier: str | None) -> str:
    if not tier:
        return "<span class='badge badge-C'>—</span>"
    cls = TIER_COLORS.get(tier, "badge-C")
    return f"<span class='badge {cls}'>{tier}</span>"


@st.cache_data(ttl=30)
def _cached_stats() -> dict:
    return api.get_stats()


@st.cache_data(ttl=30)
def _cached_pipeline_summary() -> dict:
    return api.get_pipeline_summary()


def _backend_ok(stats: dict) -> bool:
    return "error" not in stats


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🎯 B2B CRM")
    st.markdown("---")

    # Live stats ticker
    stats = _cached_stats()
    backend_alive = _backend_ok(stats)

    st.markdown("<div class='sidebar-section'>Live Stats</div>", unsafe_allow_html=True)

    if backend_alive:
        counts_by_tier: dict = stats.get("counts_by_tier", {})
        counts_by_status: dict = stats.get("counts_by_status", {})
        total_leads = sum(counts_by_status.values())
        tier_a_count = counts_by_tier.get("A", 0)

        summary = _cached_pipeline_summary()
        tier_a_uncontacted = summary.get("tier_a_uncontacted", 0) if _backend_ok(summary) else "—"
        overdue_followups = summary.get("overdue_followups", 0) if _backend_ok(summary) else "—"

        col1, col2 = st.columns(2)
        col1.metric("Total Leads", total_leads)
        col2.metric("Tier A", tier_a_count)
        col3, col4 = st.columns(2)
        col3.metric("Uncontacted A", tier_a_uncontacted)
        col4.metric("Overdue", overdue_followups)
    else:
        st.warning("Stats unavailable", icon="⚠️")

    st.markdown("---")

    # Navigation
    st.markdown("<div class='sidebar-section'>Navigation</div>", unsafe_allow_html=True)
    page_labels = [p[0] for p in PAGES]
    selection = st.radio(
        "Go to",
        page_labels,
        label_visibility="collapsed",
    )
    current_page = dict(PAGES)[selection]

    st.markdown("---")
    st.caption(f"Backend: `{api.BACKEND_URL}`")

# ---------------------------------------------------------------------------
# Connection error banner
# ---------------------------------------------------------------------------

if not backend_alive:
    st.markdown(
        "<div class='error-banner'>"
        "⚠️ <strong>Backend not reachable.</strong> "
        "Make sure the API server is running at "
        f"<code>{api.BACKEND_URL}</code>."
        "</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def page_pipeline():
    st.title("📊 Pipeline Overview")

    if not backend_alive:
        st.info("Connect the backend to view pipeline data.")
        return

    summary = _cached_pipeline_summary()
    if not _backend_ok(summary):
        st.error(f"Could not load pipeline: {summary.get('error')}")
        return

    stages = summary.get("stages", [])
    total = summary.get("total_leads", 0)
    tier_a_uncontacted = summary.get("tier_a_uncontacted", 0)
    overdue = summary.get("overdue_followups", 0)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Leads", total)
    col2.metric("Tier A Uncontacted", tier_a_uncontacted)
    col3.metric("Overdue Followups", overdue)

    st.markdown("---")
    st.subheader("Pipeline Stages")

    if stages:
        import pandas as pd

        df = pd.DataFrame(stages)[["label", "count", "tier_a_count"]]
        df.columns = ["Stage", "Total", "Tier A"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No leads yet — run a sourcing job to populate the pipeline.")


def page_lead_detail():
    st.title("🔍 Lead Detail")

    lead_id = st.number_input("Lead ID", min_value=1, step=1, value=1)

    if st.button("Load Lead"):
        lead = api.get_lead(int(lead_id))
        if "error" in lead:
            st.error(f"Error: {lead['error']}")
            return

        st.session_state["loaded_lead"] = lead

    lead = st.session_state.get("loaded_lead")
    if not lead:
        return

    company = lead.get("company") or {}
    tier = lead.get("icp_tier")

    # Header row
    col_name, col_tier, col_status = st.columns([3, 1, 1])
    col_name.markdown(f"### {lead.get('full_name', '—')}")
    col_tier.markdown(tier_badge(tier), unsafe_allow_html=True)
    col_status.markdown(f"`{lead.get('status', '—')}`")

    st.markdown(f"**Title:** {lead.get('title', '—')}  |  **Email:** {lead.get('email', '—')}")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### Lead Info")
        st.json(
            {
                "ICP Score": lead.get("icp_score"),
                "Tier": lead.get("icp_tier"),
                "Source": lead.get("source"),
                "Next Action Due": lead.get("next_action_due"),
                "Last Contacted": lead.get("last_contacted_at"),
                "LinkedIn": lead.get("linkedin_url"),
            }
        )

    with col_right:
        st.markdown("#### Company")
        if company:
            st.json(
                {
                    "Name": company.get("name"),
                    "Domain": company.get("domain"),
                    "Industry": company.get("industry"),
                    "Employees": company.get("employee_count"),
                    "Country": company.get("hq_country"),
                }
            )
        else:
            st.info("No company linked.")

    if lead.get("personalized_hook"):
        st.markdown("#### Personalized Hook")
        st.info(lead["personalized_hook"])

    if lead.get("icp_reasoning"):
        with st.expander("ICP Reasoning"):
            st.write(lead["icp_reasoning"])

    st.markdown("---")
    st.subheader("Quick Actions")
    action_col1, action_col2, action_col3 = st.columns(3)

    with action_col1:
        if st.button("🔄 Re-score"):
            result = api.score_lead(int(lead_id))
            if "error" in result:
                st.error(result["error"])
            else:
                st.success(f"Scored: Tier {result.get('icp_tier')} ({result.get('icp_score')}/100)")
                st.session_state["loaded_lead"] = result

    with action_col2:
        if st.button("✉️ Gen Hook"):
            result = api.generate_hook(int(lead_id))
            if "error" in result:
                st.error(result["error"])
            else:
                st.success("Hook generated")
                st.session_state["loaded_lead"]["personalized_hook"] = result.get("hook")

    with action_col3:
        if st.button("🔎 Enrich"):
            result = api.enrich_lead(int(lead_id))
            if "error" in result:
                st.error(result["error"])
            else:
                st.success(f"Enriched — email: {result.get('email', '—')}")
                st.session_state["loaded_lead"] = result

    st.markdown("---")
    st.subheader("Status Update")
    statuses = [
        "identified", "enriched", "contacted", "engaged",
        "qualified", "meeting_held", "design_partner",
        "closed_won", "closed_lost", "archived",
    ]
    new_status = st.selectbox("New Status", statuses, index=statuses.index(lead.get("status", "identified")) if lead.get("status") in statuses else 0)
    if st.button("Update Status"):
        result = api.update_lead(int(lead_id), {"status": new_status})
        if "error" in result:
            st.error(result["error"])
        else:
            st.success(f"Status updated to {new_status}")
            st.session_state["loaded_lead"] = result

    st.markdown("---")
    st.subheader("Activity Log")
    activities = api.get_activities(int(lead_id))
    if isinstance(activities, dict) and "error" in activities:
        st.error(activities["error"])
    elif activities:
        import pandas as pd

        df = pd.DataFrame(activities)[["occurred_at", "type", "channel", "content_snippet"]]
        df.columns = ["When", "Type", "Channel", "Snippet"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No activities recorded yet.")

    with st.expander("Log New Activity"):
        act_type = st.selectbox("Type", ["email_sent", "call", "note", "meeting", "linkedin"])
        act_channel = st.text_input("Channel (optional)")
        act_content = st.text_area("Content")
        if st.button("Log Activity"):
            result = api.post_activity(
                lead_id=int(lead_id),
                type=act_type,
                content=act_content,
                channel=act_channel or None,
            )
            if "error" in result:
                st.error(result["error"])
            else:
                st.success("Activity logged")


def page_sourcing():
    st.title("⚡ Sourcing")

    col_run, col_history = st.columns([1, 1])

    with col_run:
        st.subheader("New Sourcing Run")
        pages = st.slider("Pages to fetch", 1, 10, 1)
        titles_raw = st.text_area(
            "Job titles (one per line, blank = use ICP defaults)",
            height=100,
        )
        locations_raw = st.text_area(
            "Locations (one per line, blank = use ICP defaults)",
            height=80,
        )

        if st.button("🚀 Run Sourcing", type="primary"):
            titles = [t.strip() for t in titles_raw.splitlines() if t.strip()] or None
            locations = [l.strip() for l in locations_raw.splitlines() if l.strip()] or None

            with st.spinner("Sourcing in progress…"):
                result = api.run_sourcing(pages=pages, titles=titles, locations=locations)

            if "error" in result:
                st.error(result["error"])
            else:
                st.success(
                    f"Run complete — found: {result.get('leads_found', 0)}, "
                    f"new: {result.get('leads_new', 0)}"
                )

        st.markdown("---")
        st.subheader("Bulk Score Unscored")
        score_limit = st.number_input("Max leads to score", min_value=1, max_value=500, value=50)
        if st.button("⚡ Score Unscored"):
            with st.spinner("Scoring…"):
                result = api.score_unscored(limit=int(score_limit))
            if "error" in result:
                st.error(result["error"])
            else:
                st.success(
                    f"Scored {result.get('scored', 0)} leads "
                    f"({result.get('failed', 0)} failed)"
                )

    with col_history:
        st.subheader("Recent Sourcing Runs")
        runs = api.get_sourcing_runs(limit=10)
        if isinstance(runs, dict) and "error" in runs:
            st.error(runs["error"])
        elif runs:
            import pandas as pd

            df = pd.DataFrame(runs)[
                ["id", "status", "leads_found", "leads_new", "started_at", "completed_at"]
            ]
            df.columns = ["ID", "Status", "Found", "New", "Started", "Completed"]
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No sourcing runs yet.")


def page_analytics():
    st.title("📈 Analytics")

    if not backend_alive:
        st.info("Connect the backend to view analytics.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Pipeline Overview")
        counts_by_status: dict = stats.get("counts_by_status", {})
        if counts_by_status:
            import pandas as pd

            df = (
                pd.DataFrame(counts_by_status.items(), columns=["Status", "Count"])
                .sort_values("Count", ascending=False)
            )
            st.bar_chart(df.set_index("Status"))
        else:
            st.info("No data yet.")

    with col2:
        st.subheader("ICP Tier Distribution")
        counts_by_tier: dict = stats.get("counts_by_tier", {})
        if counts_by_tier:
            import pandas as pd

            df = (
                pd.DataFrame(counts_by_tier.items(), columns=["Tier", "Count"])
                .sort_values("Tier")
            )
            st.bar_chart(df.set_index("Tier"))
        else:
            st.info("No scored leads yet.")

    st.markdown("---")
    st.subheader("Scoring Stats")
    scoring_stats = api.get_scoring_stats()
    if "error" in scoring_stats:
        st.error(scoring_stats["error"])
    else:
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Scored", scoring_stats.get("scored_count", 0))
        s2.metric("Unscored", scoring_stats.get("unscored_count", 0))
        s3.metric("Avg Score (Tier A)", scoring_stats.get("avg_score_tier_a") or "—")
        tier_dist = scoring_stats.get("tier_distribution", {})
        s4.metric("Tier A", tier_dist.get("A", 0))


def page_settings():
    st.title("⚙️ Settings")
    st.info(
        "Runtime configuration is managed via environment variables. "
        "See the project README for available options."
    )
    st.markdown("#### Current Configuration")
    st.json({"BACKEND_URL": api.BACKEND_URL})

    st.markdown("---")
    st.subheader("Backend Health")
    if st.button("Check Connection"):
        result = api.get_stats()
        if "error" in result:
            st.error(f"Unreachable: {result['error']}")
        else:
            st.success(f"Connected — total leads: {sum(result.get('counts_by_status', {}).values())}")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_ROUTES = {
    "pipeline": page_pipeline,
    "lead_detail": page_lead_detail,
    "sourcing": page_sourcing,
    "analytics": page_analytics,
    "settings": page_settings,
}

_ROUTES[current_page]()
