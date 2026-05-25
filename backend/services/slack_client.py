"""Slack Incoming Webhook client for lead notifications and pipeline alerts."""

import logging
from datetime import date
from typing import Optional

import httpx

from config import settings
from database import Company, Lead

logger = logging.getLogger(__name__)

_LEAD_BASE_URL = "http://localhost:8501/lead_detail"


def _webhook_configured() -> bool:
    if not settings.SLACK_WEBHOOK_URL:
        logger.debug("SLACK_WEBHOOK_URL not configured — skipping notification")
        return False
    return True


async def _post(payload: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(settings.SLACK_WEBHOOK_URL, json=payload)
            r.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.error("Slack webhook request failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def notify_hot_lead(lead: Lead, company: Optional[Company]) -> bool:
    """Send a Block Kit message to Slack for a newly scored Tier A lead."""
    if not _webhook_configured():
        return False

    name = lead.full_name or "Unknown"
    title = lead.title or "Unknown"
    company_name = company.name if company else "Unknown"
    score = f"{lead.icp_score}/100" if lead.icp_score is not None else "—"
    industry = company.industry if company else "—"
    employees = str(company.employee_count) if (company and company.employee_count) else "—"
    reasoning = (lead.icp_reasoning or "")[:150]
    lead_url = f"{_LEAD_BASE_URL}?id={lead.id}"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🎯 New Tier A Lead", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Name*\n{name}"},
                {"type": "mrkdwn", "text": f"*Title*\n{title}"},
                {"type": "mrkdwn", "text": f"*Company*\n{company_name}"},
                {"type": "mrkdwn", "text": f"*Score*\n{score}"},
                {"type": "mrkdwn", "text": f"*Industry*\n{industry}"},
                {"type": "mrkdwn", "text": f"*Employees*\n{employees}"},
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": reasoning or "_No reasoning available_"}],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View Lead", "emoji": False},
                    "url": lead_url,
                }
            ],
        },
    ]

    return await _post({"blocks": blocks})


async def send_daily_digest(leads: list[dict]) -> bool:
    """Send a daily digest of new Tier A/B leads to Slack."""
    if not _webhook_configured():
        return False

    today = date.today().strftime("%b %d, %Y")

    if not leads:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"📊 Daily Lead Digest — {today}", "emoji": True},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "_No new leads today._"},
            },
        ]
        return await _post({"blocks": blocks})

    rows = []
    for lead in leads[:10]:
        name = lead.get("full_name") or lead.get("name") or "Unknown"
        company = lead.get("company_name") or lead.get("company") or "—"
        tier = lead.get("icp_tier") or lead.get("tier") or "?"
        score = lead.get("icp_score") or lead.get("score") or "—"
        rows.append(f"• *{name}* at {company} — Tier {tier} ({score}/100)")

    lead_lines = "\n".join(rows)
    total = len(leads)
    footer = f"_{total} new lead{'s' if total != 1 else ''} processed today_"
    if total > 10:
        footer = f"_Showing top 10 of {total} leads processed today_"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📊 Daily Lead Digest — {today}", "emoji": True},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": lead_lines},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": footer}],
        },
    ]

    return await _post({"blocks": blocks})


async def send_pipeline_alert(message: str, lead_id: Optional[int] = None) -> bool:
    """Send a generic pipeline event alert, with an optional deep-link to a lead."""
    if not _webhook_configured():
        return False

    text = message
    if lead_id is not None:
        text = f"{message}\n<{_LEAD_BASE_URL}?id={lead_id}|View Lead #{lead_id}>"

    return await _post({"text": text})
