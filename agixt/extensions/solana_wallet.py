from Extensions import Extensions
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts
from solders.keypair import Keypair
from solders.system_program import TransferParams, transfer, ID as SYS_PROGRAM_ID
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.message import Message, MessageV0
import base58
import requests
import json
import struct
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Any, Optional, List, Union, Tuple
from solders.transaction import VersionedTransaction, Transaction
from solders.system_program import TransferParams, transfer
from solders.hash import Hash
from solders.signature import Signature
from solana.rpc.types import TokenAccountOpts

# Define TOKEN_PROGRAM_ID and other constants
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022_PROGRAM_ID = Pubkey.from_string(
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
)
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string(
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
)
METADATA_PROGRAM_ID = Pubkey.from_string("metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s")
STAKE_PROGRAM_ID = Pubkey.from_string("Stake11111111111111111111111111111111111111")
MEMO_PROGRAM_ID = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")


# Instruction indices for SPL Token operations
class TokenInstruction:
    INITIALIZE_MINT = 0
    INITIALIZE_ACCOUNT = 1
    INITIALIZE_MULTISIG = 2
    TRANSFER = 3
    APPROVE = 4
    REVOKE = 5
    SET_AUTHORITY = 6
    MINT_TO = 7
    BURN = 8
    CLOSE_ACCOUNT = 9
    FREEZE_ACCOUNT = 10
    THAW_ACCOUNT = 11
    TRANSFER_CHECKED = 12
    APPROVE_CHECKED = 13
    MINT_TO_CHECKED = 14
    BURN_CHECKED = 15


