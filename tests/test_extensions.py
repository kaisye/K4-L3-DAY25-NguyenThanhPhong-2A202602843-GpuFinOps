from missions import m2_inference_levers, m3_purchasing, m4_allocation


def test_cache_write_charge_and_allocation_reconcile():
    r = m2_inference_levers.run(False)
    assert r['cache_write_daily'] > 0
    assert abs(r['stages']['with_cache_writes'] - r['stages']['batch']
               - r['cache_write_daily']) < 1e-9
    allocated = sum(m4_allocation.run(False)['by_team'].values())
    assert abs(allocated - r['optimized_daily']) < 0.03


def test_ten_percent_cap_preserves_traffic_already_below_limit():
    b = m2_inference_levers.run(False)['reasoning_budget']
    assert b['cap_pct'] == 10
    assert b['traffic_pct'] < 10
    assert b['cap_cost_savings_usd'] == b['cap_energy_savings_wh'] == 0
    assert b['before_usd'] == b['after_usd']
    assert b['before_wh'] == b['after_wh']
    assert sum(g['tokens'] for g in b['groups'].values()) == 7533027


def test_carbon_job_totals_match_region_totals():
    c = m3_purchasing.run(False)['carbon_aware']
    before = sum(j['before_g'] for j in c['jobs']) / 1000
    after = sum(j['after_g'] for j in c['jobs']) / 1000
    assert abs(before - next(r['carbon_kg'] for r in c['regions']
                             if r['region'] == 'us-east-1')) < 0.01
    assert abs(before - after - c['carbon_savings_kg']) < 0.01
