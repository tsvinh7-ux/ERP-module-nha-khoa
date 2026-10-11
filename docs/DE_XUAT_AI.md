# ĐỀ XUẤT NHÚNG AI VÀO DMAG DENTAL ERP (trên nền Odoo 17)

> Ngày 11/10/2026 · Bản để phê duyệt. Mỗi tính năng có **mã (AI-xx)**: anh/chị đánh dấu Duyệt / Hoãn / Bỏ.
> Nguyên tắc chung: **AI chỉ gợi ý, con người quyết định và ký**. AI không tự chẩn đoán, không tự kê đơn, không tự gửi gì cho khách khi chưa qua mẫu / người duyệt.

## 0. Ba nguồn AI và cách chọn

| Ký hiệu | Nguồn | Chạy ở đâu | Trả phí | Dữ liệu đi đâu | Dùng cho |
|---|---|---|---|---|---|
| **[LOCAL]** | Mô hình nguồn mở tự chạy: Whisper / PhoWhisper (VinAI) cho giọng nói; Qwen, Llama, SeaLLM… qua Ollama cho văn bản; scikit-learn cho dự báo | Máy chủ của phòng khám, hoặc 1 máy GPU riêng (RTX 4090 24 GB, khoảng 60–80 triệu đồng) | Không theo lượt, chỉ chi phí phần cứng + điện + vận hành | **Không ra khỏi phòng khám** | Giọng nói → chữ, ẩn danh dữ liệu, phân loại, dự báo số liệu |
| **[API-VN]** | Nhà cung cấp trong nước: FPT.AI, Viettel AI, VNPT (nhận dạng giọng nói, OCR, eKYC) | Hạ tầng tại Việt Nam | Theo lượt / phút audio | Ở Việt Nam, theo hợp đồng | Giọng nói tiếng Việt, đọc giấy tờ (khi không tự chạy) |
| **[API-LLM]** | Mô hình ngôn ngữ lớn qua API, khuyến nghị **Claude (Anthropic)** | Đám mây nước ngoài | **Theo token** (bảng mục 4) | Ra nước ngoài → **chỉ gửi văn bản đã ẩn danh**; ký thỏa thuận không lưu dữ liệu (ZDR) nếu được duyệt | Suy luận, tóm tắt, soạn thảo, hội thoại, hỏi đáp số liệu |

**Khuyến nghị: mô hình lai.** Dữ liệu thô nhạy cảm (ghi âm, CCCD, họ tên, số điện thoại) xử lý **LOCAL** hoặc **API-VN**. Phần cần trí tuệ cao chỉ nhận **văn bản đã ẩn danh** và gọi **API-LLM**. Mỗi tính năng có công tắc chọn nguồn, nên đổi nhà cung cấp mà không phải sửa nghiệp vụ.

Odoo 17 Community **không có sẵn AI** (ứng dụng AI của Odoo chỉ có ở bản 18/19 Enterprise). Vì vậy toàn bộ phần dưới đây là module riêng của DMAG chạy trên Odoo 17, dùng chung khung `dmag_ai_core` (mục AI-00).

## 1. Danh sách tính năng

### Nền tảng (bắt buộc nếu duyệt bất kỳ tính năng nào)

| Mã | Tính năng | Nguồn | Ghi chú |
|---|---|---|---|
| **AI-00** | **`dmag_ai_core`**: <br>– cổng gọi AI chung (Claude API / Ollama local / FPT-Viettel), bật/tắt và chọn nguồn theo từng tính năng; <br>– **ẩn danh hóa** trước khi gửi ra ngoài: thay họ tên, CCCD, SĐT, địa chỉ bằng mã, rồi ghép lại khi nhận kết quả; <br>– nhật ký từng lần gọi: ai gọi, tính năng nào, số token, chi phí; <br>– **trần chi phí tháng**, quyền theo vai trò, ghi nhận đồng ý của bệnh nhân; <br>– thư viện câu lệnh tiếng Việt và bộ kiểm thử chất lượng. | Odoo | Không có khung này thì không nên bật AI cho dữ liệu y tế |

