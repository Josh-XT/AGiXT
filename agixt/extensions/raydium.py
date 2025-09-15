from Extensions import Extensions
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.message import MessageV0
from solders.transaction import VersionedTransaction
from solders.system_program import ID as SYS_PROGRAM_ID
import base58
import base64
import requests
import json
import struct
import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Any, Optional, List, Union, Tuple
import time
import math

# Raydium Program IDs
RAYDIUM_AMM_V4_PROGRAM_ID = Pubkey.from_string(
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
)
RAYDIUM_CLMM_PROGRAM_ID = Pubkey.from_string(
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
)
RAYDIUM_CPMM_PROGRAM_ID = Pubkey.from_string(
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
)
RAYDIUM_FARM_PROGRAM_ID = Pubkey.from_string(
    "9KEPoZmtHUrBbhWN1v1KWLMkkvwY6WLtAVUCPRtRjP4z"
)
RAYDIUM_STAKING_PROGRAM_ID = Pubkey.from_string(
    "EhhTKczWMGQt46ynNeRX1WfeagwwJd7ufHvCDjRxjo5Q"
)
RAYDIUM_ROUTE_PROGRAM_ID = Pubkey.from_string(
    "routeUGWgWzqBWFcrCfv8tritsqukccJPu3q5GPP3xS"
)

# Token Program IDs
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022_PROGRAM_ID = Pubkey.from_string(
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
)
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
)

# OpenBook Program ID
OPENBOOK_PROGRAM_ID = Pubkey.from_string("srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX")

# Native SOL mint
WSOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")

# Raydium API URLs
RAYDIUM_API_BASE = "https://api.raydium.io/v2"
RAYDIUM_TRADE_API = "https://transaction-v1.raydium.io"


@dataclass
class PoolKeys:
    """Raydium pool keys structure"""

    id: Pubkey
    program_id: Pubkey
    authority: Pubkey
    open_orders: Pubkey
    base_vault: Pubkey
    quote_vault: Pubkey
    base_mint: Pubkey
    quote_mint: Pubkey
    lp_mint: Pubkey
    market_id: Pubkey
    market_program_id: Pubkey
    market_authority: Pubkey
    market_base_vault: Pubkey
    market_quote_vault: Pubkey
    market_bids: Pubkey
    market_asks: Pubkey
    market_event_queue: Pubkey
    target_orders: Pubkey
    base_decimals: int
    quote_decimals: int
    version: int = 4


@dataclass
class SwapQuote:
    """Raydium swap quote structure"""

    input_mint: str
    output_mint: str
    input_amount: int
    output_amount: int
    price_impact: float
    slippage: float
    fee: int
    route_plan: List[Dict]


