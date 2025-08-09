import json
from web3 import Web3
from typing import Dict, Tuple, Optional, Any
from telebot import send_telegram_message
import math

RPC_URL = "https://rpc.hyperliquid.xyz/evm" 

PRICE_DECIMALS = 10 ** 8


web3 = Web3(Web3.HTTPProvider(RPC_URL))
if not web3.is_connected():
    send_telegram_message("❌ Failed to connect to HypurrFi RPC")
    exit()

MORPHO_CONTRACT = "0x68e37de8d93d3496ae143f2e900490f6280c57cd"
FELIX_CONTRACT = "0xD4a426F010986dCad727e8dd6eed44cA4A9b7483"
ORACLE_ADDRESS = web3.to_checksum_address("0x9BE2ac1ff80950DCeb816842834930887249d9A8")

VAULT_ADDRESSES = {
    "USDe": web3.to_checksum_address("0x835febf893c6dddee5cf762b0f8e31c5b06938ab"),
    "USDT0": web3.to_checksum_address("0xfc5126377f0efc0041c0969ef9ba903ce67d151e"),
    "HYPE": web3.to_checksum_address("0x2900ABd73631b2f60747e687095537B673c06A76"),
}

markets_by_token = {
    "USDe": [
        "0x292f0a3ddfb642fbaadf258ebcccf9e4b0048a9dc5af93036288502bde1a71b1",  # WHYPE / USDe
        "0x5fe3ac84f3a2c4e3102c3e6e9accb1ec90c30f6ee87ab1fcafc197b8addeb94c",  # UBTC / USDe
    ],
    "USDT0": [
        "0xf9f0473b23ebeb82c83078f0f0f77f27ac534c9fb227cb4366e6057b6163ffbf",  # UETH / USDT0
        "0xace279b5c6eff0a1ce7287249369fa6f4d3d32225e1629b04ef308e0eb568fb0",  # WHYPE / USDT0
        "0x707dddc200e95dc984feb185abf1321cabec8486dca5a9a96fb5202184106e54",  # UBTC / USDT0
        "0xb39e45107152f02502c001a46e2d3513f429d2363323cdaffbc55a951a69b998",  # wstHYPE / USDT0
        "0x86d7bc359391486de8cd1204da45c53d6ada60ab9764450dc691e1775b2e8d69",  # hwHLP / USDT0
        "0xd4fd53f612eaf411a1acea053cfa28cbfeea683273c4133bf115b47a20130305",  # wHLP / USDT0
        "0x78f6b57d825ef01a5dc496ad1f426a6375c685047d07a30cd07ac5107ffc7976",  # kHYPE / USDT0
        "0x888679b2af61343a4c7c0da0639fc5ca5fc5727e246371c4425e4d634c09e1f6",  # kHYPE-PT / USDT0
    ],
    "HYPE": [
        "0x64e7db7f042812d4335947a7cdf6af1093d29478aff5f1ccd93cc67f8aadfddc",  # kHYPE / HYPE
        "0xe9a9bb9ed3cc53f4ee9da4eea0370c2c566873d5de807e16559a99907c9ae227",  # wstHYPE / HYPE
        "0x1df0d0ebcdc52069692452cb9a3e5cf6c017b237378141eaf08a05ce17205ed6",  # kHYPE-PT / HYPE
    ],
}


def load_abi(filename: str) -> list:
    """Load ABI from JSON file"""
    with open(filename, 'r') as f:
        return json.load(f)

def setup_contracts(web3: Web3, vault_address: str) -> Tuple[Any, Any]:
    morpho_abi = load_abi('abi/Morpho.json')
    felix_abi = load_abi('abi/Felix.json')
    vault_abi = load_abi('abi/vault1.json')
    oracle_abi = load_abi('abi/HyFiOracle.json')

    morpho_contract = web3.eth.contract(
        address=web3.to_checksum_address(MORPHO_CONTRACT),
        abi=morpho_abi
    )

    felix_contract = web3.eth.contract(
        address=web3.to_checksum_address(FELIX_CONTRACT),
        abi=felix_abi
    )
    
    vault_contract = web3.eth.contract(
        address=web3.to_checksum_address(vault_address),
        abi=vault_abi
    )

    oracle_contract = web3.eth.contract(
        address=ORACLE_ADDRESS,
        abi=oracle_abi
    )

    return morpho_contract, felix_contract, vault_contract , oracle_contract

