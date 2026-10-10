DMAG Dental – Vận hành phòng khám
=================================

* Lượt khám = một chặng trong hành trình khách hàng: Đặt lịch → Xác nhận → Check-in → Lên ghế → Hoàn tất;
  đo thời gian chờ, đánh dấu khách mới, điểm móc ``_dmag_journey_event`` cho Zalo ZNS / CSKH.
* Luật xếp lịch: chặn trùng ghế; không xếp chồng 2 ca "nặng" của cùng bác sĩ; chặn dịch vụ ngoài
  phạm vi hành nghề / dưới bậc lâm sàng / giấy phép hết hạn.
* Bệnh án lượt khám (SOAP, ICD-10, điểm đau). Bác sĩ ký → khóa; Quản lý mở bổ sung có ghi vết.
  Điểm móc ``_dmag_esign_request`` cho chữ ký số Viettel MySign.
* Sơ đồ răng theo lớp Hiện trạng / Kế hoạch / Đã điều trị.
* Kế hoạch điều trị nhiều phương án (trả góp, đặt cọc), cầu chì y đức: dịch vụ đánh dấu
  "Cần bác sĩ thứ hai duyệt" phải được bác sĩ khác duyệt trước khi bệnh nhân chọn.
* Phương án được chọn sinh hợp đồng (đơn bán). Thủ thuật hoàn tất cập nhật sơ đồ răng, đánh dấu dòng kế hoạch
  và ghi "số lượng đã thực hiện" → chỉ xuất hóa đơn phần đã làm (thu theo tiến độ).
* Dịch vụ nha khoa mặc định không chịu thuế GTGT (dịch vụ khám chữa bệnh) – kiểm tra lại với kế toán.
* Báo cáo "Bản tóm tắt kế hoạch điều trị".
