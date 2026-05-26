"""PeopleDataLabs v5 REST API client (async, httpx-based).

Implements PDLProvider(LeadProvider) for people search and enrichment.
Base URL: https://api.peopledatalabs.com/v5
"""

import logging

import httpx

from config import settings
from services.lead_provider import LeadProvider

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.peopledatalabs.com/v5"
_HEADERS = {"X-Api-Key": settings.PDL_API_KEY, "Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_pdl_person(raw: dict) -> dict:
    work_emails: list = raw.get("work_email") or []
    if isinstance(work_emails, str):
        work_emails = [work_emails]
    email = work_emails[0] if work_emails else None

    levels: list = raw.get("job_title_levels") or []

    return {
        "provider_id": raw.get("id"),
        "first_name": raw.get("first_name"),
        "last_name": raw.get("last_name"),
        "full_name": raw.get("full_name"),
        "title": raw.get("job_title"),
        "seniority": levels[0] if levels else None,
        "department": raw.get("job_title_role"),
        "linkedin_url": raw.get("linkedin_url"),
        "email": email,
        "email_verified": email is not None,
        "source": "pdl",
        "company": {
            "provider_id": raw.get("job_company_id"),
            "name": raw.get("job_company_name"),
            "domain": raw.get("job_company_website"),
            "industry": raw.get("industry"),
            "employee_count": raw.get("job_company_employee_count"),
            "hq_country": raw.get("job_company_location_country"),
            "funding_stage": raw.get("job_company_inferred_revenue"),
            "linkedin_url": raw.get("job_company_linkedin_url"),
        },
    }


def _build_person_es_query(
    titles: list[str],
    locations: list[str],
    employee_min: int,
    employee_max: int,
) -> dict:
    must: list = []

    if titles:
        must.append({
            "bool": {
                "should": [{"match": {"job_title": t}} for t in titles],
                "minimum_should_match": 1,
            }
        })

    if locations:
        must.append({
            "bool": {
                "should": [{"term": {"location_country": loc.lower()}} for loc in locations],
                "minimum_should_match": 1,
            }
        })

    must.append({
        "range": {
            "job_company_employee_count": {"gte": employee_min, "lte": employee_max}
        }
    })

    must.append({"exists": {"field": "linkedin_url"}})

    return {"query": {"bool": {"must": must}}}


# ---------------------------------------------------------------------------
# Public helpers (used by the sourcing router)
# ---------------------------------------------------------------------------

def estimate_credits_for_run(per_page: int, pages: int) -> int:
    """Return expected credit spend for a sourcing run (per_page * pages)."""
    return per_page * pages


async def search_companies(
    industry: str,
    employee_min: int,
    employee_max: int,
    country: str,
    size: int = 10,
) -> list[dict]:
    """Search for companies matching firmographic criteria.

    Uses POST /v5/company/search. Returns a list of normalized company dicts.
    """
    must = [
        {"match": {"industry": industry}},
        {"range": {"employee_count": {"gte": employee_min, "lte": employee_max}}},
        {"term": {"location_country": country.lower()}},
    ]
    es_query = {"query": {"bool": {"must": must}}}
    if not isinstance(es_query, dict):
        logger.error("es_query must be a dict, not a string — do not call json.dumps() on it")
        raise ValueError("es_query must be a dict, not a string — do not call json.dumps() on it")
    payload = {
        "query": es_query,
        "size": size,
        "pretty": False,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{_BASE_URL}/company/search",
                headers=_HEADERS,
                json=payload,
            )
        if response.status_code != 200:
            logger.error("PDL company search error %d: %s", response.status_code, response.text)
            return []
        data = response.json()
        companies = data.get("data") or []
        return [
            {
                "provider_id": c.get("id"),
                "name": c.get("name"),
                "domain": c.get("website"),
                "industry": c.get("industry"),
                "employee_count": c.get("employee_count"),
                "hq_country": c.get("location_country"),
                "funding_stage": c.get("inferred_revenue"),
                "linkedin_url": c.get("linkedin_url"),
            }
            for c in companies
        ]
    except Exception:
        logger.exception("PDL company search failed")
        return []


# ---------------------------------------------------------------------------
# PDLProvider
# ---------------------------------------------------------------------------

class PDLProvider(LeadProvider):
    """LeadProvider implementation backed by the PeopleDataLabs v5 API."""

    async def search_people(
        self,
        titles: list[str],
        locations: list[str],
        employee_min: int,
        employee_max: int,
        page: int = 1,
        per_page: int = 25,
    ) -> list[dict]:
        # Credit-safety cap: never request more records than the per-run limit.
        cap = settings.PDL_MAX_CREDITS_PER_RUN
        if per_page > cap:
            logger.warning(
                "PDL: per_page=%d exceeds PDL_MAX_CREDITS_PER_RUN=%d — capping to %d",
                per_page,
                cap,
                cap,
            )
            per_page = cap

        es_query = _build_person_es_query(titles, locations, employee_min, employee_max)
        if not isinstance(es_query, dict):
            logger.error("es_query must be a dict, not a string — do not call json.dumps() on it")
            raise ValueError("es_query must be a dict, not a string — do not call json.dumps() on it")
        payload = {
            "query": es_query,
            "size": per_page,
            "from": (page - 1) * per_page,
            "dataset": "resume,contact,social",
            "pretty": False,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{_BASE_URL}/person/search",
                    headers=_HEADERS,
                    json=payload,
                )
            if response.status_code != 200:
                logger.error(
                    "PDL person search error %d: %s", response.status_code, response.text
                )
                return []
            data = response.json()
            return [_parse_pdl_person(r) for r in (data.get("data") or [])]
        except Exception:
            logger.exception("PDL person search failed")
            return []

    async def enrich_person(
        self,
        first_name: str,
        last_name: str,
        company_name: str,
        company_domain: str | None = None,
        linkedin_url: str | None = None,
    ) -> dict | None:
        params: dict = {
            "first_name": first_name,
            "last_name": last_name,
            "company": company_name,
            "pretty": False,
            "required": "work_email",  # only charges a credit when work_email is found
        }
        # Domain is more precise than company name; override if present.
        if company_domain:
            params["company"] = company_domain
        if linkedin_url:
            params["profile"] = linkedin_url

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{_BASE_URL}/person/enrich",
                    headers=_HEADERS,
                    params=params,
                )
            if response.status_code == 404:
                return None
            if response.status_code != 200:
                logger.error(
                    "PDL enrich error %d: %s", response.status_code, response.text
                )
                return None
            data = response.json()
            work_emails: list = data.get("work_email") or []
            if isinstance(work_emails, str):
                work_emails = [work_emails]
            email = work_emails[0] if work_emails else None
            if not email:
                return None
            return {"email": email, "email_verified": True, "source": "pdl"}
        except Exception:
            logger.exception("PDL person enrich failed")
            return None

    async def get_usage_stats(self) -> dict:
        # PDL does not expose a remaining-credits endpoint on the free tier.
        return {
            "provider_name": "pdl",
            "credits_used": None,
            "credits_remaining": None,
            "note": (
                "PDL free tier: ~100 search credits/month. "
                "Monitor usage at app.peopledatalabs.com/dashboard"
            ),
        }
