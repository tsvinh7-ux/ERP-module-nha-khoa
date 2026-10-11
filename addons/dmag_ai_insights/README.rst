=============================================
DMAG – AI điều hành & Trung tâm AI
=============================================

Bốn tính năng AI cho Quản lý / Giám đốc (AI-13 … AI-16 trong ``docs/DE_XUAT_AI.md``) gắn vào **Bảng điều hành
mục tiêu**, cộng màn hình **Trung tâm AI** giới thiệu và mở thử cả 20 tính năng AI-00 … AI-19.
Mọi lời gọi mô hình ngôn ngữ đi qua cổng ``dmag.ai`` của ``dmag_ai_core`` (ẩn danh, nhật ký, chi phí, trần ngân sách).

Menu: **Nha khoa › Trợ lý AI** – *Trung tâm AI* (mọi nhân viên, lọc theo vai trò), *Hỏi đáp số liệu*, *Bản tin điều
hành*, *Cảnh báo bất thường*, *Dự báo doanh thu & vật tư* (Quản lý trở lên). Trên *Điều hành mục tiêu* có dải AI
(dự báo, bản tin, bất thường) và nút **"Hỏi AI về số liệu"** mở ngăn hội thoại.

AI-13 – Hỏi đáp số liệu điều hành
=================================
* **Claude API**: một lần ``dmag.ai.run('AI-13')`` với 5 công cụ **chỉ đọc**, ``strict: true`` (schema đóng, không
  ép ``tool_choice``): ``get_goal_dashboard(period)``, ``metric(key, date_from, date_to, doctor)``,
  ``compare_periods(key, period_a, period_b, doctor)``, ``list_top(entity, metric, period, order, limit)``,
  ``drill_records(key, period, doctor)``. Mọi số đi qua ``dmag.goal.engine`` → khớp Bảng điều hành. Công cụ trả mã
  đường dẫn; giao diện hiện nút **"Mở danh sách"** tới chứng từ (lượt khám, thủ thuật, kế hoạch, NPS…).
* **Giả lập**: bộ định tuyến ý định tiếng Việt (chỉ số: doanh thu, thực thu, khách mới, tỷ lệ chốt, không đến, NPS,
  công suất ghế, khiếu nại…; thời gian: hôm nay, tuần / tháng / quý này – trước, năm nay, 7 / 30 / 90 ngày; bác sĩ;
  kiểu câu: giá trị, vì sao, so sánh, xếp hạng, tổng quan) gọi CHÍNH các công cụ trên và ghép câu trả lời; vết gọi
  công cụ hiển thị cho người dùng.

AI-14 – Bản tin điều hành hằng tuần
===================================
Tác vụ định kỳ 07:00 sáng thứ Hai (``cron_dmag_ai_weekly_brief``) + nút *Soạn bản tin tuần ngay*. Dữ kiện tính tại chỗ:
tuần qua so với tuần trước, chỉ tiêu lệch (thực tế / mục tiêu / dự báo), nguyên nhân (phễu, bác sĩ, nhóm dịch vụ,
công suất ghế), việc tồn đọng đếm được (kế hoạch chờ chốt, lịch chưa xác nhận, ghế chiều trống, công nợ, cảnh báo).
Claude API: **một** yêu cầu với JSON dữ kiện + JSON schema (``headline, summary, off_track, causes, actions[3],
highlights``) – độc lập, không công cụ nên chuyển sang Message Batches (giảm 50 %) được (``_brief_request``).
Giả lập: dựng cùng cấu trúc từ dữ kiện. Lưu ``dmag.ai.brief`` (chatter), gửi thông báo cho Giám đốc.

AI-15 – Phát hiện bất thường (tại chỗ, không LLM)
=================================================
Thống kê chạy mỗi đêm + nút *Quét lại ngay*: giảm giá theo bác sĩ (kiểm định z), thủ thuật giảm vượt ngưỡng Tukey của
dịch vụ / vượt hạn mức, hoa hồng tuần tăng đột biến (z bền vững median/MAD), hủy / hoàn chứng từ đã có hiệu lực theo
người thao tác, hoàn tiền / hóa đơn điều chỉnh giảm, chênh lệch quỹ lặp lại, công nợ tăng nhanh (số dư phải thu tính
lại theo ngày), vật tư dùng vượt định mức BOM (theo vật tư và theo bác sĩ). Mỗi cảnh báo: mức độ, điểm thống kê,
quan sát – chuẩn so sánh, **Xem chứng từ**, luồng *Quản lý giải trình → Giám đốc đóng / bác bỏ*; tùy chọn **AI giải
thích** (qua cổng AI, chỉ gửi số liệu thống kê, không tên bệnh nhân).

AI-16 – Dự báo doanh thu & vật tư (tại chỗ)
===========================================
Doanh thu ngày còn lại = lịch đã đặt × tỷ lệ đến khám × hệ số quy đổi giá trị + phần sẽ phát sinh (Holt-Winters cộng
tính tự cài bằng Python, mùa vụ tuần 6 ngày, xu hướng hãm; ca lớn đột biến tách riêng theo ngưỡng Tukey) – trừ phần
thường đã đặt trước nếu lịch sử cho biết; mùa vụ tháng khi có ≥ 13 tháng; khoảng tin cậy 80 %; xác suất đạt mục
tiêu. Vật tư 30 ngày = max(nhịp tiêu hao, lịch hẹn × định mức + kế hoạch tồn × năng suất) so với tồn kho → gợi ý đặt.

Trung tâm AI
============
``dmag.ai.hub.get_hub()``: 20 thẻ (làm gì, ví dụ thực tế, lợi ích), nguồn (LOCAL / API trong nước / Claude API),
trạng thái (giả lập / AI thật / tại chỗ / tắt / chưa cài module), số lần dùng & chi phí tháng (hoặc chi phí nếu chạy
thật), nút **Thử ngay** mở màn hình chứa tính năng (bàn làm việc bác sĩ, bảng điều phối, Zalo giả lập, cổng bệnh
nhân, bảng điều hành…) – dò mềm external id của ``dmag_ai_clinical`` / ``dmag_ai_customer``; chưa cài thì mở màn hình
gốc gần nhất. Đầu trang: chế độ, ngân sách tháng, chi phí nếu chạy thật (dự kiến cả tháng), tỷ lệ bệnh nhân đồng ý.

Kiểm thử
========
``--test-tags /dmag_ai_insights``: giả lập trả đúng số của bộ máy chỉ số; chạy thật với client giả (vòng gọi công cụ,
công cụ strict, không ``tool_choice``); bản tin (giả lập, thật với JSON schema, tác vụ định kỳ); phát hiện bất thường
trên dữ liệu mẫu cố định + luồng duyệt; dự báo tất định; Trung tâm AI đủ 20 tính năng, trạng thái và lọc theo vai trò.
