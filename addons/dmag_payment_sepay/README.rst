=====================================
DMAG – Thu tiền SePay & chốt két
=====================================

Thu tiền tại quầy lễ tân bằng **VietQR động qua SePay** (sepay.vn), tiền mặt hoặc quẹt thẻ;
webhook SePay tự gạch nợ lượt khám; hàng chờ đối soát cho giao dịch không khớp; nhật ký thu
tiền theo phương thức và **biên bản chốt két 4 bước**.

Chức năng
=========

* ``dmag.sepay.config`` – cấu hình mỗi phòng khám: ngân hàng (mã ngắn SePay), số tài khoản, chủ
  tài khoản, API key webhook (chỉ Giám đốc / quản trị đọc được), tiền tố mã thanh toán, dung sai,
  hiệu lực mã QR, mẫu ảnh QR, múi giờ giao dịch.
* ``dmag.payment.request`` – Yêu cầu thanh toán: mã duy nhất ``<tiền tố><8 ký tự>`` (vd.
  ``DMAGK7Q2M9XA``) dùng làm nội dung chuyển khoản, ảnh QR, trạng thái
  Chờ thanh toán / Một phần / Đã thanh toán / Hết hạn / Đã hủy. Lễ tân tạo được, **không sửa được
  số tiền** (chỉ Giám đốc).
* ``dmag.sepay.transaction`` – lưu nguyên payload mỗi lần webhook gọi, idempotent theo ``id`` SePay
  (gửi lại → bản ghi ``Trùng lặp``), không xóa (chỉ Giám đốc).
* ``dmag.payment.log`` – mỗi lần ``visit.register_payment()`` ghi một dòng (phương thức, số tiền,
  người thu, nguồn: tại quầy / SePay / đối soát thủ công) – nguồn số liệu chốt két.
* Wizard **Đối soát thủ công** (Quản lý, Giám đốc, Kế toán): chọn lượt khám / yêu cầu → gạch nợ.
* ``dmag.cash.closing`` – **Chốt két 4 bước**:

  1. *Số liệu hệ thống*: gom các khoản thu & giao dịch SePay trong ngày chưa thuộc biên bản nào
     (ca trước đã chốt thì ca sau chỉ nhận phần còn lại).
  2. *Kiểm đếm*: lễ tân nhập tiền đầu ca, tiền mặt đếm thực tế, tổng phiếu POS → **Lễ tân ký bàn giao**.
  3. *Xác nhận*: **Thu ngân ký nhận** (người khác lễ tân) rồi **Quản lý xác nhận** (bắt buộc giải
     trình nếu có chênh lệch).
  4. *Khóa sổ*. Sau bước 3 chỉ Giám đốc sửa / mở lại. In "Biên bản chốt két" (QWeb PDF).

  Chênh lệch: tiền mặt = đếm – (đầu ca + thu tiền mặt); thẻ = phiếu POS – thu thẻ;
  chuyển khoản = SePay báo có – thu chuyển khoản trên hệ thống.

Menu: *Nha khoa → Thu ngân* (Yêu cầu thanh toán, Hàng chờ xử lý, Giao dịch SePay, Nhật ký thu tiền,
Chốt két); *Nha khoa → Cấu hình → SePay (chuyển khoản QR)* (Quản lý).

Cài đặt phía SePay
==================

1. Đăng ký my.sepay.vn, liên kết tài khoản ngân hàng nhận tiền của phòng khám.
2. Trong Odoo: *Nha khoa → Cấu hình → SePay* – nhập mã ngân hàng (vd. ``MBBank``), số tài khoản,
   chủ tài khoản, tiền tố (mặc định ``DMAG``), API key (chuỗi ngẫu nhiên dài, tự đặt).
3. Tại SePay → *Webhooks → Thêm webhook*:

   * URL: ``https://<tên-miền>/dmag/sepay/webhook``
   * Sự kiện: *Có tiền vào* (giao dịch tiền ra nếu có gửi cũng bị bỏ qua).
   * Kiểu chứng thực: **API Key** – nhập đúng khóa đã lưu ở Odoo. SePay gửi header
     ``Authorization: Apikey <khóa>``.
   * Nên khai báo *Cấu trúc mã thanh toán* với tiền tố giống Odoo để SePay điền trường ``code``.
4. Odoo phải xác định được database khi không có phiên đăng nhập: chạy với ``--db-filter`` /
   ``dbfilter`` khớp đúng 1 database (hoặc ``db_name``). Nếu không, webhook trả 404.

Webhook
-------

``POST /dmag/sepay/webhook`` (body JSON). Phản hồi:

