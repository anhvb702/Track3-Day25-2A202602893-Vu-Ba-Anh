# Lab 25B — Report

**Họ tên:** Vũ Bá Anh  **MSSV:** 2A202602893  **Commit:** cập nhật hash sau commit nộp  **Điểm tự động (`make grade`):** 84 / 88 (4 điểm SLO hidden do giảng viên chấm)

> Số liệu dưới đây lấy từ các báo cáo và CSV hiện có trong `reports/`. Kết quả là một lần chạy public; grader có thể dùng seed và băng ẩn khác.

## 1. Kết quả Game Day (naive vs resilient)

| Băng | Client | availability | p95 (s) | amplification | retry_ratio | cost/turn | recovery (s) | PASS? |
|---|---|---:|---:|---:|---:|---:|---:|:---:|
| G1 | naive | 0.7194 | 7.157 | 7.738 | 6.738 | 2.163 | 4 | FAIL |
| G1 | resilient | 1.0000 | 4.776 | 1.062 | 0.002 | 2.101 | 0 | PASS |
| G2 | naive | 0.4560 | 15.034 | 9.904 | 8.904 | 4.627 | 155 | FAIL |
| G2 | resilient | 1.0000 | 11.911 | 1.059 | 0.008 | 2.161 | 0 | PASS |
| G3 | naive | 1.0000 | 4.768 | 1.164 | 0.164 | 2.328 | 0 | FAIL |
| G3 | resilient | 1.0000 | 4.738 | 1.058 | 0.034 | 2.141 | 0 | PASS |
| G4 | naive | 1.0000 | 13.764 | 1.004 | 0.004 | 2.008 | 0 | FAIL |
| G4 | resilient | 1.0000 | 5.562 | 1.015 | 0.002 | 2.072 | 0 | PASS |
| G5 | naive | 0.3699 | 5.359 | 17.030 | 16.030 | 2.124 | — | FAIL |
| G5 | resilient | 0.8179 | 5.477 | 1.003 | 0.002 | 2.504 | — | PASS |
| G6 | naive | 0.5170 | 4.836 | 12.344 | 11.344 | 2.009 | 0 | FAIL |
| G6 | resilient | 1.0000 | 5.961 | 1.055 | 0.018 | 2.196 | 0 | PASS |

## 2. Cấu hình client và lý do

| Tham số | Giá trị | Vì sao (dựa trên băng nào, số liệu nào) |
|---|---:|---|
| attempt_timeout_s | 8.0 s | G6 có provider treo; timeout ngắn cho phép failover trong deadline 30 s. Thử 30 s làm G6 còn 94.88% availability, dưới ngưỡng 95%. |
| max_attempts_per_provider | 2 | Tối đa một retry cùng provider trước khi failover; G2 đạt amplification 1.059 và G3 retry_ratio 0.034. |
| backoff_base_s / cap_s | 0.25 / 4.0 s | Jitter rải retry, tránh đồng loạt quay lại provider; G1 có 0 vi phạm `retry-after`, amplification 1.062. |
| retry_budget_ratio | 0.1 | Giới hạn retry trong tải lỗi; khi breaker cố ý không mở, tắt budget làm G2 amplification tăng 1.378→1.675 và retry_ratio 0.058→0.495. |
| breaker.window_size / min_calls | 20 / 10 | Cửa sổ đủ phản ứng theo kết quả gần đây nhưng tránh mở vì vài lỗi rời rạc; G2 recovery 0 s trong lần public này. |
| breaker.failure_rate_threshold | 0.5 | Mở khi ít nhất nửa cửa sổ lỗi; G3 thực tế retry_ratio 0.034, thấp hơn giới hạn 0.10. |
| breaker.slow_call_s | 5.0 s | Bắt suy giảm không báo lỗi; G4 p95 giảm từ naive 13.764 s xuống 5.562 s. |
| breaker.open_duration_s | 10 s | Cho provider thời gian hồi phục rồi probe lại; G2 sau phục hồi có primary share 1.0. |
| breaker.half_open_max_probes / successes | 2 / 2 | Giới hạn tải lên provider đang hồi phục và chỉ đóng sau hai probe tốt; kiểm tra concurrency nằm trong unit test breaker. |
| quota_cooldown_s | 300 s | Hết quota không thể cải thiện bằng retry cùng account; G5 có 0 retry lỗi client và chỉ 2 lỗi quota trong resilient run. |

