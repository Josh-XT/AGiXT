from Extensions import Extensions
import json
from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solders.transaction import Transaction
from solders.keypair import Keypair
from solders.system_program import TransferParams, transfer
from solders.pubkey import Pubkey
from solders.instruction import Instruction
from solders.system_program import ID as SYS_PROGRAM_ID
from typing import Dict, Any, Optional, Tuple, List
import base58
import requests
import struct
from dataclasses import dataclass
from decimal import Decimal
from solana.rpc.api import Client
from solana.rpc.commitment import Confirmed
from solders.transaction import Transaction
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.system_program import transfer
from solana.rpc.types import TxOpts
import requests, asyncio
import json
from typing import List, Dict, Optional, Any


# Define TOKEN_PROGRAM_ID (this is a well-known address in Solana)
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")


class solana_wallet(Extensions):
    """
    The SolanaWallets extension enables interaction with Solana blockchain wallets using the solana‑py SDK.
    This implementation uses the new solders‑based imports for keypairs, public keys, and system instructions.

    The extension supports creating wallets, checking balances, sending SOL, and more.
    """

    # Raydium SDK constants
    RAYDIUM_ROUTER_ID = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")  # Raydium Router Program ID
    POOL_STATE_VERSION_V1 = 1
    AMM_PROGRAM_ID = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
    SERUM_PROGRAM_ID = Pubkey.from_string("9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin")
    
    @dataclass
    class PoolInfo:
        address: Pubkey
        input_reserve: int
        output_reserve: int
        input_decimals: int
        fee_numerator: int
        fee_denominator: int
        
    async def _get_token_decimals(self, token: Pubkey) -> int:
        """Get token decimals from mint account"""
        try:
            token_info = await self.client.get_account_info(token)
            if not token_info["result"]["value"]:
                return 9  # Default to 9 decimals if not found
            
            data = base58.b58decode(token_info["result"]["value"]["data"][0])
            # Parse mint account data (decimals at offset 44)
            decimals = data[44]
            return decimals
        except Exception:
            return 9  # Default to 9 decimals on error
            
    async def _get_pool_info(self, input_token: Pubkey, output_token: Pubkey) -> Optional[Dict]:
        """Get pool information for a token pair"""
        try:
            # Derive pool address using SDK algorithm
            seeds = [
                bytes("amm_pool", "utf-8"),
                bytes(input_token),
                bytes(output_token)
            ]
            pool_address, _ = Pubkey.find_program_address(seeds, self.AMM_PROGRAM_ID)
            
            # Get pool account data
            pool_data = await self.client.get_account_info(pool_address)
            if not pool_data["result"]["value"]:
                return None
                
            # Parse pool state data
            data = base58.b58decode(pool_data["result"]["value"]["data"][0])
            
            # Extract pool info from data using similar structure as SDK
            (version, status, nonce, token_a, token_b, reserve_a, 
             reserve_b, fee_numerator, fee_denominator) = struct.unpack("<BBQQQQQQQ", data[:73])
             
            return {
                "address": str(pool_address),
                "input_reserve": reserve_a if input_token == token_a else reserve_b,
                "output_reserve": reserve_b if input_token == token_a else reserve_a,
                "input_decimals": await self._get_token_decimals(input_token),
                "fee_numerator": fee_numerator,
                "fee_denominator": fee_denominator
            }
        except Exception as e:
            print(f"Error getting pool info: {str(e)}")
            return None
            
    def _compute_output_amount(self, input_amount: int, input_reserve: int, 
                             output_reserve: int, fee_numerator: int, 
                             fee_denominator: int) -> int:
        """Compute output amount based on Raydium's constant product formula"""
        fee_amount = (input_amount * fee_numerator) // fee_denominator
        amount_with_fee = input_amount - fee_amount
        numerator = amount_with_fee * output_reserve
        denominator = input_reserve + amount_with_fee
        return numerator // denominator if denominator != 0 else 0
        
    def _calculate_price_impact(self, input_amount: int, output_amount: int,
                              input_reserve: int, output_reserve: int) -> float:
        """Calculate price impact of a swap"""
        price_before = Decimal(output_reserve) / Decimal(input_reserve)
        price_after = Decimal(output_amount) / Decimal(input_amount)
        price_impact = abs((price_before - price_after) / price_before) * 100
        return float(price_impact)
    
    def __init__(
        self,
        **kwargs,
    ):
        RAYDIUM_API_URI = "https://api.raydium.io"
        SOLANA_API_URI = "https://api.mainnet-beta.solana.com"
        self.RAYDIUM_API_URI = RAYDIUM_API_URI
        self.WSOL_MINT = "So11111111111111111111111111111111111111112"
        self.SOLANA_API_URI = SOLANA_API_URI
        self.client = Client(SOLANA_API_URI)
        WALLET_PRIVATE_KEY = kwargs.get("SOLANA_WALLET_API_KEY", None)

        # If an existing wallet private key is provided, load the keypair
        if WALLET_PRIVATE_KEY:
            # Convert hex string to bytes and create keypair
            # Use from_seed to create keypair from just the secret key
            secret_bytes = bytes.fromhex(WALLET_PRIVATE_KEY)
            self.wallet_keypair = Keypair.from_seed(secret_bytes)
            self.wallet_address = str(self.wallet_keypair.pubkey())
        else:
            self.wallet_keypair = None
            self.wallet_address = None

        self.commands = {
            "Get Solana Wallet Balance": self.get_wallet_balance,
            "Send SOL": self.send_sol,
            "Get Transaction Info": self.get_transaction_info,
            "Get Recent Transactions": self.get_recent_transactions,
            "Get Solana Token Balance": self.get_token_balance,
            "Airdrop SOL": self.airdrop_sol,
            "Get Token Swap Quote": self.get_swap_quote,
            "Execute Token Swap": self.execute_swap,
            "Get Token List": self.get_token_list,
            "Get Token Price": self.get_token_price,
            "Get Wallet Token Accounts": self.get_wallet_token_accounts,
            "Get Route Quote": self.get_route_quote,
            "Execute Trade": self.execute_trade,
            "Get Public Key": self.get_public_key,
        }

    async def create_wallet(self):
        """
        Creates a new Solana wallet by generating a new keypair.
        This method can be used if no wallet was connected via the init params.
        """
        new_keypair = Keypair()
        self.wallet_keypair = new_keypair
        self.wallet_address = str(new_keypair.pubkey())
        # Get the secret key as bytes and convert to hex
        secret_hex = new_keypair.secret().hex()
        return (
            f"Created new Solana wallet.\n"
            f"Public Key: {self.wallet_address}\n"
            f"Secret Key (hex): {secret_hex}"
        )

    async def get_wallet_balance(self, wallet_address: str = None):
        """
        Retrieves the SOL balance for the given wallet address.
        If no address is provided, uses the wallet address from initialization.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if wallet_address is None:
            return "No wallet address specified."
        try:
            # Convert the wallet address string to a Pubkey object
            response = self.client.get_balance(Pubkey.from_string(wallet_address))
            balance_lamports = response["result"]["value"]
            sol_balance = balance_lamports / 1e9
            return f"Wallet {wallet_address} balance: {sol_balance} SOL."
        except Exception as e:
            return f"Error retrieving balance: {str(e)}"

    async def send_sol(
        self, from_wallet: str = None, to_wallet: str = "", amount: float = 0.0
    ):
        """
        Sends a specified amount of SOL (in SOL units) from one wallet to another.
        Uses self.wallet_keypair for signing if from_wallet is not provided.
        """
        if from_wallet is None:
            from_wallet = self.wallet_address
        if from_wallet is None or self.wallet_keypair is None:
            return "No sender wallet or keypair available."
        try:
            lamports_amount = int(amount * 1e9)
            tx = Transaction()
            tx.add(
                transfer(
                    from_pubkey=Pubkey.from_string(from_wallet),
                    to_pubkey=Pubkey.from_string(to_wallet),
                    lamports=lamports_amount,
                )
            )
            response = self.client.send_transaction(tx, self.wallet_keypair)
            return f"Transaction submitted: {response.get('result')}"
        except Exception as e:
            return f"Error sending SOL: {str(e)}"

    async def get_transaction_info(self, tx_signature: str):
        """
        Retrieves information about a specific transaction using its signature.
        """
        try:
            response = self.client.get_confirmed_transaction(tx_signature)
            return f"Transaction info: {response}"
        except Exception as e:
            return f"Error retrieving transaction info: {str(e)}"

    async def get_recent_transactions(
        self, wallet_address: str = None, limit: int = 10
    ):
        """
        Retrieves the most recent transaction signatures for the given wallet address.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if wallet_address is None:
            return "No wallet address specified."
        try:
            response = self.client.get_signatures_for_address(
                Pubkey.from_string(wallet_address), limit=limit
            )
            return f"Recent transactions for wallet {wallet_address}: {response.get('result')}"
        except Exception as e:
            return f"Error retrieving recent transactions: {str(e)}"

    async def get_token_balance(self, wallet_address: str = None, token_mint: str = ""):
        """
        Retrieves the balance of a specific SPL token for the given wallet.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        return f"Token balance for token {token_mint} in wallet {wallet_address}: [Not implemented]."

    async def airdrop_sol(self, wallet_address: str = None, amount: float = 0.0):
        """
        Requests an airdrop of SOL (on devnet) to the specified wallet address.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if wallet_address is None:
            return "No wallet address specified."
        try:
            lamports_amount = int(amount * 1e9)
            response = self.client.request_airdrop(
                Pubkey.from_string(wallet_address), lamports_amount
            )
            return f"Airdrop requested: {response.get('result')}"
        except Exception as e:
            return f"Error requesting airdrop: {str(e)}"

    async def get_swap_quote(self, from_token: str, to_token: str, amount: float):
        """
        Retrieves a quote for swapping one token to another using Raydium SDK computations.
        """
        try:
            # Convert token addresses to Pubkey objects
            input_token = Pubkey.from_string(from_token)
            output_token = Pubkey.from_string(to_token)
            
            # Get pool info for the token pair
            pool_info = await self._get_pool_info(input_token, output_token)
            if not pool_info:
                return f"No pool found for {from_token} -> {to_token}"
            
            # Calculate amounts using pool reserves and weights
            input_amount = int(amount * 10**pool_info["input_decimals"])
            output_amount = self._compute_output_amount(
                input_amount,
                pool_info["input_reserve"],
                pool_info["output_reserve"],
                pool_info["fee_numerator"],
                pool_info["fee_denominator"]
            )
            
            # Calculate price impact
            price_impact = self._calculate_price_impact(
                input_amount,
                output_amount,
                pool_info["input_reserve"],
                pool_info["output_reserve"]
            )
            
            return {
                "inputAmount": str(input_amount),
                "outputAmount": str(output_amount),
                "priceImpact": price_impact,
                "pool": pool_info["address"]
            }
        except Exception as e:
            return f"Error getting swap quote: {str(e)}"

    async def execute_swap(
        self,
        wallet_address: str = None,
        quote: Dict[str, Any] = None,
        amount: float = 0.0,
    ):
        """
        Executes a token swap using Raydium SDK instructions.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if not quote:
            return "No quote provided for swap"
            
        try:
            # Build swap instruction
            pool_address = Pubkey.from_string(quote["pool"])
            wallet_pubkey = Pubkey.from_string(wallet_address)
            
            swap_instruction = self._build_swap_instruction(
                pool_address,
                wallet_pubkey,
                int(quote["inputAmount"]),
                int(quote["outputAmount"])
            )
            
            # Create and sign transaction
            recent_blockhash = await self.client.get_recent_blockhash()
            tx = Transaction()
            tx.recent_blockhash = recent_blockhash["result"]["value"]["blockhash"]
            tx.add(swap_instruction)
            
            # Send transaction
            opts = TxOpts(skip_preflight=False)
            response = await self.client.send_transaction(tx, self.wallet_keypair, opts=opts)
            
            return {
                "success": True,
                "signature": response["result"],
                "inputAmount": quote["inputAmount"],
                "outputAmount": quote["outputAmount"]
            }
        except Exception as e:
            return f"Error executing swap: {str(e)}"
            
    def _build_swap_instruction(self, pool: Pubkey, wallet: Pubkey, 
                              input_amount: int, min_output: int) -> Instruction:
        """Build Raydium swap instruction"""
        keys = [
            {"pubkey": pool, "isSigner": False, "isWritable": True},
            {"pubkey": wallet, "isSigner": True, "isWritable": True},
            {"pubkey": TOKEN_PROGRAM_ID, "isSigner": False, "isWritable": False},
            {"pubkey": self.AMM_PROGRAM_ID, "isSigner": False, "isWritable": False}
        ]
        
        # Swap instruction data layout matches Raydium SDK
        instruction_data = struct.pack("<BQQ", 
                                     9,  # Swap instruction code
                                     input_amount,  # Input amount 
                                     min_output)  # Minimum output amount
        
        return Instruction(
            program_id=self.AMM_PROGRAM_ID,
            data=instruction_data,
            accounts=keys
        )
            
    async def get_route_quote(self, from_token: str, to_token: str, amount: float):
        """
        Get a quote for the best trading route between two tokens using SDK computations.
        """
        try:
            input_token = Pubkey.from_string(from_token)
            output_token = Pubkey.from_string(to_token)
            
            # First try direct pool
            direct_quote = await self.get_swap_quote(from_token, to_token, amount)
            if not isinstance(direct_quote, str):  # Not an error message
                return {
                    "route": [{
                        "type": "swap",
                        "in": from_token,
                        "out": to_token,
                        "pool": direct_quote["pool"]
                    }],
                    "quote": direct_quote
                }
            
            # Try routing through USDC as intermediate
            usdc_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
            
            # First hop: from_token -> USDC
            first_hop = await self.get_swap_quote(from_token, usdc_mint, amount)
            if isinstance(first_hop, str):
                return f"No route found: {first_hop}"
                
            # Second hop: USDC -> to_token
            usdc_amount = float(first_hop["outputAmount"]) / 1e6  # USDC has 6 decimals
            second_hop = await self.get_swap_quote(usdc_mint, to_token, usdc_amount)
            if isinstance(second_hop, str):
                return f"No route found: {second_hop}"
            
            # Calculate combined price impact
            total_impact = float(first_hop["priceImpact"]) + float(second_hop["priceImpact"])
            
            return {
                "route": [{
                    "type": "swap",
                    "in": from_token,
                    "out": usdc_mint,
                    "pool": first_hop["pool"]
                }, {
                    "type": "swap",
                    "in": usdc_mint,
                    "out": to_token,
                    "pool": second_hop["pool"]
                }],
                "quote": {
                    "inputAmount": first_hop["inputAmount"],
                    "outputAmount": second_hop["outputAmount"],
                    "priceImpact": total_impact,
                    "pools": [first_hop["pool"], second_hop["pool"]]
                }
            }
            
        except Exception as e:
            return f"Error getting route quote: {str(e)}"
            
    async def get_public_key(self):
        """
        Get the public key of the current wallet.
        
        Returns:
            dict: A dictionary containing the public key of the wallet or an error message if no wallet is initialized
        """
        if self.wallet_address:
            return {"public_key": self.wallet_address}
        return {"error": "No wallet initialized"}

    async def execute_trade(self, route_quote: Dict[str, Any]):
        """
        Execute a trade using a previously obtained route quote.
        Handles both direct swaps and multi-hop routes.
        """
        if not route_quote or "quote" not in route_quote or "route" not in route_quote:
            return "Invalid route quote"
            
        try:
            if len(route_quote["route"]) == 1:
                # Direct swap
                result = await self.execute_swap(quote=route_quote["quote"])
            else:
                # Multi-hop route
                tx = Transaction()
                recent_blockhash = await self.client.get_recent_blockhash()
                tx.recent_blockhash = recent_blockhash["result"]["value"]["blockhash"]
                
                # Add swap instruction for each hop
                wallet_pubkey = Pubkey.from_string(self.wallet_address)
                for idx, hop in enumerate(route_quote["route"]):
                    pool_address = Pubkey.from_string(route_quote["quote"]["pools"][idx])
                    input_amount = route_quote["quote"]["inputAmount"] if idx == 0 else None
                    output_amount = route_quote["quote"]["outputAmount"] if idx == len(route_quote["route"]) - 1 else None
                    
                    swap_ix = self._build_swap_instruction(
                        pool_address,
                        wallet_pubkey,
                        int(input_amount) if input_amount else 0,
                        int(output_amount) if output_amount else 0
                    )
                    tx.add(swap_ix)
                
                # Send transaction
                opts = TxOpts(skip_preflight=False)
                result = await self.client.send_transaction(tx, self.wallet_keypair, opts=opts)
            
            return {
                "success": True,
                "txId": result["signature"] if "signature" in result else None,
                "route": route_quote["route"],
                "amounts": {
                    "inputAmount": route_quote["quote"]["inputAmount"],
                    "outputAmount": route_quote["quote"]["outputAmount"]
                }
            }
        except Exception as e:
            return f"Error executing trade: {str(e)}"

    async def get_token_list(self):
        """
        Returns a list of popular tokens on the Solana network from Raydium API.
        """
        try:
            response = requests.get(f"{self.RAYDIUM_API_URI}/tokens")
            tokens = response.json()
            return tokens
        except Exception as e:
            return f"Error retrieving token list: {str(e)}"

    async def get_token_price(self, token: str):
        """
        Retrieves the current price for the specified token from Raydium API.
        """
        try:
            response = requests.get(f"{self.RAYDIUM_API_URI}/price?token={token}")
            price_data = response.json()
            if "error" in price_data:
                return f"Error getting price: {price_data['error']}"
            if "price" not in price_data:
                return f"Error: Price data not available for token {token}"
            return price_data["price"]
        except Exception as e:
            return f"Error retrieving token price: {str(e)}"

    async def get_wallet_token_accounts(self, wallet_address: str = None):
        """
        Retrieves all token accounts associated with the given wallet.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        try:
            response = self.client.get_token_accounts_by_owner(
                Pubkey.from_string(wallet_address),
                {"programId": TOKEN_PROGRAM_ID}
            )
            
            # Process the response to handle the token account data structure
            if "result" in response and "value" in response["result"]:
                return {"token_accounts": response["result"]["value"]}
            else:
                return {"token_accounts": []}
                
        except Exception as e:
            return f"Error retrieving token accounts: {str(e)}"