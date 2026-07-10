"""Asynchronous REST and reconnecting WebSocket client for Binance Spot market data."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import logging
from typing import Any

import httpx
import websockets
from websockets.exceptions import WebSocketException

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class BinanceError(Exception):
    """Base exception for Binance client failures."""


class BinanceRequestError(BinanceError):
    """Raised after a REST request cannot complete successfully."""


class BinanceResponseError(BinanceError):
    """Raised when Binance returns malformed or unexpected payload data."""


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    """One normalized price and quantity level in an order book."""

    price: Decimal
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class OrderBook:
    """A normalized Binance order-book snapshot or update."""

    symbol: str
    last_update_id: int
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    event_time: datetime | None


@dataclass(frozen=True, slots=True)
class RecentTrade:
    """A normalized executed Binance trade."""

    trade_id: int
    symbol: str
    price: Decimal
    quantity: Decimal
    quote_quantity: Decimal
    executed_at: datetime
    buyer_is_maker: bool


@dataclass(frozen=True, slots=True)
class Kline:
    """A normalized Binance candlestick."""

    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trade_count: int
    is_closed: bool | None = None


@dataclass(frozen=True, slots=True)
class Ticker:
    """A normalized 24-hour Binance ticker."""

    symbol: str
    last_price: Decimal
    price_change: Decimal
    price_change_percent: Decimal
    high_price: Decimal
    low_price: Decimal
    base_volume: Decimal
    quote_volume: Decimal
    open_time: datetime
    close_time: datetime
    trade_count: int


class BinanceClient:
    """Provide normalized Binance Spot REST data and reconnecting WebSocket streams.

    Public market-data endpoints require no credentials. An injected ``httpx`` client
    enables deterministic tests, while internally created clients are closed through
    :meth:`aclose` or the async context-manager protocol.
    """

    _RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        rest_base_url: str | None = None,
        websocket_base_url: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Create a Binance client using explicit values or application settings."""

        settings = get_settings()
        self._timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.binance_timeout_seconds
        )
        self._max_retries = max_retries if max_retries is not None else settings.binance_max_retries
        self._websocket_base_url = (websocket_base_url or settings.binance_websocket_base_url).rstrip("/")
        self._reconnect_max_delay = settings.binance_websocket_reconnect_max_delay_seconds
        if self._timeout_seconds <= 0 or self._max_retries < 0 or self._reconnect_max_delay <= 0:
            raise ValueError("Binance timeout, retry, and reconnect settings must be valid")

        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=(rest_base_url or settings.binance_rest_base_url).rstrip("/"),
            timeout=httpx.Timeout(self._timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "CryptoAlpha/0.1"},
        )

    async def __aenter__(self) -> "BinanceClient":
        """Return this client for use in an async context manager."""

        return self

    async def __aexit__(self, *_: object) -> None:
        """Release owned REST resources when leaving an async context."""

        await self.aclose()

    async def aclose(self) -> None:
        """Close the internally-owned HTTP client."""

        if self._owns_client:
            await self._client.aclose()

    async def get_order_book(self, symbol: str, *, limit: int = 100) -> OrderBook:
        """Return a normalized REST order-book snapshot for a trading pair."""

        self._validate_symbol(symbol)
        if limit not in {5, 10, 20, 50, 100, 500, 1000, 5000}:
            raise ValueError("limit must be a Binance-supported order book depth")
        payload = self._mapping(await self._request_json("/depth", {"symbol": symbol.upper(), "limit": str(limit)}), "order book")
        return self._normalize_order_book(payload, symbol.upper())

    async def get_recent_trades(self, symbol: str, *, limit: int = 500) -> list[RecentTrade]:
        """Return normalized recent execution records for a trading pair."""

        self._validate_symbol(symbol)
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        payload = self._sequence(await self._request_json("/trades", {"symbol": symbol.upper(), "limit": str(limit)}), "recent trades")
        return [self._normalize_trade(self._mapping(row, "trade"), symbol.upper()) for row in payload]

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        *,
        limit: int = 500,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[Kline]:
        """Return normalized historical candles for a Binance-supported interval."""

        self._validate_symbol(symbol)
        if not interval or not 1 <= limit <= 1000:
            raise ValueError("interval is required and limit must be between 1 and 1000")
        params = {"symbol": symbol.upper(), "interval": interval, "limit": str(limit)}
        if start_time:
            params["startTime"] = str(self._to_milliseconds(start_time))
        if end_time:
            params["endTime"] = str(self._to_milliseconds(end_time))
        payload = self._sequence(await self._request_json("/klines", params), "klines")
        return [self._normalize_kline(self._sequence(row, "kline"), symbol.upper(), interval) for row in payload]

    async def get_ticker(self, symbol: str) -> Ticker:
        """Return normalized 24-hour ticker statistics for a trading pair."""

        self._validate_symbol(symbol)
        payload = self._mapping(await self._request_json("/ticker/24hr", {"symbol": symbol.upper()}), "ticker")
        return self._normalize_ticker(payload)

    async def stream_order_book(self, symbol: str, *, depth: int = 20) -> AsyncIterator[OrderBook]:
        """Yield normalized depth updates and automatically reconnect on disconnects."""

        self._validate_symbol(symbol)
        stream = f"{symbol.lower()}@depth{depth}@100ms"
        async for payload in self._stream_json(stream):
            yield self._normalize_order_book(payload, symbol.upper())

    async def stream_recent_trades(self, symbol: str) -> AsyncIterator[RecentTrade]:
        """Yield normalized aggregate trade events with automatic reconnection."""

        self._validate_symbol(symbol)
        async for payload in self._stream_json(f"{symbol.lower()}@trade"):
            yield self._normalize_trade(payload, symbol.upper())

    async def stream_klines(self, symbol: str, interval: str) -> AsyncIterator[Kline]:
        """Yield normalized kline events with automatic reconnection."""

        self._validate_symbol(symbol)
        if not interval:
            raise ValueError("interval is required")
        async for payload in self._stream_json(f"{symbol.lower()}@kline_{interval}"):
            event = self._mapping(payload.get("k"), "websocket kline")
            yield self._normalize_kline_event(event, symbol.upper(), interval)

    async def stream_ticker(self, symbol: str) -> AsyncIterator[Ticker]:
        """Yield normalized rolling ticker events with automatic reconnection."""

        self._validate_symbol(symbol)
        async for payload in self._stream_json(f"{symbol.lower()}@ticker"):
            yield self._normalize_ticker(payload)

    async def _request_json(self, path: str, params: Mapping[str, str]) -> Any:
        """Perform a GET request with bounded retries for transient failures."""

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
                    logger.warning("Binance REST request exhausted retries: %s", error)
                    raise BinanceRequestError("Binance network request failed") from error
                await self._backoff(attempt)
            except httpx.HTTPStatusError as error:
                logger.warning("Binance REST request returned HTTP %d", error.response.status_code)
                raise BinanceRequestError(f"Binance returned HTTP {error.response.status_code}") from error
            except ValueError as error:
                raise BinanceResponseError("Binance returned invalid JSON") from error
        raise BinanceRequestError("Binance retry loop ended unexpectedly")

    async def _stream_json(self, stream: str) -> AsyncIterator[Mapping[str, Any]]:
        """Connect to a single Binance stream and reconnect until cancellation."""

        reconnect_attempt = 0
        url = f"{self._websocket_base_url}/{stream}"
        while True:
            try:
                logger.info("Connecting Binance WebSocket stream %s", stream)
                async with websockets.connect(url, open_timeout=self._timeout_seconds) as socket:
                    reconnect_attempt = 0
                    while True:
                        message = await asyncio.wait_for(socket.recv(), timeout=self._timeout_seconds)
                        try:
                            yield self._mapping(json.loads(message), "websocket message")
                        except (TypeError, json.JSONDecodeError) as error:
                            raise BinanceResponseError("Binance WebSocket returned invalid JSON") from error
            except (WebSocketException, OSError, asyncio.TimeoutError) as error:
                delay = min(2**reconnect_attempt, self._reconnect_max_delay)
                reconnect_attempt += 1
                logger.warning("Binance WebSocket stream %s disconnected: %s; reconnecting in %.1fs", stream, error, delay)
                await asyncio.sleep(delay)

    async def _backoff(self, attempt: int, response: httpx.Response | None = None) -> None:
        """Sleep before a REST retry, honouring a provider Retry-After header."""

        retry_after = response.headers.get("Retry-After") if response else None
        try:
            delay = max(0.0, float(retry_after)) if retry_after else min(2**attempt, 8.0)
        except ValueError:
            delay = min(2**attempt, 8.0)
        logger.info("Retrying Binance request in %.2fs", delay)
        await asyncio.sleep(delay)

    @classmethod
    def _normalize_order_book(cls, payload: Mapping[str, Any], symbol: str) -> OrderBook:
        """Normalize either REST depth data or a WebSocket depth event."""

        bids = payload.get("bids", payload.get("b", []))
        asks = payload.get("asks", payload.get("a", []))
        update_id = payload.get("lastUpdateId", payload.get("u"))
        if update_id is None:
            raise BinanceResponseError("Order book response is missing an update ID")
        event_time = cls._timestamp_or_none(payload.get("E"))
        return OrderBook(
            symbol=symbol,
            last_update_id=cls._as_int(update_id, "order book update ID"),
            bids=cls._normalize_levels(bids, "bids"),
            asks=cls._normalize_levels(asks, "asks"),
            event_time=event_time,
        )

    @classmethod
    def _normalize_trade(cls, payload: Mapping[str, Any], symbol: str) -> RecentTrade:
        """Normalize REST or WebSocket trade fields into one stable trade shape."""

        return RecentTrade(
            trade_id=cls._as_int(payload.get("id", payload.get("t")), "trade ID"),
            symbol=symbol,
            price=cls._decimal(payload.get("price", payload.get("p")), "trade price"),
            quantity=cls._decimal(payload.get("qty", payload.get("q")), "trade quantity"),
            quote_quantity=cls._decimal(payload.get("quoteQty", payload.get("Q")), "trade quote quantity"),
            executed_at=cls._timestamp(payload.get("time", payload.get("T")), "trade time"),
            buyer_is_maker=bool(payload.get("isBuyerMaker", payload.get("m", False))),
        )

    @classmethod
    def _normalize_kline(cls, values: Sequence[Any], symbol: str, interval: str) -> Kline:
        """Normalize a REST kline array."""

        if len(values) < 9:
            raise BinanceResponseError("Binance kline response contains fewer than nine values")
        return Kline(
            symbol=symbol,
            interval=interval,
            open_time=cls._timestamp(values[0], "kline open time"),
            close_time=cls._timestamp(values[6], "kline close time"),
            open=cls._decimal(values[1], "kline open"),
            high=cls._decimal(values[2], "kline high"),
            low=cls._decimal(values[3], "kline low"),
            close=cls._decimal(values[4], "kline close"),
            volume=cls._decimal(values[5], "kline volume"),
            quote_volume=cls._decimal(values[7], "kline quote volume"),
            trade_count=cls._as_int(values[8], "kline trade count"),
        )

    @classmethod
    def _normalize_kline_event(cls, payload: Mapping[str, Any], symbol: str, interval: str) -> Kline:
        """Normalize the nested kline object delivered by Binance WebSockets."""

        return Kline(
            symbol=symbol,
            interval=str(payload.get("i", interval)),
            open_time=cls._timestamp(payload.get("t"), "kline open time"),
            close_time=cls._timestamp(payload.get("T"), "kline close time"),
            open=cls._decimal(payload.get("o"), "kline open"),
            high=cls._decimal(payload.get("h"), "kline high"),
            low=cls._decimal(payload.get("l"), "kline low"),
            close=cls._decimal(payload.get("c"), "kline close"),
            volume=cls._decimal(payload.get("v"), "kline volume"),
            quote_volume=cls._decimal(payload.get("q"), "kline quote volume"),
            trade_count=cls._as_int(payload.get("n"), "kline trade count"),
            is_closed=bool(payload.get("x")),
        )

    @classmethod
    def _normalize_ticker(cls, payload: Mapping[str, Any]) -> Ticker:
        """Normalize REST or WebSocket 24-hour ticker statistics."""

        return Ticker(
            symbol=str(payload.get("symbol", payload.get("s", ""))).upper(),
            last_price=cls._decimal(payload.get("lastPrice", payload.get("c")), "ticker last price"),
            price_change=cls._decimal(payload.get("priceChange", payload.get("p")), "ticker price change"),
            price_change_percent=cls._decimal(
                payload.get("priceChangePercent", payload.get("P")), "ticker price change percent"
            ),
            high_price=cls._decimal(payload.get("highPrice", payload.get("h")), "ticker high price"),
            low_price=cls._decimal(payload.get("lowPrice", payload.get("l")), "ticker low price"),
            base_volume=cls._decimal(payload.get("volume", payload.get("v")), "ticker base volume"),
            quote_volume=cls._decimal(payload.get("quoteVolume", payload.get("q")), "ticker quote volume"),
            open_time=cls._timestamp(payload.get("openTime", payload.get("O")), "ticker open time"),
            close_time=cls._timestamp(payload.get("closeTime", payload.get("C")), "ticker close time"),
            trade_count=cls._as_int(payload.get("count", payload.get("n")), "ticker trade count"),
        )

    @classmethod
    def _normalize_levels(cls, values: Any, label: str) -> tuple[OrderBookLevel, ...]:
        """Normalize Binance's price-level arrays."""

        levels = cls._sequence(values, label)
        normalized: list[OrderBookLevel] = []
        for level in levels:
            parts = cls._sequence(level, f"{label} level")
            if len(parts) < 2:
                raise BinanceResponseError(f"Binance {label} level contains fewer than two values")
            normalized.append(
                OrderBookLevel(price=cls._decimal(parts[0], f"{label} price"), quantity=cls._decimal(parts[1], f"{label} quantity"))
            )
        return tuple(normalized)

    @staticmethod
    def _mapping(value: Any, label: str) -> Mapping[str, Any]:
        """Validate that a value is a JSON object."""

        if not isinstance(value, Mapping):
            raise BinanceResponseError(f"Expected Binance {label} response to be an object")
        return value

    @staticmethod
    def _sequence(value: Any, label: str) -> Sequence[Any]:
        """Validate that a value is a JSON array rather than a string."""

        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            raise BinanceResponseError(f"Expected Binance {label} response to be an array")
        return value

    @staticmethod
    def _decimal(value: Any, label: str) -> Decimal:
        """Convert a Binance numeric value to ``Decimal`` without binary rounding."""

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise BinanceResponseError(f"Expected Binance {label} to be numeric") from error

    @staticmethod
    def _as_int(value: Any, label: str) -> int:
        """Convert a provider integer field and reject missing or invalid values."""

        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise BinanceResponseError(f"Expected Binance {label} to be an integer") from error

    @classmethod
    def _timestamp(cls, value: Any, label: str) -> datetime:
        """Convert a millisecond epoch value to an aware UTC timestamp."""

        try:
            return datetime.fromtimestamp(float(cls._decimal(value, label) / Decimal(1000)), tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as error:
            raise BinanceResponseError(f"Expected Binance {label} to be a valid epoch") from error

    @classmethod
    def _timestamp_or_none(cls, value: Any) -> datetime | None:
        """Convert an optional Binance event timestamp."""

        return cls._timestamp(value, "event time") if value is not None else None

    @staticmethod
    def _validate_symbol(symbol: str) -> None:
        """Ensure a required Binance symbol has a usable value."""

        if not symbol or not symbol.strip():
            raise ValueError("symbol must not be blank")

    @staticmethod
    def _to_milliseconds(value: datetime) -> int:
        """Convert an aware or naive timestamp to a UTC Unix millisecond epoch."""

        utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return int(utc_value.timestamp() * 1000)
