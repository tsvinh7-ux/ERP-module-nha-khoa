DMAG – Zalo ZNS
===============

Gửi tin Zalo Notification Service (ZNS) cho phòng khám, có lớp chuyển tiếp (adapter) để sau này
ủy quyền cho module ``biz_zalo`` / ``biz_zalo_zns`` của Bizapps.

Chức năng
---------
* **Cấu hình theo phòng khám** (Thiết lập › Công ty › tab *Zalo ZNS*): OA ID, App ID, App Secret,
  access token, refresh token, thời điểm hết hạn (trường mật – chỉ Quản trị hệ thống / Giám đốc thấy).
  Chế độ gửi:

  - ``mock``: giả lập, không gửi thật (mặc định – dùng thử, kiểm thử);
  - ``live``: gọi trực tiếp Zalo Business API;
  - ``bizapps``: gọi hàm trên model ``biz.zalo.zns`` nếu có (``self.env.get('biz.zalo.zns')``), không có thì báo lỗi.

* **Làm mới token OAuth v4**: ``POST https://oauth.zaloapp.com/v4/oa/access_token``, header ``secret_key``,
  form ``refresh_token``, ``app_id``, ``grant_type=refresh_token``. Refresh token chỉ dùng một lần nên được lưu
  ngay sau khi làm mới. Cron mỗi giờ làm mới token sắp hết hạn; nút "Làm mới access token" trên công ty.
* **Danh mục mẫu** ``dmag.zns.template``: Template ID do Zalo cấp, mã nội bộ, điểm chạm hành trình, tin giao dịch,
  nội dung xem trước, bảng ánh xạ tham số ``tên tham số Zalo → biểu thức``. Biểu thức không dùng ``eval``:
  ``patient.name``, ``visit.scheduled_start|time``, ``visit.scheduled_start|date``, ``company.name``,
  ``visit.doctor_id.name || 'Bác sĩ'``. Bộ lọc: ``time, date, datetime, upper, lower, title, money, int, first,
  join, firstname``. Giờ hiển thị theo múi giờ của khách → của phòng khám → Asia/Ho_Chi_Minh.
* **API gửi**::

    message = env['dmag.zns.message'].send(
        'booking_confirm',          # mã mẫu, id hoặc bản ghi dmag.zns.template
        partner,                    # người nhận (res.partner)
        record=visit,               # bản ghi nguồn → biến visit / record
        params_override={'x': 'y'}, # ghi đè tham số
        variables={'nps': resp},    # biến bổ sung cho biểu thức
        send_now=False,             # True: gửi ngay nếu ngoài giờ yên lặng
        expire_at=False,            # quá hạn chưa gửi được → hủy
    )

  Trả về ``dmag.zns.message`` (``queued`` / ``skipped`` / ``sent`` / ``delivered`` / ``failed`` / ``cancel``),
  số chuẩn hóa ``84xxxxxxxxx`` (ưu tiên *SĐT Zalo*, rồi di động), tham số JSON, ``tracking_id``, ``msg_id``, lỗi.
* **Hàng đợi + cron** (5 phút) gửi ``POST https://business.openapi.zalo.me/message/template``
  (header ``access_token``; JSON ``phone, template_id, template_data, tracking_id`` – thêm ``mode: development``
  khi bật chế độ development). Lỗi mạng / lỗi tạm thời: thử lại lũy tiến (5, 10, 20 phút…) tối đa *Số lần thử lại*;
  lỗi không thử lại (số không có Zalo…) → ``failed`` ngay; lỗi token → làm mới token và gửi lại một lần.
* **Giờ yên lặng** 21:00–07:00 (cấu hình được): tin không phải *giao dịch* được dời đến hết giờ yên lặng.
* **Từ chối nhận tin**: ``res.partner.zns_opt_out`` – không gửi (tin ghi ``skipped``), kể cả tin đã xếp hàng.
* **Webhook** ``POST /dmag/zalo/webhook`` (hoặc ``/dmag/zalo/webhook/<mã định danh>`` khi nhiều OA): lưu nguyên văn
  vào ``dmag.zns.webhook.event``, cập nhật ``user_received_message`` → ``delivered``, ``user_feedback`` → phản hồi
  của khách (điểm móc ``_dmag_on_feedback``). Nếu nhập *OA Secret Key*, kiểm tra header
  ``X-ZEvent-Signature: mac=sha256(appId + body + timeStamp + OASecretKey)``; sai chữ ký → HTTP 401, vẫn lưu nhật ký.
* Nhật ký tin và webhook **chỉ đọc**; chỉ Giám đốc được sửa / xóa. Quản lý được "Gửi lại" / "Hủy tin".

Cần xác nhận
------------
* **Mẫu ZNS phải được đăng ký và Zalo duyệt** (nội dung, tham số, kiểu & độ dài tham số, nút "Đổi lịch" / "Bản đồ")
  trước khi gửi thật; nhập Template ID vào từng mẫu. Mẫu seed để trống Template ID.
* Tên endpoint / payload theo tài liệu Zalo hiện hành: ``/v4/oa/access_token`` (header ``secret_key``),
  ``business.openapi.zalo.me/message/template`` (header ``access_token``, các khóa ``phone``, ``template_id``,
  ``template_data``, ``tracking_id``), thời hạn access token (``expires_in``) và bảng mã lỗi (danh sách lỗi không
  thử lại trong ``NON_RETRYABLE_ERRORS``; lỗi token ``-124``, ``-216``). Không tìm được trang tài liệu chính thức
  để đối chiếu khi viết module – chỉ có SDK/đối tác bên thứ ba.
* Công thức chữ ký webhook ``X-ZEvent-Signature`` và tên sự kiện ZNS (``user_received_message``, ``user_feedback``).
* **Chế độ Bizapps**: tên model ``biz.zalo.zns`` và tên hàm gửi (mặc định ``send_zns_template`` – cấu hình được),
  chữ ký hàm (đang gọi với ``phone, template_id, template_data, tracking_id``) và dạng kết quả trả về.
* Chính sách giờ yên lặng và loại mẫu được xem là "giao dịch" theo quy định ZNS / Nghị định 13/2023 về dữ liệu cá nhân.
