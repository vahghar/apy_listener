import os
import sys
from pathlib import Path

# Add the project root to Python path so we can import data modules
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Configure Django BEFORE importing any Django models
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'defai_backend.settings')

import django
django.setup()

import pytest
from cron_job import parse_cron_data, CronPoolData

def test_parse_cron_data_single_protocol():
    """
    Tests that a cron string with only one protocol is parsed correctly.
    """
    cron_string = "hyplend usde - 13.79% apr. USDe supplied/tvl- $2,950,186.42, utilisation rate= 82.91%"
    pools = parse_cron_data(cron_string)

    assert "HyperLend" in pools
    assert "HyperFi" not in pools

    hyperlend_pool = pools["HyperLend"]
    assert isinstance(hyperlend_pool, CronPoolData)
    assert hyperlend_pool.protocol == "HyperLend"
    assert pytest.approx(hyperlend_pool.current_apr, abs=1e-4) == 0.1379
    assert pytest.approx(hyperlend_pool.tvl) == 2950186.42
    assert pytest.approx(hyperlend_pool.utilization, abs=1e-4) == 0.8291

def test_parse_cron_data_both_protocols():
    """
    Tests that a cron string with both protocols is parsed correctly.
    """
    cron_string = "hyplend usde - 13.79% apr. USDe supplied/tvl- $2,950,186.42, utilisation rate= 82.91% || hypurfi usde - 12.00% apr. USDe supplied/tvl- $1,500,000.00, utilisation rate= 75.00%"
    pools = parse_cron_data(cron_string)

    assert "HyperLend" in pools
    assert "HyperFi" in pools

    # Validate HyperFi data
    hyperfi_pool = pools["HyperFi"]
    assert isinstance(hyperfi_pool, CronPoolData)
    assert hyperfi_pool.protocol == "HyperFi"
    assert pytest.approx(hyperfi_pool.current_apr, abs=1e-4) == 0.1200
    assert pytest.approx(hyperfi_pool.tvl) == 1500000.00
    assert pytest.approx(hyperfi_pool.utilization, abs=1e-4) == 0.7500

def test_parse_cron_data_malformed_string():
    """
    Tests that the parser handles missing data gracefully.
    """
    cron_string = "invalid string without any data"
    pools = parse_cron_data(cron_string)
    assert pools == {}

def test_cron_pool_data_properties():
    """
    Test the calculated properties of CronPoolData
    """
    pool = CronPoolData(
        protocol="TestProtocol",
        current_apr=0.15,  # 15%
        tvl=1000000,       # $1M
        utilization=0.8    # 80%
    )
    
    assert pool.total_borrow == 800000  # 80% of $1M
    assert pool.available_liquidity == 200000  # $1M - $800K

def test_parse_zero_values():
    """Test parsing strings with zero values"""
    cron_string = "hyplend usde - 0.00% apr. USDe supplied/tvl- $0, utilisation rate= 0%"
    pools = parse_cron_data(cron_string)
    
    assert pools["HyperLend"].tvl == 0
    assert pools["HyperLend"].utilization == 0
    assert pools["HyperLend"].current_apr == 0

def test_parse_100_percent_utilization():
    """Test parsing 100% utilization case"""
    cron_string = "hypurfi usde - 5.00% apr. USDe supplied/tvl- $1000, utilisation rate= 100%"
    pools = parse_cron_data(cron_string)
    
    assert pools["HyperFi"].utilization == 1.0
    assert pools["HyperFi"].total_borrow == 1000
    assert pools["HyperFi"].available_liquidity == 0

def test_parse_varied_spacing():
    """Test parsing with irregular spacing"""
    cron_string = "hyplendusde-13.79%apr.USDe supplied/tvl-$2,950,186.42,utilisation rate=82.91%"
    pools = parse_cron_data(cron_string)
    
    assert pools["HyperLend"].current_apr == pytest.approx(0.1379)
    assert pools["HyperLend"].tvl == pytest.approx(2950186.42)

def test_pool_properties_edge_cases():
    """Test calculated properties with edge cases"""
    # Test negative values (should probably be handled)
    pool = CronPoolData("Test", -0.1, -1000, -0.5)
    assert pool.total_borrow == -500  # Should this be allowed?
    
    # Test very large numbers
    large_pool = CronPoolData("Test", 0.1, 1e30, 0.9)
    assert large_pool.total_borrow == 9e29

if __name__ == "__main__":
    # Run tests directly with python
    print("Running tests...")
    
    test_parse_cron_data_single_protocol()
    print("✅ test_parse_cron_data_single_protocol passed")
    
    test_parse_cron_data_both_protocols()
    print("✅ test_parse_cron_data_both_protocols passed")
    
    test_parse_cron_data_malformed_string()
    print("✅ test_parse_cron_data_malformed_string passed")
    
    test_cron_pool_data_properties()
    print("✅ test_cron_pool_data_properties passed")
    
    test_parse_zero_values()
    print("✅ test_parse_zero_values passed")
    
    test_parse_100_percent_utilization()
    print("✅ test_parse_100_percent_utilization passed")
    
    test_parse_varied_spacing()
    print("✅ test_parse_varied_spacing passed")
    
    test_pool_properties_edge_cases()
    print("✅ test_pool_properties_edge_cases passed")
    
    print("\n🎉 All tests passed!")