### A. Bác sĩ – bớt giấy tờ, thêm thời gian cho bệnh nhân

| Mã | Tính năng | Nguồn | Lợi ích | Ưu tiên |
|---|---|---|---|---|
| **AI-01** | **Ghi bệnh án bằng giọng nói**: bác sĩ / phụ tá nói trong lúc khám, AI chép thành chữ rồi điền đúng các mục mẫu 16/BV1 (lý do khám, khám ngoài mặt / trong miệng, chẩn đoán…). Bác sĩ xem, sửa, rồi mới ký. | Giọng nói: **LOCAL** (PhoWhisper) hoặc **API-VN** (FPT.AI / Viettel AI) <br>Điền mẫu: **API-LLM** trên văn bản đã ẩn danh | Giảm 5–8 phút gõ / lượt khám | ★★★ |
| **AI-02** | **Kiểm tra bệnh án trước khi ký**: thiếu mục nào, chẩn đoán ICD-10 có khớp mô tả không, mâu thuẫn giữa sơ đồ răng và bệnh án. Gợi ý mã ICD-10. | Quy tắc **LOCAL** + **API-LLM** để gợi ý | Hồ sơ đủ chuẩn thanh tra, giảm trả hồ sơ | ★★★ |
| **AI-03** | **An toàn đơn thuốc**: cảnh báo dị ứng, tương tác thuốc, liều cho trẻ em / phụ nữ có thai / người dùng thuốc chống đông, vượt 30 ngày. **Phần chặn là quy tắc cố định**; AI chỉ giải thích dễ hiểu. | **LOCAL** (cơ sở dữ liệu quy tắc) + **API-LLM** (giải thích) | An toàn người bệnh, đúng TT 26/2025 | ★★★ |
| **AI-04** | **Tóm tắt hồ sơ 30 giây** trước khi khám: tiền sử, dị ứng, lần khám gần nhất, kế hoạch đang dở, công nợ, ghi chú chăm sóc. | **API-LLM** (ẩn danh) | Bác sĩ nắm bệnh nhân ngay | ★★ |
| **AI-05** | **Soạn kế hoạch điều trị nhiều phương án** từ sơ đồ răng: gợi ý thứ tự điều trị, dịch vụ, số buổi, kèm **bản giải thích dễ hiểu cho khách** (không thuật ngữ). Bác sĩ chỉnh rồi duyệt. | **API-LLM** | Tư vấn nhanh và thống nhất giữa các bác sĩ | ★★ |
| **AI-06** | **Hỗ trợ đọc phim X-quang / CBCT**: khoanh vùng nghi sâu răng, tiêu xương, tổn thương chóp. | Nhà cung cấp chuyên ngành **đã được cấp phép** (Diagnocat, Overjet, Pearl… qua API), hoặc **LOCAL** khi có mô hình được cấp phép | Phát hiện sớm, hình minh họa thuyết phục khách | ★ (giai đoạn 3) – **vướng pháp lý**, xem mục 3 |

### B. Lễ tân, tư vấn, CSKH – nhanh hơn, không bỏ sót khách

