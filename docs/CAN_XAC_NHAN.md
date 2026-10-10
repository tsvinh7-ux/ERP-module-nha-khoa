# DANH SÁCH CẦN ANH/CHỊ XÁC NHẬN TRƯỚC KHI VẬN HÀNH THẬT

> Cập nhật 10/10/2026. Mọi mục dưới đây **đã có mã chạy được với dữ liệu giả lập**. Chỉ cần thông tin / quyết định thật để bật.
> Ký hiệu: 🔴 bắt buộc trước go-live · 🟡 nên có trước pilot · ⚪ có thể quyết sau.

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
| D5 ⚪ | Mục tiêu KPI trên Buồng lái (công suất ghế, đồng thuận kế hoạch…) | Chuẩn DMAG trong `get_owner_cockpit` |

## E. Hạ tầng

- E1 🔴 Cài **wkhtmltopdf 0.12.6 (bản patched qt)** trên server Bizapps để in PDF bệnh án, đơn thuốc, phiếu thu.
- E2 🔴 Sao lưu CSDL hằng ngày, lưu ngoài máy chủ (TT 13/2025 Đ2).
- E3 🟡 Thiết bị chẩn đoán hình ảnh: hãng, model, PACS/DICOM hay thư mục chia sẻ (ERP chỉ lưu liên kết, không lưu file nặng).
