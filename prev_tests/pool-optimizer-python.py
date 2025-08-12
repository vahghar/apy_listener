import numpy as np
from typing import Dict, Tuple, Optional, Callable
from dataclasses import dataclass
from enum import Enum

class ModelType(Enum):
    LINEAR = "linear"
    KINKED = "kinked"
    POLYNOMIAL = "polynomial"

@dataclass
class PoolState:
    """Represents the state of a lending pool"""
    supply: float
    borrow: float
    model_type: ModelType
    params: Dict[str, float]
    
    @property
    def utilization(self) -> float:
        return self.borrow / self.supply if self.supply > 0 else 0
    
    def apy(self, utilization: Optional[float] = None) -> float:
        """Calculate APY based on utilization"""
        u = utilization if utilization is not None else self.utilization
        
        if self.model_type == ModelType.LINEAR:
            return self.params['base_rate'] + self.params['slope'] * u
            
        elif self.model_type == ModelType.KINKED:
            base = self.params['base_rate']
            slope1 = self.params['slope1']
            slope2 = self.params['slope2']
            kink = self.params['kink']
            
            if u <= kink:
                return base + slope1 * u
            else:
                return base + slope1 * kink + slope2 * (u - kink)
                
        elif self.model_type == ModelType.POLYNOMIAL:
            a = self.params['a']
            b = self.params['b']
            c = self.params['c']
            return a + b * u + c * u * u
        
        raise ValueError(f"Unknown model type: {self.model_type}")

@dataclass
class OptimizationResult:
    """Results of the pool optimization"""
    optimal_amount: float
    apy_a_before: float
    apy_b_before: float
    apy_a_after: float
    apy_b_after: float
    effective_apy_before: float
    effective_apy_after: float
    gain_bps: float
    method_used: str
    iterations: Optional[int] = None

