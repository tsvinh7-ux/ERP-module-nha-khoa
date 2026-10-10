# CĂN CỨ PHÁP LÝ ÁP DỤNG TRONG DMAG DENTAL ERP

> Tổng hợp ngày 10/10/2026 từ văn bản gốc trên Drive DMAG (Luật KCB 15/2023, TT 32/2023, TT 13/2025, TT 52/2017, TT 04/2022, TT 27/2021) và kết quả tra cứu web (đánh dấu **[WEB]**). Mục **[CẦN XÁC MINH]** phải đối chiếu văn bản gốc trước khi vận hành thật.

## 1. Hồ sơ bệnh án (Luật KCB 2023, TT 32/2023, TT 13/2025)

| Yêu cầu | Căn cứ | Cách ERP đáp ứng |
|---|---|---|
| Hồ sơ gồm thông tin hành chính, tiền sử, bệnh sử, kết quả khám, cận lâm sàng, thăm dò chức năng, chẩn đoán, điều trị, chăm sóc | Luật KCB Đ2 k17; TT32 Đ52 k2a | Mẫu bệnh án ngoại trú RHM đầy đủ các mục, lập theo lượt khám |
| Mỗi thông tin phải rõ **thời gian và người ghi** | TT32 Đ52 k2d | Ghi vết (tracking) mọi trường lâm sàng; ghi nhận sơ đồ răng có người ghi + thời điểm |
| **Cấm tẩy xóa, sửa chữa làm sai lệch** hồ sơ | Luật KCB Đ7 k10 | Ký → khóa; chỉ Giám đốc mở bổ sung, có ghi vết; không xóa cứng |
| Tài liệu giao người bệnh **không viết tắt** | TT32 Đ52 k2c | Bản in cho bệnh nhân dùng tên đầy đủ (không ký hiệu) |
| Bệnh án điện tử phải đủ thông tin Chương X TT32, **gắn số định danh cá nhân** | TT13/2025 Đ1 | Trường CCCD/số định danh bắt buộc khi ký bệnh án |
| Ký/xác nhận điện tử: chữ ký điện tử hợp pháp / sinh trắc / xác nhận điện tử khác | TT13/2025 Đ3 | Chữ ký số Viettel MySign cho bác sĩ; bệnh nhân ký tablet / OTP |
| Lưu trữ dự phòng, phục hồi, truy xuất | TT13/2025 Đ2 | Sao lưu CSDL (hạ tầng) + xuất bệnh án PDF đã ký |
| Cơ sở ban hành **quy chế** hồ sơ bệnh án điện tử | TT13/2025 Đ6 k3b | Mẫu quy chế trong tài liệu triển khai (việc của phòng khám) |
| Hạn triển khai cho phòng khám ngoại trú: **31/12/2026** | TT13/2025 Đ4 k2b | — |
| Người bệnh được xem, sao chụp, nhận **bản tóm tắt** (yêu cầu bằng văn bản) | Luật KCB Đ12, Đ69 k4 | Quy trình "Yêu cầu sao chụp / tóm tắt hồ sơ" + nhật ký cung cấp |
| Giữ bí mật hồ sơ | Luật KCB Đ10 k2, Đ69 k2, k5 | Phân quyền theo vai trò, nhật ký truy cập hồ sơ |
| Thời hạn lưu trữ: theo TT 33/2025/TT-BYT (ngoại trú thường 10 năm theo TT 53/2017 cũ) | **[CẦN XÁC MINH TT 33/2025]** | Cấu hình số năm lưu trữ, chặn xóa trước hạn |
| Mẫu **Bệnh án ngoại trú Răng Hàm Mặt – 16/BV1**, Phụ lục XXVIII TT32 | **[WEB]** | Báo cáo QWeb theo bố cục họ mẫu BV1 + sơ đồ răng FDI |

## 2. Đơn thuốc (TT 26/2025/TT-BYT – hiệu lực 01/07/2025, thay TT 52/2017, 18/2018, 04/2022, 27/2021) **[WEB]**

