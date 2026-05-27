import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import settings
from database import Company, Lead, SourcingRun, get_db
from schemas import LeadResponse, SourcingRunResponse
from services import hunter_client
from services.lead_provider import get_lead_provider

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas local to this router
# ---------------------------------------------------------------------------

class SourcingRunRequest(BaseModel):
    titles: Optional[list[str]] = None
    locations: Optional[list[str]] = None
    employee_min: Optional[int] = None
    employee_max: Optional[int] = None
    industries: Optional[list[str]] = None
    pages: int = 1
    per_page: int = 25


class BulkEnrichResponse(BaseModel):
    enriched: int
    leads: list[int]


# ---------------------------------------------------------------------------
# DB upsert helpers
# ---------------------------------------------------------------------------

def _upsert_company(db: Session, company_data: dict) -> Optional[Company]:
    """Insert or update a Company row; returns the persisted instance.

    Uses provider_id (normalized key) stored in the apollo_id column for dedup.
    """
    provider_id = company_data.get("provider_id")
    name = company_data.get("name")
    if not name:
        return None

    existing = None
    if provider_id:
        existing = db.scalar(select(Company).where(Company.apollo_id == provider_id))

    if existing:
        existing.name = name or existing.name
        existing.domain = company_data.get("domain") or existing.domain
        existing.industry = company_data.get("industry") or existing.industry
        existing.employee_count = company_data.get("employee_count") or existing.employee_count
        existing.hq_country = company_data.get("hq_country") or existing.hq_country
        existing.linkedin_url = company_data.get("linkedin_url") or existing.linkedin_url
        existing.updated_at = datetime.utcnow()
        db.flush()
        return existing

    company = Company(
        apollo_id=provider_id,
        name=name,
        domain=company_data.get("domain"),
        industry=company_data.get("industry"),
        employee_count=company_data.get("employee_count"),
        hq_country=company_data.get("hq_country"),
        linkedin_url=company_data.get("linkedin_url"),
    )
    db.add(company)
    db.flush()
    return company


def _upsert_lead(db: Session, result: dict, company_id: Optional[int]) -> tuple[Lead, bool]:
    """Insert a Lead if new; return (lead, is_new). Skips update on duplicates."""
    provider_id = result.get("provider_id")
    if provider_id:
        existing = db.scalar(select(Lead).where(Lead.apollo_id == provider_id))
        if existing:
            return existing, False

    lead = Lead(
        apollo_id=provider_id,
        first_name=result.get("first_name"),
        last_name=result.get("last_name"),
        full_name=result.get("full_name"),
        title=result.get("title"),
        seniority=result.get("seniority"),
        department=result.get("department"),
        linkedin_url=result.get("linkedin_url"),
        email=result.get("email"),
        email_verified=result.get("email_verified", False),
        phone=result.get("phone"),
        company_id=company_id,
        source=result.get("source", settings.ACTIVE_LEAD_PROVIDER),
        status="identified",
    )
    db.add(lead)
    db.flush()
    return lead, True


# ---------------------------------------------------------------------------
# Email enrichment waterfall
# ---------------------------------------------------------------------------

async def _waterfall_enrich(
    lead: Lead,
    company: Optional[Company],
) -> tuple[Optional[str], bool, Optional[str]]:
    """Run the three-step email enrichment waterfall.

    Returns (email, email_verified, email_source). email_source is one of:
    "hunter_domain", "{provider}_enrich", "hunter_finder", or None on failure.
    """
    provider = get_lead_provider()

    # Step 1: Hunter domain_search — one credit reveals all emails at a domain.
    # If the lead appears in results, no additional credit is needed.
    if company and company.domain:
        domain_results = await hunter_client.domain_search(company.domain)
        for entry in domain_results:
            if (
                entry.get("first_name", "").lower() == (lead.first_name or "").lower()
                and entry.get("last_name", "").lower() == (lead.last_name or "").lower()
            ):
                email = entry.get("email")
                if email:
                    logger.info("Lead %d: email found via hunter_domain", lead.id)
                    return email, True, "hunter_domain"

    # Step 2: Provider enrich (PDL only charges when work_email is found;
    # Apollo charges a credit when reveal_email=True and an email is returned).
    try:
        result = await provider.enrich_person(
            first_name=lead.first_name or "",
            last_name=lead.last_name or "",
            company_name=company.name if company else "",
            company_domain=company.domain if company else None,
            linkedin_url=lead.linkedin_url,
        )
        if result and result.get("email"):
            email_source = f"{settings.ACTIVE_LEAD_PROVIDER}_enrich"
            logger.info("Lead %d: email found via %s", lead.id, email_source)
            return result["email"], result.get("email_verified", False), email_source
    except Exception:
        logger.warning("Lead %d: provider enrich failed", lead.id, exc_info=True)

    # Step 3: Hunter find_email — individual search credit.
    if company and company.domain:
        result = await hunter_client.find_email(
            first_name=lead.first_name or "",
            last_name=lead.last_name or "",
            domain=company.domain,
        )
        if result and result.get("email"):
            logger.info("Lead %d: email found via hunter_finder", lead.id)
            return result["email"], result.get("email_verified", False), "hunter_finder"

    # Step 4: All paths exhausted.
    logger.info(
        "Lead %d: email not found via waterfall (Hunter domain + %s + Hunter finder)",
        lead.id,
        settings.ACTIVE_LEAD_PROVIDER,
    )
    return None, False, None


