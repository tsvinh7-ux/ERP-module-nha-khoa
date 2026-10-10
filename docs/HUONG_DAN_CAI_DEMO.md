# Hướng dẫn cài bản DEMO lên Bizapps để kiểm tra

> Chỉ cài trên **cơ sở dữ liệu thử** (nhân bản DB thật hoặc tạo DB mới), không cài vào DB đang vận hành.

## 1. Chép module lên máy chủ

1. Tải gói `dmag_dental_erp_addons.zip` (hoặc lấy thư mục `addons/` của repo này).
2. Giải nén vào một thư mục nằm trong `addons_path` của Odoo Bizapps, ví dụ `/opt/odoo/custom/dmag/`.
3. Khởi động lại Odoo.

Module có mã Python nên **không** cài được bằng "Nhập mô-đun" (zip) trong giao diện. Phải chép lên máy chủ như các ứng dụng Bizapps khác.
`dmag_okr_dental` cần thêm module OKR Scale; không có thì bỏ qua module này.

## 2. Cài

1. Bật chế độ nhà phát triển → *Ứng dụng → Cập nhật danh sách ứng dụng*.
2. Tìm **"DMAG – Dữ liệu demo & giả lập tích hợp"** (`dmag_dental_demo`) → **Kích hoạt**.
   Module tự kéo theo 15 module nha khoa và sinh dữ liệu mẫu, mất **khoảng 3–5 phút**. Không đóng trình duyệt trong lúc cài.
3. Cài xong, góc trên có nhãn đỏ **CHẾ ĐỘ DEMO**.

## 3. Đăng nhập thử theo vai trò (mật khẩu `demo`)

| Tài khoản | Vai trò | Nên thử |
|---|---|---|
| `letan.demo` | Lễ tân | Bảng điều phối → Đặt lịch, Bệnh nhân mới, check-in, **Thu tiền → Chuyển khoản QR → "Giả lập khách chuyển khoản"**, in phiếu thu |
| `tuvan.demo` | Tư vấn | Chế độ tư vấn 2 phương án, chốt kế hoạch |
| `bacsi.demo`, `bacsi2.demo` | Bác sĩ | Bàn làm việc bác sĩ → sơ đồ răng, **Bệnh án 16/BV1**, **Đơn thuốc** (phát hành, in), ký bệnh án |
| `phuta.demo` | Phụ tá | Thủ thuật, vật tư |
| `quanly.demo` | Quản lý | Buồng lái, labo, kho, hồ sơ pháp chế, lương 3P (soát) |
| `giamdoc.demo` | Giám đốc | Duyệt lương 3P, mở khóa / sửa chứng từ đã chốt, giảm giá vượt mức |
| `benhnhan.demo` | Bệnh nhân | Cổng `/my/dental`: nội dung khám, đơn thuốc, kế hoạch, bảo hành, điểm |

Thử kịch bản "tạo được – không sửa": đăng nhập lễ tân hoặc bác sĩ, thử sửa một bệnh án đã ký hoặc một đơn thuốc đã phát hành. Hệ thống sẽ chặn. Đăng nhập giám đốc thì sửa được, và có ghi vết.

## 4. In ấn

Máy chủ không có wkhtmltopdf: bấm in sẽ mở **bản xem trước đúng khổ giấy** (đơn thuốc A5, bệnh án A4). Bấm nút **"In / Lưu PDF"** góc dưới bên phải rồi chọn máy in hoặc "Lưu thành PDF".

## 5. Làm mới / gỡ demo

- *Nha khoa → Cấu hình → Dữ liệu demo → "Tạo lại dữ liệu demo"*: xóa và sinh lại toàn bộ dữ liệu mẫu, ngày giờ được tính lại theo hôm nay.
- **Gỡ module `dmag_dental_demo`**: xóa sạch dữ liệu demo, tắt giả lập, khôi phục cấu hình. Các module nha khoa vẫn giữ nguyên.

## 6. Trước khi chạy thật

Làm theo [`CAN_XAC_NHAN.md`](CAN_XAC_NHAN.md): khai thông tin pháp lý, tài khoản SePay / MySign / Zalo thật, mã liên thông đơn thuốc, rồi **tắt "Chế độ demo"** trong cấu hình SePay.
