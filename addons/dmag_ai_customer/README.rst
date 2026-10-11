=====================================
DMAG – AI chăm sóc khách hàng
=====================================

Các tính năng AI phía lễ tân / CSKH / bệnh nhân của ``docs/DE_XUAT_AI.md`` (AI-07 … AI-12, AI-17 … AI-19), chạy qua
cổng ``dmag.ai`` của ``dmag_ai_core``: **chế độ Giả lập** (không khóa API – kết quả dựng từ dữ liệu THẬT của Odoo,
không tốn phí, có chi phí ước tính) và **chế độ Claude** (Claude API, mô hình theo bản ghi tính năng, mặc định
``claude-opus-5-5``). Mỗi tính năng tôn trọng công tắc bật/tắt (*Cấu hình → Trợ lý AI → Tính năng AI*) và đồng ý
xử lý bằng AI của bệnh nhân (khi thiếu: báo rõ hoặc tự chuyển sang xử lý tại chỗ).

Tính năng
=========

=======  ==========================================  ===============================  ==========================================
Mã       Tính năng                                   Nguồn                            Ở đâu
=======  ==========================================  ===============================  ==========================================
AI-07    Trợ lý Zalo OA 24/7 (đặt lịch thật)         Claude + công cụ / giả lập       CSKH › Trợ lý AI khách hàng › Mô phỏng Zalo,
                                                                                      Hộp thư trợ lý Zalo; webhook OA
AI-08    Dự báo khách không đến                      Tại chỗ (hồi quy logistic)       Huy hiệu trên Bảng điều phối, lượt khám
AI-09    Phân loại phản hồi & khiếu nại              Claude (schema) / tại chỗ        CSKH › Phản hồi cần xử lý
AI-10    Nhập bệnh nhân từ CCCD (QR)                 Tại chỗ (trình duyệt)            Hộp thoại *Bệnh nhân mới* › Quét CCCD
AI-11    Gợi ý xếp lịch                              Tại chỗ (chấm điểm)              Hộp thoại *Đặt lịch* › chip "Gợi ý"
AI-12    Nội dung chăm sóc cá nhân hóa               Claude (schema) / giả lập        Lượt khám › Soạn nội dung chăm sóc (AI);
                                                                                      nút "Chăm sóc" trên thẻ "Đã xong"
AI-17    Trợ lý trên cổng bệnh nhân                  Claude + công cụ theo phạm vi    ``/my/dental`` (nút "Hỏi trợ lý")
AI-18    Theo dõi sau điều trị (24h / 72h)           Ngưỡng tại chỗ + Claude đọc      ``/dmag/followup/<token>``; CSKH › Theo dõi
                                                     mô tả tự do                      sau điều trị
AI-19    Mô phỏng nụ cười (minh họa)                 Pillow tại chỗ + Claude vision   ``/my/dental/smile``; CSKH › Mô phỏng nụ cười
                                                     (chỉ văn bản)
=======  ==========================================  ===============================  ==========================================

AI-07 – Trợ lý Zalo OA
----------------------
* ``dmag.ai.conversation`` (kênh zalo / portal / web / simulator, trạng thái *bot → handoff → human → closed*) +
  ``dmag.ai.conversation.message`` (vai trò, công cụ đã gọi, chi phí, trạng thái gửi).
* Công cụ (``strict: true``, ``additionalProperties: false``, không ép ``tool_choice``): ``search_services`` (bảng
  giá = giá bán dịch vụ), ``get_free_slots`` (``dmag.workspace.get_free_slots`` + xếp hạng AI-11),
  ``find_patient_by_phone`` (chỉ trả có/không + tên gọi), ``book_appointment`` (bắt buộc ``consent``; tạo / gắn
  bệnh nhân, lượt khám **nháp** nguồn "Zalo OA (trợ lý AI)" để lễ tân gọi xác nhận), ``get_clinic_info``,
  ``handoff_to_staff``.
* Giả lập: nhận diện ý định bằng từ khóa → gọi đúng các công cụ trên → giá / giờ trống thật, đặt lịch nháp thật.
* Khiếu nại / ca khẩn / câu hỏi chuyên môn → chuyển nhân viên (việc cần làm, phiếu AI-09); không chẩn đoán.
* Webhook: dùng chung ``/dmag/zalo/webhook`` của ``dmag_zalo_zns`` – sự kiện ``user_send_*`` được chuyển cho trợ lý
  (``dmag.zns.webhook.event._dmag_process``). Chế độ Claude: trả lời ở tác vụ nền (cron) để webhook phản hồi nhanh.
* Gửi trả lời: theo chế độ ZNS của phòng khám (``mock`` ghi nhận giả lập; ``live`` gọi Zalo OA "tin tư vấn";
  ``bizapps`` gọi ``biz.zalo.oa.send_text_message`` nếu có). Chế độ trả lời: xem mục "Kịch bản trả lời đã duyệt".
