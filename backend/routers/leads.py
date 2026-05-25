import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, noload, selectinload

from database import Activity, Company, Lead, get_db
from schemas import LeadCreate, LeadResponse, LeadUpdate

logger = logging.getLogger(__name__)

router = APIRouter()

PIPELINE_STAGES = [
    "identified", "enriched", "contacted", "engaged",
    "qualified", "meeting_held", "design_partner",
    "closed_won", "closed_lost", "archived",
]

_STAGE_LABELS = {
    "identified": "Identified",
    "enriched": "Enriched",
    "contacted": "Contacted",
    "engaged": "Engaged",
    "qualified": "Qualified",
    "meeting_held": "Meeting Held",
    "design_partner": "Design Partner",
    "closed_won": "Closed Won",
    "closed_lost": "Closed Lost",
    "archived": "Archived",
}

_VALID_SORT_FIELDS = {
    "created_at", "updated_at", "icp_score", "full_name",
    "status", "last_contacted_at", "next_action_due",
}


# ---------------------------------------------------------------------------
# Local schemas
# ---------------------------------------------------------------------------

class ManualLeadCreate(LeadCreate):
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    source: str = "manual"


class LeadListResponse(BaseModel):
    leads: list[LeadResponse]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_company(db: Session, name: str, domain: Optional[str] = None) -> Company:
    if domain:
        existing = db.scalar(select(Company).where(Company.domain == domain))
        if existing:
            return existing
    existing = db.scalar(select(Company).where(Company.name == name))
    if existing:
        return existing
    company = Company(name=name, domain=domain)
    db.add(company)
    db.flush()
    return company


def _load_lead_response(lead: Lead, db: Session) -> LeadResponse:
    """Reload lead with all relationships and return a fully populated LeadResponse."""
    fresh = db.scalar(
        select(Lead)
        .where(Lead.id == lead.id)
        .options(selectinload(Lead.company), selectinload(Lead.activities))
    )
    activities = sorted(fresh.activities, key=lambda a: a.occurred_at, reverse=True)
    return LeadResponse.model_validate(fresh).model_copy(
        update={"activities": activities, "activity_count": len(activities)}
    )


# ---------------------------------------------------------------------------
# GET /pipeline/summary  — must be defined before /{lead_id}
# ---------------------------------------------------------------------------

@router.get("/pipeline/summary")
def pipeline_summary(db: Session = Depends(get_db)):
    status_rows = db.execute(
        select(Lead.status, func.count(Lead.id).label("cnt"))
        .group_by(Lead.status)
    ).all()
    counts_by_status = {row.status: row.cnt for row in status_rows}

    tier_a_rows = db.execute(
        select(Lead.status, func.count(Lead.id).label("cnt"))
        .where(Lead.icp_tier == "A")
        .group_by(Lead.status)
    ).all()
    tier_a_by_status = {row.status: row.cnt for row in tier_a_rows}

    stages = [
        {
            "status": stage,
            "label": _STAGE_LABELS[stage],
            "count": counts_by_status.get(stage, 0),
            "tier_a_count": tier_a_by_status.get(stage, 0),
        }
        for stage in PIPELINE_STAGES
    ]

    tier_a_uncontacted = db.scalar(
        select(func.count(Lead.id))
        .where(Lead.icp_tier == "A")
        .where(Lead.status.in_(["identified", "enriched"]))
    ) or 0

    overdue_followups = db.scalar(
        select(func.count(Lead.id))
        .where(Lead.next_action_due.is_not(None))
        .where(Lead.next_action_due < datetime.utcnow())
        .where(~Lead.status.in_(["closed_won", "closed_lost", "archived"]))
    ) or 0

    return {
        "stages": stages,
        "total_leads": sum(row.cnt for row in status_rows),
        "tier_a_uncontacted": tier_a_uncontacted,
        "overdue_followups": overdue_followups,
    }


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------

