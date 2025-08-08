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

# === Functions ===

def get_hyperlend_yields():
    try:
        response = requests.get(f"{BASE_URL_HYPERLEND}/data/markets?chain={CHAIN}")
        response.raise_for_status()
        data = response.json()

        results = {}

        for reserve in data.get("reserves", []):
            symbol = reserve.get("symbol")
            liquidity_rate = int(reserve.get("liquidityRate", 0))
            apy = (liquidity_rate / 1e27) * 100

            tvl = float(reserve.get("totalLiquidityUSD", 0))

            # Normalize symbols and filter specific ones
            normalized_symbol = symbol.replace("₮", "T")
            if normalized_symbol in ["USDT0", "kHYPE", "USDe"]:
                results[normalized_symbol] = {
                    "apy": round(apy, 2),
                    "tvl": round(tvl, 2)
                }

        return results

    except Exception as e:
        send_telegram_message(f"❌ Error fetching HyperLend data: {e}")
        return {}


def get_hypurrfi_yields():
    try:
        SECONDS_PER_YEAR = 31536000
        RAY = 10**27

        results = {}
        reserve_tokens = data_provider_contract.functions.getAllReservesTokens().call()

        for symbol, address in reserve_tokens:
            symbol = symbol.replace("₮", "T")
            if symbol not in ["USD₮0", "kHYPE", "USDe", "USDT0"]:
                continue
            data = data_provider_contract.functions.getReserveData(address).call()
            liquidity_rate = data[5]
            liquidity_rate_decimal = liquidity_rate / RAY
            apy = ((1 + liquidity_rate_decimal / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1) * 100
            results[symbol] = apy
        return results

    except Exception as e:
        send_telegram_message(f"❌ Error fetching HypurrFi data: {e}")
        return {}

def compare_yields(hyperlend, hypurrfi):
    all_assets = set(hyperlend.keys()).union(hypurrfi.keys())

    lines = ["📊 *APY Comparison: HyperLend vs HypurrFi*\n"]
    for asset in sorted(all_assets):
        apy_hyper = hyperlend.get(asset)
        apy_hypur = hypurrfi.get(asset)

        line = f"🪙 *{asset}*\n"
        line += f"  - HyperLend: `{apy_hyper:.2f}%`\n" if apy_hyper is not None else "  - HyperLend: `N/A`\n"
        line += f"  - HypurrFi:  `{apy_hypur:.2f}%`\n" if apy_hypur is not None else "  - HypurrFi:  `N/A`\n"

        if apy_hyper is not None and apy_hypur is not None:
            better = "HyperLend" if apy_hyper > apy_hypur else "HypurrFi"
            line += f"  ✅ *Better:* {better}\n"
        line += "\n"
        lines.append(line)

    final_message = "".join(lines).strip()
    send_telegram_message(final_message)

# === Run Script ===
if __name__ == "__main__":
    yields_hyperlend = get_hyperlend_yields()
    yields_hypurrfi = get_hypurrfi_yields()
    compare_yields(yields_hyperlend, yields_hypurrfi)