| Loại lỗi | Tính vào breaker? | Retry cùng provider? | Failover? | Cooldown |
|---|:---:|:---:|:---:|---|
| CLIENT_ERROR (400/401/403/404/422) | Không | Không | Không | Không |
| RATE_LIMITED (429 có retry-after) | Không | Không | Có | Tới `retry-after` |
| QUOTA_EXHAUSTED | Không | Không | Có | `quota_cooldown_s` |
| OVERLOADED / SERVER_ERROR / TIMEOUT | Có | Có, nếu còn lượt, budget và deadline | Nếu không retry được hoặc breaker từ chối | Backoff có jitter |

## 3. Ba thí nghiệm

1. **Retry budget là lớp bảo vệ cuối.** Để breaker không mở (`min_calls=1,000,000,000`) và tăng `max_attempts_per_provider=5`, bật budget cho G2 cho amplification **1.378**, retry_ratio **0.058**, recovery **0 s**; tắt budget cho kết quả **1.675**, **0.495**, **25 s**. Ở G3 retry_ratio tăng **0.068→0.159** khi tắt budget, dù availability vẫn 100%. Khi breaker hoạt động đúng, budget vẫn bảo vệ lúc breaker chưa đủ mẫu, khi có nhiều provider cùng lỗi và khi cấu hình hoặc giả định về sự cố sai.
2. **`attempt_timeout_s: 30`.** Ở G4 availability vẫn **100%**, p95 **5.608 s** (cấu hình 8 s là **5.562 s**); G4 không có lỗi nên timeout dài không giúp gì. Ở G6 availability giảm xuống **94.88%** (cấu hình 8 s là **100%**), không đạt ngưỡng 95%; p95 lần lượt **5.410 s** và **5.961 s** do fallback còn xử lý được nhiều request. Timeout nên dựa trên deadline người dùng, latency mục tiêu và thời gian còn lại để failover, không đặt bằng toàn bộ deadline.
3. **Bỏ lọc tool calling khỏi `ladder()`.** Trên G6, lần chạy không lọc ghi nhận **257 incompatible routes**, availability **89.22%**; lọc đúng thì **0** route không tương thích và availability **100%**. Nói với product manager: 257 yêu cầu cần dùng công cụ bị gửi tới model không có khả năng gọi công cụ, nên hệ thống không thể thực hiện yêu cầu dù model đó rẻ và đang sẵn sàng.

## 4. Workflow hoàn tiền

| Executor | completion | crashes | duplicate refunds | duplicate emails | lost refunds | overpaid | wasted LLM / crash |
|---|---:|---:|---:|---:|---:|---:|---:|
| naive | 1.000 | 81 | 128 | 81 | 0 | 1,574,200¢ | 1.123 |
| yours | 1.000 | 66 | 0 | 0 | 0 | 0¢ | 0.303 |

Idempotency key ngăn side effect chạy lặp khi response mất, nhưng không giúp worker biết bước nào đã hoàn tất sau khi khởi động lại; checkpoint cung cấp trạng thái đó. Checkpoint đơn thuần cũng không ngăn gọi payment lặp khi payment đã commit nhưng worker chết trước khi ghi checkpoint. Vì vậy cần cả key ổn định và checkpoint sau thành công. Nếu ghi checkpoint trước payment, crash ở giữa sẽ khiến lần resume bỏ qua payment và có thể làm mất khoản hoàn tiền.

## 5. Alerting & error budget

| Sự cố | Mong đợi | Naive alerter | Burn-rate alerter | Độ trễ phát hiện |
|---|---|---|---|---:|
| checkout_bug | page | page | page | 27 phút |
| provider_outage | page | page | page | 4 phút |
| deploy_blip | none | page (false) | none | — |
| slow_leak | ticket | không phát hiện | ticket | 1,337 phút |
| degraded_evening | page | page | page | 291 phút |
| night_spike | none | page (false) | none | — |
| small_bump | none | page (false) | none | — |

