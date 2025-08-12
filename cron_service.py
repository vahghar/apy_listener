import re
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass

import json
import requests
import json
import os
from web3 import Web3
from dotenv import load_dotenv
from telebot import send_telegram_message
import math

load_dotenv()

PRICE_DECIMALS = 10 ** 8
RPC_URL = os.getenv("RPC_URL")
CHAIN = "hyperEvm"

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
# ============================================================================
# PROTOCOL CONFIGURATIONS (from smart contracts)

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
            "HYPE": web3.to_checksum_address("0x5555555555555555555555555555555555555555")
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

# ============================================================================

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

def get_irm_params_for_hypurrfi(reserve_address, supply_usd, borrow_usd):
    base_rate = base_rate = irm_hypurrfi_contract.functions.getBaseVariableBorrowRate().call() / 1e27
    slope1 = irm_hypurrfi_contract.functions.getVariableRateSlope1().call() / 1e27
    slope2 = irm_hypurrfi_contract.functions.getVariableRateSlope2().call() / 1e27
    raw_kink = irm_hypurrfi_contract.functions.OPTIMAL_USAGE_RATIO().call()
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

def get_dynamic_protocol_params():
    """
    Fetch dynamic IRM parameters from chain for both protocols.
    Returns a dict similar to the old PROTOCOL_PARAMS, but live.
    """
    params = {}

    # ===== HyperLend =====
    hyperlend_data = get_hyperlend_yields_and_tvl()
    for token, info in hyperlend_data.items():
        supply_usd = info["tvl"]
        borrow_usd = supply_usd * (info["apy"] / 100)  # You might replace with real borrow amount if available
        
        reserve_address = web3.to_checksum_address("0xC9Fb4fbE842d57EAc1dF3e641a281827493A630e")
        irm_params = get_irm_params_for_hyperlend(reserve_address, supply_usd, borrow_usd)

        params["HyperLend"] = {
            "base_rate": irm_params["base_rate"],
            "slope1": irm_params["slope1"],
            "slope2": irm_params["slope2"],
            "kink": irm_params["kink"],
            "reserve_factor": 0.10,  # Still static unless fetched
            "supply_usd": supply_usd,
            "borrow_usd": borrow_usd
        }

    # ===== HyperFi =====
    hyperfi_data = get_hypurrfi_yields_and_tvl()
    for token, info in hyperfi_data.items():
        supply_usd = info["tvl"]
        borrow_usd = supply_usd * (info["apy"] / 100)  # Replace with actual borrow amount
        
        reserve_address = web3.to_checksum_address("0x9BE2ac1ff80950DCeb816842834930887249d9A8")
        irm_params = get_irm_params_for_hypurrfi(reserve_address, supply_usd, borrow_usd)

        params["HyperFi"] = {
            "base_rate": irm_params["base_rate"],
            "slope1": irm_params["slope1"],
            "slope2": irm_params["slope2"],
            "kink": irm_params["kink"],
            "reserve_factor": 0.10,  # Still static unless fetched
            "supply_usd": supply_usd,
            "borrow_usd": borrow_usd
        }

    return params


WAD = 10**27

PROTOCOL_PARAMS = get_dynamic_protocol_params()

# ============================================================================
# DATA PARSING
# ============================================================================

@dataclass
class CronPoolData:
    """Parsed data from cron job"""
    protocol: str
    current_apr: float  # Current supply APR from cron (for validation)
    tvl: float  # Total value locked (supplied)
    utilization: float  # Utilization rate as decimal (0.8291 for 82.91%)
    
    @property
    def total_borrow(self) -> float:
        """Calculate total borrows from TVL and utilization"""
        return self.tvl * self.utilization
    
    @property
    def available_liquidity(self) -> float:
        """Calculate available liquidity"""
        return self.tvl - self.total_borrow

