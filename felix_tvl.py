import json
from web3 import Web3
from typing import Tuple, Any
from telebot import send_telegram_message

# === Setup ===
RPC_URL = "https://rpc.hyperliquid.xyz/evm"
web3 = Web3(Web3.HTTPProvider(RPC_URL))
if not web3.is_connected():
    send_telegram_message("❌ Failed to connect to HyperEVM RPC")
    exit()

# === Constants ===
PRICE_DECIMALS = 10 ** 8

# === Vault & Oracle Addresses ===
VAULT_ADDRESSES = {
    "USDe": web3.to_checksum_address("0x835febf893c6dddee5cf762b0f8e31c5b06938ab"),
    "USDT0": web3.to_checksum_address("0xfc5126377f0efc0041c0969ef9ba903ce67d151e"),
    "HYPE": web3.to_checksum_address("0x2900ABd73631b2f60747e687095537B673c06A76"),
}
ORACLE_ADDRESS = web3.to_checksum_address("0xC9Fb4fbE842d57EAc1dF3e641a281827493A630e")

# === Load ABIs ===
def load_abi(filename: str) -> list:
    with open(filename, 'r') as f:
        return json.load(f)

# === Setup Contracts ===
def setup_contracts(vault_address) -> Tuple[Any, Any]:
    vault_abi = load_abi('abi/vault1.json')
    oracle_abi = load_abi('abi/HyperlendOracle.json')

    vault_contract = web3.eth.contract(
        address=vault_address,
        abi=vault_abi
    )
    oracle_contract = web3.eth.contract(
        address=ORACLE_ADDRESS,
        abi=oracle_abi
    )

    return vault_contract, oracle_contract

# === Calculate Vault TVL ===
def calculate_vault_tvl(vault_contract, oracle_contract, vault_name: str) -> float:
    try:
        # Step 1: Get underlying asset
        asset_address = vault_contract.functions.asset().call()
        print(f"\n🔍 [{vault_name}] Underlying asset: {asset_address}")

        # Step 2: Get total assets and decimals
        raw_total_assets = vault_contract.functions.totalAssets().call()

        # Hardcode decimals for USDT0
        if vault_name == "USDT0":
            decimals = 6
        else:
            decimals = vault_contract.functions.decimals().call()

        print(f"📦 [{vault_name}] Raw total assets: {raw_total_assets}")
        print(f"🔢 [{vault_name}] Vault decimals: {decimals}")

        # Step 3: Get token price from oracle
        token_price = oracle_contract.functions.getAssetPrice(asset_address).call()
        print(f"💲 [{vault_name}] Token price from oracle: {token_price}")

        if raw_total_assets == 0:
            print(f"⚠️ [{vault_name}] totalAssets is 0")
        if token_price == 0:
            print(f"⚠️ [{vault_name}] Oracle returned 0 price for asset")
        if decimals == 0:
            print(f"⚠️ [{vault_name}] Decimals is 0 (unusual)")

        # Step 4: Calculate TVL
        tvl = (raw_total_assets * token_price) / (10 ** decimals * PRICE_DECIMALS)
        print(f"✅ [{vault_name}] TVL: ${tvl:,.2f}")
        return tvl

    except Exception as e:
        print(f"❌ [{vault_name}] Error calculating TVL: {e}")
        return 0.0


# === Main Entry Point ===
def main():
    print("🔌 Connecting to HyperEVM...")
    print("✅ Starting TVL checks for all vaults...")

    for name, address in VAULT_ADDRESSES.items():
        vault_contract, oracle_contract = setup_contracts(address)
        tvl = calculate_vault_tvl(vault_contract, oracle_contract, name)

    

if __name__ == "__main__":
    main()
