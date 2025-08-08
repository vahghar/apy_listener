import requests
import json
import os
from web3 import Web3
from dotenv import load_dotenv
from telebot import send_telegram_message

load_dotenv()

# === CONFIG ===
HYPURRFI_RPC_URL = os.getenv("HYPURRFI_RPC_URL")
BASE_URL_HYPERLEND = "https://api.hyperlend.finance"
CHAIN = "hyperEvm"

# === HypurrFi Setup ===
web3 = Web3(Web3.HTTPProvider(HYPURRFI_RPC_URL))
if not web3.is_connected():
    send_telegram_message("❌ Failed to connect to HypurrFi RPC")
    exit()

ORACLE_ADDRESS = web3.to_checksum_address("0x9BE2ac1ff80950DCeb816842834930887249d9A8")
PROTOCOL_DATA_PROVIDER_ADDRESS = web3.to_checksum_address("0x895C799a5bbdCb63B80bEE5BD94E7b9138D977d6")

with open("abi/HyFiOracle.json") as f:
    oracle_abi = json.load(f)
with open("abi/HyFiFiDataProvider.json") as f:
    data_provider_abi = json.load(f)


oracle_contract = web3.eth.contract(address=ORACLE_ADDRESS, abi=oracle_abi)
data_provider_contract = web3.eth.contract(address=PROTOCOL_DATA_PROVIDER_ADDRESS, abi=data_provider_abi)


HYPERLEND_ORACLE_ADDRESS = web3.to_checksum_address("0xC9Fb4fbE842d57EAc1dF3e641a281827493A630e")
HYPERLEND_DATA_PROVIDER_ADDRESS = web3.to_checksum_address("0x5481bf8d3946E6A3168640c1D7523eB59F055a29")


with open("abi/HyperlendOracle.json") as f:
    hyperlend_oracle_abi = json.load(f)
with open("abi/HyperlendDataProvider.json") as f:
    hyperlend_data_provider_abi = json.load(f)

hyperlend_oracle_contract = web3.eth.contract(address=HYPERLEND_ORACLE_ADDRESS, abi=hyperlend_oracle_abi)
hyperlend_data_provider_contract = web3.eth.contract(address=HYPERLEND_DATA_PROVIDER_ADDRESS, abi=hyperlend_data_provider_abi)

# === Functions ===