| Mã | Tính năng | Nguồn | Lợi ích | Ưu tiên |
|---|---|---|---|---|
| **AI-07** | **Trợ lý Zalo OA 24/7**: trả lời giá, giờ mở cửa, chuẩn bị trước khi khám; **xem giờ trống và đặt lịch thẳng vào Odoo**; nhận biết ca khẩn hoặc khách bực để chuyển ngay cho người. **Không tư vấn chẩn đoán.** | **API-LLM** (gọi công cụ đặt lịch của Odoo) | Không mất khách ngoài giờ; lễ tân bớt trả lời lặp lại | ★★★ |
| **AI-08** | **Dự báo khách không đến** (no-show), học trên lịch sử của chính phòng khám: đánh dấu lịch hẹn rủi ro cao để gọi xác nhận hoặc xếp bù. | **LOCAL** (học máy trên dữ liệu Odoo, không cần LLM) | Tăng công suất ghế, nhất là buổi chiều | ★★ |
| **AI-09** | **Đọc phản hồi và khiếu nại**: phân loại NPS / bình luận / tin nhắn, mức độ nghiêm trọng, gợi ý cách xử lý; cảnh báo khách có nguy cơ rời bỏ. | **API-LLM** hoặc **LOCAL** (phân loại đơn giản) | Xử lý khiếu nại trong 24 giờ | ★★ |
| **AI-10** | **Nhập bệnh nhân từ CCCD**: quét **mã QR trên CCCD gắn chip** bằng camera hoặc máy quét, tự điền họ tên, ngày sinh, giới tính, số định danh, địa chỉ. | **LOCAL**, không cần AI vì đọc QR chính thức; OCR **API-VN** cho giấy tờ cũ | Đăng ký trong 10 giây, đúng số định danh mà TT 13/2025 yêu cầu | ★★★ (rẻ, làm ngay) |
| **AI-11** | **Gợi ý xếp lịch thông minh**: đề xuất khung giờ lấp chỗ trống, cân bác sĩ chính / bác sĩ phụ, ưu tiên buổi chiều. | **LOCAL** (thuật toán tối ưu) | Công suất ghế, bám mục tiêu | ★ |
| **AI-12** | **Soạn nội dung chăm sóc cá nhân hóa**: kịch bản gọi hỏi thăm sau 24 giờ, tin OA theo từng ca điều trị. Tin ZNS vẫn phải dùng mẫu đã đăng ký. | **API-LLM** | Khách thấy được quan tâm thật | ★ |

### C. Quản lý / Giám đốc – bám mục tiêu

| Mã | Tính năng | Nguồn | Lợi ích | Ưu tiên |
|---|---|---|---|---|
| **AI-13** | **Hỏi đáp số liệu bằng tiếng Việt** ngay trên Bảng điều hành mục tiêu, ví dụ "Vì sao doanh thu tháng này chậm?", "Bác sĩ nào chốt kế hoạch thấp nhất quý này?". AI **chỉ đọc** qua bộ chỉ số có sẵn, trả lời kèm số liệu và đường dẫn tới chứng từ. | **API-LLM** (gọi công cụ, chỉ đọc) | Ra quyết định nhanh, không cần biết lập báo cáo | ★★★ |
| **AI-14** | **Bản tin điều hành hằng tuần**: chỉ tiêu đang lệch, nguyên nhân có thể, 3 việc nên làm tuần tới, gửi Giám đốc mỗi sáng thứ Hai. | **API-LLM** (chạy hàng loạt, giảm 50% phí) | Họp giao ban có sẵn nội dung | ★★ |
| **AI-15** | **Phát hiện bất thường**: giảm giá, hoa hồng, sửa hoặc hủy chứng từ, công nợ hay tồn kho bất thường. | **LOCAL** (thống kê + quy tắc) | Chống thất thoát, gian lận | ★★ |
| **AI-16** | **Dự báo doanh thu và nhu cầu vật tư** theo mùa và lịch hẹn. | **LOCAL** (học máy) | Đặt mục tiêu sát thực tế, không thiếu vật tư | ★ |

### D. Khách hàng – trải nghiệm xuất sắc

| Mã | Tính năng | Nguồn | Lợi ích | Ưu tiên |
|---|---|---|---|---|
| **AI-17** | **Trợ lý trên cổng / app bệnh nhân**: giải thích kế hoạch điều trị và đơn thuốc bằng lời dễ hiểu, hướng dẫn chăm sóc sau thủ thuật, nhắc uống thuốc. | **API-LLM** | Khách hiểu và tin, tăng tỷ lệ chốt | ★★ |
| **AI-18** | **Theo dõi sau điều trị**: hỏi mức đau, chảy máu, sưng sau 24 / 72 giờ qua Zalo hoặc app. Có dấu hiệu bất thường thì **báo ngay bác sĩ phụ trách**. | Quy tắc **LOCAL** + **API-LLM** đọc câu trả lời tự do | An toàn, khách cảm thấy được chăm sóc | ★★ |
| **AI-19** | **Mô phỏng nụ cười** (thẩm mỹ, chỉnh nha) từ ảnh chụp. | Nhà cung cấp chuyên ngành (API) | Bán gói thẩm mỹ, niềng | ★ (giai đoạn 3) |

