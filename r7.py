import requests
import json
import os
from web3 import Web3
from dotenv import load_dotenv
from telebot import send_telegram_message
from typing import Dict, Tuple, Optional, Any
import math

load_dotenv()


# === CONFIG ===
PRICE_DECIMALS = 10**8
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

def get_hyperlend_yields_and_tvl():
    try:
        SECONDS_PER_YEAR = 31536000
        RAY = 10**27
        PRICE_DECIMALS = 10**8

        # Your known tokens whitelist and their addresses
        WHITELIST = ["USDe", "USD₮0", "HYPE"]

        token_map = {
            "USDe": web3.to_checksum_address("0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"),
            "USD₮0": web3.to_checksum_address("0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb"),
            "HYPE": web3.to_checksum_address("0x5555555555555555555555555555555555555555")  # make sure this address is correct!
        }

        # Get prices for these tokens
        price_addresses = [token_map[symbol] for symbol in WHITELIST]
        prices = hyperlend_oracle_contract.functions.getAssetsPrices(price_addresses).call()
        price_dict = {symbol: price for symbol, price in zip(WHITELIST, prices)}

        results = {}

        # Loop only over your known tokens
        for token_symbol in WHITELIST:
            token_address = token_map[token_symbol]
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
                    tvl = (total_supply * token_price) / (10 ** decimals * PRICE_DECIMALS)

                results[token_symbol.replace("₮", "T")] = {
                    "apy": round(apy, 2),
                    "tvl": round(tvl, 2)
                }

            except Exception as e:
                print(f"⚠️ Error processing {token_symbol}: {str(e)}")
                continue

        return results

    except Exception as e:
        print(f"❌ Error fetching HyperLend data on-chain: {e}")
        return {}

def get_hypurrfi_yields_and_tvl():
    SECONDS_PER_YEAR = 365 * 24 * 60 * 60
    RAY = 10**27
    PRICE_DECIMALS = 10**8

    # Your known whitelist tokens and their addresses
    WHITELIST = ["USD₮0", "HYPE", "USDe"]
    token_map = {
        "USD₮0": web3.to_checksum_address("0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb"),
        "HYPE": web3.to_checksum_address("0x5555555555555555555555555555555555555555"),
        "USDe": web3.to_checksum_address("0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34"),
    }

    results = {}

    for symbol in WHITELIST:
        address = token_map.get(symbol)
        if not address:
            print(f"⚠️ Address for token {symbol} not found in token_map")
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

            results[symbol.replace("₮", "T")] = {
                "apy": round(apy, 2),
                "tvl": round(tvl_usd, 2)
            }

        except Exception as e:
            print(f"⚠️ Error processing {symbol}: {str(e)}")
            continue

    return results


def main():
    print(get_hyperlend_yields_and_tvl())
    print(get_hypurrfi_yields_and_tvl())
    

if __name__ == "__main__":
    main()