def fetch_market_params(morpho_contract, market_id: str) -> Dict[str, Any]:
    """Fetch MarketParams from Morpho contract"""
    try:
        market_params = morpho_contract.functions.idToMarketParams(market_id).call()
        
        # Convert tuple to dict for easier handling
        return {
            'loanToken': market_params[0],
            'collateralToken': market_params[1],
            'oracle': market_params[2],
            'irm': market_params[3],
            'lltv': market_params[4]
        }
    except Exception as e:
        print(f"Error fetching market params: {e}")
        return None

def fetch_market_data(morpho_contract, market_id: str) -> Dict[str, Any]:
    """Fetch Market struct from Morpho contract"""
    try:
        market_data = morpho_contract.functions.market(market_id).call()
        
        # Convert tuple to dict for easier handling
        
        return {
            'totalSupplyAssets': market_data[0],
            'totalSupplyShares': market_data[1],
            'totalBorrowAssets': market_data[2],
            'totalBorrowShares': market_data[3],
            'lastUpdate': market_data[4],
            'fee': market_data[5]
        }
    except Exception as e:
        print(f"Error fetching market data: {e}")
        return None

def call_borrow_rate_view(felix_contract, market_params: Dict, market_data: Dict) -> int:
    """Call borrowRateView function on Felix contract"""
    try:
        # Convert dicts back to tuples for contract call
        market_params_tuple = (
            market_params['loanToken'],
            market_params['collateralToken'],
            market_params['oracle'],
            market_params['irm'],
            market_params['lltv']
        )
        
        market_data_tuple = (
            market_data['totalSupplyAssets'],
            market_data['totalSupplyShares'],
            market_data['totalBorrowAssets'],
            market_data['totalBorrowShares'],
            market_data['lastUpdate'],
            market_data['fee']
        )
        
        borrow_rate = felix_contract.functions.borrowRateView(
            market_params_tuple, 
            market_data_tuple
        ).call()
        
        return borrow_rate
    except Exception as e:
        print(f"Error calling borrowRateView: {e}")
        return None

def calculate_borrow_apy(borrow_rate: int) -> float:
    """
    Compute borrow APY from borrow rate (per second), compounded annually.
    Assumes borrow_rate is in 1e18 units (wei).
    """
    rate_per_second = borrow_rate / 1e18  # Adjust if your unit is different
    seconds_per_year = 365 * 24 * 3600
    borrow_apy = (1 + rate_per_second) ** seconds_per_year - 1
    return borrow_apy * 100  # percentage

def calculate_supply_apy(borrow_rate: int, market_data: Dict[str, Any]) -> float:
    """Compute supply APY from borrow rate, utilization, and fee"""
    rate_per_second = borrow_rate / 1e18
    # Utilization = borrowed assets / supplied assets
    util = 0
    if market_data['totalSupplyAssets'] > 0:
        util = market_data['totalBorrowAssets'] / market_data['totalSupplyAssets']

    reserve_factor = market_data['fee'] / 1e18
    # Supply rate per second
    supply_rate = rate_per_second * util * (1 - reserve_factor)
    # Annualize (compounding per second)
    seconds_per_year = 365 * 24 * 3600
    supply_apy = math.exp(supply_rate * seconds_per_year) - 1

    return supply_apy * 100  # in percentage

