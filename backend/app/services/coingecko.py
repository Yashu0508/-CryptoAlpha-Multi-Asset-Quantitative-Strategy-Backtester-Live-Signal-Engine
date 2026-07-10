"""Asynchronous, normalized client for the CoinGecko REST API.

This module deliberately exposes persistence-agnostic value objects. Callers can map
them into database models without carrying provider-specific JSON through the system.
"""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import logging
from typing import Any

import httpx

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class CoinGeckoError(Exception):
    """Base exception for failures while communicating with CoinGecko."""


class CoinGeckoRequestError(CoinGeckoError):
    """Raised when a request cannot be completed after retries."""


class CoinGeckoResponseError(CoinGeckoError):
    """Raised when CoinGecko returns an invalid or unexpected response body."""


@dataclass(frozen=True, slots=True)
class CurrentPrice:
    """Normalized current prices and optional market caps for a CoinGecko asset."""

    coin_id: str
    prices: Mapping[str, Decimal]
    market_caps: Mapping[str, Decimal]


@dataclass(frozen=True, slots=True)
class OHLCVCandle:
    """Normalized candle from CoinGecko's OHLC endpoint.

    CoinGecko's OHLC endpoint does not provide volume, so ``volume`` is always
    ``None``. This preserves the application's OHLCV contract without inventing data.
    """

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None


@dataclass(frozen=True, slots=True)
class MarketCap:
    """Normalized market-cap value for one asset and quote currency."""

    coin_id: str
    currency: str
    value: Decimal


@dataclass(frozen=True, slots=True)
class Coin:
    """Normalized CoinGecko coin-list entry."""

    coin_id: str
    symbol: str
    name: str


@dataclass(frozen=True, slots=True)
class CoinSearchResult:
    """Normalized CoinGecko search result."""

    coin_id: str
    symbol: str
    name: str
    market_cap_rank: int | None
    thumb_url: str | None


