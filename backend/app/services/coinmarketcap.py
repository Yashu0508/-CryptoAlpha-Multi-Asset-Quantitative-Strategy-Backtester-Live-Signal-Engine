"""Asynchronous, normalized client for the CoinMarketCap Pro API."""

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


class CoinMarketCapError(Exception):
    """Base exception for CoinMarketCap client failures."""


class CoinMarketCapRequestError(CoinMarketCapError):
    """Raised when a request fails after retry attempts are exhausted."""


class CoinMarketCapResponseError(CoinMarketCapError):
    """Raised when an API response does not meet the expected contract."""


@dataclass(frozen=True, slots=True)
class MarketRanking:
    """Normalized ranked cryptocurrency market snapshot."""

    coin_id: int
    rank: int | None
    name: str
    symbol: str
    price: Decimal
    market_cap: Decimal
    volume_24h: Decimal
    last_updated: datetime | None


@dataclass(frozen=True, slots=True)
class GlobalMetrics:
    """Normalized aggregate market metrics for one quote currency."""

    currency: str
    total_market_cap: Decimal
    total_volume_24h: Decimal
    btc_dominance: Decimal | None
    eth_dominance: Decimal | None
    active_cryptocurrencies: int | None
    last_updated: datetime | None


@dataclass(frozen=True, slots=True)
class FearAndGreedIndex:
    """Normalized CoinMarketCap market-sentiment reading."""

    value: int
    classification: str
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class AltcoinSeasonIndex:
    """Normalized CoinMarketCap altcoin-season snapshot."""

    value: int
    altcoin_market_cap: Decimal | None
    snapshot_time: datetime | None
    yearly_high: int | None
    yearly_low: int | None


@dataclass(frozen=True, slots=True)
class MarketAggregate:
    """Normalized single aggregate value such as global market cap or volume."""

    currency: str
    value: Decimal
    as_of: datetime | None