def calculate_vault_supply_apy(borrow_rates: list, market_datas: list) -> float:
    total_supply = sum(market_data['totalSupplyAssets'] for market_data in market_datas)
    if total_supply == 0:
        return 0.0
    weighted = 0.0
    for br, market_data in zip(borrow_rates, market_datas):
        weight = market_data['totalSupplyAssets'] / total_supply
        weighted += weight * calculate_supply_apy(br, market_data)
    return weighted

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

def calculate_points_apy_felix(user_lped_usd: float, vault_tvl_usd: float) -> Tuple[float, float]:

    """
    Calculate Points APY for a user.
    
    :param user_lped_usd: User's deposited USD value (LPed amount in USD).
    :param vault_tvl_usd: Total USD value locked in the vault.
    :return: (points_apy_percent, points_value_apy_percent)
    """

    AIRDROP_PERCENT = 0.20      
    FDV = 100_000_000
    TOTAL_PROJECTED_POINTS = 7_593_928
    WEEKLY_POINTS = 146_037
    user_lped_usd = 1000

    value_per_point = (AIRDROP_PERCENT * FDV) / TOTAL_PROJECTED_POINTS
    weekly_points_value_usd = WEEKLY_POINTS * value_per_point
    annual_points_value_usd = weekly_points_value_usd * 52

    if vault_tvl_usd <= 0 or user_lped_usd <= 0:
        return 0.0, 0.0
    
    user_share = user_lped_usd / vault_tvl_usd
    
    user_weekly_points = user_share * WEEKLY_POINTS
    user_annual_points = user_weekly_points * 52
    
    points_apy = (user_annual_points / user_lped_usd) * 100
    
    value_per_point = (AIRDROP_PERCENT * FDV) / TOTAL_PROJECTED_POINTS
    user_annual_points_value_usd = user_annual_points * value_per_point
    points_value_apy = ((user_annual_points_value_usd - user_lped_usd) / user_lped_usd) * 100
    
    return points_value_apy

def calculate

def main():
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("Failed to connect to HyperEVM RPC")
        return

    print("✅ Connected to HyperEVM")

    results = {}  # final results like {"USDe": {"apy": x, "tvl": y}, ...}

    for token, market_ids in markets_by_token.items():
        print(f"\n🔹 Token: {token}")
        vault_address = VAULT_ADDRESSES[token]
        morpho_contract, felix_contract, vault_contract, oracle_contract = setup_contracts(w3, vault_address)
        borrow_rates, datas = [], []

        for market_id in market_ids:
            print(f"\n➡️  Market ID: {market_id}")
            market_params = fetch_market_params(morpho_contract, market_id)
            if not market_params:
                continue

            market_data = fetch_market_data(morpho_contract, market_id)
            if not market_data:
                continue

            borrow_rate = call_borrow_rate_view(felix_contract, market_params, market_data)
            if borrow_rate is None:
                continue

            borrow_apy = calculate_borrow_apy(borrow_rate)
            supply_apy = calculate_supply_apy(borrow_rate, market_data)

            borrow_rates.append(borrow_rate)
            datas.append(market_data)

            print(f"Supply APY: {supply_apy:.2f}%")
        
        vault_apy = calculate_vault_supply_apy(borrow_rates, datas)
        print(f"🔸 Vault Supply APY ({token}): {vault_apy:.2f}%")

        vault_tvl = calculate_vault_tvl(vault_contract, oracle_contract, token)
        print(f"💰 Vault TVL ({token}): ${vault_tvl:,.2f}")

        #points_apy = (annual_points_value_usd / vault_tvl) * 100
        #print(f"💎 Points APY ({token}): {points_apy:.2f}%")

        points_apy_usd = calculate_points_apy_felix(user_lped_usd, vault_tvl)
        #print(f"💎 Points APY ({token}): {points_apy_points:.2f}% (in points)")
        print(f"💵 Points Value APY ({token}): {points_apy_usd:.2f}% (in USD value)")

        # Store results in dictionary
        results[token] = {
            "apy": round(vault_apy, 2),
            "tvl": round(vault_tvl, 2)
        }

    return results


if __name__ == "__main__":
    main()