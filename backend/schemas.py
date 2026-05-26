from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------

class CompanyCreate(BaseModel):
    apollo_id: Optional[str] = None
    name: str
    domain: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    hq_country: Optional[str] = None
    funding_stage: Optional[str] = None
    last_funding_date: Optional[date] = None
    last_funding_amount_usd: Optional[int] = None
    tech_stack: Optional[str] = None        # JSON string
    recent_signals: Optional[str] = None    # JSON string
    linkedin_url: Optional[str] = None
    careers_page_url: Optional[str] = None


class CompanyResponse(CompanyCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------

class ActivityCreate(BaseModel):
    lead_id: int
    type: str
    channel: Optional[str] = None
    content_snippet: Optional[str] = None
    sentiment: Optional[str] = None
    occurred_at: Optional[datetime] = None


class ActivityResponse(ActivityCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    created_at: datetime


# ---------------------------------------------------------------------------
# Lead
# ---------------------------------------------------------------------------

class LeadCreate(BaseModel):
    apollo_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    email_verified: bool = False
    email_source: Optional[str] = None  # "hunter_domain"|"pdl_enrich"|"apollo_enrich"|"hunter_finder"
    phone: Optional[str] = None
    company_id: Optional[int] = None
    source: str = "apollo"
    status: str = "identified"
    notes: Optional[str] = None


class LeadUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    title: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None
    linkedin_url: Optional[str] = None
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    phone: Optional[str] = None
    company_id: Optional[int] = None
    source: Optional[str] = None
    icp_score: Optional[int] = None
    icp_tier: Optional[str] = None
    icp_reasoning: Optional[str] = None
    icp_disqualifiers: Optional[str] = None
    personalized_hook: Optional[str] = None
    status: Optional[str] = None
    last_contacted_at: Optional[datetime] = None
    next_action_due: Optional[datetime] = None
    notes: Optional[str] = None
    scored_at: Optional[datetime] = None
    enriched_at: Optional[datetime] = None


class LeadResponse(LeadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    icp_score: Optional[int] = None
    icp_tier: Optional[str] = None
    icp_reasoning: Optional[str] = None
    icp_disqualifiers: Optional[str] = None
    personalized_hook: Optional[str] = None
    last_contacted_at: Optional[datetime] = None
    next_action_due: Optional[datetime] = None
    scored_at: Optional[datetime] = None
    enriched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    company: Optional[CompanyResponse] = None
    activities: list[ActivityResponse] = []
    activity_count: int = 0


# ---------------------------------------------------------------------------
# SourcingRun
# ---------------------------------------------------------------------------

class SourcingRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    leads_found: int
    leads_new: int
    error_message: Optional[str] = None
    query_params: Optional[str] = None  # JSON string


# ---------------------------------------------------------------------------
# ICP scoring result (returned by the scoring service, not stored directly)
# ---------------------------------------------------------------------------

class ICPScoreResult(BaseModel):
    score: int                              # 0–100
    tier: str                               # 'A', 'B', 'C', 'D'
    fit_reasoning: str | None = None
    disqualifiers: list[str] = []
    next_action: str | None = None
    personalized_hook: str | None = None


# ---------------------------------------------------------------------------
# Pipeline statistics (dashboard summary)
# ---------------------------------------------------------------------------

class PipelineStats(BaseModel):
    # Lead counts keyed by pipeline status (e.g. {"identified": 42, "contacted": 18})
    counts_by_status: dict[str, int]
    # Lead counts keyed by ICP tier (e.g. {"A": 5, "B": 12, "C": 30, "D": 8})
    counts_by_tier: dict[str, int]
    # Number of activities logged in the last 7 days
    recent_activity_count: int
