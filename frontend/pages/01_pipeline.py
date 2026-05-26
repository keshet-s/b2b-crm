"""B2B CRM — Pipeline View (primary outreach screen)."""

import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

# Ensure frontend/ is on path when executed as a Streamlit multi-page page
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api_client as api

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Pipeline — B2B CRM",
    page_icon="📊",
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
    html, body, [class*="css"] {
        font-family: "Inter", "Segoe UI", sans-serif;
    }
    [data-testid="metric-container"] {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 8px 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Constants ─────────────────────────────────────────────────────────────────

PIPELINE_STAGES = [
    ("identified",     "Identified"),
    ("enriched",       "Enriched"),
    ("contacted",      "Contacted"),
    ("engaged",        "Engaged"),
    ("qualified",      "Qualified"),
    ("meeting_held",   "Meeting Held"),
    ("design_partner", "Design Partner"),
    ("closed_won",     "Closed Won"),
    ("closed_lost",    "Closed Lost"),
    ("archived",       "Archived"),
]
ALL_STATUSES = [s for s, _ in PIPELINE_STAGES]

# ── Session state defaults ────────────────────────────────────────────────────

ss = st.session_state
for _k, _v in [
    ("pl_stage",       None),   # stage card currently clicked
    ("pl_confirm",     None),   # ("action_name", lead_id) pending confirmation
    ("pl_selected_id", None),   # lead_id of the selected table row
    ("pl_call_open",   False),  # whether the Log Call inline form is visible
]:
    if _k not in ss:
        ss[_k] = _v

# ── Cached data loaders ───────────────────────────────────────────────────────


@st.cache_data(ttl=30)
def _get_summary() -> dict:
    return api.get_pipeline_summary()


@st.cache_data(ttl=30)
def _get_stats() -> dict:
    return api.get_stats()


@st.cache_data(ttl=15)
def _get_leads(status: str | None, tier: str | None, search: str | None) -> dict:
    return api.get_leads(status=status, tier=tier, search=search, limit=200)


@st.cache_data(ttl=60)
def _overdue_stages() -> frozenset:
    """Return set of pipeline statuses that have at least one overdue followup."""
    now = datetime.utcnow()
    result = api.get_leads(limit=200)
    if not isinstance(result, dict) or "error" in result:
        return frozenset()
    overdue: set[str] = set()
    for lead in result.get("leads", []):
        due_str = lead.get("next_action_due")
        if not due_str:
            continue
        try:
            clean = due_str.replace("Z", "").split("+")[0].split(".")[0]
            if datetime.fromisoformat(clean) < now:
                overdue.add(lead.get("status", ""))
        except Exception:
            pass
    return frozenset(overdue)


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🎯 B2B CRM")
    st.markdown("---")

    stats = _get_stats()
    if "error" not in stats:
        summ = _get_summary()
        c1, c2 = st.columns(2)
        c1.metric("Total Leads", sum(stats.get("counts_by_status", {}).values()))
        c2.metric("Tier A", stats.get("counts_by_tier", {}).get("A", 0))
        c3, c4 = st.columns(2)
        _ok = "error" not in summ
        c3.metric("Uncontacted A", summ.get("tier_a_uncontacted", "—") if _ok else "—")
        c4.metric("Overdue",       summ.get("overdue_followups",  "—") if _ok else "—")
    else:
        st.error("Backend not reachable", icon="🔴")

    st.markdown("---")
    st.markdown("**Filters**")

    # Using key= lets Streamlit persist values automatically
    st.multiselect("Status", ALL_STATUSES,          key="pl_statuses")
    st.multiselect("Tier",   ["A", "B", "C", "D"],  key="pl_tiers")
    st.text_input("Search name / company",           key="pl_search")

    if st.button("🗑 Clear Filters", use_container_width=True):
        ss.pl_stage = None
        for k in ("pl_statuses", "pl_tiers", "pl_search"):
            ss.pop(k, None)
        st.rerun()

# ── Helpers ───────────────────────────────────────────────────────────────────


def _fmt_date(s: str | None) -> str:
    if not s:
        return ""
    try:
        clean = s.replace("Z", "").split("+")[0].split(".")[0]
        return datetime.fromisoformat(clean).strftime("%Y-%m-%d")
    except Exception:
        return s[:10] if s else ""


def _row_styler(row: pd.Series) -> list[str]:
    tier = str(row.get("Tier", ""))
    if tier == "A":
        return ["background-color:#d4edda;color:#155724"] * len(row)
    if tier == "B":
        return ["background-color:#cce5ff;color:#004085"] * len(row)
    return [""] * len(row)


# ── Quick action row ──────────────────────────────────────────────────────────

st.title("📊 Pipeline")

qa1, qa2, qa3, _gap = st.columns([2, 2, 1, 5])

with qa1:
    if st.button("🚀 Run Sourcing (1 page)", use_container_width=True):
        with st.spinner("Sourcing…"):
            result = api.run_sourcing(pages=1)
        if "error" in result:
            st.error(f"Sourcing failed: {result['error']}")
        else:
            st.success(f"Done — {result.get('leads_new', 0)} new leads added")
            st.cache_data.clear()
            st.rerun()

with qa2:
    if st.button("🤖 Score Unscored (50)", use_container_width=True):
        with st.spinner("Scoring with Claude…"):
            result = api.score_unscored(limit=50)
        if "error" in result:
            st.error(f"Scoring failed: {result['error']}")
        else:
            st.success(f"Scored {result.get('scored', 0)} leads")
            st.cache_data.clear()
            st.rerun()

with qa3:
    if st.button("📊 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ── Pipeline summary bar ──────────────────────────────────────────────────────

summary = _get_summary()
if "error" in summary:
    st.error(f"Pipeline unavailable: {summary['error']}")
    st.stop()

stages_data  = summary.get("stages", [])
over_stages  = _overdue_stages()

st.markdown("#### Pipeline Stages  ·  click to filter table")
stage_cols = st.columns(max(len(stages_data), 1))

for col, sd in zip(stage_cols, stages_data):
    status   = sd["status"]
    count    = sd["count"]
    tier_a   = sd.get("tier_a_count", 0)
    active   = ss.pl_stage == status
    overdue  = status in over_stages

    with col:
        btn_lbl = f"⚠️ {sd['label']}" if overdue else sd["label"]
        if st.button(
            btn_lbl,
            key=f"stg_{status}",
            type="primary" if active else "secondary",
            use_container_width=True,
        ):
            ss.pl_stage = None if active else status
            ss.pop("pl_statuses", None)   # stage click overrides multiselect
            st.rerun()

        if status in ("identified", "enriched") and tier_a:
            st.metric("", count, delta=f"🔥 {tier_a} Tier A", delta_color="off")
        else:
            st.metric("", count)

st.markdown("---")

# ── Resolve effective API filters ─────────────────────────────────────────────

pl_statuses: list = ss.get("pl_statuses", [])
pl_tiers: list    = ss.get("pl_tiers", [])
pl_search: str    = ss.get("pl_search", "")

# Server only accepts a single status; stage card takes precedence over empty multiselect
eff_status: str | None = (
    pl_statuses[0]  if len(pl_statuses) == 1
    else ss.pl_stage if (not pl_statuses and ss.pl_stage)
    else None
)
eff_tier: str | None   = pl_tiers[0] if len(pl_tiers) == 1 else None
eff_search: str | None = pl_search or None

raw = _get_leads(eff_status, eff_tier, eff_search)
if isinstance(raw, dict) and "error" in raw:
    st.error(f"Could not load leads: {raw['error']}")
    st.stop()

leads: list = raw.get("leads", []) if isinstance(raw, dict) else []

# Client-side post-filter for multi-select values
if len(pl_statuses) > 1:
    leads = [l for l in leads if l.get("status") in pl_statuses]
if len(pl_tiers) > 1:
    leads = [l for l in leads if l.get("icp_tier") in pl_tiers]

server_total = raw.get("total", len(leads)) if isinstance(raw, dict) else len(leads)
st.markdown(
    f"Showing **{len(leads)}** leads"
    + (f"  ·  {server_total} on server (scroll filters or increase limit)" if server_total > len(leads) else "")
)

with st.expander("Tier legend", expanded=False):
    _tc1, _tc2, _tc3, _tc4 = st.columns(4)
    _tc1.markdown(
        "<span style='background:#d4edda;color:#155724;font-weight:700;"
        "padding:3px 10px;border-radius:6px;'>A</span>"
        "&nbsp; **80–100** · Outreach now",
        unsafe_allow_html=True,
    )
    _tc2.markdown(
        "<span style='background:#cce5ff;color:#004085;font-weight:700;"
        "padding:3px 10px;border-radius:6px;'>B</span>"
        "&nbsp; **60–79** · Nurture",
        unsafe_allow_html=True,
    )
    _tc3.markdown(
        "<span style='background:#fff3cd;color:#856404;font-weight:700;"
        "padding:3px 10px;border-radius:6px;'>C</span>"
        "&nbsp; **40–59** · Hold 90 days",
        unsafe_allow_html=True,
    )
    _tc4.markdown(
        "<span style='background:#f8d7da;color:#721c24;font-weight:700;"
        "padding:3px 10px;border-radius:6px;'>D</span>"
        "&nbsp; **0–39** · Disqualify",
        unsafe_allow_html=True,
    )

# ── Build display DataFrame ───────────────────────────────────────────────────

rows: list[dict] = []
for lead in leads:
    company = lead.get("company") or {}
    rows.append({
        "ID":             lead["id"],
        "Name":           (lead.get("full_name") or "")[:35],
        "Title":          (lead.get("title") or "")[:35],
        "Company":        (company.get("name") or "")[:28],
        "Industry":       (company.get("industry") or "")[:22],
        "Employees":      company.get("employee_count"),
        "Tier":           lead.get("icp_tier") or "",
        "Score":          lead.get("icp_score"),
        "Status":         lead.get("status") or "",
        "Last Contacted": _fmt_date(lead.get("last_contacted_at")),
        "Next Due":       _fmt_date(lead.get("next_action_due")),
        "Email":          "✅" if lead.get("email_verified") else ("❌" if lead.get("email") else ""),
        "Hook":           "📝" if lead.get("personalized_hook") else "",
    })

_COL_CFG = {
    "ID":        st.column_config.NumberColumn("ID",    width="small",  format="%d"),
    "Employees": st.column_config.NumberColumn("Emps",  width="small"),
    "Score":     st.column_config.NumberColumn("Score", width="small"),
    "Tier":      st.column_config.TextColumn("Tier",    width="small"),
    "Email":     st.column_config.TextColumn("Email",   width="small"),
    "Hook":      st.column_config.TextColumn("Hook",    width="small"),
    "Status":    st.column_config.TextColumn("Status",  width="medium"),
}

selected_rows: list[int] = []

if not rows:
    st.info("No leads match the current filters.")
else:
    df = pd.DataFrame(rows)
    styled = df.style.apply(_row_styler, axis=1)
    event = st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config=_COL_CFG,
    )
    selected_rows = event.selection.rows

# ── Action panel ──────────────────────────────────────────────────────────────

if not selected_rows:
    st.caption("↑ Click a row to open the action panel.")
    st.stop()

sel_idx = selected_rows[0]
if sel_idx >= len(rows):
    st.warning("Row index out of range — please reselect a row.")
    st.stop()

sel        = rows[sel_idx]
lead_id: int   = sel["ID"]
lead_name: str = sel["Name"]

# Reset pending state when a different lead is selected
if ss.pl_selected_id != lead_id:
    ss.pl_selected_id = lead_id
    ss.pl_confirm     = None
    ss.pl_call_open   = False

st.markdown("---")
st.markdown(
    f"### ⚡ {lead_name}"
    f"<span style='font-size:0.9rem;color:#6c757d;'>"
    f"  ·  tier&nbsp;<strong>{sel['Tier'] or '?'}</strong>"
    f"  ·  {sel['Company']}"
    f"  ·  status:&nbsp;<code>{sel['Status']}</code>"
    f"  ·  score:&nbsp;{sel['Score'] or '—'}"
    f"  ·  email:&nbsp;{sel['Email'] or '—'}"
    f"</span>",
    unsafe_allow_html=True,
)

# ── Confirmation dialog (inline, renders above action buttons) ────────────────

if ss.pl_confirm:
    action, conf_id = ss.pl_confirm
    if conf_id == lead_id:

        if action == "mark_contacted":
            st.warning(
                f"Confirm: mark **{lead_name}** as contacted and schedule a follow-up in 7 days?",
                icon="✉️",
            )
            cy, cn, _ = st.columns([1, 1, 6])
            if cy.button("Confirm", key="c_yes", type="primary"):
                now = datetime.utcnow()
                with st.spinner("Updating lead…"):
                    res = api.update_lead(lead_id, {
                        "status":            "contacted",
                        "last_contacted_at": now.isoformat(),
                        "next_action_due":   (now + timedelta(days=7)).isoformat(),
                    })
                if "error" in res:
                    st.error(res["error"])
                else:
                    api.post_activity(
                        lead_id, "email_sent",
                        "Marked as contacted via CRM pipeline view",
                        channel="email",
                    )
                    st.success(f"✅ {lead_name} marked as contacted. Follow-up due in 7 days.")
                    ss.pl_confirm = None
                    st.cache_data.clear()
                    st.rerun()
            if cn.button("Cancel", key="c_no"):
                ss.pl_confirm = None
                st.rerun()

        elif action == "archive":
            st.warning(
                f"Confirm: archive **{lead_name}**? Their status will be set to 'archived'.",
                icon="⚠️",
            )
            ay, an, _ = st.columns([1, 1, 6])
            if ay.button("Archive", key="a_yes", type="primary"):
                with st.spinner("Archiving…"):
                    res = api.update_lead(lead_id, {"status": "archived"})
                if "error" in res:
                    st.error(res["error"])
                else:
                    st.success(f"✅ {lead_name} archived.")
                    ss.pl_confirm     = None
                    ss.pl_selected_id = None
                    st.cache_data.clear()
                    st.rerun()
            if an.button("Cancel", key="a_no"):
                ss.pl_confirm = None
                st.rerun()

# ── Log Call inline form (renders above action buttons) ───────────────────────

if ss.pl_call_open and ss.pl_selected_id == lead_id:
    with st.form("log_call_form", clear_on_submit=True):
        st.markdown("**📞 Log a Call**")
        call_notes = st.text_area(
            "Notes", placeholder="Describe what was discussed…", height=80
        )
        fs, fc, _ = st.columns([1, 1, 5])
        submitted = fs.form_submit_button("📞 Log", type="primary")
        cancelled = fc.form_submit_button("Cancel")

    if submitted:
        if call_notes.strip():
            res = api.post_activity(
                lead_id, "call", call_notes.strip(), channel="phone"
            )
            if "error" in res:
                st.error(res["error"])
            else:
                st.success("📞 Call logged.")
                ss.pl_call_open = False
                st.cache_data.clear()
                st.rerun()
        else:
            st.warning("Please enter notes before logging.")
    if cancelled:
        ss.pl_call_open = False
        st.rerun()

# ── Action buttons ────────────────────────────────────────────────────────────

b1, b2, b3, b4, b5, b6, b7 = st.columns(7)

with b1:
    if st.button("✉️ Mark Contacted", use_container_width=True, key="btn_contact"):
        ss.pl_confirm   = ("mark_contacted", lead_id)
        ss.pl_call_open = False
        st.rerun()

with b2:
    call_lbl = "📞 Close Form" if ss.pl_call_open else "📞 Log Call"
    if st.button(call_lbl, use_container_width=True, key="btn_call"):
        ss.pl_call_open = not ss.pl_call_open
        ss.pl_confirm   = None
        st.rerun()

with b3:
    if st.button("✅ Move to Qualified", use_container_width=True, key="btn_qual"):
        with st.spinner("Updating…"):
            res = api.update_lead(lead_id, {"status": "qualified"})
        if "error" in res:
            st.error(res["error"])
        else:
            st.success(f"✅ {lead_name} moved to Qualified.")
            st.cache_data.clear()
            st.rerun()

with b4:
    if st.button("🔬 Enrich Email", use_container_width=True, key="btn_enrich"):
        with st.spinner("Enriching via Apollo…"):
            res = api.enrich_lead(lead_id)
        if "error" in res:
            st.error(res["error"])
        else:
            email   = res.get("email", "—")
            ver_lbl = "✅ verified" if res.get("email_verified") else "unverified"
            st.success(f"Email: {email} ({ver_lbl})")
            st.cache_data.clear()
            st.rerun()

with b5:
    if st.button("🤖 Score / Rescore", use_container_width=True, key="btn_score"):
        with st.spinner("Scoring with Claude…"):
            res = api.score_lead(lead_id)
        if "error" in res:
            st.error(res["error"])
        else:
            st.success(f"Tier {res.get('icp_tier')} — {res.get('icp_score')}/100")
            st.cache_data.clear()
            st.rerun()

with b6:
    if st.button("📝 View Detail", use_container_width=True, key="btn_detail"):
        st.session_state["detail_lead_id"] = lead_id
        st.switch_page("pages/02_lead_detail.py")

with b7:
    if st.button("❌ Archive", use_container_width=True, key="btn_archive"):
        ss.pl_confirm   = ("archive", lead_id)
        ss.pl_call_open = False
        st.rerun()
