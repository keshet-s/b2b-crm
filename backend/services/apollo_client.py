"""Apollo.io REST API client (async, httpx-based).

All network calls use httpx.AsyncClient. The API key is read from
settings.APOLLO_API_KEY at import time so it can be overridden in tests.
"""

import asyncio
import logging
from typing import Callable

import httpx

from config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.apollo.io/api/v1"
_DEFAULT_HEADERS = {
    "X-Api-Key": settings.APOLLO_API_KEY,
    "Content-Type": "application/json",
    "Cache-Control": "no-cache",
}


class ApolloAPIError(Exception):
    """Raised when the Apollo API returns a non-200 response."""

    def __init__(self, message: str, status_code: int, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after


async def with_retry(coro: Callable, max_attempts: int = 3):
    """Call ``coro()`` up to *max_attempts* times, retrying on ApolloAPIError.

    Waits 2^attempt seconds between attempts (1 s, 2 s, 4 s, …).
    ``coro`` must be a zero-argument callable that returns an awaitable.
    """
    for attempt in range(max_attempts):
        try:
            return await coro()
        except ApolloAPIError:
            if attempt == max_attempts - 1:
                raise
            wait = 2 ** attempt
            logger.warning("Apollo API error on attempt %d/%d — retrying in %ds", attempt + 1, max_attempts, wait)
            await asyncio.sleep(wait)


def _raise_for_status(response: httpx.Response) -> None:
    """Inspect *response* and raise ApolloAPIError for non-200 status codes."""
    if response.status_code == 200:
        return
    if response.status_code == 429:
        retry_after_raw = response.headers.get("Retry-After", "60")
        try:
            retry_after = int(retry_after_raw)
        except ValueError:
            retry_after = 60
        logger.warning("Apollo rate limit hit — Retry-After: %s", retry_after_raw)
        raise ApolloAPIError("Apollo rate limit exceeded", status_code=429, retry_after=retry_after)
    try:
        body = response.text
    except Exception:
        body = "<unreadable>"
    logger.error("Apollo API error %d: %s", response.status_code, body)
    raise ApolloAPIError(
        f"Apollo API returned {response.status_code}",
        status_code=response.status_code,
    )


async def search_people(query_params: dict, page: int = 1, per_page: int = 100) -> dict:
    """POST to /mixed_people/api_search and return the full response dict.

    Hits the Apollo people-search endpoint. Does **not** consume email-reveal
    credits — it returns whatever contact data Apollo already has indexed.

    Args:
        query_params: Filters such as person_titles, person_locations, etc.
        page: 1-based page number.
        per_page: Results per page (max 100 for most Apollo plans).

    Returns:
        Full parsed JSON response from Apollo.

    Raises:
        ApolloAPIError: On any non-200 response.
    """
    payload = {**query_params, "page": page, "per_page": per_page}
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_BASE_URL}/mixed_people/api_search",
            headers=_DEFAULT_HEADERS,
            json=payload,
        )
    _raise_for_status(response)
    return response.json()


async def enrich_person(
    first_name: str,
    last_name: str,
    organization_name: str,
    domain: str | None = None,
    reveal_email: bool = True,
) -> dict | None:
    """POST to /people/match and return the matched ``person`` dict.

    Attempts to match a person by name and company and return enriched data.

    Note: This endpoint **consumes credits** when ``reveal_email=True`` and
    Apollo successfully reveals an email address. Set ``reveal_email=False``
    to perform a credit-free identity lookup.

    Args:
        first_name: Person's first name.
        last_name: Person's last name.
        organization_name: Name of the person's employer.
        domain: Company domain (improves match accuracy when provided).
        reveal_email: Whether to ask Apollo to reveal the work email.

    Returns:
        The ``person`` object from the response, or None if not found.

    Raises:
        ApolloAPIError: On unexpected API errors.
    """
    payload: dict = {
        "first_name": first_name,
        "last_name": last_name,
        "organization_name": organization_name,
        "reveal_personal_emails": reveal_email,
        "reveal_phone_number": False,
    }
    if domain is not None:
        payload["domain"] = domain

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_BASE_URL}/people/match",
            headers=_DEFAULT_HEADERS,
            json=payload,
        )

    if response.status_code == 404:
        return None
    _raise_for_status(response)

    data = response.json()
    person = data.get("person")
    if not person:
        return None
    return person


async def enrich_company(domain: str) -> dict | None:
    """POST to /organizations/enrich and return the ``organization`` dict.

    Looks up a company by its domain and returns enriched firmographic data.
    Does **not** consume email-reveal credits.

    Args:
        domain: The company's primary web domain (e.g. ``"acme.com"``).

    Returns:
        The ``organization`` object from the response, or None if not found.

    Raises:
        ApolloAPIError: On unexpected API errors.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_BASE_URL}/organizations/enrich",
            headers=_DEFAULT_HEADERS,
            json={"domain": domain},
        )

    if response.status_code == 404:
        return None
    _raise_for_status(response)

    data = response.json()
    return data.get("organization") or None


async def get_api_usage() -> dict:
    """POST to /usage_stats/api_usage_stats and return the usage stats dict.

    Returns credit consumption and rate-limit counters. Useful for monitoring
    dashboards and alerting. Does **not** consume credits.

    Returns:
        Usage stats dict as returned by Apollo.

    Raises:
        ApolloAPIError: On any non-200 response.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_BASE_URL}/usage_stats/api_usage_stats",
            headers=_DEFAULT_HEADERS,
            json={},
        )
    _raise_for_status(response)
    return response.json()


