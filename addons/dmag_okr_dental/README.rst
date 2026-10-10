=============================
DMAG – OKR nha khoa tự đo
=============================

Cầu nối **OKR Scale** (repo ``tsvinh7-ux/OKR-scale``) với dữ liệu nha khoa: KR **tự cập nhật** qua
hook ``_compute_progress_by_method`` – không ai phải nhập tay, nên không ai "làm đẹp số".

Phương pháp đo bổ sung (trường *Đo bằng* của KR)
================================================
=========================  ===========================================================
Mã                         Cách tính (trong khung ngày của chu kỳ OKR, có thể ghi đè)
=========================  ===========================================================
dmag_nps                   NPS = %9–10 − %0–6 từ ``dmag.nps.response`` (nếu có – mềm)
dmag_wait_time             Phút chờ TB từ check-in đến lên ghế
dmag_pain_ok_rate          % lượt khám hoàn tất có thủ thuật với điểm đau ≤ 2
dmag_ortho_new             Số bệnh nhân có thủ thuật chỉnh nha lần đầu trong kỳ
dmag_plan_acceptance       Kế hoạch đồng ý / kế hoạch đã tư vấn (trừ nháp)
dmag_referral_revenue      Doanh thu thủ thuật của bệnh nhân có người giới thiệu / nguồn giới thiệu
dmag_afternoon_util        Phút đặt lịch giao 13:30–16:30 / (số ghế × 180 phút × ngày làm việc, trừ CN)
dmag_associate_share       % thủ thuật do bác sĩ đánh dấu *Bác sĩ phụ / associate*
dmag_material_cost         Gọi mềm ``get_material_kpis`` (module kho) – khóa ``material_cost_ratio``
=========================  ===========================================================

* Có thể lọc theo bác sĩ (``dmag_doctor_ids``). KR giảm dần (ví dụ chờ 30 → 10 phút) dùng mức xuất phát >
  mục tiêu.
* Nút *Cập nhật số liệu nha khoa* và cron hằng ngày ghi số liệu vào ``current_value``; chưa có dữ
  liệu → giữ nguyên số cũ (KR mới tạo đứng ở mức xuất phát).

Chỉ số cầu chì (``dmag.okr.guardrail``)
=======================================
Tỷ lệ phàn nàn > 2%/tháng (tự đo nếu lượt khám có cờ ``dmag_complaint``), hủy hợp đồng niềng
trong 30 ngày > 5% (tự đo), đánh giá 1–2 sao > 3/tháng (nhập tay). Vượt ngưỡng → mọi KR gắn với
chỉ số chuyển **Off Track (đỏ)** và hiện cảnh báo trên KR.

Cần xác nhận
============
* Định nghĩa chính xác: "ca niềng mới" (theo thủ thuật đầu tiên hay theo hợp đồng ký), tỷ lệ chốt
  (đếm theo kế hoạch hay theo giá trị), "bác sĩ phụ", khung giờ chiều và ngày làm việc.
* Nguồn NPS / phàn nàn / chi phí vật tư từ các module hành trình, kho (tên model, trường).
* Hủy hợp đồng niềng: hiện suy ra từ thời điểm hủy kế hoạch (``write_date``) – cần trường ngày hủy riêng.
* Ẩn / gỡ ``biz_okr`` trên Bizapps để tránh 2 ứng dụng OKR.
