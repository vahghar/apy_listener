from web3 import Web3
import json
import os
from dotenv import load_dotenv

load_dotenv()

RPC_URL = os.getenv("HYPURRFI_RPC_URL")
web3 = Web3(Web3.HTTPProvider(RPC_URL))

# Oracle contract details
ORACLE_ADDRESS = web3.to_checksum_address("0xC9Fb4fbE842d57EAc1dF3e641a281827493A630e")
with open("abi/HyperlendOracle.json") as f:
    oracle_abi = json.load(f)
oracle_contract = web3.eth.contract(address=ORACLE_ADDRESS, abi=oracle_abi)

# ProtocolDataProvider contract details
PROTOCOL_DATA_PROVIDER_ADDRESS = web3.to_checksum_address("0x5481bf8d3946E6A3168640c1D7523eB59F055a29")
with open("abi/HyperlendDataProvider.json") as f:
    protocol_data_provider_abi = json.load(f)
data_provider_contract = web3.eth.contract(address=PROTOCOL_DATA_PROVIDER_ADDRESS, abi=protocol_data_provider_abi)

def get_hyperlend_prices(asset_addresses):
    """
    Fetches the price for a list of assets from the Oracle contract.
    """
    try:
        prices = oracle_contract.functions.getAssetsPrices(asset_addresses).call()
        return prices
    except Exception as e:
        print(f"Error fetching Hyperlend prices: {e}")
        return []

def get_supply_apy():
    """
    Fetches supply APY for all reserves on Hyperlend.
    """
    try:
        # Get all reserve tokens
        reserve_tokens = data_provider_contract.functions.getAllReservesTokens().call()

        # Define constants for APY calculation
        SECONDS_PER_YEAR = 31536000
        RAY = 10**27

        print("Fetching supply APY for all assets...\n")

        WHITELIST = ["USDe", "USD₮0", "kHYPE"]

        for token in reserve_tokens:
            token_symbol = token[0]
            if token_symbol not in WHITELIST:
                continue

            token_address = token[1]
            reserve_data = data_provider_contract.functions.getReserveData(token_address).call()
            liquidity_rate = reserve_data[5]

            liquidity_rate_decimal = liquidity_rate / RAY
            apy = ((1 + liquidity_rate_decimal / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1) * 100

            print(f"Asset: {token_symbol}")
            print(f"  - Address: {token_address}")
            print(f"  - Supply APY: {apy:.2f}%\n")

    except Exception as e:
        print(f"Error fetching supply APY: {e}")

if __name__ == "__main__":
    if not web3.is_connected():
        print("Failed to connect to Hyperlend RPC.")
    else:
        # Part 1: Get asset prices from the Oracle
        print("--- Fetching Prices from Oracle ---")
        assets = [
            web3.to_checksum_address("0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb"),  # usdt0
            web3.to_checksum_address("0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"),  # usde
            web3.to_checksum_address("0xfD739d4e423301CE9385c1fb8850539D657C296D")   # hype
        ]
        prices = get_hyperlend_prices(assets)
        print(f"Oracle Prices: {prices}\n")

        # Part 2: Get supply APY from the ProtocolDataProvider
        print("--- Fetching Supply APY ---")
        get_supply_apy()