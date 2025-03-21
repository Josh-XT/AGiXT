from Extensions import Extensions
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


# Constants
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

class solana_wallet(Extensions):
    """
    The SolanaWallets extension enables interaction with Solana blockchain wallets using the solana‑py SDK.
    This implementation uses the new solders‑based imports for keypairs, public keys, and system instructions.

    The extension supports creating wallets, checking balances, sending SOL, and more.
    """

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
        Retrieves a quote for swapping one token to another using Raydium API.
        """
        try:
            url = f"{self.RAYDIUM_API_URI}/quote"
            payload = {
                "inputMint": from_token,
                "outputMint": to_token,
                "amount": str(int(amount * 1e9)),  # Convert to lamports
                "slippage": 0.5  # 0.5% slippage
            }
            response = requests.post(url, json=payload)
            quote_data = response.json()
            
            if "error" in quote_data:
                return f"Error getting quote: {quote_data['error']}"
                
            return {
                "inputAmount": quote_data["inputAmount"],
                "outputAmount": quote_data["outputAmount"],
                "route": quote_data["route"],
                "priceImpact": quote_data["priceImpact"]
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
        Executes a token swap using Raydium's API.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if not quote:
            return "No quote provided for swap"
            
        try:
            # Build the swap transaction using quote data
            url = f"{self.RAYDIUM_API_URI}/swap"
            payload = {
                "wallet": wallet_address,
                "quote": quote
            }
            
            # Get transaction data from Raydium
            response = requests.post(url, json=payload)
            tx_data = response.json()
            
            if "error" in tx_data:
                return f"Error building swap transaction: {tx_data['error']}"
            
            # Create and sign transaction
            tx = Transaction.from_json(tx_data["transaction"])
            opts = TxOpts(skip_preflight=False)
            
            # Send transaction
            response = self.client.send_transaction(tx, self.wallet_keypair, opts=opts)
            
            return {
                "success": True,
                "signature": response["result"],
                "inputAmount": quote["inputAmount"],
                "outputAmount": quote["outputAmount"]
            }
        except Exception as e:
            return f"Error executing swap: {str(e)}"
            
    async def get_route_quote(self, from_token: str, to_token: str, amount: float):
        """
        Get a quote for the best trading route between two tokens.
        """
        try:
            url = f"{self.RAYDIUM_API_URI}/route"
            payload = {
                "inputMint": from_token,
                "outputMint": to_token,
                "amount": str(int(amount * 1e9)),
                "slippage": 0.5
            }
            
            response = requests.post(url, json=payload)
            route_data = response.json()
            
            if "error" in route_data:
                return f"Error getting route: {route_data['error']}"
            
            # Get quote for the best route
            quote = await self.get_swap_quote(from_token, to_token, amount)
            
            return {
                "route": route_data["route"],
                "quote": quote
            }
        except Exception as e:
            return f"Error getting route quote: {str(e)}"
            
    async def execute_trade(self, route_quote: Dict[str, Any]):
        """
        Execute a trade using a previously obtained route quote.
        """
        if not route_quote or "quote" not in route_quote:
            return "Invalid route quote"
            
        try:
            result = await self.execute_swap(
                quote=route_quote["quote"]
            )
            
            return {
                "success": True,
                "txId": result["signature"] if "signature" in result else None,
                "route": route_quote["route"],
                "amounts": result
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
            return response["result"]
        except Exception as e:
            return f"Error retrieving token accounts: {str(e)}"
