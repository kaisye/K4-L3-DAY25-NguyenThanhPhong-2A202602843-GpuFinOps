"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing, sustainability

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")

    # Extension 3: assume cache reuse from shared static prompts. Each
    # (model-tier, project) group represents one reusable prefix in this
    # synthetic dataset. Cache writes cost 1.25x a normal input-token read.
    cache_groups = {}
    for r in rows:
        if int(num(r["cached_input_tokens"])) <= 0:
            continue
        key = (r["route_tier"], r["project"] or r["team"])
        cache_groups[key] = cache_groups.get(key, 0) + 1
    cache_economics = {}
    for tier in MODEL_PRICES:
        reads = [count for (group_tier, _), count in cache_groups.items() if group_tier == tier]
        avg_reads = sum(reads) / len(reads) if reads else 0.0
        write_multiplier = 1.25
        break_even = pricing.cache_break_even_reads(write_multiplier)
        cache_economics[tier] = {
            "avg_cache_reads": round(avg_reads, 1),
            "break_even_reads": round(break_even, 2),
            "worth_it": pricing.cache_is_worth_it(avg_reads, write_multiplier),
        }

    base_cost = opt_cost = cascade_cost = cache_cost = write_cost = 0.0
    total_tokens = 0
    reasoning_rows = []
    normal_cost = normal_wh = reasoning_cost = reasoning_wh = 0.0
    group_stats = {name: {"requests": 0, "tokens": 0, "cost_usd": 0.0, "energy_wh": 0.0}
                   for name in ("reasoning", "normal")}
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        applied_cache = cached if cache_economics[r["route_tier"]]["worth_it"] else 0
        cascade_cost += pricing.request_cost(inp, out, pin, pout)
        cache_cost += pricing.request_cost(inp, out, pin, pout, cached_in=applied_cache)
        # No prefix IDs or cache-write events exist in CSV. Assume one prefix
        # per tier/project, amortize 1.25x write charge over its estimated reads.
        key = (r["route_tier"], r["project"] or r["team"])
        row_write = applied_cache / 1e6 * pin * 1.25 / cache_groups.get(key, 1)
        write_cost += row_write
        row_cost = pricing.request_cost(inp, out, pin, pout,
                                        cached_in=applied_cache, batch=is_batch) + row_write
        opt_cost += row_cost

        # Extension 4: expose the cost and energy tax of deliberate reasoning.
        is_reasoning = bool(int(num(r["is_reasoning"])))
        row_wh = sustainability.wh_per_query(inp + out, is_reasoning=is_reasoning)
        stats = group_stats["reasoning" if is_reasoning else "normal"]
        stats["requests"] += 1
        stats["tokens"] += inp + out
        stats["cost_usd"] += row_cost
        stats["energy_wh"] += row_wh
        if is_reasoning:
            reasoning_cost += row_cost
            reasoning_wh += row_wh
            normal_out = max(1, round(out / 6))  # generator's explicit reasoning-token multiplier
            capped_cost = pricing.request_cost(inp, normal_out, pin, pout,
                                               cached_in=applied_cache, batch=is_batch)
            capped_wh = sustainability.wh_per_query(inp + normal_out, is_reasoning=False)
            reasoning_rows.append({
                "cost_saving": row_cost - capped_cost,
                "wh_saving": row_wh - capped_wh,
            })
        else:
            normal_cost += row_cost
            normal_wh += row_wh

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0

    # Test the requested 10% cap; current traffic is already below this limit.
    # tasks (complexity score >=0.8 or confidence <0.6 in production).
    cap_fraction = 0.10
    allowed_reasoning = int(len(rows) * cap_fraction)
    excess = max(0, len(reasoning_rows) - allowed_reasoning)
    displaced = sorted(reasoning_rows, key=lambda x: x["cost_saving"])[:excess]
    reasoning_budget = {
        "requests": len(reasoning_rows),
        "traffic_pct": round(len(reasoning_rows) / len(rows) * 100, 1) if rows else 0.0,
        "cost_usd": round(reasoning_cost, 2),
        "cost_share_pct": round(reasoning_cost / opt_cost * 100, 1) if opt_cost else 0.0,
        "energy_wh": round(reasoning_wh, 1),
        "energy_share_pct": round(reasoning_wh / (reasoning_wh + normal_wh) * 100, 1)
        if reasoning_wh + normal_wh else 0.0,
        "cap_pct": cap_fraction * 100,
        "cap_cost_savings_usd": round(sum(x["cost_saving"] for x in displaced), 2),
        "cap_energy_savings_wh": round(sum(x["wh_saving"] for x in displaced), 1),
        "routing_rule": "reason only when complexity >= 0.8 or model confidence < 0.6",
        "groups": group_stats,
        "before_usd": opt_cost, "after_usd": opt_cost - sum(x["cost_saving"] for x in displaced),
        "before_wh": reasoning_wh + normal_wh,
        "after_wh": reasoning_wh + normal_wh - sum(x["wh_saving"] for x in displaced),
    }

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        print("cache economics:")
        for tier, result in cache_economics.items():
            print(f"  {tier}: {result['avg_cache_reads']} reads vs "
                  f"{result['break_even_reads']} break-even -> cache={result['worth_it']}")
        print("reasoning budget:")
        print(f"  {reasoning_budget['traffic_pct']}% traffic -> "
              f"{reasoning_budget['cost_share_pct']}% cost, "
              f"{reasoning_budget['energy_share_pct']}% energy")
        print(f"  cap at {reasoning_budget['cap_pct']:.0f}% saves "
              f"${reasoning_budget['cap_cost_savings_usd']:.2f}/day and "
              f"{reasoning_budget['cap_energy_savings_wh']:.1f} Wh/day")

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "cache_economics": cache_economics, "reasoning_budget": reasoning_budget,
        "stages": {"baseline": base_cost, "cascade": cascade_cost,
                   "cache": cache_cost, "batch": opt_cost - write_cost,
                   "with_cache_writes": opt_cost},
        "cache_write_daily": write_cost,
    }


if __name__ == "__main__":
    run()
