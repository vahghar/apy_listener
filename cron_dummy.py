"""
Real-time Pool Optimizer with Equilibrium Strategy
Finds stable positions that maximize yield while avoiding arbitrage triggers
"""

import re
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
import json
import os
import sys
from pathlib import Path

print("Attempting to set up Django environment...")
try:
    # Set USE_SQLITE environment variable to use a local file-based database
    os.environ['USE_SQLITE'] = 'true'

    # Add the project root to the Python path to allow importing data modules
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Configure Django settings before importing any models
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'defai_backend.settings')
    import django
    django.setup()

    # Import the data access object for saving results
    from data.data_access_layer import OptimizationResultDAO
    print("Django environment setup successful.")
except Exception as e:
    print(f"Error during Django setup: {e}")
    sys.exit(1)

# ============================================================================
# PROTOCOL CONFIGURATIONS (from smart contracts)
# ============================================================================

WAD = 10**27

PROTOCOL_PARAMS = {
    "HyperLend": {
        "kink": 0.80,
        "base_rate": 0.0,
        "slope1": 0.052,  # 5.2%
        "slope2": 1.00,   # 100%
        "reserve_factor": 0.10
    },
    "HyperFi": {
        "kink": 0.80,
        "base_rate": 0.0,
        "slope1": 0.040,  # 4.0%
        "slope2": 0.75,   # 75%
        "reserve_factor": 0.10
    }
}

# ============================================================================
# DATA PARSING
# ============================================================================

@dataclass
class CronPoolData:
    """Parsed data from cron job"""
    protocol: str
    current_apr: float  # Current supply APR from cron (TRUST THIS!)
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
        # Extract APR
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
# APR ESTIMATION (for future state prediction)
# ============================================================================

def estimate_apr_at_utilization(utilization: float, current_util: float,
                               current_apr: float, protocol: str) -> float:
    """
    Estimate the SUPPLY APR at a new utilization using a piecewise linear
    interest rate model and protocol parameters.
    
    borrow_rate(util) =
      base + slope1 * (util/kink)                  if util <= kink
      base + slope1 + slope2 * ((util-kink)/(1-kink))  otherwise
    
    supply_apr ≈ borrow_rate * (1 - reserve_factor) * util
    """
    params = PROTOCOL_PARAMS[protocol]
    kink = params["kink"]
    base_rate = params["base_rate"]
    slope1 = params["slope1"]
    slope2 = params["slope2"]
    reserve_factor = params["reserve_factor"]

    def model_supply(u: float) -> float:
        u = max(0.0, min(0.9999, u))
        if u <= kink:
            borrow = base_rate + slope1 * (u / max(kink, 1e-6))
        else:
            borrow = base_rate + slope1 + slope2 * ((u - kink) / max(1 - kink, 1e-6))
        return borrow * (1 - reserve_factor) * u

    # Calibrate the model so it passes through the observed current APR
    base_at_current = model_supply(current_util)
    scale = (current_apr / base_at_current) if base_at_current > 0 else 1.0
    return model_supply(utilization) * scale

# ============================================================================
# EQUILIBRIUM OPTIMIZER
# ============================================================================

