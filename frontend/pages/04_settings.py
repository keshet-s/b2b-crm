"""B2B CRM — Settings & API Status."""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api_client as api

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Settings — B2B CRM",
    page_icon="⚙️",
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
    .api-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 10px;
    }
    .stage-def {
        background: #f8f9fa;
        border-left: 3px solid #dee2e6;
        padding: 8px 14px;
        margin: 4px 0;
        border-radius: 0 6px 6px 0;
        font-size: 0.9rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_COST_PER_LEAD_USD = 0.003   # from claude_client.get_scoring_cost_estimate

# ── Session state ─────────────────────────────────────────────────────────────

ss = st.session_state
for _k, _v in [
    ("cfg_apollo_status",    None),   # result of last Apollo test
    ("cfg_anthropic_status", None),   # result of last Anthropic test
]:
    if _k not in ss:
        ss[_k] = _v

# ── Pipeline stage reference data ─────────────────────────────────────────────

STAGE_DEFS = [
    (
        "identified", "Identified",
        "Lead sourced from Apollo but not yet enriched or contacted.",
        "Entry: Apollo sourcing run completes.",
        "Exit: Email enriched OR first outreach sent.",
    ),
    (
        "enriched", "Enriched",
        "Apollo People Match has returned a verified email address.",
        "Entry: Enrich Email action completes with a verified result.",
        "Exit: First outreach email sent.",
    ),
    (
        "contacted", "Contacted",
        "At least one outreach attempt has been logged (email, LinkedIn, or call).",
        "Entry: Mark Contacted action or email_sent activity logged.",
        "Exit: Lead replies or engages with content.",
    ),
    (
        "engaged", "Engaged",
        "Lead has responded positively — replied to email, accepted connection, booked intro call.",
        "Entry: Positive reply or LinkedIn acceptance logged.",
        "Exit: Qualification criteria confirmed.",
    ),
    (
        "qualified", "Qualified",
        "BANT criteria confirmed: Budget, Authority, Need, Timeline are clear.",
        "Entry: Qualification call completed and logged.",
        "Exit: Demo or design-partner proposal sent.",
    ),
    (
        "meeting_held", "Meeting Held",
        "Full demo or discovery call completed.",
        "Entry: Meeting or demo activity logged.",
        "Exit: Design-partner agreement or proposal sent.",
    ),
    (
        "design_partner", "Design Partner",
        "Lead has agreed to participate as a design partner (paid or unpaid pilot).",
        "Entry: Design-partner agreement signed or verbally confirmed.",
        "Exit: Contract signed (Closed Won) or pilot abandoned (Closed Lost).",
    ),
    (
        "closed_won", "Closed Won ✅",
        "Contract signed, deal is live.",
        "Entry: Signed contract received.",
        "Exit: N/A (terminal stage).",
    ),
    (
        "closed_lost", "Closed Lost ❌",
        "Lead declined, churned, or went unresponsive after qualification.",
        "Entry: Explicit rejection, 3× no-reply after follow-up, or disqualified.",
        "Exit: Re-engage to Identified if circumstances change.",
    ),
    (
        "archived", "Archived",
        "Soft-deleted: lead is excluded from active pipeline views.",
        "Entry: Archive action or D-tier disqualification.",
        "Exit: Restore to Identified if relevant.",
    ),
]

# ── Cached loaders ─────────────────────────────────────────────────────────────


@st.cache_data(ttl=60)
def _get_stats() -> dict:
    return api.get_stats()


@st.cache_data(ttl=30)
def _get_icp_config() -> dict:
    result = api.get_icp_config()
    return result if "error" not in result else {}


@st.cache_data(ttl=120)
def _get_icp_prompt() -> dict:
    return api.get_icp_prompt()


@st.cache_data(ttl=30)
def _get_data_health() -> dict:
    result = api.get_data_health()
    return result if "error" not in result else {}


@st.cache_data(ttl=60)
def _get_scoring_stats() -> dict:
    return api.get_scoring_stats()


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🎯 B2B CRM")
    if st.button("← Pipeline", use_container_width=True):
        st.switch_page("pages/01_pipeline.py")
    st.markdown("---")

    stats = _get_stats()
    if "error" not in stats:
        c1, c2 = st.columns(2)
        c1.metric("Total", sum(stats.get("counts_by_status", {}).values()))
        c2.metric("Tier A", stats.get("counts_by_tier", {}).get("A", 0))
    else:
        st.error("Backend not reachable", icon="🔴")

    st.markdown("---")
    st.caption(f"Backend: `{api.BACKEND_URL}`")

# ── Page ──────────────────────────────────────────────────────────────────────

st.title("⚙️ Settings & API Status")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 1: API Key Status
# ════════════════════════════════════════════════════════════════════════════

st.header("1 · API Key Status")
st.caption("Keys are read from environment variables — values are never displayed here.")

# Fetch configuration status (booleans only — no secrets)
key_status = api.get_api_key_status()
keys_ok = "error" not in key_status

_CONFIGURED = "✅ Configured"
_MISSING     = "⚠️ Not configured"
_ERROR       = "❌ Error"

def _cfg_badge(configured: bool) -> str:
    return _CONFIGURED if configured else _MISSING


api_c1, api_c2 = st.columns(2)

# ── Apollo ────────────────────────────────────────────────────────────────────

with api_c1:
    with st.container():
        st.markdown("#### 🔭 Apollo.io")
        if keys_ok:
            apollo_cfg = key_status.get("apollo", False)
            st.markdown(f"**Config status:** {_cfg_badge(apollo_cfg)}")
        else:
            st.warning("Could not reach backend to check key status.")
            apollo_cfg = False

        if st.button("Test Apollo Connection", use_container_width=True, key="test_apollo"):
            with st.spinner("Testing Apollo API…"):
                result = api.get_apollo_usage()
            if "error" in result:
                st.error(f"❌ {result['error']}")
                ss.cfg_apollo_status = ("error", result["error"])
            else:
                st.success("✅ Apollo reachable")
                ss.cfg_apollo_status = ("ok", result)

        if ss.cfg_apollo_status:
            st_val, data = ss.cfg_apollo_status
            if st_val == "ok" and isinstance(data, dict):
                with st.expander("Usage details"):
                    st.json(data)

# ── Anthropic ─────────────────────────────────────────────────────────────────

with api_c2:
    with st.container():
        st.markdown("#### 🤖 Anthropic (Claude)")
        if keys_ok:
            anth_cfg = key_status.get("anthropic", False)
            st.markdown(f"**Config status:** {_cfg_badge(anth_cfg)}")
        else:
            anth_cfg = False

        icp_cfg = _get_icp_config()
        if icp_cfg:
            st.markdown(f"**Scoring model:** `{icp_cfg.get('ANTHROPIC_MODEL_SCORING', '—')}`")
            st.markdown(f"**Writing model:**  `{icp_cfg.get('ANTHROPIC_MODEL_WRITING', '—')}`")

        if st.button("Test Anthropic (via scoring stats)", use_container_width=True, key="test_anth"):
            with st.spinner("Calling backend scoring endpoint…"):
                result = api.get_scoring_stats()
            if "error" in result:
                st.error(f"❌ {result['error']}")
                ss.cfg_anthropic_status = "error"
            else:
                st.success("✅ Backend scoring endpoint reachable")
                ss.cfg_anthropic_status = "ok"

api_c3, api_c4 = st.columns(2)

# ── Hunter ────────────────────────────────────────────────────────────────────

with api_c3:
    with st.container():
        st.markdown("#### 🎯 Hunter.io")
        if keys_ok:
            hunter_cfg = key_status.get("hunter", False)
            st.markdown(f"**Config status:** {_cfg_badge(hunter_cfg)}")
            if not hunter_cfg:
                st.caption("Set `HUNTER_API_KEY` env var to enable email verification.")
        else:
            st.markdown(f"**Config status:** {_MISSING}")

# ── Slack ─────────────────────────────────────────────────────────────────────

with api_c4:
    with st.container():
        st.markdown("#### 💬 Slack")
        if keys_ok:
            slack_cfg = key_status.get("slack", False)
            st.markdown(f"**Config status:** {_cfg_badge(slack_cfg)}")
            if not slack_cfg:
                st.caption("Set `SLACK_WEBHOOK_URL` env var to enable Tier A/B notifications.")
        else:
            st.markdown(f"**Config status:** {_MISSING}")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 2: ICP Configuration
# ════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.header("2 · ICP Configuration")

cfg_left, cfg_right = st.columns([1, 1])

with cfg_left:
    st.subheader("Current Settings")
    icp = _get_icp_config()

    if icp:
        st.markdown("**Target Job Titles**")
        titles = icp.get("ICP_TITLES") or []
        if titles:
            for t in titles:
                st.markdown(f"- {t}")
        else:
            st.caption("*(not configured — set `ICP_TITLES` env var)*")

        st.markdown("**Target Locations**")
        locs = icp.get("ICP_LOCATIONS") or []
        if locs:
            for l in locs:
                st.markdown(f"- {l}")
        else:
            st.caption("*(not configured — set `ICP_LOCATIONS` env var)*")

        st.markdown("**Target Industries**")
        inds = icp.get("ICP_INDUSTRIES") or []
        if inds:
            for i in inds:
                st.markdown(f"- {i}")
        else:
            st.caption("*(not configured)*")

        emp_min = icp.get("ICP_EMPLOYEE_MIN", "—")
        emp_max = icp.get("ICP_EMPLOYEE_MAX", "—")
        st.markdown(f"**Employee Range:** {emp_min} – {emp_max}")
    else:
        st.warning("Could not load ICP config — backend may be unreachable.")

    st.markdown("---")
    st.markdown("**To update these settings:**")
    st.markdown(
        "1. Edit the `.env` file (or your Docker `environment:` block)\n"
        "2. Set values like: `ICP_TITLES=VP of Engineering,CTO`\n"
        "3. Restart the container: `docker compose restart backend`"
    )

with cfg_right:
    st.subheader("ICP Scoring Prompt")

    if st.button("🔄 Reload prompt", key="reload_prompt"):
        st.cache_data.clear()

    prompt_data = _get_icp_prompt()

    if "error" in prompt_data and prompt_data["error"]:
        st.error(f"Could not load prompt: {prompt_data['error']}")
    elif prompt_data.get("content"):
        st.caption(f"Path: `{prompt_data.get('path', '—')}`")
        with st.expander("View full prompt", expanded=False):
            st.code(prompt_data["content"], language="markdown")
        char_count = len(prompt_data["content"])
        line_count = prompt_data["content"].count("\n") + 1
        st.caption(f"{line_count} lines · {char_count:,} characters")
    else:
        st.info("Prompt file is empty or could not be read.")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 3: Pipeline Stage Reference
# ════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.header("3 · Pipeline Stage Reference")

st.caption(
    "Hover over a stage to see entry and exit criteria. "
    "This is a read-only reference — stages are defined in the codebase."
)

for status, label, definition, entry, exit_ in STAGE_DEFS:
    with st.expander(f"`{status}` — **{label}**"):
        st.markdown(f"{definition}")
        col_e, col_x = st.columns(2)
        with col_e:
            st.markdown(f"**Entry criteria**  \n{entry}")
        with col_x:
            st.markdown(f"**Exit criteria**  \n{exit_}")

# ════════════════════════════════════════════════════════════════════════════
# SECTION 4: Quick Stats
# ════════════════════════════════════════════════════════════════════════════

st.markdown("---")
st.header("4 · Quick Stats")

qs_col1, qs_col2, qs_col3 = st.columns(3)

# Session scoring from 03_sourcing.py (shared session state keys)
session_scored = ss.get("src_session_scored", 0)
session_cost   = ss.get("src_session_cost", 0.0)

with qs_col1:
    st.subheader("This Session")
    st.metric("Leads scored", session_scored)
    st.metric("Est. LLM spend", f"${session_cost:.4f}")
    if session_scored > 0:
        st.caption(f"≈ ${_COST_PER_LEAD_USD:.3f}/lead (Claude Haiku)")

with qs_col2:
    st.subheader("Database")
    dh = _get_data_health()
    if dh:
        total     = dh.get("total", 0)
        db_bytes  = dh.get("db_size_bytes", 0)
        db_mb     = db_bytes / 1_048_576 if db_bytes else 0
        st.metric("Total leads",  total)
        st.metric("DB size",      f"{db_mb:.2f} MB" if db_mb else "—")
    else:
        st.metric("Total leads",  "—")
        st.metric("DB size",      "—")

with qs_col3:
    st.subheader("Scoring Coverage")
    scoring = _get_scoring_stats()
    if "error" not in scoring:
        scored   = scoring.get("scored_count", 0)
        unscored = scoring.get("unscored_count", 0)
        total    = scored + unscored
        avg_a    = scoring.get("avg_score_tier_a")
        tier_d   = scoring.get("tier_distribution", {})
        st.metric("Scored leads",  scored)
        st.metric("Unscored",      unscored)
        if avg_a:
            st.metric("Avg score (Tier A)", f"{avg_a}")
    else:
        st.metric("Scored leads", "—")
        st.metric("Unscored",     "—")

st.markdown("---")
st.caption(
    f"Backend: `{api.BACKEND_URL}`  ·  "
    "To restart the stack: `docker compose restart`  ·  "
    "API docs: [/api/docs](/api/docs)"
)
