DMAG – Hồ sơ bệnh án RHM chuẩn Bộ Y tế
========================================

Module ``dmag_dental_emr`` (phụ thuộc ``dmag_dental_clinic``) bổ sung bệnh án ngoại trú Răng Hàm Mặt
theo bố cục mẫu **16/BV1** (Phụ lục XXVIII Thông tư 32/2023/TT-BYT), đáp ứng Luật Khám bệnh, chữa bệnh 2023,
TT 32/2023 Chương X và TT 13/2025/TT-BYT (bệnh án điện tử).

Chức năng
---------

* **Hành chính người bệnh** (``res.partner``): loại giấy tờ định danh (căn cước / hộ chiếu / giấy khai sinh),
  lý do chưa có số định danh, dân tộc, quốc tịch, nơi làm việc, đối tượng (bảo hiểm y tế / thu phí / miễn / khác),
  số thẻ và hạn thẻ bảo hiểm y tế, người nhà báo tin (họ tên, địa chỉ, điện thoại), tiền sử gia đình.
* **Bệnh án lượt khám** (``dmag.dental.visit``, trang "Bệnh án RHM (16/BV1)"): nơi giới thiệu và chẩn đoán nơi
  giới thiệu; bệnh sử; tiền sử bản thân / gia đình (lấy mặc định từ hồ sơ người bệnh); mạch, nhiệt độ, huyết áp,
  nhịp thở, cân nặng, chiều cao; toàn thân, các bộ phận; khám ngoài mặt, trong miệng, khớp cắn, mô mềm, nha chu;
  cận lâm sàng; bệnh chính (``primary_diagnosis_id``) + bệnh kèm theo (``diagnosis_ids`` trừ bệnh chính);
  chẩn đoán khi kết thúc; hướng điều trị; điều trị từ ngày / đến ngày; tổng kết bệnh án.
  Mọi trường đều ``tracking=True`` (TT 32 Điều 52 khoản 2 điểm d: thời gian + người ghi).
* **Khóa sau ký**: các trường mới được khóa như ``CLINICAL_FIELDS`` của lõi (ghi đè ``write``); chỉ ghi được với
  context ``dmag_record_amend`` (nút "Bổ sung bệnh án" của Giám đốc). "Số lưu trữ" vẫn ghi được sau ký.
* **Kiểm tra khi ký** (``action_sign_record``): bắt buộc số định danh người bệnh (hoặc lý do chưa có), lý do đến khám,
  ít nhất một chẩn đoán ICD-10, kết quả khám. Khi ký: tự đặt bệnh chính, ngày bắt đầu điều trị, cấp **số ngoại trú**.
* **Báo cáo A4** (tự ghi nhật ký truy cập mỗi lần in / xuất):

  - ``dmag_dental_emr.action_report_dental_record`` – BỆNH ÁN NGOẠI TRÚ RĂNG HÀM MẶT (MS: 16/BV1), mục I–IX,
    sơ đồ răng FDI (18–28 / 48–38, răng sữa 55–65 / 85–75) có chú giải, chữ ký "Bác sĩ khám bệnh" /
    "Thủ trưởng cơ sở", trang 2 "TỔNG KẾT BỆNH ÁN".
  - ``dmag_dental_emr.action_report_treatment_sheet`` – PHIẾU ĐIỀU TRỊ (các lượt khám cùng kế hoạch điều trị
    hoặc cùng đợt điều trị từ ngày – đến ngày).
  - ``dmag_dental_emr.action_report_record_summary`` – TÓM TẮT HỒ SƠ BỆNH ÁN (giao người bệnh, không viết tắt).
  - ``dmag_dental_emr.action_report_consent`` – GIẤY CAM KẾT / ĐỒNG Ý THỰC HIỆN THỦ THUẬT (model ``dmag.consent``).

* **Cam kết của người bệnh** (``dmag.consent``): thủ thuật, răng, nguy cơ, phương án thay thế, chi phí, nội dung
  cam kết lưu tại thời điểm ký, người ký / người đại diện, hình thức ký (máy tính bảng – widget chữ ký, OTP,
  giấy quét), thời điểm + IP. Khóa và không xóa được sau khi ký.