class solana_wallet(Extensions):
    """
    The SolanaWallets extension enables comprehensive interaction with Solana blockchain
    including SOL transfers, SPL token operations, NFTs, staking, and more.

    This implementation supports:
    - SOL and SPL token transfers
    - Associated token accounts
    - NFT operations
    - Staking and unstaking
    - Token minting and burning
    - Jupiter swaps
    - Transaction building and signing
    """

    CATEGORY = "Finance & Crypto"
    friendly_name = "Solana Wallet"

    JUPITER_API_BASE_URL = "https://quote-api.jup.ag/v6"
    JUPITER_PROGRAM_ID = Pubkey.from_string(
        "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
    )

    # Popular token mints for reference
    USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    BONK_MINT = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"

    async def _get_token_decimals(self, token: Pubkey) -> int:
        """Get token decimals from mint account"""
        try:
            token_info = await self.client.get_account_info(token)
            if not token_info.value or not token_info.value.data:
                return 9

            data = base58.b58decode(token_info.value.data)
            decimals = data[44]
            return decimals
        except Exception:
            return 9

    def __init__(
        self,
        **kwargs,
    ):
        # Use the HelloMoon RPC endpoint
        SOLANA_API_URI = "https://rpc.hellomoon.io/15b3c970-4cdc-4718-ac26-3896d5422fb6"
        self.WSOL_MINT = "So11111111111111111111111111111111111111112"
        self.SOLANA_API_URI = SOLANA_API_URI
        self.client = AsyncClient(SOLANA_API_URI)
        WALLET_PRIVATE_KEY = kwargs.get("SOLANA_WALLET_API_KEY", None)

        if (
            WALLET_PRIVATE_KEY
            and WALLET_PRIVATE_KEY.strip()
            and WALLET_PRIVATE_KEY.upper() not in ["NONE", "NULL", "UNDEFINED", ""]
        ):  # Check for non-empty string and valid values
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

                logging.debug(f"Solana wallet initialization failed: {e}")
                self.wallet_keypair = None
                self.wallet_address = None
        else:
            # No private key provided or empty private key
            # print("No valid private key provided for Solana wallet initialization")
            self.wallet_keypair = None
            self.wallet_address = None

        self.commands = {
            "Get Solana Wallet Balance": self.get_wallet_balance,
            "Send SOL": self.send_sol,
            "Get Public Key": self.get_public_key,
            "Get Transaction Info": self.get_transaction_info,
            "Get Recent Transactions": self.get_recent_transactions,
            "Get Token Balance": self.get_token_balance,
            "Get All Token Balances": self.get_all_token_balances,
            "Send SPL Token": self.send_spl_token,
            "Create Associated Token Account": self.create_associated_token_account,
            "Get Associated Token Address": self.get_associated_token_address,
            "Burn Tokens": self.burn_tokens,
            "Close Token Account": self.close_token_account,
            "Get NFTs": self.get_nfts,
            "Transfer NFT": self.transfer_nft,
            "Stake SOL": self.stake_sol,
            "Get Stake Accounts": self.get_stake_accounts,
            "Deactivate Stake": self.deactivate_stake,
            "Withdraw Stake": self.withdraw_stake,
            "Get Jupiter Swap Quote": self.get_jupiter_swap_quote,
            "Execute Jupiter Swap": self.execute_jupiter_swap,
            "Get Token List": self.get_token_list,
            "Get Token Metadata": self.get_token_metadata,
            "Add Memo to Transaction": self.create_memo_instruction,
            "Get Rent Exempt Balance": self.get_rent_exempt_balance,
            "Request Airdrop": self.request_airdrop,
            "Get Validators": self.get_validators,
            "Set Priority Fee": self.set_priority_fee_instruction,
            "Get Priority Fee Estimate": self.get_priority_fee_estimate,
            "Create Token Mint": self.create_token_mint,
            "Mint Tokens": self.mint_tokens,
            "Get Program Accounts": self.get_program_accounts,
            "Create Multisig Account": self.create_multisig_account,
            "Get Token Supply": self.get_token_supply,
            "Freeze Token Account": self.freeze_token_account,
            "Thaw Token Account": self.thaw_token_account,
            "Get Slot": self.get_slot,
            "Get Block Height": self.get_block_height,
            "Get Epoch Info": self.get_epoch_info,
            "Simulate Transaction": self.simulate_transaction,
            "Get Token Largest Accounts": self.get_token_largest_accounts,
            "Partial Sign Transaction": self.partial_sign_transaction,
            "Get Address Lookup Table": self.get_address_lookup_table,
            "Create Address Lookup Table": self.create_address_lookup_table,
            "Extend Address Lookup Table": self.extend_address_lookup_table,
        }

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
            pubkey = Pubkey.from_string(wallet_address)
            response = await self.client.get_balance(pubkey, commitment=Confirmed)

            balance_lamports = response.value
            sol_balance = balance_lamports / 1_000_000_000

            sol_balance_str = f"{sol_balance:.9f}".rstrip("0").rstrip(".")

            return f"The balance of the Solana wallet with public key {wallet_address} is {sol_balance_str} SOL."
        except Exception as e:
            return f"Error retrieving balance: {str(e)}"

    async def send_sol(
        self,
        from_wallet: str = None,
        to_wallet: str = "",
        amount: str = "0.0",
        memo: str = None,
    ):
        """
        Sends a specified amount of SOL from one wallet to another with optional memo.

        Args:
            from_wallet (str): Sender's public key (defaults to self.wallet_address if None).
            to_wallet (str): Recipient's public key.
            amount (str): Amount of SOL to send as a string (e.g., "0.005657068").
            memo (str): Optional memo to include with the transaction.

        Returns:
            str: Success message with transaction signature or an error message.
        """
        if from_wallet is None:
            from_wallet = self.wallet_address
        if from_wallet is None or self.wallet_keypair is None:
            return "No sender wallet or private key available. Please initialize with SOLANA_WALLET_API_KEY or create a wallet."
        if not to_wallet:
            return "No recipient wallet specified."

        try:
            amount_float = float(amount)
            if amount_float <= 0:
                return "Amount must be greater than 0."

            balance_response = await self.client.get_balance(
                Pubkey.from_string(from_wallet), commitment=Confirmed
            )
            available_lamports = balance_response.value

            FEE_LAMPORTS = 5000
            max_lamports_to_send = available_lamports - FEE_LAMPORTS

            if max_lamports_to_send <= 0:
                return f"Insufficient funds: Balance ({available_lamports / 1e9} SOL) is less than the estimated fee ({FEE_LAMPORTS / 1e9} SOL)."

            if amount_float > 1000:
                lamports_amount = int(amount_float)
            else:
                lamports_amount = int(amount_float * 1_000_000_000)

            if lamports_amount > max_lamports_to_send:
                lamports_amount = max_lamports_to_send
                adjusted_amount_sol = lamports_amount / 1_000_000_000
                print(
                    f"Adjusted amount to {adjusted_amount_sol} SOL to account for transaction fee."
                )

            if lamports_amount <= 0:
                return "Amount too small to send after fee adjustment."

            instructions = []

            # Add transfer instruction
            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=Pubkey.from_string(from_wallet),
                    to_pubkey=Pubkey.from_string(to_wallet),
                    lamports=lamports_amount,
                )
            )
            instructions.append(transfer_ix)

            # Add memo if provided
            if memo:
                memo_ix = self.create_memo_instruction(memo, from_wallet)
                instructions.append(memo_ix)

            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=Pubkey.from_string(from_wallet),
                instructions=instructions,
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)
            tx_signature = response.value

            return f"Transaction submitted successfully. Signature: {tx_signature}"
        except ValueError as ve:
            return f"Error: Invalid amount format - {str(ve)}"
        except Exception as e:
            return f"Error sending SOL: {str(e)}"

    async def get_associated_token_address(
        self, wallet_address: str, token_mint: str
    ) -> Pubkey:
        """
        Derive the associated token account address for a wallet and token mint.
        """
        wallet_pubkey = Pubkey.from_string(wallet_address)
        mint_pubkey = Pubkey.from_string(token_mint)

        # Find PDA for associated token account
        seeds = [bytes(wallet_pubkey), bytes(TOKEN_PROGRAM_ID), bytes(mint_pubkey)]

        ata, _ = Pubkey.find_program_address(seeds, ASSOCIATED_TOKEN_PROGRAM_ID)
        return ata

    async def create_associated_token_account(
        self, wallet_address: str = None, token_mint: str = ""
    ):
        """
        Create an associated token account for a specific SPL token.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."
        if not token_mint:
            return "No token mint specified."

        try:
            wallet_pubkey = Pubkey.from_string(wallet_address)
            mint_pubkey = Pubkey.from_string(token_mint)

            # Get associated token address
            ata = await self.get_associated_token_address(wallet_address, token_mint)

            # Check if account already exists
            account_info = await self.client.get_account_info(ata)
            if account_info.value:
                return f"Associated token account already exists: {ata}"

            # Create instruction
            keys = [
                AccountMeta(pubkey=wallet_pubkey, is_signer=True, is_writable=True),
                AccountMeta(pubkey=ata, is_signer=False, is_writable=True),
                AccountMeta(pubkey=wallet_pubkey, is_signer=False, is_writable=False),
                AccountMeta(pubkey=mint_pubkey, is_signer=False, is_writable=False),
                AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
                AccountMeta(
                    pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False
                ),
            ]

            create_ata_ix = Instruction(
                program_id=ASSOCIATED_TOKEN_PROGRAM_ID, accounts=keys, data=bytes()
            )

            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=wallet_pubkey,
                instructions=[create_ata_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return f"Associated token account created successfully. Account: {ata}, Signature: {response.value}"
        except Exception as e:
            return f"Error creating associated token account: {str(e)}"

    async def send_spl_token(
        self,
        from_wallet: str = None,
        to_wallet: str = "",
        token_mint: str = "",
        amount: str = "0.0",
        decimals: int = None,
        create_ata_if_needed: bool = True,
    ):
        """
        Send SPL tokens from one wallet to another.

        Args:
            from_wallet: Sender's wallet address
            to_wallet: Recipient's wallet address
            token_mint: Token mint address
            amount: Amount to send (human readable)
            decimals: Token decimals (auto-detected if not provided)
            create_ata_if_needed: Create recipient's ATA if it doesn't exist
        """
        if from_wallet is None:
            from_wallet = self.wallet_address
        if from_wallet is None or self.wallet_keypair is None:
            return "No sender wallet or private key available."
        if not to_wallet:
            return "No recipient wallet specified."
        if not token_mint:
            return "No token mint specified."

        try:
            from_pubkey = Pubkey.from_string(from_wallet)
            to_pubkey = Pubkey.from_string(to_wallet)
            mint_pubkey = Pubkey.from_string(token_mint)

            # Get token decimals if not provided
            if decimals is None:
                decimals = await self._get_token_decimals(mint_pubkey)

            # Calculate amount in base units
            amount_float = float(amount)
            amount_base = int(amount_float * (10**decimals))

            # Get source and destination token accounts
            source_ata = await self.get_associated_token_address(
                from_wallet, token_mint
            )
            dest_ata = await self.get_associated_token_address(to_wallet, token_mint)

            instructions = []

            # Check if destination ATA exists
            dest_account_info = await self.client.get_account_info(dest_ata)
            if not dest_account_info.value and create_ata_if_needed:
                # Create ATA instruction
                keys = [
                    AccountMeta(pubkey=from_pubkey, is_signer=True, is_writable=True),
                    AccountMeta(pubkey=dest_ata, is_signer=False, is_writable=True),
                    AccountMeta(pubkey=to_pubkey, is_signer=False, is_writable=False),
                    AccountMeta(pubkey=mint_pubkey, is_signer=False, is_writable=False),
                    AccountMeta(
                        pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False
                    ),
                    AccountMeta(
                        pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False
                    ),
                ]

                create_ata_ix = Instruction(
                    program_id=ASSOCIATED_TOKEN_PROGRAM_ID, accounts=keys, data=bytes()
                )
                instructions.append(create_ata_ix)

            # Create transfer instruction
            transfer_data = bytearray([TokenInstruction.TRANSFER_CHECKED])
            transfer_data.extend(struct.pack("<Q", amount_base))
            transfer_data.append(decimals)

            transfer_keys = [
                AccountMeta(pubkey=source_ata, is_signer=False, is_writable=True),
                AccountMeta(pubkey=mint_pubkey, is_signer=False, is_writable=False),
                AccountMeta(pubkey=dest_ata, is_signer=False, is_writable=True),
                AccountMeta(pubkey=from_pubkey, is_signer=True, is_writable=False),
            ]

            transfer_ix = Instruction(
                program_id=TOKEN_PROGRAM_ID,
                accounts=transfer_keys,
                data=bytes(transfer_data),
            )
            instructions.append(transfer_ix)

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=from_pubkey,
                instructions=instructions,
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return f"SPL token transfer successful. Amount: {amount} tokens, Signature: {response.value}"
        except Exception as e:
            return f"Error sending SPL token: {str(e)}"

    async def burn_tokens(self, token_mint: str, amount: str, decimals: int = None):
        """
        Burn SPL tokens from your wallet.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            wallet_pubkey = Pubkey.from_string(self.wallet_address)
            mint_pubkey = Pubkey.from_string(token_mint)

            if decimals is None:
                decimals = await self._get_token_decimals(mint_pubkey)

            amount_float = float(amount)
            amount_base = int(amount_float * (10**decimals))

            # Get token account
            token_account = await self.get_associated_token_address(
                self.wallet_address, token_mint
            )

            # Create burn instruction
            burn_data = bytearray([TokenInstruction.BURN_CHECKED])
            burn_data.extend(struct.pack("<Q", amount_base))
            burn_data.append(decimals)

            burn_keys = [
                AccountMeta(pubkey=token_account, is_signer=False, is_writable=True),
                AccountMeta(pubkey=mint_pubkey, is_signer=False, is_writable=True),
                AccountMeta(pubkey=wallet_pubkey, is_signer=True, is_writable=False),
            ]

            burn_ix = Instruction(
                program_id=TOKEN_PROGRAM_ID, accounts=burn_keys, data=bytes(burn_data)
            )

            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=wallet_pubkey,
                instructions=[burn_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return f"Successfully burned {amount} tokens. Signature: {response.value}"
        except Exception as e:
            return f"Error burning tokens: {str(e)}"

    async def close_token_account(self, token_mint: str):
        """
        Close a token account and recover rent.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            wallet_pubkey = Pubkey.from_string(self.wallet_address)
            token_account = await self.get_associated_token_address(
                self.wallet_address, token_mint
            )

            # Create close account instruction
            close_data = bytearray([TokenInstruction.CLOSE_ACCOUNT])

            close_keys = [
                AccountMeta(pubkey=token_account, is_signer=False, is_writable=True),
                AccountMeta(pubkey=wallet_pubkey, is_signer=False, is_writable=True),
                AccountMeta(pubkey=wallet_pubkey, is_signer=True, is_writable=False),
            ]

            close_ix = Instruction(
                program_id=TOKEN_PROGRAM_ID, accounts=close_keys, data=bytes(close_data)
            )

            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=wallet_pubkey,
                instructions=[close_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return f"Token account closed successfully. Signature: {response.value}"
        except Exception as e:
            return f"Error closing token account: {str(e)}"

    async def get_all_token_balances(self, wallet_address: str = None):
        """
        Get all SPL token balances for a wallet.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if wallet_address is None:
            return "No wallet address specified."

        try:
            wallet_pubkey = Pubkey.from_string(wallet_address)

            # Get all token accounts
            response = await self.client.get_token_accounts_by_owner(
                wallet_pubkey, TokenAccountOpts(program_id=TOKEN_PROGRAM_ID)
            )

            if not response.value:
                return f"No token accounts found for wallet {wallet_address}"

            balances = []
            for account in response.value:
                try:
                    balance_response = await self.client.get_token_account_balance(
                        account.pubkey
                    )
                    if balance_response.value:
                        amount = balance_response.value.amount
                        decimals = balance_response.value.decimals
                        ui_amount = int(amount) / (10**decimals)

                        # Get mint from account data
                        account_info = await self.client.get_account_info(
                            account.pubkey
                        )
                        if account_info.value and account_info.value.data:
                            data = base58.b58decode(account_info.value.data)
                            mint = base58.b58encode(data[0:32]).decode()

                            balances.append(
                                {
                                    "mint": mint,
                                    "balance": ui_amount,
                                    "decimals": decimals,
                                    "account": str(account.pubkey),
                                }
                            )
                except Exception:
                    continue

            return {"wallet": wallet_address, "tokens": balances}
        except Exception as e:
            return f"Error getting token balances: {str(e)}"

    async def get_nfts(self, wallet_address: str = None):
        """
        Get all NFTs owned by a wallet.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if wallet_address is None:
            return "No wallet address specified."

        try:
            wallet_pubkey = Pubkey.from_string(wallet_address)

            # Get all token accounts
            response = await self.client.get_token_accounts_by_owner(
                wallet_pubkey, TokenAccountOpts(program_id=TOKEN_PROGRAM_ID)
            )

            nfts = []
            for account in response.value:
                try:
                    balance_response = await self.client.get_token_account_balance(
                        account.pubkey
                    )
                    if balance_response.value:
                        amount = balance_response.value.amount
                        decimals = balance_response.value.decimals

                        # NFTs have supply of 1 and 0 decimals
                        if int(amount) == 1 and decimals == 0:
                            account_info = await self.client.get_account_info(
                                account.pubkey
                            )
                            if account_info.value and account_info.value.data:
                                data = base58.b58decode(account_info.value.data)
                                mint = base58.b58encode(data[0:32]).decode()

                                nfts.append(
                                    {"mint": mint, "tokenAccount": str(account.pubkey)}
                                )
                except Exception:
                    continue

            return {"wallet": wallet_address, "nfts": nfts, "count": len(nfts)}
        except Exception as e:
            return f"Error getting NFTs: {str(e)}"

    async def transfer_nft(self, nft_mint: str, to_wallet: str):
        """
        Transfer an NFT to another wallet.
        """
        # NFTs are just SPL tokens with supply of 1 and 0 decimals
        return await self.send_spl_token(
            from_wallet=self.wallet_address,
            to_wallet=to_wallet,
            token_mint=nft_mint,
            amount="1",
            decimals=0,
        )

    async def stake_sol(self, amount: str, validator: str = None):
        """
        Stake SOL with a validator.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            from_pubkey = Pubkey.from_string(self.wallet_address)
            stake_keypair = Keypair()

            amount_float = float(amount)
            lamports = int(amount_float * 1_000_000_000)

            # Get rent exemption for stake account
            rent_response = await self.client.get_minimum_balance_for_rent_exemption(
                200
            )
            rent_exempt = rent_response

            total_lamports = lamports + rent_exempt

            instructions = []

            # Create stake account instruction
            from solders.system_program import CreateAccountParams, create_account

            create_account_ix = create_account(
                CreateAccountParams(
                    from_pubkey=from_pubkey,
                    to_pubkey=stake_keypair.pubkey(),
                    lamports=total_lamports,
                    space=200,
                    owner=STAKE_PROGRAM_ID,
                )
            )
            instructions.append(create_account_ix)

            # Initialize stake instruction
            initialize_data = bytearray([0])  # Initialize instruction
            initialize_data.extend(bytes(from_pubkey))  # Authorized staker
            initialize_data.extend(bytes(from_pubkey))  # Authorized withdrawer

            initialize_ix = Instruction(
                program_id=STAKE_PROGRAM_ID,
                accounts=[
                    AccountMeta(
                        pubkey=stake_keypair.pubkey(), is_signer=False, is_writable=True
                    ),
                    AccountMeta(
                        pubkey=Pubkey.from_string(
                            "SysvarRent111111111111111111111111111111111"
                        ),
                        is_signer=False,
                        is_writable=False,
                    ),
                ],
                data=bytes(initialize_data),
            )
            instructions.append(initialize_ix)

            # Delegate stake instruction
            if validator:
                validator_pubkey = Pubkey.from_string(validator)
            else:
                # Use a default validator or get from vote accounts
                validators = await self.get_validators()
                if validators and len(validators) > 0:
                    validator_pubkey = Pubkey.from_string(validators[0]["votePubkey"])
                else:
                    return "No validator specified and could not find default validator"

            delegate_data = bytearray([2])  # Delegate instruction
            delegate_ix = Instruction(
                program_id=STAKE_PROGRAM_ID,
                accounts=[
                    AccountMeta(
                        pubkey=stake_keypair.pubkey(), is_signer=False, is_writable=True
                    ),
                    AccountMeta(
                        pubkey=validator_pubkey, is_signer=False, is_writable=False
                    ),
                    AccountMeta(
                        pubkey=Pubkey.from_string(
                            "SysvarC1ock11111111111111111111111111111111"
                        ),
                        is_signer=False,
                        is_writable=False,
                    ),
                    AccountMeta(
                        pubkey=Pubkey.from_string(
                            "SysvarStakeHistory1111111111111111111111111"
                        ),
                        is_signer=False,
                        is_writable=False,
                    ),
                    AccountMeta(
                        pubkey=Pubkey.from_string(
                            "Stake11111111111111111111111111111111111111"
                        ),
                        is_signer=False,
                        is_writable=False,
                    ),
                    AccountMeta(pubkey=from_pubkey, is_signer=True, is_writable=False),
                ],
                data=bytes(delegate_data),
            )
            instructions.append(delegate_ix)

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=from_pubkey,
                instructions=instructions,
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair, stake_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return f"Successfully staked {amount} SOL. Stake account: {stake_keypair.pubkey()}, Signature: {response.value}"

        except Exception as e:
            return f"Error staking SOL: {str(e)}"

    async def get_stake_accounts(self, wallet_address: str = None):
        """
        Get all stake accounts for a wallet.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if wallet_address is None:
            return "No wallet address specified."

        try:
            # Get stake accounts owned by wallet
            response = await self.client.get_program_accounts(
                STAKE_PROGRAM_ID,
                filters=[{"memcmp": {"offset": 12, "bytes": wallet_address}}],
            )

            stake_accounts = []
            for account in response.value:
                stake_accounts.append(
                    {
                        "pubkey": str(account.pubkey),
                        "lamports": account.account.lamports,
                    }
                )

            return {"wallet": wallet_address, "stakeAccounts": stake_accounts}
        except Exception as e:
            return f"Error getting stake accounts: {str(e)}"

    async def deactivate_stake(self, stake_account: str):
        """
        Deactivate a stake account to prepare for withdrawal.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            from_pubkey = Pubkey.from_string(self.wallet_address)
            stake_pubkey = Pubkey.from_string(stake_account)

            # Create deactivate instruction
            deactivate_data = bytearray([5])  # Deactivate instruction

            deactivate_ix = Instruction(
                program_id=STAKE_PROGRAM_ID,
                accounts=[
                    AccountMeta(pubkey=stake_pubkey, is_signer=False, is_writable=True),
                    AccountMeta(
                        pubkey=Pubkey.from_string(
                            "SysvarC1ock11111111111111111111111111111111"
                        ),
                        is_signer=False,
                        is_writable=False,
                    ),
                    AccountMeta(pubkey=from_pubkey, is_signer=True, is_writable=False),
                ],
                data=bytes(deactivate_data),
            )

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=from_pubkey,
                instructions=[deactivate_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return f"Stake account deactivated. It will be available for withdrawal after cooldown period. Signature: {response.value}"

        except Exception as e:
            return f"Error deactivating stake: {str(e)}"

    async def withdraw_stake(self, stake_account: str, amount: str = None):
        """
        Withdraw from a deactivated stake account.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            from_pubkey = Pubkey.from_string(self.wallet_address)
            stake_pubkey = Pubkey.from_string(stake_account)

            # Get stake account info to determine withdrawable amount
            stake_info = await self.client.get_account_info(stake_pubkey)
            if not stake_info.value:
                return f"Stake account not found: {stake_account}"

            # If no amount specified, withdraw all
            if amount is None:
                lamports = stake_info.value.lamports
            else:
                amount_float = float(amount)
                lamports = int(amount_float * 1_000_000_000)

            # Create withdraw instruction
            withdraw_data = bytearray([4])  # Withdraw instruction
            withdraw_data.extend(struct.pack("<Q", lamports))

            withdraw_ix = Instruction(
                program_id=STAKE_PROGRAM_ID,
                accounts=[
                    AccountMeta(pubkey=stake_pubkey, is_signer=False, is_writable=True),
                    AccountMeta(pubkey=from_pubkey, is_signer=False, is_writable=True),
                    AccountMeta(
                        pubkey=Pubkey.from_string(
                            "SysvarC1ock11111111111111111111111111111111"
                        ),
                        is_signer=False,
                        is_writable=False,
                    ),
                    AccountMeta(
                        pubkey=Pubkey.from_string(
                            "SysvarStakeHistory1111111111111111111111111"
                        ),
                        is_signer=False,
                        is_writable=False,
                    ),
                    AccountMeta(pubkey=from_pubkey, is_signer=True, is_writable=False),
                ],
                data=bytes(withdraw_data),
            )

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=from_pubkey,
                instructions=[withdraw_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            sol_amount = lamports / 1_000_000_000
            return f"Successfully withdrew {sol_amount} SOL from stake account. Signature: {response.value}"

        except Exception as e:
            return f"Error withdrawing stake: {str(e)}"

    async def get_token_metadata(self, token_mint: str):
        """
        Get metadata for a token/NFT using Metaplex metadata program.
        """
        try:
            mint_pubkey = Pubkey.from_string(token_mint)

            # Derive metadata PDA
            seeds = [b"metadata", bytes(METADATA_PROGRAM_ID), bytes(mint_pubkey)]

            metadata_pda, _ = Pubkey.find_program_address(seeds, METADATA_PROGRAM_ID)

            # Get metadata account
            account_info = await self.client.get_account_info(metadata_pda)

            if not account_info.value:
                return f"No metadata found for token {token_mint}"

            # Parse metadata (simplified - actual parsing is more complex)
            return {
                "mint": token_mint,
                "metadataAccount": str(metadata_pda),
                "hasMetadata": True,
            }
        except Exception as e:
            return f"Error getting token metadata: {str(e)}"

    def create_memo_instruction(self, memo: str, signer: str) -> Instruction:
        """
        Create a memo instruction to add a message to a transaction.
        """
        signer_pubkey = Pubkey.from_string(signer)

        return Instruction(
            program_id=MEMO_PROGRAM_ID,
            accounts=[
                AccountMeta(pubkey=signer_pubkey, is_signer=True, is_writable=False)
            ],
            data=memo.encode("utf-8"),
        )

    async def get_rent_exempt_balance(self, data_size: int):
        """
        Get the minimum balance required for rent exemption.
        """
        try:
            response = await self.client.get_minimum_balance_for_rent_exemption(
                data_size
            )
            lamports = response
            sol = lamports / 1_000_000_000
            return f"Rent exempt balance for {data_size} bytes: {lamports} lamports ({sol} SOL)"
        except Exception as e:
            return f"Error getting rent exempt balance: {str(e)}"

    async def request_airdrop(
        self, amount_sol: float = 1.0, wallet_address: str = None
    ):
        """
        Request an airdrop of SOL (only works on devnet/testnet).
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if wallet_address is None:
            return "No wallet address specified."

        try:
            pubkey = Pubkey.from_string(wallet_address)
            lamports = int(amount_sol * 1_000_000_000)

            signature = await self.client.request_airdrop(pubkey, lamports)
            return f"Airdrop requested: {amount_sol} SOL. Signature: {signature.value}"
        except Exception as e:
            return f"Error requesting airdrop: {str(e)} (Note: Airdrops only work on devnet/testnet)"

    async def get_token_balance(self, wallet_address: str = None, token_mint: str = ""):
        """
        Retrieves the balance of a specific SPL token for the given wallet.
        """
        if wallet_address is None:
            wallet_address = self.wallet_address
        if wallet_address is None:
            return "No wallet address specified."
        if not token_mint:
            return "No token mint address specified."

        try:
            token_accounts = await self.client.get_token_accounts_by_owner(
                Pubkey.from_string(wallet_address),
                {"mint": Pubkey.from_string(token_mint)},
            )

            if not token_accounts.value:
                return f"No token account found for token {token_mint} in wallet {wallet_address}."

            token_account = token_accounts.value[0].pubkey

            account_info = await self.client.get_token_account_balance(token_account)

            if not account_info.value:
                return f"Error retrieving token balance: No account data found."

            amount = account_info.value.amount
            decimals = account_info.value.decimals

            token_balance = int(amount) / (10**decimals)

            return f"Token {token_mint} balance in wallet {wallet_address}: {token_balance}"
        except Exception as e:
            return f"Error retrieving token balance: {str(e)}"

    async def get_public_key(self):
        """
        Get the public key of the current wallet.
        """
        if self.wallet_address:
            return {"public_key": self.wallet_address}
        return {"error": "No wallet initialized"}

    async def get_token_list(self):
        """
        Get a list of supported tokens from Jupiter API.
        """
        try:
            response = requests.get(f"{self.JUPITER_API_BASE_URL}/tokens")
            if response.status_code == 200:
                return response.json()
            else:
                return f"Error getting token list: HTTP status {response.status_code}"
        except Exception as e:
            return f"Error getting token list: {str(e)}"

    async def get_jupiter_swap_quote(
        self, input_mint: str, output_mint: str, amount: str, slippage_bps: int = 100
    ):
        """
        Get a swap quote from Jupiter API.

        Returns:
            dict: The swap quote with details or an error message
        """
        try:

            amount_value = amount

            params = {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": amount_value,
                "slippageBps": slippage_bps,
                "onlyDirectRoutes": "false",
                "platformFeeBps": 0,
            }

            response = requests.get(f"{self.JUPITER_API_BASE_URL}/quote", params=params)

            if response.status_code != 200:
                return f"Error getting swap quote: {response.status_code} - {response.text}"

            quote_data = response.json()

            return {
                "inputAmount": quote_data.get("inputAmount"),
                "outputAmount": quote_data.get("outputAmount"),
                "otherAmountThreshold": quote_data.get("otherAmountThreshold"),
                "priceImpactPct": quote_data.get("priceImpactPct"),
                "marketInfos": quote_data.get("marketInfos", []),
                "routePlan": quote_data.get("routePlan", []),
                "quoteResponse": quote_data,
            }
        except Exception as e:
            return f"Error getting Jupiter swap quote: {str(e)}"

    async def execute_jupiter_swap(
        self,
        quote_response: Dict[str, Any] = None,
    ):
        """
        Execute a token swap using Jupiter API and SDK.

        Args:
            quote_response (Dict): The quote response from get_jupiter_swap_quote

        Returns:
            dict: The result of the swap with transaction signature or an error message
        """
        if not self.wallet_address or not self.wallet_keypair:
            return (
                "No wallet initialized. Please initialize with SOLANA_WALLET_API_KEY."
            )

        if not quote_response or "quoteResponse" not in quote_response:
            return "Invalid quote response. Please get a quote first."

        try:

            swap_request = {
                "quoteResponse": quote_response["quoteResponse"],
                "userPublicKey": self.wallet_address,
                "wrapAndUnwrapSol": True,
            }

            swap_response = requests.post(
                f"{self.JUPITER_API_BASE_URL}/swap", json=swap_request
            )

            if swap_response.status_code != 200:
                return f"Error getting swap transaction: {swap_response.status_code} - {swap_response.text}"

            swap_data = swap_response.json()

            if "swapTransaction" not in swap_data:
                return f"Invalid swap response: Missing swapTransaction field - {swap_data}"

            serialized_tx = swap_data["swapTransaction"]

            import base64

            tx_bytes = base64.b64decode(serialized_tx)

            versioned_tx = VersionedTransaction.from_bytes(tx_bytes)

            versioned_tx.sign([self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(versioned_tx, opts=opts)
            tx_signature = response.value

            return {
                "success": True,
                "signature": tx_signature,
                "inputMint": quote_response["quoteResponse"]["inputMint"],
                "outputMint": quote_response["quoteResponse"]["outputMint"],
                "inputAmount": quote_response["inputAmount"],
                "outputAmount": quote_response["outputAmount"],
                "priceImpactPct": quote_response["priceImpactPct"],
            }
        except Exception as e:
            return f"Error executing Jupiter swap: {str(e)}"

    async def get_transaction_info(self, tx_signature: str):
        """
        Retrieves information about a specific transaction using its signature.
        """
        try:
            # Convert string signature to Signature type if needed
            sig = (
                Signature.from_string(tx_signature)
                if isinstance(tx_signature, str)
                else tx_signature
            )
            response = await self.client.get_transaction(sig, commitment=Confirmed)

            if response.value:
                # Format transaction info
                tx_info = {
                    "signature": tx_signature,
                    "slot": response.value.slot,
                    "blockTime": response.value.block_time,
                    "fee": response.value.meta.fee if response.value.meta else None,
                    "status": (
                        "Success"
                        if response.value.meta and response.value.meta.err is None
                        else "Failed"
                    ),
                }

                if response.value.meta and response.value.meta.err:
                    tx_info["error"] = response.value.meta.err

                return tx_info
            else:
                return f"Transaction not found: {tx_signature}"
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

            transactions = []
            for sig_info in response.value:
                transactions.append(
                    {
                        "signature": str(sig_info.signature),
                        "slot": sig_info.slot,
                        "blockTime": sig_info.block_time,
                        "confirmationStatus": sig_info.confirmation_status,
                        "err": sig_info.err,
                    }
                )

            return {
                "wallet": wallet_address,
                "transactions": transactions,
                "count": len(transactions),
            }
        except Exception as e:
            return f"Error retrieving recent transactions: {str(e)}"

    async def get_validators(self, limit: int = 10):
        """
        Get a list of validators for staking.
        """
        try:
            # Get vote accounts
            response = await self.client.get_vote_accounts()

            validators = []
            for vote_account in response.value.current[:limit]:
                validators.append(
                    {
                        "votePubkey": str(vote_account.vote_pubkey),
                        "nodePubkey": str(vote_account.node_pubkey),
                        "activatedStake": vote_account.activated_stake,
                        "commission": vote_account.commission,
                        "lastVote": vote_account.last_vote,
                        "rootSlot": vote_account.root_slot,
                    }
                )

            return validators
        except Exception as e:
            return f"Error getting validators: {str(e)}"

    async def set_priority_fee_instruction(
        self, micro_lamports: int = 1000
    ) -> Instruction:
        """
        Create a compute budget instruction to set priority fee for a transaction.
        """
        COMPUTE_BUDGET_PROGRAM_ID = Pubkey.from_string(
            "ComputeBudget111111111111111111111111111111"
        )

        # SetComputeUnitPrice instruction
        data = bytearray([3])  # Instruction index for SetComputeUnitPrice
        data.extend(struct.pack("<Q", micro_lamports))

        return Instruction(
            program_id=COMPUTE_BUDGET_PROGRAM_ID, accounts=[], data=bytes(data)
        )

    async def get_priority_fee_estimate(self):
        """
        Get an estimate for priority fees based on recent blocks.
        """
        try:
            # Get recent performance samples
            response = await self.client.get_recent_performance_samples(limit=5)

            if response.value:
                # Calculate average from recent samples
                total_units = sum(sample.num_transactions for sample in response.value)
                if total_units > 0:
                    # Estimate based on recent activity
                    base_fee = 1000  # micro lamports
                    if total_units > 1000:
                        multiplier = min(total_units / 1000, 10)
                        suggested_fee = int(base_fee * multiplier)
                    else:
                        suggested_fee = base_fee

                    return {
                        "suggested_priority_fee": suggested_fee,
                        "unit": "micro_lamports",
                        "recent_tx_count": total_units,
                    }

            return {
                "suggested_priority_fee": 1000,
                "unit": "micro_lamports",
                "note": "Default estimate",
            }
        except Exception as e:
            return f"Error estimating priority fee: {str(e)}"

    async def create_token_mint(
        self,
        decimals: int = 9,
        freeze_authority: str = None,
        mint_authority: str = None,
    ):
        """
        Create a new SPL token mint.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            payer = Pubkey.from_string(self.wallet_address)
            mint_keypair = Keypair()

            if mint_authority is None:
                mint_authority = self.wallet_address
            if freeze_authority is None:
                freeze_authority = self.wallet_address

            mint_auth_pubkey = Pubkey.from_string(mint_authority)
            freeze_auth_pubkey = (
                Pubkey.from_string(freeze_authority) if freeze_authority else None
            )

            # Get rent exemption for mint account
            rent_response = await self.client.get_minimum_balance_for_rent_exemption(82)
            rent_lamports = rent_response

            instructions = []

            # Create account for mint
            from solders.system_program import CreateAccountParams, create_account

            create_account_ix = create_account(
                CreateAccountParams(
                    from_pubkey=payer,
                    to_pubkey=mint_keypair.pubkey(),
                    lamports=rent_lamports,
                    space=82,
                    owner=TOKEN_PROGRAM_ID,
                )
            )
            instructions.append(create_account_ix)

            # Initialize mint instruction
            init_mint_data = bytearray([TokenInstruction.INITIALIZE_MINT])
            init_mint_data.append(decimals)
            init_mint_data.extend(bytes(mint_auth_pubkey))

            # Option for freeze authority
            if freeze_auth_pubkey:
                init_mint_data.append(1)  # Some
                init_mint_data.extend(bytes(freeze_auth_pubkey))
            else:
                init_mint_data.append(0)  # None

            init_mint_keys = [
                AccountMeta(
                    pubkey=mint_keypair.pubkey(), is_signer=False, is_writable=True
                ),
                AccountMeta(
                    pubkey=Pubkey.from_string(
                        "SysvarRent111111111111111111111111111111111"
                    ),
                    is_signer=False,
                    is_writable=False,
                ),
            ]

            init_mint_ix = Instruction(
                program_id=TOKEN_PROGRAM_ID,
                accounts=init_mint_keys,
                data=bytes(init_mint_data),
            )
            instructions.append(init_mint_ix)

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=payer,
                instructions=instructions,
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair, mint_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return {
                "mint": str(mint_keypair.pubkey()),
                "decimals": decimals,
                "mintAuthority": mint_authority,
                "freezeAuthority": freeze_authority,
                "signature": str(response.value),
            }
        except Exception as e:
            return f"Error creating token mint: {str(e)}"

    async def mint_tokens(
        self, mint: str, destination: str, amount: str, decimals: int = None
    ):
        """
        Mint new tokens to a destination account.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            mint_pubkey = Pubkey.from_string(mint)
            dest_pubkey = Pubkey.from_string(destination)
            authority_pubkey = Pubkey.from_string(self.wallet_address)

            if decimals is None:
                decimals = await self._get_token_decimals(mint_pubkey)

            amount_float = float(amount)
            amount_base = int(amount_float * (10**decimals))

            # Create mint to instruction
            mint_to_data = bytearray([TokenInstruction.MINT_TO_CHECKED])
            mint_to_data.extend(struct.pack("<Q", amount_base))
            mint_to_data.append(decimals)

            mint_to_keys = [
                AccountMeta(pubkey=mint_pubkey, is_signer=False, is_writable=True),
                AccountMeta(pubkey=dest_pubkey, is_signer=False, is_writable=True),
                AccountMeta(pubkey=authority_pubkey, is_signer=True, is_writable=False),
            ]

            mint_to_ix = Instruction(
                program_id=TOKEN_PROGRAM_ID,
                accounts=mint_to_keys,
                data=bytes(mint_to_data),
            )

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=authority_pubkey,
                instructions=[mint_to_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return f"Successfully minted {amount} tokens. Signature: {response.value}"
        except Exception as e:
            return f"Error minting tokens: {str(e)}"

    async def get_program_accounts(self, program_id: str, filters: list = None):
        """
        Get all accounts owned by a specific program.
        """
        try:
            program_pubkey = Pubkey.from_string(program_id)

            if filters:
                response = await self.client.get_program_accounts(
                    program_pubkey, filters=filters
                )
            else:
                response = await self.client.get_program_accounts(program_pubkey)

            accounts = []
            for account_info in response.value:
                accounts.append(
                    {
                        "pubkey": str(account_info.pubkey),
                        "lamports": account_info.account.lamports,
                        "owner": str(account_info.account.owner),
                        "executable": account_info.account.executable,
                        "rent_epoch": account_info.account.rent_epoch,
                    }
                )

            return {"program": program_id, "accounts": accounts, "count": len(accounts)}
        except Exception as e:
            return f"Error getting program accounts: {str(e)}"

    async def create_multisig_account(self, signers: List[str], threshold: int):
        """
        Create a multisig account for SPL tokens.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            payer = Pubkey.from_string(self.wallet_address)
            multisig_keypair = Keypair()

            # Validate threshold
            if threshold < 1 or threshold > len(signers):
                return "Invalid threshold. Must be between 1 and number of signers."

            if len(signers) > 11:
                return "Maximum 11 signers allowed for multisig."

            # Get rent exemption
            space = 355  # Multisig account size
            rent_response = await self.client.get_minimum_balance_for_rent_exemption(
                space
            )
            rent_lamports = rent_response

            instructions = []

            # Create account
            from solders.system_program import CreateAccountParams, create_account

            create_account_ix = create_account(
                CreateAccountParams(
                    from_pubkey=payer,
                    to_pubkey=multisig_keypair.pubkey(),
                    lamports=rent_lamports,
                    space=space,
                    owner=TOKEN_PROGRAM_ID,
                )
            )
            instructions.append(create_account_ix)

            # Initialize multisig
            init_multisig_data = bytearray([TokenInstruction.INITIALIZE_MULTISIG])
            init_multisig_data.append(threshold)

            init_multisig_keys = [
                AccountMeta(
                    pubkey=multisig_keypair.pubkey(), is_signer=False, is_writable=True
                ),
                AccountMeta(
                    pubkey=Pubkey.from_string(
                        "SysvarRent111111111111111111111111111111111"
                    ),
                    is_signer=False,
                    is_writable=False,
                ),
            ]

            # Add signers
            for signer in signers:
                init_multisig_keys.append(
                    AccountMeta(
                        pubkey=Pubkey.from_string(signer),
                        is_signer=False,
                        is_writable=False,
                    )
                )

            init_multisig_ix = Instruction(
                program_id=TOKEN_PROGRAM_ID,
                accounts=init_multisig_keys,
                data=bytes(init_multisig_data),
            )
            instructions.append(init_multisig_ix)

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=payer,
                instructions=instructions,
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair, multisig_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return {
                "multisig": str(multisig_keypair.pubkey()),
                "signers": signers,
                "threshold": threshold,
                "signature": str(response.value),
            }
        except Exception as e:
            return f"Error creating multisig account: {str(e)}"

    async def get_token_supply(self, mint: str):
        """
        Get the current supply of a token.
        """
        try:
            mint_pubkey = Pubkey.from_string(mint)
            response = await self.client.get_token_supply(mint_pubkey)

            if response.value:
                return {
                    "mint": mint,
                    "supply": response.value.amount,
                    "decimals": response.value.decimals,
                    "uiAmount": response.value.ui_amount,
                    "uiAmountString": response.value.ui_amount_string,
                }
            else:
                return f"Could not get supply for token {mint}"
        except Exception as e:
            return f"Error getting token supply: {str(e)}"

    async def freeze_token_account(self, token_account: str, mint: str):
        """
        Freeze a token account.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            account_pubkey = Pubkey.from_string(token_account)
            mint_pubkey = Pubkey.from_string(mint)
            authority_pubkey = Pubkey.from_string(self.wallet_address)

            # Create freeze account instruction
            freeze_data = bytearray([TokenInstruction.FREEZE_ACCOUNT])

            freeze_keys = [
                AccountMeta(pubkey=account_pubkey, is_signer=False, is_writable=True),
                AccountMeta(pubkey=mint_pubkey, is_signer=False, is_writable=False),
                AccountMeta(pubkey=authority_pubkey, is_signer=True, is_writable=False),
            ]

            freeze_ix = Instruction(
                program_id=TOKEN_PROGRAM_ID,
                accounts=freeze_keys,
                data=bytes(freeze_data),
            )

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=authority_pubkey,
                instructions=[freeze_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return f"Token account frozen successfully. Signature: {response.value}"
        except Exception as e:
            return f"Error freezing token account: {str(e)}"

    async def thaw_token_account(self, token_account: str, mint: str):
        """
        Thaw a frozen token account.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            account_pubkey = Pubkey.from_string(token_account)
            mint_pubkey = Pubkey.from_string(mint)
            authority_pubkey = Pubkey.from_string(self.wallet_address)

            # Create thaw account instruction
            thaw_data = bytearray([TokenInstruction.THAW_ACCOUNT])

            thaw_keys = [
                AccountMeta(pubkey=account_pubkey, is_signer=False, is_writable=True),
                AccountMeta(pubkey=mint_pubkey, is_signer=False, is_writable=False),
                AccountMeta(pubkey=authority_pubkey, is_signer=True, is_writable=False),
            ]

            thaw_ix = Instruction(
                program_id=TOKEN_PROGRAM_ID, accounts=thaw_keys, data=bytes(thaw_data)
            )

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=authority_pubkey,
                instructions=[thaw_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return f"Token account thawed successfully. Signature: {response.value}"
        except Exception as e:
            return f"Error thawing token account: {str(e)}"

    async def get_slot(self):
        """
        Get the current slot.
        """
        try:
            response = await self.client.get_slot()
            return {"slot": response}
        except Exception as e:
            return f"Error getting slot: {str(e)}"

    async def get_block_height(self):
        """
        Get the current block height.
        """
        try:
            response = await self.client.get_block_height()
            return {"blockHeight": response}
        except Exception as e:
            return f"Error getting block height: {str(e)}"

    async def get_epoch_info(self):
        """
        Get information about the current epoch.
        """
        try:
            response = await self.client.get_epoch_info()
            return {
                "epoch": response.epoch,
                "slotIndex": response.slot_index,
                "slotsInEpoch": response.slots_in_epoch,
                "absoluteSlot": response.absolute_slot,
                "blockHeight": response.block_height,
                "transactionCount": response.transaction_count,
            }
        except Exception as e:
            return f"Error getting epoch info: {str(e)}"

    async def simulate_transaction(
        self, instructions: List[Instruction], signers: List[str] = None
    ):
        """
        Simulate a transaction without sending it.
        """
        if self.wallet_address is None:
            return "No wallet address available."

        try:
            payer = Pubkey.from_string(self.wallet_address)

            # Build transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=payer,
                instructions=instructions,
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            # Create unsigned transaction for simulation
            tx = VersionedTransaction(msg, [])

            # Simulate
            response = await self.client.simulate_transaction(tx)

            if response.value:
                result = {
                    "err": response.value.err,
                    "logs": response.value.logs,
                    "unitsConsumed": response.value.units_consumed,
                }

                if response.value.err:
                    result["status"] = "Failed"
                else:
                    result["status"] = "Success"

                return result
            else:
                return "Simulation failed: No response"
        except Exception as e:
            return f"Error simulating transaction: {str(e)}"

    async def get_token_largest_accounts(self, mint: str, limit: int = 20):
        """
        Get the largest token accounts for a specific mint.
        """
        try:
            mint_pubkey = Pubkey.from_string(mint)
            response = await self.client.get_token_largest_accounts(mint_pubkey)

            if response.value:
                accounts = []
                for account in response.value[:limit]:
                    accounts.append(
                        {
                            "address": str(account.address),
                            "amount": account.amount,
                            "decimals": account.decimals,
                            "uiAmount": account.ui_amount,
                            "uiAmountString": account.ui_amount_string,
                        }
                    )

                return {"mint": mint, "largestAccounts": accounts}
            else:
                return f"No accounts found for token {mint}"
        except Exception as e:
            return f"Error getting token largest accounts: {str(e)}"

    async def partial_sign_transaction(self, serialized_tx: str):
        """
        Partially sign a transaction (for multisig).
        """
        if self.wallet_keypair is None:
            return "No wallet keypair available."

        try:
            # Deserialize transaction
            import base64

            tx_bytes = base64.b64decode(serialized_tx)
            tx = VersionedTransaction.from_bytes(tx_bytes)

            # Sign with our keypair
            tx.sign([self.wallet_keypair])

            # Serialize back
            signed_tx = base64.b64encode(bytes(tx)).decode()

            return {"partiallySignedTx": signed_tx, "signer": self.wallet_address}
        except Exception as e:
            return f"Error partially signing transaction: {str(e)}"

    async def get_address_lookup_table(self, table_address: str):
        """
        Get the contents of an address lookup table.
        """
        try:
            table_pubkey = Pubkey.from_string(table_address)
            account_info = await self.client.get_account_info(table_pubkey)

            if account_info.value and account_info.value.data:
                # Parse lookup table data (simplified)
                data = base58.b58decode(account_info.value.data)

                # Extract addresses (this is a simplified version)
                addresses = []
                offset = 56  # Skip header
                while offset + 32 <= len(data):
                    addr_bytes = data[offset : offset + 32]
                    addresses.append(base58.b58encode(addr_bytes).decode())
                    offset += 32

                return {
                    "tableAddress": table_address,
                    "addresses": addresses,
                    "count": len(addresses),
                }
            else:
                return f"Address lookup table not found: {table_address}"
        except Exception as e:
            return f"Error getting address lookup table: {str(e)}"

    async def create_address_lookup_table(self, authority: str = None):
        """
        Create a new address lookup table.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            payer = Pubkey.from_string(self.wallet_address)
            if authority is None:
                authority = self.wallet_address
            authority_pubkey = Pubkey.from_string(authority)

            # Address Lookup Table Program ID
            LOOKUP_TABLE_PROGRAM_ID = Pubkey.from_string(
                "AddressLookupTab1e1111111111111111111111111"
            )

            # Get recent slot
            slot = await self.client.get_slot()

            # Derive lookup table address
            slot_bytes = struct.pack("<Q", slot)
            seeds = [bytes(authority_pubkey), slot_bytes]
            lookup_table_address, bump = Pubkey.find_program_address(
                seeds, LOOKUP_TABLE_PROGRAM_ID
            )

            # Create lookup table instruction
            # Instruction: CreateLookupTable
            create_data = bytearray([0])  # Create instruction
            create_data.extend(struct.pack("<Q", slot))
            create_data.append(bump)

            create_keys = [
                AccountMeta(
                    pubkey=lookup_table_address, is_signer=False, is_writable=True
                ),
                AccountMeta(pubkey=authority_pubkey, is_signer=True, is_writable=False),
                AccountMeta(pubkey=payer, is_signer=True, is_writable=True),
                AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
            ]

            create_ix = Instruction(
                program_id=LOOKUP_TABLE_PROGRAM_ID,
                accounts=create_keys,
                data=bytes(create_data),
            )

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=payer,
                instructions=[create_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return {
                "lookupTableAddress": str(lookup_table_address),
                "authority": authority,
                "signature": str(response.value),
            }
        except Exception as e:
            return f"Error creating address lookup table: {str(e)}"

    async def extend_address_lookup_table(
        self, table_address: str, new_addresses: List[str]
    ):
        """
        Extend an address lookup table with new addresses.
        """
        if self.wallet_address is None or self.wallet_keypair is None:
            return "No wallet or private key available."

        try:
            payer = Pubkey.from_string(self.wallet_address)
            table_pubkey = Pubkey.from_string(table_address)

            # Address Lookup Table Program ID
            LOOKUP_TABLE_PROGRAM_ID = Pubkey.from_string(
                "AddressLookupTab1e1111111111111111111111111"
            )

            # Convert addresses to pubkeys
            new_pubkeys = [Pubkey.from_string(addr) for addr in new_addresses]

            # Create extend instruction
            # Instruction: ExtendLookupTable
            extend_data = bytearray([1])  # Extend instruction
            extend_data.extend(struct.pack("<Q", len(new_pubkeys)))
            for pubkey in new_pubkeys:
                extend_data.extend(bytes(pubkey))

            extend_keys = [
                AccountMeta(pubkey=table_pubkey, is_signer=False, is_writable=True),
                AccountMeta(
                    pubkey=payer, is_signer=True, is_writable=False
                ),  # Authority
                AccountMeta(pubkey=payer, is_signer=True, is_writable=True),
                AccountMeta(pubkey=SYS_PROGRAM_ID, is_signer=False, is_writable=False),
            ]

            extend_ix = Instruction(
                program_id=LOOKUP_TABLE_PROGRAM_ID,
                accounts=extend_keys,
                data=bytes(extend_data),
            )

            # Build and send transaction
            blockhash_response = await self.client.get_latest_blockhash(
                commitment=Confirmed
            )
            recent_blockhash = blockhash_response.value.blockhash

            msg = MessageV0.try_compile(
                payer=payer,
                instructions=[extend_ix],
                address_lookup_table_accounts=[],
                recent_blockhash=recent_blockhash,
            )

            tx = VersionedTransaction(msg, [self.wallet_keypair])

            opts = TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
            response = await self.client.send_transaction(tx, opts=opts)

            return {
                "tableAddress": table_address,
                "addedAddresses": new_addresses,
                "count": len(new_addresses),
                "signature": str(response.value),
            }
        except Exception as e:
            return f"Error extending address lookup table: {str(e)}"
