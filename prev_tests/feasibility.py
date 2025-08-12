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
PRICE_DECIMALS = 10 ** 8
RPC_URL = os.getenv("RPC_URL")
CHAIN = "hyperEvm"

# === HypurrFi Setup ===
web3 = Web3(Web3.HTTPProvider(RPC_URL))
if not web3.is_connected():
    print("❌ Failed to connect to  RPC")
    exit()

ORACLE_ADDRESS = web3.to_checksum_address("0x9BE2ac1ff80950DCeb816842834930887249d9A8")
PROTOCOL_DATA_PROVIDER_ADDRESS = web3.to_checksum_address("0x895C799a5bbdCb63B80bEE5BD94E7b9138D977d6")
HYPURRFI_IRM_ADDRESS = web3.to_checksum_address("0x701B26833A2dFa145B29Ef1264DE3a5240E17bBD")

with open("abi/HyFiOracle.json") as f:
    oracle_abi = json.load(f)
with open("abi/HyFiFiDataProvider.json") as f:
    data_provider_abi = json.load(f)
with open("abi/hypurrfiirm.json") as f:
    irm_hy_abi = json.load(f)


oracle_contract = web3.eth.contract(address=ORACLE_ADDRESS, abi=oracle_abi)
data_provider_contract = web3.eth.contract(address=PROTOCOL_DATA_PROVIDER_ADDRESS, abi=data_provider_abi)
irm_hypurrfi_contract = web3.eth.contract(address=HYPURRFI_IRM_ADDRESS,abi = irm_hy_abi)

HYPERLEND_ORACLE_ADDRESS = web3.to_checksum_address("0xC9Fb4fbE842d57EAc1dF3e641a281827493A630e")
HYPERLEND_DATA_PROVIDER_ADDRESS = web3.to_checksum_address("0x5481bf8d3946E6A3168640c1D7523eB59F055a29")
IRM_ADDRESS = web3.to_checksum_address("0xD01E9AA0ba6a4a06E756BC8C79579E6cef070822")


with open("abi/HyperlendOracle.json") as f:
    hyperlend_oracle_abi = json.load(f)
with open("abi/HyperlendDataProvider.json") as f:
    hyperlend_data_provider_abi = json.load(f)
with open("abi/aaveIrm.json") as f:
    irm_abi = json.load(f)

hyperlend_oracle_contract = web3.eth.contract(address=HYPERLEND_ORACLE_ADDRESS, abi=hyperlend_oracle_abi)
hyperlend_data_provider_contract = web3.eth.contract(address=HYPERLEND_DATA_PROVIDER_ADDRESS, abi=hyperlend_data_provider_abi)
irm_contract = web3.eth.contract(address=IRM_ADDRESS, abi=irm_abi)