class CoinMarketCapClient:
    """Retrieve normalized market context from CoinMarketCap using an API key.

    The client accepts an injected ``httpx.AsyncClient`` for tests. For production,
    set ``COINMARKETCAP_API_KEY`` in the environment; it is sent only in the
    ``X-CMC_PRO_API_KEY`` request header.
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
        """Create a client with explicit values or environment-backed settings."""

        settings = get_settings()
        resolved_api_key = api_key if api_key is not None else settings.coinmarketcap_api_key
        if not resolved_api_key:
            raise ValueError("COINMARKETCAP_API_KEY must be configured")

        self._max_retries = max_retries if max_retries is not None else settings.coinmarketcap_max_retries
        timeout = timeout_seconds if timeout_seconds is not None else settings.coinmarketcap_timeout_seconds
        if self._max_retries < 0 or timeout <= 0:
            raise ValueError("max_retries must be non-negative and timeout_seconds must be positive")

        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=(base_url or settings.coinmarketcap_base_url).rstrip("/"),
            timeout=httpx.Timeout(timeout),
            headers={
                "Accept": "application/json",
                "User-Agent": "CryptoAlpha/0.1",
                "X-CMC_PRO_API_KEY": resolved_api_key,
            },
        )

    async def __aenter__(self) -> "CoinMarketCapClient":
        """Return this instance for use in an async context manager."""

        return self

    async def __aexit__(self, *_: object) -> None:
        """Close internally owned resources on context exit."""

        await self.aclose()

    async def aclose(self) -> None:
        """Release the internally owned HTTP connection pool."""

        if self._owns_client:
            await self._client.aclose()

    async def get_market_rankings(
        self, *, start: int = 1, limit: int = 100, convert: str = "USD"
    ) -> list[MarketRanking]:
        """Return a ranked normalized cryptocurrency listing by market capitalization."""

        if start < 1 or not 1 <= limit <= 5000:
            raise ValueError("start must be positive and limit must be between 1 and 5000")
        currency = self._currency(convert)
        data = self._sequence(
            await self._data("/v1/cryptocurrency/listings/latest", {"start": str(start), "limit": str(limit), "convert": currency}),
            "market rankings",
        )
        return [self._ranking(self._mapping(item, "market ranking"), currency) for item in data]

    async def get_global_metrics(self, *, convert: str = "USD") -> GlobalMetrics:
        """Return normalized global market-cap, volume, and dominance metrics."""

        currency = self._currency(convert)
        data = self._mapping(await self._data("/v1/global-metrics/quotes/latest", {"convert": currency}), "global metrics")
        quote = self._quote(data, currency)
        return GlobalMetrics(
            currency=currency,
            total_market_cap=self._decimal(quote.get("total_market_cap"), "total market cap"),
            total_volume_24h=self._decimal(quote.get("total_volume_24h"), "total volume"),
            btc_dominance=self._optional_decimal(data.get("btc_dominance"), "BTC dominance"),
            eth_dominance=self._optional_decimal(data.get("eth_dominance"), "ETH dominance"),
            active_cryptocurrencies=self._optional_int(data.get("active_cryptocurrencies")),
            last_updated=self._optional_timestamp(data.get("last_updated") or quote.get("last_updated")),
        )

    async def get_fear_and_greed_index(self) -> FearAndGreedIndex:
        """Return CoinMarketCap's latest normalized crypto fear-and-greed value."""

        data = self._mapping(await self._data("/v3/fear-and-greed/latest", {}), "fear and greed")
        return FearAndGreedIndex(
            value=self._integer(data.get("value"), "fear and greed value"),
            classification=str(data.get("value_classification", "")),
            updated_at=self._optional_timestamp(data.get("update_time")),
        )

    async def get_altcoin_season(self) -> AltcoinSeasonIndex:
        """Return CoinMarketCap's latest normalized altcoin-season index."""

        data = self._mapping(await self._data("/v1/altcoin-season-index/latest", {}), "altcoin season")
        return AltcoinSeasonIndex(
            value=self._integer(data.get("altcoin_index"), "altcoin season index"),
            altcoin_market_cap=self._optional_decimal(data.get("altcoin_marketcap"), "altcoin market cap"),
            snapshot_time=self._optional_timestamp(data.get("snapshot_time")),
            yearly_high=self._optional_int(data.get("yearly_high")),
            yearly_low=self._optional_int(data.get("yearly_low")),
        )

    async def get_market_cap(self, *, convert: str = "USD") -> MarketAggregate:
        """Return the global cryptocurrency market capitalization."""

        metrics = await self.get_global_metrics(convert=convert)
        return MarketAggregate(metrics.currency, metrics.total_market_cap, metrics.last_updated)

    async def get_volume(self, *, convert: str = "USD") -> MarketAggregate:
        """Return the global 24-hour cryptocurrency trading volume."""

        metrics = await self.get_global_metrics(convert=convert)
        return MarketAggregate(metrics.currency, metrics.total_volume_24h, metrics.last_updated)

    async def _data(self, path: str, params: Mapping[str, str]) -> Any:
        """Fetch a CoinMarketCap response and extract its standard ``data`` envelope."""

        response = self._mapping(await self._request_json(path, params), "response")
        status = self._mapping(response.get("status"), "response status")
        if self._integer(status.get("error_code"), "response error code") != 0:
            raise CoinMarketCapResponseError(str(status.get("error_message") or "CoinMarketCap request failed"))
        if "data" not in response:
            raise CoinMarketCapResponseError("CoinMarketCap response does not contain data")
        return response["data"]

    async def _request_json(self, path: str, params: Mapping[str, str]) -> Any:
        """Execute a retryable HTTP GET and decode its JSON body."""

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(path, params=params)
                if response.status_code in self._RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                    await self._backoff(attempt, response)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt >= self._max_retries:
                    logger.warning("CoinMarketCap request exhausted retries: %s", error)
                    raise CoinMarketCapRequestError("CoinMarketCap network request failed") from error
                await self._backoff(attempt)
            except httpx.HTTPStatusError as error:
                logger.warning("CoinMarketCap returned HTTP %d for %s", error.response.status_code, path)
                raise CoinMarketCapRequestError(f"CoinMarketCap returned HTTP {error.response.status_code}") from error
            except ValueError as error:
                raise CoinMarketCapResponseError("CoinMarketCap returned invalid JSON") from error
        raise CoinMarketCapRequestError("CoinMarketCap retry loop ended unexpectedly")

    async def _backoff(self, attempt: int, response: httpx.Response | None = None) -> None:
        """Pause between retries using the supplied rate-limit delay when present."""

        retry_after = response.headers.get("Retry-After") if response else None
        try:
            delay = max(0.0, float(retry_after)) if retry_after else min(2**attempt, 8.0)
        except ValueError:
            delay = min(2**attempt, 8.0)
        logger.info("Retrying CoinMarketCap request in %.2fs", delay)
        await asyncio.sleep(delay)

    @classmethod
    def _ranking(cls, data: Mapping[str, Any], currency: str) -> MarketRanking:
        """Convert a listings entry into a provider-independent ranking object."""

        quote = cls._quote(data, currency)
        return MarketRanking(
            coin_id=cls._integer(data.get("id"), "coin ID"),
            rank=cls._optional_int(data.get("cmc_rank")),
            name=str(data.get("name", "")),
            symbol=str(data.get("symbol", "")),
            price=cls._decimal(quote.get("price"), "coin price"),
            market_cap=cls._decimal(quote.get("market_cap"), "coin market cap"),
            volume_24h=cls._decimal(quote.get("volume_24h"), "coin volume"),
            last_updated=cls._optional_timestamp(quote.get("last_updated") or data.get("last_updated")),
        )

    @classmethod
    def _quote(cls, data: Mapping[str, Any], currency: str) -> Mapping[str, Any]:
        """Extract one quote currency object from a CoinMarketCap response."""

        quotes = cls._mapping(data.get("quote"), "quote")
        quote = quotes.get(currency)
        if quote is None:
            raise CoinMarketCapResponseError(f"CoinMarketCap response has no {currency} quote")
        return cls._mapping(quote, f"{currency} quote")

    @staticmethod
    def _currency(value: str) -> str:
        """Normalize and validate a quote currency symbol."""

        currency = value.strip().upper()
        if not currency:
            raise ValueError("convert must not be blank")
        return currency

    @staticmethod
    def _mapping(value: Any, label: str) -> Mapping[str, Any]:
        """Validate a JSON object response value."""

        if not isinstance(value, Mapping):
            raise CoinMarketCapResponseError(f"Expected CoinMarketCap {label} to be an object")
        return value

    @staticmethod
    def _sequence(value: Any, label: str) -> Sequence[Any]:
        """Validate a JSON array response value."""

        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise CoinMarketCapResponseError(f"Expected CoinMarketCap {label} to be an array")
        return value

    @staticmethod
    def _decimal(value: Any, label: str) -> Decimal:
        """Convert a required provider numeric value to an exact decimal."""

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise CoinMarketCapResponseError(f"Expected CoinMarketCap {label} to be numeric") from error

    @classmethod
    def _optional_decimal(cls, value: Any, label: str) -> Decimal | None:
        """Convert an optional numeric field to ``Decimal``."""

        return cls._decimal(value, label) if value is not None else None

    @staticmethod
    def _integer(value: Any, label: str) -> int:
        """Convert a required provider integer field."""

        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise CoinMarketCapResponseError(f"Expected CoinMarketCap {label} to be an integer") from error

    @classmethod
    def _optional_int(cls, value: Any) -> int | None:
        """Convert an optional provider integer field."""

        return cls._integer(value, "integer field") if value is not None else None

    @staticmethod
    def _optional_timestamp(value: Any) -> datetime | None:
        """Convert an optional ISO-8601 CoinMarketCap timestamp."""

        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as error:
            raise CoinMarketCapResponseError("CoinMarketCap timestamp is invalid") from error
