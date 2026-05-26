"""Synchronous HTTP client wrapping the FastAPI backend."""

import os
from typing import Optional

import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

_TIMEOUT = httpx.Timeout(30.0)


def _get(path: str, **params) -> dict | list:
    try:
        r = httpx.get(f"{BACKEND_URL}{path}", params=params or None, timeout=_TIMEOUT)
    except httpx.ConnectError:
        return {"error": "Backend not reachable"}
    except httpx.RequestError:
        return {"error": "Backend not reachable"}
    if r.is_error:
        try:
            detail = r.json().get("detail", str(r.status_code))
        except Exception:
            detail = str(r.status_code)
        return {"error": detail}
    return r.json()


def _post(path: str, json: dict | None = None, **params) -> dict | list:
    try:
        r = httpx.post(
            f"{BACKEND_URL}{path}",
            json=json,
            params=params or None,
            timeout=_TIMEOUT,
        )
    except httpx.ConnectError:
        return {"error": "Backend not reachable"}
    except httpx.RequestError:
        return {"error": "Backend not reachable"}
    if r.is_error:
        try:
            detail = r.json().get("detail", str(r.status_code))
        except Exception:
            detail = str(r.status_code)
        return {"error": detail}
    return r.json()


def _patch(path: str, json: dict) -> dict:
    try:
        r = httpx.patch(f"{BACKEND_URL}{path}", json=json, timeout=_TIMEOUT)
    except httpx.ConnectError:
        return {"error": "Backend not reachable"}
    except httpx.RequestError:
        return {"error": "Backend not reachable"}
    if r.is_error:
        try:
            detail = r.json().get("detail", str(r.status_code))
        except Exception:
            detail = str(r.status_code)
        return {"error": detail}
    return r.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_stats() -> dict:
    return _get("/api/stats")


def get_leads(
    status: Optional[str] = None,
    tier: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    params = {"limit": limit, "offset": offset}
    if status:
        params["status"] = status
    if tier:
        params["tier"] = tier
    if search:
        params["search"] = search
    return _get("/api/leads/", **params)


def get_lead(lead_id: int) -> dict:
    return _get(f"/api/leads/{lead_id}")


def update_lead(lead_id: int, updates: dict) -> dict:
    return _patch(f"/api/leads/{lead_id}", json=updates)


def get_pipeline_summary() -> dict:
    return _get("/api/leads/pipeline/summary")


def get_activities(lead_id: int) -> list:
    result = _get(f"/api/activities/lead/{lead_id}")
    if isinstance(result, dict) and "error" in result:
        return result
    return result


def post_activity(
    lead_id: int,
    type: str,
    content: str,
    channel: Optional[str] = None,
) -> dict:
    body = {"lead_id": lead_id, "type": type, "content_snippet": content}
    if channel:
        body["channel"] = channel
    return _post("/api/activities/", json=body)


def run_sourcing(
    pages: int = 1,
    titles: Optional[list] = None,
    locations: Optional[list] = None,
) -> dict:
    body: dict = {"pages": pages}
    if titles:
        body["titles"] = titles
    if locations:
        body["locations"] = locations
    return _post("/api/sourcing/run", json=body)


def score_unscored(limit: int = 50) -> dict:
    return _post("/api/scoring/score-unscored", limit=limit)


def score_lead(lead_id: int) -> dict:
    return _post(f"/api/scoring/score/{lead_id}")


def enrich_lead(lead_id: int) -> dict:
    return _post(f"/api/sourcing/enrich/{lead_id}")


def generate_hook(lead_id: int) -> dict:
    return _post(f"/api/scoring/generate-hook/{lead_id}")


def get_scoring_stats() -> dict:
    return _get("/api/scoring/stats")


def get_sourcing_runs(limit: int = 10) -> list:
    result = _get("/api/sourcing/runs", limit=limit)
    if isinstance(result, dict) and "error" in result:
        return result
    return result
