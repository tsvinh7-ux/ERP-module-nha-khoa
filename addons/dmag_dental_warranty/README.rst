DMAG – Thẻ bảo hành
===================

Thẻ bảo hành điện tử cho implant, răng sứ, chỉnh nha…

* Thêm "Điều kiện bảo hành" trên dịch vụ (cạnh "Bảo hành (tháng)").
* Hoàn tất thủ thuật có ``warranty_months > 0`` (ghi đè ``action_done`` qua ``super()``) → tự sinh
  ``dmag.warranty.card``: mã thẻ ``BHyy…``, bệnh nhân, thủ thuật, dịch vụ, răng, ngày bắt đầu / hết hạn,
  điều kiện; liên kết mềm số phiếu labo (``dmag_dental_lab``) và serial implant (``dmag_dental_stock``) nếu có cài.
* Thẻ **khóa sau khi tạo**: chỉ quy trình (hết hạn, bảo hành) đổi trạng thái; chỉ Giám đốc sửa / vô hiệu (có lý do).
* Yêu cầu bảo hành ``dmag.warranty.claim``: lễ tân tiếp nhận, bác sĩ kết luận "Được bảo hành / Không thuộc
  bảo hành" (bắt buộc giải thích), tạo lượt khám bảo hành 1 chạm. Đã kết luận → khóa.
* Cron hằng ngày: chuyển thẻ quá hạn sang "Hết hạn", tạo việc nhắc cho thẻ sắp hết hạn trong 30 ngày.
  Điểm móc cho ZNS: ``dmag.warranty.card._dmag_warranty_expiring(days=30, company_id=False)`` trả recordset thẻ;
  ``_dmag_warranty_expiry_notify()`` (ghi đè bằng ``super()`` ở module hành trình).
* Mẫu in "Thẻ bảo hành" cỡ thẻ ngân hàng 85,6 × 54 mm, màu DMAG (#11346A / #178BEC), mặt sau in điều kiện.
* Nút "Bảo hành" trên hồ sơ bệnh nhân.

Cần xác nhận
------------

* Ngày bắt đầu bảo hành = ngày hoàn tất thủ thuật (hay ngày gắn phục hình / thanh toán đủ?).
* Sau một lần "Được bảo hành" thẻ chuyển "Đã bảo hành" – có tiếp tục bảo hành cho lần sau (giới hạn số lần)?
* Bảo hành có điều kiện tái khám định kỳ: có tự vô hiệu khi bệnh nhân bỏ tái khám quá X tháng?
* Thời điểm nhắc trước hạn (đang 30 ngày) và nội dung ZNS.
* Thẻ hiển thị trên Cổng bệnh nhân (``dmag_patient_portal``) – module portal đọc ``res.partner.warranty_card_ids``.
