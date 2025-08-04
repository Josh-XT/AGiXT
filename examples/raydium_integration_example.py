#!/usr/bin/env python3
"""
Raydium Integration Example for AGiXT

This example demonstrates how to use the comprehensive Raydium integration
to perform various DeFi operations on the Solana blockchain.

Features demonstrated:
- Token swapping
- Pool creation and management
- Liquidity provision
- Farm staking
- Analytics and data fetching
- Authority management

Requirements:
- Set SOLANA_WALLET_API_KEY environment variable with your private key
- Ensure you have SOL for transaction fees
- Have the tokens you want to trade/provide liquidity for
"""

import asyncio
import os
import sys

sys.path.append("../agixt/extensions")

from raydium_integration import raydium_integration

# Common token mints for examples
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
RAY_MINT = "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"
SOL_MINT = "So11111111111111111111111111111111111111112"  # Wrapped SOL

# Example pool IDs (SOL-USDC is a popular pair)
SOL_USDC_POOL = "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"
RAY_USDC_POOL = "6UmmUiYoBjSrhakAobJw8BvkmJtDVxaeBtbt7rxWo1mg"


async def main():
    """Main example function demonstrating Raydium integration"""

    # Initialize the Raydium integration
    # Make sure to set your SOLANA_WALLET_API_KEY environment variable
    raydium = raydium_integration(
        SOLANA_WALLET_API_KEY=os.getenv("SOLANA_WALLET_API_KEY")
    )

    print("🚀 Raydium Integration Example")
    print("=" * 50)

    # 1. Get token prices
    print("\n📊 Getting Token Prices...")
    usdc_price = await raydium.get_token_price(USDC_MINT)
    ray_price = await raydium.get_token_price(RAY_MINT)
    print(f"USDC: {usdc_price}")
    print(f"RAY: {ray_price}")

    # 2. Get swap quote
    print("\n💱 Getting Swap Quote...")
    quote = await raydium.get_swap_quote(
        input_mint=SOL_MINT,
        output_mint=USDC_MINT,
        amount="1000000000",  # 1 SOL (9 decimals)
        slippage_bps=100,  # 1% slippage
    )
    print(quote)

    # 3. Get pool information
    print("\n🏊 Getting Pool Information...")
    pool_info = await raydium.get_pool_info(SOL_USDC_POOL)
    print(pool_info)

    # 4. Get pool analytics
    print("\n📈 Getting Pool Analytics...")
    analytics = await raydium.get_pool_analytics(SOL_USDC_POOL)
    print(analytics)

    # 5. Get pool keys (needed for direct contract interaction)
    print("\n🔑 Getting Pool Keys...")
    pool_keys = await raydium.get_pool_keys(SOL_USDC_POOL)
    print(pool_keys)

    # 6. Get APR information
    print("\n💰 Getting Pool APR...")
    apr_info = await raydium.get_pool_apr(SOL_USDC_POOL)
    print(apr_info)

    # 7. Get TVL information
    print("\n💎 Getting Pool TVL...")
    tvl_info = await raydium.get_pool_tvl(SOL_USDC_POOL)
    print(tvl_info)

    # 8. Get farm information
    print("\n🚜 Getting Farm Information...")
    farm_info = await raydium.get_farm_info(
        "GUzaohfNuFbBqQTnPgPSNciv3aUvriXYjQduRE3ZkqFw"
    )
    print(farm_info)

    # 9. Get pool list
    print("\n📋 Getting Pool List...")
    pool_list = await raydium.get_pool_list(official_only=True)
    print(pool_list)

    # 10. Demonstrate trading operations (simulation mode)
    print("\n🎯 Trading Operations (Simulation)...")

    # Get best route for a trade
    best_route = await raydium.get_best_route(
        input_mint=SOL_MINT, output_mint=USDC_MINT, amount="500000000"  # 0.5 SOL
    )
    print(f"Best route: {best_route}")

    # Execute swap (commented out for safety - uncomment to actually trade)
    # swap_result = await raydium.execute_swap(
    #     input_mint=SOL_MINT,
    #     output_mint=USDC_MINT,
    #     amount="100000000",  # 0.1 SOL
    #     slippage_bps=100
    # )
    # print(f"Swap result: {swap_result}")

    # 11. Demonstrate liquidity operations (simulation mode)
    print("\n💧 Liquidity Operations (Simulation)...")

    # Add liquidity (commented out for safety)
    # add_liquidity_result = await raydium.add_liquidity(
    #     pool_id=SOL_USDC_POOL,
    #     base_amount="100000000",  # 0.1 SOL
    #     quote_amount="10000000",  # 10 USDC (6 decimals)
    #     slippage=0.01
    # )
    # print(f"Add liquidity result: {add_liquidity_result}")

    # Get LP token balance
    lp_balance = await raydium.get_lp_token_balance(SOL_USDC_POOL)
    print(f"LP balance: {lp_balance}")

    # Calculate LP value
    lp_value = await raydium.calculate_lp_value(SOL_USDC_POOL, "1000000")
    print(f"LP value: {lp_value}")

    # 12. Demonstrate farming operations (simulation mode)
    print("\n🌾 Farming Operations (Simulation)...")

    # Stake LP tokens (commented out for safety)
    # stake_result = await raydium.stake_lp_tokens(
    #     farm_id="GUzaohfNuFbBqQTnPgPSNciv3aUvriXYjQduRE3ZkqFw",
    #     lp_amount="1000000"
    # )
    # print(f"Stake result: {stake_result}")

    # Get user farm info
    user_farm_info = await raydium.get_user_farm_info(
        "GUzaohfNuFbBqQTnPgPSNciv3aUvriXYjQduRE3ZkqFw"
    )
    print(f"User farm info: {user_farm_info}")

    # 13. Demonstrate pool creation (simulation mode)
    print("\n🏗️ Pool Creation (Simulation)...")

    # Create CLMM pool (commented out for safety)
    # clmm_result = await raydium.create_clmm_pool(
    #     base_mint="YourTokenMintHere",
    #     quote_mint=USDC_MINT,
    #     fee_tier=2500,  # 0.25%
    #     initial_price=1.0
    # )
    # print(f"CLMM pool creation: {clmm_result}")

    # Create CPMM pool (commented out for safety)
    # cpmm_result = await raydium.create_cpmm_pool(
    #     base_mint="YourTokenMintHere",
    #     quote_mint=USDC_MINT,
    #     base_amount="1000000000",  # 1000 tokens
    #     quote_amount="1000000000"  # 1000 USDC
    # )
    # print(f"CPMM pool creation: {cpmm_result}")

    # 14. Demonstrate advanced features (simulation mode)
    print("\n🎯 Advanced Features (Simulation)...")

    # Create market maker position (commented out for safety)
    # mm_position = await raydium.create_market_maker_position(
    #     pool_id=SOL_USDC_POOL,
    #     lower_price=50.0,
    #     upper_price=150.0,
    #     base_amount="100000000",
    #     quote_amount="5000000000"
    # )
    # print(f"Market maker position: {mm_position}")

    # Get position info
    position_info = await raydium.get_position_info("example_position_id")
    print(f"Position info: {position_info}")

    # 15. Demonstrate authority management (DANGEROUS - commented out)
    print("\n⚠️ Authority Management (DANGEROUS - Simulation Only)...")

    # Revoke pool authority (IRREVERSIBLE - commented out for safety)
    # revoke_result = await raydium.revoke_pool_authority(SOL_USDC_POOL)
    # print(f"Revoke authority result: {revoke_result}")

    # Burn and earn (IRREVERSIBLE - commented out for safety)
    # burn_earn_result = await raydium.burn_and_earn(SOL_USDC_POOL)
    # print(f"Burn and earn result: {burn_earn_result}")

    print("\n✅ Raydium Integration Example Complete!")
    print("\nNote: Most transaction operations are commented out for safety.")
    print("Uncomment and modify them carefully for actual trading.")
    print("\n⚠️ IMPORTANT WARNINGS:")
    print("1. Always test on devnet first")
    print("2. Start with small amounts")
    print("3. Understand slippage and price impact")
    print("4. Authority revocation is IRREVERSIBLE")
    print("5. Always verify token addresses")


