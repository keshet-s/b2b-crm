"""
PDL (People Data Labs) API client.

Docs: https://docs.peopledatalabs.com/docs/person-search-api
"""

import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger("crm.pdl_client")

PDL_BASE_URL = "https://api.peopledatalabs.com/v5"


def _assert_es_query_is_dict(es_query: Any, caller: str) -> None:
    """Guard against accidentally passing a JSON string instead of a dict.

    json.dumps() must never be called on the query object before it reaches
    this client — httpx serialises the dict correctly when passed as json=.
    """
    if not isinstance(es_query, dict):
        msg = (
            f"{caller}: es_query must be a dict, not a string — "
            "do not call json.dumps() on it before passing here"
        )
        logger.error(msg)
        raise ValueError(msg)


class PDLClient:
    """Thin async wrapper around the PDL Person Search and Company Search APIs."""

    # ------------------------------------------------------------------
    # Person search
    # ------------------------------------------------------------------

    async def search_people(
        self,
        es_query: dict,
        *,
        per_page: int = 25,
        from_offset: int = 0,
        dataset: str = "resume,contact,demographic,social",
    ) -> dict[str, Any]:
        """Search PDL for people matching an Elasticsearch query.

        Args:
            es_query:    A PDL Elasticsearch query *dict*.  Do NOT call
                         json.dumps() on this before passing it — httpx sends
                         it as a proper JSON object in the POST body.
            per_page:    Maximum records to return (PDL cap: 100).
            from_offset: Pagination offset.
            dataset:     Comma-separated PDL dataset names to include.

        Returns:
            The parsed JSON response from PDL.

        Raises:
            ValueError:        If es_query is not a dict.
            httpx.HTTPError:   On network or HTTP-level failures.
        """
        _assert_es_query_is_dict(es_query, "search_people")

        body = {
            "query": es_query,   # dict — httpx serialises this correctly
            "size": per_page,
            "from": from_offset,
            "dataset": dataset,
            "pretty": False,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PDL_BASE_URL}/person/search",
                headers={"X-Api-Key": settings.PDL_API_KEY},
                json=body,          # sends Content-Type: application/json
                timeout=30.0,
            )

        logger.debug(
            "PDL person/search → %d  (total_available=%s)",
            response.status_code,
            response.json().get("total", "?") if response.status_code == 200 else "n/a",
        )
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Company search
    # ------------------------------------------------------------------

    async def search_companies(
        self,
        es_query: dict,
        *,
        per_page: int = 25,
        from_offset: int = 0,
    ) -> dict[str, Any]:
        """Search PDL for companies matching an Elasticsearch query.

        Args:
            es_query:    A PDL Elasticsearch query *dict*.  Do NOT call
                         json.dumps() on this before passing it.
            per_page:    Maximum records to return.
            from_offset: Pagination offset.

        Returns:
            The parsed JSON response from PDL.

        Raises:
            ValueError:        If es_query is not a dict.
            httpx.HTTPError:   On network or HTTP-level failures.
        """
        _assert_es_query_is_dict(es_query, "search_companies")

        body = {
            "query": es_query,   # dict — httpx serialises this correctly
            "size": per_page,
            "from": from_offset,
            "pretty": False,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{PDL_BASE_URL}/company/search",
                headers={"X-Api-Key": settings.PDL_API_KEY},
                json=body,
                timeout=30.0,
            )

        logger.debug(
            "PDL company/search → %d",
            response.status_code,
        )
        response.raise_for_status()
        return response.json()
