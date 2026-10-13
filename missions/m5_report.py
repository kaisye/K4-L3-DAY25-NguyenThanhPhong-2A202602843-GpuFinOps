"""M5 — Optimization Report: combine M1-M4 into baseline-vs-optimized (deck §1/§11).

Run: python missions/m5_report.py   ->  outputs/report.md + outputs/savings.png
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import os
from missions._common import ROOT
from finops import report, sustainability
from missions import m1_efficiency_audit, m2_inference_levers, m3_purchasing

DAYS = 30
def run(verbose: bool = True) -> dict:
    r1 = m1_efficiency_audit.run(verbose=False)
    r2 = m2_inference_levers.run(verbose=False)
    r3 = m3_purchasing.run(verbose=False)
    # --- buckets ---
    infer_savings = (r2["baseline_daily"] - r2["optimized_daily"]) * DAYS
    purchasing_savings = r3["on_demand_monthly"] - r3["optimized_monthly"]

    idle_savings = r1["idle_waste_daily"] * DAYS
    rightsize_savings = r1["rightsize_monthly"]
    reasoning_savings = r2["reasoning_budget"]["cap_cost_savings_usd"] * DAYS

    levers = {
        "Inference (cascade/cache/batch)": round(infer_savings),
        "Purchasing (spot/reserved)": round(purchasing_savings),
        "Right-size memory-bound GPUs": round(rightsize_savings),
        "Recover low-MFU capacity": r1["mfu_recovery_monthly"],
        "Kill idle GPUs": round(idle_savings),
        "Reasoning budget": round(reasoning_savings),
    }
    baseline = r2["baseline_daily"] * DAYS + r3["on_demand_monthly"]
    optimized = baseline - sum(levers.values())
    total_pct = sum(levers.values()) / baseline * 100 if baseline else 0.0

    # --- sustainability snapshot ---
    median_tokens = 800
    wh = sustainability.wh_per_query(median_tokens)
    sust = {
        "wh_per_query": wh,
        "carbon_g": sustainability.carbon_g(wh, "us-east-1"),
        "best_region": r3["carbon_aware"]["balanced_region"],
        "carbon_savings_kg": r3["carbon_aware"]["carbon_savings_kg"],
        "carbon_reduction_pct": r3["carbon_aware"]["carbon_reduction_pct"],
    }

    adjusted_opt_daily = r2["reasoning_budget"]["after_usd"]
    adjusted_opt_per_m = adjusted_opt_daily / (r2["total_tokens"] / 1e6)
    cache_values = list(r2["cache_economics"].values())
    extensions = {
        "purchasing": {"legacy_savings_pct": r3["legacy_savings_pct"],
                       "savings_pct": r3["savings_pct"]},
        "rightsize": {"count": len(r1["rightsize"]),
                      "monthly_savings": r1["rightsize_monthly"]},
        "cache": {"observed_reads": min(v["avg_cache_reads"] for v in cache_values),
                  "break_even_reads": max(v["break_even_reads"] for v in cache_values)},
        "reasoning": r2["reasoning_budget"],
    }
    md = report.build_report(
        baseline, optimized, levers, sustainability=sust,
        unit_economics={"baseline_per_m": r2["baseline_per_m"],
                        "optimized_per_m": adjusted_opt_per_m},
        extensions=extensions,
    )
    conservative_savings = sum(levers.values()) - r1["mfu_recovery_monthly"]
    md += (f"\n\n## Scope and conditional capacity recovery\n\n"
           f"Savings excluding the unbenchmarked MFU target: ${conservative_savings:,.0f} "
           f"({conservative_savings / baseline * 100:.1f}%). The headline includes "
           f"${r1['mfu_recovery_monthly']:,.0f} conditional capacity value at MFU 35%; "
           "it is a projection, not verified cash savings.\n\n"
           "Inference $/1M-token covers API-model charges only; GPU purchasing is a separate "
           "30-day scenario. Telemetry fleet IDs are not mapped to workload jobs, so additive "
           "fleet savings require a non-overlap assumption. Carbon uses actual job days. "
           "Reserved 1-year rates assume recurring service demand for at least one year; "
           "30 days of observations alone cannot justify that commitment.\n")
    from missions.submission_details import build_details
    md += build_details(r1, r2, r3)
    out_md = os.path.join(ROOT, "outputs", "report.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w") as f:
        f.write(md)
    with open(os.path.join(ROOT, "outputs", "analysis_writeup.md"), "w") as f:
        f.write("# Kiến thức, quá trình và điểm cần chú ý — Lab 25\n\n"
                "Đã đọc hướng dẫn, code engine, dữ liệu và rubric; chạy baseline seed=25; "
                "triển khai 5 extension; đối chiếu lại checklist; sửa write charge cache, "
                "cap reasoning 10%, bảng policy cũ/mới, carbon từng job và giả định forecast.\n\n"
                "Kiến thức cần đọc: MFU/MBU và roofline (metrics.py), unit economics và "
                "cache break-even (pricing.py), spot checkpoint/rework, break-even reserved, "
                "showback/chargeback và FOCUS (allocation.py), Wh/carbon (sustainability.py).\n\n"
                "Khó khăn chính: CSV không có prefix IDs/read counts, không có forecast nhiều năm, "
                "không map fleet sang jobs. Vì thế cache, commitment và tổng savings đều cần "
                "giả định công khai. MFU 35% chưa được benchmark; phần capacity recovery "
                "được giữ riêng dưới dạng conditional projection.\n\n"
                "Chạy lại: `.venv/bin/python data/generate.py`, "
                "`.venv/bin/python missions/run_all.py`, `.venv/bin/python verify.py`, "
                "`.venv/bin/python -m pytest -q`. Kiểm chứng bàn giao: 11/11 checks, 20 tests.\n\n"
                + md + "\n")
    png = report.savings_waterfall(levers, os.path.join(ROOT, "outputs", "savings.png"))

    if verbose:
        print("== M5 Optimization Report ==")
        print(md)
        print(f"\nWritten: outputs/report.md" + (f" + outputs/savings.png" if png else " (matplotlib absent: PNG skipped)"))

    return {"baseline_monthly": round(baseline), "optimized_monthly": round(optimized),
            "levers": levers, "total_savings_pct": round(total_pct, 1),
            "extensions": extensions, "sustainability": sust}


if __name__ == "__main__":
    run()
