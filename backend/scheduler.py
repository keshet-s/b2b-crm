"""Background job scheduler using APScheduler BackgroundScheduler.

Each job is a plain synchronous function (APScheduler runs them in a
thread pool). Async service calls (Apollo, Claude, Slack) are executed
with asyncio.run(), which creates a fresh event loop per invocation.
Every job opens its own DB session and closes it in a finally block so
a crashed job never leaks a connection.
"""

import asyncio
import json
import logging
import threading
import traceback
from datetime import date, datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from config import settings
from database import Company, Lead, SourcingRun, SessionLocal
from services import apollo_client, claude_client, slack_client
from services.apollo_client import build_icp_search_params, parse_apollo_person

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler(timezone="UTC")


# ---------------------------------------------------------------------------
# Shared DB helpers (mirror of sourcing router upsert logic)
# ---------------------------------------------------------------------------

def _upsert_company(db, company_data: dict) -> Optional[Company]:
    apollo_id = company_data.get("apollo_id")
    name = company_data.get("name")
    if not name:
        return None

    existing = None
    if apollo_id:
        existing = db.scalar(select(Company).where(Company.apollo_id == apollo_id))

    if existing:
        existing.name = name
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


def _upsert_lead(db, parsed: dict, company_id: Optional[int]) -> tuple[Lead, bool]:
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
# Job 1: Daily sourcing — 06:00 UTC
# ---------------------------------------------------------------------------

def daily_sourcing_job() -> None:
    try:
        titles = list(settings.ICP_TITLES)
        if len(titles) > 3:
            batch_size = 3
            day_of_year = date.today().timetuple().tm_yday
            offset = (day_of_year * batch_size) % len(titles)
            batch = titles[offset : offset + batch_size]
            titles = batch if batch else titles[:batch_size]

        query_params = build_icp_search_params(
            titles=titles,
            locations=settings.ICP_LOCATIONS,
            employee_min=settings.ICP_EMPLOYEE_MIN,
            employee_max=settings.ICP_EMPLOYEE_MAX,
        )

        db = SessionLocal()
        run = SourcingRun(status="running", query_params=json.dumps(query_params))
        db.add(run)
        db.commit()
        db.refresh(run)

        leads_found = 0
        leads_new = 0

        try:
            response = asyncio.run(
                apollo_client.search_people(query_params, page=1, per_page=100)
            )
            people = response.get("people") or []

            for raw_person in people:
                parsed = parse_apollo_person(raw_person)
                company = _upsert_company(db, parsed["company"])
                _, is_new = _upsert_lead(db, parsed, company.id if company else None)
                leads_found += 1
                if is_new:
                    leads_new += 1

            db.flush()
            run.status = "completed"
            run.leads_found = leads_found
            run.leads_new = leads_new
            run.completed_at = datetime.utcnow()
            db.commit()
            logger.info("Daily sourcing: found %d, new %d", leads_found, leads_new)

        except Exception:
            db.rollback()
            run.status = "failed"
            run.error_message = traceback.format_exc()[:1000]
            run.leads_found = leads_found
            run.leads_new = leads_new
            run.completed_at = datetime.utcnow()
            db.add(run)
            db.commit()
            logger.exception("Daily sourcing job failed")

        finally:
            db.close()

    except Exception:
        logger.exception("Daily sourcing job: outer error")


# ---------------------------------------------------------------------------
# Job 2: Daily scoring — 07:00 UTC
# ---------------------------------------------------------------------------

def daily_scoring_job() -> None:
    try:
        db = SessionLocal()
        try:
            lead_ids = list(
                db.scalars(select(Lead.id).where(Lead.scored_at.is_(None)).limit(100)).all()
            )

            if not lead_ids:
                logger.info("Daily scoring: no unscored leads")
                return

            result = asyncio.run(claude_client.score_leads_batch(lead_ids, db))
            logger.info(
                "Daily scoring: scored=%d tiers=%s errors=%d",
                result["scored_count"],
                result["tier_counts"],
                result["errors_count"],
            )

        finally:
            db.close()

    except Exception:
        logger.exception("Daily scoring job: unexpected error")


# ---------------------------------------------------------------------------
# Job 3: Daily Slack digest — 08:00 UTC
# ---------------------------------------------------------------------------

def daily_slack_digest() -> None:
    if not settings.SLACK_WEBHOOK_URL:
        return

    try:
        db = SessionLocal()
        try:
            leads = db.scalars(
                select(Lead)
                .where(Lead.icp_tier == "A")
                .where(Lead.status.in_(["identified", "enriched"]))
            ).all()

            leads_data = []
            for lead in leads:
                company = db.get(Company, lead.company_id) if lead.company_id else None
                leads_data.append({
                    "full_name": lead.full_name,
                    "company_name": company.name if company else "—",
                    "icp_tier": lead.icp_tier,
                    "icp_score": lead.icp_score,
                })

            asyncio.run(slack_client.send_daily_digest(leads_data))
            logger.info("Daily Slack digest: sent digest with %d Tier A leads", len(leads_data))

        finally:
            db.close()

    except Exception:
        logger.exception("Daily Slack digest job: unexpected error")


# ---------------------------------------------------------------------------
# Job 4: Follow-up reminders — 09:00 UTC
# ---------------------------------------------------------------------------

