import logging
import base58
import json
from typing import Optional
import aiohttp

try:
    from solana.rpc.async_api import AsyncClient
    from solana.transaction import Transaction
    from solders.system_program import (
        TransferParams,
        transfer,
        Keypair,
        Pubkey as PublicKey,
    )
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "solana"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "base58"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "solders"])
    from solana.rpc.async_api import AsyncClient
    from solana.transaction import Transaction
    from solders.system_program import (
        TransferParams,
        transfer,
        Keypair,
        Pubkey as PublicKey,
    )
from Extensions import Extensions

JUPITER_API_URL = "https://quote-api.jup.ag/v6"


class solana_wallet(Extensions):
    """
    The Solana extension for AGiXT enables an agent to interact with the Solana blockchain.
    It provides functionalities for wallet management (creation, balance checking), SOL transfers,
    transaction lookups, SPL token balance queries, token swap quoting and execution via Jupiter,
    and (on testnets) SOL airdrops.
    """

    def __init__(
        self,
        SOLANA_RPC_ENDPOINT: str = "https://api.mainnet-beta.solana.com",
        SOLANA_PRIVATE_KEY: str = "",
        **kwargs,
    ):
        self.rpc_endpoint = SOLANA_RPC_ENDPOINT
        self.private_key = SOLANA_PRIVATE_KEY
        self.client = AsyncClient(self.rpc_endpoint)
        self.keypair = None
        if self.private_key:
            try:
                private_key_bytes = base58.b58decode(self.private_key)
                self.keypair = Keypair.from_secret_key(private_key_bytes)
                logging.info("Initialized keypair from provided private key.")
            except Exception as e:
                logging.error(f"Error initializing Solana keypair: {str(e)}")
        self.commands = {
            "Create Solana Wallet": self.create_wallet,
            "Get Solana Wallet Balance": self.get_wallet_balance,
            "Send SOL": self.send_sol,
            "Get Transaction Info": self.get_transaction_info,
            "Get Recent Transactions": self.get_recent_transactions,
            "Get Solana Token Balance": self.get_token_balance,
            "Airdrop SOL": self.airdrop_sol,
            "Get Token List": self.get_token_list,
            "Get Token Price": self.get_token_price,
            "Get Token Swap Quote": self.get_swap_quote,
            "Execute Token Swap": self.execute_swap,
            "Get Wallet Token Accounts": self.get_wallet_token_accounts,
        }

    async def create_wallet(self) -> str:
        """
        Create a new Solana wallet by generating a new keypair.

        Returns:
            str: JSON string with the public and private keys.
        """
        try:
            new_keypair = Keypair()
            wallet_info = {
                "public_key": str(new_keypair.public_key),
                "private_key": base58.b58encode(new_keypair.secret_key).decode("utf-8"),
            }
            logging.info("Wallet created successfully.")
            return json.dumps(wallet_info, indent=2)
        except Exception as e:
            logging.error(f"Error creating wallet: {str(e)}")
            return f"Error creating wallet: {str(e)}"

    async def get_wallet_balance(self, wallet_address: str) -> str:
        """
        Retrieve the SOL balance for the specified wallet address.

        Args:
            wallet_address (str): The Solana wallet address.

        Returns:
            str: Message containing the balance in SOL.
        """
        try:
            pubkey = PublicKey(wallet_address)
            balance_response = await self.client.get_balance(pubkey)
            # Convert lamports to SOL
            sol_balance = balance_response.value / 1_000_000_000
            logging.info(f"Balance for {wallet_address}: {sol_balance} SOL")
            return f"Balance: {sol_balance} SOL"
        except Exception as e:
            logging.error(f"Error getting balance for {wallet_address}: {str(e)}")
            return f"Error getting balance: {str(e)}"

    async def send_sol(
        self, to_address: str, amount: float, from_private_key: Optional[str] = None
    ) -> str:
        """
        Send SOL from one wallet to another.

        Args:
            to_address (str): Recipient wallet address.
            amount (float): Amount of SOL to send.
            from_private_key (Optional[str]): Sender's private key. Uses initialized keypair if not provided.

        Returns:
            str: Transaction signature or error message.
        """
        try:
            if from_private_key:
                sender_keypair = Keypair.from_secret_key(
                    base58.b58decode(from_private_key)
                )
            elif self.keypair:
                sender_keypair = self.keypair
            else:
                return "Error: No sender wallet provided."

            recipient = PublicKey(to_address)
            lamports = int(amount * 1_000_000_000)
            transfer_params = TransferParams(
                from_pubkey=sender_keypair.public_key,
                to_pubkey=recipient,
                lamports=lamports,
            )
            transfer_ix = transfer(transfer_params)
            transaction = Transaction().add(transfer_ix)
            # Fetch a recent blockhash for the transaction
            recent_blockhash_resp = await self.client.get_latest_blockhash()
            transaction.recent_blockhash = recent_blockhash_resp.value.blockhash
            transaction.fee_payer = sender_keypair.public_key

            transaction.sign(sender_keypair)
            signature_resp = await self.client.send_transaction(
                transaction, sender_keypair
            )
            signature = signature_resp.value
            logging.info(f"Transaction sent: {signature}")
            return f"Transaction sent successfully. Signature: {signature}"
        except Exception as e:
            logging.error(f"Error sending SOL: {str(e)}")
            return f"Error sending SOL: {str(e)}"

    async def get_transaction_info(self, signature: str) -> str:
        """
        Retrieve detailed information about a transaction by its signature.

        Args:
            signature (str): The transaction signature.

        Returns:
            str: JSON-formatted transaction details or error message.
        """
        try:
            tx_info_resp = await self.client.get_transaction(signature)
            if tx_info_resp.value:
                tx_data = tx_info_resp.value
                formatted_info = {
                    "slot": tx_data.slot,
                    "blockhash": tx_data.transaction.message.recent_blockhash,
                    "success": tx_data.meta is not None and tx_data.meta.err is None,
                    "fee": tx_data.meta.fee if tx_data.meta else None,
                    "timestamp": tx_data.block_time,
                }
                logging.info(f"Transaction info retrieved for {signature}")
                return json.dumps(formatted_info, indent=2)
            logging.info(f"Transaction not found for signature: {signature}")
            return "Transaction not found."
        except Exception as e:
            logging.error(
                f"Error retrieving transaction info for {signature}: {str(e)}"
            )
            return f"Error getting transaction info: {str(e)}"

    async def get_recent_transactions(self, wallet_address: str, limit: int = 5) -> str:
        """
        Get a list of recent transactions for a given wallet address.

        Args:
            wallet_address (str): The Solana wallet address.
            limit (int): Maximum number of transactions to retrieve.

        Returns:
            str: JSON-formatted list of recent transactions.
        """
        try:
            pubkey = PublicKey(wallet_address)
            sigs_resp = await self.client.get_signatures_for_address(
                pubkey, limit=limit
            )
            transactions = []
            if sigs_resp.value:
                for sig in sigs_resp.value:
                    tx_info = {
                        "signature": sig.signature,
                        "slot": sig.slot,
                        "error": sig.err,
                        "memo": sig.memo,
                        "block_time": sig.block_time,
                    }
                    transactions.append(tx_info)
            logging.info(
                f"Retrieved {len(transactions)} transactions for {wallet_address}."
            )
            return json.dumps(transactions, indent=2)
        except Exception as e:
            logging.error(
                f"Error retrieving transactions for {wallet_address}: {str(e)}"
            )
            return f"Error getting recent transactions: {str(e)}"

    async def get_token_balance(self, wallet_address: str, token_address: str) -> str:
        """
        Retrieve the balance of a specific SPL token for a wallet address.

        Args:
            wallet_address (str): The wallet address.
            token_address (str): The SPL token mint address.

        Returns:
            str: Message indicating token balance or error message.
        """
        try:
            owner_pubkey = PublicKey(wallet_address)
            token_pubkey = PublicKey(token_address)
            token_accounts_resp = await self.client.get_token_accounts_by_owner(
                owner_pubkey, {"mint": str(token_pubkey)}
            )
            if not token_accounts_resp.value:
                return f"No token account found for token {token_address}."
            total_balance = 0.0
            for account in token_accounts_resp.value:
                balance_info = await self.client.get_token_account_balance(
                    PublicKey(account.pubkey)
                )
                ui_amount = getattr(balance_info.value, "uiAmount", None)
                if ui_amount is not None:
                    total_balance += float(ui_amount)
                else:
                    amount = getattr(balance_info.value, "amount", "0")
                    decimals = getattr(balance_info.value, "decimals", 0)
                    total_balance += (
                        int(amount) / (10**decimals) if decimals else int(amount)
                    )
            logging.info(
                f"Token balance for {token_address} in {wallet_address}: {total_balance}"
            )
            return f"Token Balance: {total_balance}"
        except Exception as e:
            logging.error(
                f"Error retrieving token balance for {wallet_address} and {token_address}: {str(e)}"
            )
            return f"Error getting token balance: {str(e)}"

    async def airdrop_sol(self, wallet_address: str, amount: float) -> str:
        """
        Request an airdrop of SOL to the specified wallet address (only available on testnets).

        Args:
            wallet_address (str): The wallet address.
            amount (float): Amount of SOL to airdrop.

        Returns:
            str: Transaction signature or error message.
        """
        try:
            if "mainnet" in self.rpc_endpoint:
                return "Airdrop is not supported on the mainnet."
            pubkey = PublicKey(wallet_address)
            lamports = int(amount * 1_000_000_000)
            airdrop_resp = await self.client.request_airdrop(pubkey, lamports)
            signature = airdrop_resp.value
            logging.info(f"Airdrop requested for {wallet_address}: {signature}")
            return f"Airdrop requested. Transaction signature: {signature}"
        except Exception as e:
            logging.error(f"Error requesting airdrop for {wallet_address}: {str(e)}")
            return f"Error requesting airdrop: {str(e)}"

    async def get_token_list(self) -> str:
        """
        Get the list of supported tokens from the Jupiter DEX API.

        Returns:
            str: JSON string of token information.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{JUPITER_API_URL}/tokens") as response:
                    tokens = await response.json()
                    logging.info(f"Retrieved {len(tokens)} tokens from Jupiter API")
                    return json.dumps(tokens, indent=2)
        except Exception as e:
            logging.error(f"Error getting token list: {str(e)}")
            return f"Error getting token list: {str(e)}"

    async def get_token_price(self, token_address: str) -> str:
        """
        Get the current price of a token in USDC via Jupiter API.

        Args:
            token_address (str): The token's mint address.

        Returns:
            str: Price information or error message.
        """
        try:
            usdc_mint = (
                "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC mint on Solana
            )
            params = {
                "inputMint": token_address,
                "outputMint": usdc_mint,
                "amount": "1000000",  # 1 token in base units (adjust if needed)
                "slippageBps": 50,  # 0.5% slippage
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{JUPITER_API_URL}/quote", params=params
                ) as response:
                    quote = await response.json()
                    if "data" in quote:
                        price = float(quote["data"]["outAmount"]) / 1_000_000
                        return f"Price: ${price:.2f} USDC"
                    return "Price information not available"
        except Exception as e:
            logging.error(f"Error getting token price: {str(e)}")
            return f"Error getting token price: {str(e)}"

    async def get_swap_quote(
        self, input_token: str, output_token: str, amount: float, slippage: float = 0.5
    ) -> str:
        """
        Get a token swap quote from Jupiter DEX.

        Args:
            input_token (str): Input token mint address.
            output_token (str): Output token mint address.
            amount (float): Amount of input tokens.
            slippage (float): Maximum slippage percentage (default 0.5).

        Returns:
            str: JSON-formatted swap quote information.
        """
        try:
            params = {
                "inputMint": input_token,
                "outputMint": output_token,
                "amount": str(int(amount * 1e9)),  # Convert to lowest denomination
                "slippageBps": int(slippage * 100),
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{JUPITER_API_URL}/quote", params=params
                ) as response:
                    quote = await response.json()
                    logging.info(f"Retrieved swap quote for {amount} tokens")
                    return json.dumps(quote, indent=2)
        except Exception as e:
            logging.error(f"Error getting swap quote: {str(e)}")
            return f"Error getting swap quote: {str(e)}"

    async def execute_swap(
        self,
        input_token: str,
        output_token: str,
        amount: float,
        slippage: float = 0.5,
        wallet_private_key: Optional[str] = None,
    ) -> str:
        """
        Execute a token swap via Jupiter DEX.

        Args:
            input_token (str): Input token mint address.
            output_token (str): Output token mint address.
            amount (float): Amount of input tokens to swap.
            slippage (float): Maximum slippage percentage.
            wallet_private_key (Optional[str]): Private key for signing the swap.

        Returns:
            str: Transaction signature or error message.
        """
        try:
            # Obtain swap quote
            quote_result = await self.get_swap_quote(
                input_token, output_token, amount, slippage
            )
            quote = json.loads(quote_result)
            if "error" in quote:
                return f"Error getting quote: {quote['error']}"

            # Prepare swap transaction request
            async with aiohttp.ClientSession() as session:
                swap_request = {
                    "quoteResponse": quote,
                    "userPublicKey": (
                        str(self.keypair.public_key) if self.keypair else ""
                    ),
                }
                async with session.post(
                    f"{JUPITER_API_URL}/swap", json=swap_request
                ) as response:
                    swap_tx = await response.json()
                    if "swapTransaction" not in swap_tx:
                        return f"Error preparing swap transaction: {swap_tx.get('error', 'Unknown error')}"

                    # The swap transaction is expected to be a serialized transaction (possibly base64 encoded)
                    # Adjust decoding if necessary; here we assume raw bytes can be obtained.
                    tx_bytes = bytes(swap_tx["swapTransaction"])
                    tx = Transaction.deserialize(tx_bytes)

                    # Use provided private key if given
                    if wallet_private_key:
                        signer = Keypair.from_secret_key(
                            base58.b58decode(wallet_private_key)
                        )
                    elif self.keypair:
                        signer = self.keypair
                    else:
                        return "Error: No wallet available for signing the swap."

                    tx.sign(signer)
                    signature_resp = await self.client.send_transaction(tx, signer)
                    signature = signature_resp.value
                    logging.info(f"Swap transaction sent: {signature}")
                    return f"Swap transaction sent successfully. Signature: {signature}"
        except Exception as e:
            logging.error(f"Error executing swap: {str(e)}")
            return f"Error executing swap: {str(e)}"

    async def get_wallet_token_accounts(self, wallet_address: str) -> str:
        """
        Retrieve all token accounts associated with a wallet address.

        Args:
            wallet_address (str): The Solana wallet address.

        Returns:
            str: JSON-formatted list of token accounts and balances.
        """
        try:
            owner_pubkey = PublicKey(wallet_address)
            response = await self.client.get_token_accounts_by_owner(
                owner_pubkey,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            )
            token_accounts = []
            for account in response.value:
                balance_info = await self.client.get_token_account_balance(
                    PublicKey(account.pubkey)
                )
                account_info = {
                    "account_address": account.pubkey,
                    "mint": account.account.data.parsed["info"]["mint"],
                    "balance": balance_info.value.amount,
                    "decimals": balance_info.value.decimals,
                    "ui_amount": balance_info.value.ui_amount,
                }
                token_accounts.append(account_info)
            logging.info(
                f"Retrieved {len(token_accounts)} token accounts for {wallet_address}"
            )
            return json.dumps(token_accounts, indent=2)
        except Exception as e:
            logging.error(
                f"Error getting token accounts for {wallet_address}: {str(e)}"
            )
            return f"Error getting token accounts: {str(e)}"