Naive tạo 7 page, 3 false page và không tạo ticket; burn-rate tạo 3 page, 1 ticket và **0 false page**. Với 25,901,755 request, 55,618 lỗi và ngân sách cho phép 129,508.8 lỗi, availability là **99.7853%**, đã dùng **42.95%**, còn **57.05%**; chưa freeze release. `small_bump` kéo dài 20 phút nhưng không vượt đồng thời ngưỡng dài và ngắn của page; nó tiêu khoảng 1% error budget tháng, không đáng đánh thức on-call giữa đêm hay giữa ngày.

## 6. Postmortem — Băng G2 với client naive

![G2: attempts mỗi giây và tỷ lệ call thành công của naive/resilient](gameday/G2_overload_storm.png)

Hình dùng tỷ lệ thành công trượt 10 giây; bảng timeline bên dưới tổng hợp cửa sổ 30 giây từ cùng CSV. Hai biểu đồ attempts dùng thang trục Y khác nhau.

**Tóm tắt:** Tại t=120, alpha mất 75% năng lực và tải request tăng nhanh hơn khả năng xử lý. Client naive tiếp tục retry cố định trên alpha, đẩy amplification lên 9.904 và availability toàn băng xuống 45.60%. Provider hồi phục ở t=300 nhưng hàng đợi retry còn tồn tại, khiến recovery mất thêm 155 giây.

**Ảnh hưởng:** 1,285/2,362 lượt user thất bại (**54.4%**); từ lúc sự cố bắt đầu ở t=120 tới khi recovery đạt tiêu chí vào khoảng t=455 là **335 giây**. Nếu tháng có 4 request/giây trong 30 ngày, error budget 0.5% tương đương khoảng 51,840 request lỗi; 1,285 lỗi chiếm khoảng **2.48%** ngân sách đó.

**Timeline** (cửa sổ 30 giây trong CSV; success ratio = `calls_ok / calls_done`):

| t (giây) | Sự kiện | Bằng chứng (số) |
|---:|---|---|
| 0–29 | Trạng thái bình thường | 7.3 attempts/s; success ratio 1.00 |
| 120–149 | Alpha mất 75% năng lực | 90.8 attempts/s; success ratio 0.52 |
| 150–179 | Retry storm hình thành | 140.7 attempts/s; success ratio 0.00 |
| 210–239 | Tải retry duy trì | 148.7 attempts/s; success ratio 0.00 |
| 270–299 | Trước khi provider hồi phục | 155.8 attempts/s; success ratio 0.00 |
| 300–329 | Alpha hồi phục hoàn toàn tại t=300 | 23.4 attempts/s; success ratio 0.00 |
| 360–389 | Hàng đợi còn nghẽn sau restore | 113.2 attempts/s; success ratio 0.00 |
| 420–449 | Đang hồi phục | 21.5 attempts/s; success ratio 0.00 |
| 450–479 | Tỷ lệ thành công bắt đầu trở lại | 11.5 attempts/s; success ratio 0.901; metric recovery đạt khoảng t=455 |
| 480–509 | Trở lại bình thường | 10.4 attempts/s; success ratio 1.00 |

**Trigger vs root cause:** Trigger là alpha mất 75% GPU trong 180 giây. Root cause là ba tầng retry chồng nhau, delay cố định, thiếu jitter, retry budget và breaker đã khuếch đại tải. Request đã timeout ở client vẫn tiếp tục chiếm slot provider; retry mới xếp thêm vào hàng đợi, làm độ trễ và timeout tăng, rồi kích hoạt thêm retry. Sau t=300, các request cũ vẫn chiếm năng lực, nên tải retry cao hơn khả năng phục vụ và hệ thống không tự phục hồi ngay.

**Điều gì giúp / điều gì làm tệ hơn:** Việc provider phục hồi là điều kiện cần nhưng không xóa hàng đợi đã tích tụ. Retry 3 tầng và thiếu jitter làm tệ hơn: peak đạt **155.8 attempts/s** so với **7.3 attempts/s** lúc bình thường; success ratio vẫn 0 trong cửa sổ t=360–389. Client resilient giới hạn amplification ở **1.059** và recovery đo được là **0 s** sau restore trong lần chạy này.

