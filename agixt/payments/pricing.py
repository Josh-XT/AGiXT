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
        "mint": "So11111111111111111111111111111111111111111",
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
    "ZEC": {
        "network": "solana",
        "decimals": 8,
        "mint": "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS",
        "dexscreener_token": "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS",
    },
}


class PriceService:
    """Centralized price conversion utilities with caching for token-based billing."""

    def __init__(self, cache_ttl_seconds: int = 300) -> None:
        self.cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def supported_currencies(self) -> Dict[str, Dict[str, Any]]:
        return SUPPORTED_CURRENCIES

    async def get_token_quote(self, token_millions: int) -> Dict[str, Any]:
        """Get quote for token purchase in USD - token_millions is the number of millions of tokens"""
        try:
            token_price_per_million = Decimal(
                str(getenv("TOKEN_PRICE_PER_MILLION_USD"))
            )
        except Exception:
            token_price_per_million = Decimal("0.00")

        # Ensure token price is positive
        if token_price_per_million <= 0:
            # No quote needed
            return {
                "token_millions": token_millions,
                "tokens": token_millions * 1_000_000,
                "amount_usd": 0.00,
                "price_per_million": 0.00,
            }

        min_topup_usd = Decimal(str(getenv("MIN_TOKEN_TOPUP_USD", "10.00")))

        if token_millions < 1:
            raise HTTPException(
                status_code=400, detail="Token amount must be at least 1 million"
            )

        amount_usd = Decimal(token_millions) * token_price_per_million

        if amount_usd < min_topup_usd:
            min_millions = int(
                (min_topup_usd / token_price_per_million).to_integral_value(ROUND_UP)
            )
            raise HTTPException(
                status_code=400,
                detail=f"Minimum top-up is ${float(min_topup_usd)}. Please purchase at least {min_millions}M tokens.",
            )

        return {
            "token_millions": token_millions,
            "tokens": token_millions * 1_000_000,
            "amount_usd": float(self._quantize(amount_usd, 2)),
            "price_per_million": float(token_price_per_million),
        }

    async def get_token_quote_for_currency(
        self, token_millions: int, currency: str
    ) -> Dict[str, Any]:
        """Get quote for token purchase in specific currency"""
        symbol = currency.upper()
        if symbol not in SUPPORTED_CURRENCIES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported currency '{currency}'. Supported: {', '.join(SUPPORTED_CURRENCIES.keys())}",
            )

        # Get USD quote first
        usd_quote = await self.get_token_quote(token_millions)
        amount_usd = Decimal(str(usd_quote["amount_usd"]))

        # Convert to requested currency
        rate = await self._get_rate(symbol)
        decimals = SUPPORTED_CURRENCIES[symbol]["decimals"]
        amount_currency = self._quantize(amount_usd / rate, decimals)

        return {
            "token_millions": token_millions,
            "tokens": token_millions * 1_000_000,
            "currency": symbol,
            "network": SUPPORTED_CURRENCIES[symbol].get("network"),
            "amount_usd": float(usd_quote["amount_usd"]),
            "amount_currency": float(amount_currency),
            "exchange_rate": float(self._quantize(rate, 8)),
            "mint": SUPPORTED_CURRENCIES[symbol].get("mint"),
            "price_per_million_usd": float(usd_quote["price_per_million"]),
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

    def get_token_price(self) -> Decimal:
        """Get the current token price per million USD.

        Returns 0 if billing is paused, otherwise returns the configured price.

        Note: This reads directly from the database to ensure consistency
        across all workers without requiring server restart.
        """
        try:
            # Import here to avoid circular imports
            from DB import get_server_config

            # Check if billing is paused - read directly from DB for consistency
            billing_paused = (
                get_server_config("BILLING_PAUSED", "false") or "false"
            ).lower() == "true"
            if billing_paused:
                return Decimal("0")

            # Read token price directly from DB for consistency across workers
            token_price_str = (
                get_server_config("TOKEN_PRICE_PER_MILLION_USD", "0") or "0"
            )
            token_price = Decimal(str(token_price_str))
            # Return the actual value, including 0 (which means billing disabled)
            return token_price if token_price >= 0 else Decimal("0")
        except Exception:
            return Decimal("0")
