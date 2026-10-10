=====================================
DMAG – Thủ thuật phí & hoa hồng
=====================================

Thủ thuật phí bác sĩ / phụ tá, hoa hồng tư vấn viên, lễ tân, telesale, người giới thiệu –
**chỉ tính trên tiền thực thu**.

Quy tắc (``dmag.commission.rule``)
==================================
* Vai trò: bác sĩ, phụ tá, tư vấn viên, lễ tân, telesale, người giới thiệu.
* Phạm vi: mọi dịch vụ / nhóm dịch vụ nha khoa / nhóm sản phẩm / dịch vụ cụ thể (cụ thể hơn thắng,
  sau đó theo thứ tự).
* Cách tính: % thực thu (gồm thuế) · % doanh thu chưa thuế đã thu · cố định mỗi thủ thuật ·
  lũy tiến theo thực thu tháng của người hưởng.
* Quy tắc mẫu được nạp ở trạng thái **tắt** – Giám đốc xác nhận tỷ lệ rồi bật.

Người hưởng
===========
Bác sĩ / phụ tá: trên thủ thuật · Tư vấn viên: trên kế hoạch điều trị (hoặc lượt khám) ·
Lễ tân: người check-in (tự ghi, sửa được) · Telesale: trên lượt khám hoặc hồ sơ bệnh nhân ·
Người giới thiệu: ``referrer_id`` của bệnh nhân.

Cơ chế
======
* Sinh dòng khi thu tiền (``_dmag_journey_event('paid')``) và khi có đối trừ / bỏ đối trừ / hóa đơn
  điều chỉnh / đưa hóa đơn về nháp (``account.move.line.reconcile``, ``remove_move_reconcile``,
  ``account.move._post`` cho hóa đơn điều chỉnh, ``button_draft``). Nút *Tính lại theo thực thu*
  trên lượt khám.
* Phần đã thu của mỗi thủ thuật = phần hóa đơn được trả bằng tiền (bút toán thanh toán) trừ phần
  hóa đơn điều chỉnh giảm phải hoàn khách, phân bổ theo dòng đơn bán của thủ thuật.
* **Idempotent**: số phải hưởng lũy kế − tổng đã ghi = chênh lệch → dòng dương / dòng âm (đảo).
* **Cầu chì y đức**: thủ thuật cần bác sĩ thứ hai duyệt mà kế hoạch chưa duyệt (hoặc làm ngoài kế
  hoạch), hoặc lượt khám có cờ ``dmag_complaint`` (nếu module hành trình có) → mọi dòng hợp lệ của
  thủ thuật chuyển *Hủy – cầu chì y đức*, ghi lý do và ghi chatter lượt khám.
* Bảng kê tháng theo người hưởng (wizard *Lập bảng kê tháng*); đã chốt → chỉ Giám đốc sửa.
* Nguồn P3 cho ``dmag_hr_3p``: ``dmag.commission.line._dmag_amount_for_employee(employee, from, to)``.

Phân quyền
==========
Nhân viên (lễ tân trở lên) chỉ xem dòng / bảng kê của mình (record rule); Quản lý xem tất cả;
chỉ Giám đốc sửa / xóa dòng hoa hồng và quy tắc.

Cần xác nhận
============
* Tỷ lệ chuẩn từng vai trò (bác sĩ, phụ tá, tư vấn, lễ tân sản phẩm 8–10% / chốt dịch vụ 1–2%,
  telesale, người giới thiệu) và nhóm dịch vụ áp dụng.
* Cơ sở tính: gồm thuế hay chưa thuế; có trừ chi phí labo / vật tư trước khi tính thủ thuật phí không.
* Hoa hồng đã chốt bảng kê / đã trả lương mà sau đó bị đảo hoặc hủy (cầu chì): trừ vào kỳ sau?
* Lễ tân hưởng theo người check-in hay người thu tiền; người giới thiệu ngoài hệ thống được trả thế nào.
* Danh sách vi phạm y đức kích hoạt cầu chì (ngoài 2 trường hợp hiện có).