def build_icp_search_params(
    titles: list[str],
    locations: list[str],
    employee_min: int,
    employee_max: int,
    page: int = 1,
) -> dict:
    """Build the search payload for Apollo people search from ICP filter values.

    Constructs the ``query_params`` dict expected by :func:`search_people`.

    Args:
        titles: Job titles to target (e.g. ``["VP of Engineering", "CTO"]``).
        locations: Geographic locations (e.g. ``["United States", "Canada"]``).
        employee_min: Minimum number of employees at target companies.
        employee_max: Maximum number of employees at target companies.
        page: 1-based page number to embed in the payload.

    Returns:
        Complete payload dict ready to pass to :func:`search_people`.
    """
    return {
        "person_titles": titles,
        "person_locations": locations,
        "organization_num_employees_ranges": [f"{employee_min},{employee_max}"],
        "page": page,
    }


def parse_apollo_person(raw_person: dict, raw_org: dict | None = None) -> dict:
    """Transform a raw Apollo person object into our internal schema.

    Merges person-level data with organization data. ``raw_org`` takes
    precedence over the embedded ``organization`` object in the person record
    when provided (useful after a separate :func:`enrich_company` call).

    Args:
        raw_person: Person dict as returned by Apollo search or match endpoints.
        raw_org: Optional standalone organization dict from an enrich call.

    Returns:
        Normalised dict with ``apollo_id``, ``first_name``, ``last_name``,
        ``full_name``, ``title``, ``seniority``, ``department``,
        ``linkedin_url``, ``email``, ``email_verified``, ``phone``, and a
        nested ``company`` dict.
    """
    org = raw_org or raw_person.get("organization") or {}

    email = raw_person.get("email") or raw_person.get("work_email")
    email_verified = raw_person.get("email_status") == "verified"

    phone = raw_person.get("phone") or raw_person.get("sanitized_phone")

    company = {
        "apollo_id": org.get("id"),
        "name": org.get("name"),
        "domain": org.get("primary_domain") or org.get("domain"),
        "industry": org.get("industry"),
        "employee_count": org.get("estimated_num_employees"),
        "hq_country": org.get("country"),
        "linkedin_url": org.get("linkedin_url"),
    }

    return {
        "apollo_id": raw_person.get("id"),
        "first_name": raw_person.get("first_name"),
        "last_name": raw_person.get("last_name"),
        "full_name": raw_person.get("name"),
        "title": raw_person.get("title"),
        "seniority": raw_person.get("seniority"),
        "department": raw_person.get("department"),
        "linkedin_url": raw_person.get("linkedin_url"),
        "email": email,
        "email_verified": email_verified,
        "phone": phone,
        "company": company,
    }


# ---------------------------------------------------------------------------
# LeadProvider implementation
# ---------------------------------------------------------------------------

class ApolloProvider:
    """Wraps the module-level Apollo functions to satisfy the LeadProvider interface."""

    async def search_people(
        self,
        titles: list[str],
        locations: list[str],
        employee_min: int,
        employee_max: int,
        page: int = 1,
        per_page: int = 25,
    ) -> list[dict]:
        query_params = build_icp_search_params(
            titles=titles,
            locations=locations,
            employee_min=employee_min,
            employee_max=employee_max,
            page=page,
        )
        response = await search_people(query_params, page=page, per_page=per_page)
        raw_people = response.get("people") or []
        results = []
        for raw_person in raw_people:
            parsed = parse_apollo_person(raw_person)
            company = parsed.pop("company", {})
            lead = {
                "provider_id": parsed.pop("apollo_id", None),
                **parsed,
                "source": "apollo",
                "company": {
                    "provider_id": company.get("apollo_id"),
                    "name": company.get("name"),
                    "domain": company.get("domain"),
                    "industry": company.get("industry"),
                    "employee_count": company.get("employee_count"),
                    "hq_country": company.get("hq_country"),
                    "funding_stage": None,
                    "linkedin_url": company.get("linkedin_url"),
                },
            }
            results.append(lead)
        return results

    async def enrich_person(
        self,
        first_name: str,
        last_name: str,
        company_name: str,
        company_domain: str | None = None,
        linkedin_url: str | None = None,
    ) -> dict | None:
        person = await enrich_person(
            first_name=first_name,
            last_name=last_name,
            organization_name=company_name,
            domain=company_domain,
            reveal_email=True,
        )
        if person is None:
            return None
        email = person.get("email") or person.get("work_email")
        email_verified = person.get("email_status") == "verified"
        return {"email": email, "email_verified": email_verified, **person}

    async def get_usage_stats(self) -> dict:
        raw = await get_api_usage()
        usage = raw.get("usage") or {}
        return {
            "provider_name": "apollo",
            "credits_used": usage.get("credits_used"),
            "credits_remaining": usage.get("credits_remaining"),
        }