class CoinGeckoClient:
    """HTTP client for CoinGecko with bounded retries and normalized responses.

    The client can own its underlying :class:`httpx.AsyncClient` or accept one from a
    caller, which makes it straightforward to test with a mock transport. Call
    :meth:`aclose` when this instance owns a client, or use it as an async context
    manager.
    """

    _RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Create a CoinGecko client with optional explicit runtime configuration."""

        settings = get_settings()
        self._max_retries = max_retries if max_retries is not None else settings.coingecko_max_retries
        if self._max_retries < 0:
            raise ValueError("max_retries must be greater than or equal to zero")

        timeout = timeout_seconds if timeout_seconds is not None else settings.coingecko_timeout_seconds
        if timeout <= 0:
            raise ValueError("timeout_seconds must be greater than zero")

        resolved_base_url = (base_url or settings.coingecko_base_url).rstrip("/")
        headers = {"Accept": "application/json", "User-Agent": "CryptoAlpha/0.1"}
        resolved_api_key = api_key if api_key is not None else settings.coingecko_api_key
        if resolved_api_key:
            headers["x-cg-demo-api-key"] = resolved_api_key

        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=resolved_base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
        )

    async def __aenter__(self) -> "CoinGeckoClient":
        """Return this client for use in an async context manager."""

        return self

    async def __aexit__(self, *_: object) -> None:
        """Close an internally managed HTTP client."""

        await self.aclose()

    async def aclose(self) -> None:
        """Release the owned HTTP connection pool."""

        if self._owns_client:
            await self._client.aclose()

    async def get_current_price(
        self,
        coin_ids: Sequence[str],
        *,
        vs_currencies: Sequence[str] = ("usd",),
        include_market_cap: bool = False,
    ) -> list[CurrentPrice]:
        """Return normalized current prices for the requested CoinGecko IDs."""

        self._require_values("coin_ids", coin_ids)
        self._require_values("vs_currencies", vs_currencies)
        payload = await self._request_json(
            "/simple/price",
            params={
                "ids": ",".join(coin_ids),
                "vs_currencies": ",".join(vs_currencies),
                "include_market_cap": str(include_market_cap).lower(),
            },
        )
        response = self._as_mapping(payload, "current price")
        currencies = [currency.lower() for currency in vs_currencies]
        results: list[CurrentPrice] = []
        for coin_id, raw_quote in response.items():
            quote = self._as_mapping(raw_quote, f"current price for {coin_id}")
            prices = {
                currency: self._as_decimal(quote[currency], f"{coin_id}.{currency}")
                for currency in currencies
                if currency in quote and quote[currency] is not None
            }
            market_caps = {
                currency: self._as_decimal(quote[f"{currency}_market_cap"], f"{coin_id}.{currency}_market_cap")
                for currency in currencies
                if f"{currency}_market_cap" in quote and quote[f"{currency}_market_cap"] is not None
            }
            results.append(CurrentPrice(coin_id=str(coin_id), prices=prices, market_caps=market_caps))
        return results

    async def get_historical_ohlcv(
        self, coin_id: str, *, vs_currency: str = "usd", days: int | str = 1
    ) -> list[OHLCVCandle]:
        """Return normalized historical OHLC candles for a CoinGecko asset."""

        if not coin_id:
            raise ValueError("coin_id must not be empty")
        payload = await self._request_json(
            f"/coins/{coin_id}/ohlc", params={"vs_currency": vs_currency.lower(), "days": str(days)}
        )
        rows = self._as_sequence(payload, "OHLC")
        candles: list[OHLCVCandle] = []
        for row in rows:
            values = self._as_sequence(row, "OHLC row")
            if len(values) != 5:
                raise CoinGeckoResponseError("CoinGecko OHLC row must contain five values")
            milliseconds = self._as_decimal(values[0], "OHLC timestamp")
            candles.append(
                OHLCVCandle(
                    timestamp=datetime.fromtimestamp(float(milliseconds / Decimal(1000)), tz=timezone.utc),
                    open=self._as_decimal(values[1], "OHLC open"),
                    high=self._as_decimal(values[2], "OHLC high"),
                    low=self._as_decimal(values[3], "OHLC low"),
                    close=self._as_decimal(values[4], "OHLC close"),
                )
            )
        return candles

    async def get_market_cap(self, coin_id: str, *, vs_currency: str = "usd") -> MarketCap | None:
        """Return a normalized market cap, or ``None`` when CoinGecko has no quote."""

        prices = await self.get_current_price(
            [coin_id], vs_currencies=[vs_currency], include_market_cap=True
        )
        if not prices:
            return None
        currency = vs_currency.lower()
        value = prices[0].market_caps.get(currency)
        return (
            MarketCap(coin_id=prices[0].coin_id, currency=currency, value=value)
            if value is not None
            else None
        )

    async def get_coin_list(self, *, include_platform: bool = False) -> list[Coin]:
        """Return all CoinGecko coins in a provider-independent normalized shape."""

        payload = await self._request_json(
            "/coins/list", params={"include_platform": str(include_platform).lower()}
        )
        return [
            Coin(
                coin_id=str(item["id"]),
                symbol=str(item["symbol"]),
                name=str(item["name"]),
            )
            for item in (self._as_mapping(row, "coin-list row") for row in self._as_sequence(payload, "coin list"))
            if item.get("id") and item.get("symbol") and item.get("name")
        ]

    async def search_coin(self, query: str) -> list[CoinSearchResult]:
        """Search CoinGecko and return normalized matching coin results."""

        if not query.strip():
            raise ValueError("query must not be blank")
        payload = self._as_mapping(await self._request_json("/search", params={"query": query}), "search")
        coins = self._as_sequence(payload.get("coins", []), "search coins")
        return [self._normalize_search_result(self._as_mapping(item, "search coin")) for item in coins]

    async def _request_json(self, path: str, *, params: Mapping[str, str]) -> Any:
        """Request a JSON resource with retry handling for transient provider failures."""

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(path, params=params)
                if response.status_code in self._RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                    await self._wait_before_retry(attempt, response)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt >= self._max_retries:
                    logger.warning("CoinGecko request failed after %d retries: %s", attempt, error)
                    raise CoinGeckoRequestError("CoinGecko network request failed") from error
                await self._wait_before_retry(attempt)
            except httpx.HTTPStatusError as error:
                logger.warning("CoinGecko returned HTTP %d for %s", error.response.status_code, path)
                raise CoinGeckoRequestError(f"CoinGecko returned HTTP {error.response.status_code}") from error
            except ValueError as error:
                raise CoinGeckoResponseError("CoinGecko returned invalid JSON") from error

        raise CoinGeckoRequestError("CoinGecko request retry loop ended unexpectedly")

    async def _wait_before_retry(self, attempt: int, response: httpx.Response | None = None) -> None:
        """Wait using Retry-After when supplied, otherwise bounded exponential backoff."""

        retry_after = response.headers.get("Retry-After") if response else None
        try:
            delay = max(0.0, float(retry_after)) if retry_after else min(2**attempt, 8.0)
        except ValueError:
            delay = min(2**attempt, 8.0)
        logger.info("Retrying CoinGecko request in %.2f seconds (attempt %d)", delay, attempt + 1)
        await asyncio.sleep(delay)

    @staticmethod
    def _as_mapping(value: Any, label: str) -> Mapping[str, Any]:
        """Validate that a provider value is a JSON object."""

        if not isinstance(value, Mapping):
            raise CoinGeckoResponseError(f"Expected {label} response to be an object")
        return value

    @staticmethod
    def _as_sequence(value: Any, label: str) -> Sequence[Any]:
        """Validate that a provider value is a JSON array, excluding strings."""

        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise CoinGeckoResponseError(f"Expected {label} response to be an array")
        return value

    @staticmethod
    def _as_decimal(value: Any, label: str) -> Decimal:
        """Convert a provider numeric value into an exact decimal representation."""

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise CoinGeckoResponseError(f"Expected {label} to be numeric") from error

    @staticmethod
    def _require_values(name: str, values: Sequence[str]) -> None:
        """Ensure required query parameter lists contain non-empty strings."""

        if not values or any(not value.strip() for value in values):
            raise ValueError(f"{name} must contain at least one non-empty value")

    @staticmethod
    def _normalize_search_result(item: Mapping[str, Any]) -> CoinSearchResult:
        """Convert a CoinGecko search item into a stable application result."""

        rank = item.get("market_cap_rank")
        return CoinSearchResult(
            coin_id=str(item.get("id", "")),
            symbol=str(item.get("symbol", "")),
            name=str(item.get("name", "")),
            market_cap_rank=rank if isinstance(rank, int) else None,
            thumb_url=str(item["thumb"]) if item.get("thumb") else None,
        )
