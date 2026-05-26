import logging
import os
import time
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

import scheduler
from config import settings
from database import Activity, Lead, SourcingRun, get_db, init_db
from routers import activities, companies, leads, scoring, sourcing
from schemas import PipelineStats
from utils import days_ago

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("crm")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="B2B CRM API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Internal-only tool — allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def _log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d  (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def _startup():
    init_db()
    scheduler.start()
    db_path = settings.DATABASE_URL.replace("sqlite:////", "/")
    logger.info("B2B CRM API v1.0.0 started — DB: %s", db_path)


@app.on_event("shutdown")
def _shutdown():
    scheduler.shutdown()

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(leads.router,      prefix="/api/leads",      tags=["leads"])
app.include_router(companies.router,  prefix="/api/companies",  tags=["companies"])
app.include_router(sourcing.router,   prefix="/api/sourcing",   tags=["sourcing"])
app.include_router(scoring.router,    prefix="/api/scoring",    tags=["scoring"])
app.include_router(activities.router, prefix="/api/activities", tags=["activities"])

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["ops"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "db": "connected",
    }

# ---------------------------------------------------------------------------
# Scheduler endpoints
# ---------------------------------------------------------------------------

@app.get("/api/scheduler/jobs", tags=["scheduler"])
def list_scheduler_jobs():
    """Return all registered background jobs with their next run times."""
    return {"jobs": scheduler.get_jobs_info()}


@app.post("/api/scheduler/trigger/{job_id}", tags=["scheduler"])
def trigger_scheduler_job(job_id: str):
    """Manually trigger a scheduled job by its ID (runs in background thread)."""
    from fastapi import HTTPException
    if not scheduler.trigger_job(job_id):
        raise HTTPException(
            status_code=404,
            detail=f"Unknown job '{job_id}'. Valid IDs: {list(scheduler._JOB_MAP.keys())}",
        )
    return {"triggered": job_id, "status": "running"}


# ---------------------------------------------------------------------------
# Pipeline stats
# ---------------------------------------------------------------------------

@app.get("/api/stats", response_model=PipelineStats, tags=["ops"])
def pipeline_stats(db: Session = Depends(get_db)):
    # Counts by pipeline status
    status_rows = db.execute(
        select(Lead.status, func.count(Lead.id)).group_by(Lead.status)
    ).all()
    counts_by_status = {row[0]: row[1] for row in status_rows}

    # Counts by ICP tier (exclude un-scored leads where tier is NULL)
    tier_rows = db.execute(
        select(Lead.icp_tier, func.count(Lead.id))
        .where(Lead.icp_tier.is_not(None))
        .group_by(Lead.icp_tier)
    ).all()
    counts_by_tier = {row[0]: row[1] for row in tier_rows}

    # Activity volume in the last 7 days
    recent_activity_count = db.scalar(
        select(func.count(Activity.id)).where(
            Activity.created_at >= days_ago(7)
        )
    ) or 0

    return PipelineStats(
        counts_by_status=counts_by_status,
        counts_by_tier=counts_by_tier,
        recent_activity_count=recent_activity_count,
    )


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------

@app.get("/api/settings/icp-prompt", tags=["settings"])
def icp_prompt():
    """Read and return the ICP scoring prompt file."""
    path = settings.PROMPT_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content, "path": path}
    except FileNotFoundError:
        return {"content": "", "path": path, "error": f"File not found: {path}"}
    except Exception as exc:
        return {"content": "", "path": path, "error": str(exc)}


@app.get("/api/settings/icp-config", tags=["settings"])
def icp_config():
    """Return current ICP configuration (no API keys)."""
    return {
        "ICP_TITLES":               settings.ICP_TITLES,
        "ICP_LOCATIONS":            settings.ICP_LOCATIONS,
        "ICP_INDUSTRIES":           settings.ICP_INDUSTRIES,
        "ICP_EMPLOYEE_MIN":         settings.ICP_EMPLOYEE_MIN,
        "ICP_EMPLOYEE_MAX":         settings.ICP_EMPLOYEE_MAX,
        "ANTHROPIC_MODEL_SCORING":  settings.ANTHROPIC_MODEL_SCORING,
        "ANTHROPIC_MODEL_WRITING":  settings.ANTHROPIC_MODEL_WRITING,
    }


@app.get("/api/settings/data-health", tags=["settings"])
def data_health(db: Session = Depends(get_db)):
    """Return data quality and coverage statistics."""
    stale_cutoff = datetime.utcnow() - timedelta(days=30)

    total       = db.scalar(select(func.count(Lead.id))) or 0
    with_email  = db.scalar(select(func.count(Lead.id)).where(Lead.email.is_not(None))) or 0
    verified    = db.scalar(select(func.count(Lead.id)).where(Lead.email_verified == True)) or 0  # noqa: E712
    scored      = db.scalar(select(func.count(Lead.id)).where(Lead.scored_at.is_not(None))) or 0
    with_hook   = db.scalar(select(func.count(Lead.id)).where(Lead.personalized_hook.is_not(None))) or 0
    stale       = db.scalar(select(func.count(Lead.id)).where(Lead.updated_at < stale_cutoff)) or 0

    db_path       = settings.DATABASE_URL.replace("sqlite:////", "/")
    db_size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0

    return {
        "total":         total,
        "with_email":    with_email,
        "without_email": total - with_email,
        "verified_email": verified,
        "scored":        scored,
        "unscored":      total - scored,
        "with_hook":     with_hook,
        "stale_30d":     stale,
        "db_size_bytes": db_size_bytes,
    }


@app.get("/api/settings/api-status", tags=["settings"])
def api_key_status():
    """Return which API keys/webhooks are configured (not the values)."""
    return {
        "apollo":    bool(settings.APOLLO_API_KEY),
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "hunter":    bool(settings.HUNTER_API_KEY),
        "slack":     bool(settings.SLACK_WEBHOOK_URL),
        "pdl":       bool(settings.PDL_API_KEY),
    }
