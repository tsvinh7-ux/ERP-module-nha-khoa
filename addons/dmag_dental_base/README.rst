DMAG Dental – Nền tảng
======================

Lõi dữ liệu nha khoa của DMAG Dental ERP.

* Danh mục răng FDI (vĩnh viễn 11–48, răng sữa 51–85), mặt răng, tình trạng răng.
* Danh mục chẩn đoán ICD-10 nhóm K00–K14.
* Hồ sơ bệnh nhân trên Liên hệ: mã BN, CCCD, tiền sử, dị ứng, cảnh báo y khoa, nguồn khách, gia đình.
* Ghế nha theo phòng khám.
* **Lịch làm việc phòng khám** (``dmag.clinic.schedule``, *Nha khoa › Cấu hình › Phòng khám › Lịch làm việc*): theo
  phòng khám, mỗi thứ mở / nghỉ với một hoặc nhiều ca (mặc định **mở cửa cả tuần – Thứ 2 – Chủ nhật** 08:00–12:00,
  13:30–20:00; quyết định 11/10/2026: Chủ nhật vẫn làm và đông khách nhất), danh sách ngày nghỉ lễ / nghỉ đột xuất (mẫu ngày lễ 2026 ghi **[CẦN XÁC MINH]**),
  bước khung giờ đặt lịch, chế độ đặt ngoài giờ (chặn – chỉ Quản lý trở lên / chỉ cảnh báo); bác sĩ có thể khai **ngày
  làm việc riêng** (``work_weekday_ids``). Đây là nguồn duy nhất cho: giờ trống đặt lịch và kiểm tra đặt lịch ngoài giờ
  (``dmag_dental_clinic`` / ``dmag_clinic_workspace``), gợi ý xếp lịch AI-11 và trợ lý Zalo AI-07
  (``dmag_ai_customer``), số ngày làm việc / nhịp độ và công suất ghế (``dmag_dental_goals``, ``dmag_okr_dental``), dự
  báo AI-16 (``dmag_ai_insights``), dữ liệu demo. API Python: ``env['dmag.clinic.schedule'].get_info(company)`` →
  ``ScheduleInfo`` (``shifts(day)``, ``is_open_day``, ``open_days``, ``count_open_days``, ``check_interval``,
  ``chair_utilization``, ``weekly_text``…); RPC ``get_day_info(date)``.
* **Lịch nghỉ luân phiên** (``dmag_staff_rotation.py``; *Cấu hình › Phòng khám › Nhân sự luân phiên / Nghỉ phép – đổi
  ca*, màn hình lịch tháng ở ``dmag_clinic_workspace``): mỗi bác sĩ / phụ tá / lễ tân một ngày nghỉ hằng tuần vào ngày
  thường (mặc định Thứ 2 – Thứ 6; không cho nghỉ Chủ nhật trừ khi bật "Cho phép nghỉ Chủ nhật"; tùy chọn xoay vòng mỗi
  tuần). Nút **"Xếp lịch nghỉ luân phiên tự động"** (Quản lý) chia ngày nghỉ vòng tròn, giữ số người trực tối thiểu cấu hình
  trên Lịch làm việc (mặc định ≥ 2 bác sĩ, ≥ 1 lễ tân, ≥ 1 phụ tá mỗi nhóm 4 ghế); thiếu người → cảnh báo. Nghỉ phép /
  đổi ca (``dmag.staff.leave``): nhân viên tạo yêu cầu cho chính mình, **Quản lý duyệt** (hiện trước "nếu duyệt sẽ thiếu
  người"), đã duyệt chỉ Giám đốc sửa. ``RosterInfo`` gắn vào ``ScheduleInfo.roster``; ``practitioner.off_reason(day)``,
  ``works_on``, ``duty_days``, ``duty_text`` → giờ trống, cảnh báo đặt lịch, AI-11, AI-07, nhịp mục tiêu từng bác sĩ,
  người nhận thông báo của trợ lý (``on_duty_users``), dữ liệu demo. RPC ``get_month_roster(month)``.
* Nhân sự lâm sàng: bậc lâm sàng, phạm vi hành nghề, giấy phép hành nghề, cảnh báo hết hạn.
* Dịch vụ nha khoa: thời lượng, độ nặng ca, phạm vi/bậc yêu cầu, bảo hành, nhắc tái khám.
* Nhóm quyền: Lễ tân/Thu ngân, Phụ tá, Bác sĩ, Quản lý phòng khám.