# ---------------------------------------------------------------------------
# POST /run
# ---------------------------------------------------------------------------

@router.post("/run", response_model=SourcingRunResponse)
async def run_sourcing(body: SourcingRunRequest, db: Session = Depends(get_db)):
    """Trigger a new lead-sourcing run using the configured provider."""
    titles = body.titles or settings.ICP_TITLES
    locations = body.locations or settings.ICP_LOCATIONS
    employee_min = body.employee_min if body.employee_min is not None else settings.ICP_EMPLOYEE_MIN
    employee_max = body.employee_max if body.employee_max is not None else settings.ICP_EMPLOYEE_MAX
    industries = body.industries or settings.ICP_INDUSTRIES or None

    logger.info("Sourcing run starting with provider: %s", settings.ACTIVE_LEAD_PROVIDER)

    # Credit guard for PDL: reject before creating the run record.
    if settings.ACTIVE_LEAD_PROVIDER == "pdl":
        from services.pdl_client import estimate_credits_for_run
        estimated = estimate_credits_for_run(per_page=body.per_page, pages=body.pages)
        logger.info("Estimated PDL credits for this run: %d", estimated)
        if estimated > settings.PDL_MAX_CREDITS_PER_RUN:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Run would consume ~{estimated} PDL credits, "
                    f"exceeding PDL_MAX_CREDITS_PER_RUN={settings.PDL_MAX_CREDITS_PER_RUN}. "
                    f"Reduce pages or increase PDL_MAX_CREDITS_PER_RUN in .env"
                ),
            )

    query_params_summary = {
        "provider": settings.ACTIVE_LEAD_PROVIDER,
        "titles": titles,
        "locations": locations,
        "employee_min": employee_min,
        "employee_max": employee_max,
        "pages": body.pages,
    }

    run = SourcingRun(
        status="running",
        query_params=json.dumps(query_params_summary),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    provider = get_lead_provider()
    leads_found = 0
    leads_new = 0

    try:
        for page in range(1, body.pages + 1):
            logger.info("Sourcing run %d — fetching page %d/%d", run.id, page, body.pages)
            results = await provider.search_people(
                titles=titles,
                locations=locations,
                employee_min=employee_min,
                employee_max=employee_max,
                industries=industries,
                page=page,
                per_page=body.per_page,
            )

            if not results:
                logger.info(
                    "Sourcing run %d — page %d returned no results, stopping early",
                    run.id,
                    page,
                )
                break

            for result in results:
                company = _upsert_company(db, result["company"])
                _, is_new = _upsert_lead(db, result, company.id if company else None)
                leads_found += 1
                if is_new:
                    leads_new += 1

            db.flush()

        run.status = "completed"
        run.leads_found = leads_found
        run.leads_new = leads_new
        run.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
        logger.info(
            "Sourcing run %d completed — found=%d new=%d", run.id, leads_found, leads_new
        )

    except Exception as exc:
        db.rollback()
        run.status = "failed"
        run.error_message = str(exc)
        run.leads_found = leads_found
        run.leads_new = leads_new
        run.completed_at = datetime.utcnow()
        db.add(run)
        db.commit()
        logger.exception("Sourcing run %d failed: %s", run.id, exc)
        raise

    return run


# ---------------------------------------------------------------------------
# GET /runs
# ---------------------------------------------------------------------------

@router.get("/runs", response_model=list[SourcingRunResponse])
def list_runs(limit: int = 20, offset: int = 0, db: Session = Depends(get_db)):
    """Return sourcing run history, most recent first."""
    rows = db.scalars(
        select(SourcingRun)
        .order_by(SourcingRun.started_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return rows


# ---------------------------------------------------------------------------
# GET /runs/{run_id}
# ---------------------------------------------------------------------------

@router.get("/runs/{run_id}", response_model=SourcingRunResponse)
def get_run(run_id: int, db: Session = Depends(get_db)):
    """Return a single sourcing run by ID."""
    run = db.get(SourcingRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Sourcing run not found")
    return run


# ---------------------------------------------------------------------------
# POST /enrich/{lead_id}
# ---------------------------------------------------------------------------

@router.post("/enrich/{lead_id}", response_model=LeadResponse)
async def enrich_lead(lead_id: int, db: Session = Depends(get_db)):
    """Enrich a single lead using the Hunter + provider waterfall.

    Waterfall order:
    1. Hunter domain_search (cheapest — one credit covers all emails at a domain)
    2. Active provider enrich (PDL charges only on success; Apollo charges on reveal)
    3. Hunter find_email (individual search credit)
    """
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    company = db.get(Company, lead.company_id) if lead.company_id else None

    email, email_verified, email_source = await _waterfall_enrich(lead, company)

    now = datetime.utcnow()

    if email:
        lead.email = email
        lead.email_verified = email_verified
        lead.email_source = email_source
        lead.enriched_at = now

    lead.updated_at = now
    db.commit()
    db.refresh(lead)
    return lead


# ---------------------------------------------------------------------------
# POST /enrich-tier-a
# ---------------------------------------------------------------------------

@router.post("/enrich-tier-a", response_model=BulkEnrichResponse)
async def enrich_tier_a(db: Session = Depends(get_db)):
    """Bulk-enrich up to 10 Tier A leads that are missing a verified email."""
    leads = db.scalars(
        select(Lead)
        .where(Lead.icp_tier == "A")
        .where((Lead.email.is_(None)) | (Lead.email_verified == False))  # noqa: E712
        .limit(10)
    ).all()

    enriched_count = 0
    enriched_ids: list[int] = []
    now = datetime.utcnow()

    for lead in leads:
        company = db.get(Company, lead.company_id) if lead.company_id else None
        try:
            email, email_verified, email_source = await _waterfall_enrich(lead, company)
        except Exception as exc:
            logger.warning("Failed to enrich lead %d: %s", lead.id, exc)
            continue

        if email:
            lead.email = email
            lead.email_verified = email_verified
            lead.email_source = email_source
            lead.enriched_at = now
            enriched_count += 1
            enriched_ids.append(lead.id)

        lead.updated_at = now

    db.commit()
    return BulkEnrichResponse(enriched=enriched_count, leads=enriched_ids)


# ---------------------------------------------------------------------------
# GET /usage
# ---------------------------------------------------------------------------

@router.get("/usage")
async def api_usage():
    """Return API usage stats for the active provider and Hunter.io."""
    provider = get_lead_provider()
    provider_stats = await provider.get_usage_stats()
    hunter_stats = await hunter_client.get_usage()
    return {
        "active_provider": settings.ACTIVE_LEAD_PROVIDER,
        "provider": provider_stats,
        "hunter": hunter_stats,
    }


# ---------------------------------------------------------------------------
# GET /provider-info
# ---------------------------------------------------------------------------

@router.get("/provider-info")
async def provider_info():
    """Return provider configuration for the Settings page."""
    return {
        "active_provider": settings.ACTIVE_LEAD_PROVIDER,
        "available_providers": ["pdl", "apollo"],
        "pdl_configured": bool(settings.PDL_API_KEY),
        "apollo_configured": bool(settings.APOLLO_API_KEY),
        "hunter_configured": bool(settings.HUNTER_API_KEY),
        "switching_instructions": (
            "To switch providers, set ACTIVE_LEAD_PROVIDER=apollo (or pdl) "
            "in your .env file and restart the backend container: "
            "docker compose restart backend"
        ),
    }