**Action items:**

| # | Hành động | Loại | Owner | Cách kiểm chứng |
|---|---|---|---|---|
| 1 | Chỉ cho phép một tầng retry với exponential full jitter | prevent | Owner: Agent Platform | CI chạy G1–G6; amplification ≤1.6, retry-after violations =0 |
| 2 | Thêm alert cho retry amplification và success ratio theo cửa sổ ngắn/dài | detect | Owner: SRE | Mô phỏng G2; alert trong 5 phút, không page trên blip ngắn |
| 3 | Bật breaker, retry budget và kiểm tra recovery sau restore | mitigate | Owner: Runtime | G2 nhiều seed: availability ≥95%, recovery ≤30 s, amplification ≤1.6 |

## 7. Một điểm yếu còn lại

G2 resilient có p95 **11.911 s**, vẫn cao dù availability 100% và amplification 1.059. Một số request chờ đến timeout alpha rồi mới failover, làm tăng tail latency. Có thể giảm `attempt_timeout_s` hoặc dùng timeout thích nghi theo latency gần đây, sau đó chạy lại G2/G6 nhiều seed để giữ availability ≥95%, G2 p95 thấp hơn và không tăng retry amplification quá 1.6.

## 8. Cache (Part G)

| Client | availability | faq_availability | cache_hit_ratio | stale_served | wrong_answers | outdated_answers | cost/turn | PASS? |
|---|---:|---:|---:|---:|---:|---:|---:|:---:|
| resilient (không cache) | 0.8373 | 0.8424 | 0.000 | 0 | 0 | 0 | 1.386 | FAIL |
| cached | 0.9124 | 0.9645 | 0.592 | 192 | 0 | 2 | 0.955 | PASS |

| Tham số `cache:` | Giá trị | Vì sao (số liệu nào) |
|---|---:|---|
| similarity_threshold | 0.92 | 0.80 gây 181 câu trả lời nhầm `other_question`; 0.92 đưa lỗi về 0. 0.97 cũng 0 lỗi nhưng hit ratio tụt xuống 0.499, dưới ngưỡng 0.50. |
| ttl_s | 30 s | Với TTL 30/60/300, outdated lần lượt 2/3/95; 300 vượt giới hạn 15 do thay đổi shipping không gửi webhook. |
| max_stale_s | 300 s | Stale-if-error giữ FAQ availability 96.45% trong outage. Khi max stale =0, FAQ availability giảm còn 85.29%, hit ratio 48.1%. |
| max_entries | 500 | Giới hạn bộ nhớ; số liệu C1 không cho thấy cần tăng hoặc giảm để đạt ngưỡng. |

**Thí nghiệm cache:** Với ngưỡng 0.80/0.92/0.97, hit ratio là **0.610/0.592/0.499**, wrong answers **181/0/0**, cost/turn **1.016/0.955/1.018**. Các câu bị trộn ở 0.80 thuộc intent khác nhau nhưng embedding gần nhau, như phí ship thành phố/tỉnh hoặc chính sách hoàn tiền/thời gian hoàn tiền (`other_question`).

Với TTL 30/60/300 giây, outdated answers là **2/3/95**, hit ratio **0.592/0.652/0.731**, cost/turn **0.955/0.915/0.863**. Webhook chỉ invalidate tài liệu đã được thông báo đổi; bảng phí ship đổi im lặng nên TTL là giới hạn duy nhất ngăn dùng câu trả lời cũ vô thời hạn. Khi `max_stale_s=0`, FAQ availability giảm từ **96.45% xuống 85.29%** vì cache không còn phục vụ câu trả lời cũ trong outage.

Câu hỏi cá nhân không được cache vì câu trả lời phụ thuộc dữ liệu riêng và có thể đổi sau khi cache; cache theo user vẫn có nguy cơ dùng sai scope hoặc lộ dữ liệu nếu key/scope sai. Khi cache đang che lỗi provider, on-call nên theo dõi availability và error rate trực tiếp của provider, burn rate, tỷ lệ stale served và tuổi dữ liệu; cache hit không chứng minh upstream đang khỏe.
