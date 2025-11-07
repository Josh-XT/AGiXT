from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_UP
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException

from Globals import getenv

SUPPORTED_CURRENCIES: Dict[str, Dict[str, Any]] = {
    "SOL": {
        "network": "solana",
        "decimals": 9,
        "coingecko_id": "solana",
    },
    "USDC": {
        "network": "solana",
        "decimals": 6,
        "coingecko_id": "usd-coin",
        "stable": True,
        "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    },
    "AGIXT": {
        "network": "solana",
        "decimals": 9,
        "mint": "F9TgEJLLRUKDRF16HgjUCdJfJ5BK6ucyiW8uJxVPpump",
        "dexscreener_token": "F9TgEJLLRUKDRF16HgjUCdJfJ5BK6ucyiW8uJxVPpump",
    },
}


class PriceService:
    """Centralized price conversion utilities with caching."""

    def __init__(self, cache_ttl_seconds: int = 300) -> None:
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        try:
            self.base_price_usd = Decimal(
                str(getenv("MONTHLY_PRICE_PER_USER_USD", "99"))
            )
        except Exception as exc:  # pragma: no cover - defensive conversion guard
            self.base_price_usd = 0.00

    def supported_currencies(self) -> Dict[str, Dict[str, Any]]:
        return SUPPORTED_CURRENCIES

    async def get_quote(self, currency: str, seat_count: int) -> Dict[str, Any]:
        symbol = currency.upper()
        if symbol not in SUPPORTED_CURRENCIES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported currency '{currency}'. Supported: {', '.join(SUPPORTED_CURRENCIES.keys())}",
            )
        if seat_count < 1:
            raise HTTPException(status_code=400, detail="Seat count must be at least 1")

        rate = await self._get_rate(symbol)
        amount_usd = self.base_price_usd * Decimal(seat_count)
        decimals = SUPPORTED_CURRENCIES[symbol]["decimals"]
        amount_currency = self._quantize(amount_usd / rate, decimals)

        return {
            "seat_count": seat_count,
            "currency": symbol,
            "network": SUPPORTED_CURRENCIES[symbol].get("network"),
            "amount_usd": float(self._quantize(amount_usd, 2)),
            "amount_currency": float(amount_currency),
            "exchange_rate": float(self._quantize(rate, 8)),
            "mint": SUPPORTED_CURRENCIES[symbol].get("mint"),
        }

    async def _get_rate(self, symbol: str) -> Decimal:
        now = datetime.now(timezone.utc)
        cached = self._cache.get(symbol)
        if cached and cached["expires_at"] > now:
            return cached["rate"]

        async with self._lock:
            cached = self._cache.get(symbol)
            if cached and cached["expires_at"] > now:
                return cached["rate"]

            rate = await self._fetch_rate(symbol)
            self._cache[symbol] = {
                "rate": rate,
                "expires_at": now + self.cache_ttl,
            }
            return rate

    async def _fetch_rate(self, symbol: str) -> Decimal:
        details = SUPPORTED_CURRENCIES[symbol]

        if details.get("stable"):
            return Decimal("1")

        if "coingecko_id" in details:
            rate = await self._fetch_coingecko_price(details["coingecko_id"])
        elif "dexscreener_token" in details:
            rate = await self._fetch_dexscreener_price(details["dexscreener_token"])
        else:
            raise HTTPException(
                status_code=500, detail=f"No price source configured for {symbol}"
            )

        if rate <= 0:
            raise HTTPException(
                status_code=502, detail=f"Invalid rate received for {symbol}"
            )
        return rate

    async def _fetch_coingecko_price(self, asset_id: str) -> Decimal:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": asset_id, "vs_currencies": "usd"}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise HTTPException(
                status_code=502, detail="Unable to fetch pricing data"
            ) from exc

        price = payload.get(asset_id, {}).get("usd")
        if price is None:
            raise HTTPException(
                status_code=502, detail=f"Price data missing for {asset_id}"
            )
        return Decimal(str(price))

    async def _fetch_dexscreener_price(self, token_address: str) -> Decimal:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise HTTPException(
                status_code=502, detail="Unable to fetch token pricing data"
            ) from exc

        pairs = payload.get("pairs") or []
        if not pairs:
            raise HTTPException(
                status_code=404, detail="Token pricing data not available"
            )
        primary_pair = max(
            pairs, key=lambda pair: float(pair.get("liquidity", {}).get("usd", 0) or 0)
        )
        price = primary_pair.get("priceUsd")
        if price is None:
            raise HTTPException(status_code=502, detail="Token price unavailable")
        return Decimal(str(price))

    @staticmethod
    def _quantize(value: Decimal, decimals: int) -> Decimal:
        quant = Decimal(1).scaleb(-decimals)
        return value.quantize(quant, rounding=ROUND_UP)
