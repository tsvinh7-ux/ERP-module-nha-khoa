=============================================
DMAG – Đơn thuốc điện tử & liên thông
=============================================

Kê đơn thuốc điện tử cho phòng khám nha khoa theo **TT 26/2025/TT-BYT** và liên thông
**Hệ thống đơn thuốc quốc gia** (donthuocquocgia.vn, QĐ 808/QĐ-BYT).

Phụ thuộc: ``dmag_dental_clinic``.

Chức năng
=========

Danh mục thuốc (``dmag.drug``)
------------------------------

* Hoạt chất / tên chung (INN), hàm lượng, dạng bào chế, đơn vị tính, đơn vị liều, đường dùng,
  tên thương mại, số đăng ký, mã thuốc Dược quốc gia.
* Cờ: gây nghiện (N), hướng thần / tiền chất (H), thực phẩm chức năng (bị chặn kê – Luật KCB 2023 Đ63 k2),
  thuốc nhiều hoạt chất.
* Tên trên đơn tự sinh theo TT 26: một hoạt chất → ``INN hàm lượng (Tên thương mại)``;
  nhiều hoạt chất → ``Tên thương mại hàm lượng``.
* Dữ liệu demo: 15 thuốc nha khoa thường dùng (Vitamin C viên sủi đánh dấu thực phẩm chức năng).

Đơn thuốc mẫu (``dmag.prescription.template``)
----------------------------------------------

"Sau nhổ răng khôn", "Viêm tủy cấp", "Sau cấy implant" (demo). Chọn đơn mẫu trên đơn nháp →
điền thuốc, lời dặn, ngày tái khám.

Đơn thuốc (``dmag.prescription``)
---------------------------------

* Loại đơn ``c`` / ``n`` / ``h`` / ``y``. Đơn N, H bị chặn trừ khi công ty bật
  "Cho phép kê đơn N, H" **và** bác sĩ có cờ "Được kê đơn thuốc gây nghiện / hướng thần".
* **Mã đơn 14 ký tự** ``xxxxxyyyyyyy-z`` cấp khi phát hành: mã cơ sở KCB (``company.dmag_facility_code``,
  bắt buộc 5 ký tự) + 7 ký tự ngẫu nhiên ``[0-9a-z]`` duy nhất trong cơ sở + ``-`` + loại đơn.
* Chụp thông tin người bệnh khi phát hành: họ tên, ngày sinh, tuổi / tháng tuổi, giới, số định danh / CCCD,
  nơi cư trú, điện thoại, số thẻ BHYT (trường mới ``res.partner.dmag_bhyt_number``).
  Trẻ dưới 72 tháng: bắt buộc cân nặng + họ tên người đưa trẻ.
* Dòng thuốc: liều mỗi lần, số lần/ngày, số ngày, thời điểm, đường dùng; câu cách dùng tự soạn
  ("Uống ngày 2 lần, mỗi lần 1 viên, sau ăn"), số lượng tự tính, in số lượng < 10 có số 0 phía trước.
* Kiểm tra khi phát hành: tối đa 30 ngày/thuốc (90 ngày nếu dòng đánh dấu bệnh mạn tính và công ty bật
  cấu hình – mặc định tắt); số lượng > 0; không thực phẩm chức năng; có số định danh (hoặc ghi
  "Lý do không có số định danh"); có chẩn đoán; bác sĩ đúng vai trò, có số giấy phép, giấy phép chưa hết
  hạn; chỉ chính bác sĩ kê đơn (hoặc Giám đốc) phát hành.
* Trạng thái: Nháp → Đã phát hành (khóa) → Đã liên thông / Lỗi liên thông; Đã thay thế; Đã hủy.
* **Không sửa sau phát hành** (kể cả Giám đốc – chỉ ghi chú nội bộ / lý do hủy).
  "Kê đơn thay thế" tạo đơn nháp mới ``replaced_id``; khi đơn mới phát hành, đơn cũ chuyển
  "Đã thay thế" (và gửi lệnh hủy liên thông nếu đã gửi).
