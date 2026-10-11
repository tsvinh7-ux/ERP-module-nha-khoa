===============================
DMAG – Trợ lý AI cho bác sĩ
===============================

Các tính năng AI dành cho bác sĩ, gắn thẳng vào **Bàn làm việc bác sĩ** (``dmag_clinic_workspace``), dùng cổng AI chung
``dmag.ai.run`` của ``dmag_ai_core`` (ẩn danh, nhật ký, chi phí, trần ngân sách, đồng ý của bệnh nhân).

Nguyên tắc: **AI chỉ soạn nháp – bác sĩ duyệt**. Không có gì được tự ký, tự phát hành hay tự tạo; mọi nội dung AI
chỉ vào bệnh án khi bác sĩ bấm chấp nhận, kèm dòng chatter "có hỗ trợ AI, bác sĩ … duyệt".

Tính năng
=========

========  ==========================================  ===================================================================
Mã        Ở đâu trên giao diện                        Giả lập (không khóa API)  /  Claude API (có khóa)
========  ==========================================  ===================================================================
AI-01     Tab *Bệnh án*: nút micro                    Bản đọc mẫu dựng từ dữ liệu thật của lượt khám (tuổi, giới, lý do,
          "Ghi bệnh án bằng giọng nói"                sơ đồ răng, dị ứng) → tách mục 16/BV1 bằng quy tắc từ khóa.
                                                      Claude: structured output theo schema các mục 16/BV1 + ICD-10
                                                      (enum = danh mục phòng khám). Hộp thoại so sánh từng mục
                                                      hiện tại ↔ gợi ý, chấp nhận từng mục / tất cả → ghi qua
                                                      ``save_record_from_workspace``.
AI-02     Nút "AI kiểm tra bệnh án" + tự chạy khi     Quy tắc cố định: ``_emr_missing_for_signature`` (mục bắt buộc),
          bấm "Ký bệnh án"                            sơ đồ răng ↔ ICD-10, dị ứng chưa ghi tiền sử, sinh hiệu, xử trí…
                                                      AI: đối chiếu mô tả ↔ ICD-10 ↔ sơ đồ; công cụ ``lookup_icd10``
                                                      (``strict: true``) + enum mã → không bao giờ bịa mã. Bác sĩ vẫn ký
                                                      được ("Vẫn ký bệnh án").
AI-03     Tab *Đơn thuốc*: khung "An toàn đơn thuốc"  Quy tắc cố định (``models/rx_safety.py``) chạy mỗi lần thêm / bỏ
                                                      thuốc và trước khi phát hành – **kể cả khi AI tắt**: dị ứng (tên
                                                      INN / biệt dược / tên Việt – Anh, họ Penicillin, Cephalosporin dị
                                                      ứng chéo, NSAID, thuốc tê…) → CHẶN; NSAID + chống đông / aspirin,
                                                      Metronidazol + Warfarin, thai kỳ, trẻ < 12 tuổi (liều theo cân
                                                      nặng; Tetracyclin < 8 tuổi CHẶN), trùng hoạt chất / trùng nhóm
                                                      NSAID → cảnh báo phải xác nhận; > 30 ngày → CHẶN. Chặn trên MỌI
                                                      đường phát hành (``dmag.prescription.action_issue``); chỉ Giám đốc
                                                      duyệt vượt (xem mục dưới). "AI giải thích" viết lại bằng lời dễ
                                                      hiểu + gợi ý thay thế từ danh mục thuốc.
AI-04     Thẻ "Tóm tắt hồ sơ 30 giây" dưới thẻ        Dữ kiện thật: dị ứng, cảnh báo, thuốc đang dùng, thai kỳ, 5 lần
          bệnh nhân (thu gọn được)                    khám gần nhất, kế hoạch đang dở (dòng chưa làm), công nợ hóa đơn,
                                                      ghi chú chăm sóc. Giả lập tự tạo khi mở bệnh nhân; Claude: bấm
                                                      "Tóm tắt" (tránh tốn phí mỗi lần mở).
AI-05     Tab *Sơ đồ răng* / *Kế hoạch điều trị*:     2 phương án *Tối ưu* / *Cơ bản*, dịch vụ CHỈ từ danh mục
          "AI gợi ý kế hoạch"                         (``product_id`` enum), răng FDI, giai đoạn, số buổi, lời giải thích
                                                      cho khách. "Dùng gợi ý" điền sẵn khung lập kế hoạch (cột A = Tối
                                                      ưu, B = Cơ bản) – bác sĩ sửa rồi tự bấm "Lưu kế hoạch".
AI-06     Thanh công cụ sơ đồ răng: "AI đọc phim"     Chọn / tải ảnh phim (ir.attachment của lượt khám) hoặc dùng phim
          (minh họa)                                  mẫu. Claude: khối ảnh (vision) + schema (răng, mô tả, mã tình
                                                      trạng, độ tin cậy, khung vị trí). Giả lập: phim mẫu → kết quả mẫu
                                                      đúng vị trí đã vẽ; ảnh khác → lấy từ sơ đồ răng (ghi rõ). Khung
                                                      trên ảnh + tô răng trên sơ đồ; "Ghi lên sơ đồ" từng phát hiện khi
                                                      bác sĩ xác nhận. Banner: *Chỉ minh họa – không phải thiết bị chẩn
                                                      đoán được cấp phép; bác sĩ quyết định.*
