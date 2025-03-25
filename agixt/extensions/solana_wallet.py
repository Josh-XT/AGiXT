from Extensions import Extensions
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.keypair import Keypair
import base58
from solders.system_program import TransferParams, transfer



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
        SOLANA_API_URI = "https://api.mainnet-beta.solana.com"
        self.SOLANA_API_URI = SOLANA_API_URI
        self.client = AsyncClient(SOLANA_API_URI)
        WALLET_PRIVATE_KEY = kwargs.get("SOLANA_WALLET_API_KEY", None)
        self.wallet_keypair = None
        self.wallet_address = None

        # If an existing wallet private key is provided, load the keypair
        if WALLET_PRIVATE_KEY:
            # Here we assume the private key is a base58-encoded string.
            try:
                self.wallet_keypair = Keypair.from_base58_string(WALLET_PRIVATE_KEY)
                self.wallet_address = str(self.wallet_keypair.pubkey())
            except (ValueError, TypeError):
                pass

        self.commands = {
            "Get Solana Wallet Balance": self.get_wallet_balance,
            "Send SOL": self.send_sol,
            "Get Transaction Info": self.get_transaction_info,
            "Get Recent Transactions": self.get_recent_transactions,
            "Get Solana Token Balance": self.get_token_balance,
            "Airdrop SOL": self.airdrop_sol,
            "Get Public Key": self.get_public_key,
            "Get Token Swap Quote": self.get_swap_quote,
            "Execute Token Swap": self.execute_swap,
            "Get Token List": self.get_token_list,
            "Get Token Price": self.get_token_price,
            "Get Wallet Token Accounts": self.get_wallet_token_accounts,
        }

    async def create_wallet(self):
        """
        Creates a new Solana wallet by generating a new keypair.
        This method can be used if no wallet was connected via the init params.
        """
        new_keypair = Keypair()
        self.wallet_keypair = new_keypair
        self.wallet_address = str(new_keypair.pubkey())
        private_key = base58.b58encode(bytes(new_keypair)).decode()
        return (
            f"Created new Solana wallet.\n"
            f"Public Key: {self.wallet_address}\n"
            f"Private Key: {private_key}"
        )

    async def get_public_key(self):
        """
        Get the public key (wallet address) for the current wallet.
        Returns the public key as a string if wallet exists, otherwise returns an error message.
        """
        if self.wallet_address is None:
            # Create new wallet if none exists
            new_keypair = Keypair()
            self.wallet_keypair = new_keypair
            self.wallet_address = str(new_keypair.pubkey())
            private_key = base58.b58encode(bytes(new_keypair)).decode()
            # Return both private key and public key so it can be saved
            return f"Created new wallet.\nPublic Key: {self.wallet_address}\n" \
                   f"Private Key: {private_key}"
            
        return (f"Public Key: {self.wallet_address}")


    async def get_wallet_balance(self, wallet_address: str = None):
        """
        Retrieves the SOL balance for the given wallet address.
        If no address is provided, uses the wallet address from initialization.
        """
        if not wallet_address:  # Handles both None and empty string
            wallet_address = self.wallet_address
        if wallet_address is None:
            return "No wallet address specified."
        try:
            # Convert the wallet address string to a Pubkey object
            response = await self.client.get_balance(Pubkey.from_string(wallet_address), commitment=Confirmed)
            balance_lamports = response.value
            sol_balance = balance_lamports / 1e9
            return f"Wallet {wallet_address} balance: {sol_balance} SOL."
        except Exception as e:
            return f"Error retrieving balance: {str(e)}"

    async def send_sol(
        self, from_wallet: str = None, to_wallet: str = "", amount: str = "0.0"
    ):
        """
        Sends a specified amount of SOL (in SOL units) from one wallet to another.
        Amount is provided as a string and converted appropriately, with fee consideration.
        """
        if from_wallet is None:
            from_wallet = self.wallet_address
        if from_wallet is None or self.wallet_keypair is None:
            return "No sender wallet or keypair available."
        if not to_wallet:
            return "No recipient wallet specified."

        try:
            # Convert amount from string to float
            amount_float = float(amount)
            if amount_float <= 0:
                return "Amount must be greater than 0."

            # Get current balance asynchronously
            balance_response = await self.client.get_balance(Pubkey.from_string(from_wallet), commitment=Confirmed)
            available_lamports = balance_response.value

            # Estimate transaction fee (5000 lamports is typical)
            FEE_LAMPORTS = 5000
            max_lamports_to_send = available_lamports - FEE_LAMPORTS

            if max_lamports_to_send <= 0:
                return f"Insufficient funds: Balance ({available_lamports / 1e9} SOL) is less than the estimated fee ({FEE_LAMPORTS / 1e9} SOL)."

            # Determine if amount is in SOL or lamports
            if amount_float > 1000:
                lamports_amount = int(amount_float)
            else:
                lamports_amount = int(amount_float * 1_000_000_000)

            # Adjust amount if it exceeds available balance minus fee
            adjustment_message = ""
            if lamports_amount > max_lamports_to_send:
                lamports_amount = max_lamports_to_send
                adjusted_amount_sol = lamports_amount / 1_000_000_000
                adjustment_message = f"Adjusted amount to {adjusted_amount_sol} SOL to account for transaction fee."

            if lamports_amount <= 0:
                return "Amount too small to send after fee adjustment."

            # Create transfer instruction
            transfer_ix = transfer(TransferParams(
                from_pubkey=Pubkey.from_string(from_wallet),
                to_pubkey=Pubkey.from_string(to_wallet),
                lamports=lamports_amount,
            )
            )

            # Get recent blockhash and create versioned transaction
            blockhash_response = await self.client.get_latest_blockhash(commitment=Confirmed)
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=Pubkey.from_string(from_wallet),
                instructions=[transfer_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])
            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)
            return f"Transaction submitted successfully. Signature: {response.value}\n{adjustment_message}".strip()
        except ValueError as ve:
            return f"Error: Invalid amount format - {str(ve)}"
        except Exception as e:
            return f"Error sending SOL: {str(e)}"

    async def get_transaction_info(self, tx_signature: str):
        """
        Retrieves information about a specific transaction using its signature.
        """
        try:
            response = await self.client.get_confirmed_transaction(tx_signature)
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
            response = await self.client.get_signatures_for_address(
                Pubkey.from_string(wallet_address), limit=limit
            )
            return f"Recent transactions for wallet {wallet_address}: {response.get('result')}"
        except Exception as e:
            return f"Error retrieving recent transactions: {str(e)}"

    async def get_token_balance(self, wallet_address: str = None, token_mint: str = ""):
        """
        Retrieves the balance of a specific SPL token for the given wallet.
        (Placeholder: implement actual token queries as needed.)
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
            response = await self.client.request_airdrop(
                Pubkey.from_string(wallet_address), lamports_amount
            )
            return f"Airdrop requested: {response.get('result')}"
        except Exception as e:
            return f"Error requesting airdrop: {str(e)}"

    async def get_swap_quote(self, from_token: str, to_token: str, amount: float):
        """
        Retrieves a simulated quote for swapping one token to another.
        (Placeholder: integrate with a DEX API for real quotes.)
        """
        simulated_quote = amount * 0.95
        return f"Simulated swap quote: {amount} {from_token} ≈ {simulated_quote:.2f} {to_token}."

    async def execute_swap(
        self,
        wallet_address: str = None,
        from_token: str = "",
        to_token: str = "",
        amount: float = 0.0,
    ):
        """
        Executes a simulated token swap for the given wallet.
        (Placeholder: integrate with a DEX API for real swaps.)
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        simulated_received = amount * 0.95
        return f"Simulated token swap: {amount} {from_token} swapped for {simulated_received:.2f} {to_token} in wallet {wallet_address}."

    async def get_token_list(self):
        """
        Returns a simulated list of popular tokens on the Solana network.
        """
        tokens = ["SOL", "USDC", "USDT", "SRM", "RAY"]
        return "Token list: " + ", ".join(tokens)

    async def get_token_price(self, token: str):
        """
        Retrieves a simulated price for the specified token.
        """
        simulated_price = 1.23
        return f"Price for {token}: ${simulated_price} (example price)."

    async def get_wallet_token_accounts(self, wallet_address: str = None):
        """
        Retrieves all token accounts associated with the given wallet.
        (Placeholder: implement actual token account lookup.)
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        simulated_accounts = ["TokenAccount1", "TokenAccount2"]
        return f"Token accounts for wallet {wallet_address}: {simulated_accounts}"
