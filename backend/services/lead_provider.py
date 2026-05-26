"""Provider-agnostic interface for lead sourcing and enrichment.

Import ``get_lead_provider`` here — never import a concrete provider directly.

Normalized lead dict schema returned by every provider's search_people():
{
    "provider_id":    str,           # provider's internal unique ID
    "first_name":     str | None,
    "last_name":      str | None,
    "full_name":      str | None,
    "title":          str | None,
    "seniority":      str | None,    # "c_suite","vp","director","manager","senior","entry" etc.
    "department":     str | None,
    "linkedin_url":   str | None,
    "email":          str | None,    # only populated if provider returned it for free
    "email_verified": bool,          # False unless explicitly confirmed
    "source":         str,           # e.g. "pdl", "apollo"
    "company": {
        "provider_id":   str | None,
        "name":          str | None,
        "domain":        str | None,
        "industry":      str | None,
        "employee_count": int | None,
        "hq_country":    str | None,
        "funding_stage": str | None,
        "linkedin_url":  str | None,
    }
}
"""

from abc import ABC, abstractmethod

from config import settings


class LeadProvider(ABC):

    @abstractmethod
    async def search_people(
        self,
        titles: list[str],
        locations: list[str],
        employee_min: int,
        employee_max: int,
        page: int = 1,
        per_page: int = 25,
    ) -> list[dict]:
        """Search for people matching ICP criteria.

        Returns a list of normalized lead dicts (see module-level schema).
        Must NOT consume email-reveal credits — discovery only.
        """

    @abstractmethod
    async def enrich_person(
        self,
        first_name: str,
        last_name: str,
        company_name: str,
        company_domain: str | None = None,
        linkedin_url: str | None = None,
    ) -> dict | None:
        """Attempt to find a verified work email for a known person.

        Returns a dict with at minimum {"email": str, "email_verified": bool},
        or None if not found.
        Credits are consumed here — only call for Tier A/B leads.
        """

    @abstractmethod
    async def get_usage_stats(self) -> dict:
        """Return current API usage/credit stats for the Settings page.

        Keys: provider_name, credits_used, credits_remaining (or None if unknown).
        """


def get_lead_provider() -> LeadProvider:
    """Return the active lead provider based on settings.ACTIVE_LEAD_PROVIDER.

    Import this function wherever a provider is needed.
    """
    provider = settings.ACTIVE_LEAD_PROVIDER.lower()
    if provider == "apollo":
        from services.apollo_client import ApolloProvider
        return ApolloProvider()
    elif provider == "pdl":
        from services.pdl_client import PDLProvider
        return PDLProvider()
    else:
        raise ValueError(
            f"Unknown ACTIVE_LEAD_PROVIDER: '{provider}'. "
            f"Valid options: 'pdl', 'apollo'"
        )
