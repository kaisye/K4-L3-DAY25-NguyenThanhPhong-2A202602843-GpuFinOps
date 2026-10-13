"""Report assembly — the lab's deliverable: baseline vs optimized + savings chart."""
from __future__ import annotations


def build_report(baseline_usd: float, optimized_usd: float, levers: dict,
                 sustainability: dict | None = None, period: str = "monthly",
                 unit_economics: dict | None = None,
                 extensions: dict | None = None) -> str:
    """Return a markdown cost-optimization report."""
    savings = baseline_usd - optimized_usd
    pct = (savings / baseline_usd * 100.0) if baseline_usd > 0 else 0.0
    lines = [
        "# NimbusAI — GPU Cost Optimization Report",
        "",
        f"**Period:** {period}",
        f"**Baseline spend:** ${baseline_usd:,.0f}",
        f"**Optimized spend:** ${optimized_usd:,.0f}",
        f"**Projected savings:** ${savings:,.0f}  (**{pct:.0f}%**)",
    ]
    if unit_economics:
        lines += [
            f"**Baseline unit cost:** ${unit_economics.get('baseline_per_m', 0):.3f}/1M-token",
            f"**Optimized unit cost:** ${unit_economics.get('optimized_per_m', 0):.3f}/1M-token",
        ]
    lines += ["", "## Savings by lever", "", "| Lever | Savings (USD) |", "|---|---|"]
    for name, amount in levers.items():
        lines.append(f"| {name} | ${amount:,.0f} |")
    if sustainability:
        lines += [
            "",
            "## Sustainability",
            "",
            f"- Energy per query: {sustainability.get('wh_per_query', 0):.2f} Wh",
            f"- Carbon per query: {sustainability.get('carbon_g', 0):.3f} gCO2e",
            f"- Region selected by equal-weight normalized cost/carbon score: {sustainability.get('best_region', 'n/a')}",
        ]
        if "carbon_savings_kg" in sustainability:
            lines.append(
                f"- Carbon-aware scheduling savings: {sustainability['carbon_savings_kg']:,.2f} "
                f"kgCO2e ({sustainability.get('carbon_reduction_pct', 0):.1f}%)"
            )
    if extensions:
        cache = extensions.get("cache", {})
        reasoning = extensions.get("reasoning", {})
        purchasing = extensions.get("purchasing", {})
        rightsize = extensions.get("rightsize", {})
        lines += [
            "", "## Your Turn extensions", "",
            "1. **Risk-aware purchasing:** legacy policy saved "
            f"{purchasing.get('legacy_savings_pct', 0):.1f}%; the duration/risk-aware policy "
            f"saves {purchasing.get('savings_pct', 0):.1f}% while avoiding an unjustified 3-year commitment.",
            "2. **MBU right-sizing:** "
            f"{rightsize.get('count', 0)} serving GPUs have safe alternatives after VRAM and bandwidth "
            f"guardrails, worth ${rightsize.get('monthly_savings', 0):,.0f}/month.",
            "3. **Cache economics:** cache is enabled only above break-even; assumed reuse is "
            f"{cache.get('observed_reads', 0):.1f} reads versus {cache.get('break_even_reads', 0):.2f} required.",
            "4. **Reasoning budget:** "
            f"{reasoning.get('traffic_pct', 0):.1f}% of requests consume "
            f"{reasoning.get('energy_share_pct', 0):.1f}% of inference energy. A "
            f"{reasoning.get('cap_pct', 0):.0f}% cap saves "
            f"{reasoning.get('cap_energy_savings_wh', 0):,.1f} Wh/day.",
            "5. **Carbon-aware scheduling:** move checkpointable jobs only after latency and data-residency "
            "checks; the cleanest region is not automatically the operationally best region.",
        ]
    lines += ["", "_Figures are June-2026 as-of snapshots; re-baseline before acting._"]
    return "\n".join(lines)


def savings_waterfall(levers: dict, path: str) -> str:
    """Write a simple savings bar chart PNG. Returns the path. No-op if matplotlib absent."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    names = list(levers.keys())
    vals = [levers[n] for n in names]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(names, vals, color="#2e548a")
    ax.set_ylabel("Savings (USD / month)")
    ax.set_title("GPU cost savings by FinOps lever")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
