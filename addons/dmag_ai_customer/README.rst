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

AI-07 – Chế độ MẶC ĐỊNH "Tự động – chỉ trả lời từ dữ liệu đã nạp" (quyết định 12/10/2026)
-------------------------------------------------------------------------------------------
Chủ phòng khám: *"muốn thay hoàn toàn nhưng có chuẩn trả lời những cái có trong database được nạp, còn ngoài mà không có
thì phải thông báo tới người phụ trách như lễ tân"*.

* **Kho tri thức trợ lý** (``dmag.ai.knowledge``, *CSKH › Trợ lý AI khách hàng › Kho tri thức trợ lý*): chủ đề, các cách
  khách hỏi, nội dung được phép trả lời, thẻ, nguồn, hiệu lực từ / đến; Quản lý soạn, **chỉ Giám đốc duyệt**, đã duyệt
  bị khóa ("Mở lại để sửa"). Bộ nạp: kịch bản đã duyệt; **dữ liệu gốc Odoo** (bảng giá + bảo hành theo dịch vụ, Lịch làm
  việc, ngày nghỉ lễ, bác sĩ & ngày trực theo Lịch nghỉ luân phiên, địa chỉ, gửi xe, thanh toán, chuẩn bị, hotline, gói
  chăm sóc) – tự duyệt vì là dữ liệu gốc, nội dung giá dựng lại lúc trả lời; **tài liệu** TXT / Markdown / PDF
  (``dmag.ai.knowledge.document``: trích văn bản, tách đoạn theo tiêu đề → nháp, Giám đốc duyệt tài liệu); **hỏi – đáp
  từ hộp thư**. Màn hình **"Dữ liệu đã nạp"** (thẻ ``dmag_ai_kb_overview``): số mục theo nguồn, lần nạp cuối, "Nạp lại dữ
  liệu", "Thử hỏi trợ lý" (kết quả tìm + kết luận có / ngoài dữ liệu), mục chờ duyệt, câu hỏi ngoài dữ liệu gần đây. Cron
  hằng ngày nạp lại; trợ lý tự nạp nếu kho cũ hơn 6 giờ.
* **Tìm kiếm**: BM25 tại chỗ, không phân biệt dấu, từ đồng nghĩa nha khoa (trồng răng ~ implant, niềng ~ chỉnh nha…);
  chỉ mục ĐÃ DUYỆT, còn hiệu lực; đủ tin cậy khi có từ hiếm khớp, độ phủ ≥ 60 %, điểm ≥ 0,32.
* **Trả lời** – giả lập: an toàn tại chỗ (ca khẩn → mẫu an toàn cố định + chuyển người; khiếu nại / muốn gặp người →
  chuyển người; không chẩn đoán) → luồng đặt lịch (công cụ thật, lịch nháp, chỉ bác sĩ đang trực) → kịch bản đã duyệt →
  kho tri thức (trích câu liên quan) → bảng giá → mẫu chào hỏi cố định → **ngoài dữ liệu**. Claude: ``dmag.ai.run`` với
  công cụ chỉ đọc ``search_knowledge``, ``search_services``, ``get_free_slots``, ``get_clinic_info``,
  ``find_patient_by_phone`` + ``book_appointment`` (nháp) + ``handoff_to_staff`` và structured output
  ``{answer, grounded, sources, needs_staff, reason}``.
* **Kiểm tra phía máy chủ** (cả hai chế độ): ``grounded`` sai / ``needs_staff`` / không có nguồn / nguồn không phải công
  cụ hay mục tri thức thực sự được gọi trong lượt / câu trả lời có **con số** (giá, giờ, ngày, số tháng…) không có
  trong nguồn → KHÔNG gửi (nháp bị chặn để nhân viên sửa, quyết định ``blocked_unverified``).
