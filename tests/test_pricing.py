import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from finops import pricing


def test_discount_stack_is_multiplicative():
    assert abs(pricing.discount_stack(batch=True, cache_hit_frac=1.0) - 0.05) < 1e-9   # ~95% off
    assert pricing.discount_stack() == 1.0
    assert abs(pricing.discount_stack(batch=True) - 0.5) < 1e-9


def test_break_even():
    assert abs(pricing.break_even_utilization(0.45) - 0.55) < 1e-9
    assert pricing.break_even_utilization(0.0) == 1.0


def test_recommend_tier():
    assert pricing.recommend_tier(2, True) == "spot"
    assert pricing.recommend_tier(24, False) == "reserved"
    assert pricing.recommend_tier(4, False) == "on_demand"


def test_request_cost_and_cache():
    full = pricing.request_cost(1000, 1000, 3.0, 15.0)
    cached = pricing.request_cost(1000, 1000, 3.0, 15.0, cached_in=1000)
    assert cached < full                       # caching reduces cost
    batched = pricing.request_cost(1000, 1000, 3.0, 15.0, batch=True)
    assert abs(batched - full * 0.5) < 1e-9    # batch = -50%


def test_cache_break_even_and_gate():
    assert abs(pricing.cache_break_even_reads(1.25, 0.10) - (1.25 / 0.9)) < 1e-9
    assert pricing.cache_is_worth_it(2.0, 1.25) is True
    assert pricing.cache_is_worth_it(1.0, 1.25) is False


def test_risk_and_duration_aware_tier_policy():
    assert pricing.recommend_tier(8, True, gpu_type="A10G", job_days=22) == "spot"
    assert pricing.recommend_tier(8, True, gpu_type="A10G", job_days=22,
                                  interruption_rate=0.25) == "on_demand"
    assert pricing.recommend_tier(24, False, gpu_type="A100", job_days=30) == "reserved"
    assert pricing.recommend_tier(24, False, gpu_type="A100", job_days=7) == "on_demand"
    assert pricing.recommend_reserved_term(365, 1.4, 1.0) == "reserved_1yr"
    assert pricing.recommend_reserved_term(1095, 1.4, 1.0) == "reserved_3yr"


def test_spot_checkpoint_saves():
    res = pricing.spot_checkpoint_cost(100, 1.5, 2.5)
    assert res["spot_cost"] < res["on_demand_cost"]
    assert res["savings_pct"] > 0
