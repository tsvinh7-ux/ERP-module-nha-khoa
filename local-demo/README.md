# DMAG Dental ERP – chạy demo riêng trên máy (localhost)

Bản demo chạy độc lập bằng Docker: Odoo 17 Community + PostgreSQL, **không liên quan tới Bizapps**.
Lần đầu khởi động, hệ thống tự làm các việc sau:
- tạo cơ sở dữ liệu `dmag_demo`;
- cài toàn bộ module nha khoa;
- sinh dữ liệu mẫu: khoảng 40 bệnh nhân, 60 ngày lịch sử khám, lịch hôm nay, chính sách và mục tiêu mẫu;
- giả lập mọi tích hợp (SePay, MySign, Zalo, Đơn thuốc quốc gia);
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

Mở **http://localhost:8069**. Lần đầu mất **3–5 phút**; xem tiến trình bằng `docker compose logs -f odoo`.
Muốn dùng cổng khác: `DMAG_PORT=8080 ./start.sh`.

## Tài khoản (mật khẩu `demo`)

| Đăng nhập | Vai trò | Nên thử |
|---|---|---|
| `giamdoc.demo` | Giám đốc | **Điều hành mục tiêu** (mục tiêu kinh doanh, OKR, KPI); duyệt lương 3P; sửa chứng từ đã chốt |
| `quanly.demo` | Quản lý | Điều hành mục tiêu, labo, kho, pháp chế |
| `letan.demo` | Lễ tân | Bảng điều phối: đặt lịch, check-in, thu tiền QR → **"Giả lập khách chuyển khoản"** |
| `tuvan.demo` | Tư vấn | Chế độ tư vấn 2 phương án, chốt kế hoạch |
| `bacsi.demo`, `bacsi2.demo` | Bác sĩ | Sơ đồ răng, bệnh án 16/BV1, kê đơn thuốc, ký bệnh án |
| `phuta.demo` | Phụ tá | Thủ thuật, vật tư |
| `benhnhan.demo` | Bệnh nhân | http://localhost:8069/my/dental |
| `admin` (mật khẩu `admin`) | Quản trị hệ thống | Cài đặt kỹ thuật |

## Cập nhật khi có bản mới

Bản demo đọc module trực tiếp từ thư mục `../addons`. Lấy code mới (`git pull`) rồi chạy `./reset.sh`
(hoặc `reset.bat`). Lệnh này tạo lại CSDL với dữ liệu mẫu theo ngày hôm nay.

## OKR Scale (tùy chọn)

Chép các module OKR Scale vào thư mục `okr/` rồi chạy `reset`. Khi đó phần OKR tự đo (`dmag_okr_dental`) được cài kèm.
