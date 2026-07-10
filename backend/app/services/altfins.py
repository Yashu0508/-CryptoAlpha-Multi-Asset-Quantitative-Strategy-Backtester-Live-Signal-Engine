"""Asynchronous, normalized client for the altFINS analytics API."""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging
from typing import Any

import httpx

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class AltFinsError(Exception):
    """Base exception for altFINS provider failures."""


class AltFinsRequestError(AltFinsError):
    """Raised when an altFINS request cannot be completed."""


class AltFinsResponseError(AltFinsError):
    """Raised when altFINS returns data outside the expected response contract."""


@dataclass(frozen=True, slots=True)
class TechnicalIndicator:
    """Normalized technical indicator or analytic observation."""

    asset: str | None
    timeframe: str | None
    name: str
    value: Decimal | None
    signal: str | None
    observed_at: datetime | None


@dataclass(frozen=True, slots=True)
class TradingSignal:
    """Normalized actionable altFINS signal."""

    asset: str | None
    direction: str
    signal_type: str | None
    timeframe: str | None
    generated_at: datetime | None
    summary: str | None


@dataclass(frozen=True, slots=True)
class MarketSentiment:
    """Normalized aggregate sentiment reading provided by altFINS."""

    classification: str | None
    score: Decimal | None
    observed_at: datetime | None
    source: str = "altfins"


