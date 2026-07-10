"""Provider-neutral market-data facade for all CryptoAlpha application code.

Application layers must depend on :class:`MarketDataService` rather than a concrete
third-party client. Provider-specific request shapes and response models stay inside
the individual adapter modules.
"""

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import logging

from app.config.settings import get_settings
from app.services.altfins import AltFinsClient
from app.services.binance import BinanceClient
from app.services.coingecko import CoinGeckoClient
from app.services.coinmarketcap import CoinMarketCapClient
from app.services.dexscreener import DexScreenerClient

logger = logging.getLogger(__name__)


class MarketDataSource(StrEnum):
    """Supported market-data providers exposed by the facade."""

    BINANCE = "binance"
    COINGECKO = "coingecko"
    COINMARKETCAP = "coinmarketcap"
    DEXSCREENER = "dexscreener"
    ALTFINS = "altfins"


class MarketDataServiceError(Exception):
    """Base error raised by the provider-neutral market-data boundary."""


class ProviderUnavailableError(MarketDataServiceError):
    """Raised when a requested optional provider has not been configured."""


class MarketDataNotFoundError(MarketDataServiceError):
    """Raised when a provider has no market data for a requested identifier."""


@dataclass(frozen=True, slots=True)
class Price:
    """Provider-neutral current market price."""

    instrument: str
    currency: str
    value: Decimal
    source: MarketDataSource
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OHLCV:
    """Provider-neutral OHLCV candle."""

    instrument: str
    interval: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None
    source: MarketDataSource


@dataclass(frozen=True, slots=True)
class MarketCap:
    """Provider-neutral market-cap value."""

    instrument: str | None
    currency: str
    value: Decimal
    source: MarketDataSource
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    """Provider-neutral price level."""

    price: Decimal
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class OrderBook:
    """Provider-neutral order-book snapshot."""

    instrument: str
    last_update_id: int
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
    source: MarketDataSource
    observed_at: datetime | None


@dataclass(frozen=True, slots=True)
class Sentiment:
    """Combined provider-neutral market-sentiment snapshot."""

    classification: str | None
    score: Decimal | None
    fear_greed_value: int | None
    fear_greed_classification: str | None
    altcoin_season_value: int | None
    observed_at: datetime | None
    sources: tuple[MarketDataSource, ...]


