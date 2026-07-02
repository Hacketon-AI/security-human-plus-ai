"""Operational liveness probe.

This is an operational endpoint, not a domain API. It must stay cheap and must
not touch the database or external systems, so it can report process liveness
even when dependencies are degraded.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["operational"])


class Health(BaseModel):
    status: str


@router.get("/healthz")
async def healthz() -> Health:
    return Health(status="ok")
