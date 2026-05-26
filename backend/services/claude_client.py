"""Anthropic Claude API client for ICP fit scoring and email personalization."""

import asyncio
import json
import logging
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

from config import settings
from database import Company, Lead
from schemas import ICPScoreResult
from utils import parse_json_field, to_json_field, utcnow

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# Load the master ICP prompt once at module import time.
_icp_prompt: Optional[str] = None
try:
    with open(settings.PROMPT_PATH, "r", encoding="utf-8") as _f:
        _icp_prompt = _f.read()
except FileNotFoundError:
    logger.critical(
        "ICP prompt file not found at %s — scoring functions will return error fallback",
        settings.PROMPT_PATH,
    )

_FALLBACK_RESULT = ICPScoreResult(
    score=0,
    tier="D",
    fit_reasoning="Scoring failed — manual review needed",
    disqualifiers=[],
    next_action="hold_90d",
    personalized_hook="",
)

_COST_INPUT_PER_1K = 0.001
_COST_OUTPUT_PER_1K = 0.005


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences that Claude sometimes wraps JSON in."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    if text.startswith("```"):
        # Remove the opening fence (```json or just ```)
        text = text[text.index("\n") + 1:] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def _log_usage(model: str, usage: anthropic.types.Usage) -> None:
    cost = (usage.input_tokens / 1000 * _COST_INPUT_PER_1K) + (
        usage.output_tokens / 1000 * _COST_OUTPUT_PER_1K
    )
    logger.info(
        "Claude API usage: model=%s input_tokens=%d output_tokens=%d approx_cost_usd=%.6f",
        model,
        usage.input_tokens,
        usage.output_tokens,
        cost,
    )


def _build_lead_payload(lead: Lead) -> dict:
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


async def score_lead(lead_data: dict) -> ICPScoreResult:
    """Score a single lead's ICP fit using Claude Haiku."""
    if _icp_prompt is None:
        return _FALLBACK_RESULT

    user_message = "Score this prospect:\n\n" + json.dumps(lead_data, indent=2, default=str)

    def _call(messages: list) -> anthropic.types.Message:
        return client.messages.create(
            model=settings.ANTHROPIC_MODEL_SCORING,
            max_tokens=1024,
            system=_icp_prompt,
            messages=messages,
        )

    response = await asyncio.to_thread(_call, [{"role": "user", "content": user_message}])
    raw = response.content[0].text
    _log_usage(settings.ANTHROPIC_MODEL_SCORING, response.usage)

    try:
        cleaned = _strip_code_fences(raw)
        logger.debug("score_lead cleaned response (first 200 chars): %s", cleaned[:200])
        return ICPScoreResult(**json.loads(cleaned))
    except (json.JSONDecodeError, ValueError, Exception):
        logger.warning("score_lead: non-JSON response on first attempt, retrying. Raw: %.300s", raw)

    retry_message = (
        user_message
        + "\n\nYour previous response was not valid JSON. Return ONLY the JSON object, nothing else."
    )
    response2 = await asyncio.to_thread(_call, [{"role": "user", "content": retry_message}])
    raw2 = response2.content[0].text
    _log_usage(settings.ANTHROPIC_MODEL_SCORING, response2.usage)

    try:
        return ICPScoreResult(**json.loads(_strip_code_fences(raw2)))
    except (json.JSONDecodeError, ValueError, Exception):
        logger.error("score_lead: second attempt also non-JSON. Returning fallback. Raw: %.300s", raw2)
        return _FALLBACK_RESULT


async def generate_email_hook(lead_data: dict, company_data: dict) -> str:
    """Generate a personalized one-sentence cold email opener using Claude Sonnet."""
    system = (
        "You write personalized cold email openers for B2B outreach. "
        "Rules: max 22 words, reference ONE specific fact from the data, "
        "no flattery, no these banned phrases: 'I came across', 'I noticed', "
        "'Hope you are well', 'Just checking in', 'I wanted to reach out'. "
        "Return ONLY the sentence, no quotes."
    )
    payload = {
        "lead": lead_data,
        "company": company_data,
        "signals": company_data.get("company_recent_signals") or company_data.get("recent_signals"),
    }
    user_message = json.dumps(payload, indent=2, default=str)

    def _call() -> anthropic.types.Message:
        return client.messages.create(
            model=settings.ANTHROPIC_MODEL_WRITING,
            max_tokens=100,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )

    response = await asyncio.to_thread(_call)
    _log_usage(settings.ANTHROPIC_MODEL_WRITING, response.usage)
    return response.content[0].text.strip().strip('"').strip("'")


async def score_leads_batch(lead_ids: list[int], db: Session) -> dict:
    """Score multiple leads and persist results to the database. Returns a summary dict."""
    scored_count = 0
    tier_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    errors_count = 0

    for i, lead_id in enumerate(lead_ids):
        if i > 0:
            await asyncio.sleep(0.5)

        lead: Optional[Lead] = db.query(Lead).filter(Lead.id == lead_id).first()
        if lead is None:
            logger.warning("score_leads_batch: lead_id=%d not found, skipping", lead_id)
            errors_count += 1
            continue

        try:
            lead_data = _build_lead_payload(lead)
            result = await score_lead(lead_data)

            lead.icp_score = result.score
            lead.icp_tier = result.tier
            lead.icp_reasoning = result.fit_reasoning
            lead.icp_disqualifiers = to_json_field(result.disqualifiers)
            lead.personalized_hook = result.personalized_hook
            lead.scored_at = utcnow()
            db.commit()

            tier_counts[result.tier] = tier_counts.get(result.tier, 0) + 1
            scored_count += 1
        except Exception:
            logger.exception("score_leads_batch: unhandled error scoring lead_id=%d", lead_id)
            errors_count += 1
            db.rollback()

    return {
        "scored_count": scored_count,
        "tier_counts": tier_counts,
        "errors_count": errors_count,
    }


async def get_scoring_cost_estimate(lead_count: int) -> dict:
    """Return a rough cost estimate for scoring and hook generation."""
    haiku_cost_usd = lead_count * 0.003
    sonnet_cost_usd = lead_count * 0.025
    return {
        "haiku_cost_usd": haiku_cost_usd,
        "sonnet_cost_usd": sonnet_cost_usd,
        "total_for_scoring_only": haiku_cost_usd,
    }