* **Ngoài dữ liệu**: khách nhận **tin giữ chỗ cố định** (một lần mỗi đợt chờ); tạo **"Câu hỏi ngoài dữ liệu"**
  (``dmag.ai.kb.gap``) giao **lễ tân đang trực hôm nay** trong danh sách *Lễ tân phụ trách trả lời khách* (theo phòng khám /
  kênh, ``dmag.ai.duty.line``; tôn trọng Lịch nghỉ luân phiên, ít câu chờ nhất; chưa khai danh sách → lễ tân đang trực
  theo lịch luân phiên → CSKH mặc định): việc cần làm + thông báo nổi (bus) + huy hiệu trên Bảng điều phối và Hộp thư.
  Quá **N phút** (mặc định 15, cấu hình) chưa trả lời → báo **Quản lý** (cron 5 phút). Hội thoại vẫn do trợ lý trả lời
  các câu khác.
* **Hộp thư**: tab **"Ngoài dữ liệu"**; thẻ câu hỏi (đã báo ai, lúc nào, quá hạn / đã báo Quản lý); nhân viên trả lời khách
  → **"Nạp vào kho tri thức"** một chạm (nháp hỏi – đáp → Giám đốc duyệt → lần sau trợ lý tự trả lời) – khép vòng.
* Mô phỏng Zalo hiện **"Trả lời từ: Bảng giá · Lịch làm việc · Kịch bản 'Giá dịch vụ'"** hoặc **"Ngoài dữ liệu đã nạp
  → đã báo lễ tân …"** cho từng lượt. Các chế độ cũ (nhân viên duyệt mọi câu / theo kịch bản / tự động hoàn toàn) vẫn
  chọn được trong cấu hình phòng khám.

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
* **Bộ 14 kịch bản chuẩn đã rà soát** (``models/reply_script_samples.py``, nạp ở trạng thái **nháp** khi cài – nút "Nạp
  kịch bản mẫu"): giá dịch vụ, giờ làm việc (mở cả tuần, Chủ nhật), địa chỉ / đỗ xe, đặt lịch, đổi / hủy lịch, chuẩn bị
  trước khám, bảo hành (``{bao_hanh}`` – số tháng theo từng dịch vụ), trả góp & thanh toán, đau sau nhổ răng (mẫu an toàn
  + chuyển bác sĩ), niềng răng (kèm bác sĩ chỉnh nha & ngày trực), tẩy trắng, khám trẻ em, **bác sĩ làm việc ngày nào**
  (``{bac_si_lam_viec}`` – Lịch nghỉ luân phiên), **gói chăm sóc theo năm** (``{goi_cham_soc}``). Không ghi cứng số liệu:
  giá / bảo hành / giờ / bác sĩ lấy từ dữ liệu thật. ``dmag_dental_demo`` duyệt bằng tài khoản Giám đốc demo. Kịch bản có
  trường **Nguồn** (bộ chuẩn / Quản lý soạn / **nhân viên đề xuất từ hộp thư**) và bộ lọc "Nhân viên đề xuất".
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
``tests/test_grounded.py``: chế độ mặc định; trả lời có nguồn (kịch bản + bảng giá, hỏi – đáp, giờ làm việc, lịch trực);
ngoài dữ liệu → tin giữ chỗ (không lặp), câu hỏi giao lễ tân ĐANG TRỰC (người kia nghỉ luân phiên), việc cần làm, thông
báo nổi, hàng "Ngoài dữ liệu"; quá 15 phút → Quản lý; nhân viên trả lời → nạp kho (Lễ tân / Quản lý không duyệt, Giám đốc
duyệt) → lần sau trợ lý tự trả lời; an toàn (ca khẩn, câu hỏi chuyên môn, đau sau nhổ răng); đặt lịch chỉ bác sĩ đang
trực; kiểm tra nguồn & con số (giá sai, không nguồn, nguồn không gọi); Claude (client giả) trả lời đúng → gửi, bịa giá →
chặn + nháp + báo lễ tân; bộ nạp, khóa, tài liệu Markdown, tìm không dấu; ô dữ liệu mới của kịch bản.
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
