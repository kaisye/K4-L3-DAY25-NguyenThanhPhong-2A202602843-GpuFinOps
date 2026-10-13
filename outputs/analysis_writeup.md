# Kiến thức, quá trình và điểm cần chú ý — Lab 25

Đã đọc hướng dẫn, code engine, dữ liệu và rubric; chạy baseline seed=25; triển khai 5 extension; đối chiếu lại checklist; sửa write charge cache, cap reasoning 10%, bảng policy cũ/mới, carbon từng job và giả định forecast.

Kiến thức cần đọc: MFU/MBU và roofline (metrics.py), unit economics và cache break-even (pricing.py), spot checkpoint/rework, break-even reserved, showback/chargeback và FOCUS (allocation.py), Wh/carbon (sustainability.py).

Khó khăn chính: CSV không có prefix IDs/read counts, không có forecast nhiều năm, không map fleet sang jobs. Vì thế cache, commitment và tổng savings đều cần giả định công khai. MFU 35% chưa được benchmark; phần capacity recovery được giữ riêng dưới dạng conditional projection.

Chạy lại: `.venv/bin/python data/generate.py`, `.venv/bin/python missions/run_all.py`, `.venv/bin/python verify.py`, `.venv/bin/python -m pytest -q`. Kiểm chứng bàn giao: 11/11 checks, 20 tests.

# NimbusAI — GPU Cost Optimization Report

**Period:** monthly
**Baseline spend:** $27,133
**Optimized spend:** $16,170
**Projected savings:** $10,963  (**40%**)
**Baseline unit cost:** $6.488/1M-token
**Optimized unit cost:** $1.129/1M-token

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,211 |
| Purchasing (spot/reserved) | $8,062 |
| Right-size memory-bound GPUs | $288 |
| Recover low-MFU capacity | $802 |
| Kill idle GPUs | $600 |
| Reasoning budget | $0 |

## Sustainability

- Energy per query: 0.24 Wh
- Carbon per query: 0.091 gCO2e
- Region selected by equal-weight normalized cost/carbon score: europe-north1
- Carbon-aware scheduling savings: 626.15 kgCO2e (92.1%)

## Your Turn extensions

1. **Risk-aware purchasing:** legacy policy saved 39.1%; the duration/risk-aware policy saves 31.4% while avoiding an unjustified 3-year commitment.
2. **MBU right-sizing:** 2 serving GPUs have safe alternatives after VRAM and bandwidth guardrails, worth $288/month.
3. **Cache economics:** cache is enabled only above break-even; assumed reuse is 62.2 reads versus 1.39 required.
4. **Reasoning budget:** 8.4% of requests consume 94.0% of inference energy. A 10% cap saves 0.0 Wh/day.
5. **Carbon-aware scheduling:** move checkpointable jobs only after latency and data-residency checks; the cleanest region is not automatically the operationally best region.

_Figures are June-2026 as-of snapshots; re-baseline before acting._

## Scope and conditional capacity recovery

Savings excluding the unbenchmarked MFU target: $10,161 (37.4%). The headline includes $802 conditional capacity value at MFU 35%; it is a projection, not verified cash savings.

Inference $/1M-token covers API-model charges only; GPU purchasing is a separate 30-day scenario. Telemetry fleet IDs are not mapped to workload jobs, so additive fleet savings require a non-overlap assumption. Carbon uses actual job days. Reserved 1-year rates assume recurring service demand for at least one year; 30 days of observations alone cannot justify that commitment.

## Chi tiết đo lường và giả định

### Inference: cùng số token, lần lượt từng đòn bẩy

| Bước | USD/ngày | USD/1M-token | Savings tăng thêm USD/ngày |
|---|---:|---:|---:|
| baseline | 48.874161 | 6.487984 | 0.000000 |
| cascade | 11.475643 | 1.523377 | 37.398518 |
| cache | 10.279188 | 1.364549 | 1.196455 |
| batch | 8.484623 | 1.126323 | 1.794565 |
| with_cache_writes | 8.505652 | 1.129115 | -0.021029 |