def parse_cron_data(cron_string: str) -> Dict[str, CronPoolData]:
    """
    Parse cron job data strings into structured data
    
    Example input:
    "hyplend usde - 13.79% apr. USDe supplied/tvl- $2,950,186.42, utilisation rate= 82.91%"
    """
    pools = {}
    
    # Parse HyperLend data
    if "hyplend" in cron_string.lower() or "hyperlend" in cron_string.lower():
        # Extract APR (for validation/comparison)
        apr_match = re.search(r'hyp[er]*lend.*?(\d+\.?\d*)%\s*apr', cron_string.lower())
        apr = float(apr_match.group(1)) / 100 if apr_match else 0
        
        # Extract TVL
        tvl_match = re.search(r'hyp[er]*lend.*?\$([0-9,]+\.?\d*)', cron_string.lower())
        tvl = float(tvl_match.group(1).replace(',', '')) if tvl_match else 0
        
        # Extract utilization
        util_match = re.search(r'hyp[er]*lend.*?utilisation rate\s*=\s*(\d+\.?\d*)%', cron_string.lower())
        utilization = float(util_match.group(1)) / 100 if util_match else 0
        
        pools["HyperLend"] = CronPoolData(
            protocol="HyperLend",
            current_apr=apr,
            tvl=tvl,
            utilization=utilization
        )
    
    # Parse HyperFi data
    if "hypurfi" in cron_string.lower() or "hyperfi" in cron_string.lower():
        # Extract APR
        apr_match = re.search(r'hyp[ue]*rfi.*?(\d+\.?\d*)%\s*apr', cron_string.lower())
        apr = float(apr_match.group(1)) / 100 if apr_match else 0
        
        # Extract TVL
        tvl_match = re.search(r'hyp[ue]*rfi.*?\$([0-9,]+\.?\d*)', cron_string.lower())
        tvl = float(tvl_match.group(1).replace(',', '')) if tvl_match else 0
        
        # Extract utilization
        util_match = re.search(r'hyp[ue]*rfi.*?utilisation rate\s*=\s*(\d+\.?\d*)%', cron_string.lower())
        utilization = float(util_match.group(1)) / 100 if util_match else 0
        
        pools["HyperFi"] = CronPoolData(
            protocol="HyperFi",
            current_apr=apr,
            tvl=tvl,
            utilization=utilization
        )
    
    return pools

# ============================================================================
# INTEREST RATE CALCULATIONS
# ============================================================================

def calculate_borrow_apr(utilization: float, protocol: str) -> float:
    """
    Calculate borrow APR using the kinked model
    """
    params = PROTOCOL_PARAMS[protocol]
    
    if utilization <= params["kink"]:
        # Below kink: base + slope1 * (U / kink)
        if params["kink"] > 0:
            borrow_apr = params["base_rate"] + params["slope1"] * (utilization / params["kink"])
        else:
            borrow_apr = params["base_rate"]
    else:
        # Above kink: base + slope1 + slope2 * ((U - kink) / (1 - kink))
        borrow_apr = (params["base_rate"] + params["slope1"] + 
                     params["slope2"] * ((utilization - params["kink"]) / (1 - params["kink"])))
    
    return borrow_apr

def calculate_supply_apr(utilization: float, protocol: str) -> float:
    """
    Calculate supply APR
    Supply APR = Borrow APR * Utilization * (1 - Reserve Factor)
    """
    borrow_apr = calculate_borrow_apr(utilization, protocol)
    params = PROTOCOL_PARAMS[protocol]
    supply_apr = borrow_apr * utilization * (1 - params["reserve_factor"])
    
    return supply_apr

# ============================================================================
# OPTIMIZER
# ============================================================================

