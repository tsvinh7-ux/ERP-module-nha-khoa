# DANH SÁCH CẦN ANH/CHỊ XÁC NHẬN TRƯỚC KHI VẬN HÀNH THẬT

> Cập nhật 11/10/2026. Mọi mục dưới đây **đã có mã chạy được với dữ liệu giả lập**. Chỉ cần thông tin / quyết định thật để bật.
> Ký hiệu: 🔴 bắt buộc trước go-live · 🟡 nên có trước pilot · ⚪ có thể quyết sau · ✅ đã quyết.

## A. Pháp lý y tế

| # | Việc | Ai làm | Ghi chú |
|---|---|---|---|
| A1 🔴 | **Đơn thuốc đang dùng (file ĐƠN THUỐC.pdf) chưa đúng TT 26/2025**: thiếu mã đơn 14 ký tự, số định danh, ICD-10, tên chung + hàm lượng. | Phòng khám | Từ nay dùng bản in của ERP (`docs/screenshots/14_in_don_thuoc.png`). |
| A2 🔴 | Đăng ký **mã liên thông** Hệ thống đơn thuốc quốc gia (cơ sở + từng bác sĩ) với Sở Y tế. Gửi tài liệu API bản mới nhất trên donthuocquocgia.vn. | Phòng khám | ERP đang chạy bộ giả lập. Môi trường dev bị chặn domain .vn nên chưa đối chiếu được tên trường. |
| A3 🔴 | Khai báo **Mã cơ sở KCB 5 ký tự, số giấy phép hoạt động, người chịu trách nhiệm chuyên môn** tại *Thiết lập → Công ty*. | Phòng khám | Thiếu mã thì ERP chặn phát hành đơn thuốc. |
| A4 🟡 | Gửi bản gốc **Phụ lục XXVIII TT 32/2023 (mẫu 16/BV1)** và **Phụ lục I TT 26/2025** để căn bố cục in 1:1. | Anh/chị | Nội dung các mục đã đủ; chỉ còn căn bố cục. |
| A5 🟡 | Xác nhận thời hạn lưu trữ bệnh án theo **TT 33/2025** (đang đặt mặc định 10 năm, ERP chặn xóa trước hạn). | Pháp chế | |
| A6 🟡 | Hồ sơ pháp chế: dùng **TT 16/2018** (kiểm soát nhiễm khuẩn) hay **TT 18/2018**? Danh mục giấy tờ trong `dmag_dental_compliance` cần duyệt. | Pháp chế | |
| A7 ⚪ | Ban hành **Quy chế hồ sơ bệnh án điện tử** (TT 13/2025 Đ6). Hạn với phòng khám: 31/12/2026. | Giám đốc | Sẽ soạn mẫu khi anh/chị yêu cầu. |
| A8 ⚪ | Phạm vi bệnh nhân được xem trên cổng (portal / app sau này). Hiện tại: tóm tắt lượt khám (chẩn đoán, việc đã làm, lời dặn, đơn thuốc, lịch hẹn, chi phí), kế hoạch điều trị, bảo hành, điểm. Chưa hiện toàn văn bệnh án và ảnh X-quang. Chủ hộ xem được cả gia đình. Link chia sẻ qua Zalo không cần đăng nhập, hết hạn sau 30 ngày. | Giám đốc | Xác nhận có giữ link không đăng nhập không (tiện, nhưng ai có link đều xem được). |

## B. Thuế và hóa đơn

| # | Việc | Ghi chú |
|---|---|---|
| B1 🔴 | Đối chiếu thuế **"KCT – Không chịu thuế GTGT"** với module HĐĐT Viettel của Bizapps (mã thuế suất gửi sang S-Invoice). | Dịch vụ y tế gán KCT; dịch vụ **thẩm mỹ thuần túy** và hàng bán lẻ gán thuế thường (Luật 48/2024 Đ5). Kế toán duyệt danh sách dịch vụ thẩm mỹ. |
| B2 🟡 | Mức **giảm giá tối đa** nhân viên được tự áp (mặc định 10%; vượt thì cần Giám đốc). | *Thiết lập → Công ty → Nha khoa* |

## C. Tích hợp (cần hợp đồng hoặc tài khoản)