def get_hyperlend_yields_and_tvl():
    try:
        SECONDS_PER_YEAR = 31536000
        RAY = 10**27
        PRICE_DECIMALS = 10**8
        WHITELIST = ["USDe", "USD₮0", "kHYPE"]

        # Map of symbols to addresses (based on your provided script)
        token_map = {
            "USDe": web3.to_checksum_address("0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"),
            "USD₮0": web3.to_checksum_address("0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb"),
            "kHYPE": web3.to_checksum_address("0xfD739d4e423301CE9385c1fb8850539D657C296D")
        }

        price_addresses = [token_map[symbol] for symbol in WHITELIST]
        prices = hyperlend_oracle_contract.functions.getAssetsPrices(price_addresses).call()
        price_dict = {symbol: price for symbol, price in zip(WHITELIST, prices)}

        reserve_tokens = hyperlend_data_provider_contract.functions.getAllReservesTokens().call()
        results = {}

        for token_symbol, token_address in reserve_tokens:
            if token_symbol not in WHITELIST:
                continue

            token_address = web3.to_checksum_address(token_address)
            try:
                reserve_data = hyperlend_data_provider_contract.functions.getReserveData(token_address).call()
                config_data = hyperlend_data_provider_contract.functions.getReserveConfigurationData(token_address).call()
                total_supply = hyperlend_data_provider_contract.functions.getATokenTotalSupply(token_address).call()

                liquidity_rate = reserve_data[5]
                decimals = config_data[0]
                token_price = price_dict.get(token_symbol, 0)

                apy = 0.0
                if liquidity_rate > 0:
                    liquidity_rate_decimal = liquidity_rate / RAY
                    apy = ((1 + liquidity_rate_decimal / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1) * 100

                tvl = 0.0
                if total_supply > 0 and token_price > 0:
                    tvl = (total_supply * token_price) / (10**decimals * PRICE_DECIMALS)

                results[token_symbol.replace("₮", "T")] = {
                    "apy": round(apy, 2),
                    "tvl": round(tvl, 2)
                }

            except Exception as e:
                send_telegram_message(f"⚠️ Error processing {token_symbol}: {str(e)}")
                continue

        return results

    except Exception as e:
        send_telegram_message(f"❌ Error fetching HyperLend data on-chain: {e}")
        return {}

def get_hypurrfi_yields_and_tvl():
    SECONDS_PER_YEAR = 365 * 24 * 60 * 60
    RAY = 10**27
    PRICE_DECIMALS = 10**8

    results = {}
    
    try:
        reserve_tokens = data_provider_contract.functions.getAllReservesTokens().call()

        for symbol, address in reserve_tokens:
            symbol = symbol.replace("₮", "T").strip()
            if symbol not in ["USD₮0", "kHYPE", "USDe", "USDT0"]:
                continue

            try:
                # Get reserve data
                data1 = data_provider_contract.functions.getReserveData(address).call()
                data2 = data_provider_contract.functions.getReserveConfigurationData(address).call()
                liquidity_rate = data1[5]  # liquidityRate in ray
                decimals = data2[0]  # token decimals per reserve
                DECIMALS = 10 ** decimals
                
                # Calculate APY with edge case handling
                apy = 0.0
                if liquidity_rate > 0:
                    liquidity_rate_decimal = liquidity_rate / RAY
                    apy = ((1 + liquidity_rate_decimal / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1) * 100

        # TVL Calculation
                tvl_usd = 0.0
                try:
                    total_supply = data_provider_contract.functions.getATokenTotalSupply(address).call()
                    token_price = hyperlend_oracle_contract.functions.getAssetPrice(address).call()
                    if total_supply > 0 and token_price > 0:
                        tvl_usd = (total_supply * token_price) / (DECIMALS * PRICE_DECIMALS)
                except Exception as e:
                    tvl_usd = 0.0
                results[symbol] = {
                    "apy": round(apy, 2),
                    "tvl": round(tvl_usd, 2)
                }

            except Exception as e:
                send_telegram_message(f"⚠️ Error processing {symbol}: {str(e)}")
                continue

    except Exception as e:
        send_telegram_message(f"❌ Critical error in HypurrFi data fetch: {str(e)}")
        return {}

    return results


points_per_week = {
    "USDe": 198_000,
    "USD₮0": 100_000,
    "kHYPE": 50_000
}


TOKEN_VALUE_PER_POINT = 10  
WEEKS_PER_YEAR = 52

def calculate_points_apy_static(points_per_week, pool_tvl_usd, total_fdv=100_000_000, airdrop_percentage=0.20):
    """
    Static estimation of points APY for each pool.

    Args:
        points_per_week (dict): Points per token/pool, e.g., {"USDe": 198_000, "USD₮0": 100_000}
        pool_tvl_usd (dict): TVL in USD for each pool, same keys as above
        total_fdv (float): Estimated FDV of protocol
        airdrop_percentage (float): Portion of FDV being airdropped (e.g., 0.20 for 20%)

    Returns:
        dict: Estimated APY from points for each token/pool
    """
    SECONDS_PER_YEAR = 31536000
    WEEKS_PER_YEAR = SECONDS_PER_YEAR / (7 * 24 * 60 * 60)

    total_airdrop_usd = total_fdv * airdrop_percentage
    total_points_weekly = sum(points_per_week.values())
    usd_per_point = total_airdrop_usd / (total_points_weekly * WEEKS_PER_YEAR)

    points_apy = {}

    for token, weekly_points in points_per_week.items():
        yearly_points = weekly_points * WEEKS_PER_YEAR
        estimated_usd_rewards = yearly_points * usd_per_point
        tvl = pool_tvl_usd.get(token, 0)

        if tvl > 0:
            apy = (estimated_usd_rewards / tvl) * 100
        else:
            apy = 0

        points_apy[token] = apy

    return points_apy


# === Run Script ===
if __name__ == "__main__":
    
    # Fetch data
    yields_hyperlend = get_hyperlend_yields_and_tvl()
    yields_hypurrfi = get_hypurrfi_yields_and_tvl()
    
    # Generate reports
    current_report = ["🔍 *Current Yield Report*"]
    comparison_report = compare_yields(yields_hyperlend, yields_hypurrfi, TEST_DEPOSIT_AMOUNT)
    
    for token in sorted(set(yields_hyperlend.keys()).union(yields_hypurrfi.keys())):
        # Current yields
        current_report.append(f"\n🪙 *{token}*")
        if token in yields_hyperlend:
            hl = yields_hyperlend[token]
            current_report.append(f"  - HyperLend: `{hl['apy']:.2f}%` (TVL: ${hl['tvl']:,.2f})")
        if token in yields_hypurrfi:
            hf = yields_hypurrfi[token]
            current_report.append(f"  - HypurrFi:  `{hf['apy']:.2f}%` (TVL: ${hf['tvl']:,.2f})")
        
        # Projections
        
    apy = calculate_points_apy_static(points_per_week, pool_tvl_usd)
    print(apy)
    # Also print to console
    print("\n".join(current_report))