* Giờ làm việc / ngày nghỉ trợ lý báo khách và giờ trống lấy từ **Lịch làm việc phòng khám** (``dmag.clinic.schedule``,
  *Nha khoa › Cấu hình › Phòng khám › Lịch làm việc*); ngày nghỉ → báo ngày làm việc gần nhất.

AI-07 – Kịch bản trả lời đã duyệt (quyết định 11/10/2026)
----------------------------------------------------------
Chủ phòng khám: *"cho tự trả lời nhưng theo kịch bản hoặc được duyệt training trước"*.

* ``dmag.ai.reply.script`` – **Kịch bản trả lời đã duyệt**: chủ đề / mã ý định, câu hỏi mẫu của khách, từ khóa, **mẫu trả
  lời** có ô dữ liệu điền từ Odoo (``{gia_dich_vu}`` bảng giá, ``{gio_trong}`` giờ trống 2 ngày làm việc tới,
  ``{gio_lam_viec}`` / ``{ngay_nghi_sap_toi}`` Lịch làm việc, ``{dia_chi}``, ``{gui_xe}``, ``{thanh_toan}``,
  ``{chuan_bi}``, ``{hotline}``, ``{ten_khach}``, ``{ten_phong_kham}``), công cụ được phép (``dmag.ai.reply.tool``), cách
  trả lời (*theo mẫu* / *đặt lịch qua công cụ* / *mẫu an toàn rồi chuyển nhân viên*), cho phép diễn đạt lại nhẹ, ngưỡng
  riêng, người đề xuất / Giám đốc duyệt / thời điểm duyệt.
* Quyền: Lễ tân xem; **Quản lý trở lên tạo / sửa bản nháp**; **chỉ Giám đốc duyệt**; kịch bản đã duyệt **bị khóa** (kể cả
  Giám đốc) – "Mở lại để sửa" (Giám đốc, ghi vết) → trợ lý ngừng dùng tới khi duyệt lại. Duyệt kiểm tra ô dữ liệu cần
  công cụ đã được phép.