- **Kê đơn điện tử bắt buộc**, liên thông Hệ thống đơn thuốc quốc gia: phòng khám **từ 01/01/2026** (đã quá hạn).
- Nội dung: mã đơn thuốc; tên cơ sở, địa chỉ, điện thoại; họ tên, ngày sinh, giới, **số định danh/CCCD**, nơi cư trú, số thẻ BHYT (nếu có); trẻ < 72 tháng: số tháng tuổi, cân nặng, họ tên người đưa trẻ; chẩn đoán (ICD-10); thuốc: 1 hoạt chất ghi **tên chung (INN) + hàm lượng** (có thể kèm tên thương mại trong ngoặc), nhiều hoạt chất ghi tên thương mại; số lượng, liều, đường dùng, số ngày dùng; lời dặn; ngày kê; bác sĩ ký, ghi rõ họ tên (đơn điện tử: chữ ký số).
- Tối đa **30 ngày**/thuốc (252 bệnh Phụ lục VII: 90 ngày). Số lượng < 10 viết thêm số 0 phía trước.
- **Không sửa đơn**: kê đơn mới thay thế.
- Đơn "N" (gây nghiện), "H" (hướng thần/tiền chất) có mẫu riêng – phòng khám nha khoa thông thường không kê; ERP chặn kê thuốc N/H nếu chưa cấu hình.
- Luật KCB Đ63 k2: không kê thực phẩm chức năng trong đơn.

## 3. Liên thông đơn thuốc quốc gia (QĐ 808/QĐ-BYT 2022, QĐ 228/QĐ-QLD 2023) **[WEB]**

- **Mã đơn thuốc 14 ký tự** `xxxxxyyyyyyy-z`: 5 ký tự mã cơ sở KCB + 7 ký tự ngẫu nhiên [0-9a-z] duy nhất trong cơ sở + `-` + loại đơn (`c` thường, `n` gây nghiện, `h` hướng thần, `y` YHCT).
- Đăng nhập cơ sở / bác sĩ (mã liên thông do Sở Y tế cấp) → token (7 ngày) → gửi đơn `gui-don-thuoc` ngay sau khi khám; gửi mã đơn cho người bệnh qua phương tiện điện tử.
- **[CẦN XÁC MINH]** tài liệu API bản mới nhất trên donthuocquocgia.vn trước khi bật kết nối thật.

## 4. Thuế GTGT (Luật 48/2024/QH15, hiệu lực 01/07/2025; NĐ 181/2025)

- Dịch vụ y tế (khám bệnh, chữa bệnh, phòng bệnh…) **không chịu thuế GTGT** (Điều 5) → hóa đơn ghi **KCT**.
- Dịch vụ **thẩm mỹ thuần túy** (không nhằm điều trị) và **hàng hóa bán lẻ** chịu thuế suất thông thường.
- Phải hạch toán tách doanh thu chịu thuế / không chịu thuế. **[CẦN XÁC MINH]** khoản cụ thể của Điều 5 và sửa đổi tại NĐ 144/2026.

## 5. Khác

- Phạm vi hành nghề, giấy phép 5 năm, số định danh trên giấy phép: Luật KCB Đ26, Đ27, Đ39; TT32 Đ11 k4, Phụ lục VIII.
- Liên thông dữ liệu lên Hệ thống thông tin quản lý KCB: Luật KCB Đ112; Sổ sức khỏe điện tử VNeID – QĐ 1551/QĐ-BYT ngày 31/5/2026 **[WEB]**.
- Xử phạt: NĐ 90/2026/NĐ-CP (có trên Drive) **[CẦN ĐỌC]**.

## 6. Tài liệu cần tải bản gốc (môi trường phát triển bị chặn các domain .vn)

1. TT 26/2025/TT-BYT kèm phụ lục mẫu đơn.
2. Phụ lục XXVIII TT 32/2023 – mẫu 16/BV1.
3. TT 33/2025/TT-BYT – thời hạn lưu trữ.
4. Hướng dẫn kết nối API donthuocquocgia.vn bản mới nhất.
5. Tài liệu API Viettel MySign, SePay, Zalo ZNS (theo hợp đồng dịch vụ).