class PoolOptimizer:
    def __init__(self, 
                 pool_a: PoolState, 
                 pool_b: PoolState,
                 user_balance_a: float,
                 user_balance_b: float = 0,
                 min_gain_bps: float = 5,
                 eps: float = 1e-6):
        """
        Initialize the pool optimizer
        
        Args:
            pool_a: State of pool A (withdrawing from)
            pool_b: State of pool B (depositing to)
            user_balance_a: User's balance in pool A
            user_balance_b: User's balance in pool B (default 0)
            min_gain_bps: Minimum gain required to justify move (in basis points)
            eps: Tolerance for convergence
        """
        self.pool_a = pool_a
        self.pool_b = pool_b
        self.user_balance_a = user_balance_a
        self.user_balance_b = user_balance_b
        self.min_gain_bps = min_gain_bps
        self.eps = eps
        self.max_movable = min(user_balance_a, pool_a.supply * 0.99)  # Can't drain pool
        
    def apy_a_after_withdraw(self, x: float) -> float:
        """APY of pool A after withdrawing x"""
        new_util = self.pool_a.borrow / (self.pool_a.supply - x)
        return self.pool_a.apy(new_util)
    
    def apy_b_after_deposit(self, x: float) -> float:
        """APY of pool B after depositing x"""
        new_util = self.pool_b.borrow / (self.pool_b.supply + x)
        return self.pool_b.apy(new_util)
    
    def delta(self, x: float) -> float:
        """Difference in APY (B - A) after moving x"""
        return self.apy_b_after_deposit(x) - self.apy_a_after_withdraw(x)
    
    def effective_apy(self, amount_in_a: float, amount_in_b: float) -> float:
        """Calculate weighted average APY across both pools"""
        total = amount_in_a + amount_in_b
        if total == 0:
            return 0
        
        apy_a = self.apy_a_after_withdraw(self.user_balance_a - amount_in_a)
        apy_b = self.apy_b_after_deposit(amount_in_b - self.user_balance_b)
        
        return (amount_in_a * apy_a + amount_in_b * apy_b) / total
    
    def solve_analytical_linear(self) -> Optional[float]:
        """
        Analytical solution for linear models
        Setting APY_A(x) = APY_B(x) and solving for x
        """
        if (self.pool_a.model_type != ModelType.LINEAR or 
            self.pool_b.model_type != ModelType.LINEAR):
            return None
        
        # For linear: APY = base + slope * utilization
        # APY_A = base_a + slope_a * (borrow_a / (supply_a - x))
        # APY_B = base_b + slope_b * (borrow_b / (supply_b + x))
        
        base_a = self.pool_a.params['base_rate']
        slope_a = self.pool_a.params['slope']
        base_b = self.pool_b.params['base_rate']
        slope_b = self.pool_b.params['slope']
        
        # Solving for equilibrium point
        numerator = (slope_b * self.pool_b.borrow * self.pool_a.supply - 
                    slope_a * self.pool_a.borrow * self.pool_b.supply + 
                    (base_b - base_a) * self.pool_a.supply * self.pool_b.supply)
        denominator = (slope_a * self.pool_a.borrow + slope_b * self.pool_b.borrow + 
                      (base_b - base_a) * (self.pool_a.supply + self.pool_b.supply))
        
        if abs(denominator) < self.eps:
            return None
            
        x = numerator / denominator
        return max(0, min(x, self.max_movable))
    
    def solve_analytical_polynomial(self) -> Optional[float]:
        """
        Analytical solution for polynomial models
        Results in a quartic equation - simplified version shown
        """
        if (self.pool_a.model_type != ModelType.POLYNOMIAL or 
            self.pool_b.model_type != ModelType.POLYNOMIAL):
            return None
        
        # This is complex for general case, showing simplified version
        # where both pools have same polynomial coefficients
        if self.pool_a.params != self.pool_b.params:
            return None  # Fall back to numerical for different params
        
        # Simplified case: equal coefficients
        c = self.pool_a.params['c']
        b = self.pool_a.params['b']
        
        # This reduces to finding x where utilizations are equal
        # borrow_a / (supply_a - x) = borrow_b / (supply_b + x)
        x = (self.pool_b.borrow * self.pool_a.supply - 
             self.pool_a.borrow * self.pool_b.supply) / (
             self.pool_a.borrow + self.pool_b.borrow)
        
        return max(0, min(x, self.max_movable))
    
    def solve_binary_search(self) -> Tuple[float, int]:
        """
        Binary search solution for any model type
        Returns (optimal_amount, iterations)
        """
        iterations = 0
        low, high = 0.0, self.max_movable
        
        # Quick boundary checks
        if self.delta(0) <= self.min_gain_bps / 10000:
            return 0.0, 0
        if self.delta(high) > self.min_gain_bps / 10000:
            return high, 1
        
        # Binary search for crossing point
        while high - low > self.eps and iterations < 50:
            iterations += 1
            mid = (low + high) / 2
            
            if self.delta(mid) > 0:
                low = mid
            else:
                high = mid
        
        # Check if gain is sufficient
        optimal = low
        if self.delta(optimal) < self.min_gain_bps / 10000:
            optimal = 0.0
            
        return optimal, iterations
    
    def solve_newton_raphson(self, x0: Optional[float] = None) -> Tuple[float, int]:
        """
        Newton-Raphson method for faster convergence on smooth functions
        Returns (optimal_amount, iterations)
        """
        if x0 is None:
            x0 = self.max_movable / 2
        
        x = x0
        iterations = 0
        h = 0.0001  # Small step for numerical derivative
        
        while iterations < 20:
            iterations += 1
            
            # Numerical derivative
            f = self.delta(x)
            f_prime = (self.delta(x + h) - f) / h
            
            if abs(f_prime) < self.eps:
                break
                
            x_new = x - f / f_prime
            x_new = max(0, min(x_new, self.max_movable))
            
            if abs(x_new - x) < self.eps:
                break
                
            x = x_new
        
        # Check if gain is sufficient
        if self.delta(x) < self.min_gain_bps / 10000:
            x = 0.0
            
        return x, iterations
    
    def optimize(self) -> OptimizationResult:
        """
        Main optimization function - tries analytical first, then numerical
        """
        # Record initial state
        apy_a_before = self.pool_a.apy()
        apy_b_before = self.pool_b.apy()
        effective_before = self.effective_apy(self.user_balance_a, self.user_balance_b)
        
        # Try analytical solutions first
        optimal_amount = None
        method = "none"
        iterations = None
        
        if self.pool_a.model_type == ModelType.LINEAR and self.pool_b.model_type == ModelType.LINEAR:
            optimal_amount = self.solve_analytical_linear()
            method = "analytical_linear"
            
        elif self.pool_a.model_type == ModelType.POLYNOMIAL and self.pool_b.model_type == ModelType.POLYNOMIAL:
            optimal_amount = self.solve_analytical_polynomial()
            if optimal_amount is not None:
                method = "analytical_polynomial"
        
        # Fall back to numerical methods
        if optimal_amount is None:
            # Try Newton-Raphson for smooth functions
            if self.pool_a.model_type != ModelType.KINKED and self.pool_b.model_type != ModelType.KINKED:
                optimal_amount, iterations = self.solve_newton_raphson()
                method = "newton_raphson"
            else:
                # Use binary search for kinked models
                optimal_amount, iterations = self.solve_binary_search()
                method = "binary_search"
        
        # Calculate final state
        apy_a_after = self.apy_a_after_withdraw(optimal_amount)
        apy_b_after = self.apy_b_after_deposit(optimal_amount)
        
        new_balance_a = self.user_balance_a - optimal_amount
        new_balance_b = self.user_balance_b + optimal_amount
        effective_after = self.effective_apy(new_balance_a, new_balance_b)
        
        gain_bps = (effective_after - effective_before) * 10000
        
        return OptimizationResult(
            optimal_amount=optimal_amount,
            apy_a_before=apy_a_before,
            apy_b_before=apy_b_before,
            apy_a_after=apy_a_after,
            apy_b_after=apy_b_after,
            effective_apy_before=effective_before,
            effective_apy_after=effective_after,
            gain_bps=gain_bps,
            method_used=method,
            iterations=iterations
        )

