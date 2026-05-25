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
from services import apollo_client
from services.apollo_client import build_icp_search_params, parse_apollo_person

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
    pages: int = 1


class BulkEnrichResponse(BaseModel):
    enriched: int
    leads: list[int]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upsert_company(db: Session, company_data: dict) -> Optional[Company]:
    """Insert or update a Company row; returns the persisted instance."""
    apollo_id = company_data.get("apollo_id")
    name = company_data.get("name")
    if not name:
        return None

    if apollo_id:
        existing = db.scalar(select(Company).where(Company.apollo_id == apollo_id))
    else:
        existing = None

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
        apollo_id=apollo_id,
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


def _upsert_lead(db: Session, parsed: dict, company_id: Optional[int]) -> tuple[Lead, bool]:
    """Insert a Lead if new; return (lead, is_new). Skips update on duplicates."""
    apollo_id = parsed.get("apollo_id")
    if apollo_id:
        existing = db.scalar(select(Lead).where(Lead.apollo_id == apollo_id))
        if existing:
            return existing, False

    lead = Lead(
        apollo_id=apollo_id,
        first_name=parsed.get("first_name"),
        last_name=parsed.get("last_name"),
        full_name=parsed.get("full_name"),
        title=parsed.get("title"),
        seniority=parsed.get("seniority"),
        department=parsed.get("department"),
        linkedin_url=parsed.get("linkedin_url"),
        email=parsed.get("email"),
        email_verified=parsed.get("email_verified", False),
        phone=parsed.get("phone"),
        company_id=company_id,
        source="apollo",
        status="identified",
    )
    db.add(lead)
    db.flush()
    return lead, True


# ---------------------------------------------------------------------------
# POST /run
# ---------------------------------------------------------------------------

@router.post("/run", response_model=SourcingRunResponse)
async def run_sourcing(body: SourcingRunRequest, db: Session = Depends(get_db)):
    """Trigger a new Apollo people-search sourcing run.

    Uses ICP settings as defaults; all fields in the request body are
    optional overrides.
    """
    titles = body.titles or settings.ICP_TITLES
    locations = body.locations or settings.ICP_LOCATIONS
    employee_min = body.employee_min if body.employee_min is not None else settings.ICP_EMPLOYEE_MIN
    employee_max = body.employee_max if body.employee_max is not None else settings.ICP_EMPLOYEE_MAX

    query_params_base = build_icp_search_params(
        titles=titles,
        locations=locations,
        employee_min=employee_min,
        employee_max=employee_max,
    )

    run = SourcingRun(
        status="running",
        query_params=json.dumps(query_params_base),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    leads_found = 0
    leads_new = 0

    try:
        for page in range(1, body.pages + 1):
            logger.info("Sourcing run %d — fetching page %d/%d", run.id, page, body.pages)
            response = await apollo_client.search_people(query_params_base, page=page)
            people = response.get("people") or []

            for raw_person in people:
                parsed = parse_apollo_person(raw_person)
                company = _upsert_company(db, parsed["company"])
                _, is_new = _upsert_lead(db, parsed, company.id if company else None)
                leads_found += 1
                if is_new:
                    leads_new += 1

            db.flush()

            # Stop early if Apollo returned fewer results than requested
            pagination = response.get("pagination") or {}
            total_pages = pagination.get("total_pages", 1)
            if page >= total_pages:
                break

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
    """Enrich a single lead with a verified email via Apollo /people/match.

    Consumes Apollo credits when a verified email is revealed.
    """
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    company = db.get(Company, lead.company_id) if lead.company_id else None

    person = await apollo_client.enrich_person(
        first_name=lead.first_name or "",
        last_name=lead.last_name or "",
        organization_name=company.name if company else "",
        domain=company.domain if company else None,
        reveal_email=True,
    )

    now = datetime.utcnow()

    if person:
        email = person.get("email") or person.get("work_email")
        email_status = person.get("email_status")
        email_verified = email_status == "verified"

        if email:
            lead.email = email
            lead.email_verified = email_verified
            lead.enriched_at = now
            if email_verified:
                logger.info("Lead %d enriched — credit consumed (verified email revealed)", lead_id)
            else:
                logger.info("Lead %d enriched — email found but not verified (status=%s)", lead_id, email_status)
        else:
            logger.info("Lead %d enriched — no email returned by Apollo", lead_id)
    else:
        logger.info("Lead %d — Apollo returned no match", lead_id)

    lead.updated_at = now
    db.commit()
    db.refresh(lead)
    return lead


# ---------------------------------------------------------------------------
# POST /enrich-tier-a
# ---------------------------------------------------------------------------

@router.post("/enrich-tier-a", response_model=BulkEnrichResponse)
async def enrich_tier_a(db: Session = Depends(get_db)):
    """Bulk-enrich up to 10 Tier A leads that are missing a verified email.

    Processes at most 10 leads per call to keep credit usage predictable.
    """
    leads = db.scalars(
        select(Lead)
        .where(Lead.icp_tier == "A")
        .where((Lead.email.is_(None)) | (Lead.email_verified == False))  # noqa: E712
        .limit(10)
    ).all()

    enriched_count = 0
    enriched_ids: list[int] = []

    for lead in leads:
        company = db.get(Company, lead.company_id) if lead.company_id else None
        try:
            person = await apollo_client.enrich_person(
                first_name=lead.first_name or "",
                last_name=lead.last_name or "",
                organization_name=company.name if company else "",
                domain=company.domain if company else None,
                reveal_email=True,
            )
        except Exception as exc:
            logger.warning("Failed to enrich lead %d: %s", lead.id, exc)
            continue

        now = datetime.utcnow()

        if person:
            email = person.get("email") or person.get("work_email")
            email_status = person.get("email_status")
            email_verified = email_status == "verified"

            if email:
                lead.email = email
                lead.email_verified = email_verified
                lead.enriched_at = now
                if email_verified:
                    logger.info(
                        "Bulk enrich: lead %d — credit consumed (verified email revealed)", lead.id
                    )
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
    """Return Apollo API credit usage stats (no credits consumed)."""
    return await apollo_client.get_api_usage()