Cache reads không được đo trong CSV: giả định một prefix dùng chung cho mỗi (tier, project/team), không expire trong ngày; số request trong nhóm là số reads giả định. Chi phí ghi bổ sung 1.25 lần giá input, phân bổ theo reads, không hưởng batch discount. Đây là scenario kinh tế, cần prefix ID/TTL/write events để đo thật.

| Tier | Reads giả định | Reads hòa vốn | Bật cache |
|---|---:|---:|---|
| small | 237.8 | 1.39 | True |
| large | 62.2 | 1.39 | True |

Ít reads: 1 × 0.9 < 1.25 nên không bật. Nhiều reads: 2 × 0.9 > 1.25 nên bật. Đơn vị write_cost trong helper là bội số giá input, không phải USD tuyệt đối.

### Reasoning: cap 10%

| Nhóm | Request | Token | USD/ngày | Wh/ngày | % request | % tiền | % Wh |
|---|---:|---:|---:|---:|---:|---:|---:|
| reasoning | 201 | 1241156 | 1.397181 | 29787.744 | 8.38 | 16.43 | 94.04 |
| normal | 2199 | 6291871 | 7.108470 | 1887.561 | 91.62 | 83.57 | 5.96 |

| Cap | USD trước | USD sau | Wh trước | Wh sau |
|---|---:|---:|---:|---:|
| 10% | 8.505652 | 8.505652 | 31675.305 | 31675.305 |

Traffic reasoning đã dưới 10% nên savings USD và Wh bằng 0; không đổi output/model trong kịch bản này, mẫu số token giữ nguyên. Quy tắc đề xuất: chỉ reasoning khi complexity >=0.8 hoặc confidence <0.6; CSV chưa có score nên chưa kiểm chứng chất lượng routing.

### Purchasing: policy trước/sau

Interruption rate là giả định minh họa theo giờ (không phải số đo provider): H100 3%, H200 4%, A100 5%, A10G 10%, L4 8%, B200 6%, MI300X 7%. Chi phí dùng 30 ngày để tái lập baseline lab. Reserved 1 năm giả định demand lặp lại ít nhất 365 ngày; job_days 30 chỉ là cửa sổ quan sát, cần forecast trước khi mua.

| Job | Tier cũ | USD cũ | Tier/kỳ hạn mới | USD mới |
|---|---|---:|---|---:|
| job-train-llm | spot | 7596.00 | spot | 7524.00 |
| job-train-embed | spot | 1392.60 | spot | 1393.00 |
| job-finetune | spot | 569.70 | spot | 564.00 |
| job-infer-chat | reserved_3yr | 2592.00 | reserved_1yr | 3456.00 |
| job-infer-rag | reserved_3yr | 2160.00 | reserved_1yr | 3024.00 |
| job-infer-search | reserved_3yr | 972.00 | reserved_1yr | 1296.00 |
| job-dev-sandbox | spot | 202.56 | spot | 207.00 |
| job-batch-eval | spot | 142.43 | spot | 141.00 |

Savings policy cũ 39.1%, mới 31.4%. Không job nào đổi nhóm tier ở dataset này; ba service reserved đổi kỳ hạn 3 năm sang 1 năm. Giá cao hơn là đổi lấy cam kết ngắn hơn; spot thay đổi chi phí do rate theo GPU.

### Right-sizing: dung lượng và bandwidth

| GPU hiện tại → đề xuất | VRAM cần / có GB | BW cần / có TB/s | USD/GB-hour cũ → mới | USD/tháng |
|---|---:|---:|---|---:|
| gpu-a10g-0: A10G → L4 | 22.3 / 24 | 0.227 / 0.3 | 0.04167 → 0.03333 | 144 |
| gpu-a10g-1: A10G → L4 | 22.4 / 24 | 0.265 / 0.3 | 0.04167 → 0.03333 | 144 |