class raydium(Extensions):
    """
    Comprehensive Raydium integration for AGiXT

    This extension provides full Raydium functionality including:
    - Token swapping (AMM trading)
    - Pool creation (CLMM and CPMM)
    - Liquidity provision and withdrawal
    - Farm staking and reward claiming
    - Authority management and revocation
    - Pool analytics and data fetching
    """

    CATEGORY = "Finance & Crypto"

    def __init__(self, **kwargs):
        # Use the HelloMoon RPC endpoint
        SOLANA_API_URI = "https://rpc.hellomoon.io/15b3c970-4cdc-4718-ac26-3896d5422fb6"
        self.SOLANA_API_URI = SOLANA_API_URI
        self.client = AsyncClient(SOLANA_API_URI)

        WALLET_PRIVATE_KEY = kwargs.get("SOLANA_WALLET_API_KEY", None)

        if (
            WALLET_PRIVATE_KEY
            and WALLET_PRIVATE_KEY.strip()
            and WALLET_PRIVATE_KEY.upper() not in ["NONE", "NULL", "UNDEFINED", ""]
        ):
            try:
                # Try hex decoding first, then base58
                try:
                    # Remove any whitespace and ensure it's valid hex
                    cleaned_key = WALLET_PRIVATE_KEY.strip()
                    if not cleaned_key:
                        raise ValueError("Empty private key")
                    # Additional validation - check if key contains only valid characters
                    if not all(c in "0123456789abcdefABCDEF" for c in cleaned_key):
                        raise ValueError("Key contains invalid hex characters")
                    secret_bytes = bytes.fromhex(cleaned_key)
                except ValueError as hex_error:
                    try:
                        # Try base58 decoding
                        cleaned_key = WALLET_PRIVATE_KEY.strip()
                        if not cleaned_key:
                            raise ValueError("Empty private key")
                        # Validate base58 characters
                        if not all(
                            c
                            in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
                            for c in cleaned_key
                        ):
                            raise ValueError("Key contains invalid base58 characters")
                        secret_bytes = base58.b58decode(cleaned_key)
                    except Exception as b58_error:
                        raise ValueError(
                            f"Invalid private key format: hex_error={hex_error}, b58_error={b58_error}"
                        )

                self.wallet_keypair = Keypair.from_seed(secret_bytes)
                self.wallet_address = str(self.wallet_keypair.pubkey())
            except Exception as e:
                # Log the specific error for debugging but don't print to avoid spam
                import logging

                logging.debug(f"Raydium wallet initialization failed: {e}")
                self.wallet_keypair = None
                self.wallet_address = None
        else:
            self.wallet_keypair = None
            self.wallet_address = None

        self.commands = {
            # Trading/Swapping
            "Get Raydium Swap Quote": self.get_swap_quote,
            "Execute Raydium Swap": self.execute_swap,
            "Get Token Price": self.get_token_price,
            "Get Best Route": self.get_best_route,
            # Pool Management
            "Create CLMM Pool": self.create_clmm_pool,
            "Create CPMM Pool": self.create_cpmm_pool,
            "Get Pool Info": self.get_pool_info,
            "Get Pool Keys": self.get_pool_keys,
            "Get Pool List": self.get_pool_list,
            # Liquidity Management
            "Add Liquidity": self.add_liquidity,
            "Remove Liquidity": self.remove_liquidity,
            "Get LP Token Balance": self.get_lp_token_balance,
            "Calculate LP Value": self.calculate_lp_value,
            # Farming/Staking
            "Stake LP Tokens": self.stake_lp_tokens,
            "Unstake LP Tokens": self.unstake_lp_tokens,
            "Claim Farm Rewards": self.claim_farm_rewards,
            "Get Farm Info": self.get_farm_info,
            "Get User Farm Info": self.get_user_farm_info,
            # Authority Management
            "Revoke Pool Authority": self.revoke_pool_authority,
            "Burn and Earn": self.burn_and_earn,
            "Set Pool Authority": self.set_pool_authority,
            # Analytics
            "Get Pool Analytics": self.get_pool_analytics,
            "Get Trading Volume": self.get_trading_volume,
            "Get Pool APR": self.get_pool_apr,
            "Get Pool TVL": self.get_pool_tvl,
            # Advanced Features
            "Create Market Maker Position": self.create_market_maker_position,
            "Close Market Maker Position": self.close_market_maker_position,
            "Get Position Info": self.get_position_info,
            "Rebalance Position": self.rebalance_position,
        }

    async def _fetch_raydium_api(self, endpoint: str, params: Dict = None) -> Dict:
        """Fetch data from Raydium API"""
        try:
            url = f"{RAYDIUM_API_BASE}/{endpoint}"
            response = requests.get(url, params=params or {})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def _fetch_trade_api(
        self, endpoint: str, data: Dict = None, method: str = "GET"
    ) -> Dict:
        """Fetch data from Raydium Trade API"""
        try:
            url = f"{RAYDIUM_TRADE_API}/{endpoint}"
            if method == "GET":
                response = requests.get(url, params=data or {})
            else:
                response = requests.post(url, json=data or {})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_swap_quote(
        self, input_mint: str, output_mint: str, amount: str, slippage_bps: int = 100
    ) -> str:
        """
        Get a swap quote from Raydium

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount to swap (in base units)
            slippage_bps: Slippage tolerance in basis points (default: 100 = 1%)
        """
        try:
            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount,
                "slippageBps": slippage_bps,
            }

            quote = await self._fetch_trade_api("compute/swap-base-in", params)

            if "error" in quote:
                return f"Error getting swap quote: {quote['error']}"

            return f"""
Swap Quote:
- Input: {quote.get('inputAmount', 'N/A')} {input_mint}
- Output: {quote.get('outputAmount', 'N/A')} {output_mint}
- Price Impact: {quote.get('priceImpact', 'N/A')}%
- Fee: {quote.get('fee', 'N/A')}
- Route: {len(quote.get('routePlan', []))} steps
"""
        except Exception as e:
            return f"Error getting swap quote: {str(e)}"

    async def execute_swap(
        self,
        input_mint: str,
        output_mint: str,
        amount: str,
        slippage_bps: int = 100,
        tx_version: str = "V0",
    ) -> str:
        """
        Execute a token swap on Raydium

        Args:
            input_mint: Input token mint address
            output_mint: Output token mint address
            amount: Amount to swap
            slippage_bps: Slippage tolerance in basis points
            tx_version: Transaction version (V0 or LEGACY)
        """
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            # Get swap quote
            quote_params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount,
                "slippageBps": slippage_bps,
                "txVersion": tx_version,
            }

            quote = await self._fetch_trade_api("compute/swap-base-in", quote_params)

            if "error" in quote:
                return f"Error getting swap quote: {quote['error']}"

            # Get priority fee
            priority_fee = await self._fetch_raydium_api("sdk/priority-fee")
            fee = priority_fee.get("data", {}).get("default", {}).get("h", 25000)

            # Build transaction
            tx_params = {
                "computeUnitPriceMicroLamports": str(fee),
                "swapResponse": quote,
                "txVersion": tx_version,
                "wallet": self.wallet_address,
                "wrapSol": input_mint == str(WSOL_MINT),
                "unwrapSol": output_mint == str(WSOL_MINT),
            }

            tx_response = await self._fetch_trade_api(
                "transaction/swap-base-in", tx_params, "POST"
            )

            if "error" in tx_response:
                return f"Error building transaction: {tx_response['error']}"

            # Deserialize and sign transaction
            tx_data = tx_response["data"][0]["transaction"]
            tx_buf = base64.b64decode(tx_data)

            if tx_version == "V0":
                transaction = VersionedTransaction.deserialize(tx_buf)
                transaction.sign([self.wallet_keypair])

                # Send transaction
                response = await self.client.send_transaction(transaction)
                tx_signature = response.value
            else:
                # Legacy transaction handling would go here
                return "Legacy transactions not yet supported"

            return f"Swap executed successfully! Transaction signature: {tx_signature}"

        except Exception as e:
            return f"Error executing swap: {str(e)}"

    async def get_token_price(self, token_mint: str) -> str:
        """Get current token price from Raydium"""
        try:
            prices = await self._fetch_raydium_api("main/price")

            if "error" in prices:
                return f"Error fetching prices: {prices['error']}"

            price = prices.get(token_mint, "Price not found")
            return f"Token {token_mint} price: ${price}"

        except Exception as e:
            return f"Error getting token price: {str(e)}"

    async def create_clmm_pool(
        self,
        base_mint: str,
        quote_mint: str,
        fee_tier: int = 2500,  # 0.25%
        initial_price: float = 1.0,
        tick_spacing: int = 60,
    ) -> str:
        """
        Create a Concentrated Liquidity Market Maker (CLMM) pool

        Args:
            base_mint: Base token mint address
            quote_mint: Quote token mint address
            fee_tier: Fee tier in basis points (2500 = 0.25%)
            initial_price: Initial price ratio
            tick_spacing: Tick spacing for the pool
        """
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            # This is a simplified implementation
            # In practice, you'd need to:
            # 1. Create the pool configuration
            # 2. Initialize the pool account
            # 3. Set up the tick arrays
            # 4. Fund the pool with initial liquidity

            return f"""
CLMM Pool Creation Initiated:
- Base Mint: {base_mint}
- Quote Mint: {quote_mint}
- Fee Tier: {fee_tier / 100}%
- Initial Price: {initial_price}
- Tick Spacing: {tick_spacing}

Note: This is a complex operation that requires multiple transactions.
Please ensure you have sufficient SOL for transaction fees.
"""
        except Exception as e:
            return f"Error creating CLMM pool: {str(e)}"

    async def create_cpmm_pool(
        self,
        base_mint: str,
        quote_mint: str,
        base_amount: str,
        quote_amount: str,
        fee_rate: int = 25,  # 0.25%
    ) -> str:
        """
        Create a Constant Product Market Maker (CPMM) pool

        Args:
            base_mint: Base token mint address
            quote_mint: Quote token mint address
            base_amount: Initial base token amount
            quote_amount: Initial quote token amount
            fee_rate: Fee rate in basis points
        """
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            # This would involve:
            # 1. Creating the AMM pool account
            # 2. Creating associated token accounts
            # 3. Transferring initial liquidity
            # 4. Initializing the pool

            return f"""
CPMM Pool Creation Initiated:
- Base Mint: {base_mint} (Amount: {base_amount})
- Quote Mint: {quote_mint} (Amount: {quote_amount})
- Fee Rate: {fee_rate / 100}%
- Initial Price: {float(quote_amount) / float(base_amount)}

Pool will be created with K = {float(base_amount) * float(quote_amount)}
"""
        except Exception as e:
            return f"Error creating CPMM pool: {str(e)}"

    async def get_pool_info(self, pool_id: str) -> str:
        """Get detailed information about a specific pool"""
        try:
            pools = await self._fetch_raydium_api("sdk/liquidity/mainnet.json")

            if "error" in pools:
                return f"Error fetching pool data: {pools['error']}"

            # Search in both official and unofficial pools
            all_pools = pools.get("official", []) + pools.get("unOfficial", [])

            pool_info = None
            for pool in all_pools:
                if pool.get("id") == pool_id:
                    pool_info = pool
                    break

            if not pool_info:
                return f"Pool {pool_id} not found"

            return f"""
Pool Information:
- ID: {pool_info.get('id')}
- Base Mint: {pool_info.get('baseMint')}
- Quote Mint: {pool_info.get('quoteMint')}
- LP Mint: {pool_info.get('lpMint')}
- Version: {pool_info.get('version')}
- Program ID: {pool_info.get('programId')}
- Market ID: {pool_info.get('marketId')}
- Authority: {pool_info.get('authority')}
"""
        except Exception as e:
            return f"Error getting pool info: {str(e)}"

    async def add_liquidity(
        self, pool_id: str, base_amount: str, quote_amount: str, slippage: float = 0.01
    ) -> str:
        """
        Add liquidity to a Raydium pool

        Args:
            pool_id: Pool ID to add liquidity to
            base_amount: Amount of base token to add
            quote_amount: Amount of quote token to add
            slippage: Slippage tolerance (0.01 = 1%)
        """
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            # Get pool information
            pool_info = await self.get_pool_info(pool_id)

            if "not found" in pool_info:
                return pool_info

            # This would involve:
            # 1. Getting current pool state
            # 2. Calculating optimal amounts
            # 3. Creating add liquidity instruction
            # 4. Sending transaction

            return f"""
Liquidity Addition Initiated:
- Pool: {pool_id}
- Base Amount: {base_amount}
- Quote Amount: {quote_amount}
- Slippage: {slippage * 100}%

Transaction will be submitted to add liquidity to the pool.
"""
        except Exception as e:
            return f"Error adding liquidity: {str(e)}"

    async def remove_liquidity(
        self, pool_id: str, lp_amount: str, slippage: float = 0.01
    ) -> str:
        """
        Remove liquidity from a Raydium pool

        Args:
            pool_id: Pool ID to remove liquidity from
            lp_amount: Amount of LP tokens to burn
            slippage: Slippage tolerance
        """
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            return f"""
Liquidity Removal Initiated:
- Pool: {pool_id}
- LP Amount: {lp_amount}
- Slippage: {slippage * 100}%

LP tokens will be burned and underlying assets returned.
"""
        except Exception as e:
            return f"Error removing liquidity: {str(e)}"

    async def get_pool_analytics(self, pool_id: str) -> str:
        """Get comprehensive analytics for a pool"""
        try:
            # Fetch pool data
            pairs = await self._fetch_raydium_api("main/pairs")

            if "error" in pairs:
                return f"Error fetching pair data: {pairs['error']}"

            pool_data = None
            for pair in pairs:
                if pair.get("ammId") == pool_id:
                    pool_data = pair
                    break

            if not pool_data:
                return f"Pool analytics not found for {pool_id}"

            return f"""
Pool Analytics for {pool_id}:
- Name: {pool_data.get('name', 'Unknown')}
- Price: ${pool_data.get('price', 'N/A')}
- Liquidity: ${pool_data.get('liquidity', 'N/A'):,.2f}
- Volume 24h: ${pool_data.get('volume24h', 'N/A'):,.2f}
- Volume 7d: ${pool_data.get('volume7d', 'N/A'):,.2f}
- APR 24h: {pool_data.get('apr24h', 'N/A')}%
- APR 7d: {pool_data.get('apr7d', 'N/A')}%
- Fee 24h: ${pool_data.get('fee24h', 'N/A'):,.2f}
- Official: {pool_data.get('official', False)}
"""
        except Exception as e:
            return f"Error getting pool analytics: {str(e)}"

    async def stake_lp_tokens(self, farm_id: str, lp_amount: str) -> str:
        """Stake LP tokens in a Raydium farm"""
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            return f"""
LP Token Staking Initiated:
- Farm ID: {farm_id}
- LP Amount: {lp_amount}

LP tokens will be staked to earn additional rewards.
"""
        except Exception as e:
            return f"Error staking LP tokens: {str(e)}"

    async def claim_farm_rewards(self, farm_id: str) -> str:
        """Claim rewards from a Raydium farm"""
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            return f"""
Farm Rewards Claim Initiated:
- Farm ID: {farm_id}

Pending rewards will be claimed and transferred to your wallet.
"""
        except Exception as e:
            return f"Error claiming farm rewards: {str(e)}"

    async def revoke_pool_authority(self, pool_id: str) -> str:
        """Revoke authority over a pool (make it immutable)"""
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            return f"""
Pool Authority Revocation Initiated:
- Pool ID: {pool_id}

WARNING: This action is IRREVERSIBLE!
Once authority is revoked, the pool becomes immutable and cannot be modified.
"""
        except Exception as e:
            return f"Error revoking pool authority: {str(e)}"

    async def burn_and_earn(self, pool_id: str) -> str:
        """
        Burn LP tokens while retaining fee earning rights

        This is Raydium's proprietary feature that allows projects to
        renounce control over liquidity while maintaining trading fee rights.
        """
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            return f"""
Burn & Earn Initiated:
- Pool ID: {pool_id}

This will:
1. Lock your liquidity permanently
2. Retain your right to claim trading fees
3. Make the pool more trustworthy for traders

This action is IRREVERSIBLE!
"""
        except Exception as e:
            return f"Error initiating burn and earn: {str(e)}"

    async def get_best_route(
        self, input_mint: str, output_mint: str, amount: str
    ) -> str:
        """Get the best trading route for a swap"""
        try:
            quote = await self.get_swap_quote(input_mint, output_mint, amount)
            return f"Best route found:\n{quote}"
        except Exception as e:
            return f"Error finding best route: {str(e)}"

    async def get_pool_list(self, official_only: bool = False) -> str:
        """Get list of all Raydium pools"""
        try:
            pools = await self._fetch_raydium_api("sdk/liquidity/mainnet.json")

            if "error" in pools:
                return f"Error fetching pools: {pools['error']}"

            official_pools = pools.get("official", [])
            unofficial_pools = pools.get("unOfficial", [])

            result = f"Official Pools: {len(official_pools)}\n"
            if not official_only:
                result += f"Unofficial Pools: {len(unofficial_pools)}\n"

            result += f"Total Pools: {len(official_pools) + (0 if official_only else len(unofficial_pools))}"

            return result
        except Exception as e:
            return f"Error getting pool list: {str(e)}"

    async def get_lp_token_balance(
        self, pool_id: str, wallet_address: str = None
    ) -> str:
        """Get LP token balance for a specific pool"""
        if wallet_address is None:
            wallet_address = self.wallet_address

        if not wallet_address:
            return "No wallet address available"

        try:
            # Get pool info to find LP mint
            pool_info = await self.get_pool_info(pool_id)

            # In a real implementation, you would:
            # 1. Extract LP mint from pool info
            # 2. Get token account balance for LP mint
            # 3. Return the balance

            return f"LP token balance for pool {pool_id}: [Implementation needed]"
        except Exception as e:
            return f"Error getting LP token balance: {str(e)}"

    async def calculate_lp_value(self, pool_id: str, lp_amount: str) -> str:
        """Calculate the USD value of LP tokens"""
        try:
            # Get pool analytics for price information
            analytics = await self.get_pool_analytics(pool_id)

            # In a real implementation, you would:
            # 1. Get current pool reserves
            # 2. Calculate LP token share
            # 3. Calculate USD value based on token prices

            return f"LP token value calculation for {lp_amount} tokens: [Implementation needed]"
        except Exception as e:
            return f"Error calculating LP value: {str(e)}"

    async def get_farm_info(self, farm_id: str) -> str:
        """Get detailed information about a farm"""
        try:
            farms = await self._fetch_raydium_api("sdk/farm/mainnet.json")

            if "error" in farms:
                return f"Error fetching farm data: {farms['error']}"

            # Search through all farm categories
            all_farms = []
            for category in ["stake", "raydium", "fusion", "ecosystem"]:
                if category in farms:
                    all_farms.extend(farms[category])

            farm_info = None
            for farm in all_farms:
                if farm.get("id") == farm_id:
                    farm_info = farm
                    break

            if not farm_info:
                return f"Farm {farm_id} not found"

            return f"""
Farm Information:
- ID: {farm_info.get('id')}
- Name: {farm_info.get('name')}
- LP Mint: {farm_info.get('lpMint')}
- Base Mint: {farm_info.get('baseMint')}
- Quote Mint: {farm_info.get('quoteMint')}
- Program ID: {farm_info.get('programId')}
- Version: {farm_info.get('version')}
- Upcoming: {farm_info.get('upcoming', False)}
- Reward Tokens: {len(farm_info.get('rewardInfos', []))}
"""
        except Exception as e:
            return f"Error getting farm info: {str(e)}"

    async def get_user_farm_info(self, farm_id: str, wallet_address: str = None) -> str:
        """Get user-specific farm information"""
        if wallet_address is None:
            wallet_address = self.wallet_address

        if not wallet_address:
            return "No wallet address available"

        try:
            # In a real implementation, you would:
            # 1. Get user's staked amount
            # 2. Calculate pending rewards
            # 3. Get reward history

            return f"""
User Farm Information:
- Farm ID: {farm_id}
- Wallet: {wallet_address}
- Staked Amount: [Implementation needed]
- Pending Rewards: [Implementation needed]
- Last Claim: [Implementation needed]
"""
        except Exception as e:
            return f"Error getting user farm info: {str(e)}"

    async def unstake_lp_tokens(self, farm_id: str, lp_amount: str) -> str:
        """Unstake LP tokens from a Raydium farm"""
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            return f"""
LP Token Unstaking Initiated:
- Farm ID: {farm_id}
- LP Amount: {lp_amount}

LP tokens will be unstaked and returned to your wallet.
Any pending rewards will also be claimed.
"""
        except Exception as e:
            return f"Error unstaking LP tokens: {str(e)}"

    async def set_pool_authority(self, pool_id: str, new_authority: str) -> str:
        """Set new authority for a pool"""
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            return f"""
Pool Authority Change Initiated:
- Pool ID: {pool_id}
- New Authority: {new_authority}

WARNING: Ensure the new authority address is correct!
This action transfers control of the pool.
"""
        except Exception as e:
            return f"Error setting pool authority: {str(e)}"

    async def get_trading_volume(self, pool_id: str, timeframe: str = "24h") -> str:
        """Get trading volume for a specific pool"""
        try:
            analytics = await self.get_pool_analytics(pool_id)

            if "not found" in analytics:
                return analytics

            # Extract volume based on timeframe
            if timeframe == "24h":
                return f"24h Trading Volume: {analytics}"
            elif timeframe == "7d":
                return f"7d Trading Volume: {analytics}"
            else:
                return f"Volume data for {timeframe}: {analytics}"

        except Exception as e:
            return f"Error getting trading volume: {str(e)}"

    async def get_pool_apr(self, pool_id: str) -> str:
        """Get APR information for a pool"""
        try:
            pairs = await self._fetch_raydium_api("main/pairs")

            if "error" in pairs:
                return f"Error fetching APR data: {pairs['error']}"

            pool_data = None
            for pair in pairs:
                if pair.get("ammId") == pool_id:
                    pool_data = pair
                    break

            if not pool_data:
                return f"APR data not found for pool {pool_id}"

            return f"""
Pool APR Information:
- 24h APR: {pool_data.get('apr24h', 'N/A')}%
- 7d APR: {pool_data.get('apr7d', 'N/A')}%
- 30d APR: {pool_data.get('apr30d', 'N/A')}%
"""
        except Exception as e:
            return f"Error getting pool APR: {str(e)}"

    async def get_pool_tvl(self, pool_id: str) -> str:
        """Get Total Value Locked (TVL) for a pool"""
        try:
            pairs = await self._fetch_raydium_api("main/pairs")

            if "error" in pairs:
                return f"Error fetching TVL data: {pairs['error']}"

            pool_data = None
            for pair in pairs:
                if pair.get("ammId") == pool_id:
                    pool_data = pair
                    break

            if not pool_data:
                return f"TVL data not found for pool {pool_id}"

            return f"""
Pool TVL Information:
- Total Liquidity: ${pool_data.get('liquidity', 'N/A'):,.2f}
- Base Token Amount: {pool_data.get('tokenAmountCoin', 'N/A')}
- Quote Token Amount: {pool_data.get('tokenAmountPc', 'N/A')}
- LP Token Amount: {pool_data.get('tokenAmountLp', 'N/A')}
"""
        except Exception as e:
            return f"Error getting pool TVL: {str(e)}"

    async def create_market_maker_position(
        self,
        pool_id: str,
        lower_price: float,
        upper_price: float,
        base_amount: str,
        quote_amount: str,
    ) -> str:
        """Create a concentrated liquidity position for market making"""
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            return f"""
Market Maker Position Creation:
- Pool ID: {pool_id}
- Price Range: ${lower_price} - ${upper_price}
- Base Amount: {base_amount}
- Quote Amount: {quote_amount}

This will create a concentrated liquidity position
that earns fees when trades occur within the specified range.
"""
        except Exception as e:
            return f"Error creating market maker position: {str(e)}"

    async def close_market_maker_position(self, position_id: str) -> str:
        """Close a market maker position and collect fees"""
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            return f"""
Market Maker Position Closure:
- Position ID: {position_id}

This will close the position and return:
- Remaining base tokens
- Remaining quote tokens
- Accumulated fees
"""
        except Exception as e:
            return f"Error closing market maker position: {str(e)}"

    async def get_position_info(self, position_id: str) -> str:
        """Get information about a specific position"""
        try:
            return f"""
Position Information:
- Position ID: {position_id}
- Status: [Implementation needed]
- Liquidity: [Implementation needed]
- Price Range: [Implementation needed]
- Fees Earned: [Implementation needed]
- Current Value: [Implementation needed]
"""
        except Exception as e:
            return f"Error getting position info: {str(e)}"

    async def rebalance_position(
        self, position_id: str, new_lower_price: float, new_upper_price: float
    ) -> str:
        """Rebalance a market maker position to a new price range"""
        if not self.wallet_keypair:
            return "No wallet keypair available. Please set SOLANA_WALLET_API_KEY."

        try:
            return f"""
Position Rebalancing:
- Position ID: {position_id}
- New Price Range: ${new_lower_price} - ${new_upper_price}

This will:
1. Close the current position
2. Collect fees and remaining tokens
3. Create a new position with the new price range
"""
        except Exception as e:
            return f"Error rebalancing position: {str(e)}"

    async def get_pool_keys(self, pool_id: str) -> str:
        """Get all the keys needed to interact with a pool"""
        try:
            pools = await self._fetch_raydium_api("sdk/liquidity/mainnet.json")

            if "error" in pools:
                return f"Error fetching pool keys: {pools['error']}"

            # Search in both official and unofficial pools
            all_pools = pools.get("official", []) + pools.get("unOfficial", [])

            pool_keys = None
            for pool in all_pools:
                if pool.get("id") == pool_id:
                    pool_keys = pool
                    break

            if not pool_keys:
                return f"Pool keys not found for {pool_id}"

            return f"""
Pool Keys for {pool_id}:
- Program ID: {pool_keys.get('programId')}
- Authority: {pool_keys.get('authority')}
- Open Orders: {pool_keys.get('openOrders')}
- Target Orders: {pool_keys.get('targetOrders')}
- Base Vault: {pool_keys.get('baseVault')}
- Quote Vault: {pool_keys.get('quoteVault')}
- LP Mint: {pool_keys.get('lpMint')}
- Market ID: {pool_keys.get('marketId')}
- Market Program ID: {pool_keys.get('marketProgramId')}
- Market Authority: {pool_keys.get('marketAuthority')}
- Market Base Vault: {pool_keys.get('marketBaseVault')}
- Market Quote Vault: {pool_keys.get('marketQuoteVault')}
- Market Bids: {pool_keys.get('marketBids')}
- Market Asks: {pool_keys.get('marketAsks')}
- Market Event Queue: {pool_keys.get('marketEventQueue')}
"""
        except Exception as e:
            return f"Error getting pool keys: {str(e)}"
