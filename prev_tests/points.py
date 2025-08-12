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
user_lped_usd = 1000

# === HypurrFi Setup ===
web3 = Web3(Web3.HTTPProvider(RPC_URL))
if not web3.is_connected():
    print("❌ Failed to connect to  RPC")
    exit()

ORACLE_ADDRESS = web3.to_checksum_address("0x9BE2ac1ff80950DCeb816842834930887249d9A8")
PROTOCOL_DATA_PROVIDER_ADDRESS = web3.to_checksum_address("0x895C799a5bbdCb63B80bEE5BD94E7b9138D977d6")

VAULT_ADDRESSES = {
    "USDe": web3.to_checksum_address("0x835febf893c6dddee5cf762b0f8e31c5b06938ab"),
    "USDT0": web3.to_checksum_address("0xfc5126377f0efc0041c0969ef9ba903ce67d151e"),
    "HYPE": web3.to_checksum_address("0x2900ABd73631b2f60747e687095537B673c06A76"),
}

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

MORPHO_CONTRACT = "0x68e37de8d93d3496ae143f2e900490f6280c57cd"
FELIX_CONTRACT = "0xD4a426F010986dCad727e8dd6eed44cA4A9b7483"

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

# === Functions ===

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

#here starts for hyperlend
'''def get_hyperlend_yields_and_tvl():
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
        return {}'''

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
#here ends for hyperlend

#here starts for hypurrfi
'''def get_hypurrfi_yields_and_tvl():
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

    return results'''

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

#here ends for hypurrfi

#here starts for felix
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
        #print(f"\n🔍 [{vault_name}] Underlying asset: {asset_address}")

        # Step 2: Get total assets and decimals
        raw_total_assets = vault_contract.functions.totalAssets().call()

        # Hardcode decimals for USDT0
        if vault_name == "USDT0":
            decimals = 6
        else:
            decimals = vault_contract.functions.decimals().call()

        #print(f"📦 [{vault_name}] Raw total assets: {raw_total_assets}")
        #print(f"🔢 [{vault_name}] Vault decimals: {decimals}")

        # Step 3: Get token price from oracle
        token_price = oracle_contract.functions.getAssetPrice(asset_address).call()
        #print(f"💲 [{vault_name}] Token price from oracle: {token_price}")

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

def get_felix_yields_and_tvl():
    results = {}
    for token, market_ids in markets_by_token.items():
        #print(f"\n🔹 Token: {token}")
        vault_address = VAULT_ADDRESSES[token]
        morpho_contract, felix_contract, vault_contract, oracle_contract = setup_contracts(web3, vault_address)
        borrow_rates, datas = [], []

        for market_id in market_ids:
            #print(f"\n➡️  Market ID: {market_id}")
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

            #print(f"Supply APY: {supply_apy:.2f}%")
        
        vault_apy = calculate_vault_supply_apy(borrow_rates, datas)
        #print(f"🔸 Vault Supply APY ({token}): {vault_apy:.2f}%")

        vault_tvl = calculate_vault_tvl(vault_contract, oracle_contract, token)
        #print(f"💰 Vault TVL ({token}): ${vault_tvl:,.2f}")

        # Store results in dictionary
        results[token] = {
            "apy": round(vault_apy, 2),
            "tvl": round(vault_tvl, 2)
        }

    return results
#here ends for felix

def calculate_effective_yield(current_apy: float, current_tvl: float, deposit_amount: float) -> float:

    """
    Calculate future yield using the reward dilution formula:
    (Annual Rewards / (TVL + Deposit)) * 100
    
    Args:
        current_apy: Current APY percentage (e.g., 12.36 for 12.36%)
        current_tvl: Current total value locked in USD
        deposit_amount: Proposed deposit amount in USD
    
    Returns:
        Projected APY after deposit
    """
    annual_rewards = (current_apy / 100) * current_tvl
    return (annual_rewards / (current_tvl + deposit_amount)) * 100

