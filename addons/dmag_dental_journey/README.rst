DMAG – Hành trình khách hàng Trước–Trong–Sau
============================================

Tự động hóa các điểm chạm trong bảng "Hành trình khách hàng" (Đề xuất – mục 5.1) bằng Zalo ZNS
(module ``dmag_zalo_zns``) và bảng việc CSKH.

Luật hành trình (``dmag.journey.rule``)
---------------------------------------
* **Kích hoạt**: sự kiện lượt khám (``booked, confirmed, arrived, in_chair, done, cancelled, no_show, signed, paid``
  – kế thừa ``dmag.dental.visit._dmag_journey_event`` và gọi ``super()``) hoặc theo thời gian (cron 15 phút):
  trước giờ hẹn X giờ, sau khi hoàn tất X giờ, đến hạn tái khám (``product.recall_months``), sinh nhật,
  sắp hết bảo hành (``product.warranty_months``; module thẻ bảo hành có thể ghi đè ``_dmag_warranty_due``).
* **Điều kiện**: domain trên lượt khám, phạm vi dịch vụ (mọi lượt / có thủ thuật / chỉ khám-chụp phim),
  chỉ ca xâm lấn (ca nặng / Phẫu thuật / Implant), chỉ khách mới, phòng khám.
* **Hành động**: gửi ZNS, giao việc "Gọi CSKH" cho Nhân viên CSKH / Trưởng CSKH / bác sĩ / người đặt lịch, hoặc cả hai.
* **Chống trùng**: ``dmag.journey.execution`` (unique luật + khóa: ``visit:<id>``, ``visit:<id>:<giờ hẹn>`` – đổi giờ
  hẹn thì nhắc lại, ``recall:<lượt>:<dịch vụ>``, ``birthday:<khách>:<năm>``, ``warranty:<thủ thuật>``).
  Lỗi hành trình không bao giờ chặn nghiệp vụ phòng khám (savepoint + ghi nhật ký ``error``).
* Hủy lịch / không đến → các tin nhắc lịch còn chờ bị hủy; tin nhắc lịch hết hạn tại giờ hẹn.

Luật mặc định (seed, có thể sửa)
--------------------------------
=================  =============================================================  ==========================
Giai đoạn          Điểm chạm                                                       Hành động
=================  =============================================================  ==========================
Trước khi đến      Đặt lịch thành công                                             ZNS xác nhận (giao dịch)
Trước khi đến      Trước 1 ngày – lượt khám                                        ZNS nhắc lịch
Trước khi đến      Trước 1 ngày – ca thủ thuật                                     ZNS nhắc + video "không đau"
Trước khi đến      Trước 2 giờ                                                     ZNS nhắc + khai báo sức khỏe
Trước khi đến      Không đến                                                       Việc gọi lại (giờ chiều)
Trong              Check-in                                                        ZNS chào mừng (giao dịch)
Sau khi về         Hoàn tất                                                        ZNS cảm ơn + "Nội dung khám hôm nay"
Sau khi về         +24 giờ, ca xâm lấn                                             Việc gọi hỏi điểm đau
Sau khi về         +48 giờ                                                         ZNS NPS 1 câu
Sau khi về         Đến hạn tái khám (báo trước 7 ngày)                             ZNS + việc CSKH
Sau khi về         Sinh nhật                                                       ZNS lời chúc
Sau khi về         Bảo hành sắp hết (trước 30 ngày)                                ZNS nhắc
=================  =============================================================  ==========================

Link "Nội dung khám hôm nay" = ``visit.dmag_portal_url`` nếu module cổng bệnh nhân có trường này, ngược lại
website phòng khám (``visit.dmag_journey_today_url``). Video "quy trình không đau", link khai báo sức khỏe,
link đánh giá Google, lời mời giới thiệu, Nhân viên CSKH / Trưởng CSKH cấu hình ở Công ty › tab *Chăm sóc khách hàng*.

NPS và điểm đau
---------------
* ``dmag.nps.response``: bệnh nhân, lượt khám, điểm 0–10, góp ý, kênh, ngày; trang công khai
  ``/dmag/nps/<token>`` (di động, hết hạn 30 ngày, trả lời một lần). Điểm ≤ 6 → phiếu phàn nàn (việc
  "Phàn nàn khách hàng" cho Trưởng CSKH); 9–10 → mời đánh giá Google + mã giới thiệu (mã bệnh nhân).
* Điểm đau sau 24h: nút "Ghi điểm đau 24h" trên lượt khám (``record_pain_score_24h(score, note)``) →
  ``pain_score_24h``; điểm ≥ 7 tự giao việc cho bác sĩ.

Bảng việc & bảng điều khiển
---------------------------
* Nha khoa › Chăm sóc khách hàng › *Bảng việc CSKH*: danh sách / kanban việc "Gọi CSKH" và "Phàn nàn",
  lọc Hôm nay / Quá hạn / Của tôi, nút Mở hồ sơ / Xong.
* ``dmag.dental.visit.get_journey_dashboard(date_from=False, date_to=False)`` (mặc định 30 ngày) trả về::

    {'period': {'from', 'to'},
     'visits': {'total', 'booked', 'showed', 'no_show', 'cancelled'},
     'show_up_rate': %, 'no_show_rate': %,
     'nps': {'score', 'responses', 'promoters', 'passives', 'detractors', 'complaints_open'},
     'recall_due': int,
     'messages': {'queued', 'sent', 'delivered', 'failed', 'skipped', 'cancel', 'total'},
     'call_tasks': {'today', 'overdue', 'planned'}}

  Hiển thị ở *Bảng điều khiển hành trình* (OWL).

Phân quyền: lễ tân xem luật / nhật ký / NPS và làm việc CSKH; Quản lý cấu hình luật, mẫu; nhật ký điểm chạm và câu
trả lời NPS chỉ đọc (chỉ Giám đốc xóa – xóa nhật ký để cho phép chạy lại điểm chạm).

Cần xác nhận
------------
* Mỗi mẫu ZNS seed phải được **đăng ký và Zalo duyệt**, sau đó nhập Template ID; tên tham số trong bảng ánh xạ phải
  trùng tham số đã duyệt (độ dài tối đa theo kiểu tham số).
* Mẫu nào được coi là "giao dịch" (gửi cả giờ yên lặng): hiện là *Xác nhận đặt lịch* và *Chào mừng check-in*.
* Nhắc lịch D-1 hiện tính đúng 24 giờ trước giờ hẹn (không gửi nếu đặt lịch sát giờ) – có thể đổi thành "khung giờ cố
  định ngày hôm trước".
* Quà sinh nhật theo hạng, doanh thu từ khách giới thiệu, CAC theo kênh: do module loyalty / CRM bổ sung.
* Thẻ bảo hành điện tử: khi có module bảo hành, ghi đè ``_dmag_warranty_due`` để dùng ngày hết hạn trên thẻ.
