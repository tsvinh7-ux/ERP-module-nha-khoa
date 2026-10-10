# ĐÁNH GIÁ ACS HMS (ALMIGHTY CONSULTING) THEO CHUẨN DMAG

> Phạm vi: `acs_hms_base`, `acs_hms`, `acs_hms_dental`, `acs_hms_dental_chart` (đã có trong addons hệ thống Bizapps, **chưa cài**).
> Cơ sở đánh giá: mô tả chính thức trên Odoo Apps của nhà phát triển và yêu cầu DMAG trong `DE_XUAT_DENTAL_ERP.md`.
> **Chưa đọc source code** của ACS. Phần chất lượng code và chi tiết nghiệp vụ cần kiểm tra thêm (mục 4).

## 1. ACS HMS là gì

| Hạng mục | Thông tin |
|---|---|
| Nhà phát triển | Almighty Consulting Solutions Pvt. Ltd. (Ấn Độ), bộ HMS lâu năm, có từ Odoo 13 đến 19 |
| Giấy phép | **OPL-1** (Odoo Proprietary License): giấy phép thương mại, đóng |
| Giá tham khảo (v17) | `acs_hms_dental_chart` ~436–450 USD; `acs_hms_dental` ~235 USD; cộng thêm `acs_hms` và `acs_hms_base` |
| Thiết kế gốc | Hệ thống **bệnh viện đa khoa** (nội trú, phòng mổ, xét nghiệm, nhà thuốc…). Nha khoa là **một chuyên khoa gắn thêm** |
| Chức năng nha khoa (theo mô tả) | Thủ thuật và tính tiền theo thủ thuật, lịch hẹn, quản lý răng và mặt răng, bộ câu hỏi tiền sử y khoa/nha khoa, sơ đồ răng hiển thị thủ thuật trên từng răng (răng đã nhổ thì ẩn hình), mở sơ đồ từ hồ sơ BN/lịch hẹn/điều trị |

## 2. Chấm theo tiêu chí DMAG

✅ đáp ứng · 🟡 có một phần / cần kiểm tra · ❌ không có

| # | Tiêu chí DMAG | ACS HMS | Ghi chú |
|---|---|---|---|
| 1 | Hồ sơ bệnh nhân, tiền sử, dị ứng | ✅ | Thế mạnh của HMS |
| 2 | Sơ đồ răng, mặt răng, thủ thuật theo răng | ✅ | Có sẵn. Cần xem có đủ **răng sữa / hàm hỗn hợp** và **3 lớp hiện trạng – kế hoạch – đã làm** không |
| 3 | Tính tiền theo thủ thuật | ✅ | Có |
| 4 | **Kế hoạch điều trị 2+ phương án**, bệnh nhân tự chọn, trả góp, "Bản tóm tắt bệnh án mini" | 🟡/❌ | Không thấy trong mô tả. Phải viết thêm |
| 5 | **Bệnh án điện tử chuẩn Việt Nam** (TT 13/2025: ký số, khóa hồ sơ, sửa có vết, xuất bệnh án) | ❌ | Sản phẩm quốc tế, không có chuẩn VN, không có **chữ ký số Viettel MySign** |
| 6 | Đơn thuốc mẫu Bộ Y tế (TT 52/2017, TT 04/2022), liên thông đơn thuốc quốc gia | ❌ | Có đơn thuốc nhưng theo mẫu chung, không theo mẫu VN |
| 7 | **Phạm vi hành nghề + bậc lâm sàng** chặn chỉ định/xếp lịch | ❌ | Không có |
| 8 | Lịch theo **bác sĩ + ghế**, luật xen ca khó/dễ, hàng chờ, đồng hồ chờ | 🟡 | Có lịch hẹn và màn hình gọi BN; logic ghế và luật xếp lịch phải viết thêm |
| 9 | Định mức vật tư theo dịch vụ, serial implant ↔ BN, labo | 🟡 | Có liên kết kho; định mức/labo nha khoa cần kiểm tra |
| 10 | **Giao diện riêng cho bác sĩ**, tablet, ≤ 3 chạm | ❌ | Giao diện form/list Odoo chuẩn, đúng thứ bác sĩ không quen dùng |
| 11 | Thu tiền **SePay** + HĐĐT Viettel tự động + chốt két | ❌ | Không có (chỉ liên kết Invoicing) |
| 12 | Hành trình Trước–Trong–Sau qua **Zalo ZNS** | ❌ | ACS dùng SMS/WhatsApp |
| 13 | Loyalty, ví gia đình, giới thiệu | ❌ | Không có (có gói subscription) |
| 14 | Hoa hồng/thủ thuật phí theo thực thu, gắn **3P và OKR Scale** | 🟡 | Có `acs_hms_commission` nhưng không gắn 3P/OKR |
| 15 | Tiếng Việt, thuật ngữ nha khoa VN | 🟡 | Phải dịch và chuẩn hóa lại thuật ngữ |
| 16 | Mô hình dữ liệu gọn cho phòng khám nha 1–10 ghế | 🟡 | Kéo theo nhiều khái niệm bệnh viện (khoa, phòng, nội trú…) không cần thiết |
| 17 | **Quyền sở hữu sản phẩm & đóng gói bán SaaS cho nhiều phòng khám** | ❌ | OPL-1 thường **không cho phép phân phối lại/bán lại**; mỗi phòng khám có thể phải mua bản quyền riêng. Cần ACS xác nhận bằng văn bản |
| 18 | Nâng cấp lên Odoo 18/19 do mình chủ động | 🟡 | Phụ thuộc lịch phát hành và phí của ACS |

