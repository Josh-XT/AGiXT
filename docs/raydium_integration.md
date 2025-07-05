# Raydium Integration for AGiXT

This comprehensive extension provides full integration with Raydium, Solana's leading automated market maker (AMM) and decentralized exchange (DEX).

## 🚀 Features

### Trading & Swapping
- **Token Swapping**: Execute trades between any SPL tokens
- **Swap Quotes**: Get real-time pricing and routing information
- **Best Route Finding**: Automatically find optimal trading paths
- **Slippage Protection**: Configurable slippage tolerance

### Pool Management
- **CLMM Pools**: Create and manage Concentrated Liquidity Market Maker pools
- **CPMM Pools**: Create and manage Constant Product Market Maker pools
- **Pool Analytics**: Comprehensive pool performance metrics
- **Pool Information**: Detailed pool data and statistics

### Liquidity Provision
- **Add Liquidity**: Provide liquidity to existing pools
- **Remove Liquidity**: Withdraw liquidity and collect fees
- **LP Token Management**: Track and manage LP token balances
- **Value Calculation**: Calculate USD value of LP positions

### Farming & Staking
- **Farm Staking**: Stake LP tokens to earn additional rewards
- **Reward Claiming**: Claim accumulated farming rewards
- **Farm Analytics**: Track farm performance and APR
- **User Positions**: Monitor your staking positions

### Authority Management
- **Pool Authority**: Manage pool ownership and permissions
- **Authority Revocation**: Make pools immutable (irreversible)
- **Burn & Earn**: Lock liquidity while retaining fee rights

### Advanced Features
- **Market Making**: Create concentrated liquidity positions
- **Position Management**: Monitor and rebalance positions
- **Analytics**: Comprehensive trading and pool analytics
- **Priority Fees**: Automatic fee optimization

## 📋 Requirements

### Dependencies
```bash
pip install solana solders requests
```

### Environment Variables
```bash
export SOLANA_WALLET_API_KEY="your_private_key_here"
```

## 🔧 Setup

### 1. Install Dependencies
```bash
cd AGiXT
pip install -r requirements.txt
```

### 2. Configure Wallet
Set your Solana wallet private key as an environment variable:
```bash
export SOLANA_WALLET_API_KEY="your_base58_private_key"
```

### 3. Test Connection
Run the example script to verify everything is working:
```bash
python examples/raydium_integration_example.py
```

## 📚 Usage Examples

### Basic Token Swap
```python
from agixt.extensions.raydium_integration import raydium_integration

# Initialize the extension
raydium = raydium_integration(
    SOLANA_WALLET_API_KEY="your_private_key"
)

# Get a swap quote
quote = await raydium.get_swap_quote(
    input_mint="So11111111111111111111111111111111111111112",  # SOL
    output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    amount="1000000000",  # 1 SOL
    slippage_bps=100  # 1% slippage
)

# Execute the swap
result = await raydium.execute_swap(
    input_mint="So11111111111111111111111111111111111111112",
    output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    amount="1000000000",
    slippage_bps=100
)
```

### Pool Analytics
```python
# Get comprehensive pool information
pool_info = await raydium.get_pool_info("58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2")
analytics = await raydium.get_pool_analytics("58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2")
apr_info = await raydium.get_pool_apr("58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2")
tvl_info = await raydium.get_pool_tvl("58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2")
```

### Liquidity Management
```python
# Add liquidity to a pool
result = await raydium.add_liquidity(
    pool_id="58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2",
    base_amount="100000000",  # 0.1 SOL
    quote_amount="10000000",  # 10 USDC
    slippage=0.01  # 1% slippage
)

# Remove liquidity
result = await raydium.remove_liquidity(
    pool_id="58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2",
    lp_amount="1000000",
    slippage=0.01
)
```

### Farm Staking
```python
# Stake LP tokens in a farm
result = await raydium.stake_lp_tokens(
    farm_id="GUzaohfNuFbBqQTnPgPSNciv3aUvriXYjQduRE3ZkqFw",
    lp_amount="1000000"
)

# Claim farming rewards
result = await raydium.claim_farm_rewards(
    farm_id="GUzaohfNuFbBqQTnPgPSNciv3aUvriXYjQduRE3ZkqFw"
)
```

### Pool Creation
```python
# Create a CLMM pool
result = await raydium.create_clmm_pool(
    base_mint="YourTokenMint",
    quote_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    fee_tier=2500,  # 0.25%
    initial_price=1.0
)

# Create a CPMM pool
result = await raydium.create_cpmm_pool(
    base_mint="YourTokenMint",
    quote_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    base_amount="1000000000",
    quote_amount="1000000000"
)
```