========  ==========================================  ===================================================================

Mọi khối AI hiển thị nhãn **AI**, chế độ **Giả lập** / **Claude**, chi phí (thật hoặc "≈ … đ nếu chạy thật"), trạng
thái đang chạy và thông báo lỗi đúng nội dung ``UserError``. Nút ẩn khi tính năng tắt (*Cấu hình → Trợ lý AI → Tính
năng AI*) hoặc người dùng không phải bác sĩ.

AI-03 – chặn mọi đường phát hành & Giám đốc duyệt vượt
========================================================
Quyết định của chủ phòng khám (11/10/2026): đơn vi phạm quy tắc an toàn **bị chặn ở mọi đường phát hành** – form đơn
thuốc, Bàn làm việc bác sĩ, đơn thay thế, mọi lời gọi máy chủ – vì quy tắc chạy trong ``dmag.prescription.action_issue``
(kể cả quyền hệ thống). Cảnh báo (không chặn) vẫn giữ cách xác nhận "Đã xem – vẫn phát hành" như cũ.

* **Bác sĩ**: khung "An toàn đơn thuốc" hiện "Không phát hành được" + nút **Đề nghị Giám đốc duyệt vượt** → tạo việc
  cần làm (activity) cho Giám đốc kèm danh sách quy tắc bị vượt; form đơn thuốc có nút cùng tên.
* **Giám đốc** (``group_dmag_director``, không phải Quản lý): nút **Duyệt vượt & ký chịu trách nhiệm** → hộp thoại liệt
  kê quy tắc bị vượt, ô **lý do bắt buộc** (≥ 15 ký tự), ô xác nhận "ký bổ sung và chịu trách nhiệm" → ghi lên đơn các
  trường chỉ đọc ``rx_safety_override``, ``rx_override_uid``, ``rx_override_date``, ``rx_override_reason``,
  ``rx_override_rules``, ``rx_override_esign`` + chatter, rồi phát hành. Trên form đơn thuốc dùng wizard
  ``dmag.rx.override.wizard`` (tab "An toàn đơn thuốc (AI-03)" là nhật ký kiểm soát).
* Duyệt vượt gắn với **đúng tập vi phạm** lúc duyệt (mã quy tắc + thuốc, ``rx_override_codes``): sửa đơn làm phát sinh vi
  phạm khác → chặn lại, cần duyệt lần nữa. Các trường duyệt vượt không ghi được bằng ``write`` thông thường.
* **Ký số bổ sung (phụ thuộc mềm)**: nếu đã cài ``dmag_esign_mysign`` và phòng khám có nhà cung cấp ký số, hệ thống dựng
  "Văn bản duyệt vượt quy tắc an toàn đơn thuốc" (HTML), băm SHA-256 và tạo ``dmag.esign.request`` cho hồ sơ ký số của
  Giám đốc (hồ sơ nhân sự lâm sàng gắn tài khoản – có thể để *lưu trữ* để không hiện trong danh sách bác sĩ). Chưa cài /
  chưa cấu hình / Giám đốc chưa có hồ sơ ký số → ghi rõ lý do "Chưa ký số", xác nhận vẫn lưu trong hệ thống. Demo dùng
  nhà cung cấp giả lập.
* Bản in đơn thuốc / bệnh án **không** in thông tin duyệt vượt; kiểm toán xem trên đơn (tab An toàn đơn thuốc, chatter,
  hồ sơ ký số).

Đồng ý của bệnh nhân
====================
Khi bệnh nhân chưa đồng ý xử lý bằng AI (``dmag_ai_consent``), các khối AI hiện thông báo kèm nút một chạm
**"Bệnh nhân đồng ý"** (chỉ bác sĩ) → ghi ``dmag_ai_consent`` + thời điểm + chatter, rồi chạy lại. Quy tắc cố định
AI-02 / AI-03 vẫn chạy khi chưa có đồng ý (không gửi dữ liệu ra ngoài).

Nhận dạng giọng nói (AI-01)
===========================
Chọn ở *Cấu hình → Trợ lý AI → Cài đặt AI* (bác sĩ đổi tạm được ngay trên khung ghi âm):

* **Giả lập** – bản đọc mẫu, demo không cần micro.
* **Trình duyệt** – Web Speech API (``webkitSpeechRecognition``, ``vi-VN``, liên tục, có kết quả tạm). Miễn phí, hợp
  demo / thí điểm; âm thanh do trình duyệt gửi tới dịch vụ của hãng trình duyệt (Chrome / Edge).