@router.get("/", response_model=LeadListResponse)
def list_leads(
    status: Optional[str] = None,
    tier: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    db: Session = Depends(get_db),
):
    if sort_by not in _VALID_SORT_FIELDS:
        sort_by = "created_at"

    pattern = f"%{search}%" if search else None

    def _apply_filters(q):
        if search:
            q = q.outerjoin(Company, Lead.company_id == Company.id)
        if status:
            q = q.where(Lead.status == status)
        if tier:
            q = q.where(Lead.icp_tier == tier)
        if pattern:
            q = q.where(or_(
                Lead.full_name.ilike(pattern),
                Lead.email.ilike(pattern),
                Company.name.ilike(pattern),
            ))
        return q

    total = db.scalar(
        select(func.count()).select_from(_apply_filters(select(Lead.id)).subquery())
    ) or 0

    sort_col = getattr(Lead, sort_by, Lead.created_at)
    order = sort_col.asc() if sort_dir == "asc" else sort_col.desc()

    leads_list = db.scalars(
        _apply_filters(select(Lead))
        .options(selectinload(Lead.company), noload(Lead.activities))
        .order_by(order)
        .limit(limit)
        .offset(offset)
    ).unique().all()

    lead_ids = [lead.id for lead in leads_list]
    activity_counts: dict[int, int] = {}
    if lead_ids:
        rows = db.execute(
            select(Activity.lead_id, func.count(Activity.id).label("cnt"))
            .where(Activity.lead_id.in_(lead_ids))
            .group_by(Activity.lead_id)
        ).all()
        activity_counts = {row.lead_id: row.cnt for row in rows}

    result = [
        LeadResponse.model_validate(lead).model_copy(
            update={"activity_count": activity_counts.get(lead.id, 0), "activities": []}
        )
        for lead in leads_list
    ]

    return LeadListResponse(leads=result, total=total, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# POST /
# ---------------------------------------------------------------------------

@router.post("/", response_model=LeadResponse, status_code=201)
def create_lead(body: ManualLeadCreate, db: Session = Depends(get_db)):
    if body.status and body.status not in PIPELINE_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{body.status}'. Valid stages: {', '.join(PIPELINE_STAGES)}",
        )

    company_id = body.company_id
    if body.company_name and not company_id:
        company = _get_or_create_company(db, body.company_name, body.company_domain)
        company_id = company.id

    lead_data = body.model_dump(exclude={"company_name", "company_domain"})
    lead_data["company_id"] = company_id
    lead = Lead(**lead_data)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return _load_lead_response(lead, db)


# ---------------------------------------------------------------------------
# GET /{lead_id}
# ---------------------------------------------------------------------------

@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.scalar(
        select(Lead)
        .where(Lead.id == lead_id)
        .options(selectinload(Lead.company), selectinload(Lead.activities))
    )
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    activities = sorted(lead.activities, key=lambda a: a.occurred_at, reverse=True)
    return LeadResponse.model_validate(lead).model_copy(
        update={"activities": activities, "activity_count": len(activities)}
    )


# ---------------------------------------------------------------------------
# GET /{lead_id}/export
# ---------------------------------------------------------------------------

@router.get("/{lead_id}/export")
def export_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.scalar(
        select(Lead)
        .where(Lead.id == lead_id)
        .options(selectinload(Lead.company), selectinload(Lead.activities))
    )
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    activities_summary = [
        {
            "type": a.type,
            "channel": a.channel,
            "content_snippet": a.content_snippet,
            "sentiment": a.sentiment,
            "occurred_at": a.occurred_at.isoformat(),
        }
        for a in sorted(lead.activities, key=lambda a: a.occurred_at, reverse=True)[:10]
    ]

    company_data = None
    if lead.company:
        company_data = {
            "name": lead.company.name,
            "domain": lead.company.domain,
            "industry": lead.company.industry,
            "employee_count": lead.company.employee_count,
            "hq_country": lead.company.hq_country,
            "tech_stack": lead.company.tech_stack,
            "recent_signals": lead.company.recent_signals,
        }

    return {
        "lead": {
            "id": lead.id,
            "full_name": lead.full_name,
            "title": lead.title,
            "email": lead.email,
            "email_verified": lead.email_verified,
            "linkedin_url": lead.linkedin_url,
            "status": lead.status,
            "icp_tier": lead.icp_tier,
            "icp_score": lead.icp_score,
            "notes": lead.notes,
            "next_action_due": lead.next_action_due.isoformat() if lead.next_action_due else None,
        },
        "company": company_data,
        "activities_summary": activities_summary,
        "personalized_hook": lead.personalized_hook,
        "icp_reasoning": lead.icp_reasoning,
    }


# ---------------------------------------------------------------------------
# PATCH /{lead_id}
# ---------------------------------------------------------------------------

@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(lead_id: int, body: LeadUpdate, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    update_data = body.model_dump(exclude_unset=True)

    if "status" in update_data and update_data["status"] not in PIPELINE_STAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{update_data['status']}'. Valid stages: {', '.join(PIPELINE_STAGES)}",
        )

    old_status = lead.status
    now = datetime.utcnow()

    for field, value in update_data.items():
        setattr(lead, field, value)
    lead.updated_at = now

    if "status" in update_data and update_data["status"] != old_status:
        db.add(Activity(
            lead_id=lead.id,
            type="status_change",
            content_snippet=f"Status changed: {old_status} → {update_data['status']}",
            occurred_at=now,
        ))

    db.commit()
    return _load_lead_response(lead, db)


# ---------------------------------------------------------------------------
# DELETE /{lead_id}
# ---------------------------------------------------------------------------

@router.delete("/{lead_id}")
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead.status = "archived"
    lead.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Lead archived", "lead_id": lead_id}
