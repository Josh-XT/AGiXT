from Extensions import Extensions
from solana.rpc.api import Client
from solders.transaction import Transaction
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.system_program import transfer


class solana_wallet(Extensions):
    """
    The SolanaWallets extension enables interaction with Solana blockchain wallets using the solana‑py SDK.
    This implementation uses the new solders‑based imports for keypairs, public keys, and system instructions.

    The extension supports creating wallets, checking balances, sending SOL, and more.
    """

    def __init__(
        self,
        SOLANA_API_URI: str = "https://api.devnet.solana.com",
        WALLET_PRIVATE_KEY: str = "",
        **kwargs,
    ):
        self.SOLANA_API_URI = SOLANA_API_URI
        self.client = Client(SOLANA_API_URI)

        # If an existing wallet private key is provided, load the keypair
        if WALLET_PRIVATE_KEY:
            # Here we assume the private key is a base58-encoded string.
            # (You might instead have a hex string; adjust as needed.)
            self.wallet_keypair = Keypair.from_base58_string(WALLET_PRIVATE_KEY)
            self.wallet_address = self.wallet_keypair.pubkey().to_string()
        else:
            self.wallet_keypair = None
            self.wallet_address = None

        self.commands = {
            "Create Solana Wallet": self.create_wallet,
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
        }

    async def create_wallet(self):
        """
        Creates a new Solana wallet by generating a new keypair.
        This method can be used if no wallet was connected via the init params.
        """
        new_keypair = Keypair.generate()
        self.wallet_keypair = new_keypair
        self.wallet_address = new_keypair.pubkey().to_string()
        secret_hex = (
            new_keypair.secret().hex()
        )  # for display; store securely in practice
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
            response = self.client.request_airdrop(
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