class RealtimeOptimizer:
    """Optimizer for real-time cron job data"""
    
    def __init__(self, pools: Dict[str, CronPoolData], current_position: Dict[str, float],
                 min_gain_bps: float = 5, gas_cost_usd: float = 10, verbose: bool = True):
        """
        Initialize optimizer with parsed cron data
        
        Args:
            pools: Dictionary of parsed pool data
            current_position: Dict with protocol names as keys and balances as values
            min_gain_bps: Minimum basis points gain to consider profitable
            gas_cost_usd: Estimated gas cost in USD
            verbose: Whether to print detailed logs
        """
        self.pools = pools
        self.position = current_position
        self.min_gain_bps = min_gain_bps
        self.gas_cost_usd = gas_cost_usd
        self.verbose = verbose
        
        # Validate parsed APRs against calculated ones
        self._validate_aprs()
    
    def _validate_aprs(self):
        """Validate that parsed APRs match our model calculations"""
        if self.verbose:
            print("\n📊 APR Validation:")
            print("-" * 60)
        
        for name, pool in self.pools.items():
            calculated_apr = calculate_supply_apr(pool.utilization, name)
            if self.verbose:
                print(f"{name}: Reported={pool.current_apr*100:.2f}%, Calculated={calculated_apr*100:.2f}%")
            if abs(calculated_apr - pool.current_apr) > 0.01:  # More than 1% difference
                print(f"  ⚠️  Warning: {name} APR mismatch - using calculated value")
    
    def analyze_move(self, amount: float, from_protocol: str, to_protocol: str) -> Dict:
        """
        Analyze the impact of moving funds
        
        FIXED LOGIC:
        - Withdrawing from a pool INCREASES its utilization (less supply, same borrows)
        - Depositing to a pool DECREASES its utilization (more supply, same borrows)
        """
        if amount > self.position.get(from_protocol, 0):
            return {"error": f"Insufficient balance in {from_protocol}"}
        
        if amount <= 0:
            return {"error": "Amount must be positive"}
        
        # Hard constraint: stay above kink on HyperLend when depositing
        if to_protocol in ("HyperLend",):
            safe_cap = _max_move_to_keep_util_above(self.pools[to_protocol], 0.80)
            if amount > safe_cap:
                return {
                    "error": "Move exceeds kink guard for HyperLend",
                    "reason": f"Amount {amount:.2f} > safe_cap {safe_cap:.2f} to keep util ≥ 80%",
                    "safe_cap": safe_cap
                }

        from_pool = self.pools[from_protocol]
        to_pool = self.pools[to_protocol]
        
        # Calculate new TVLs after the move
        new_tvl_from = from_pool.tvl - amount  # Withdrawing reduces TVL
        new_tvl_to = to_pool.tvl + amount      # Depositing increases TVL
        
        # Calculate new utilizations
        # Utilization = Borrows / Supply (TVL)
        new_util_from = from_pool.total_borrow / new_tvl_from if new_tvl_from > 0 else 1.0
        new_util_to = to_pool.total_borrow / new_tvl_to if new_tvl_to > 0 else 0
        
        # Cap utilization at 100%
        new_util_from = min(new_util_from, 1.0)
        new_util_to = min(new_util_to, 1.0)
        
        # Calculate new APRs based on new utilizations
        new_apr_from = calculate_supply_apr(new_util_from, from_protocol)
        new_apr_to = calculate_supply_apr(new_util_to, to_protocol)
        
        # Calculate current weighted APR
        total_balance = sum(self.position.values())
        current_weighted_apr = 0
        for protocol, balance in self.position.items():
            if balance > 0 and protocol in self.pools:
                current_weighted_apr += calculate_supply_apr(self.pools[protocol].utilization, protocol) * balance
        current_weighted_apr = current_weighted_apr / total_balance if total_balance > 0 else 0
        
        # Calculate new weighted APR after move
        new_balance_from = self.position.get(from_protocol, 0) - amount
        new_balance_to = self.position.get(to_protocol, 0) + amount
        
        new_weighted_apr = (new_balance_from * new_apr_from + new_balance_to * new_apr_to) / total_balance if total_balance > 0 else 0
        
        # Calculate gains
        annual_gain_usd = (new_weighted_apr - current_weighted_apr) * total_balance
        gain_bps = (new_weighted_apr - current_weighted_apr) * 10000
        
        # Check kink crossings
        kink = PROTOCOL_PARAMS[from_protocol]["kink"]
        from_crosses_kink = (
            (from_pool.utilization < kink <= new_util_from) or
            (new_util_from < kink <= from_pool.utilization)
        )
        
        to_crosses_kink = (
            (to_pool.utilization < kink <= new_util_to) or
            (new_util_to < kink <= to_pool.utilization)
        )
        
        return {
            "amount": amount,
            "from": from_protocol,
            "to": to_protocol,
            "current_util": {
                from_protocol: from_pool.utilization,
                to_protocol: to_pool.utilization
            },
            "new_util": {
                from_protocol: new_util_from,
                to_protocol: new_util_to
            },
            "util_change": {
                from_protocol: new_util_from - from_pool.utilization,
                to_protocol: new_util_to - to_pool.utilization
            },
            "current_apr": {
                from_protocol: calculate_supply_apr(from_pool.utilization, from_protocol),
                to_protocol: calculate_supply_apr(to_pool.utilization, to_protocol)
            },
            "new_apr": {
                from_protocol: new_apr_from,
                to_protocol: new_apr_to
            },
            "current_weighted_apr": current_weighted_apr,
            "new_weighted_apr": new_weighted_apr,
            "annual_gain_usd": annual_gain_usd,
            "gain_bps": gain_bps,
            "kink_crossings": {
                from_protocol: from_crosses_kink,
                to_protocol: to_crosses_kink
            },
            "profitable": gain_bps > self.min_gain_bps and annual_gain_usd > self.gas_cost_usd
        }
    
    def find_optimal_move(self) -> Dict:
        """
        Find the optimal amount to move between pools to maximize total yield
        Uses 1000 increments to find the precise optimal distribution
        """
        best_move = None
        best_weighted_apr = -float('inf')
        
        # Calculate current weighted APR as baseline
        total_balance = sum(self.position.values())
        current_weighted_apr = 0
        for protocol, balance in self.position.items():
            if balance > 0 and protocol in self.pools:
                current_weighted_apr += calculate_supply_apr(self.pools[protocol].utilization, protocol) * balance
        current_weighted_apr = current_weighted_apr / total_balance if total_balance > 0 else 0
        
        # Track the best APR we've found (start with current)
        best_weighted_apr = current_weighted_apr
        
        # For detailed tracking
        all_results = []
        
        # Check each possible move direction
        for from_protocol in self.position:
            if self.position[from_protocol] <= 0:
                continue
                
            for to_protocol in self.pools:
                if from_protocol == to_protocol:
                    continue
                
                max_amount = self.position[from_protocol]
                
                # Find kink crossing points
                kink_points = self._find_kink_points(from_protocol, to_protocol, max_amount)
                
                # Create test points with 1000 increments for precise optimization
                test_points = []
                
                # Add kink points (critical points where APR changes dramatically)
                test_points.extend(kink_points)
                
                # Add 1000 evenly spaced points for fine-grained search
                increment = max_amount / 1000
                for i in range(0, 1001):  # 0 to 1000 inclusive
                    test_points.append(i * increment)
                
                # Remove duplicates and sort
                test_points = sorted(set([p for p in test_points if 0 <= p <= max_amount]))
                
                if self.verbose:
                    print(f"\n🔍 Testing {len(test_points)} points from {from_protocol} to {to_protocol}...")
                
                # Test each point
                for i, amount in enumerate(test_points):
                    result = self.analyze_move(amount, from_protocol, to_protocol)
                    
                    if "error" not in result:
                        all_results.append({
                            'amount': amount,
                            'weighted_apr': result["new_weighted_apr"],
                            'from': from_protocol,
                            'to': to_protocol
                        })
                        
                        # Track if this is the best so far
                        if result["new_weighted_apr"] > best_weighted_apr:
                            best_weighted_apr = result["new_weighted_apr"]
                            best_move = result
                            
                            # Print when we find a new best
                            if self.verbose and (i % 100 == 0 or amount in kink_points):
                                print(f"  New best at ${amount:,.0f}: {best_weighted_apr*100:.4f}% APR")
                
                # Fine-tune around the best point found using golden section search
                if best_move and best_move["from"] == from_protocol and best_move["to"] == to_protocol:
                    if self.verbose:
                        print(f"\n🎯 Fine-tuning around ${best_move['amount']:,.0f}...")
                    
                    optimal = self._fine_tune_for_max_apr(
                        best_move["amount"], 
                        from_protocol, 
                        to_protocol,
                        max_amount
                    )
                    result = self.analyze_move(optimal, from_protocol, to_protocol)
                    if "error" not in result and result["new_weighted_apr"] > best_weighted_apr:
                        best_weighted_apr = result["new_weighted_apr"]
                        best_move = result
                        if self.verbose:
                            print(f"  Fine-tuned to ${optimal:,.2f}: {best_weighted_apr*100:.4f}% APR")
        
        # Print summary of search
        if self.verbose and all_results:
            print(f"\n📊 Search Summary:")
            print(f"  Tested {len(all_results)} total combinations")
            print(f"  Current APR: {current_weighted_apr*100:.4f}%")
            print(f"  Best APR found: {best_weighted_apr*100:.4f}%")
            if best_move:
                print(f"  Optimal move: ${best_move['amount']:,.2f} from {best_move['from']} to {best_move['to']}")
        
        # Always return the best move found, even if gain is small
        if best_move is None:
            # No move is better than current position
            return {
                "no_move_needed": True,
                "reason": "Current position is already optimal",
                "current_position": self.position,
                "current_weighted_apr": current_weighted_apr,
                "pool_status": {
                    name: {
                        "utilization": pool.utilization,
                        "apr": calculate_supply_apr(pool.utilization, name),
                        "tvl": pool.tvl,
                        "borrows": pool.total_borrow
                    }
                    for name, pool in self.pools.items()
                }
            }
        
        # Add detailed breakdown to the result
        best_move["detailed_breakdown"] = {
            "tests_performed": len(all_results),
            "kink_points_found": len(kink_points) if 'kink_points' in locals() else 0,
            "improvement_bps": (best_weighted_apr - current_weighted_apr) * 10000,
            "current_yield_annual": current_weighted_apr * total_balance,
            "new_yield_annual": best_weighted_apr * total_balance
        }
        
        # Check if the gain is worth the gas cost
        if best_move["gain_bps"] < 0.1 and best_move["annual_gain_usd"] < self.gas_cost_usd:
            best_move["warning"] = f"Gain of {best_move['gain_bps']:.1f} bps may not cover gas costs"
        
        return best_move
    
    def _fine_tune_for_max_apr(self, initial: float, from_protocol: str, to_protocol: str, max_amount: float) -> float:
        """Fine-tune amount to maximize weighted APR using golden section search"""
        # Golden ratio
        phi = (1 + 5**0.5) / 2
        resphi = 2 - phi
        
        # Define search bounds
        left = max(0, initial - max_amount * 0.1)
        right = min(max_amount, initial + max_amount * 0.1)
        
        # Required precision
        tol = 0.1  # 10 cents precision
        
        # Golden section search
        x1 = left + resphi * (right - left)
        x2 = right - resphi * (right - left)
        
        result1 = self.analyze_move(x1, from_protocol, to_protocol)
        result2 = self.analyze_move(x2, from_protocol, to_protocol)
        
        f1 = result1.get("new_weighted_apr", -float('inf'))
        f2 = result2.get("new_weighted_apr", -float('inf'))
        
        iterations = 0
        while abs(right - left) > tol and iterations < 50:
            iterations += 1
            if f1 > f2:
                right = x2
                x2 = x1
                f2 = f1
                x1 = left + resphi * (right - left)
                result1 = self.analyze_move(x1, from_protocol, to_protocol)
                f1 = result1.get("new_weighted_apr", -float('inf'))
            else:
                left = x1
                x1 = x2
                f1 = f2
                x2 = right - resphi * (right - left)
                result2 = self.analyze_move(x2, from_protocol, to_protocol)
                f2 = result2.get("new_weighted_apr", -float('inf'))
        
        return (left + right) / 2
    
    def _find_kink_points(self, from_protocol: str, to_protocol: str, max_amount: float) -> list:
        """Find amounts that cause utilization to hit kink (80%)"""
        kink = 0.80
        points = []
        
        from_pool = self.pools[from_protocol]
        to_pool = self.pools[to_protocol]
        
        # Withdrawing from 'from_protocol' INCREASES its utilization
        if from_pool.utilization < kink:
            # Find amount that pushes utilization to exactly 80%
            # New util = borrows / (tvl - amount) = kink
            # amount = tvl - (borrows / kink)
            amount_to_kink = from_pool.tvl - (from_pool.total_borrow / kink)
            if 0 < amount_to_kink < max_amount:
                points.append(amount_to_kink)
        
        # Depositing to 'to_protocol' DECREASES its utilization
        if to_pool.utilization > kink:
            # Find amount that reduces utilization to exactly 80%
            # New util = borrows / (tvl + amount) = kink
            # amount = (borrows / kink) - tvl
            amount_to_kink = (to_pool.total_borrow / kink) - to_pool.tvl
            if 0 < amount_to_kink < max_amount:
                points.append(amount_to_kink)
        
        return points
    
    def _fine_tune(self, initial: float, from_protocol: str, to_protocol: str, max_amount: float) -> float:
        """Fine-tune amount using ternary search"""
        left = max(0, initial - max_amount * 0.05)
        right = min(max_amount, initial + max_amount * 0.05)
        
        for _ in range(30):
            if right - left < 1:  # $1 precision
                break
            
            mid1 = left + (right - left) / 3
            mid2 = right - (right - left) / 3
            
            result1 = self.analyze_move(mid1, from_protocol, to_protocol)
            result2 = self.analyze_move(mid2, from_protocol, to_protocol)
            
            gain1 = result1.get("gain_bps", -float('inf'))
            gain2 = result2.get("gain_bps", -float('inf'))
            
            if gain1 > gain2:
                right = mid2
            else:
                left = mid1
        
        return (left + right) / 2

