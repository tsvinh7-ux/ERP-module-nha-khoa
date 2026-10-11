DMAG Dental – Nền tảng
======================

Lõi dữ liệu nha khoa của DMAG Dental ERP.

* Danh mục răng FDI (vĩnh viễn 11–48, răng sữa 51–85), mặt răng, tình trạng răng.
* Danh mục chẩn đoán ICD-10 nhóm K00–K14.
* Hồ sơ bệnh nhân trên Liên hệ: mã BN, CCCD, tiền sử, dị ứng, cảnh báo y khoa, nguồn khách, gia đình.
* Ghế nha theo phòng khám.
* **Lịch làm việc phòng khám** (``dmag.clinic.schedule``, *Nha khoa › Cấu hình › Phòng khám › Lịch làm việc*): theo
  phòng khám, mỗi thứ mở / nghỉ với một hoặc nhiều ca (mặc định Thứ 2 – Thứ 7 08:00–12:00, 13:30–20:00; Chủ nhật nghỉ –
  đúng số ngày làm việc trước đây), danh sách ngày nghỉ lễ / nghỉ đột xuất (mẫu ngày lễ 2026 ghi **[CẦN XÁC MINH]**),
  bước khung giờ đặt lịch, chế độ đặt ngoài giờ (chặn – chỉ Quản lý trở lên / chỉ cảnh báo); bác sĩ có thể khai **ngày
  làm việc riêng** (``work_weekday_ids``). Đây là nguồn duy nhất cho: giờ trống đặt lịch và kiểm tra đặt lịch ngoài giờ
  (``dmag_dental_clinic`` / ``dmag_clinic_workspace``), gợi ý xếp lịch AI-11 và trợ lý Zalo AI-07
  (``dmag_ai_customer``), số ngày làm việc / nhịp độ và công suất ghế (``dmag_dental_goals``, ``dmag_okr_dental``), dự
  báo AI-16 (``dmag_ai_insights``), dữ liệu demo. API Python: ``env['dmag.clinic.schedule'].get_info(company)`` →
  ``ScheduleInfo`` (``shifts(day)``, ``is_open_day``, ``open_days``, ``count_open_days``, ``check_interval``,
  ``chair_utilization``, ``weekly_text``…); RPC ``get_day_info(date)``.
* Nhân sự lâm sàng: bậc lâm sàng, phạm vi hành nghề, giấy phép hành nghề, cảnh báo hết hạn.
* Dịch vụ nha khoa: thời lượng, độ nặng ca, phạm vi/bậc yêu cầu, bảo hành, nhắc tái khám.
* Nhóm quyền: Lễ tân/Thu ngân, Phụ tá, Bác sĩ, Quản lý phòng khám.