| # | Dịch vụ | Cần gửi |
|---|---|---|
| C1 🔴 | **SePay** | API key, số tài khoản, mã ngân hàng (BIN), mẫu payload webhook thật. Nếu nhiều DB cần cấu hình `dbfilter`. |
| C2 🔴 | **Viettel MySign** | Client ID/secret, profile, endpoint chính thức; chứng thư từng bác sĩ. Chọn ký PAdES trên PDF (cần wkhtmltopdf trên server) hay ký hash như hiện tại. |
| C3 🟡 | **Zalo OA/ZNS** | OA ID, app ID/secret, **đăng ký mẫu ZNS** (12 mẫu trong `dmag_dental_journey`). Bizapps đã có module Zalo không, hay ERP gọi trực tiếp? |

## D. Chính sách kinh doanh (đang dùng số demo)

| # | Việc | Mặc định demo |
|---|---|---|
| D1 🟡 | Hạng thành viên & tỷ lệ tích điểm | Thực thu 12 tháng: Bạc 5tr / Vàng 15tr / Kim cương 40tr (hoặc điểm tương tác 150/400/800); 10.000 đ thực thu = 1 điểm |
| D2 🟡 | Ngày bắt đầu bảo hành | Ngày hoàn tất thủ thuật |
| D3 🟡 | Doanh thu tính hoa hồng / tỷ lệ giá vốn: theo **thực thu** hay theo **hóa đơn**? | Hoa hồng: thực thu (đảo hóa đơn thì tự trừ) |
| D4 🟡 | Khung bậc **P (chuyên môn) / M (quản lý)** và mức lương 3P thật | Đang là khung demo, sẽ import file thật. |
| D6 🟡 | Hoa hồng: tỷ lệ từng vai trò; tính trên giá trước hay sau thuế; có trừ chi phí labo không; lễ tân hưởng theo người check-in hay người thu tiền; khoản đã trả lương mà sau đó hóa đơn bị đảo thì trừ vào kỳ sau? | Quy tắc mẫu đã nạp nhưng **đang tắt** |
| D7 🟡 | Lương 3P: cách quy đổi điểm năng lực ra hệ số P2, trần KPI (đang 120%), ngưỡng thưởng OKR (đang 70%); mã nhân viên và mã “Loại đầu vào” trên Payroll Bizapps (file xuất dùng cột `DMAG_P1`, `DMAG_P2`, `DMAG_P3`…) | Xem `addons/dmag_hr_3p/README.rst` |
| D8 ⚪ | Nhóm Quản lý phòng khám đang được quyền đọc hồ sơ nhân viên. Giữ vậy hay tách nhóm Nhân sự riêng? | |
| D9 ⚪ | Định nghĩa cho OKR tự đo: “ca niềng mới”, “bác sĩ phụ”, khung giờ buổi chiều. **Ẩn app `biz_okr`** để không bị 2 app OKR | |
| D5 ⚪ | Mục tiêu KPI trên Bảng điều hành mục tiêu (công suất ghế, đồng thuận kế hoạch…) | Giám đốc đặt trong *Cấu hình → Mục tiêu kinh doanh* (`dmag_dental_goals`); chưa đặt thì dùng chuẩn DMAG (ghi rõ "chuẩn DMAG") |

## E. Hạ tầng

- E1 🔴 Cài **wkhtmltopdf 0.12.6 (bản patched qt)** trên server Bizapps để in PDF bệnh án, đơn thuốc, phiếu thu.
- E2 🔴 Sao lưu CSDL hằng ngày, lưu ngoài máy chủ (TT 13/2025 Đ2).
- E3 🟡 Thiết bị chẩn đoán hình ảnh: hãng, model, PACS/DICOM hay thư mục chia sẻ (ERP chỉ lưu liên kết, không lưu file nặng).

## F. Quyết định của chủ phòng khám (đã chốt 11–12/10/2026)

