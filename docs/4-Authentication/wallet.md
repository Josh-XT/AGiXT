````markdown
# Wallet (Crypto) Sign-In Integration

## Overview

This module provides signature-based authentication for cryptocurrency wallets, allowing users to authenticate using their blockchain wallet addresses. This supports various wallet types including Phantom (Solana), MetaMask (Ethereum/EVM), and other compatible wallets.

## How It Works

Unlike traditional OAuth, wallet authentication uses cryptographic signatures:

1. Server generates a unique nonce (one-time message)
2. User signs the nonce with their wallet's private key
3. Server verifies the signature against the wallet's public address
4. User is authenticated without sharing any sensitive information

## Supported Chains and Wallets

### Solana
- Phantom Wallet
- Brave Wallet (Solana mode)
- Solflare

### Ethereum/EVM
- MetaMask
- Brave Wallet (Ethereum mode)
- WalletConnect
- Coinbase Wallet
- Rainbow

## No Environment Variables Required

Wallet authentication doesn't require API keys or secrets. The authentication is performed entirely through cryptographic signature verification.

## Authentication Flow

### Step 1: Request Nonce

The client requests a nonce from the server for a specific wallet address.

### Step 2: Sign Message

The user signs the nonce message using their wallet:

```javascript
// Example for Solana (Phantom)
const message = new TextEncoder().encode(nonce);
const signature = await window.solana.signMessage(message, "utf8");

// Example for Ethereum (MetaMask)
const signature = await window.ethereum.request({
  method: 'personal_sign',
  params: [message, walletAddress],
});
```

### Step 3: Verify and Authenticate

The signature is sent to the server, which verifies it matches the wallet address and authenticates the user.

## Security Features

- **Nonce expiration**: Nonces expire after 5 minutes
- **One-time use**: Each nonce can only be used once
- **No private key exposure**: Only signatures are transmitted
- **Address verification**: Signature mathematically proves wallet ownership

## Supported Signature Types

### Solana (Ed25519)
- Uses Ed25519 elliptic curve signatures
- Base58 encoded signatures
- Verified using `nacl` library

### Ethereum (EIP-191)
- Uses secp256k1 signatures
- Hex encoded signatures
- Verified using `eth_account` library

## Features

Once authenticated, users can:

- Link their wallet address to their AGiXT account
- Use wallet-based authentication for future logins
- Access blockchain-specific extensions
- Manage crypto assets through connected wallets

## Client Integration Example

```javascript
// Solana (Phantom) login
async function loginWithPhantom() {
  const provider = window.solana;
  if (!provider?.isPhantom) {
    throw new Error("Phantom wallet not found");
  }
  
  await provider.connect();
  const publicKey = provider.publicKey.toString();
  
  // Get nonce from AGiXT
  const nonceResponse = await fetch(`/api/wallet/nonce?address=${publicKey}`);
  const { nonce } = await nonceResponse.json();
  
  // Sign the nonce
  const message = new TextEncoder().encode(nonce);
  const signature = await provider.signMessage(message, "utf8");
  
  // Submit signature for verification
  const authResponse = await fetch('/api/wallet/verify', {
    method: 'POST',
    body: JSON.stringify({
      address: publicKey,
      signature: signature.signature,
      nonce: nonce,
      chain: 'solana'
    })
  });
  
  return authResponse.json();
}
```

## Security Considerations

- Never reuse nonces
- Implement rate limiting on nonce generation
- Validate wallet address format before processing
- Use HTTPS for all communications
- Consider implementing message prefixes to prevent signature reuse across services
````