## 2. Lộ trình đề xuất (thử từng giai đoạn như cách đang làm)

| Giai đoạn | Tính năng | Vì sao |
|---|---|---|
| **GĐ1 – nền + thắng nhanh** (4–6 tuần) | AI-00, **AI-10** (CCCD), **AI-02**, **AI-03**, **AI-13** | Chi phí thấp, rủi ro thấp, đúng luật ngay, Giám đốc thấy giá trị liền |
| **GĐ2 – bác sĩ & khách** | **AI-01** (ghi bệnh án bằng giọng nói), **AI-07** (Zalo OA), AI-04, AI-08, AI-09, AI-18 | Lợi ích lớn nhất về thời gian và trải nghiệm; cần chạy thí điểm với 1–2 bác sĩ |
| **GĐ3 – mở rộng** | AI-05, AI-11, AI-12, AI-14…AI-17, AI-06, AI-19 | Khi đã có dữ liệu thật và quy trình ổn |

## 3. Pháp lý & an toàn (bắt buộc đọc trước khi duyệt)

1. **Dữ liệu sức khỏe là dữ liệu cá nhân nhạy cảm** (Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15, hiệu lực 01/01/2026; NĐ 356/2025/NĐ-CP thay NĐ 13/2023 – **[CẦN XÁC MINH]**, xem `NGHIEN_CUU_AI.md`):
   - phải có **đồng ý riêng** của bệnh nhân cho việc xử lý bằng AI (đã có cơ chế ghi nhận đồng ý, sẽ thêm mục "AI");
   - gửi dữ liệu **ra nước ngoài** cần hồ sơ đánh giá tác động chuyển dữ liệu xuyên biên giới → vì vậy thiết kế **ẩn danh trước khi gửi**, giữ dữ liệu định danh ở trong nước.
2. **AI đọc phim / chẩn đoán có thể là trang thiết bị y tế** (NĐ 98/2021, sửa đổi bởi NĐ 07/2023) **[CẦN XÁC MINH]**; Luật Trí tuệ nhân tạo 134/2025/QH15 (hiệu lực 01/3/2026) yêu cầu quản lý theo mức rủi ro và gắn nhãn nội dung do AI tạo **[CẦN XÁC MINH]** → chỉ dùng sản phẩm đã có số lưu hành tại Việt Nam, hoặc chỉ ở mức "khoanh vùng gợi ý, bác sĩ quyết định".
3. **Trách nhiệm chuyên môn thuộc bác sĩ** (Luật KCB 2023):
   - mọi nội dung AI soạn đều ở trạng thái **nháp**, phải có người duyệt mới vào hồ sơ;
   - bệnh án ghi rõ "có hỗ trợ AI" và ai đã duyệt;
   - nhật ký lưu lại lần gọi AI để truy vết.
4. Không để AI tự gửi tin cho khách ngoài các kịch bản và mẫu đã duyệt. Trợ lý Zalo **không chẩn đoán, không báo giá ngoài bảng giá**, và chuyển người khi khách khiếu nại hoặc có ca khẩn.

## 4. Chi phí ước tính (API-LLM = Claude, giá công bố 10/2026, tỷ giá tạm 26.000 đ/USD)

**Giá theo 1 triệu token:**