#here starts for hyperlend
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
                total_borrow = hyperlend_data_provider_contract.functions.getTotalDebt(token_address).call()

                liquidity_rate = reserve_data[5]
                decimals = config_data[0]
                token_price = price_dict.get(token_symbol, 0)
                borrows_usd = (total_borrow * token_price) / (10 ** decimals * PRICE_DECIMALS)

                apy = 0.0
                if liquidity_rate > 0:
                    liquidity_rate_decimal = liquidity_rate / RAY
                    apy = ((1 + liquidity_rate_decimal / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1) * 100

                tvl = 0.0
                if total_supply > 0 and token_price > 0:
                    tvl = (total_supply * token_price) / (10 ** decimals * PRICE_DECIMALS)

                results[token_symbol.replace("₮", "T")] = {
                    "apy": round(apy, 2),
                    "tvl": round(tvl, 2),
                    "address": token_address,
                    "borrows": borrows_usd
                }

            except Exception as e:
                print(f"⚠️ Error processing {token_symbol}: {str(e)}")
                continue

        return results

    except Exception as e:
        print(f"❌ Error fetching HyperLend data on-chain: {e}")
        return {}
#here ends for hyperlend

#here starts for hypurrfi
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
            total_borrow = data_provider_contract.functions.getTotalDebt(address).call()
            token_price = oracle_contract.functions.getAssetPrice(address).call()
            
            liquidity_rate = data1[5]  # liquidityRate in ray
            decimals = data2[0]  # token decimals per reserve
            DECIMALS = 10 ** decimals
            borrows_usd = (total_borrow * token_price) / (10 ** decimals * PRICE_DECIMALS)
            # Calculate APY with edge case handling
            apy = 0.0
            if liquidity_rate > 0:
                liquidity_rate_decimal = liquidity_rate / RAY
                apy = ((1 + liquidity_rate_decimal / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1) * 100

            # TVL Calculation
            tvl_usd = 0.0
            try:
                total_supply = data_provider_contract.functions.getATokenTotalSupply(address).call()
                token_price = oracle_contract.functions.getAssetPrice(address).call()
                if total_supply > 0 and token_price > 0:
                    tvl_usd = (total_supply * token_price) / (DECIMALS * PRICE_DECIMALS)
            except Exception as e:
                tvl_usd = 0.0

            results[symbol.replace("₮", "T")] = {
                "apy": round(apy, 2),
                "tvl": round(tvl_usd, 2),
                "address": address,
                "borrows":borrows_usd
            }

        except Exception as e:
            print(f"⚠️ Error processing {symbol}: {str(e)}")
            continue

    return results
#here ends for hypurrfi

def get_irm_params_for_hyperlend(reserve_address, supply_usd, borrow_usd):
    base_rate = irm_contract.functions.getBaseVariableBorrowRate(reserve_address).call() / 1e27
    slope1 = irm_contract.functions.getVariableRateSlope1(reserve_address).call() / 1e27
    slope2 = irm_contract.functions.getVariableRateSlope2(reserve_address).call() / 1e27
    raw_kink = irm_contract.functions.getOptimalUsageRatio(reserve_address).call()
    if raw_kink > 1_000_000:
        kink = raw_kink / 1e27
    else:  
        kink = raw_kink / 10_000


    return {
        "base_rate": base_rate,
        "slope1": slope1,
        "slope2": slope2,
        "kink": kink,
        "supply_usd": supply_usd,
        "borrow_usd": borrow_usd
    }

def get_irm_params_for_reserve_hypurrfi(reserve_address, supply_usd, borrow_usd):
    base_rate = base_rate = irm_hypurrfi_contract.functions.getBaseVariableBorrowRate().call() / 1e27
    slope1 = irm_hypurrfi_contract.functions.getVariableRateSlope1().call() / 1e27
    slope2 = irm_hypurrfi_contract.functions.getVariableRateSlope2().call() / 1e27
    raw_kink = irm_hypurrfi_contract.functions.getOptimalUsageRatio().call()
    if raw_kink > 1_000_000:
        kink = raw_kink / 1e27
    else:
        kink = raw_kink / 10_000

    return {
        "base_rate": base_rate,
        "slope1": slope1,
        "slope2": slope2,
        "kink": kink,
        "supply_usd": supply_usd,
        "borrow_usd": borrow_usd
    }


# === APY Calculation Helpers ===
def calculate_kinked_apy(utilization: float, base_rate: float, slope1: float, slope2: float, kink: float) -> float:
    if utilization <= kink:
        rate = base_rate + slope1 * (utilization / kink)
    else:
        rate = base_rate + slope1 + slope2 * ((utilization - kink) / (1 - kink))
    return rate * 100  # convert to %

def find_max_deposit_binary(current_supply, current_borrow, irm_params, target_apy, tolerance=0.01, max_multiplier=5.0):
    base_rate = irm_params["base_rate"]
    slope1 = irm_params["slope1"]
    slope2 = irm_params["slope2"]
    kink = irm_params["kink"]

    current_utilization = current_borrow / current_supply if current_supply > 0 else 0
    current_apy = calculate_kinked_apy(current_utilization, base_rate, slope1, slope2, kink)

    if current_apy <= target_apy:
        return 0.0

    low, high = 0, current_supply * max_multiplier

    while high - low > tolerance:
        mid = (low + high) / 2
        new_supply = current_supply + mid
        utilization = current_borrow / new_supply if new_supply > 0 else 0
        apy = calculate_kinked_apy(utilization, base_rate, slope1, slope2, kink)

        if apy >= target_apy:
            low = mid
        else:
            high = mid

    return round(low, 2)

# === Comparison with Kinked Model ===
def compare_yields_with_kink(hyperlend_data, hypurrfi_data, irm_map, debug=False):
    lines = ["📊 *Yield Comparison Report (Kinked Model)*"]
    all_assets = sorted(set(hyperlend_data.keys()) | set(hypurrfi_data.keys()))

    for asset in all_assets:
        protocols = {}
        if asset in hyperlend_data:
            protocols["HyperLend"] = hyperlend_data[asset]
        if asset in hypurrfi_data:
            protocols["HypurrFi"] = hypurrfi_data[asset]

        if len(protocols) < 2:
            continue

        sorted_protocols = sorted(protocols.items(), key=lambda x: x[1]["apy"], reverse=True)
        top1_name, top1_data = sorted_protocols[0]
        top2_name, top2_data = sorted_protocols[1]

        line = f"\n🪙 *{asset}*"
        for name, data in protocols.items():
            line += f"\n  - {name}: {data['apy']:.2f}% (TVL: ${data['tvl']:,.2f})"

        diff = top1_data['apy'] - top2_data['apy']
        if abs(diff) < 0.5:
            lines.append(line + "\n🔹 Top two protocols offer similar yields currently")
        else:
            lines.append(line + f"\n🔸 {top1_name} offers {abs(diff):.2f}% higher yield than {top2_name}")

            if asset in irm_map.get(top1_name, {}):
                params = irm_map[top1_name][asset]
                
                max_dep = find_max_deposit_binary(
                    current_supply=params["supply_usd"],
                    current_borrow=params["borrow_usd"],
                    irm_params=params,
                    target_apy=top2_data["apy"]
                )

                if debug:
                    print(f"  Max deposit before APY ≤ {top2_name}: {max_dep}")

                lines.append(f"💰 Max deposit in {top1_name} before APY ≤ {top2_name}: ${max_dep:,.2f}")

    return "\n".join(lines)

# === Main ===
if __name__ == "__main__":
    # Pull yield + TVL data
    yields_hyperlend = get_hyperlend_yields_and_tvl()  # returns {token: {"apy": X, "tvl": Y, "borrows": Z, "address": addr}}
    yields_hypurrfi = get_hypurrfi_yields_and_tvl()

    # Build IRM param map only for HyperLend pools (or any kinked pool)
    irm_map = {
    "HyperLend": {},
    "HypurrFi": {}
}
    for token, data in yields_hyperlend.items():
        irm_params = get_irm_params_for_hyperlend(
            reserve_address=data["address"],
            supply_usd=data["tvl"],
            borrow_usd=data["borrows"]
        )
        irm_map["HyperLend"][token] = irm_params

# HypurrFi IRM params
    for token, data in yields_hypurrfi.items():
        irm_params = get_irm_params_for_reserve_hypurrfi(
            reserve_address=data["address"],
            supply_usd=data["tvl"],
            borrow_usd=data["borrows"]
        )
        irm_map["HypurrFi"][token] = irm_params

    # Reports
    current_report = ["🔍 *Current Yield Report*"]
    for token in sorted(set(yields_hyperlend.keys()) | set(yields_hypurrfi.keys())):
        current_report.append(f"\n🪙 *{token}*")
        if token in yields_hyperlend:
            hl = yields_hyperlend[token]
            current_report.append(f"  - HyperLend: `{hl['apy']:.2f}%` (TVL: ${hl['tvl']:,.2f})")
        if token in yields_hypurrfi:
            hf = yields_hypurrfi[token]
            current_report.append(f"  - HypurrFi:  `{hf['apy']:.2f}%` (TVL: ${hf['tvl']:,.2f})")

    comparison_report = compare_yields_with_kink(yields_hyperlend, yields_hypurrfi, irm_map, debug=True)


    print("\n".join(current_report))
    print("\n" + comparison_report)