"""Asynchronous, rate-limit-aware client for DEX Screener public market data."""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import logging
from time import monotonic
from typing import Any

import httpx

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class DexScreenerError(Exception):
    """Base exception for DEX Screener provider failures."""


class DexScreenerRequestError(DexScreenerError):
    """Raised when a DEX Screener request cannot be completed."""


class DexScreenerResponseError(DexScreenerError):
    """Raised when DEX Screener returns malformed provider data."""


@dataclass(frozen=True, slots=True)
class DexPair:
    """Normalized DEX Screener pair snapshot."""

    chain_id: str
    dex_id: str
    pair_address: str
    base_symbol: str
    quote_symbol: str
    price_usd: Decimal | None
    liquidity_usd: Decimal | None
    volume_24h: Decimal | None
    market_cap: Decimal | None
    url: str | None


@dataclass(frozen=True, slots=True)
class PairLiquidity:
    """Normalized pair liquidity totals."""

    pair_address: str
    usd: Decimal | None
    base: Decimal | None
    quote: Decimal | None


@dataclass(frozen=True, slots=True)
class PairPrice:
    """Normalized pair price in native and USD units."""

    pair_address: str
    native: Decimal | None
    usd: Decimal | None


@dataclass(frozen=True, slots=True)
class PairVolume:
    """Normalized volume values keyed by DEX Screener time-window label."""

    pair_address: str
    values: Mapping[str, Decimal]