# ============================================================================
# MAIN FUNCTION
# ============================================================================


# --- Kink guard helper: max deposit that keeps utilization ≥ min_util ---
def _max_move_to_keep_util_above(pool, min_util: float) -> float:
    """
    If we deposit x: TVL' = TVL + x, Borrows' = Borrows.
    Util' = Borrows / (TVL + x) ≥ min_util  =>  x ≤ Borrows/min_util - TVL
    """
    tvl = getattr(pool, "tvl", None)
    borrows = getattr(pool, "total_borrow", None)
    if tvl is None or borrows is None:
        return float("inf")
    if min_util <= 0.0:
        return float("inf")
    limit = (borrows / float(min_util)) - tvl
    return max(0.0, float(limit))

def optimize_from_cron_data(cron_data: str, current_hyperfi_deposit: float = 300000, verbose: bool = True) -> Dict:
    """
    Main function to process cron data and return optimization
    
    Args:
        cron_data: String containing pool data from cron job
        current_hyperfi_deposit: Current deposit in HyperFi
        verbose: Whether to show detailed optimization progress
    
    Returns:
        Dictionary with optimization details
    """
    # Parse the cron data
    pools = parse_cron_data(cron_data)
    
    if not pools:
        return {"error": "Failed to parse cron data"}
    
    # Set up current position
    current_position = {
        "HyperFi": current_hyperfi_deposit,
        "HyperLend": 0
    }
    
    # Create optimizer with very low threshold to find ANY improvement
    optimizer = RealtimeOptimizer(
        pools=pools,
        current_position=current_position,
        min_gain_bps=0.1,  # Even 0.1 bps improvement is worth finding
        gas_cost_usd=10,
        verbose=verbose
    )
    
    # Find optimal move
    result = optimizer.find_optimal_move()
    
    return result

