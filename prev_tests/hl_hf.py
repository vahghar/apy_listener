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

def compare_yields(hyperlend_data: dict, hypurrfi_data: dict, test_deposit: float = 100000) -> str:
    """
    Compare current and projected yields between protocols with recommendations
    
    Args:
        test_deposit: Fixed test amount in USD (default $100k)
    """
    lines = [
        "📊 *Yield Comparison Report*",
        f"⚠️ Projections assume fixed test deposit of ${test_deposit:,.2f}\n"
    ]
    
    for asset in sorted(set(hyperlend_data.keys()).union(hypurrfi_data.keys())):
        hl = hyperlend_data.get(asset)
        hf = hypurrfi_data.get(asset)
        
        line = f"\n🪙 *{asset}*"
        recommendations = []
        
        # HyperLend data
        if hl:
            hl_projected = calculate_effective_yield(hl['apy'], hl['tvl'], test_deposit)
            line += f"\n  - HyperLend: {hl['apy']:.2f}% → {hl_projected:.2f}%"
            if hl['apy'] != 0:  # Only calculate dilution if APY isn't zero
                dilution = ((hl['apy'] - hl_projected)/hl['apy'])
                line += f" (Dilution: {dilution:.1%})"
            else:
                line += " (Dilution: N/A)"
        
        # HypurrFi data
        if hf:
            hf_projected = calculate_effective_yield(hf['apy'], hf['tvl'], test_deposit)
            line += f"\n  - HypurrFi:  {hf['apy']:.2f}% → {hf_projected:.2f}%"
            if hf['apy'] != 0:  # Only calculate dilution if APY isn't zero
                dilution = ((hf['apy'] - hf_projected)/hf['apy'])
                line += f" (Dilution: {dilution:.1%})"
            else:
                line += " (Dilution: N/A)"
        
        # Add comparison and recommendation
        if hl and hf:
            current_diff = hl['apy'] - hf['apy']
            projected_diff = hl_projected - hf_projected
            
            if abs(current_diff) < 0.5:  # Less than 0.5% difference
                recommendations.append("🔹 Both protocols offer similar yields currently")
            elif current_diff > 0:
                recommendations.append(f"🔸 HyperLend offers {abs(current_diff):.2f}% higher yield currently")
            else:
                recommendations.append(f"🔸 HypurrFi offers {abs(current_diff):.2f}% higher yield currently")
                
            if abs(projected_diff) < 0.5:
                recommendations.append("🔹 Projected yields would be similar after deposit")
            elif projected_diff > 0:
                recommendations.append(f"🔹 After deposit, HyperLend would offer {abs(projected_diff):.2f}% better yield")
            else:
                recommendations.append(f"🔹 After deposit, HypurrFi would offer {abs(projected_diff):.2f}% better yield")
                
            # Final recommendation
            if projected_diff > 1.0:  # More than 1% difference
                recommendations.append("✅ RECOMMENDATION: HyperLend is significantly better")
            elif projected_diff < -1.0:
                recommendations.append("✅ RECOMMENDATION: HypurrFi is significantly better")
            else:
                recommendations.append("✅ RECOMMENDATION: Both are comparable, consider other factors")
        
        lines.append(line)
        if recommendations:
            lines.extend(recommendations)
    
    return "\n".join(lines)

POINTS_PER_WEEK = {
    "USDe": 198_380,  
    "USD₮0": 100_000,
    "kHYPE": 50_000
}

TOKEN_VALUE_PER_POINT = 10  # $10 per point
WEEKS_PER_YEAR = 52

def calculate_points_apy(symbol: str, tvl: float) -> float:
    points = POINTS_PER_WEEK.get(symbol, 0)
    if tvl == 0 or points == 0:
        return 0.0
    total_rewards = points * WEEKS_PER_YEAR * TOKEN_VALUE_PER_POINT
    return (total_rewards / tvl) * 100

# === Run Script ===
if __name__ == "__main__":
    # Configuration
    TEST_DEPOSIT_AMOUNT = 100000  # $100k test deposit
    
    # Fetch data
    yields_hyperlend = get_hyperlend_yields_and_tvl()
    yields_hypurrfi = get_hypurrfi_yields_and_tvl()
    
    # Generate reports
    current_report = ["🔍 *Current Yield Report*"]
    projection_report = [f"🔮 *Yield Projections* (Test Deposit: ${TEST_DEPOSIT_AMOUNT:,.2f})"]
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
        projection_report.append(f"\n🪙 *{token}*")
        if token in yields_hyperlend:
            hl = yields_hyperlend[token]
            hl_proj = calculate_effective_yield(hl['apy'], hl['tvl'], TEST_DEPOSIT_AMOUNT)
            projection_report.append(
                f"  - HyperLend: `{hl['apy']:.2f}%` → `{hl_proj:.2f}%` "
                f"(Δ: {hl['apy']-hl_proj:.2f}pp)"
            )
        
        if token in yields_hypurrfi:
            hf = yields_hypurrfi[token]
            if hf['tvl'] > 0:
                hf_proj = calculate_effective_yield(hf['apy'], hf['tvl'], TEST_DEPOSIT_AMOUNT)
                projection_report.append(
                    f"  - HypurrFi:  `{hf['apy']:.2f}%` → `{hf_proj:.2f}%` "
                    f"(Δ: {hf['apy']-hf_proj:.2f}pp)"
                )
            else:
                projection_report.append(f"  - HypurrFi:  `{hf['apy']:.2f}%` (No TVL)")
    
    # Send to Telegram (split long messages)
    #send_telegram_message("\n".join(current_report))
    #send_telegram_message("\n".join(projection_report))
    #send_telegram_message(comparison_report)
    
    # Also print to console
    print("\n".join(current_report))
    print("\n" + "\n".join(projection_report))
    #print("\n" + comparison_report)