class DexScreenerClient:
    """Fetch normalized DEX Screener data with local pacing and retry handling."""

    _RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        requests_per_minute: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Configure the client with explicit values or project settings."""

        settings = get_settings()
        timeout = timeout_seconds if timeout_seconds is not None else settings.dexscreener_timeout_seconds
        self._max_retries = max_retries if max_retries is not None else settings.dexscreener_max_retries
        rpm = requests_per_minute if requests_per_minute is not None else settings.dexscreener_requests_per_minute
        if timeout <= 0 or self._max_retries < 0 or rpm <= 0:
            raise ValueError("timeout, retries, and requests_per_minute must be valid")
        self._minimum_interval = 60.0 / rpm
        self._next_request_at = 0.0
        self._rate_lock = asyncio.Lock()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=(base_url or settings.dexscreener_base_url).rstrip("/"),
            timeout=httpx.Timeout(timeout),
            headers={"Accept": "application/json", "User-Agent": "CryptoAlpha/0.1"},
        )

    async def __aenter__(self) -> "DexScreenerClient":
        """Return the client for use in an async context manager."""

        return self

    async def __aexit__(self, *_: object) -> None:
        """Close owned HTTP resources."""

        await self.aclose()

    async def aclose(self) -> None:
        """Close the internally created HTTP client."""

        if self._owns_client:
            await self._client.aclose()

    async def get_pair(self, chain_id: str, pair_address: str) -> DexPair:
        """Look up and normalize a pair using its chain and pair address."""

        self._require("chain_id", chain_id)
        self._require("pair_address", pair_address)
        payload = self._mapping(await self._request_json(f"/latest/dex/pairs/{chain_id}/{pair_address}"), "pair")
        pairs = self._sequence(payload.get("pairs"), "pairs")
        if not pairs:
            raise DexScreenerResponseError("DEX Screener did not return the requested pair")
        return self._pair(self._mapping(pairs[0], "pair item"))

    async def get_liquidity(self, chain_id: str, pair_address: str) -> PairLiquidity:
        """Return normalized liquidity values for a pair."""

        payload = await self._pair_payload(chain_id, pair_address)
        liquidity = self._mapping(payload.get("liquidity") or {}, "liquidity")
        return PairLiquidity(str(payload.get("pairAddress", pair_address)), self._optional_decimal(liquidity.get("usd")), self._optional_decimal(liquidity.get("base")), self._optional_decimal(liquidity.get("quote")))

    async def get_volume(self, chain_id: str, pair_address: str) -> PairVolume:
        """Return normalized volume values for all periods provided by the pair snapshot."""

        payload = await self._pair_payload(chain_id, pair_address)
        volume = self._mapping(payload.get("volume") or {}, "volume")
        return PairVolume(str(payload.get("pairAddress", pair_address)), {str(key): self._decimal(value) for key, value in volume.items() if value is not None})

    async def get_price(self, chain_id: str, pair_address: str) -> PairPrice:
        """Return normalized native and USD pair prices."""

        payload = await self._pair_payload(chain_id, pair_address)
        return PairPrice(str(payload.get("pairAddress", pair_address)), self._optional_decimal(payload.get("priceNative")), self._optional_decimal(payload.get("priceUsd")))

    async def get_trending_pairs(self, *, limit: int = 20) -> list[DexPair]:
        """Return pairs for the most actively boosted tokens as a trending-pair proxy.

        DEX Screener exposes boosted tokens rather than a dedicated trending-pairs API.
        Each boosted token is resolved through its documented token-pairs endpoint.
        """

        if not 1 <= limit <= 30:
            raise ValueError("limit must be between 1 and 30")
        boosts = self._sequence(await self._request_json("/token-boosts/top/v1"), "top boosts")
        results: list[DexPair] = []
        seen: set[tuple[str, str]] = set()
        for boost in boosts:
            item = self._mapping(boost, "boost")
            chain_id, token_address = str(item.get("chainId", "")), str(item.get("tokenAddress", ""))
            if not chain_id or not token_address:
                continue
            pairs = self._sequence(await self._request_json(f"/token-pairs/v1/{chain_id}/{token_address}"), "token pairs")
            for raw_pair in pairs:
                pair = self._pair(self._mapping(raw_pair, "token pair"))
                key = (pair.chain_id, pair.pair_address)
                if key not in seen:
                    results.append(pair)
                    seen.add(key)
                if len(results) >= limit:
                    return results
        return results

    async def _pair_payload(self, chain_id: str, pair_address: str) -> Mapping[str, Any]:
        """Fetch one pair response and return its first pair object."""

        self._require("chain_id", chain_id)
        self._require("pair_address", pair_address)
        response = self._mapping(await self._request_json(f"/latest/dex/pairs/{chain_id}/{pair_address}"), "pair")
        pairs = self._sequence(response.get("pairs"), "pairs")
        if not pairs:
            raise DexScreenerResponseError("DEX Screener did not return the requested pair")
        return self._mapping(pairs[0], "pair item")

    async def _request_json(self, path: str) -> Any:
        """Send a locally paced request with retries for provider rate limits and outages."""

        for attempt in range(self._max_retries + 1):
            try:
                await self._wait_for_slot()
                response = await self._client.get(path)
                if response.status_code in self._RETRYABLE_STATUS_CODES and attempt < self._max_retries:
                    await self._backoff(attempt, response)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt >= self._max_retries:
                    logger.warning("DEX Screener request exhausted retries: %s", error)
                    raise DexScreenerRequestError("DEX Screener network request failed") from error
                await self._backoff(attempt)
            except httpx.HTTPStatusError as error:
                logger.warning("DEX Screener returned HTTP %d", error.response.status_code)
                raise DexScreenerRequestError(f"DEX Screener returned HTTP {error.response.status_code}") from error
            except ValueError as error:
                raise DexScreenerResponseError("DEX Screener returned invalid JSON") from error
        raise DexScreenerRequestError("DEX Screener retry loop ended unexpectedly")

    async def _wait_for_slot(self) -> None:
        """Serialize request starts enough to honor the configured provider budget."""

        async with self._rate_lock:
            now = monotonic()
            delay = self._next_request_at - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_request_at = monotonic() + self._minimum_interval

    async def _backoff(self, attempt: int, response: httpx.Response | None = None) -> None:
        """Delay a retry using a server-supplied rate-limit window when available."""

        retry_after = response.headers.get("Retry-After") if response else None
        try:
            delay = max(0.0, float(retry_after)) if retry_after else min(2**attempt, 8.0)
        except ValueError:
            delay = min(2**attempt, 8.0)
        logger.info("Retrying DEX Screener request in %.2fs", delay)
        await asyncio.sleep(delay)

    @classmethod
    def _pair(cls, item: Mapping[str, Any]) -> DexPair:
        """Normalize a DEX Screener pair object."""

        base = cls._mapping(item.get("baseToken"), "base token")
        quote = cls._mapping(item.get("quoteToken"), "quote token")
        volume = cls._mapping(item.get("volume") or {}, "volume")
        liquidity = cls._mapping(item.get("liquidity") or {}, "liquidity")
        return DexPair(
            chain_id=str(item.get("chainId", "")), dex_id=str(item.get("dexId", "")), pair_address=str(item.get("pairAddress", "")),
            base_symbol=str(base.get("symbol", "")), quote_symbol=str(quote.get("symbol", "")),
            price_usd=cls._optional_decimal(item.get("priceUsd")), liquidity_usd=cls._optional_decimal(liquidity.get("usd")),
            volume_24h=cls._optional_decimal(volume.get("h24")), market_cap=cls._optional_decimal(item.get("marketCap")),
            url=str(item["url"]) if item.get("url") else None,
        )

    @staticmethod
    def _mapping(value: Any, label: str) -> Mapping[str, Any]:
        """Validate a JSON object response value."""

        if not isinstance(value, Mapping):
            raise DexScreenerResponseError(f"Expected DEX Screener {label} to be an object")
        return value

    @staticmethod
    def _sequence(value: Any, label: str) -> Sequence[Any]:
        """Validate a JSON array response value."""

        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise DexScreenerResponseError(f"Expected DEX Screener {label} to be an array")
        return value

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        """Convert a required numeric value to ``Decimal``."""

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise DexScreenerResponseError("Expected DEX Screener value to be numeric") from error

    @classmethod
    def _optional_decimal(cls, value: Any) -> Decimal | None:
        """Convert an optional provider numeric field."""

        return cls._decimal(value) if value is not None else None

    @staticmethod
    def _require(name: str, value: str) -> None:
        """Validate required string endpoint identifiers."""

        if not value or not value.strip():
            raise ValueError(f"{name} must not be blank")
