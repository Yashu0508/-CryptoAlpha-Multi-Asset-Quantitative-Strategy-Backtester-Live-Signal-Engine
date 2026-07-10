"""Application service boundaries.

Market-data consumers should import only ``MarketDataService`` from this package.
"""

from app.services.market_data import MarketDataService

__all__ = ["MarketDataService"]