| # | Việc | Quyết định | Đã làm trong ERP |
|---|---|---|---|
| F1 ✅ | Đơn thuốc vi phạm quy tắc an toàn (dị ứng, chống chỉ định, > 30 ngày…) | **Chặn trên mọi đường phát hành**; chỉ Giám đốc duyệt vượt, có lý do bằng văn bản và **ký bổ sung chịu trách nhiệm**. | `dmag_ai_clinical`: chặn ở `dmag.prescription.action_issue` (form đơn, Bàn làm việc bác sĩ, đơn thay thế); bác sĩ bấm "Đề nghị Giám đốc duyệt vượt"; Giám đốc "Duyệt vượt & ký chịu trách nhiệm" → ghi người / giờ / lý do / quy tắc bị vượt lên đơn + chatter, gửi ký số MySign nếu đã cấu hình (`docs/screenshots/dec_01*.png`). Bản in đơn thuốc / bệnh án không đổi. |
| F2 ✅ | Trợ lý Zalo tự trả lời | **Cho tự trả lời nhưng chỉ theo kịch bản hoặc nội dung đã được duyệt** (huấn luyện trước). | `dmag_ai_customer`: "Kịch bản trả lời đã duyệt" (Quản lý soạn, **chỉ Giám đốc duyệt**, duyệt xong bị khóa), 12 kịch bản mẫu; chế độ mặc định **Tự động theo kịch bản đã duyệt** – không khớp / tin cậy thấp / khiếu nại / câu hỏi chuyên môn → nhân viên duyệt; ca khẩn gửi mẫu an toàn cố định. Hộp thư: "Đề xuất thành kịch bản", thống kê tự trả lời / chuyển nhân viên. Còn cần: Giám đốc **đọc lại 12 kịch bản mẫu** (giá, bảo hành, trả góp…) trước khi bật thật. |
| F3 ✅ | Giờ làm việc dùng ở đâu | **Gắn với lịch làm việc thực tế của phòng khám.** | `dmag_dental_base`: *Nha khoa › Cấu hình › Phòng khám › Lịch làm việc* (ca theo thứ, ngày nghỉ lễ / đột xuất, ngày làm của từng bác sĩ) → giờ trống đặt lịch, chặn đặt ngoài giờ (Quản lý trở lên được đặt), gợi ý xếp lịch, trợ lý Zalo, ngày làm việc / nhịp mục tiêu, công suất ghế, dự báo AI-16, dữ liệu demo. Mặc định ban đầu Thứ 2 – Thứ 7 (Chủ nhật nghỉ) – **đã thay bằng F5: mở cửa 7 ngày**. Còn cần: **nhập lịch thật** và xác minh ngày lễ 2026 (đang ghi **[CẦN XÁC MINH]**). |
| F4 ✅ | Nhận dạng giọng nói (AI-01) | **Thử bằng nhận dạng của trình duyệt trước**; đề xuất nhà cung cấp tốt hơn sau khi thí điểm. | Không cần sửa mã: chọn "Trình duyệt" ở *Cấu hình → Trợ lý AI*. Sau 1–2 tuần thí điểm sẽ so sánh FPT.AI / Google Chirp 3 (xem `NGHIEN_CUU_AI.md`). |
| F5 ✅ | Chủ nhật & nghỉ luân phiên | *"Chủ nhật vẫn làm, nghỉ luân phiên nhau vào ngày trong tuần vì Chủ nhật khách hàng đi khám đông"* → **mở cửa 7 ngày**, nhân sự nghỉ luân phiên ngày thường. | `dmag_dental_base`: lịch mặc định Thứ 2 – Chủ nhật 08:00–12:00, 13:30–20:00 (thay quyết định F3 "Chủ nhật nghỉ"); **Lịch nghỉ luân phiên** – mỗi bác sĩ / phụ tá / lễ tân một ngày nghỉ thường (không nghỉ Chủ nhật trừ khi bật), nút "Xếp lịch tự động" giữ tối thiểu ≥ 2 bác sĩ, ≥ 1 lễ tân, ≥ 1 phụ tá mỗi nhóm 4 ghế (cấu hình được), xoay vòng mỗi tuần (tùy chọn), nghỉ phép / đổi ca do Quản lý duyệt; lịch tháng có ô đỏ thiếu người (*Nha khoa › Lịch nghỉ luân phiên*). Áp vào giờ trống (chỉ bác sĩ đang trực), cảnh báo đặt lịch bác sĩ đang nghỉ, Bảng điều phối ("Trực hôm nay"), AI-11, AI-07, ngày làm việc / nhịp mục tiêu (7 ngày; mục tiêu bác sĩ theo ngày trực của bác sĩ), công suất ghế, dự báo AI-16 (mùa vụ theo thứ, Chủ nhật đỉnh), dữ liệu demo (Chủ nhật ≈ 1,5–2× khách). Ảnh `docs/screenshots/rot_*.png`. Còn cần: **danh sách nhân sự thật và mức tối thiểu** từng vai trò; ngày được nghỉ có gồm Thứ 7 không. |
| F6 ✅ | Rà soát 12 kịch bản Zalo | *"Đồng ý hãy dựng"* → dựng bộ kịch bản chuẩn. | `dmag_ai_customer`: **14 kịch bản** đã rà soát (thêm "Bác sĩ làm việc ngày nào", "Gói chăm sóc theo năm"); không ghi cứng số liệu – giá, **bảo hành theo dịch vụ** (`{bao_hanh}`), giờ làm việc mở cả tuần, **ngày trực bác sĩ** (`{bac_si_lam_viec}`), gói chăm sóc, thanh toán / trả góp lấy từ dữ liệu thật; mẫu an toàn đau sau nhổ răng + chuyển bác sĩ. Demo: Giám đốc demo duyệt bằng nút thật. Còn cần: Giám đốc đọc lại câu chữ bản thật (điều kiện bảo hành, trả góp). |
| F7 ✅ | Lễ tân đề xuất kịch bản | *"Được, lên demo đi"*. | Demo: từ câu hỏi ngoài dữ liệu, lễ tân / tư vấn trả lời khách rồi **"Đề xuất thành kịch bản"** – 2 đề xuất chờ Giám đốc duyệt, 1 đề xuất (hóa đơn VAT) Giám đốc đã sửa & duyệt; danh sách kịch bản có cột **Nguồn** và bộ lọc "Nhân viên đề xuất" (`docs/screenshots/kb_05_kich_ban_de_xuat.png`). |
| F8 ✅ | Trợ lý thay hoàn toàn nhân viên | *"Muốn thay hoàn toàn nhưng chỉ trả lời những cái có trong database được nạp; ngoài dữ liệu phải thông báo người phụ trách như lễ tân"*. | Chế độ MẶC ĐỊNH mới **"Tự động – chỉ trả lời từ dữ liệu đã nạp"**: **Kho tri thức trợ lý** (Quản lý soạn, Giám đốc duyệt, đã duyệt bị khóa; nạp từ kịch bản, bảng giá + bảo hành, lịch làm việc, lịch trực, thông tin phòng khám, gói chăm sóc, tài liệu TXT / MD / PDF, hỏi – đáp từ hộp thư); màn hình **"Dữ liệu đã nạp"**; mỗi câu trả lời có **nguồn** ("Trả lời từ: Bảng giá · Lịch làm việc · Kịch bản 'Giá dịch vụ'"); máy chủ **chặn** câu trả lời không nguồn hoặc có con số không có trong nguồn; ngoài dữ liệu → tin giữ chỗ cố định + báo **lễ tân đang trực** (theo lịch luân phiên; việc cần làm, thông báo nổi, huy hiệu Bảng điều phối / Hộp thư), quá 15 phút → **Quản lý**; hàng "Câu hỏi ngoài dữ liệu" + một chạm **"Nạp vào kho tri thức"** (Giám đốc duyệt). Quy tắc an toàn giữ nguyên. Các chế độ cũ vẫn chọn được. Ảnh `kb_*.png`. Còn cần: **danh sách lễ tân phụ trách & số phút báo Quản lý** thật; nạp tài liệu chính sách thật của phòng khám. |
| F9 ✅ | Hồ sơ ký số Giám đốc | Giám đốc sẽ có hồ sơ **Viettel MySign**. | Không cần sửa mã – hướng dẫn nhập ở `addons/dmag_esign_mysign/README.rst` (mục 5a: hồ sơ nhân sự lâm sàng của Giám đốc, có thể lưu trữ, nhập Tài khoản MySign → "Lấy thông tin chứng thư"). Còn cần: Giám đốc cung cấp mã người dùng MySign sau khi Viettel-CA cấp. |