class MarketDataService:
    """The sole market-data interface for application services and strategies.

    Binance, CoinGecko, and DEX Screener are available without secrets. CoinMarketCap
    and altFINS are initialized only when their respective environment API keys are
    present, keeping unrelated workflows available in minimal deployments.
    """

    def __init__(
        self,
        *,
        binance: BinanceClient | None = None,
        coingecko: CoinGeckoClient | None = None,
        coinmarketcap: CoinMarketCapClient | None = None,
        dexscreener: DexScreenerClient | None = None,
        altfins: AltFinsClient | None = None,
    ) -> None:
        """Construct the facade with injectable provider clients for testing."""

        settings = get_settings()
        self._binance = binance or BinanceClient()
        self._coingecko = coingecko or CoinGeckoClient()
        self._dexscreener = dexscreener or DexScreenerClient()
        self._coinmarketcap = coinmarketcap or (
            CoinMarketCapClient() if settings.coinmarketcap_api_key else None
        )
        self._altfins = altfins or (AltFinsClient() if settings.altfins_api_key else None)
        self._owns_clients = {
            "binance": binance is None,
            "coingecko": coingecko is None,
            "coinmarketcap": coinmarketcap is None,
            "dexscreener": dexscreener is None,
            "altfins": altfins is None,
        }

    async def __aenter__(self) -> "MarketDataService":
        """Return the facade for use in an async context manager."""

        return self

    async def __aexit__(self, *_: object) -> None:
        """Close provider resources owned by this facade."""

        await self.aclose()

    async def aclose(self) -> None:
        """Close only provider clients instantiated by this service."""

        closers: list[Awaitable[None]] = []
        for name, client in self._clients().items():
            if client is not None and self._owns_clients[name]:
                closers.append(client.aclose())
        await asyncio.gather(*closers)

    async def get_price(
        self,
        instrument: str,
        *,
        currency: str = "USD",
        source: MarketDataSource = MarketDataSource.BINANCE,
        chain_id: str | None = None,
        pair_address: str | None = None,
    ) -> Price:
        """Return a normalized price from a selected provider.

        Binance expects an exchange symbol such as ``BTCUSDT``. CoinGecko expects a
        CoinGecko ID such as ``bitcoin``. DEX Screener requires ``chain_id`` and
        ``pair_address`` because DEX symbols are not globally unique.
        """

        resolved = self._source(source)
        if resolved is MarketDataSource.BINANCE:
            ticker = await self._binance.get_ticker(instrument)
            return Price(ticker.symbol, currency.upper(), ticker.last_price, resolved, ticker.close_time)
        if resolved is MarketDataSource.COINGECKO:
            prices = await self._coingecko.get_current_price([instrument], vs_currencies=[currency])
            if not prices or currency.lower() not in prices[0].prices:
                raise MarketDataNotFoundError(f"No CoinGecko price found for {instrument}")
            return Price(instrument, currency.upper(), prices[0].prices[currency.lower()], resolved)
        if resolved is MarketDataSource.DEXSCREENER:
            pair = await self._dexscreener.get_pair(self._required("chain_id", chain_id), self._required("pair_address", pair_address))
            if pair.price_usd is None:
                raise MarketDataNotFoundError(f"No USD price found for DEX pair {pair.pair_address}")
            return Price(pair.pair_address, "USD", pair.price_usd, resolved)
        raise ValueError("get_price supports binance, coingecko, and dexscreener sources")

    async def get_ohlcv(
        self,
        instrument: str,
        interval: str,
        *,
        source: MarketDataSource = MarketDataSource.BINANCE,
        currency: str = "USD",
        limit: int = 500,
        days: int | str = 1,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[OHLCV]:
        """Return normalized historical candles from Binance or CoinGecko."""

        resolved = self._source(source)
        if resolved is MarketDataSource.BINANCE:
            candles = await self._binance.get_klines(instrument, interval, limit=limit, start_time=start_time, end_time=end_time)
            return [OHLCV(instrument, interval, candle.open_time, candle.open, candle.high, candle.low, candle.close, candle.volume, resolved) for candle in candles]
        if resolved is MarketDataSource.COINGECKO:
            candles = await self._coingecko.get_historical_ohlcv(instrument, vs_currency=currency, days=days)
            return [OHLCV(instrument, interval, candle.timestamp, candle.open, candle.high, candle.low, candle.close, candle.volume, resolved) for candle in candles]
        raise ValueError("get_ohlcv supports binance and coingecko sources")

    async def get_market_cap(
        self,
        instrument: str | None = None,
        *,
        currency: str = "USD",
        source: MarketDataSource = MarketDataSource.COINMARKETCAP,
        chain_id: str | None = None,
        pair_address: str | None = None,
    ) -> MarketCap:
        """Return normalized global, asset, or DEX-pair market capitalization."""

        resolved = self._source(source)
        if resolved is MarketDataSource.COINMARKETCAP:
            client = self._configured("coinmarketcap", self._coinmarketcap)
            aggregate = await client.get_market_cap(convert=currency)
            return MarketCap(None, aggregate.currency, aggregate.value, resolved, aggregate.as_of)
        if resolved is MarketDataSource.COINGECKO:
            coin_id = self._required("instrument", instrument)
            market_cap = await self._coingecko.get_market_cap(coin_id, vs_currency=currency)
            if market_cap is None:
                raise MarketDataNotFoundError(f"No CoinGecko market cap found for {coin_id}")
            return MarketCap(coin_id, market_cap.currency.upper(), market_cap.value, resolved)
        if resolved is MarketDataSource.DEXSCREENER:
            pair = await self._dexscreener.get_pair(
                self._required("chain_id", chain_id), self._required("pair_address", pair_address)
            )
            if pair.market_cap is None:
                raise MarketDataNotFoundError(f"No market cap found for DEX pair {pair.pair_address}")
            return MarketCap(pair.pair_address, "USD", pair.market_cap, resolved)
        raise ValueError("get_market_cap supports coinmarketcap, coingecko, and dexscreener sources")

    async def get_order_book(
        self, instrument: str, *, limit: int = 100, source: MarketDataSource = MarketDataSource.BINANCE
    ) -> OrderBook:
        """Return a normalized order-book snapshot from a centralized exchange provider."""

        if self._source(source) is not MarketDataSource.BINANCE:
            raise ValueError("get_order_book currently supports the binance source only")
        snapshot = await self._binance.get_order_book(instrument, limit=limit)
        return OrderBook(
            instrument=snapshot.symbol,
            last_update_id=snapshot.last_update_id,
            bids=tuple(OrderBookLevel(level.price, level.quantity) for level in snapshot.bids),
            asks=tuple(OrderBookLevel(level.price, level.quantity) for level in snapshot.asks),
            source=MarketDataSource.BINANCE,
            observed_at=snapshot.event_time,
        )

    async def get_sentiment(self) -> Sentiment:
        """Combine configured CoinMarketCap and altFINS sentiment into one snapshot.

        A temporary failure in one configured sentiment provider does not discard a
        successful reading from the other provider. If neither provider returns data,
        the method raises an explicit service error.
        """

        tasks: list[tuple[MarketDataSource, str, Awaitable[object]]] = []
        if self._coinmarketcap is not None:
            tasks.extend(
                [
                    (MarketDataSource.COINMARKETCAP, "fear-and-greed", self._coinmarketcap.get_fear_and_greed_index()),
                    (MarketDataSource.COINMARKETCAP, "altcoin-season", self._coinmarketcap.get_altcoin_season()),
                ]
            )
        if self._altfins is not None:
            tasks.append((MarketDataSource.ALTFINS, "market-sentiment", self._altfins.get_market_sentiment()))
        if not tasks:
            raise ProviderUnavailableError("Configure COINMARKETCAP_API_KEY or ALTFINS_API_KEY for sentiment")

        settled = await asyncio.gather(*(task[2] for task in tasks), return_exceptions=True)
        results: dict[str, object] = {}
        sources: set[MarketDataSource] = set()
        for (source, label, _), result in zip(tasks, settled, strict=True):
            if isinstance(result, Exception):
                logger.warning("Market sentiment provider %s failed: %s", label, result)
                continue
            results[label] = result
            sources.add(source)
        if not results:
            raise MarketDataServiceError("No configured sentiment provider returned data")

        fear_greed = results.get("fear-and-greed")
        altcoin = results.get("altcoin-season")
        altfins = results.get("market-sentiment")
        return Sentiment(
            classification=getattr(altfins, "classification", None) or getattr(fear_greed, "classification", None),
            score=getattr(altfins, "score", None),
            fear_greed_value=getattr(fear_greed, "value", None),
            fear_greed_classification=getattr(fear_greed, "classification", None),
            altcoin_season_value=getattr(altcoin, "value", None),
            observed_at=getattr(altfins, "observed_at", None) or getattr(fear_greed, "updated_at", None),
            sources=tuple(sorted(sources, key=str)),
        )

    def _clients(self) -> dict[str, object | None]:
        """Return all provider clients keyed consistently with ownership tracking."""

        return {
            "binance": self._binance,
            "coingecko": self._coingecko,
            "coinmarketcap": self._coinmarketcap,
            "dexscreener": self._dexscreener,
            "altfins": self._altfins,
        }

    @staticmethod
    def _source(source: MarketDataSource | str) -> MarketDataSource:
        """Coerce a public source value into the closed source enum."""

        try:
            return MarketDataSource(source)
        except ValueError as error:
            raise ValueError(f"Unsupported market-data source: {source}") from error

    @staticmethod
    def _required(name: str, value: str | None) -> str:
        """Return a required nonblank identifier or fail with a clear input error."""

        if not value or not value.strip():
            raise ValueError(f"{name} is required")
        return value

    @staticmethod
    def _configured[T](name: str, client: T | None) -> T:
        """Return a configured optional client or raise a provider-specific error."""

        if client is None:
            raise ProviderUnavailableError(f"{name} is not configured")
        return client