Tiêu chí dùng max bộ nhớ đã đo +10%, max bandwidth đã đo +25%, và MBU <40% ở serving workload. Đây là heuristic memory-bound; chưa có arithmetic intensity hay benchmark giữ throughput/p95 nên chỉ là ứng viên cần xác nhận.

### Carbon: cùng công việc, ngày thực tế

| Job | Ngày | Wh | us-east-1 gCO2e | europe-north1 gCO2e | Giảm gCO2e |
|---|---:|---:|---:|---:|---:|
| job-train-llm | 14 | 1568000 | 595840.0 | 47040.0 | 548800.0 |
| job-train-embed | 5 | 80000 | 30400.0 | 2400.0 | 28000.0 |
| job-finetune | 3 | 25200 | 9576.0 | 756.0 | 8820.0 |
| job-dev-sandbox | 22 | 52800 | 20064.0 | 1584.0 | 18480.0 |
| job-batch-eval | 30 | 63000 | 23940.0 | 1890.0 | 22050.0 |

| Vùng | USD/kWh | gCO2e/kWh | USD điện | kgCO2e |
|---|---:|---:|---:|---:|
| us-east-1 | 0.12 | 380 | 214.68 | 679.82 |
| us-west-2 | 0.07 | 120 | 125.23 | 214.68 |
| europe-north1 | 0.09 | 30 | 161.01 | 53.67 |
| europe-central2 | 0.18 | 660 | 322.02 | 1180.74 |
| us-east-wa | 0.055 | 90 | 98.39 | 161.01 |

Điện ước lượng = rated watts × hours_per_day × days × num_gpus, chưa gồm PUE hay checkpoint/rework; các vùng giữ cùng lượng công việc. Rẻ nhất us-east-wa, sạch nhất europe-north1. Tổng giảm 626,148 gCO2e. Score cân bằng cộng hai tỷ lệ cost/min_cost và carbon/min_carbon; trọng số khác có thể đổi lựa chọn.

## Trả lời câu hỏi Guide.md

**M1 (4.3):** GPU-Util cao nhất là gpu-h100-4: 98.2%, MFU 0.194. Kernel có thể active nhưng FLOPs thấp do memory stalls, đồng bộ hoặc I/O; cần profiling để xác định nguyên nhân. Idle gpu-h100-5 là 8 giờ: 20 USD/ngày, 600 USD/tháng. Đó là khoảng 2.2% baseline tổng hợp; riêng fleet telemetry phải dùng hóa đơn fleet làm mẫu số.

**M2 (5.4):** Cascade đóng góp lớn nhất, xem bảng từng bước. 0.5 × 0.1 = 0.05 chỉ cho phần input cache hoàn toàn; output vẫn trả phí. Batch phù hợp offline/eval, không phù hợp chat tương tác có SLA latency thấp.

**M3 (6.4):** train-llm, train-embed, finetune, dev-sandbox và batch-eval dùng spot vì interruptible và có thể checkpoint. Effective hours gồm checkpoint + rework do thu hồi. infer-chat/rag/search chỉ nên reserved khi demand ổn định vượt break-even và có forecast đủ dài; nếu kết thúc sau 30 ngày thật thì on-demand phù hợp hơn.

**M4 (7.4):** Assistant tốn nhiều nhất, khoảng 2.59 USD/ngày (~30.5% tổng inference). Tag coverage khoảng 92%, vượt gate 80%; phải xử lý phần thiếu project trước khi chargeback nghiêm ngặt. FOCUS chuẩn hóa schema để so sánh chi phí nhiều provider. Export hiện là mẫu 50 request, FOCUS-style tối thiểu, không phải toàn hóa đơn hay chứng nhận đầy đủ chuẩn FOCUS.