**Tổng quan:** ACS đáp ứng tốt khoảng **3/18** tiêu chí, một phần **7/18**, không đáp ứng **8/18**. Các tiêu chí không đạt lại đúng là phần làm nên khác biệt của DMAG: tuân thủ VN, giao diện bác sĩ, tài chính minh bạch, hành trình khách hàng, con người.

## 3. Kết luận & khuyến nghị

**ACS HMS là sản phẩm có thật và dùng được, nhưng chưa đạt chuẩn DMAG và không phù hợp làm nền cho một sản phẩm DMAG bán cho nhiều phòng khám.** Lý do:

1. **Giấy phép:** dựng sản phẩm thương mại của DMAG trên module OPL-1 của bên thứ ba thì DMAG không sở hữu lõi, và có rủi ro pháp lý khi đóng gói SaaS.
2. **Lệch thiết kế:** mô hình bệnh viện quốc tế. Phần phải viết thêm cho chuẩn VN và chuẩn DMAG chiếm phần lớn khối lượng, trong khi vẫn gánh mô hình nặng của ACS.
3. **Phần ACS làm tốt** (hồ sơ BN, sơ đồ răng, thủ thuật) là phần ít rủi ro nhất để tự viết. Sơ đồ răng vẫn phải viết lại dạng OWL tablet cho giao diện bác sĩ.

👉 **Khuyến nghị: tự dựng lõi `dmag_*` (phương án 2)**, dùng ACS làm **tài liệu tham khảo nghiệp vụ** (cài trên staging để xem luồng, không phụ thuộc code). Giữ nguyên các app nền Bizapps như đề xuất.

## 4. Nếu muốn chắc chắn hơn trước khi chốt

1. Đẩy source 4 module (`acs_hms_base`, `acs_hms`, `acs_hms_dental`, `acs_hms_dental_chart`) vào một **repo private** để tôi đọc code và mô hình dữ liệu. Nên đọc trong phạm vi đánh giá nội bộ, không phân phối.
2. Hỏi ACS/Bizapps: giấy phép đang có là cho 1 database hay nhiều; có được dùng trong SaaS bán lại không.
3. Cài thử trên **staging** (không cài lên hệ thống đang chạy), để bác sĩ DMAG xem thử sơ đồ răng và luồng khám, làm tham chiếu cho thiết kế giao diện của mình.

Nguồn: [acs_hms_dental (Odoo Apps 17.0)](https://apps.odoo.com/apps/modules/17.0/acs_hms_dental) · [acs_hms_dental_chart (17.0)](https://apps.odoo.com/apps/modules/17.0/acs_hms_dental_chart) · [acs_hms_dental_chart (18.0)](https://apps.odoo.com/apps/modules/18.0/acs_hms_dental_chart) · [acs_hms_dental (19.0)](https://apps.odoo.com/apps/modules/19.0/acs_hms_dental) · [acs_hms (15.0)](https://apps.openerp.com/apps/modules/15.0/acs_hms)
