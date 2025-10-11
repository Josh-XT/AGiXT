# Wallet Authentication for AGiXT

This document describes the complete wallet-based authentication and interaction system for AGiXT, allowing users to log in using their crypto wallets and enabling AI agents to interact with user wallets.

## Overview

The wallet authentication system provides a complete Web3 integration that:
1. Allows users to authenticate using their crypto wallets (login)
2. Enables AI agents to interact with the user's connected wallet (transactions)

This is implemented as an extension that integrates with AGiXT's existing authentication infrastructure while providing wallet functionality that works with the user's wallet (not the agent's wallet).

## Architecture

### Key Distinction: User Wallet vs Agent Wallet

- **Agent Wallet** (`solana_wallet.py`): Uses private keys stored during agent creation, can sign transactions directly
- **User Wallet** (`wallet.py`): Never has access to private keys, prepares transactions for browser signing

### Components

1. **Backend Extension** (`agixt/extensions/wallet.py`)
   - FastAPI endpoints for authentication
   - AI commands for wallet operations
   - Signature verification (Ed25519 for Solana, EIP-191 for EVM)
   - Transaction preparation (not execution)

2. **Frontend Component** (`components/auth/WalletAuth.tsx`)
   - Auto-detects installed wallet extensions
   - Manages wallet connection flow
   - Handles signature requests
   - Executes prepared transactions

3. **Authentication Endpoints**
   - `/v1/wallet/providers` - Lists supported wallet providers
   - `/v1/wallet/nonce` - Generates authentication nonce
   - `/v1/wallet/verify` - Verifies wallet signature and creates session
   - `/v1/wallet/session` - Gets wallet session information

## Supported Wallets & Chains

### Wallet Providers
- **Phantom** - Primary Solana wallet, also supports Ethereum/Polygon
- **Brave Wallet** - Multi-chain support
- **MetaMask** - EVM chains (Ethereum, Polygon, BSC, Avalanche, Arbitrum, Optimism)
- **Solflare** - Solana-specific wallet
- **Solana Mobile Wallet (Seeker Vault)** - Native wallet shipping with Solana Mobile devices

### Blockchain Support
- **Full Support**: Solana (authentication + all operations)
- **Auth Only**: EVM chains (operations can be added)

## Implementation Details

### Authentication Flow

1. User clicks "Continue with Wallet" on login page
2. Frontend component detects available wallets
3. User connects wallet and selects account
4. Backend generates nonce and signing message
5. User signs message in wallet (no transaction, just signature)
6. Backend verifies signature cryptographically
7. User account created/retrieved with synthetic email: `wallet_address@crypto.wallet`
8. JWT session established like any other login

### AI Wallet Commands

The extension provides commands that prepare transactions for user signing:

```python
# Available AI commands
"Get Connected Wallet Info"      # Gets wallet details from session
"Get Connected Wallet Balance"   # Checks SOL balance on-chain
"Prepare SOL Transfer"           # Returns transaction params for frontend
"Prepare Token Transfer"         # Prepares SPL token transfers
"Get Connected Wallet Tokens"    # Lists all tokens in wallet
"Prepare Swap Transaction"       # Gets Jupiter quotes and prepares swaps
```

### Transaction Flow

1. **AI Prepares**: AI uses commands to prepare transaction parameters
2. **Frontend Builds**: JavaScript constructs actual transaction
3. **User Signs**: Wallet popup for user approval
4. **Frontend Submits**: Signed transaction sent to blockchain

Example command result:
```json
{
  "success": true,
  "action": "transfer_sol",
  "requires_signature": true,
  "transaction": {
    "from": "8Ujmb...",
    "to": "5TQwK...",
    "amount": 1000000000,
    "unit": "lamports",
    "display_amount": "1 SOL"
  },
  "message": "Prepare to transfer 1 SOL to 5TQwK..."
}
```

## Security Features

### Authentication Security
- **Nonce-based**: Unique nonce expires in 5 minutes, prevents replay attacks
- **Cryptographic verification**: Ed25519 (Solana) or EIP-191 (Ethereum) signatures
- **No passwords**: Wallet signature serves as authentication
- **Session management**: Standard JWT after successful auth

### Transaction Security
- **No private key access**: Extension never sees or stores private keys
- **User approval required**: Every transaction needs explicit wallet signature
- **Read-only operations**: Balance checks don't require signatures
- **Transparent operations**: User sees exactly what they're signing

## Installation & Configuration

### Backend Setup

1. Install dependencies:
```bash
pip install PyNaCl>=1.5.0 eth-account>=0.13.0 base58 solana
```

2. Extension auto-loads if dependencies are met

### Frontend Setup

1. Component is already integrated in `/app/user/page.tsx`
2. Works alongside existing OAuth providers
3. Auto-detects wallet extensions

## Usage Examples

### For Users

1. **Login**:
   - Go to login page
   - Click "Continue with Wallet"
   - Connect wallet when prompted
   - Sign authentication message
   - You're logged in!

2. **Using AI with Wallet**:
   ```
   User: "Check my wallet balance"
   AI: [Uses Get Connected Wallet Balance command]
   AI: "Your wallet has 5.23 SOL"
   
   User: "Send 1 SOL to address ABC123..."
   AI: [Uses Prepare SOL Transfer command]
   AI: "I've prepared a transaction to send 1 SOL. Please approve it in your wallet."
   [Wallet popup appears for signature]
   ```

### For Developers

```python
# Initialize extension with user context
wallet_ext = wallet(
    user_email="wallet_address@crypto.wallet"
)

# Get wallet info
info = await wallet_ext.get_connected_wallet_info()

# Check balance
balance = await wallet_ext.get_connected_wallet_balance()

# Prepare transfer (returns data for frontend)
transfer = await wallet_ext.prepare_sol_transfer(
    to_address="...",
    amount=1.0
)
```

## API Reference

### FastAPI Endpoints

#### GET /v1/wallet/providers
Returns list of supported wallet providers and their configurations.

#### POST /v1/wallet/nonce
Generates a nonce for wallet authentication.
- Body: `{"wallet_address": "...", "chain": "solana"}`
- Returns: `{"nonce": "...", "message": "...", "timestamp": "..."}`

#### POST /v1/wallet/verify
Verifies wallet signature and creates user session.
- Body: `{"wallet_address": "...", "signature": "...", "message": "...", "nonce": "...", "wallet_type": "phantom", "chain": "solana"}`
- Returns: JWT token and session details

#### GET /v1/wallet/session
Gets current wallet session information (requires auth).

### AI Commands

All commands return dictionaries with `success` boolean and relevant data or error messages.

#### Get Connected Wallet Info
Returns wallet address, type, chain, and email from user session.

#### Get Connected Wallet Balance
Returns current SOL balance (or error for unsupported chains).

#### Prepare SOL Transfer
- Parameters: `to_address`, `amount`
- Returns: Transaction parameters for frontend signing

#### Prepare Token Transfer
- Parameters: `to_address`, `token_mint`, `amount`, `decimals`
- Returns: SPL token transfer parameters

#### Get Connected Wallet Tokens
Returns list of all SPL tokens with balances.

#### Prepare Swap Transaction
- Parameters: `input_mint`, `output_mint`, `amount`, `slippage_bps`
- Returns: Jupiter swap quote and parameters

## Testing

### Backend Testing
```python
# Test nonce generation
pytest AGiXT/tests/extensions/test_wallet.py::test_nonce_generation

# Test signature verification
pytest AGiXT/tests/extensions/test_wallet.py::test_signature_verification

# Test wallet commands
pytest AGiXT/tests/extensions/test_wallet.py::test_wallet_commands
```

### Frontend Testing
```javascript
// Test wallet detection
npm run test -- WalletAuth.test.tsx

// E2E test
npm run e2e:wallet-login
```

### Manual Testing Checklist
- [ ] Wallet detection works for all supported wallets
- [ ] Login flow completes successfully
- [ ] Session persists across page refreshes
- [ ] Wallet commands return correct data
- [ ] Transaction preparation works
- [ ] Error handling for declined signatures
- [ ] Logout clears wallet session

## File Structure

### Backend Files
```
AGiXT/
├── agixt/
│   └── extensions/
│       └── wallet.py           # Main wallet extension with auth & commands
├── requirements.txt            # Updated with PyNaCl, eth-account, base58
└── docs/
    └── wallet_authentication.md # This documentation
```

### Frontend Files
```
web/
├── components/
│   └── auth/
│       └── WalletAuth.tsx     # Wallet authentication component
└── app/
    └── user/
        └── page.tsx           # Login page with wallet integration
```

## Troubleshooting

### Common Issues

1. **"No wallet detected"**
   - Ensure wallet extension is installed
   - Check browser compatibility
   - Try refreshing the page

2. **"Invalid signature"**
   - Ensure correct chain selected in wallet
   - Check wallet is unlocked
   - Verify correct account selected

3. **"Transaction preparation failed"**
   - Check wallet has sufficient balance
   - Verify correct network (mainnet vs devnet)
   - Ensure RPC endpoint is responsive

## Key Implementation Highlights

### What Makes This Different
1. **User Custody**: Unlike `solana_wallet.py` which uses agent's private keys, this extension never has access to user's keys
2. **Transaction Preparation**: Commands return parameters for frontend to build transactions
3. **Browser Signing**: All signatures happen in the browser wallet extension
4. **Session Integration**: Wallet users are treated like any other authenticated user

### Security Best Practices
1. Nonces expire after 5 minutes
2. Each nonce can only be used once
3. Signatures are cryptographically verified
4. No sensitive data stored (only public addresses)
5. Standard JWT session management after auth

## Future Enhancements

### Planned Features
- [ ] Hardware wallet support (Ledger, Trezor)
- [ ] Multi-signature wallet support
- [ ] EVM chain transaction support (currently auth only)
- [ ] WebSocket updates for transaction status
- [ ] Wallet portfolio analytics
- [ ] Cross-chain swaps via Wormhole
- [ ] NFT gallery and management
- [ ] DeFi protocol integrations
- [ ] Mobile wallet support (WalletConnect)
- [ ] Transaction history tracking

## Contributing

To add support for a new wallet:

1. Add wallet configuration to `WALLET_PROVIDERS` in `wallet.py`
2. Implement signature verification if using different algorithm
3. Update frontend detection in `WalletAuth.tsx`
4. Add tests for new wallet type
5. Update this documentation

## Pull Request Checklist

When submitting PRs for wallet authentication:

### Backend PR
- [ ] `wallet.py` extension with auth endpoints and AI commands
- [ ] Updated `requirements.txt` with wallet dependencies
- [ ] This documentation file
- [ ] No changes to `Auth.py` (endpoints in extension)
- [ ] Test coverage for wallet operations

### Frontend PR
- [ ] `WalletAuth.tsx` component
- [ ] Updated `user/page.tsx` with wallet integration
- [ ] Auto-detection logic for wallets
- [ ] Error handling for wallet operations
- [ ] TypeScript types for wallet data

## License

This wallet authentication system is part of AGiXT and follows the same licensing terms.
