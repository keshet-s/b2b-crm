from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    event,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy import create_engine

from config import settings


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
)

if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        """Enable WAL mode for better concurrent read performance on SQLite."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    apollo_id: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    employee_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hq_country: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    funding_stage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_funding_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    last_funding_amount_usd: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Stored as JSON strings — deserialise in the service layer
    tech_stack: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    recent_signals: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    careers_page_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    leads: Mapped[list["Lead"]] = relationship("Lead", back_populates="company")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    apollo_id: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    seniority: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    company_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("companies.id"), nullable=True
    )

    # Provenance
    source: Mapped[str] = mapped_column(String, default="apollo", nullable=False)
    email_source: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # which waterfall step found the email

    # ICP scoring
    icp_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    icp_tier: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # A/B/C/D
    icp_reasoning: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    icp_disqualifiers: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON
    personalized_hook: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Pipeline
    status: Mapped[str] = mapped_column(String, default="identified", nullable=False)
    last_contacted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    next_action_due: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Timestamps
    scored_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    enriched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    company: Mapped[Optional["Company"]] = relationship("Company", back_populates="leads")
    activities: Mapped[list["Activity"]] = relationship(
        "Activity", back_populates="lead", cascade="all, delete-orphan"
    )


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("leads.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(String, nullable=False)
    channel: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    content_snippet: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    sentiment: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    lead: Mapped["Lead"] = relationship("Lead", back_populates="activities")


class SourcingRun(Base):
    __tablename__ = "sourcing_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String, default="running", nullable=False)
    leads_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    leads_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    query_params: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # JSON


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------

import logging as _logging
_db_logger = _logging.getLogger(__name__)


def _migrate_columns() -> None:
    """Add columns introduced after the initial schema was created.

    SQLAlchemy's create_all() never alters existing tables, so new columns
    must be applied here. Each ALTER TABLE is guarded by a PRAGMA check so
    the migration is safe to run on every startup.
    """
    with engine.connect() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(leads)"))}
        if "email_source" not in existing:
            conn.execute(text("ALTER TABLE leads ADD COLUMN email_source VARCHAR"))
            conn.commit()
            _db_logger.info("Migration: added email_source column to leads")


def init_db() -> None:
    """Create all tables and apply pending column migrations on every startup."""
    Base.metadata.create_all(bind=engine)
    _migrate_columns()
