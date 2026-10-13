# DMAG Dental ERP – chạy demo riêng trên máy (localhost)

Bản demo chạy độc lập bằng Docker: Odoo 17 Community + PostgreSQL, **không liên quan tới Bizapps**.
Lần đầu khởi động, hệ thống tự làm các việc sau:
- tạo cơ sở dữ liệu `dmag_demo`;
- cài toàn bộ module nha khoa;
- sinh dữ liệu mẫu: khoảng 40 bệnh nhân, 60 ngày lịch sử khám, lịch hôm nay, chính sách và mục tiêu mẫu;
- giả lập mọi tích hợp (SePay, MySign, Zalo, Đơn thuốc quốc gia);
- bật **Trợ lý AI ở chế độ Giả lập** (20 tính năng AI-00 … AI-19, chạy trên số liệu thật, không tốn phí);
- chuyển giao diện sang tiếng Việt.

## Cần có
- **Docker Desktop** (Windows / macOS) hoặc Docker Engine (Linux), đang chạy.
- Máy có khoảng 4 GB RAM trống và 3 GB ổ đĩa.

## Chạy

| | macOS / Linux | Windows |
|---|---|---|
| Khởi động | `./start.sh` | bấm đúp `start.bat` |
| Tắt (giữ dữ liệu) | `./stop.sh` | `stop.bat` |
| Làm lại từ đầu (dữ liệu mẫu mới theo hôm nay) | `./reset.sh` | `reset.bat` |

Mở **http://localhost:8069**. Lần đầu mất **5–8 phút** (tải ảnh Docker + sinh dữ liệu mẫu); xem tiến trình bằng `docker compose logs -f odoo`.
Muốn dùng cổng khác: `DMAG_PORT=8080 ./start.sh`.

## Tài khoản (mật khẩu `demo`)

| Đăng nhập | Vai trò | Nên thử |
|---|---|---|
| `giamdoc.demo` | Giám đốc | **Điều hành mục tiêu** (mục tiêu kinh doanh, OKR, KPI, hỏi AI về số liệu); **Trung tâm AI**; bản tin tuần, cảnh báo bất thường, dự báo; duyệt lương 3P |
| `quanly.demo` | Quản lý | **Lịch nghỉ luân phiên** (Xếp lịch tự động, duyệt nghỉ phép), **Dữ liệu đã nạp** của trợ lý Zalo, Điều hành mục tiêu, labo, kho, pháp chế |
| `letan.demo` | Lễ tân | Bảng điều phối: đặt lịch, check-in, thu tiền QR → **"Giả lập khách chuyển khoản"**; **Mô phỏng Zalo** (hỏi giá, giờ làm việc, đặt lịch; hỏi câu ngoài dữ liệu để thấy báo lễ tân); **Hộp thư lễ tân** (trả lời → "Nạp vào kho tri thức") |
| `tuvan.demo` | Tư vấn | Chế độ tư vấn 2 phương án, chốt kế hoạch |
| `bacsi.demo`, `bacsi2.demo`, `bacsi3.demo` | Bác sĩ | Sơ đồ răng, bệnh án 16/BV1 (đọc bằng giọng nói), kê đơn thuốc (an toàn đơn thuốc), ký bệnh án; bệnh nhân Nguyễn Thị Mai có sẵn phim mẫu |
| `phuta.demo`, `phuta2.demo` | Phụ tá | Thủ thuật, vật tư |
| `benhnhan.demo` | Bệnh nhân | http://localhost:8069/my/dental |
| `admin` (mật khẩu `admin`) | Quản trị hệ thống | Cài đặt kỹ thuật |

## Trợ lý AI: Giả lập → AI thật (Claude API)

Mở **Nha khoa › Trợ lý AI › Trung tâm AI** để xem cả 20 tính năng AI, trạng thái, số lần dùng, chi phí và nút
**"Thử ngay"**. Mặc định mọi tính năng chạy **Giả lập**: kết quả tính từ số liệu thật của bản demo nhưng không gọi AI,
không tốn phí; nhật ký vẫn ghi *chi phí nếu chạy thật*.

Ảnh Docker của bản demo được dựng từ `Dockerfile` trong thư mục này (`odoo:17.0` + thư viện Python `anthropic`), nên
chuyển sang AI thật chỉ cần dán khóa:

1. Lấy khóa API tại https://console.anthropic.com → **API Keys** → *Create Key* (dạng `sk-ant-…`).
2. Đăng nhập `giamdoc.demo` → **Nha khoa › Cấu hình › Trợ lý AI › Cài đặt AI**.
3. Dán khóa vào ô **Khóa API Claude**, chọn **Chế độ AI = Claude API (AI thật)**, đặt **Trần chi phí AI / tháng**
   (mặc định 5 triệu đồng; vượt trần → tự tạm dừng) rồi **Lưu**.
4. Thử: *Điều hành mục tiêu* → **Hỏi AI về số liệu** → "Vì sao doanh thu tháng này chậm?". Câu trả lời có nhãn
   "Claude API", số token và chi phí thật; xem chi tiết ở *Cấu hình › Trợ lý AI › Nhật ký & chi phí AI*.

Muốn quay lại giả lập: chọn lại **Giả lập** (khóa vẫn được giữ). Mô hình mặc định Claude Opus 5.5; đổi mô hình
(Sonnet / Haiku) hoặc tắt từng tính năng tại *Cấu hình › Trợ lý AI › Tính năng AI*.

> Ảnh được build tự động ở lần `start` đầu tiên (cần Internet để tải `anthropic` từ PyPI). Máy sau tường lửa công ty
> chặn chứng chỉ HTTPS: `docker compose build` với `--secret id=ca,src=<tệp CA.pem>` (xem chú thích trong `Dockerfile`).
> Kiểm tra thư viện: `docker compose exec odoo python3 -c "import anthropic; print(anthropic.__version__)"`.

## Cập nhật khi có bản mới

Bản demo đọc module trực tiếp từ thư mục `../addons`. Lấy code mới (`git pull`) rồi chạy `./reset.sh`
(hoặc `reset.bat`). Lệnh này tạo lại CSDL với dữ liệu mẫu theo ngày hôm nay.

## OKR Scale (tùy chọn)

Chép các module OKR Scale vào thư mục `okr/` rồi chạy `reset`. Khi đó phần OKR tự đo (`dmag_okr_dental`) được cài kèm.