* 12 kịch bản mẫu tiếng Việt (``models/reply_script_samples.py``, nạp ở trạng thái **nháp** khi cài – nút "Nạp kịch bản
  mẫu"): giá dịch vụ, giờ mở cửa, địa chỉ / đỗ xe, đặt lịch, đổi / hủy lịch, chuẩn bị trước khám, bảo hành, trả góp,
  đau sau nhổ răng (mẫu an toàn + chuyển nhân viên), niềng răng, tẩy trắng, khám cho trẻ em. ``dmag_dental_demo`` duyệt
  chúng bằng tài khoản Giám đốc demo.
* Chế độ trả lời theo phòng khám (``dmag_ai_zalo_reply_mode``, áp cho Zalo OA và Mô phỏng Zalo):

  - ``approve`` – **Nhân viên duyệt mọi câu** (như trước);
  - ``script`` – **Tự động theo kịch bản đã duyệt** (MẶC ĐỊNH): kiểm tra an toàn tại chỗ trước (ca khẩn → mẫu an toàn
    cố định gửi ngay + chuyển người; khiếu nại / muốn gặp người → chuyển người). Sau đó nhận diện ý định – *giả lập*:
    từ khóa + độ giống câu hỏi mẫu / ví dụ đã duyệt; *Claude*: structured output chỉ được chọn ``script_id`` trong enum
    các kịch bản đã duyệt (+ ``none``), kèm ``confidence`` và cờ an toàn. Khớp với độ tin cậy ≥ ngưỡng (mặc định 60 %)
    → tự gửi **đúng mẫu đã duyệt điền dữ liệu thật** (Claude chỉ diễn đạt lại nhẹ khi kịch bản cho phép; lệch bất kỳ con
    số nào → dùng nguyên mẫu). Kịch bản đặt lịch: luồng giữ chỗ với đúng công cụ được phép, lịch tạo ở trạng thái
    **nháp** chờ lễ tân xác nhận. Không khớp / tin cậy thấp / câu hỏi chuyên môn → nháp (chỉ công cụ đọc) **chờ nhân
    viên duyệt**, khách nhận tin báo đã nhận (mẫu cố định, một lần), lễ tân có việc cần làm;
  - ``auto`` – **Tự động hoàn toàn** (chỉ Giám đốc bật, form hiện cảnh báo).
* Mỗi câu trả lời lưu quyết định (``decision``: tự gửi theo kịch bản / luồng đặt lịch / mẫu an toàn / chờ duyệt vì
  không khớp, tin cậy thấp, chuyên môn / khiếu nại / ca khẩn), kịch bản, độ tin cậy, lý do – hiện trên Mô phỏng Zalo
  ("Khớp kịch bản …" hoặc "Chuyển nhân viên – vì sao") và Hộp thư.
* **Huấn luyện**: câu trả lời nhân viên đã duyệt / đã sửa / tự viết trong Hộp thư → **"Đề xuất thành kịch bản"** (một
  chạm, tạo kịch bản nháp có câu hỏi mẫu + câu trả lời, giao việc cho Giám đốc) hoặc **"+ Ví dụ"** (``dmag.ai.reply.example``
  – hỏi / đáp few-shot gắn kịch bản, Giám đốc duyệt mới dùng cho nhận diện). Đề xuất của lễ tân được tạo bằng quyền hệ
  thống ở trạng thái nháp (người đề xuất ghi lại).
* **Thống kê** (đầu Hộp thư, ``get_script_stats``): % tự trả lời, % chuyển nhân viên (30 ngày), số kịch bản đã duyệt /
  chờ duyệt, các câu hỏi chưa có kịch bản nhiều nhất kèm nút "Thành kịch bản".

AI-08 – Dự báo không đến
------------------------
Đặc trưng: số ngày đặt trước, tỷ lệ không đến trước đó (chỉ lịch sử TRƯỚC giờ hẹn), khách mới, cuối tuần, giờ tối /
sáng sớm, đã xác nhận (nhật ký trạng thái / ZNS đã tới / cờ ``dmag_was_confirmed``), ca nhẹ, kênh đặt online.
Hồi quy logistic thuần Python (chuẩn hóa z-score, L2, gradient descent – xác định); < 40 lượt hoặc < 5 lần không đến →
trọng số kinh nghiệm. Cron hằng đêm huấn luyện + chấm điểm 14 ngày tới; chấm lại khi tạo / đổi giờ / xác nhận lịch.
Thẻ bảng điều phối: "Nguy cơ không đến 72%" + gợi ý gọi xác nhận; rê chuột xem yếu tố và cách tính.

Điểm móc vào module khác
========================
* ``dmag.dental.visit``: ``_workspace_card`` (+ ``noshow``, ``ai_booked``), ``create`` / ``write`` (chấm điểm),
  ``_dmag_journey_event('done')`` (tạo câu hỏi theo dõi AI-18).
* ``dmag.workspace.quick_create_patient`` (+ ``street`` từ CCCD), ``get_slot_suggestions`` (mới).
* ``dmag.nps.response.submit`` (AI-09), ``dmag.zns.webhook.event._dmag_process`` (AI-07).
* OWL: ``patch`` ``FrontDesk``, ``BookingDialog``, ``NewPatientDialog`` + kế thừa template (``t-inherit``) – không sửa
  file của ``dmag_clinic_workspace``. ``NewPatientDialog.save`` được ghi đè để gửi thêm địa chỉ.
* Cổng: kế thừa controller ``DmagPatientPortal.dmag_home`` và template ``portal_dental_shell`` / ``portal_dental_home``.

Thư viện bên thứ ba
===================
``static/lib/jsqr`` – jsQR 1.4.0 (Apache-2.0), chỉ tải khi trình duyệt không có ``BarcodeDetector``.

Kiểm thử
========
``tests/test_reply_scripts.py``: 12 kịch bản mẫu; khớp kịch bản → tự gửi mẫu điền giá / giờ làm việc thật (mô phỏng và
Zalo); không khớp / chuyên môn → nháp chờ duyệt + tin báo đã nhận một lần; ca khẩn / khiếu nại / mẫu an toàn đau sau nhổ
răng; kịch bản đặt lịch tạo lịch nháp; kịch bản mở lại không được dùng; quyền (lễ tân không tạo, Quản lý không duyệt,
Giám đốc duyệt, đã duyệt bị khóa, ô dữ liệu cần công cụ); "Tự động hoàn toàn" chỉ Giám đốc; đề xuất từ hộp thư + ví dụ
few-shot + thống kê; Claude (client giả): enum ``script_id`` chặt, diễn đạt lại giữ số liệu, lệch số → dùng mẫu, ``none``
→ nháp chỉ công cụ đọc, cờ khẩn → mẫu an toàn.

Cần xác minh
============
* Payload webhook Zalo OA ``user_send_text`` (``sender.id``, ``message.text``), API gửi tin tư vấn
  ``POST https://openapi.zalo.me/v3.0/oa/message/cs`` và khung thời gian được phép trả lời; chữ ký webhook.
* Định dạng QR CCCD các đợt cấp mới (có thêm trường?), thẻ căn cước 2024.
* Quy định gửi tin chủ động: tin chăm sóc AI-12 chỉ gửi trong hội thoại khách đã nhắn OA; ngoài khung → ZNS mẫu đã duyệt.