* Chỉ Giám đốc hủy đơn đã phát hành (bắt buộc lý do). Bác sĩ hủy được đơn nháp.
* Móc ký số: ``_dmag_esign_prescription()`` (trả True) – module ký số ghi đè.
* ``get_patient_message()``: tin nhắn mã đơn thuốc gửi người bệnh (Zalo / SMS dùng lại).

Liên thông đơn thuốc quốc gia
-----------------------------

* ``dmag.rx.national.config`` (mỗi công ty): bật/tắt, chế độ ``mock`` (giả lập) / ``live``,
  địa chỉ API (mặc định ``https://api.donthuocquocgia.vn``), đường dẫn đăng nhập cơ sở / bác sĩ / gửi đơn /
  hủy đơn, mã liên thông cơ sở + mật khẩu (chỉ Giám đốc thấy), số lần gửi tối đa.
* Bác sĩ: ``rx_link_code`` + ``rx_link_password`` (chỉ Giám đốc thấy) trên hồ sơ Nhân sự lâm sàng.
* Token cơ sở / bác sĩ lưu kèm hạn (mặc định 7 ngày, chỉ quản trị hệ thống thấy), tự đăng nhập lại khi hết hạn.
* Gửi tự động khi phát hành; nếu tắt liên thông hoặc lỗi mạng → hàng đợi, cron 15 phút gửi lại
  (``_cron_send_pending``); nút "Gửi lại" trên đơn.
* Nhật ký ``dmag.rx.send.log``: dữ liệu gửi (đã che mật khẩu / token), mã HTTP, phản hồi, lỗi, thời gian.
* Ánh xạ trường JSON gom trong **một** phương thức ``dmag.rx.national.config._rx_national_payload(rx)``;
  đánh giá phản hồi trong ``_parse_response``.

Báo cáo
-------

"Đơn thuốc" (A5) theo bố cục Phụ lục I TT 26: cơ quan quản lý / tên cơ sở, địa chỉ, điện thoại, giấy phép;
mã đơn + QR (``/report/barcode/?barcode_type=QR``); thông tin người bệnh; khối trẻ dưới 72 tháng; chẩn đoán
kèm mã ICD-10; thuốc đánh số; lời dặn; ngày tái khám; "Ngày … tháng … năm …"; "Bác sĩ / Y sĩ khám bệnh
(Ký, ghi rõ họ tên)"; chân trang "Khám lại xin mang theo đơn này", điện thoại. Không viết tắt.

API cho màn hình bác sĩ (``dmag.dental.visit``)
================================================

``get_visit_workspace()`` – thêm khóa ``prescriptions``: danh sách dict đơn thuốc (xem cấu trúc bên dưới).

``get_rx_catalog()`` (``@api.model``) trả về::

    {
      'drugs': [{'id', 'name', 'inn_name', 'strength', 'brand_name', 'dosage_form', 'unit', 'dose_unit',
                 'route', 'is_narcotic', 'is_psychotropic', 'is_supplement', 'default_dose_per_time',
                 'default_times_per_day', 'default_days', 'default_timing'}],   # không gồm thực phẩm chức năng
      'templates': [{'id', 'name', 'advice', 're_exam_days', 'diagnoses': [{'id', 'name'}],
                     'lines': [<dòng thuốc>]}],
      'routes': [[key, label]], 'timings': [[key, label]], 'rx_types': [[key, label]],
      'max_days': 30, 'max_days_chronic': 30|90, 'allow_controlled': bool,
    }

``save_prescription_from_workspace(vals)`` – tạo / cập nhật đơn **nháp** của lượt khám::

    vals = {
      'id': int (bỏ trống = tạo mới),
      'template_id': int (tùy chọn – áp đơn mẫu),
      'rx_type': 'c', 'diagnosis_ids': [int], 'diagnosis_text': str, 'advice': str,
      're_exam_date': 'YYYY-MM-DD' | False, 're_exam_days': int,
      'weight': float, 'companion_name': str, 'identity_exemption_reason': str,
      'lines': [{'drug_id', 'dose_per_time', 'times_per_day', 'days', 'timing', 'route',
                 'quantity' (bỏ trống = tự tính), 'usage' (bỏ trống = tự soạn), 'usage_note',
                 'is_chronic', 'unit'}],     # có khóa 'lines' = thay toàn bộ dòng thuốc
    }

trả về dict đơn thuốc::

    {'id', 'code', 'state', 'state_label', 'rx_type', 'date', 'doctor', 'doctor_id',
     'diagnoses': [{'id', 'name'}], 'diagnosis_text', 'advice', 're_exam_date', 'weight',
     'companion_name', 'identity_exemption_reason', 'is_under_72_months', 'send_error',
     'replaced_id', 'replaced_by_id', 'can_edit', 'print_url',
     'lines': [{'id', 'sequence', 'drug_id', 'drug_name', 'route', 'dose_per_time', 'times_per_day',
                'days', 'timing', 'usage_note', 'usage', 'quantity', 'quantity_display', 'unit',
                'is_chronic'}]}

``issue_prescription(prescription_id)`` – phát hành (lỗi kiểm tra → ``ValidationError`` liệt kê lý do)::

    {'id', 'code', 'state', 'state_label', 'send_status': 'sent'|'error'|'queued',
     'send_error', 'patient_message'}

Phân quyền
==========

* Lễ tân: xem, in đơn. Phụ tá: xem. Bác sĩ: tạo, sửa nháp, phát hành, kê đơn thay thế, gửi lại,
  quản lý đơn mẫu. Quản lý: danh mục thuốc, xem cấu hình / nhật ký liên thông.
  Giám đốc: hủy đơn đã phát hành, cấu hình liên thông, mật khẩu liên thông.
* Quy tắc theo ``company_id`` cho mọi mô hình (thuốc / đơn mẫu không gắn công ty dùng chung).

Cần xác nhận
============

1. **Tên trường và giá trị API** "gui-don-thuoc" bản mới nhất trên donthuocquocgia.vn (môi trường phát triển
   chặn domain .vn; tên trường lấy theo tóm tắt QĐ 808/QĐ-BYT). Đặc biệt: mã giá trị ``gioi_tinh``,
   ``hinh_thuc_dieu_tri`` (ngoại trú), ``hinh_thuc``, định dạng ngày, có trường số định danh / CCCD người bệnh
   hay không; tài liệu nhà thuốc dùng ``thong_tin_thuoc`` – kiểm tra ``thong_tin_don_thuoc`` cho API gửi đơn;
   có cần header ``app-name`` / ``app-key`` không.
2. **Đường dẫn và luồng đăng nhập** cơ sở / bác sĩ (tên trường ``ma_lien_thong_co_so_kham_chua_benh``,
   ``ma_lien_thong_bac_si``, ``password``; token gửi bằng ``Authorization: Bearer``), cấu trúc phản hồi
   (``success`` / ``message`` / ``token``), API hủy đơn (đường dẫn mặc định ``/api/v1/huy-don-thuoc`` là giả định).
3. **Mẫu Phụ lục I TT 26/2025/TT-BYT bản gốc**: bố cục cuối cùng, dòng cơ quan chủ quản, vị trí mã vạch / QR,
   nội dung chân trang, khổ giấy (đang dùng A5), mẫu riêng cho đơn N / H.
4. **Thời hạn lưu trữ** đơn thuốc / nhật ký liên thông (TT 26/2025, TT 33/2025) – module không xóa đơn
   đã phát hành; chưa có cơ chế xóa theo hạn.
5. Danh mục bệnh mạn tính được kê 90 ngày (Phụ lục VII) – hiện chỉ là cờ trên dòng thuốc, chưa đối chiếu ICD.
6. Ngoại lệ không có số định danh (người nước ngoài, trẻ em chưa cấp số…) – đang cho phép khi ghi lý do.
7. Số đăng ký / mã thuốc Dược quốc gia của danh mục demo để trống – phòng khám cập nhật theo sản phẩm thực tế.
