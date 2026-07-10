"""Schemas for operational endpoints."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response returned by health checks."""

    status: str
    environment: str