* **FPT.AI** / **Viettel AI** – trình duyệt ghi âm (MediaRecorder) → ``POST /dmag_ai_clinical/stt`` → Odoo chuyển tiếp
  tới nhà cung cấp (khóa API giữ ở máy chủ, chỉ Giám đốc thấy). Có ``ffmpeg`` trên máy chủ thì âm thanh được đổi sang
  WAV 16 kHz mono trước khi gửi.

  - FPT.AI: mặc định ``POST https://api.fpt.ai/hmi/asr/general``, header ``api-key``, thân là dữ liệu âm thanh
    **[CẦN XÁC MINH]** địa chỉ, định dạng nhận và cấu trúc JSON trả về theo tài liệu / hợp đồng hiện hành.
  - Viettel AI: mặc định ``POST https://viettelai.vn/asr/recognize``, ``token`` (header + form), file ``multipart``
    **[CẦN XÁC MINH]** địa chỉ, tên trường và cấu trúc JSON trả về.

  Bộ đọc kết quả tìm khóa ``utterance`` / ``transcript`` / ``text`` trong JSON nên chịu được khác biệt nhỏ.

Phim mẫu (AI-06)
================
``static/img/xray_sample_1.png``, ``xray_sample_2.png``: ảnh panorama **tổng hợp** vẽ bằng mã
(``scripts/generate_xray_samples.py``, Pillow) – không phải phim bệnh nhân, không lấy từ nguồn ngoài, giấy phép như
module (LGPL-3). Vị trí tổn thương đã vẽ nằm trong ``static/img/xray_samples.json`` và là kết quả mẫu ở chế độ giả
lập. Mẫu 1 khớp sơ đồ răng bệnh nhân demo *Nguyễn Thị Mai*, mẫu 2 khớp *Đỗ Thanh Hương*.

Điểm móc vào module khác
========================
Không sửa file nào của ``dmag_clinic_workspace``:

* JS: ``patch(DoctorDesk.prototype)`` (``setup``, ``openVisit``, ``visitAction`` – chặn "Ký bệnh án" để kiểm tra
  trước) và ``patch(RxPanel.prototype)`` (``setup``, ``addDrug``, ``applyTemplate``, ``removeLine``, ``editDraft``,
  ``issue``); thêm component vào ``DoctorDesk.components`` / ``RxPanel.components``.
* Mẫu OWL: ``t-inherit-mode="extension"`` trên ``dmag_clinic_workspace.DoctorDesk`` và ``dmag_clinic_workspace.RxPanel``
  (xpath theo class: ``dmag-patient-head``, ``dmag-record``/``EmrPanel``, ``dmag-chart-toolbar``,
  ``dmag-chart-board``/``Odontogram`` – thêm thuộc tính ``highlight``, ``dmag-chart-side``, ``dmag-plans``,
  ``dmag-rx-editor``).
* Python: ``dmag.prescription.action_issue`` (``_inherit`` + ``super()``) chặn đơn vi phạm quy tắc an toàn trên mọi
  đường phát hành; ``_workspace_dict`` thêm ``rx_override``. Hộp thoại OWL ``RxOverrideDialog``.
* Ghi dữ liệu qua đường sẵn có: ``save_record_from_workspace``, ``dmag.dental.chart.entry.add_from_chart``; khung lập
  kế hoạch của DoctorDesk (``state.builder``) → ``dmag.treatment.plan.create_from_workspace`` khi bác sĩ bấm lưu.

API (``dmag.ai.clinical``, chỉ bác sĩ)
======================================
``get_status``, ``record_consent``, ``ai01_sample_transcript``, ``ai01_structure``, ``ai01_apply``, ``stt_transcribe``,
``ai02_check``, ``ai02_add_diagnosis``, ``rx_check``, ``ai03_explain``, ``ai04_summary``, ``ai05_suggest``,
``ai06_images``, ``ai06_add_sample``, ``ai06_upload``, ``ai06_analyze``, ``ai06_add_to_chart``, ``rx_request_override``
(bác sĩ), ``rx_override`` (Giám đốc). ``rx_check`` nhận thêm ``prescription_id`` và trả trạng thái duyệt vượt.

Kiểm thử
========
``tests/test_ai_clinical.py`` (post_install): giả lập từng tính năng ánh xạ đúng trường thật; chạy thật với client
Claude giả (schema chặt, không ``tool_choice`` ép buộc, công cụ ``strict``, ẩn danh, khối ảnh); dữ liệu chỉ ghi khi
chấp nhận; quy tắc đơn thuốc chặn dị ứng / thai kỳ / trẻ em / > 30 ngày; ICD-10 và dịch vụ chỉ từ danh mục; lễ tân không
gọi được phương thức của bác sĩ. ``tests/test_rx_override.py``: chặn cả ``action_issue`` (bác sĩ, Giám đốc, quyền hệ
thống); chỉ Giám đốc duyệt vượt, bắt buộc lý do + xác nhận; ghi vết + chatter; sửa đơn → duyệt lại; đề nghị tạo việc cho
Giám đốc; ký số giả lập khi có ``dmag_esign_mysign``.
