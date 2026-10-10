DMAG – Tài khoản bệnh nhân
==========================

Cổng bệnh nhân (chỉ dựa trên ``portal``, không cần ``website``), trang đặt lịch trực tuyến và API JSON
cho ứng dụng di động. Giao diện mobile-first, màu DMAG (navy ``#11346A`` / xanh ``#178BEC``), tiếng Việt.

Trang cổng
----------

==============================  ==========  ===============================================================
Đường dẫn                       Quyền       Nội dung
==============================  ==========  ===============================================================
``/my/dental``                  đăng nhập   Lịch hẹn sắp tới, hạng & điểm, thao tác nhanh, lần khám gần đây
``/my/dental/visits``           đăng nhập   Danh sách lượt khám (lọc ``?patient_id=``)
``/my/dental/visit/<id>``       đăng nhập   "Nội dung khám hôm nay": ngày, bác sĩ, chẩn đoán, việc đã làm,
                                hoặc token  lời dặn + ``aftercare_note`` của dịch vụ, đơn thuốc (nếu có
                                            ``dmag.prescription``), lịch hẹn tiếp, chi phí / thanh toán
``/my/dental/plans``            đăng nhập   Kế hoạch điều trị: phương án, khuyến nghị, trả góp, tiến độ
``/my/dental/warranty``         đăng nhập   Thẻ bảo hành (nếu có ``dmag.warranty.card``)
``/my/dental/loyalty``          đăng nhập   Hạng, điểm, tiến độ lên hạng, voucher, gói chăm sóc, gia đình
``/dental/booking``             công khai   Đặt lịch trực tuyến
==============================  ==========  ===============================================================

**Phạm vi xem**: người dùng cổng chỉ thấy *chính mình*, *thành viên gia đình khi là chủ hộ*
(``dmag.patient.family.head_id``) và *người mình giám hộ* (``guardian_id``). Nhóm Portal **không** được cấp
quyền đọc trực tiếp dữ liệu y khoa; controller kiểm tra phạm vi rồi đọc bằng quyền hệ thống.

**Link chia sẻ**: ``visit.dmag_portal_url`` (trường tính toán) = ``/my/dental/visit/<id>?access_token=…``,
không cần đăng nhập, hiệu lực 30 ngày kể từ khi cấp; hết hạn thì lần đọc sau cấp token mới (link cũ vô hiệu).
Module ``dmag_dental_journey`` dùng trường này cho tin ZNS "Cảm ơn + Nội dung khám hôm nay".

Đặt lịch trực tuyến
-------------------

Form: họ tên, số điện thoại (Zalo), ngày + giờ mong muốn, dịch vụ, chi nhánh, ghi chú, **ô đồng ý xử lý dữ liệu
cá nhân bắt buộc** (Nghị định 13/2023/NĐ-CP). Tìm bệnh nhân theo số điện thoại; chưa có thì tạo hồ sơ bệnh nhân
(``data_consent`` + thời điểm đồng ý). Tạo ``dmag.dental.visit`` trạng thái *Đã đặt lịch* (``create()`` bắn
``_dmag_journey_event('booked')``). Chống spam: tối đa 3 yêu cầu / số điện thoại / 24 giờ, 10 yêu cầu / IP / giờ,
trường bẫy bot, CSRF. Nhật ký ``dmag.portal.booking.log``.

REST JSON API ``/api/dmag/v1/``
-------------------------------

Xác thực: ``Authorization: Bearer <API key>`` (``res.users.apikeys`` của tài khoản bệnh nhân, scope
``dmag_patient_api`` hoặc khóa toàn quyền) **hoặc** phiên đăng nhập cổng (cookie). Lỗi:
``{"error": {"code": "...", "message": "..."}}`` với HTTP 401 / 403 / 404 / 400 / 415.

``GET /api/dmag/v1/me``
    ``{"user": {id, name, login}, "partner": {id, name, phone, email},
    "patients": [{id, name, patient_code, relation, is_patient, tier, points}]}``

``GET /api/dmag/v1/visits?patient_id=&upcoming=1|0&limit=``
    ``{"items": [{id, name, patient_id, patient, state, state_label, start (UTC), start_display (giờ VN),
    doctor, branch, services[], procedures[]}], "count": n}``

``GET /api/dmag/v1/visit/<id>``
    Thẻ lượt khám + ``date_display, complaint, diagnoses[], assessment, treatment_note,
    procedure_lines[{name, teeth[], quantity, amount}], advice, aftercare[{service, note}],
    next_visit{id, name, start, start_display, doctor, services[]} | false, prescriptions[{code, date}],
    invoices[{name, date, amount_total, amount_residual, payment_state, paid}], amount_total, amount_due,
    currency, signed``

``GET /api/dmag/v1/plans?patient_id=``
    ``{"items": [{id, name, title, patient_id, patient, date, doctor, state, state_label, progress,
    amount_accepted, currency, options[{id, name, recommended, accepted, summary, amount_total,
    estimated_visits, deposit, installment_months, monthly_amount, lines[{name, phase, amount, done}]}]}]}``

``GET /api/dmag/v1/loyalty?patient_id=``
    Kết quả ``res.partner.get_loyalty_summary`` (xem README ``dmag_dental_loyalty``).

``POST /api/dmag/v1/booking`` (``Content-Type: application/json``)
    Vào: ``{"date": "YYYY-MM-DD", "time": "HH:MM", "service_id": 12, "company_id": 1, "note": "...",
    "consent": true, "patient_id": 34 (tùy chọn – người trong phạm vi), "name"/"phone" (tùy chọn)}``.
    Ra (201): ``{"ok": true, "visit": {id, name, state, start}}``.

Bảo mật
-------

* Token so sánh hằng thời gian (``consteq``), gắn với từng lượt khám, hết hạn 30 ngày.
* API POST không dùng CSRF nhưng bắt buộc JSON (trình duyệt không gửi chéo nguồn được nếu không có CORS).
* Không có quyền ACL nào cho nhóm Portal trên model nha khoa.

Cần xác nhận
------------

* Hồ sơ trùng: đặt lịch với số điện thoại đã có nhưng tên khác → hiện gắn vào bệnh nhân cũ và ghi chú cho lễ tân
  kiểm tra. Có muốn tạo "yêu cầu đặt lịch" riêng chờ lễ tân xác minh không?
* Thời hạn link chia sẻ 30 ngày; link có hiển thị chi phí / hóa đơn – có cần ẩn chi phí trên link không đăng nhập?
* Cách cấp tài khoản cổng cho bệnh nhân (mời qua email / Zalo OTP?) và cho phép tự tạo API key
  (tham số hệ thống ``portal.allow_api_keys``) cho ứng dụng di động.
* Con trên 18 tuổi trong gia đình: chủ hộ vẫn xem được hồ sơ – có cần sự đồng ý của người đó (NĐ 13/2023)?
* Giới hạn chống spam (3 / số / ngày, 10 / IP / giờ) và khung giờ nhận đặt (08:00–19:30, 90 ngày tới).
* Nội dung chẩn đoán hiển thị theo tên ICD-10 tiếng Việt + đánh giá của bác sĩ – có cần trường "giải thích dễ hiểu"
  riêng cho bệnh nhân không?
