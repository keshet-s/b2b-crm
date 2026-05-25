import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Activity, Company, Lead, get_db
from schemas import ActivityCreate, ActivityResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Local schemas
# ---------------------------------------------------------------------------

class ActivityWithLeadResponse(ActivityResponse):
    model_config = ConfigDict(from_attributes=True)

    lead_name: Optional[str] = None
    company_name: Optional[str] = None


# ---------------------------------------------------------------------------
# POST /
# ---------------------------------------------------------------------------

@router.post("/", response_model=ActivityResponse, status_code=201)
def create_activity(body: ActivityCreate, db: Session = Depends(get_db)):
    lead = db.get(Lead, body.lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    now = datetime.utcnow()
    activity = Activity(
        lead_id=body.lead_id,
        type=body.type,
        channel=body.channel,
        content_snippet=body.content_snippet,
        sentiment=body.sentiment,
        occurred_at=body.occurred_at or now,
    )
    db.add(activity)

    if body.type == "email_sent":
        lead.last_contacted_at = now
        lead.updated_at = now

    db.commit()
    db.refresh(activity)
    return activity


# ---------------------------------------------------------------------------
# GET /recent  — must be defined before /lead/{lead_id}
# ---------------------------------------------------------------------------

@router.get("/recent", response_model=list[ActivityWithLeadResponse])
def recent_activities(db: Session = Depends(get_db)):
    rows = db.execute(
        select(
            Activity,
            Lead.full_name.label("lead_name"),
            Company.name.label("company_name"),
        )
        .join(Lead, Activity.lead_id == Lead.id)
        .outerjoin(Company, Lead.company_id == Company.id)
        .order_by(Activity.occurred_at.desc())
        .limit(50)
    ).all()

    result = []
    for activity, lead_name, company_name in rows:
        resp = ActivityWithLeadResponse.model_validate(activity)
        result.append(resp.model_copy(update={"lead_name": lead_name, "company_name": company_name}))
    return result


# ---------------------------------------------------------------------------
# GET /lead/{lead_id}
# ---------------------------------------------------------------------------

@router.get("/lead/{lead_id}", response_model=list[ActivityResponse])
def list_lead_activities(
    lead_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    activities = db.scalars(
        select(Activity)
        .where(Activity.lead_id == lead_id)
        .order_by(Activity.occurred_at.desc())
        .limit(limit)
    ).all()
    return list(activities)
