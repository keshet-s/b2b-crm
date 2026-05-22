import logging
import time
from datetime import datetime

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

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
    db_path = settings.DATABASE_URL.replace("sqlite:////", "/")
    logger.info("B2B CRM API v1.0.0 started — DB: %s", db_path)

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
