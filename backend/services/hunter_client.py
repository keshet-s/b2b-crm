"""Hunter.io API v2 client (async, httpx-based).

Email-finding utility used after PDL discovery. Not a LeadProvider —
call these functions from the sourcing router for Tier A/B leads.
API key is read from settings.HUNTER_API_KEY.
"""

import logging
from datetime import date

import httpx

from config import settings

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.hunter.io/v2"

# Simple in-memory daily counter to protect the free-tier monthly budget.
_daily_search_count: dict[str, int] = {}


def _check_daily_limit() -> bool:
    """Return True if we are under HUNTER_MAX_SEARCHES_PER_DAY."""
    today = date.today().isoformat()
    return _daily_search_count.get(today, 0) < settings.HUNTER_MAX_SEARCHES_PER_DAY


def _increment_daily_count() -> None:
    today = date.today().isoformat()
    _daily_search_count[today] = _daily_search_count.get(today, 0) + 1


# ---------------------------------------------------------------------------
# Public API functions
# ---------------------------------------------------------------------------

async def find_email(first_name: str, last_name: str, domain: str) -> dict | None:
    """Find a verified work email for a person at a given domain.

    Hunter free tier: 25 searches/month.
    Only call for Tier A/B leads without a PDL email.

    Returns {"email": str, "score": int, "email_verified": bool} on success,
    or None if not found. Hunter does not charge credits for misses.
    """
    if not _check_daily_limit():
        logger.warning(
            "Hunter daily search limit (%d) reached — skipping find_email for %s %s",
            settings.HUNTER_MAX_SEARCHES_PER_DAY,
            first_name,
            last_name,
        )
        return None

    params = {
        "first_name": first_name,
        "last_name": last_name,
        "domain": domain,
        "api_key": settings.HUNTER_API_KEY,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{_BASE_URL}/email-finder", params=params)

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            logger.error("Hunter find_email error %d: %s", response.status_code, response.text)
            return None

        _increment_daily_count()
        data = response.json().get("data") or {}
        email = data.get("email")
        if not email:
            return None
        return {
            "email": email,
            "score": data.get("score", 0),
            "email_verified": data.get("score", 0) >= 80,
        }
    except Exception:
        logger.exception("Hunter find_email failed for %s %s @ %s", first_name, last_name, domain)
        return None


async def domain_search(domain: str, limit: int = 10) -> list[dict]:
    """Return all known email addresses at a domain in a single credit.

    Use before find_email for a company — if the target person appears in
    domain_search results, no additional credit needed.

    Returns a list of {"email", "first_name", "last_name", "position", "confidence"}.
    Returns empty list on error or not found.
    """
    if not _check_daily_limit():
        logger.warning(
            "Hunter daily search limit (%d) reached — skipping domain_search for %s",
            settings.HUNTER_MAX_SEARCHES_PER_DAY,
            domain,
        )
        return []

    params = {
        "domain": domain,
        "limit": limit,
        "api_key": settings.HUNTER_API_KEY,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{_BASE_URL}/domain-search", params=params)

        if response.status_code == 404:
            return []
        if response.status_code != 200:
            logger.error("Hunter domain_search error %d: %s", response.status_code, response.text)
            return []

        _increment_daily_count()
        data = response.json().get("data") or {}
        emails = data.get("emails") or []
        return [
            {
                "email": e.get("value"),
                "first_name": e.get("first_name"),
                "last_name": e.get("last_name"),
                "position": e.get("position"),
                "confidence": e.get("confidence"),
            }
            for e in emails
            if e.get("value")
        ]
    except Exception:
        logger.exception("Hunter domain_search failed for %s", domain)
        return []


async def verify_email(email: str) -> dict:
    """Verify deliverability of a known email address.

    Consumes 1 verification credit (separate pool from search credits).
    Returns {"email", "result": "deliverable|risky|undeliverable", "score": int}.
    """
    params = {"email": email, "api_key": settings.HUNTER_API_KEY}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{_BASE_URL}/email-verifier", params=params)

        if response.status_code != 200:
            logger.error("Hunter verify_email error %d: %s", response.status_code, response.text)
            return {"email": email, "result": "unknown", "score": 0}

        data = response.json().get("data") or {}
        return {
            "email": email,
            "result": data.get("result", "unknown"),
            "score": data.get("score", 0),
        }
    except Exception:
        logger.exception("Hunter verify_email failed for %s", email)
        return {"email": email, "result": "unknown", "score": 0}


async def get_usage() -> dict:
    """Return Hunter account usage stats including requests used and available."""
    params = {"api_key": settings.HUNTER_API_KEY}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{_BASE_URL}/account", params=params)

        if response.status_code != 200:
            logger.error("Hunter get_usage error %d: %s", response.status_code, response.text)
            return {}

        return response.json().get("data") or {}
    except Exception:
        logger.exception("Hunter get_usage failed")
        return {}