def followup_reminder_job() -> None:
    if not settings.SLACK_WEBHOOK_URL:
        return

    try:
        db = SessionLocal()
        try:
            now = datetime.utcnow()
            leads = db.scalars(
                select(Lead)
                .where(Lead.next_action_due <= now)
                .where(Lead.status.in_(["contacted", "engaged", "qualified"]))
                .limit(20)
            ).all()

            if not leads:
                logger.info("Follow-up reminder: no overdue leads")
                return

            async def _send_all(overdue_leads):
                count = 0
                for lead in overdue_leads:
                    name = lead.full_name or f"Lead #{lead.id}"
                    due = (
                        lead.next_action_due.strftime("%Y-%m-%d")
                        if lead.next_action_due
                        else "unknown"
                    )
                    msg = (
                        f"Follow-up overdue for *{name}* "
                        f"(status: {lead.status}) — was due {due}"
                    )
                    await slack_client.send_pipeline_alert(msg, lead_id=lead.id)
                    count += 1
                return count

            sent = asyncio.run(_send_all(list(leads)))
            logger.info("Follow-up reminder job: sent %d reminders", sent)

        finally:
            db.close()

    except Exception:
        logger.exception("Follow-up reminder job: unexpected error")


# ---------------------------------------------------------------------------
# Job 5: Weekly re-enrichment — Sunday 10:00 UTC
# ---------------------------------------------------------------------------

def weekly_reenrichment_job() -> None:
    try:
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(days=30)
            leads = list(
                db.scalars(
                    select(Lead)
                    .where(Lead.icp_tier.in_(["A", "B"]))
                    .where(
                        (Lead.enriched_at.is_(None)) | (Lead.enriched_at < cutoff)
                    )
                    .where(Lead.email_verified == False)  # noqa: E712
                    .limit(10)
                ).all()
            )

            if not leads:
                logger.info("Weekly re-enrichment: no leads to enrich")
                return

            async def _enrich_batch(batch):
                results = []
                for lead in batch:
                    company = db.get(Company, lead.company_id) if lead.company_id else None
                    try:
                        person = await apollo_client.enrich_person(
                            first_name=lead.first_name or "",
                            last_name=lead.last_name or "",
                            organization_name=company.name if company else "",
                            domain=company.domain if company else None,
                            reveal_email=True,
                        )
                        results.append((lead, person))
                    except Exception:
                        logger.warning(
                            "Re-enrichment: Apollo call failed for lead %d",
                            lead.id,
                            exc_info=True,
                        )
                        results.append((lead, None))
                return results

            enrichment_results = asyncio.run(_enrich_batch(leads))

            enriched_count = 0
            for lead, person in enrichment_results:
                if not person:
                    continue
                email = person.get("email") or person.get("work_email")
                if email:
                    lead.email = email
                    lead.email_verified = person.get("email_status") == "verified"
                    lead.enriched_at = datetime.utcnow()
                    lead.updated_at = datetime.utcnow()
                    enriched_count += 1

            db.commit()
            logger.info(
                "Weekly re-enrichment: enriched %d of %d leads",
                enriched_count,
                len(leads),
            )

        finally:
            db.close()

    except Exception:
        logger.exception("Weekly re-enrichment job: unexpected error")


# ---------------------------------------------------------------------------
# Job registry (used for manual trigger endpoint)
# ---------------------------------------------------------------------------

_JOB_MAP: dict[str, object] = {
    "daily_sourcing_job":    daily_sourcing_job,
    "daily_scoring_job":     daily_scoring_job,
    "daily_slack_digest":    daily_slack_digest,
    "followup_reminder_job": followup_reminder_job,
    "weekly_reenrichment_job": weekly_reenrichment_job,
}


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

def start() -> None:
    """Register all cron jobs and start the scheduler."""
    _scheduler.add_job(
        daily_sourcing_job,
        CronTrigger(hour=6, minute=0, timezone="UTC"),
        id="daily_sourcing_job",
        replace_existing=True,
    )
    _scheduler.add_job(
        daily_scoring_job,
        CronTrigger(hour=7, minute=0, timezone="UTC"),
        id="daily_scoring_job",
        replace_existing=True,
    )
    _scheduler.add_job(
        daily_slack_digest,
        CronTrigger(hour=8, minute=0, timezone="UTC"),
        id="daily_slack_digest",
        replace_existing=True,
    )
    _scheduler.add_job(
        followup_reminder_job,
        CronTrigger(hour=9, minute=0, timezone="UTC"),
        id="followup_reminder_job",
        replace_existing=True,
    )
    _scheduler.add_job(
        weekly_reenrichment_job,
        CronTrigger(day_of_week="sun", hour=10, minute=0, timezone="UTC"),
        id="weekly_reenrichment_job",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started — %d jobs registered", len(_scheduler.get_jobs()))


def shutdown() -> None:
    """Stop the scheduler without waiting for running jobs to finish."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")


def get_jobs_info() -> list[dict]:
    """Return metadata for all registered jobs (used by the API endpoint)."""
    return [
        {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
        }
        for job in _scheduler.get_jobs()
    ]


def trigger_job(job_id: str) -> bool:
    """Run a job by ID in a daemon thread. Returns False if job_id is unknown."""
    func = _JOB_MAP.get(job_id)
    if func is None:
        return False
    threading.Thread(target=func, daemon=True, name=f"manual-{job_id}").start()
    return True