class EquilibriumOptimizer:
    """Optimizer that finds stable positions avoiding arbitrage triggers"""
    
    def __init__(self, pools: Dict[str, CronPoolData], current_position: Dict[str, float],
                 min_gain_bps: float = 10, max_spread_bps: float = 150, 
                 min_safe_util: float = 0.805, max_safe_util: float = 0.87,
                 gas_cost_usd: float = 10, verbose: bool = True):
        """
        Initialize equilibrium-aware optimizer
        
        Args:
            pools: Dictionary of parsed pool data
            current_position: Dict with protocol names as keys and balances as values
            min_gain_bps: Minimum basis points gain to consider move worthwhile
            max_spread_bps: Maximum APR spread to avoid arbitrage (150 = 1.5%)
            min_safe_util: Minimum safe utilization (just above kink)
            max_safe_util: Maximum safe utilization (before extreme rates)
            gas_cost_usd: Estimated gas cost in USD
            verbose: Whether to show detailed optimization progress
        """
        self.pools = pools
        self.position = current_position
        self.min_gain_bps = min_gain_bps
        self.max_spread_bps = max_spread_bps
        self.min_safe_util = min_safe_util  # 80.5% - safely above kink
        self.max_safe_util = max_safe_util  # 87% - before rates go extreme
        self.gas_cost_usd = gas_cost_usd
        self.verbose = verbose
    
    def analyze_move(self, amount: float, from_protocol: str, to_protocol: str) -> Dict:
        """
        Analyze move with equilibrium considerations
        """
        if amount > self.position.get(from_protocol, 0):
            return {"error": f"Insufficient balance in {from_protocol}"}
        
        if amount <= 0:
            return {"error": "Amount must be positive"}
        
        from_pool = self.pools[from_protocol]
        to_pool = self.pools[to_protocol]
        
        # Calculate new TVLs and utilizations
        new_tvl_from = from_pool.tvl - amount
        new_tvl_to = to_pool.tvl + amount
        
        new_util_from = from_pool.total_borrow / new_tvl_from if new_tvl_from > 0 else 1.0
        new_util_to = to_pool.total_borrow / new_tvl_to if new_tvl_to > 0 else 0
        
        # Estimate new APRs using market data
        new_apr_from = estimate_apr_at_utilization(
            new_util_from, from_pool.utilization, from_pool.current_apr, from_protocol
        )
        new_apr_to = estimate_apr_at_utilization(
            new_util_to, to_pool.utilization, to_pool.current_apr, to_protocol
        )
        
        # Calculate spread
        apr_spread = abs(new_apr_from - new_apr_to)
        
        # Check if position is stable (won't trigger arbitrage), but allow
        # convergence moves that reduce an already-large spread.
        current_spread = abs(from_pool.current_apr - to_pool.current_apr)
        reduces_spread = apr_spread < current_spread
        spread_within_limit = apr_spread <= self.max_spread_bps / 10000
        util_within_limits = (
            self.min_safe_util <= new_util_from <= self.max_safe_util and
            self.min_safe_util <= new_util_to <= self.max_safe_util
        )

        is_stable = util_within_limits and (spread_within_limit or reduces_spread)
        
        # Calculate weighted APRs
        total_balance = sum(self.position.values())
        current_weighted_apr = 0
        for protocol, balance in self.position.items():
            if balance > 0 and protocol in self.pools:
                current_weighted_apr += self.pools[protocol].current_apr * balance
        current_weighted_apr = current_weighted_apr / total_balance if total_balance > 0 else 0
        
        new_balance_from = self.position.get(from_protocol, 0) - amount
        new_balance_to = self.position.get(to_protocol, 0) + amount
        new_weighted_apr = (new_balance_from * new_apr_from + new_balance_to * new_apr_to) / total_balance
        
        # Calculate gains
        annual_gain_usd = (new_weighted_apr - current_weighted_apr) * total_balance
        gain_bps = (new_weighted_apr - current_weighted_apr) * 10000
        
        # Calculate stability score (0-1, higher is better)
        stability_score = 0
        if is_stable:
            # Prefer utilizations around 82-83%
            optimal_util = 0.825
            util_score = 1 - (abs(new_util_from - optimal_util) + abs(new_util_to - optimal_util)) / 0.2
            
            # Prefer smaller spreads
            spread_score = 1 - (apr_spread / (self.max_spread_bps / 10000))
            
            stability_score = (util_score * 0.6 + spread_score * 0.4)
        
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
            "current_apr": {
                from_protocol: from_pool.current_apr,
                to_protocol: to_pool.current_apr
            },
            "new_apr": {
                from_protocol: new_apr_from,
                to_protocol: new_apr_to
            },
            "apr_spread": apr_spread,
            "is_stable": is_stable,
            "stability_score": stability_score,
            "current_weighted_apr": current_weighted_apr,
            "new_weighted_apr": new_weighted_apr,
            "annual_gain_usd": annual_gain_usd,
            "gain_bps": gain_bps,
            "profitable": gain_bps > self.min_gain_bps and annual_gain_usd > self.gas_cost_usd
        }
    
    def find_optimal_equilibrium(self) -> Dict:
        """
        Find optimal move that balances yield and stability
        """
        best_move = None
        best_score = -float('inf')
        # Track a convergence-specific recommendation: minimize APR spread while safe
        best_convergence_move = None
        smallest_spread = float('inf')
        all_candidates = []
        
        # Calculate current state
        total_balance = sum(self.position.values())
        current_weighted_apr = sum(
            self.pools[p].current_apr * b for p, b in self.position.items() 
            if b > 0 and p in self.pools
        ) / total_balance if total_balance > 0 else 0
        
        # Test moves in both directions
        for from_protocol in self.position:
            if self.position[from_protocol] <= 0:
                continue
                
            for to_protocol in self.pools:
                if from_protocol == to_protocol:
                    continue
                
                max_amount = self.position[from_protocol]
                
                # Calculate max safe amount (don't push either pool outside safe zone)
                from_pool = self.pools[from_protocol]
                to_pool = self.pools[to_protocol]
                
                # Max amount we can withdraw from from_pool without exceeding max_safe_util
                max_withdraw_allowed = from_pool.tvl - (from_pool.total_borrow / self.max_safe_util) if self.max_safe_util > 0 else max_amount
                max_from_util = min(max_amount, max(0, max_withdraw_allowed))
                
                # Max amount before to_pool goes below min_safe_util
                max_to_util = max(
                    0,
                    (to_pool.total_borrow / self.min_safe_util) - to_pool.tvl
                )
                
                # Use the most restrictive limit
                safe_max = min(max_amount, max(0, max_from_util))
                if max_to_util > 0:
                    safe_max = min(safe_max, max_to_util)
                
                if safe_max <= 0:
                    continue
                
                # Test increments (more granular for better optimization)
                test_amounts = []
                for i in range(0, 101, 2):  # Every 2%
                    test_amounts.append(safe_max * i / 100)
                
                if self.verbose:
                    print(f"\n🔍 Testing {from_protocol} → {to_protocol} (max safe: ${safe_max:,.0f})...")
                
                for amount in test_amounts:
                    if amount == 0:
                        continue
                        
                    result = self.analyze_move(amount, from_protocol, to_protocol)
                    
                    if "error" not in result:
                        # Calculate combined score (yield + stability)
                        yield_score = result["gain_bps"] / 100  # Normalize to ~0-1 range
                        stability_score = result["stability_score"]
                        
                        # Weight: 60% stability, 40% yield for equilibrium strategy
                        combined_score = stability_score * 0.6 + yield_score * 0.4
                        
                        # Always track convergence candidate if it reduces spread and stays within util bounds
                        if (
                            self.min_safe_util <= result["new_util"][from_protocol] <= self.max_safe_util and
                            self.min_safe_util <= result["new_util"][to_protocol] <= self.max_safe_util
                        ):
                            if result["apr_spread"] < smallest_spread:
                                smallest_spread = result["apr_spread"]
                                best_convergence_move = result

                        # Only consider stable or converging positions for the main recommended move
                        if result["is_stable"]:
                            all_candidates.append({
                                **result,
                                "combined_score": combined_score
                            })
                            
                            if combined_score > best_score:
                                best_score = combined_score
                                best_move = result
                                
                                if self.verbose:
                                    print(f"  ✓ New best: ${amount:,.0f} "
                                          f"(APR: {result['new_weighted_apr']*100:.2f}%, "
                                          f"Spread: {result['apr_spread']*10000:.0f}bps, "
                                          f"Stability: {stability_score:.2f})")
        
        if self.verbose and all_candidates:
            print(f"\n📊 Equilibrium Analysis:")
            print(f"  Found {len(all_candidates)} stable positions")
            print(f"  Current APR: {current_weighted_apr*100:.2f}%")
            if best_move:
                print(f"  Best equilibrium APR: {best_move['new_weighted_apr']*100:.2f}%")
                print(f"  Best stability score: {best_move['stability_score']:.2f}")
        
        if best_move is None:
            return {
                "no_move_needed": True,
                "reason": "Current position is already at equilibrium",
                "current_position": self.position,
                "current_weighted_apr": current_weighted_apr,
                "pool_status": {
                    name: {
                        "utilization": pool.utilization,
                        "apr": pool.current_apr,
                        "tvl": pool.tvl,
                        "borrows": pool.total_borrow
                    }
                    for name, pool in self.pools.items()
                },
                "convergence_recommendation": best_convergence_move
            }
        
        # Add equilibrium analysis to result
        best_move["equilibrium_analysis"] = {
            "stability_score": best_move["stability_score"],
            "apr_spread_bps": best_move["apr_spread"] * 10000,
            "both_in_safe_zone": best_move["is_stable"],
            "estimated_rebalance_frequency": "Low" if best_move["stability_score"] > 0.7 else "Medium",
            "arbitrage_risk": "Low" if best_move["apr_spread"] < 0.01 else "Medium"
        }
        # Attach convergence suggestion alongside best move
        best_move["convergence_recommendation"] = best_convergence_move
        
        return best_move