* **Yêu cầu cung cấp hồ sơ** (``dmag.record.request``, Luật KCB Điều 12, Điều 69): người yêu cầu (người bệnh,
  người đại diện, cơ quan có thẩm quyền, bảo hiểm, nghiên cứu), căn cứ pháp lý, văn bản yêu cầu bắt buộc,
  nội dung (tóm tắt / sao chụp / xem). Mới tiếp nhận → Quản lý duyệt → Đã cung cấp (người, thời điểm) / Từ chối.
* **Nhật ký truy cập** (``dmag.record.access.log``): ghi khi mở ``get_visit_workspace`` (gộp trong 10 phút),
  in / xuất các báo cáo bệnh án và khi cung cấp hồ sơ. Không ai sửa / xóa được; chỉ Giám đốc xem.
* **Thời hạn lưu trữ** (công ty: ``dmag_record_retention_years``, mặc định 10 năm): không ai, kể cả Giám đốc,
  xóa được lượt khám đã có nội dung bệnh án trước hạn lưu trữ.
* **Danh sách ký hiệu viết tắt** (``dmag.abbreviation``, TT 32 Điều 52 khoản 2 điểm c) – danh mục mẫu.

Giao diện bác sĩ (workspace)
----------------------------

``get_visit_workspace()`` trả thêm khóa ``emr`` (ghi nhật ký truy cập):

* Trường văn bản / số: ``referral_source``, ``referral_facility``, ``referral_diagnosis``, ``present_illness``,
  ``personal_history``, ``family_history``, ``pulse``, ``temperature``, ``bp_systolic``, ``bp_diastolic``,
  ``respiratory_rate``, ``weight``, ``height``, ``general_exam``, ``organ_exam``, ``exam_extraoral``,
  ``exam_intraoral``, ``exam_occlusion``, ``exam_soft_tissue``, ``exam_periodontal``, ``paraclinical_summary``,
  ``final_diagnosis``, ``treatment_direction``, ``treatment_from``, ``treatment_to`` (``YYYY-MM-DD``),
  ``summary_course``, ``summary_method``, ``summary_status_end``, ``summary_next_direction``.
* Chẩn đoán: ``primary_diagnosis_id``, ``primary_diagnosis``, ``secondary_diagnoses`` ([{id, name}]),
  ``final_diagnosis_id``, ``final_diagnosis_name``.
* Khác: ``bmi``, ``vitals`` ({pulse, temperature, bp_systolic, bp_diastolic, respiratory_rate, weight, height, bmi}),
  ``outpatient_number``, ``archive_number``, ``missing_for_signature`` (danh sách mục còn thiếu để ký),
  ``consents`` ([{id, name, type, state}]), ``patient_admin`` ({identity_type, citizen_id,
  identity_exemption_reason, ethnicity, nationality, workplace, patient_category, bhyt_number, bhyt_valid_to,
  emergency_contact_name, emergency_contact_phone}).

``save_record_from_workspace(values)`` nhận thêm (phẳng hoặc lồng trong ``values['emr']``) tất cả các khóa văn bản /
số ở trên cùng ``primary_diagnosis_id`` và ``final_diagnosis_id`` (id hoặc ``False``). Khóa khác bị bỏ qua.

Cần xác nhận
------------

* **Mẫu 16/BV1**: nhãn, thứ tự, đánh số mục (I–IX, 13 mục hành chính), tiêu đề "TỔNG KẾT BỆNH ÁN" và bảng
  "Hồ sơ, phim, ảnh" được dựng theo họ mẫu BV1 qua tra cứu – phải đối chiếu nguyên văn Phụ lục XXVIII
  TT 32/2023/TT-BYT (bản gốc chưa tải được) trước khi vận hành.
* **Thời hạn lưu trữ**: mặc định 10 năm (theo TT 53/2017 cũ) – cần xác minh theo **TT 33/2025/TT-BYT**.
* Mã số mẫu của "Phiếu điều trị", "Giấy cam kết" và "Tóm tắt hồ sơ bệnh án" chưa in (chưa xác minh mẫu gốc).
* Quy chế bệnh án điện tử của cơ sở (TT 13/2025 Điều 6 khoản 3 điểm b) và quyết định ban hành danh sách viết tắt
  là việc của phòng khám.
* Chữ ký số của bác sĩ trên bản in do module ``dmag_esign_mysign`` gắn vào báo cáo
  ``dmag_dental_emr.action_report_dental_record``.
