from web3 import Web3
import json
import os
from dotenv import load_dotenv

load_dotenv()

# --- Web3 Setup ---
RPC_URL = os.getenv("HYPURRFI_RPC_URL")
web3 = Web3(Web3.HTTPProvider(RPC_URL))

# --- Contract Setup ---
ORACLE_ADDRESS = web3.to_checksum_address("0xC9Fb4fbE842d57EAc1dF3e641a281827493A630e")
with open("abi/HyperlendOracle.json") as f:
    oracle_abi = json.load(f)
oracle_contract = web3.eth.contract(address=ORACLE_ADDRESS, abi=oracle_abi)

PROTOCOL_DATA_PROVIDER_ADDRESS = web3.to_checksum_address("0x5481bf8d3946E6A3168640c1D7523eB59F055a29")
with open("abi/HyperlendDataProvider.json") as f:
    protocol_data_provider_abi = json.load(f)
data_provider_contract = web3.eth.contract(address=PROTOCOL_DATA_PROVIDER_ADDRESS, abi=protocol_data_provider_abi)



# --- Get Oracle Prices ---
def get_hyperlend_prices(asset_addresses):
    try:
        prices = oracle_contract.functions.getAssetsPrices(asset_addresses).call()
        return prices
    except Exception as e:
        print(f"Error fetching Hyperlend prices: {e}")
        return []


# --- Fetch APY and TVL ---
def get_supply_apy_and_tvl():
    try:
        # Constants
        SECONDS_PER_YEAR = 31536000
        RAY = 10**27
        PRICE_DECIMALS = 10**8
        WHITELIST = ["USDe", "USD₮0", "kHYPE"]

        # Mapping symbols to addresses
        token_map = {
            "USDe": web3.to_checksum_address("0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"),
            "USD₮0": web3.to_checksum_address("0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb"),
            "kHYPE": web3.to_checksum_address("0xfD739d4e423301CE9385c1fb8850539D657C296D")
        }

        # Batch get prices
        price_addresses = [token_map[sym] for sym in WHITELIST]
        prices = get_hyperlend_prices(price_addresses)
        price_dict = {sym: price for sym, price in zip(WHITELIST, prices)}

        # Get reserves
        reserve_tokens = data_provider_contract.functions.getAllReservesTokens().call()

        print("\n--- HyperLend Supply APY & TVL ---\n")

        for token_symbol, token_address in reserve_tokens:
            if token_symbol not in WHITELIST:
                continue

            reserve_data = data_provider_contract.functions.getReserveData(token_address).call()
            config_data = data_provider_contract.functions.getReserveConfigurationData(token_address).call()
            total_supply = data_provider_contract.functions.getATokenTotalSupply(token_address).call()

            liquidity_rate = reserve_data[5]
            decimals = config_data[0]
            token_price = price_dict.get(token_symbol, 0)

            # Calculate APY
            liquidity_rate_decimal = liquidity_rate / RAY
            apy = ((1 + liquidity_rate_decimal / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1) * 100

            # Calculate TVL
            tvl = 0
            if total_supply > 0 and token_price > 0:
                tvl = (total_supply * token_price) / (10**decimals * PRICE_DECIMALS)

            print(f"Asset: {token_symbol.replace('₮', 'T')}")
            print(f"  - Address: {token_address}")
            print(f"  - Supply APY: {apy:.2f}%")
            print(f"  - TVL: ${tvl:,.2f}\n")

    except Exception as e:
        print(f"Error fetching APY and TVL: {e}")


# --- Main Entry Point ---
if __name__ == "__main__":
    if not web3.is_connected():
        print("❌ Failed to connect to HyperLend RPC.")
    else:
        print("✅ Connected to HyperLend RPC.\n")
        get_supply_apy_and_tvl()
