"""Reproducible submission tables and Vietnamese mission analysis."""
from missions._common import catalog_by_type, num


def build_details(r1, r2, r3):
    lines = ["", "## Chi tiết đo lường và giả định", "",
             "### Inference: cùng số token, lần lượt từng đòn bẩy", "",
             "| Bước | USD/ngày | USD/1M-token | Savings tăng thêm USD/ngày |",
             "|---|---:|---:|---:|"]
    previous = None
    for name, cost in r2["stages"].items():
        saving = 0 if previous is None else previous - cost
        lines.append(f"| {name} | {cost:.6f} | {cost / (r2['total_tokens'] / 1e6):.6f} | {saving:.6f} |")
        previous = cost
    lines += ["", "Cache reads không được đo trong CSV: giả định một prefix dùng chung cho mỗi "
              "(tier, project/team), không expire trong ngày; số request trong nhóm là số reads "
              "giả định. Chi phí ghi bổ sung 1.25 lần giá input, phân bổ theo reads, không hưởng "
              "batch discount. Đây là scenario kinh tế, cần prefix ID/TTL/write events để đo thật.", "",
              "| Tier | Reads giả định | Reads hòa vốn | Bật cache |",
              "|---|---:|---:|---|"]
    for tier, c in r2["cache_economics"].items():
        lines.append(f"| {tier} | {c['avg_cache_reads']} | {c['break_even_reads']} | {c['worth_it']} |")
    lines += ["", "Ít reads: 1 × 0.9 < 1.25 nên không bật. Nhiều reads: 2 × 0.9 > 1.25 nên bật. "
              "Đơn vị write_cost trong helper là bội số giá input, không phải USD tuyệt đối.", "",
              "### Reasoning: cap 10%", "",
              "| Nhóm | Request | Token | USD/ngày | Wh/ngày | % request | % tiền | % Wh |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    budget = r2["reasoning_budget"]
    for name, g in budget["groups"].items():
        lines.append(f"| {name} | {g['requests']} | {g['tokens']} | {g['cost_usd']:.6f} | "
                     f"{g['energy_wh']:.3f} | {g['requests']/2400*100:.2f} | "
                     f"{g['cost_usd']/budget['before_usd']*100:.2f} | "
                     f"{g['energy_wh']/budget['before_wh']*100:.2f} |")
    lines += ["", "| Cap | USD trước | USD sau | Wh trước | Wh sau |",
              "|---|---:|---:|---:|---:|",
              f"| 10% | {budget['before_usd']:.6f} | {budget['after_usd']:.6f} | "
              f"{budget['before_wh']:.3f} | {budget['after_wh']:.3f} |",
              "", "Traffic reasoning đã dưới 10% nên savings USD và Wh bằng 0; không đổi output/model "
              "trong kịch bản này, mẫu số token giữ nguyên. Quy tắc đề xuất: chỉ reasoning khi complexity "
              ">=0.8 hoặc confidence <0.6; CSV chưa có score nên chưa kiểm chứng chất lượng routing.", "",
              "### Purchasing: policy trước/sau", "",
              "Interruption rate là giả định minh họa theo giờ (không phải số đo provider): "
              "H100 3%, H200 4%, A100 5%, A10G 10%, L4 8%, B200 6%, MI300X 7%. "
              "Chi phí dùng 30 ngày để tái lập baseline lab. Reserved 1 năm giả định demand lặp lại "
              "ít nhất 365 ngày; job_days 30 chỉ là cửa sổ quan sát, cần forecast trước khi mua.", "",
              "| Job | Tier cũ | USD cũ | Tier/kỳ hạn mới | USD mới |",
              "|---|---|---:|---|---:|"]
    for j in r3["recommendations"]:
        old = "reserved_3yr" if j["legacy_tier"] == "reserved" else j["legacy_tier"]
        lines.append(f"| {j['job_id']} | {old} | {j['legacy_cost']:.2f} | "
                     f"{j['reserved_term'] or j['tier']} | {j['optimized']:.2f} |")
    lines += ["", f"Savings policy cũ {r3['legacy_savings_pct']}%, mới {r3['savings_pct']}%. "
              "Không job nào đổi nhóm tier ở dataset này; ba service reserved đổi kỳ hạn 3 năm sang "
              "1 năm. Giá cao hơn là đổi lấy cam kết ngắn hơn; spot thay đổi chi phí do rate theo GPU.", "",
              "### Right-sizing: dung lượng và bandwidth", "",
              "| GPU hiện tại → đề xuất | VRAM cần / có GB | BW cần / có TB/s | USD/GB-hour cũ → mới | USD/tháng |",
              "|---|---:|---:|---|---:|"]
    cat = catalog_by_type()
    for x in r1["rightsize"]:
        old, new = cat[x["current_gpu"]], cat[x["target_gpu"]]
        lines.append(f"| {x['gpu_id']}: {x['current_gpu']} → {x['target_gpu']} | "
                     f"{x['required_vram_gb']} / {x['target_vram_gb']} | "
                     f"{x['required_bw_tbs']} / {x['target_bw_tbs']} | "
                     f"{num(old['on_demand_hr'])/num(old['hbm_gb']):.5f} → "
                     f"{num(new['on_demand_hr'])/num(new['hbm_gb']):.5f} | {x['monthly_savings']} |")
    lines += ["", "Tiêu chí dùng max bộ nhớ đã đo +10%, max bandwidth đã đo +25%, và MBU <40% "
              "ở serving workload. Đây là heuristic memory-bound; chưa có arithmetic intensity "
              "hay benchmark giữ throughput/p95 nên chỉ là ứng viên cần xác nhận.", "",
              "### Carbon: cùng công việc, ngày thực tế", "",
              "| Job | Ngày | Wh | us-east-1 gCO2e | europe-north1 gCO2e | Giảm gCO2e |",
              "|---|---:|---:|---:|---:|---:|"]
    carbon = r3["carbon_aware"]
    for j in carbon["jobs"]:
        lines.append(f"| {j['job_id']} | {j['days']} | {j['energy_wh']:.0f} | "
                     f"{j['before_g']:.1f} | {j['after_g']:.1f} | {j['before_g']-j['after_g']:.1f} |")
    lines += ["", "| Vùng | USD/kWh | gCO2e/kWh | USD điện | kgCO2e |",
              "|---|---:|---:|---:|---:|"]
    for reg in carbon["regions"]:
        lines.append(f"| {reg['region']} | {reg['usd_per_kwh']} | {reg['gco2_per_kwh']} | "
                     f"{reg['electricity_cost_usd']} | {reg['carbon_kg']} |")
    lines += ["", "Điện ước lượng = rated watts × hours_per_day × days × num_gpus, chưa gồm PUE "
              "hay checkpoint/rework; các vùng giữ cùng lượng công việc. Rẻ nhất us-east-wa, "
              "sạch nhất europe-north1. Tổng giảm 626,148 gCO2e. Score cân bằng cộng hai tỷ lệ "
              "cost/min_cost và carbon/min_carbon; trọng số khác có thể đổi lựa chọn.", "",
              "## Trả lời câu hỏi Guide.md", "",
              "**M1 (4.3):** GPU-Util cao nhất là gpu-h100-4: 98.2%, MFU 0.194. "
              "Kernel có thể active nhưng FLOPs thấp do memory stalls, đồng bộ hoặc I/O; cần profiling "
              "để xác định nguyên nhân. Idle gpu-h100-5 là 8 giờ: 20 USD/ngày, 600 USD/tháng. "
              "Đó là khoảng 2.2% baseline tổng hợp; riêng fleet telemetry phải dùng hóa đơn fleet làm mẫu số.", "",
              "**M2 (5.4):** Cascade đóng góp lớn nhất, xem bảng từng bước. 0.5 × 0.1 = 0.05 "
              "chỉ cho phần input cache hoàn toàn; output vẫn trả phí. Batch phù hợp offline/eval, "
              "không phù hợp chat tương tác có SLA latency thấp.", "",
              "**M3 (6.4):** train-llm, train-embed, finetune, dev-sandbox và batch-eval dùng spot "
              "vì interruptible và có thể checkpoint. Effective hours gồm checkpoint + rework do thu hồi. "
              "infer-chat/rag/search chỉ nên reserved khi demand ổn định vượt break-even và có forecast "
              "đủ dài; nếu kết thúc sau 30 ngày thật thì on-demand phù hợp hơn.", "",
              "**M4 (7.4):** Assistant tốn nhiều nhất, khoảng 2.59 USD/ngày (~30.5% tổng "
              "inference). Tag coverage khoảng 92%, vượt gate 80%; phải "
              "xử lý phần thiếu project trước khi chargeback nghiêm ngặt. FOCUS chuẩn hóa schema "
              "để so sánh chi phí nhiều provider. Export hiện là mẫu 50 request, FOCUS-style tối thiểu, "
              "không phải toàn hóa đơn hay chứng nhận đầy đủ chuẩn FOCUS.", ""]
    return "\n".join(lines)