def format_result(result: OptimizationResult) -> str:
    """Pretty print the optimization result"""
    return f"""
╔═══════════════════════════════════════════════════════╗
║            POOL REBALANCING OPTIMIZATION              ║
╠═══════════════════════════════════════════════════════╣
║ Optimal Move Amount: ${result.optimal_amount:,.2f}
║ Method Used: {result.method_used}
{f'║ Iterations: {result.iterations}' if result.iterations else ''}
╠═══════════════════════════════════════════════════════╣
║ APY Changes:
║   Pool A: {result.apy_a_before*100:.3f}% → {result.apy_a_after*100:.3f}% 
║   Pool B: {result.apy_b_before*100:.3f}% → {result.apy_b_after*100:.3f}%
╠═══════════════════════════════════════════════════════╣
║ Effective APY (Weighted):
║   Before: {result.effective_apy_before*100:.3f}%
║   After:  {result.effective_apy_after*100:.3f}%
║   Gain:   {result.gain_bps:.2f} bps
╚═══════════════════════════════════════════════════════╝
"""

# Example usage
if __name__ == "__main__":
    # Example 1: Linear model pools
    print("=" * 60)
    print("EXAMPLE 1: Linear APY Models")
    print("=" * 60)
    
    pool_a = PoolState(
        supply=5_000_000,
        borrow=3_000_000,
        model_type=ModelType.LINEAR,
        params={'base_rate': 0.02, 'slope': 0.15}
    )
    
    pool_b = PoolState(
        supply=3_000_000,
        borrow=1_000_000,
        model_type=ModelType.LINEAR,
        params={'base_rate': 0.02, 'slope': 0.15}
    )
    
    optimizer = PoolOptimizer(
        pool_a=pool_a,
        pool_b=pool_b,
        user_balance_a=500_000,
        user_balance_b=0,
        min_gain_bps=5
    )
    
    result = optimizer.optimize()
    print(format_result(result))
    
    # Example 2: Kinked model pools (Compound-style)
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Kinked APY Models (Compound-style)")
    print("=" * 60)
    
    pool_a_kinked = PoolState(
        supply=10_000_000,
        borrow=7_500_000,
        model_type=ModelType.KINKED,
        params={
            'base_rate': 0.02,
            'slope1': 0.07,
            'slope2': 0.5,
            'kink': 0.8
        }
    )
    
    pool_b_kinked = PoolState(
        supply=8_000_000,
        borrow=2_000_000,
        model_type=ModelType.KINKED,
        params={
            'base_rate': 0.02,
            'slope1': 0.07,
            'slope2': 0.5,
            'kink': 0.8
        }
    )
    
    optimizer_kinked = PoolOptimizer(
        pool_a=pool_a_kinked,
        pool_b=pool_b_kinked,
        user_balance_a=1_000_000,
        user_balance_b=0,
        min_gain_bps=10
    )
    
    result_kinked = optimizer_kinked.optimize()
    print(format_result(result_kinked))
    
    # Example 3: Mixed model types
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Mixed Model Types (Linear + Polynomial)")
    print("=" * 60)
    
    pool_a_poly = PoolState(
        supply=4_000_000,
        borrow=2_800_000,
        model_type=ModelType.POLYNOMIAL,
        params={'a': 0.02, 'b': 0.05, 'c': 0.2}
    )
    
    pool_b_linear = PoolState(
        supply=6_000_000,
        borrow=1_500_000,
        model_type=ModelType.LINEAR,
        params={'base_rate': 0.03, 'slope': 0.12}
    )
    
    optimizer_mixed = PoolOptimizer(
        pool_a=pool_a_poly,
        pool_b=pool_b_linear,
        user_balance_a=750_000,
        user_balance_b=250_000,  # Already has some in pool B
        min_gain_bps=3
    )
    
    result_mixed = optimizer_mixed.optimize()
    print(format_result(result_mixed))
    
    # Performance comparison
    print("\n" + "=" * 60)
    print("PERFORMANCE COMPARISON")
    print("=" * 60)
    
    import time
    
    # Test with different pool sizes
    test_cases = [
        ("Small pools", 1_000_000, 500_000),
        ("Medium pools", 10_000_000, 5_000_000),
        ("Large pools", 100_000_000, 50_000_000),
    ]
    
    for name, supply, borrow in test_cases:
        pool_test_a = PoolState(
            supply=supply,
            borrow=borrow,
            model_type=ModelType.LINEAR,
            params={'base_rate': 0.02, 'slope': 0.15}
        )
        
        pool_test_b = PoolState(
            supply=supply * 0.8,
            borrow=borrow * 0.3,
            model_type=ModelType.LINEAR,
            params={'base_rate': 0.02, 'slope': 0.15}
        )
        
        optimizer_test = PoolOptimizer(
            pool_a=pool_test_a,
            pool_b=pool_test_b,
            user_balance_a=supply * 0.1,
            user_balance_b=0
        )
        
        start = time.perf_counter()
        result_test = optimizer_test.optimize()
        elapsed = (time.perf_counter() - start) * 1000
        
        print(f"{name:15} | Method: {result_test.method_used:20} | Time: {elapsed:.3f}ms")