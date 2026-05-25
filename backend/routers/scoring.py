"""ICP scoring and email hook generation endpoints."""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from database import Activity, Company, Lead, get_db
from schemas import LeadResponse
from services import claude_client
from utils import parse_json_field, to_json_field, utcnow

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_lead_data(lead: Lead) -> dict:
    company: Optional[Company] = lead.company
    email_domain = None
    if lead.email and "@" in lead.email:
        email_domain = "@" + lead.email.split("@", 1)[1]
    return {
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "title": lead.title,
        "seniority": lead.seniority,
        "department": lead.department,
        "linkedin_url": lead.linkedin_url,
        "email": email_domain,
        "email_verified": lead.email_verified,
        "company_name": company.name if company else None,
        "company_domain": company.domain if company else None,
        "company_industry": company.industry if company else None,
        "company_employee_count": company.employee_count if company else None,
        "company_hq_country": company.hq_country if company else None,
        "company_funding_stage": company.funding_stage if company else None,
        "company_last_funding_date": company.last_funding_date if company else None,
        "company_tech_stack": parse_json_field(company.tech_stack) if company else None,
        "company_recent_signals": parse_json_field(company.recent_signals) if company else None,
    }


def _build_company_data(company: Optional[Company]) -> dict:
    if company is None:
        return {}
    return {
        "name": company.name,
        "domain": company.domain,
        "industry": company.industry,
        "employee_count": company.employee_count,
        "hq_country": company.hq_country,
        "funding_stage": company.funding_stage,
        "last_funding_date": company.last_funding_date,
        "tech_stack": parse_json_field(company.tech_stack),
        "recent_signals": parse_json_field(company.recent_signals),
    }


async def _notify_slack_hot_lead(lead: Lead, score: int, tier: str) -> None:
    if not settings.SLACK_WEBHOOK_URL:
        return
    name = lead.full_name or f"{lead.first_name or ''} {lead.last_name or ''}".strip()
    company_name = lead.company.name if lead.company else "Unknown"
    text = (
        f":fire: *Hot lead — Tier {tier} ({score}/100)*\n"
        f"*{name}* | {lead.title or 'N/A'} at {company_name}\n"
        f"Hook: {lead.personalized_hook or '_none_'}"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            await http.post(settings.SLACK_WEBHOOK_URL, json={"text": text})
    except Exception:
        logger.warning("Slack hot-lead notification failed for lead %d", lead.id, exc_info=True)


# ---------------------------------------------------------------------------
# POST /score/{lead_id}
# ---------------------------------------------------------------------------

@router.post("/score/{lead_id}", response_model=LeadResponse)
async def score_lead(lead_id: int, db: Session = Depends(get_db)):
    """Score a single lead and persist the ICP result."""
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead_data = _build_lead_data(lead)
    result = await claude_client.score_lead(lead_data)

    lead.icp_score = result.score
    lead.icp_tier = result.tier
    lead.icp_reasoning = result.fit_reasoning
    lead.icp_disqualifiers = to_json_field(result.disqualifiers)
    lead.personalized_hook = result.personalized_hook
    lead.scored_at = utcnow()

    db.add(Activity(
        lead_id=lead.id,
        type="note",
        content_snippet=f"ICP scored: {result.tier} ({result.score}/100)",
    ))
    db.commit()
    db.refresh(lead)

    if result.tier in ("A", "B"):
        await _notify_slack_hot_lead(lead, result.score, result.tier)

    return lead


# ---------------------------------------------------------------------------
# POST /score-unscored
# ---------------------------------------------------------------------------

@router.post("/score-unscored")
async def score_unscored(
    limit: int = Query(50, ge=1, le=500),
    tier_filter: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Score leads in bulk. Without tier_filter: only unscored leads.
    With tier_filter: re-score leads already assigned that tier."""
    query = select(Lead.id)
    if tier_filter:
        query = query.where(Lead.icp_tier == tier_filter)
    else:
        query = query.where(Lead.scored_at.is_(None))
    query = query.limit(limit)

    lead_ids = list(db.scalars(query).all())
    return await claude_client.score_leads_batch(lead_ids, db)


# ---------------------------------------------------------------------------
# POST /generate-hook/{lead_id}
# ---------------------------------------------------------------------------

@router.post("/generate-hook/{lead_id}")
async def generate_hook(lead_id: int, db: Session = Depends(get_db)):
    """Generate or regenerate a personalized cold email opener for a lead."""
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead_data = _build_lead_data(lead)
    company_data = _build_company_data(lead.company)
    hook = await claude_client.generate_email_hook(lead_data, company_data)

    lead.personalized_hook = hook
    db.commit()

    return {"lead_id": lead_id, "hook": hook}


# ---------------------------------------------------------------------------
# GET /cost-estimate
# ---------------------------------------------------------------------------

@router.get("/cost-estimate")
async def cost_estimate(lead_count: int = Query(100, ge=1)):
    """Return a rough cost estimate for scoring and hook generation."""
    return await claude_client.get_scoring_cost_estimate(lead_count)


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------

@router.get("/stats")
def scoring_stats(db: Session = Depends(get_db)):
    """Return scoring coverage and tier distribution statistics."""
    scored_count = db.scalar(
        select(func.count(Lead.id)).where(Lead.scored_at.is_not(None))
    ) or 0

    unscored_count = db.scalar(
        select(func.count(Lead.id)).where(Lead.scored_at.is_(None))
    ) or 0

    tier_rows = db.execute(
        select(Lead.icp_tier, func.count(Lead.id))
        .where(Lead.icp_tier.is_not(None))
        .group_by(Lead.icp_tier)
    ).all()
    tier_distribution: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    for tier, count in tier_rows:
        if tier in tier_distribution:
            tier_distribution[tier] = count

    avg_score_tier_a = db.scalar(
        select(func.avg(Lead.icp_score))
        .where(Lead.icp_tier == "A")
        .where(Lead.icp_score.is_not(None))
    )

    last_scored_at = db.scalar(select(func.max(Lead.scored_at)))

    return {
        "scored_count": scored_count,
        "unscored_count": unscored_count,
        "tier_distribution": tier_distribution,
        "avg_score_tier_a": round(float(avg_score_tier_a), 1) if avg_score_tier_a else None,
        "last_scored_at": last_scored_at,
    }