* ``200 {"success": true}`` – đã ghi nhận (kể cả khi không khớp → vào hàng chờ, hoặc trùng lặp).
* ``401 {"success": false}`` – sai / thiếu API key (không lưu gì).
* ``400`` – body không phải JSON object.

Xử lý: so khớp API key thời gian hằng → bỏ qua ``transferType != "in"`` → idempotent theo ``id`` →
đọc mã từ ``code`` / ``content`` / ``description`` (regex ``<TIỀN TỐ>[A-Z0-9]{8}``, không phân biệt
hoa thường, chịu được khoảng trắng chèn giữa) → tìm yêu cầu cùng phòng khám → gạch nợ tối đa số
còn phải thu bằng ``visit.register_payment('transfer', số_tiền, reference=mã)`` với quyền hệ thống.
Chuyển thiếu → yêu cầu "Một phần"; chuyển thừa / không có mã / lượt khám đã trả đủ / lỗi →
``needs_review`` (Hàng chờ xử lý). Yêu cầu đã hết hạn vẫn được gạch nợ nếu lượt khám còn nợ.

API cho giao diện lễ tân
========================

* ``dmag.dental.visit.get_payment_qr(amount=False)`` → ``{request_id, code, amount, qr_url, bank,
  account_number, account_name, content, expiry, state}``. Tự lập + ghi sổ hóa đơn nếu
  ``payment_status == 'to_invoice'``; dùng lại yêu cầu đang chờ cùng số tiền, hủy yêu cầu chờ cũ khác số tiền.
* ``dmag.payment.request.get_status()`` → ``{request_id, code, state, amount, paid_amount, residual,
  visit_id, visit_payment_status, visit_amount_due}``.
* ``dmag.payment.request.action_cancel()``.
* ``dmag.dental.visit.register_payment(method, amount, reference)`` (lõi) – tiền mặt / thẻ; module này
  ghi thêm nhật ký thu tiền.

Thông báo bus (realtime)
------------------------

* Kênh: ``(res.company, 'dmag_payment')`` – người dùng thuộc nhóm Lễ tân trở lên được **tự động**
  đăng ký kênh của các phòng khám mình được phép (override ``ir.websocket._build_bus_channel_list``),
  client không cần ``addChannel``.
* Loại thông báo: ``dmag_payment/update``. Ở OWL::

    busService.subscribe("dmag_payment/update", (payload) => { ... });

* Payload: ``{event: 'received' | 'unmatched', request_id, code, state, amount, paid_amount, residual,
  visit_id, visit_payment_status, visit_amount_due, transaction_id, transaction_amount, message}``
  (sự kiện ``unmatched`` chỉ có ``transaction_id, transaction_amount, message, request_id, visit_id``).

Phân quyền
==========

* Lễ tân: tạo yêu cầu thanh toán, xem giao dịch, tạo / kiểm đếm / ký chốt két.
* Quản lý: cấu hình SePay (trừ API key), hàng chờ & đối soát thủ công, xác nhận và khóa sổ chốt két.
* Kế toán (``account.group_account_invoice``): xem, đối soát thủ công.
* Giám đốc: đọc / sửa API key, sửa số tiền yêu cầu, sửa / xóa giao dịch, mở lại biên bản chốt két.
* Record rule theo ``company_id`` cho mọi model.

Cần xác nhận
============

* Tên trường payload SePay đang dùng: ``id, gateway, transactionDate ("YYYY-MM-DD HH:MM:SS", giờ VN),
  accountNumber, subAccount, code, content, transferType ("in"/"out"), transferAmount, accumulated,
  referenceCode, description`` – đối chiếu developer.sepay.vn (mục Webhooks).
* Header chứng thực ``Authorization: Apikey <key>`` (mã cũng chấp nhận ``Bearer <key>`` và
  ``Bearer Apikey <key>``).
* Định dạng ảnh QR: ``https://qr.sepay.vn/img?acc=<STK>&bank=<mã ngân hàng>&amount=<số>&des=<nội dung>&template=compact``
  – địa chỉ và mẫu có thể đổi trong cấu hình; kiểm tra mã ngân hàng đúng danh sách của SePay.
* SePay coi phản hồi HTTP 200/201 kèm ``{"success": true}`` là thành công, ngoài ra gửi lại
  (tối đa ~7 lần) – đã idempotent theo ``id``.
* Ngân hàng có thể cắt / chèn ký tự vào nội dung chuyển khoản; mã 8 ký tự không dấu đã được chọn
  để chịu được điều này, cần thử thực tế với ngân hàng của phòng khám.
* Dung sai: chỉ dùng để xếp trạng thái yêu cầu "Đã thanh toán"; phần thiếu vẫn còn nợ trên hóa đơn.
