"""M3 — Purchasing Strategy: break-even, tier choice, spot-checkpoint sim (deck §4).

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops import pricing, sustainability

DAYS = 30


def run(verbose: bool = True) -> dict:
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    on_demand_monthly = optimized_monthly = legacy_optimized_monthly = 0.0
    recs = []
    interruptible_wh = 0.0
    carbon_jobs = []
    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        interruptible = bool(int(num(j["interruptible"])))
        job_days = int(num(j["days"]))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        on_demand_cost = gpu_hours * od

        tier = pricing.recommend_tier(hpd, interruptible, gpu_type=gtype, job_days=job_days)
        reserved_term = None
        if tier == "spot":
            sim = pricing.spot_checkpoint_cost(
                gpu_hours, num(c["spot_hr"]), od,
                interrupt_rate=pricing.SPOT_INTERRUPTION_RATE.get(gtype, 0.05),
            )
            opt_cost = sim["spot_cost"]
        elif tier == "reserved":
            reserved_term = pricing.recommend_reserved_term(
                job_days, num(c["reserved_1yr_hr"]), num(c["reserved_3yr_hr"])
            )
            rate_key = "reserved_3yr_hr" if reserved_term == "reserved_3yr" else "reserved_1yr_hr"
            opt_cost = gpu_hours * num(c[rate_key])
        else:
            opt_cost = on_demand_cost

        # The original lab policy always chose spot for interruptible work and
        # priced every reserved recommendation at the 3-year rate.
        legacy_tier = "spot" if interruptible and hpd < 24 else (
            "reserved" if hpd / 24 >= pricing.break_even_utilization(0.45) else "on_demand"
        )
        if legacy_tier == "spot":
            legacy_cost = pricing.spot_checkpoint_cost(
                gpu_hours, num(c["spot_hr"]), od
            )["spot_cost"]
        elif legacy_tier == "reserved":
            legacy_cost = gpu_hours * num(c["reserved_3yr_hr"])
        else:
            legacy_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        optimized_monthly += opt_cost
        legacy_optimized_monthly += legacy_cost
        recs.append({"job_id": j["job_id"], "gpu_type": gtype, "tier": tier,
                     "reserved_term": reserved_term,
                     "interruption_rate": pricing.SPOT_INTERRUPTION_RATE.get(gtype, 0.05),
                     "legacy_tier": legacy_tier, "legacy_cost": round(legacy_cost, 2),
                     "job_days": job_days,
                     "on_demand": round(on_demand_cost), "optimized": round(opt_cost)})
        if interruptible:
            job_wh = num(c["watts"]) * hpd * job_days * ngpu
            interruptible_wh += job_wh
            carbon_jobs.append({"job_id": j["job_id"], "days": job_days,
                                "energy_wh": job_wh,
                                "before_g": sustainability.carbon_g(job_wh, "us-east-1"),
                                "after_g": sustainability.carbon_g(job_wh, "europe-north1")})

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0
    legacy_savings_pct = ((on_demand_monthly - legacy_optimized_monthly) /
                          on_demand_monthly * 100) if on_demand_monthly else 0.0

    # Extension 5: carbon-aware placement for checkpointable jobs. Electricity
    # cost is deliberately separated from the provider GPU price: it is a small
    # bill component but a large carbon lever.
    region_comparison = []
    for region, intensity in sustainability.REGION_CARBON.items():
        carbon = sustainability.carbon_g(interruptible_wh, region)
        electricity = sustainability.energy_cost_usd(interruptible_wh, region)
        region_comparison.append({
            "region": region, "usd_per_kwh": sustainability.REGION_PRICE_KWH[region],
            "gco2_per_kwh": intensity, "electricity_cost_usd": round(electricity, 2),
            "carbon_kg": round(carbon / 1000, 2),
        })
    cheapest_region = min(region_comparison, key=lambda r: r["electricity_cost_usd"])["region"]
    cleanest_region = min(region_comparison, key=lambda r: r["carbon_kg"])["region"]
    min_cost = min(r["electricity_cost_usd"] for r in region_comparison)
    min_carbon = min(r["carbon_kg"] for r in region_comparison)
    balanced_region = min(
        region_comparison,
        key=lambda r: r["electricity_cost_usd"] / min_cost + r["carbon_kg"] / min_carbon,
    )["region"]
    current = next(r for r in region_comparison if r["region"] == "us-east-1")
    cleanest = next(r for r in region_comparison if r["region"] == cleanest_region)
    carbon_aware = {
        "workload_energy_kwh": round(interruptible_wh / 1000, 1),
        "regions": region_comparison,
        "jobs": carbon_jobs, "period": "actual workload days; rated power estimate",
        "cheapest_region": cheapest_region, "cleanest_region": cleanest_region,
        "balanced_region": balanced_region,
        "carbon_savings_kg": round(current["carbon_kg"] - cleanest["carbon_kg"], 2),
        "carbon_reduction_pct": round((1 - cleanest["carbon_kg"] / current["carbon_kg"]) * 100, 1),
    }

    if verbose:
        print("== M3 Purchasing Strategy ==")
        print(f"break-even utilization @ 45% reserved discount = {pricing.break_even_utilization(0.45):.0%}")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'term':15}{'on-demand':>12}{'optimized':>12}")
        for r in recs:
            print(f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:11}"
                  f"{(r['reserved_term'] or '-'):15}${r['on_demand']:>11,}${r['optimized']:>11,}")
        print(f"\nmonthly: on-demand ${on_demand_monthly:,.0f} -> optimized ${optimized_monthly:,.0f}  ({savings_pct:.1f}% saved)")
        print(f"policy comparison: legacy {legacy_savings_pct:.1f}% vs risk-aware {savings_pct:.1f}% savings")
        print("\nCarbon-aware scheduling for interruptible jobs:")
        for r in region_comparison:
            print(f"  {r['region']:16} ${r['electricity_cost_usd']:>8,.2f}  {r['carbon_kg']:>8,.2f} kgCO2e")
        print(f"  cheapest={cheapest_region}, cleanest={cleanest_region}, balanced={balanced_region}")
        print(f"  us-east-1 -> {cleanest_region}: {carbon_aware['carbon_savings_kg']:,.2f} kgCO2e "
              f"saved ({carbon_aware['carbon_reduction_pct']}%); validate latency/data residency first")

    return {"recommendations": recs, "on_demand_monthly": round(on_demand_monthly),
            "optimized_monthly": round(optimized_monthly), "savings_pct": round(savings_pct, 1),
            "legacy_savings_pct": round(legacy_savings_pct, 1), "carbon_aware": carbon_aware}


if __name__ == "__main__":
    run()