class AltFinsClient:
    """Access altFINS analytics, signals, and technical-analysis datasets.

    Request filters are accepted as mappings because altFINS exposes an extensive and
    evolving filter vocabulary. This client preserves that flexibility while returning
    stable, provider-independent result objects.
    """

    _RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Create an API-key-authenticated altFINS client."""

        settings = get_settings()
        key = api_key if api_key is not None else settings.altfins_api_key
        if not key:
            raise ValueError("ALTFINS_API_KEY must be configured")
        timeout = timeout_seconds if timeout_seconds is not None else settings.altfins_timeout_seconds
        self._max_retries = max_retries if max_retries is not None else settings.altfins_max_retries
        if timeout <= 0 or self._max_retries < 0:
            raise ValueError("timeout_seconds must be positive and max_retries non-negative")
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=(base_url or settings.altfins_base_url).rstrip("/"),
            timeout=httpx.Timeout(timeout),
            headers={"Accept": "application/json", "X-Api-Key": key, "User-Agent": "CryptoAlpha/0.1"},
        )

    async def __aenter__(self) -> "AltFinsClient":
        """Return this client for use in an async context manager."""

        return self

    async def __aexit__(self, *_: object) -> None:
        """Close internally owned HTTP resources."""

        await self.aclose()

    async def aclose(self) -> None:
        """Close the internally created HTTP client."""

        if self._owns_client:
            await self._client.aclose()

    async def get_technical_indicators(
        self, filters: Mapping[str, Any] | None = None
    ) -> list[TechnicalIndicator]:
        """Return normalized analytic and technical-indicator records.

        ``filters`` maps directly to altFINS's documented analytics search request.
        """

        records = self._records(await self._request_json("POST", "/api/v2/public/analytics/search-requests", filters or {}))
        return [self._indicator(self._mapping(record, "technical indicator")) for record in records]

    async def get_buy_signals(self, filters: Mapping[str, Any] | None = None) -> list[TradingSignal]:
        """Return normalized bullish signals from the altFINS signals feed."""

        return await self._signals("BULLISH", filters)

    async def get_sell_signals(self, filters: Mapping[str, Any] | None = None) -> list[TradingSignal]:
        """Return normalized bearish signals from the altFINS signals feed."""

        return await self._signals("BEARISH", filters)

    async def get_market_sentiment(self) -> MarketSentiment:
        """Return the aggregate sentiment exposed by altFINS technical analysis."""

        payload = self._mapping(await self._request_json("GET", "/api/v2/public/technical-analysis/data"), "technical analysis")
        data = payload.get("data", payload)
        if isinstance(data, Mapping):
            candidate: Any = data.get("marketSentiment", data.get("sentiment", data))
        elif isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            candidate = next((item for item in data if isinstance(item, Mapping)), {})
        else:
            raise AltFinsResponseError("altFINS technical-analysis data has an invalid shape")
        sentiment = candidate if isinstance(candidate, Mapping) else {"classification": candidate}
        return MarketSentiment(
            classification=self._string(sentiment, "classification", "label", "sentiment", "signal"),
            score=self._optional_decimal(self._first(sentiment, "score", "value", "sentimentScore")),
            observed_at=self._optional_timestamp(self._first(sentiment, "timestamp", "updatedAt", "date")),
        )

    async def _signals(self, direction: str, filters: Mapping[str, Any] | None) -> list[TradingSignal]:
        """Request one directional signal-feed view and normalize its records."""

        request_body = dict(filters or {})
        request_body.setdefault("direction", direction)
        records = self._records(await self._request_json("POST", "/api/v2/public/signals-feed/search-requests", request_body))
        return [self._signal(self._mapping(record, "signal"), direction) for record in records]

    async def _request_json(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        """Make a retryable authenticated altFINS request and parse JSON."""

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.request(method, path, json=body)
                if response.status_code in self._RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                    await self._backoff(attempt, response)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt >= self._max_retries:
                    logger.warning("altFINS request exhausted retries: %s", error)
                    raise AltFinsRequestError("altFINS network request failed") from error
                await self._backoff(attempt)
            except httpx.HTTPStatusError as error:
                logger.warning("altFINS returned HTTP %d for %s", error.response.status_code, path)
                raise AltFinsRequestError(f"altFINS returned HTTP {error.response.status_code}") from error
            except ValueError as error:
                raise AltFinsResponseError("altFINS returned invalid JSON") from error
        raise AltFinsRequestError("altFINS retry loop ended unexpectedly")

    async def _backoff(self, attempt: int, response: httpx.Response | None = None) -> None:
        """Delay a retry using ``Retry-After`` when the server supplies one."""

        retry_after = response.headers.get("Retry-After") if response else None
        try:
            delay = max(0.0, float(retry_after)) if retry_after else min(2**attempt, 8.0)
        except ValueError:
            delay = min(2**attempt, 8.0)
        logger.info("Retrying altFINS request in %.2fs", delay)
        await asyncio.sleep(delay)

    @classmethod
    def _records(cls, payload: Any) -> Sequence[Any]:
        """Extract a records array from common altFINS response envelopes."""

        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
            return payload
        response = cls._mapping(payload, "response")
        data = response.get("data", response)
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            return data
        envelope = cls._mapping(data, "data")
        for key in ("items", "results", "content", "records"):
            value = envelope.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
                return value
        raise AltFinsResponseError("altFINS response does not contain a records array")

    @classmethod
    def _indicator(cls, item: Mapping[str, Any]) -> TechnicalIndicator:
        """Normalize a technical-analysis row despite provider field aliases."""

        return TechnicalIndicator(
            asset=cls._string(item, "symbol", "asset", "instrument", "ticker"),
            timeframe=cls._string(item, "timeframe", "interval", "period"),
            name=cls._string(item, "indicator", "name", "type", "analyticsType") or "unknown",
            value=cls._optional_decimal(cls._first(item, "value", "indicatorValue", "score")),
            signal=cls._string(item, "signal", "recommendation", "direction"),
            observed_at=cls._optional_timestamp(cls._first(item, "timestamp", "date", "updatedAt")),
        )

    @classmethod
    def _signal(cls, item: Mapping[str, Any], fallback_direction: str) -> TradingSignal:
        """Normalize a signal-feed row into the application's stable signal shape."""

        return TradingSignal(
            asset=cls._string(item, "symbol", "asset", "instrument", "ticker"),
            direction=cls._string(item, "direction", "signalDirection", "side") or fallback_direction,
            signal_type=cls._string(item, "signalType", "type", "signal"),
            timeframe=cls._string(item, "timeframe", "interval", "period"),
            generated_at=cls._optional_timestamp(cls._first(item, "timestamp", "createdAt", "date")),
            summary=cls._string(item, "summary", "description", "title", "message"),
        )

    @staticmethod
    def _mapping(value: Any, label: str) -> Mapping[str, Any]:
        """Validate a JSON object response value."""

        if not isinstance(value, Mapping):
            raise AltFinsResponseError(f"Expected altFINS {label} to be an object")
        return value

    @staticmethod
    def _first(item: Mapping[str, Any], *keys: str) -> Any:
        """Return the first present non-null field among provider aliases."""

        return next((item[key] for key in keys if item.get(key) is not None), None)

    @classmethod
    def _string(cls, item: Mapping[str, Any], *keys: str) -> str | None:
        """Return an optional string from the first matching provider field."""

        value = cls._first(item, *keys)
        return str(value) if value is not None else None

    @staticmethod
    def _optional_decimal(value: Any) -> Decimal | None:
        """Convert an optional numeric provider field into ``Decimal``."""

        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise AltFinsResponseError("Expected altFINS value to be numeric") from error

    @staticmethod
    def _optional_timestamp(value: Any) -> datetime | None:
        """Convert an optional ISO-8601 provider timestamp."""

        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as error:
            raise AltFinsResponseError("altFINS timestamp is invalid") from error
