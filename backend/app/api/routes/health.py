"""Operational health endpoints."""

from fastapi import APIRouter

from app.config.settings import get_settings
from app.schemas.health import HealthResponse

router = APIRouter(prefix="/health")


@router.get("", response_model=HealthResponse, summary="Check service health")
async def health_check() -> HealthResponse:
    """Return basic process health without depending on business services."""

    settings = get_settings()
    return HealthResponse(status="ok", environment=settings.app_env)