def compare_yields(hyperlend_data: dict, hypurrfi_data: dict, felix_data: dict) -> str:
    lines = [
        "📊 *Yield Comparison Report*"
    ]
    
    all_assets = sorted(set(hyperlend_data.keys()) | set(hypurrfi_data.keys()) | set(felix_data.keys()))

    for asset in all_assets:
        protocols = {}

        if asset in hyperlend_data:
            protocols["HyperLend"] = hyperlend_data[asset]
        if asset in hypurrfi_data:
            protocols["HypurrFi"] = hypurrfi_data[asset]
        if asset in felix_data:
            protocols["Felix"] = felix_data[asset]

        if len(protocols) < 2:
            continue  # not enough data to compare

        # Sort protocols by APY descending
        sorted_protocols = sorted(protocols.items(), key=lambda x: x[1]["apy"], reverse=True)
        top1_name, top1_data = sorted_protocols[0]
        top2_name, top2_data = sorted_protocols[1]

        line = f"\n🪙 *{asset}*"
        recommendations = []

        # List all protocol APYs and TVLs
        for name, data in protocols.items():
            line += f"\n  - {name}: {data['apy']:.2f}% (TVL: ${data['tvl']:,.2f})"

        # Yield comparison
        diff = top1_data['apy'] - top2_data['apy']
        if abs(diff) < 0.5:
            recommendations.append("🔹 Top two protocols offer similar yields currently")
        else:
            recommendations.append(f"🔸 {top1_name} offers {abs(diff):.2f}% higher yield than {top2_name}")

            # Max deposit before top1 falls below top2
            max_deposit = max_deposit_to_match_yield(
                top1_data['apy'], top1_data['tvl'], top2_data['apy']
            )
            if max_deposit > 0:
                recommendations.append(
                    f"💰 Max deposit in {top1_name} before it drops below {top2_name}: ${max_deposit:,.2f}"
                )

        lines.append(line)
        if recommendations:
            lines.extend(recommendations)

    return "\n".join(lines)

def max_deposit_to_match_yield(higher_apy, higher_tvl, lower_apy) -> float:
    if lower_apy >= higher_apy or lower_apy == 0:
        return 0.0
    return ((higher_apy - lower_apy) * higher_tvl) / lower_apy

def calculate_points_apy_felix(user_lped_usd: float, vault_tvl_usd: float) -> Tuple[float, float]:

    AIRDROP_PERCENT = 0.20      
    FDV = 100_000_000
    TOTAL_PROJECTED_POINTS = 3_650_926
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
    
    #points_apy = (user_annual_points / user_lped_usd) * 100
    
    value_per_point = (AIRDROP_PERCENT * FDV) / TOTAL_PROJECTED_POINTS
    user_annual_points_value_usd = user_annual_points * value_per_point
    points_value_apy = ((user_annual_points_value_usd - user_lped_usd) / user_lped_usd) * 100
    
    #val = (user_share)*52*100*value_per_point

    return points_value_apy

def calculate_points_apy_hyperlend(user_lped_usd: float, vault_tvl_usd: float) -> float:
    if vault_tvl_usd <= 0 or user_lped_usd <= 0:
        return 0.0
    
    FDV = 500_000_000
    AIRDROP_PERCENT = 0.30
    TOTAL_POINTS = 160_000_000
    #BASE_VALUE_PER_POINT = 0.5
    
    value_per_point = (AIRDROP_PERCENT * FDV) / TOTAL_POINTS 
    WEEKLY_POINTS = 0.019 * TOTAL_POINTS  # ~3,040,000
    
    user_share = user_lped_usd / vault_tvl_usd
    
    user_weekly_points = user_share * WEEKLY_POINTS
    user_annual_points = user_weekly_points * 52
    
    user_annual_points_value_usd = user_annual_points * value_per_point
    
    points_value_apy = ((user_annual_points_value_usd - user_lped_usd) / user_lped_usd) * 100
    
    return points_value_apy


# === Run Script ===
if __name__ == "__main__":
    # Configuration
    
    # Fetch data
    yields_hyperlend = get_hyperlend_yields_and_tvl()
    yields_hypurrfi = get_hypurrfi_yields_and_tvl()
    yields_felix = get_felix_yields_and_tvl()
    
    # Generate reports
    current_report = ["🔍 *Current Yield Report*"]
    comparison_report = compare_yields(yields_hyperlend, yields_hypurrfi, yields_felix)  
    
    for token in sorted(set(yields_hyperlend.keys()) | set(yields_hypurrfi.keys()) | set(yields_felix.keys())):

        # Current yields
        current_report.append(f"\n🪙 *{token}*")
        if token in yields_hyperlend:
            hl = yields_hyperlend[token]
            #hl_points_apy = calculate_points_apy_hyperlend(user_lped_usd, hl['tvl'])
            #print(hl_points_apy)
            current_report.append(f"  - HyperLend: `{hl['apy']:.2f}%` (TVL: ${hl['tvl']:,.2f})")
        if token in yields_hypurrfi:
            hf = yields_hypurrfi[token]
            current_report.append(f"  - HypurrFi:  `{hf['apy']:.2f}%` (TVL: ${hf['tvl']:,.2f})")
        if token in yields_felix:
            fx = yields_felix[token]
            #fx_points_apy = calculate_points_apy_felix(user_lped_usd, fx['tvl'])
            #print(fx_points_apy)
            current_report.append(f"  - Felix:     `{fx['apy']:.2f}%` (TVL: ${fx['tvl']:,.2f})")
    
    # Output or send
    print("\n".join(current_report))
    #print("\n" + "\n".join(projection_report))
    print("\n" + comparison_report)

    # Uncomment if sending via Telegram
    # send_telegram_message("\n".join(current_report))
    # send_telegram_message("\n".join(projection_report))
    # send_telegram_message(comparison_report)