def format_recommendation(result: Dict) -> str:
    """Format the optimization result for display"""
    if "no_move_needed" in result:
        output = f"\n✅ {result['reason']}\n"
        if "pool_status" in result:
            output += "\n   Current Pool Status:\n"
            for name, status in result["pool_status"].items():
                output += f"   - {name}: {status['utilization']*100:.2f}% util, {status['apr']*100:.2f}% APR\n"
        if "current_weighted_apr" in result:
            output += f"\n   Your current weighted APR: {result['current_weighted_apr']*100:.2f}%\n"
        return output
    
    if "error" in result:
        output = f"\n❌ {result['error']}\n"
        if "reason" in result:
            output += f"   Reason: {result['reason']}\n"
        if "pool_status" in result:
            output += "\n   Current Pool Status:\n"
            for name, status in result["pool_status"].items():
                output += f"   - {name}: {status['utilization']*100:.2f}% util, {status['apr']*100:.2f}% APR\n"
        if "current_weighted_apr" in result:
            output += f"\n   Your current weighted APR: {result['current_weighted_apr']*100:.2f}%\n"
        return output
    
    # Check for kink warnings
    kink_warnings = []
    if result["kink_crossings"].get(result["from"]):
        kink_warnings.append(f"{result['from']} will cross 80% kink")
    if result["kink_crossings"].get(result["to"]):
        kink_warnings.append(f"{result['to']} will cross 80% kink")
    
    warning_text = ""
    if kink_warnings:
        warning_text = "\n║ ⚠️  WARNING: " + ", ".join(kink_warnings)
    
    # Show utilization direction with arrows
    from_util_change = "↑" if result["util_change"][result["from"]] > 0 else "↓"
    to_util_change = "↑" if result["util_change"][result["to"]] > 0 else "↓"
    
    return f"""
╔═══════════════════════════════════════════════════════════════════╗
║                 🎯 OPTIMIZATION RECOMMENDATION                    ║
╠═══════════════════════════════════════════════════════════════════╣
║ ACTION: Move ${result['amount']:,.2f}
║ FROM: {result['from']} 
║ TO: {result['to']}{warning_text}
╠═══════════════════════════════════════════════════════════════════╣
║ UTILIZATION CHANGES:
║   {result['from']}: {result['current_util'][result['from']]*100:.2f}% → {result['new_util'][result['from']]*100:.2f}% {from_util_change}
║   {result['to']}: {result['current_util'][result['to']]*100:.2f}% → {result['new_util'][result['to']]*100:.2f}% {to_util_change}
╠═══════════════════════════════════════════════════════════════════╣
║ APR CHANGES:
║   {result['from']}: {result['current_apr'][result['from']]*100:.2f}% → {result['new_apr'][result['from']]*100:.2f}%
║   {result['to']}: {result['current_apr'][result['to']]*100:.2f}% → {result['new_apr'][result['to']]*100:.2f}%
╠═══════════════════════════════════════════════════════════════════╣
║ YOUR WEIGHTED APR:
║   Current: {result['current_weighted_apr']*100:.3f}%
║   After Move: {result['new_weighted_apr']*100:.3f}%
║   
║ 💰 GAIN: {result['gain_bps']:.1f} basis points
║ 💵 Annual Extra Yield: ${result['annual_gain_usd']:.2f}
╚═══════════════════════════════════════════════════════════════════╗
"""

# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Example 1: Your exact cron data
    print("=" * 70)
    print("REAL-TIME OPTIMIZATION FROM CRON DATA")
    print("=" * 70)
    
    cron_data = """
    hyplend usde - 13.79% apr. USDe supplied/tvl- $2,950,186.42, utilisation rate= 82.91%
    Hypurfi USDe- 12.31% apr. USDe supplied/tvl- $2,310,000, utilisation rate= 82.19%
    """
    
    print("📊 Current Market Data:")
    print("-" * 70)
    pools = parse_cron_data(cron_data)
    for name, pool in pools.items():
        print(f"{name:10} | APR: {pool.current_apr*100:6.2f}% | TVL: ${pool.tvl:13,.2f} | Util: {pool.utilization*100:6.2f}%")
        print(f"           | Borrows: ${pool.total_borrow:13,.2f} | Available: ${pool.available_liquidity:13,.2f}")
    
    print("\n💼 Your Position:")
    print("-" * 70)
    print("HyperFi: $200,000")
    print("HyperLend: $0")
    print(f"Current Yield: $200,000 × 12.31% = ${300000 * 0.1231:,.2f}/year")
    
    # Run optimization
    result = optimize_from_cron_data(cron_data, current_hyperfi_deposit=300000)
    
    print(format_recommendation(result))
    
    # Show why this is optimal with detailed breakdown
    if "amount" in result and result["amount"] > 0:
        print("\n🎯 Why This Is Optimal:")
        print("-" * 70)
        print(f"• Moving ${result['amount']:,.2f} optimally balances the yield differential")
        print(f"\nUtilization Changes:")
        print(f"  HyperFi: {result['current_util']['HyperFi']*100:.2f}% → {result['new_util']['HyperFi']*100:.2f}% {'↑' if result['util_change']['HyperFi'] > 0 else '↓'}")
        print(f"  HyperLend: {result['current_util']['HyperLend']*100:.2f}% → {result['new_util']['HyperLend']*100:.2f}% {'↑' if result['util_change']['HyperLend'] > 0 else '↓'}")
        
        print(f"\nAPR Changes (this is key!):")
        print(f"  HyperFi: {result['current_apr']['HyperFi']*100:.2f}% → {result['new_apr']['HyperFi']*100:.2f}%")
        print(f"  HyperLend: {result['current_apr']['HyperLend']*100:.2f}% → {result['new_apr']['HyperLend']*100:.2f}%")
        
        new_balance_hf = 300000 - result["amount"]
        new_balance_hl = result["amount"]
        
        print(f"\n💰 Yield Calculation:")
        print(f"  Before: $200,000 × {result['current_weighted_apr']*100:.2f}% = ${300000 * result['current_weighted_apr']:,.2f}/year")
        print(f"  After:")
        print(f"    HyperFi: ${new_balance_hf:,.2f} × {result['new_apr']['HyperFi']*100:.2f}% = ${new_balance_hf * result['new_apr']['HyperFi']:,.2f}/year")
        print(f"    HyperLend: ${new_balance_hl:,.2f} × {result['new_apr']['HyperLend']*100:.2f}% = ${new_balance_hl * result['new_apr']['HyperLend']:,.2f}/year")
        print(f"    Total: ${(new_balance_hf * result['new_apr']['HyperFi'] + new_balance_hl * result['new_apr']['HyperLend']):,.2f}/year")
        print(f"\n  📈 Additional yield: ${result['annual_gain_usd']:,.2f}/year ({result['gain_bps']:.1f} bps)")
        
        # Show if there are kink considerations
        if result.get('kink_crossings', {}).get('HyperLend'):
            print(f"\n⚠️  Note: This move crosses HyperLend's 80% kink threshold")
        if result.get('kink_crossings', {}).get('HyperFi'):
            print(f"\n⚠️  Note: This move crosses HyperFi's 80% kink threshold")
        
        # Show detailed breakdown if available
        if "detailed_breakdown" in result:
            print(f"\n📊 Optimization Stats:")
            print(f"  • Tested {result['detailed_breakdown']['tests_performed']} different amounts")
            print(f"  • Found {result['detailed_breakdown']['kink_points_found']} critical kink points")
            print(f"  • Improvement: {result['detailed_breakdown']['improvement_bps']:.2f} basis points")
    
    # Show detailed impact analysis
    print("\n" + "=" * 70)
    print("DETAILED IMPACT ANALYSIS - Finding the Optimal Distribution")
    print("=" * 70)
    
    optimizer = RealtimeOptimizer(
        pools=parse_cron_data(cron_data),
        current_position={"HyperFi": 300000, "HyperLend": 0},
        min_gain_bps=0.1,  # Find any improvement
        verbose=False  # Suppress verbose output for the table
    )
    
    print("\nOptimization Table - Finding Maximum Yield Distribution:")
    print("-" * 120)
    print(f"{'Amount':<15} {'HF Balance':<15} {'HL Balance':<15} {'HF Util→APR':<20} {'HL Util→APR':<20} {'Weighted APR':<15} {'Annual Yield':<15} {'Note':<10}")
    print("-" * 120)
    
    best_apr = 0
    best_amount = 0
    best_yield = 0
    
    # Test key amounts including around the expected optimum
    test_amounts = [0, 10000, 20000, 30000, 40000, 45000, 50000, 55000, 60000, 70000, 80000, 
                   90000, 100000, 110000, 120000, 140000, 160000, 180000, 300000]
    
    for amount in test_amounts:
        result = optimizer.analyze_move(amount, "HyperFi", "HyperLend")
        if "error" not in result:
            hf_balance = 300000 - amount
            hl_balance = amount
            
            hf_util_apr = f"{result['new_util']['HyperFi']*100:.1f}%→{result['new_apr']['HyperFi']*100:.2f}%"
            hl_util_apr = f"{result['new_util']['HyperLend']*100:.1f}%→{result['new_apr']['HyperLend']*100:.2f}%"
            
            annual_yield = hf_balance * result['new_apr']['HyperFi'] + hl_balance * result['new_apr']['HyperLend']
            
            # Check if this is the best
            note = ""
            if result['new_weighted_apr'] > best_apr:
                best_apr = result['new_weighted_apr']
                best_amount = amount
                best_yield = annual_yield
                note = "← BEST"
            
            # Check for kink crossings
            if result['kink_crossings']['HyperFi']:
                note += " ⚠️HF"
            if result['kink_crossings']['HyperLend']:
                note += " ⚠️HL"
            
            print(f"${amount:<14,} ${hf_balance:<14,} ${hl_balance:<14,} {hf_util_apr:<20} {hl_util_apr:<20} "
                  f"{result['new_weighted_apr']*100:>13.3f}% ${annual_yield:>14,.2f} {note}")
    
    print("-" * 120)
    print(f"\n💡 Optimal Distribution: Move ${best_amount:,} to HyperLend")
    print(f"   • Keep ${300000-best_amount:,} in HyperFi")  
    print(f"   • Weighted APR: {best_apr*100:.3f}%")
    print(f"   • Annual Yield: ${best_yield:,.2f}")
    print(f"   • Gain vs current: ${best_yield - 24620:.2f}/year")
    
    print("\n📝 Key Insights:")
    print("-" * 70)
    print("• The optimizer tests 1000+ points to find the exact optimum")
    print("• HyperLend at 82.91% util offers 13.79% but will drop if too much is deposited")
    print("• HyperFi at 82.19% util offers 12.31% but will increase if funds are withdrawn")
    print("• The sweet spot maximizes (balance_in_HF × APR_HF) + (balance_in_HL × APR_HL)")
    print("• ⚠️ marks where utilization crosses the 80% kink threshold")
    print("• Even small optimizations compound significantly over time!")
    
    # Example 2: More favorable scenario
    print("\n\n" + "=" * 70)
    print("SCENARIO 2: HyperLend Below Kink (More Favorable)")
    print("=" * 70)
    
    cron_data_2 = """
    hyplend usde - 3.50% apr. USDe supplied/tvl- $5,000,000, utilisation rate= 75.00%
    Hypurfi USDe- 4.25% apr. USDe supplied/tvl- $3,000,000, utilisation rate= 85.00%
    """
    
    pools2 = parse_cron_data(cron_data_2)
    print("📊 Market Data:")
    for name, pool in pools2.items():
        print(f"{name:10} | APR: {pool.current_apr*100:6.2f}% | TVL: ${pool.tvl:13,.2f} | Util: {pool.utilization*100:6.2f}%")
    
    result2 = optimize_from_cron_data(cron_data_2, current_hyperfi_deposit=300000, verbose=False)
    print(format_recommendation(result2))

def recommended_move_amount_from_cron(cron_data: str, current_hyperfi_deposit: float = 300000) -> dict:
    """
    Returns a minimal recommendation dict with amount/from/to, obeying kink guard.
    """
    pools = parse_cron_data(cron_data)
    opt = RealtimeOptimizer(
        pools=pools,
        current_position={"HyperFi": current_hyperfi_deposit, "HyperLend": 0},
        min_gain_bps=0.1,
        verbose=False
    )
    best = opt.find_optimal_move()
    if isinstance(best, dict):
        return {"amount": best.get("amount", 0.0), "from": best.get("from"), "to": best.get("to")}
    return {"error": "No recommendation produced"}