| Mô hình | Đầu vào | Đầu ra | Ghi chú |
|---|---|---|---|
| **Claude Opus 5.5** (mạnh nhất phổ thông, **mặc định đề xuất**) | 4 USD | 20 USD | Lập luận y khoa, kế hoạch điều trị, hỏi đáp số liệu |
| Claude Sonnet 5.5 | 2 USD | 10 USD | Cân bằng, có thể dùng cho hội thoại Zalo |
| Claude Haiku 5.5 | 0,10 USD | 0,50 USD | Rất rẻ, cho phân loại / tóm tắt ngắn |

Có thêm: **bộ nhớ đệm** (phần lặp lại tính 0,20 USD / 1 triệu token với Opus / Sonnet) và **chạy hàng loạt giảm 50%** (bản tin tuần, phân loại phản hồi).

**Ước tính cho 1 phòng khám ~30 lượt/ngày (~780 lượt/tháng), chạy toàn bộ trên Opus 5.5:**

| Tính năng | Giả định | USD/tháng | ≈ VNĐ/tháng |
|---|---|---|---|
| AI-01 ghi bệnh án (phần điền mẫu) | 780 lượt × ~5.000 token vào + 1.500 ra | ~40 | ~1,0 triệu |
| AI-02 + AI-04 kiểm tra & tóm tắt | 780 × ~4.000 vào + 800 ra | ~25 | ~0,65 triệu |
| AI-07 trợ lý Zalo | ~1.000 hội thoại × 8 lượt, có bộ nhớ đệm | ~60–90 | ~1,6–2,3 triệu |
| AI-13 + AI-14 hỏi đáp & bản tin | ~300 câu hỏi + 4 bản tin | ~15 | ~0,4 triệu |
| Còn lại (AI-03, 09, 17, 18) | | ~20 | ~0,5 triệu |
| **Tổng API-LLM** | | **~160–190** | **~4–5 triệu đồng / phòng khám / tháng** |

**Các khoản khác:**
- Nhận dạng giọng nói: **LOCAL** gần như 0 đ theo lượt (cần máy GPU nếu muốn nhanh); **API-VN** tham khảo vài trăm đồng mỗi phút audio **[báo giá theo hợp đồng]**.
- Có thể hạ chi phí 2–5 lần bằng cách chuyển các tính năng đơn giản (AI-07, AI-09) sang Sonnet hoặc Haiku. Việc chuyển chỉ làm sau khi đo trên bộ kiểm thử thấy chất lượng đạt — **anh/chị quyết**.
- AI-00 có **trần chi phí tháng**: vượt trần thì tính năng tự tạm dừng và báo Giám đốc.

## 5. Cần anh/chị phê duyệt

1. Đánh dấu **Duyệt / Hoãn / Bỏ** cho từng mã AI-00 … AI-19 (hoặc duyệt theo giai đoạn GĐ1 / GĐ2 / GĐ3).
2. Chọn hướng hạ tầng:
   - (a) **Lai** – khuyến nghị: API-LLM cho suy luận, dữ liệu thô xử lý local / trong nước;
   - (b) **Toàn bộ local**: không có dữ liệu ra ngoài, nhưng chất lượng tiếng Việt và suy luận thấp hơn rõ, cần máy GPU và người vận hành;
   - (c) **Toàn bộ API**: nhanh triển khai nhất, nhưng thủ tục chuyển dữ liệu ra nước ngoài nặng hơn.
3. Có đồng ý ký thỏa thuận xử lý dữ liệu / không lưu dữ liệu (ZDR) với nhà cung cấp API-LLM không?
4. Trần chi phí AI mỗi tháng cho 1 phòng khám, ví dụ 5 triệu đồng.
5. Nhận dạng giọng nói: **đã chốt thuê** (Odoo sẽ chạy online) – demo/thí điểm dùng nhận dạng có sẵn của Chrome/Edge (0 đ); vận hành thật: FPT.AI chính, Google Chirp 3 dự phòng, sau 1 tuần so sánh (xem `NGHIEN_CUU_AI.md`).
6. Một hoặc hai bác sĩ thí điểm AI-01 (ghi bệnh án bằng giọng nói).