## 🎯 Available Commands

### Trading Commands
- `Get Raydium Swap Quote` - Get pricing for token swaps
- `Execute Raydium Swap` - Execute token swaps
- `Get Token Price` - Get current token prices
- `Get Best Route` - Find optimal trading routes

### Pool Commands
- `Create CLMM Pool` - Create concentrated liquidity pools
- `Create CPMM Pool` - Create constant product pools
- `Get Pool Info` - Get detailed pool information
- `Get Pool Keys` - Get pool interaction keys
- `Get Pool List` - List all available pools

### Liquidity Commands
- `Add Liquidity` - Provide liquidity to pools
- `Remove Liquidity` - Withdraw liquidity from pools
- `Get LP Token Balance` - Check LP token balances
- `Calculate LP Value` - Calculate LP position value

### Farming Commands
- `Stake LP Tokens` - Stake LP tokens for rewards
- `Unstake LP Tokens` - Unstake LP tokens
- `Claim Farm Rewards` - Claim accumulated rewards
- `Get Farm Info` - Get farm information
- `Get User Farm Info` - Get user-specific farm data

### Authority Commands
- `Revoke Pool Authority` - Make pools immutable
- `Burn and Earn` - Lock liquidity, retain fees
- `Set Pool Authority` - Transfer pool ownership

### Analytics Commands
- `Get Pool Analytics` - Comprehensive pool metrics
- `Get Trading Volume` - Pool trading volume data
- `Get Pool APR` - Annual percentage returns
- `Get Pool TVL` - Total value locked

### Advanced Commands
- `Create Market Maker Position` - Create concentrated positions
- `Close Market Maker Position` - Close positions
- `Get Position Info` - Position information
- `Rebalance Position` - Adjust position ranges

## ⚠️ Important Safety Notes

### Testing
- **Always test on devnet first** before using mainnet
- Start with small amounts to verify functionality
- Understand slippage and price impact before trading

### Authority Operations
- **Authority revocation is IRREVERSIBLE**
- **Burn & Earn locks liquidity permanently**
- Only use these features if you fully understand the implications

### Security
- Keep your private keys secure
- Verify all token addresses before trading
- Double-check transaction parameters

### Fees
- All operations require SOL for transaction fees
- Consider priority fees during network congestion
- Factor in trading fees and slippage

## 🔗 Useful Resources

### Raydium Documentation
- [Raydium Docs](https://docs.raydium.io/)
- [Trade API](https://docs.raydium.io/raydium/traders/trade-api)
- [Pool Creation](https://docs.raydium.io/raydium/pool-creation)

### Solana Resources
- [Solana Docs](https://docs.solana.com/)
- [SPL Token Program](https://spl.solana.com/token)
- [Solana Web3.js](https://solana-labs.github.io/solana-web3.js/)

### Token Information
- [Solana Token List](https://github.com/solana-labs/token-list)
- [Raydium Token List](https://api.raydium.io/v2/sdk/token/raydium.mainnet.json)

## 🐛 Troubleshooting

### Common Issues

#### Wallet Connection
```
Error: No wallet keypair available
```
**Solution**: Set the `SOLANA_WALLET_API_KEY` environment variable

#### Insufficient Funds
```
Error: Insufficient funds for transaction
```
**Solution**: Ensure you have enough SOL for transaction fees

#### Network Congestion
```
Error: Transaction failed to confirm
```
**Solution**: Increase priority fees or retry during less congested times

#### Invalid Token Address
```
Error: Invalid mint address
```
**Solution**: Verify token mint addresses using Solana Explorer

### Getting Help
- Check the [AGiXT Discord](https://discord.gg/agixt) for community support
- Review the example scripts for implementation guidance
- Consult Raydium documentation for specific feature details

## 📈 Performance Tips

### Optimization
- Use versioned transactions (V0) for better performance
- Set appropriate priority fees during network congestion
- Batch multiple operations when possible

### Monitoring
- Monitor pool performance regularly
- Set up alerts for significant price movements
- Track farming rewards and claim them efficiently

### Risk Management
- Diversify liquidity across multiple pools
- Understand impermanent loss risks
- Use appropriate slippage settings

## 🤝 Contributing

Contributions to improve the Raydium integration are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request with detailed description

## 📄 License

This extension is part of AGiXT and follows the same licensing terms.

---

**Disclaimer**: This software is provided as-is. Trading cryptocurrencies involves risk. Always do your own research and never invest more than you can afford to lose. 