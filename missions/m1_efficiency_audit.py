"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {
        "util": [], "mfu": [], "mbu": [], "achieved_bw": [], "mem_used": [],
        "type": None, "workload": None, "idle_hours": 0,
    })
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["workload"] = r["workload"]
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        a["achieved_bw"].append(num(r["achieved_bw_tbs"]))
        a["mem_used"].append(num(r["mem_used_gb"]))
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"], "workload": a["workload"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "achieved_bw_tbs": round(max(a["achieved_bw"]), 3),
            "required_vram_gb": round(max(a["mem_used"]) * 1.10, 1),
            "idle_hours": a["idle_hours"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(catalog_by_type()[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    # Extension 2: right-size bandwidth-bound serving GPUs. A candidate must
    # preserve 10% VRAM headroom and 25% bandwidth headroom; choosing solely by
    # $/GPU-hour could pick a device that cannot hold the model or feed decode.
    catalog_efficiency = []
    for gtype, c in cat.items():
        hbm = num(c["hbm_gb"])
        catalog_efficiency.append({
            "gpu_type": gtype,
            "usd_per_gb_vram": round(num(c["on_demand_hr"]) / hbm, 4) if hbm else 0.0,
            "peak_bw_tbs": num(c["peak_bw_tbs"]),
            "on_demand_hr": num(c["on_demand_hr"]),
        })

    rightsize = []
    for s in summary:
        if s["workload"] not in ("infer", "embed") or s["mbu"] >= 0.40:
            continue
        current = cat[s["gpu_type"]]
        required_bw = s["achieved_bw_tbs"] * 1.25
        candidates = [
            (gtype, c) for gtype, c in cat.items()
            if num(c["hbm_gb"]) >= s["required_vram_gb"]
            and num(c["peak_bw_tbs"]) >= required_bw
            and num(c["on_demand_hr"]) < num(current["on_demand_hr"])
        ]
        if not candidates:
            continue
        target, target_cat = min(candidates, key=lambda item: num(item[1]["on_demand_hr"]))
        hourly_savings = num(current["on_demand_hr"]) - num(target_cat["on_demand_hr"])
        rightsize.append({
            "gpu_id": s["gpu_id"], "current_gpu": s["gpu_type"], "target_gpu": target,
            "required_vram_gb": s["required_vram_gb"], "required_bw_tbs": round(required_bw, 3),
            "target_vram_gb": int(num(target_cat["hbm_gb"])),
            "target_bw_tbs": num(target_cat["peak_bw_tbs"]),
            "monthly_savings": round(hourly_savings * 24 * 30),
            "savings_pct": round(hourly_savings / num(current["on_demand_hr"]) * 100, 1),
        })
    rightsize_monthly = sum(r["monthly_savings"] for r in rightsize)

    # A compute-bound training util-lie is not a right-sizing signal. Estimate
    # only the equivalent capacity recoverable by lifting MFU to a conservative
    # 35% target through profiling, larger batches, and communication overlap.
    mfu_recovery = []
    for s in lies:
        if s["workload"] != "train" or s["mfu"] >= 0.35:
            continue
        monthly_cost = num(cat[s["gpu_type"]]["on_demand_hr"]) * 24 * 30
        recoverable_fraction = 1.0 - s["mfu"] / 0.35
        mfu_recovery.append({
            "gpu_id": s["gpu_id"], "current_mfu": s["mfu"], "target_mfu": 0.35,
            "equivalent_monthly_savings": round(monthly_cost * recoverable_fraction),
        })
    mfu_recovery_monthly = sum(r["equivalent_monthly_savings"] for r in mfu_recovery)

    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")
        print("\nMemory-bound right-sizing (VRAM + bandwidth guardrails):")
        if rightsize:
            for r in rightsize:
                print(f"  {r['gpu_id']}: {r['current_gpu']} -> {r['target_gpu']}  "
                      f"${r['monthly_savings']:,}/month ({r['savings_pct']}%)")
        else:
            print("  no safe cheaper candidate")
        print(f"Right-size savings: ${rightsize_monthly:,.0f}/month")
        if mfu_recovery:
            print("MFU remediation (equivalent capacity, validate before deprovisioning):")
            for r in mfu_recovery:
                print(f"  {r['gpu_id']}: MFU {r['current_mfu']:.3f} -> {r['target_mfu']:.2f}, "
                      f"up to ${r['equivalent_monthly_savings']:,}/month")

    return {"summary": summary, "lies": lies, "idle_waste_daily": round(idle_waste, 2),
            "catalog_efficiency": catalog_efficiency, "rightsize": rightsize,
            "rightsize_monthly": round(rightsize_monthly), "mfu_recovery": mfu_recovery,
            "mfu_recovery_monthly": round(mfu_recovery_monthly)}


if __name__ == "__main__":
    run()
