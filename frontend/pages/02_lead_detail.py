"""B2B CRM — Lead Detail View."""

import json
import os
import sys
from datetime import date, datetime, time

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api_client as api

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Lead Detail — B2B CRM",
    page_icon="🔍",
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
    .activity-card {
        border-left: 3px solid #dee2e6;
        padding: 8px 14px;
        margin: 6px 0;
        background: #f8f9fa;
        border-radius: 0 6px 6px 0;
        line-height: 1.5;
    }
    .activity-card.email_sent     { border-color: #007bff; }
    .activity-card.email_received { border-color: #17a2b8; }
    .activity-card.call           { border-color: #28a745; }
    .activity-card.meeting        { border-color: #6f42c1; }
    .activity-card.status_change  { border-color: #fd7e14; }
    .company-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 14px 16px;
        line-height: 1.9;
    }
    .chip {
        display: inline-block;
        background: #e3f2fd;
        color: #1565c0;
        padding: 3px 10px;
        border-radius: 12px;
        margin: 2px;
        font-size: 0.8rem;
        font-weight: 500;
    }
    .signal-item {
        padding: 5px 0;
        border-bottom: 1px solid #f0f0f0;
        font-size: 0.88rem;
    }
    .hook-box {
        background: #fffbf0;
        border: 1px solid #ffc107;
        border-radius: 8px;
        padding: 14px;
        margin: 8px 0;
    }
    .status-badge {
        display: inline-block;
        background: #e9ecef;
        color: #495057;
        padding: 4px 12px;
        border-radius: 8px;
        font-size: 0.85rem;
        font-weight: 600;
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

VALID_TRANSITIONS: dict[str, list[str]] = {
    "identified":     ["enriched", "contacted", "archived"],
    "enriched":       ["contacted", "identified", "archived"],
    "contacted":      ["engaged", "qualified", "closed_lost", "archived"],
    "engaged":        ["qualified", "meeting_held", "contacted", "closed_lost", "archived"],
    "qualified":      ["meeting_held", "design_partner", "engaged", "closed_lost", "archived"],
    "meeting_held":   ["design_partner", "qualified", "closed_lost", "archived"],
    "design_partner": ["closed_won", "meeting_held", "closed_lost", "archived"],
    "closed_won":     ["archived"],
    "closed_lost":    ["archived", "identified"],
    "archived":       ["identified"],
}

ACTIVITY_ICONS: dict[str, str] = {
    "email_sent":     "✉️",
    "email_received": "📨",
    "call":           "📞",
    "meeting":        "🤝",
    "note":           "📝",
    "linkedin":       "💼",
    "status_change":  "🔄",
}

SENTIMENT_BADGES: dict[str, str] = {
    "positive": "🟢",
    "neutral":  "🟡",
    "negative": "🔴",
}

TIER_STYLE: dict[str, tuple[str, str]] = {
    "A": ("#d4edda", "#155724"),
    "B": ("#cce5ff", "#004085"),
    "C": ("#e2e3e5", "#383d41"),
    "D": ("#f8d7da", "#721c24"),
}

_EMAIL_TEMPLATE = """\
Hi {first_name},

{hook}

I'm reaching out because [explain your specific value prop for their company/role].

Would you be open to a quick 15-minute call this week to explore whether there's a fit?

Best,
[Your name]
[Your title] | [Company]
[Phone / Calendar link]
"""

# ── Session state defaults ────────────────────────────────────────────────────

ss = st.session_state
for _k, _v in [
    ("ld_draft_open",    False),
    ("ld_subject_input", ""),
    ("ld_body_input",    ""),
]:
    if _k not in ss:
        ss[_k] = _v

# ── Lead ID resolution ────────────────────────────────────────────────────────

lead_id: int | None = None

try:
    qp = st.query_params.get("id")
    if qp:
        lead_id = int(qp)
except (ValueError, TypeError, AttributeError):
    pass

if lead_id is None:
    for _key in ("detail_lead_id", "selected_lead_id"):
        _val = ss.get(_key)
        if _val:
            try:
                lead_id = int(_val)
                break
            except (ValueError, TypeError):
                pass

if lead_id is None:
    st.title("🔍 Lead Detail")
    st.info("No lead selected. Enter an ID below or navigate here from the Pipeline view.")
    with st.form("pick_lead"):
        manual_id = st.number_input("Lead ID", min_value=1, step=1, value=1)
        if st.form_submit_button("Load Lead →"):
            ss.detail_lead_id = int(manual_id)
            st.rerun()
    st.stop()

# ── Data loaders ──────────────────────────────────────────────────────────────


@st.cache_data(ttl=60)
def _load_lead(lid: int) -> dict:
    return api.get_lead(lid)


@st.cache_data(ttl=30)
def _load_activities(lid: int) -> list:
    result = api.get_activities(lid)
    return result if isinstance(result, list) else []


@st.cache_data(ttl=60)
def _load_stats() -> dict:
    return api.get_stats()


lead = _load_lead(lead_id)

if "error" in lead:
    st.error(f"Could not load lead #{lead_id}: {lead['error']}")
    if st.button("← Back to Pipeline"):
        st.switch_page("pages/01_pipeline.py")
    st.stop()

activities = _load_activities(lead_id)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else [str(parsed)]
    except Exception:
        return [raw] if raw else []


def _fmt_dt(s: str | None, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not s:
        return "—"
    try:
        clean = s.replace("Z", "").split("+")[0].split(".")[0]
        return datetime.fromisoformat(clean).strftime(fmt)
    except Exception:
        return (s[:16] if len(s) >= 16 else s)


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        clean = s.replace("Z", "").split("+")[0].split(".")[0]
        return datetime.fromisoformat(clean).date()
    except Exception:
        return None


def _score_color(score: int | None) -> str:
    if score is None:
        return "#6c757d"
    if score >= 80:
        return "#28a745"
    if score >= 60:
        return "#007bff"
    if score >= 40:
        return "#fd7e14"
    return "#dc3545"


def _tier_html(tier: str | None, large: bool = False) -> str:
    if not tier:
        return ""
    bg, fg = TIER_STYLE.get(tier, ("#e2e3e5", "#383d41"))
    pad  = "8px 26px" if large else "3px 12px"
    size = "1.15rem"  if large else "0.85rem"
    return (
        f"<span style='background:{bg};color:{fg};padding:{pad};"
        f"border-radius:14px;font-size:{size};font-weight:700;"
        f"letter-spacing:0.05em'>{tier}</span>"
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🎯 B2B CRM")
    if st.button("← Pipeline", use_container_width=True):
        st.switch_page("pages/01_pipeline.py")
    st.markdown("---")

    stats = _load_stats()
    if "error" not in stats:
        c1, c2 = st.columns(2)
        c1.metric("Total", sum(stats.get("counts_by_status", {}).values()))
        c2.metric("Tier A", stats.get("counts_by_tier", {}).get("A", 0))

    st.markdown("---")
    st.markdown("**Jump to Lead**")
    jump_id = st.number_input("Lead ID", min_value=1, step=1, value=lead_id, key="ld_jump")
    if st.button("Go →", use_container_width=True):
        ss.detail_lead_id = int(jump_id)
        ss.ld_draft_open  = False
        st.cache_data.clear()
        st.rerun()

# ── Unpack lead ───────────────────────────────────────────────────────────────

company:       dict       = lead.get("company") or {}
name:          str        = lead.get("full_name") or f"Lead #{lead_id}"
first_name:    str        = lead.get("first_name") or name.split()[0]
title:         str        = lead.get("title") or "—"
tier:          str | None = lead.get("icp_tier")
score:         int | None = lead.get("icp_score")
hook:          str | None = lead.get("personalized_hook")
reasoning:     str | None = lead.get("icp_reasoning")
disqualifiers: list       = _parse_json_list(lead.get("icp_disqualifiers"))
current_status: str       = lead.get("status") or "identified"

co_domain:   str = company.get("domain") or ""
domain_url:  str = (f"https://{co_domain}" if co_domain and not co_domain.startswith("http") else co_domain)
tech_stack:  list = _parse_json_list(company.get("tech_stack"))
signals:     list = _parse_json_list(company.get("recent_signals"))

# ── Two-column layout ─────────────────────────────────────────────────────────

left_col, right_col = st.columns([7, 3])

# ════════════════════════════════════════════════════════════════════════════
# LEFT COLUMN
# ════════════════════════════════════════════════════════════════════════════

with left_col:

    # ── Header ────────────────────────────────────────────────────────────────

    hdr, hdr_badge = st.columns([5, 1])
    hdr.markdown(f"# {name}")
    if tier:
        hdr_badge.markdown(
            f"<div style='text-align:right;padding-top:14px'>{_tier_html(tier, large=True)}</div>",
            unsafe_allow_html=True,
        )

    co_name = company.get("name") or "—"
    st.markdown(f"**{title}** · {co_name}")

    meta: list[str] = []
    email_str = lead.get("email") or ""
    if email_str:
        badge = "✅" if lead.get("email_verified") else "❌"
        meta.append(f"{badge} `{email_str}`")
    if lead.get("linkedin_url"):
        meta.append(f"[🌐 LinkedIn]({lead['linkedin_url']})")
    if lead.get("phone"):
        meta.append(f"📞 {lead['phone']}")
    if meta:
        st.markdown("  ·  ".join(meta))

    st.markdown("---")

    # ── ICP Score gauge + tier ────────────────────────────────────────────────

    gauge_col, tier_col = st.columns([3, 1])

    with gauge_col:
        if score is not None:
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=score,
                title={"text": "ICP Score", "font": {"size": 14}},
                gauge={
                    "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#6c757d"},
                    "bar":  {"color": _score_color(score), "thickness": 0.28},
                    "bgcolor": "white",
                    "borderwidth": 1,
                    "bordercolor": "#dee2e6",
                    "steps": [
                        {"range": [0,  40], "color": "#f8d7da"},
                        {"range": [40, 60], "color": "#fff3cd"},
                        {"range": [60, 80], "color": "#cce5ff"},
                        {"range": [80, 100], "color": "#d4edda"},
                    ],
                    "threshold": {
                        "line": {"color": _score_color(score), "width": 4},
                        "thickness": 0.75,
                        "value": score,
                    },
                },
            ))
            fig.update_layout(
                height=210,
                margin=dict(l=20, r=20, t=40, b=0),
                font=dict(family="Inter, Segoe UI, sans-serif"),
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.markdown("#### ICP Score")
            st.caption("*Not yet scored — click Rescore to generate.*")

    with tier_col:
        st.markdown("#### Tier")
        if tier:
            st.markdown(_tier_html(tier, large=True), unsafe_allow_html=True)
        else:
            st.markdown("*Unscored*")

        scored_at = _fmt_dt(lead.get("scored_at"), "%Y-%m-%d")
        st.caption(f"Scored: {scored_at}")
        st.markdown("")

        if st.button("🤖 Rescore", key="ld_rescore", use_container_width=True):
            with st.spinner("Scoring with Claude…"):
                res = api.score_lead(lead_id)
            if "error" in res:
                st.error(res["error"])
            else:
                st.success(f"Tier {res.get('icp_tier')} — {res.get('icp_score')}/100")
                st.cache_data.clear()
                st.rerun()

        if st.button("🔬 Enrich", key="ld_enrich", use_container_width=True):
            with st.spinner("Enriching via Apollo…"):
                res = api.enrich_lead(lead_id)
            if "error" in res:
                st.error(res["error"])
            else:
                em  = res.get("email", "—")
                ver = "✅" if res.get("email_verified") else "unverified"
                st.success(f"{em} ({ver})")
                st.cache_data.clear()
                st.rerun()

    # ── ICP Reasoning ─────────────────────────────────────────────────────────

    if reasoning:
        with st.expander("💡 ICP Reasoning", expanded=bool(reasoning)):
            st.info(reasoning)

    # ── Disqualifiers ─────────────────────────────────────────────────────────

    if disqualifiers:
        st.markdown("#### 🚫 Hard Disqualifiers")
        for dq in disqualifiers:
            st.error(str(dq), icon="🚫")

    st.markdown("---")

    # ── Personalized Hook ─────────────────────────────────────────────────────

    st.markdown("#### 📬 Personalized Hook")

    if hook:
        st.markdown("<div class='hook-box'>", unsafe_allow_html=True)
        st.code(hook, language=None)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.caption("No hook yet — click Regenerate Hook to create one.")

    hk1, hk2 = st.columns(2)

    with hk1:
        if st.button("🔄 Regenerate Hook", use_container_width=True, key="ld_regen"):
            with st.spinner("Generating with Claude…"):
                res = api.generate_hook(lead_id)
            if "error" in res:
                st.error(res["error"])
            else:
                st.success("Hook updated.")
                st.cache_data.clear()
                st.rerun()

    with hk2:
        draft_lbl = "✉️ Close Draft" if ss.ld_draft_open else "📧 Draft Email"
        if st.button(draft_lbl, use_container_width=True, key="ld_draft_btn"):
            if not ss.ld_draft_open:
                # Build draft; generate hook on the fly if missing
                current_hook = hook
                if not current_hook:
                    with st.spinner("Generating hook…"):
                        res = api.generate_hook(lead_id)
                    if "error" not in res:
                        current_hook = res.get("hook", "")
                        st.cache_data.clear()

                ss.ld_subject_input = f"Quick question, {first_name}"
                ss.ld_body_input    = _EMAIL_TEMPLATE.format(
                    first_name=first_name,
                    hook=current_hook or "[Add your personalized opener here]",
                )
            ss.ld_draft_open = not ss.ld_draft_open
            st.rerun()

    # ── Email Draft ───────────────────────────────────────────────────────────

    if ss.ld_draft_open:
        st.markdown("##### ✉️ Email Draft")
        st.text_input("Subject", key="ld_subject_input")
        st.text_area("Body", height=230, key="ld_body_input")
        st.markdown("**Full email — click copy icon to copy:**")
        full_email = (
            f"Subject: {ss.get('ld_subject_input', '')}\n\n"
            f"{ss.get('ld_body_input', '')}"
        )
        st.code(full_email, language=None)

    st.markdown("---")

    # ── Activity Timeline ─────────────────────────────────────────────────────

    n_act = len(activities)
    st.markdown(f"#### 🕐 Activity Timeline  ·  {n_act} event{'s' if n_act != 1 else ''}")

    if activities:
        for act in activities:
            act_type   = act.get("type") or "note"
            icon       = ACTIVITY_ICONS.get(act_type, "📌")
            snippet    = act.get("content_snippet") or "—"
            occurred   = _fmt_dt(act.get("occurred_at"))
            channel    = act.get("channel") or ""
            sentiment  = act.get("sentiment") or ""
            sent_icon  = SENTIMENT_BADGES.get(sentiment, "")

            ch_txt   = f" · {channel}" if channel else ""
            sent_txt = f" · {sent_icon}" if sent_icon else ""
            css_cls  = act_type.replace("_", "-") if act_type in ACTIVITY_ICONS else ""

            st.markdown(
                f"<div class='activity-card {css_cls}'>"
                f"<span style='font-size:1.05rem'>{icon}</span>&nbsp;"
                f"<strong>{act_type.replace('_', ' ').title()}</strong>"
                f"<span style='color:#868e96;font-size:0.8rem'>{ch_txt}{sent_txt}&nbsp;·&nbsp;{occurred}</span>"
                f"<br><span style='font-size:0.9rem'>{snippet}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No activities recorded yet.")

    # ── Log Activity ──────────────────────────────────────────────────────────

    with st.expander("➕ Log New Activity"):
        with st.form("log_act_form", clear_on_submit=True):
            r1c1, r1c2 = st.columns(2)
            act_type_sel = r1c1.selectbox(
                "Type",
                ["email_sent", "email_received", "call", "meeting", "note", "linkedin"],
            )
            act_channel_in = r1c2.text_input("Channel", placeholder="email / phone / …")

            act_notes = st.text_area("Notes", placeholder="What happened?", height=80)

            r2c1, r2c2 = st.columns([2, 1])
            act_sentiment_sel = r2c1.selectbox(
                "Sentiment", ["", "positive", "neutral", "negative"]
            )
            log_submitted = r2c2.form_submit_button(
                "📌 Log", type="primary", use_container_width=True
            )

        if log_submitted:
            if act_notes.strip():
                body = {
                    "lead_id":          lead_id,
                    "type":             act_type_sel,
                    "content_snippet":  act_notes.strip(),
                }
                if act_channel_in:
                    body["channel"] = act_channel_in
                if act_sentiment_sel:
                    body["sentiment"] = act_sentiment_sel
                res = api._post("/api/activities/", json=body)
                if isinstance(res, dict) and "error" in res:
                    st.error(res["error"])
                else:
                    st.success("Activity logged.")
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.warning("Please enter notes.")


# ════════════════════════════════════════════════════════════════════════════
# RIGHT COLUMN
# ════════════════════════════════════════════════════════════════════════════

with right_col:

    # ── Company card ──────────────────────────────────────────────────────────

    st.markdown("#### 🏢 Company")

    if company:
        co_industry  = company.get("industry") or "—"
        co_emps      = company.get("employee_count")
        co_country   = company.get("hq_country") or "—"
        co_funding   = company.get("funding_stage") or "—"
        co_fund_dt   = company.get("last_funding_date") or ""
        co_fund_amt  = company.get("last_funding_amount_usd")

        domain_link = (
            f"<a href='{domain_url}' target='_blank' style='font-size:0.85rem'>{co_domain}</a>"
            if co_domain else ""
        )
        emps_str   = f"{co_emps:,}" if co_emps else "—"
        fund_extra = ""
        if co_fund_dt:
            fund_extra += f"<br><span style='font-size:0.8rem;color:#6c757d'>Last: {co_fund_dt}</span>"
        if co_fund_amt:
            fund_extra += f"<br><span style='font-size:0.8rem;color:#6c757d'>${co_fund_amt:,}</span>"

        st.markdown(
            f"<div class='company-card'>"
            f"<strong style='font-size:1.05rem'>{co_name}</strong>"
            + (f"<br>{domain_link}" if domain_link else "")
            + f"<br>"
            f"<span style='color:#6c757d;font-size:0.8rem'>🏭 Industry</span><br>"
            f"<strong>{co_industry}</strong><br>"
            f"<span style='color:#6c757d;font-size:0.8rem'>👥 Employees</span><br>"
            f"<strong>{emps_str}</strong><br>"
            f"<span style='color:#6c757d;font-size:0.8rem'>🌍 Country</span><br>"
            f"<strong>{co_country}</strong><br>"
            f"<span style='color:#6c757d;font-size:0.8rem'>💰 Funding Stage</span><br>"
            f"<strong>{co_funding}</strong>{fund_extra}"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption("No company linked to this lead.")

    # ── External links ────────────────────────────────────────────────────────

    st.markdown("")
    lnk1, lnk2 = st.columns(2)
    if lead.get("linkedin_url"):
        lnk1.link_button("🌐 LinkedIn", lead["linkedin_url"], use_container_width=True)
    if domain_url:
        lnk2.link_button("🏢 Website", domain_url, use_container_width=True)

    # ── Tech Stack ────────────────────────────────────────────────────────────

    if tech_stack:
        st.markdown("---")
        st.markdown("#### ⚙️ Tech Stack")
        chips = "".join(
            f"<span class='chip'>{t}</span>"
            for t in tech_stack
            if t
        )
        st.markdown(chips, unsafe_allow_html=True)

    # ── Recent Signals ────────────────────────────────────────────────────────

    if signals:
        st.markdown("---")
        st.markdown("#### 📡 Recent Signals")
        for sig in signals[:8]:
            if isinstance(sig, dict):
                label  = sig.get("title") or sig.get("type") or sig.get("name") or str(sig)
                detail = sig.get("description") or sig.get("detail") or ""
                st.markdown(
                    f"<div class='signal-item'>🔔 <strong>{label}</strong>"
                    + (f"<br><span style='color:#6c757d;font-size:0.8rem'>{detail}</span>" if detail else "")
                    + "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<div class='signal-item'>🔔 {sig}</div>",
                    unsafe_allow_html=True,
                )

    # ── Buying signals ────────────────────────────────────────────────────────

    careers_url = company.get("careers_page_url") if company else None
    if careers_url:
        st.markdown("---")
        st.markdown("#### 🎯 Buying Signals")
        st.link_button("📋 Careers Page", careers_url, use_container_width=True)
        st.caption("Active hiring often signals budget and growth — strong buying intent.")

    # ── Status management ─────────────────────────────────────────────────────

    st.markdown("---")
    st.markdown("#### 🎯 Status")

    st.markdown(
        f"Current: <span class='status-badge'>{current_status}</span>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    next_stages = VALID_TRANSITIONS.get(current_status, ALL_STATUSES)
    new_status = st.selectbox(
        "Move to stage",
        next_stages,
        key="ld_new_status",
        label_visibility="collapsed",
    )
    if st.button("▶ Update Status", use_container_width=True, key="ld_do_status"):
        with st.spinner("Updating…"):
            res = api.update_lead(lead_id, {"status": new_status})
        if "error" in res:
            st.error(res["error"])
        else:
            st.success(f"Status → **{new_status}**")
            st.cache_data.clear()
            st.rerun()

    # ── Next Action Due ───────────────────────────────────────────────────────

    st.markdown("---")
    st.markdown("**📅 Next Action Due**")

    current_due = _parse_date(lead.get("next_action_due"))
    due_key     = f"ld_due_{lead_id}"
    if due_key not in ss:
        ss[due_key] = current_due or date.today()

    new_due = st.date_input("Due", key=due_key, label_visibility="collapsed")

    if st.button("💾 Save Due Date", use_container_width=True, key="ld_save_due"):
        due_iso = datetime.combine(new_due, time(12, 0)).isoformat() if new_due else None
        with st.spinner("Saving…"):
            res = api.update_lead(lead_id, {"next_action_due": due_iso})
        if "error" in res:
            st.error(res["error"])
        else:
            st.success("Due date saved.")
            ss.pop(due_key, None)   # reset so it reflects new DB value
            st.cache_data.clear()
            st.rerun()

    # ── Notes ─────────────────────────────────────────────────────────────────

    st.markdown("---")
    st.markdown("**📓 Notes**")

    notes_key = f"ld_notes_{lead_id}"
    if notes_key not in ss:
        ss[notes_key] = lead.get("notes") or ""

    st.text_area("Notes", height=120, key=notes_key, label_visibility="collapsed")

    if st.button("💾 Save Notes", use_container_width=True, key="ld_save_notes"):
        with st.spinner("Saving…"):
            res = api.update_lead(lead_id, {"notes": ss[notes_key]})
        if "error" in res:
            st.error(res["error"])
        else:
            st.success("Notes saved.")
            st.cache_data.clear()

    # ── Lead metadata ─────────────────────────────────────────────────────────

    st.markdown("---")
    st.caption(
        f"Lead #{lead_id}  ·  source: {lead.get('source', '—')}  \n"
        f"Created: {_fmt_dt(lead.get('created_at'), '%Y-%m-%d')}  \n"
        f"Updated: {_fmt_dt(lead.get('updated_at'), '%Y-%m-%d')}  \n"
        f"Enriched: {_fmt_dt(lead.get('enriched_at'), '%Y-%m-%d')}"
    )