# ============================================================================
# MAIN FUNCTION
# ============================================================================

def optimize_for_equilibrium(
    cron_data: str,
    current_hyperfi_deposit: float = 200000,
    verbose: bool = True,
    current_position: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Main function to find equilibrium position
    
    Args:
        cron_data: String containing pool data from cron job
        current_hyperfi_deposit: Current deposit in HyperFi
        verbose: Whether to show detailed progress
    
    Returns:
        Dictionary with equilibrium position details
    """
    # Parse the cron data
    pools = parse_cron_data(cron_data)
    
    if not pools:
        return {"error": "Failed to parse cron data"}
    
    # Set up current position
    if current_position is None:
        current_position = {
            "HyperFi": current_hyperfi_deposit,
            "HyperLend": 0,
        }
    
    # Create equilibrium optimizer
    optimizer = EquilibriumOptimizer(
        pools=pools,
        current_position=current_position,
        min_gain_bps=10,  # Require meaningful improvement
        max_spread_bps=150,  # Max 1.5% spread to avoid arbitrage
        min_safe_util=0.805,  # Stay above kink
        max_safe_util=0.87,  # Avoid extreme rates
        gas_cost_usd=10,
        verbose=verbose
    )
    
    # Find optimal equilibrium position
    result = optimizer.find_optimal_equilibrium()
    
    return result

def format_equilibrium_result(result: Dict) -> str:
    """Format the equilibrium optimization result."""
    if "no_move_needed" in result:
        header = (
            "╔═══════════════════════════════════════════════════════════════════╗\n"
            "║                 ✅ EQUILIBRIUM STATUS                             ║\n"
            "╠═══════════════════════════════════════════════════════════════════╣\n"
            f"║ {result['reason']}\n"
            f"║ Current weighted APR: {result['current_weighted_apr']*100:.2f}%\n"
            "║\n"
            "║ Pool Status:"
        )
        lines: List[str] = [header]
        for name, status in result.get("pool_status", {}).items():
            lines.append(
                f"║   {name}: {status['utilization']*100:.1f}% util, {status['apr']*100:.2f}% APR"
            )
        lines.append("╚═══════════════════════════════════════════════════════════════════╝")
        return "\n".join(lines)

    if "error" in result:
        return f"\n❌ {result['error']}\n"

    # Build stability indicators
    stability_emoji = (
        "🟢" if result["stability_score"] > 0.7 else "🟡" if result["stability_score"] > 0.4 else "🔴"
    )
    arb_risk = result.get("equilibrium_analysis", {}).get("arbitrage_risk", "Unknown")

    return (
        "╔═══════════════════════════════════════════════════════════════════╗\n"
        "║              🎯 EQUILIBRIUM OPTIMIZATION RESULT                   ║\n"
        "╠═══════════════════════════════════════════════════════════════════╣\n"
        f"║ RECOMMENDED ACTION: Move ${result['amount']:,.2f}\n"
        f"║ FROM: {result['from']} \n"
        f"║ TO: {result['to']}\n"
        "╠═══════════════════════════════════════════════════════════════════╣\n"
        "║ UTILIZATION CHANGES:\n"
        f"║   {result['from']}: {result['current_util'][result['from']]*100:.2f}% → {result['new_util'][result['from']]*100:.2f}%\n"
        f"║   {result['to']}: {result['current_util'][result['to']]*100:.2f}% → {result['new_util'][result['to']]*100:.2f}%\n"
        "║   \n"
        f"║   Both remain in safe zone (80.5% - 87%)? {'✅ Yes' if result['is_stable'] else '❌ No'}\n"
        "╠═══════════════════════════════════════════════════════════════════╣\n"
        "║ APR CHANGES:\n"
        f"║   {result['from']}: {result['current_apr'][result['from']]*100:.2f}% → {result['new_apr'][result['from']]*100:.2f}%\n"
        f"║   {result['to']}: {result['current_apr'][result['to']]*100:.2f}% → {result['new_apr'][result['to']]*100:.2f}%\n"
        "║   \n"
        f"║   APR Spread: {result['apr_spread']*10000:.0f} bps (max 150 for stability)\n"
        "╠═══════════════════════════════════════════════════════════════════╣\n"
        "║ YIELD IMPROVEMENT:\n"
        f"║   Current: {result['current_weighted_apr']*100:.3f}%\n"
        f"║   After: {result['new_weighted_apr']*100:.3f}%\n"
        f"║   Gain: {result['gain_bps']:.1f} bps = ${result['annual_gain_usd']:,.2f}/year\n"
        "╠═══════════════════════════════════════════════════════════════════╣\n"
        f"║ STABILITY ANALYSIS {stability_emoji}\n"
        f"║   Stability Score: {result['stability_score']:.2f}/1.00\n"
        f"║   Arbitrage Risk: {arb_risk}\n"
        f"║   Est. Rebalance Frequency: {result.get('equilibrium_analysis', {}).get('estimated_rebalance_frequency', 'Unknown')}\n"
        "║   \n"
        "║   This position should remain optimal for days/weeks\n"
        "║   without triggering arbitrage bots\n"
        "╚═══════════════════════════════════════════════════════════════════╝\n"
    )

def print_hardcoded_text_outcomes(pools: Dict[str, CronPoolData], result: Dict) -> None:
    """Print a plain text, easy-to-scan outcome summary first."""
    print("\nOUTCOMES (plain text)")
    print("-" * 70)
    # Current pool stats
    if pools:
        for name, pool in pools.items():
            print(
                f"{name}: APR {pool.current_apr*100:.2f}%, Util {pool.utilization*100:.2f}%, TVL ${pool.tvl:,.0f}"
            )
    # Decision summary
    if "error" in result:
        print(f"Decision: Error - {result['error']}")
        return
    if result.get("no_move_needed"):
        print("Decision: Maintain current position (equilibrium).")
        print(f"Current weighted APR: {result.get('current_weighted_apr', 0)*100:.2f}%")
        # If we have a convergence suggestion, show it plainly
        conv = result.get("convergence_recommendation")
        if conv:
            print(
                f"Convergence suggestion: Move ${conv['amount']:,.0f} {conv['from']}→{conv['to']} | "
                f"Spread → {conv['apr_spread']*10000:.0f} bps | New APR: {conv['new_weighted_apr']*100:.2f}%"
            )
    else:
        print(
            f"Decision: Move ${result['amount']:,.0f} from {result['from']} to {result['to']}"
        )
        print(
            f"Post-move weighted APR: {result['new_weighted_apr']*100:.2f}% (gain {result['gain_bps']:.1f} bps)"
        )
        if result.get("convergence_recommendation"):
            conv = result["convergence_recommendation"]
            if conv:
                print(
                    f"Convergence-min spread: ${conv['amount']:,.0f} {conv['from']}→{conv['to']} | "
                    f"Spread {conv['apr_spread']*10000:.0f} bps"
                )
    # Stability rationale
    if not result.get("no_move_needed"):
        print(
            f"Stability: {'Stable' if result.get('is_stable') else 'Unstable'} | APR spread: {result.get('apr_spread', 0)*10000:.0f} bps"
        )
    else:
        # Provide a general rationale using pool spread
        if len(pools) >= 2:
            names = list(pools.keys())
            a, b = pools[names[0]], pools[names[1]]
            spread_bps = abs(a.current_apr - b.current_apr) * 10000
            print(f"Stability: Spread ≈ {spread_bps:.0f} bps vs max 150 bps → No stable move suggested.")
    print("-" * 70)

# EXAMPLE USAGE
# ============================================================================

def save_result_to_db(result: Dict):
    """
    Saves the optimization result to the database using OptimizationResultDAO.
    """
    try:
        dao = OptimizationResultDAO()
        
        # Only save if a move is recommended and profitable
        if "amount" in result and result.get("profitable"):
            from_protocol = result['from']
            to_protocol = result['to']
            
            result_data = {
                "from_protocol": from_protocol,
                "to_protocol": to_protocol,
                "amount_usd": result['amount'],
                "current_apr_from": result['current_apr'][from_protocol],
                "current_apr_to": result['current_apr'][to_protocol],
                "projected_apr": result['new_weighted_apr'],
                "utilization_from": result['new_util'][from_protocol],
                "utilization_to": result['new_util'][to_protocol],
                "extra_yield_bps": result['gain_bps'],
                "notes": f"Equilibrium move. Stability: {result['stability_score']:.2f}, Spread: {result['apr_spread']*10000:.0f}bps"
            }
            dao.create_result(result_data)
            print("\n✅ Result successfully saved to the database.")

        elif result.get("no_move_needed"):
            print(f"\nℹ️ No move needed, not saving to DB. Reason: {result.get('reason')}")

        elif result.get("error"):
            print(f"\n❌ Error occurred, not saving to DB: {result.get('error')}")
            
        else:
            print(f"\nℹ️ Move not profitable or not recommended, not saving to DB.")

    except Exception as e:
        print(f"\n🚨 Error saving result to the database: {e}")


if __name__ == "__main__":
    print("=" * 70)
    print("EQUILIBRIUM-AWARE POOL OPTIMIZATION")
    print("Finding stable positions that won't trigger arbitrage")
    print("=" * 70)

    # --- SCENARIO 1: Existing Case ---
    print("\n" + "=" * 70)
    print("SCENARIO 1: $200,000 Position (in HyperLend)")
    print("=" * 70)
    
    cron_data_1 = """
    hyplend usde - 12.09% apr. USDe supplied/tvl- $2,958,413, utilisation rate= 82.49%
    Hypurfi USDe- 16.87% apr. USDe supplied/tvl- $2,410,000, utilisation rate= 83.62%
    """
    
    print("\n📊 Current Market Data (Scenario 1):")
    print("-" * 70)
    pools_1 = parse_cron_data(cron_data_1)
    for name, pool in pools_1.items():
        print(f"{name:10} | APR: {pool.current_apr*100:6.2f}% | TVL: ${pool.tvl:13,.2f} | Util: {pool.utilization*100:6.2f}%")
    
    result_1 = optimize_for_equilibrium(
        cron_data_1,
        current_position={"HyperFi": 0, "HyperLend": 200000},
    )
    
    print_hardcoded_text_outcomes(pools_1, result_1)
    print(format_equilibrium_result(result_1))
    save_result_to_db(result_1)

    # --- SCENARIO 2: New High Spread Case (>50 bps) ---
    print("\n" + "=" * 70)
    print("SCENARIO 2: HIGH SPREAD (>50 bps) - $150,000 Position")
    print("=" * 70)

    cron_data_2 = """
    hyplend usde - 10.00% apr. USDe supplied/tvl- $3,000,000, utilisation rate= 81.00%
    Hypurfi USDe- 15.50% apr. USDe supplied/tvl- $2,000,000, utilisation rate= 84.00%
    """
    
    print("\n📊 Current Market Data (Scenario 2):")
    print("-" * 70)
    pools_2 = parse_cron_data(cron_data_2)
    for name, pool in pools_2.items():
        print(f"{name:10} | APR: {pool.current_apr*100:6.2f}% | TVL: ${pool.tvl:13,.2f} | Util: {pool.utilization*100:6.2f}%")

    result_2 = optimize_for_equilibrium(
        cron_data_2,
        current_position={"HyperFi": 50000, "HyperLend": 100000},
    )

    print_hardcoded_text_outcomes(pools_2, result_2)
    print(format_equilibrium_result(result_2))
    save_result_to_db(result_2)