async def trading_bot_example():
    """Example of a simple trading bot using Raydium integration"""
    print("\n🤖 Trading Bot Example")
    print("=" * 30)

    raydium = raydium_integration(
        SOLANA_WALLET_API_KEY=os.getenv("SOLANA_WALLET_API_KEY")
    )

    # Simple arbitrage detection example
    print("Checking for arbitrage opportunities...")

    # Get prices from different pools
    sol_usdc_analytics = await raydium.get_pool_analytics(SOL_USDC_POOL)

    # In a real bot, you would:
    # 1. Monitor multiple pools for the same pair
    # 2. Calculate price differences
    # 3. Execute trades when profitable
    # 4. Account for fees and slippage

    print("Arbitrage check complete (simulation)")


async def liquidity_provider_example():
    """Example of automated liquidity provision"""
    print("\n💧 Liquidity Provider Example")
    print("=" * 35)

    raydium = raydium_integration(
        SOLANA_WALLET_API_KEY=os.getenv("SOLANA_WALLET_API_KEY")
    )

    # Automated liquidity management example
    print("Managing liquidity positions...")

    # In a real LP bot, you would:
    # 1. Monitor pool performance
    # 2. Rebalance positions based on price movements
    # 3. Compound rewards automatically
    # 4. Adjust ranges for concentrated liquidity

    # Get current position value
    lp_value = await raydium.calculate_lp_value(SOL_USDC_POOL, "1000000")
    print(f"Current LP value: {lp_value}")

    # Check if rebalancing is needed
    apr_info = await raydium.get_pool_apr(SOL_USDC_POOL)
    print(f"Pool APR: {apr_info}")

    print("Liquidity management complete (simulation)")


if __name__ == "__main__":
    # Check if wallet key is set
    if not os.getenv("SOLANA_WALLET_API_KEY"):
        print("❌ Error: SOLANA_WALLET_API_KEY environment variable not set")
        print("Please set your Solana wallet private key:")
        print("export SOLANA_WALLET_API_KEY='your_private_key_here'")
        sys.exit(1)

    # Run the main example
    asyncio.run(main())

    # Run additional examples
    asyncio.run(trading_bot_example())
    asyncio.run(liquidity_provider_example())

    print("\n🎉 All examples completed successfully!")
    print("Remember to always test on devnet before using on mainnet!")
