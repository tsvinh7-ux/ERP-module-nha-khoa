# ĐỀ XUẤT KIẾN TRÚC DENTAL ERP TRÊN ODOO 17 COMMUNITY (BIZAPPS)

> Trạng thái: **BẢN NHÁP CHỜ PHÊ DUYỆT** — chưa viết code.
> Ghi chú: tại thời điểm lập đề xuất, repository còn trống (chưa có source Odoo/Bizapps). Đề xuất dựa trên năng lực chuẩn của Odoo 17 Community; danh sách cần đối chiếu lại với bộ addons Bizapps đang dùng (xem mục 8).

---

## 1. Nguyên tắc thiết kế

1. **Không sửa core** Odoo/Bizapps — mọi thứ nằm trong addons riêng, kế thừa (`_inherit`) model sẵn có.
2. **Tái sử dụng tối đa app sẵn có** (Contacts, Calendar, Sales, Invoicing, Inventory, Purchase, HR, CRM, POS, Website…) thay vì viết lại.
3. **Tách module nhỏ, cài theo gói** — phòng khám đơn lẻ cài gói lõi; chuỗi nha khoa cài thêm gói chuỗi/marketing.
4. **Chỉ dùng tính năng Community** — các app Enterprise (Appointment, Studio, Sign, Documents, Payroll, Helpdesk, Marketing Automation, WhatsApp…) phải có phương án thay thế bằng custom hoặc OCA.
5. **Tuân thủ pháp lý Việt Nam**: hồ sơ bệnh án, đơn thuốc điện tử, hóa đơn điện tử, bảo vệ dữ liệu cá nhân (dữ liệu sức khỏe là dữ liệu nhạy cảm).

---

## 2. Danh sách module đề xuất

Tiền tố tạm đặt `dental_` (có thể đổi theo quy ước Bizapps, ví dụ `bz_dental_`).

### Nhóm A — Lõi (bắt buộc)

| # | Module | Chức năng chính | Kế thừa từ |
|---|--------|-----------------|------------|
| A1 | `dental_base` | Menu "Nha khoa", phân quyền (Lễ tân, Bác sĩ, Phụ tá, Thu ngân, Quản lý chi nhánh, Giám đốc), danh mục răng FDI (11–48, răng sữa 51–85), mặt răng (M/D/O/B/L), tình trạng răng, danh mục chẩn đoán ICD-10 nhóm K00–K14, cấu hình chi nhánh/ghế nha | `base`, `res.company` |
| A2 | `dental_patient` | Hồ sơ bệnh nhân: mã BN tự sinh, CCCD, ngày sinh, giới tính, người giám hộ (trẻ em), tiền sử bệnh toàn thân, dị ứng thuốc, thuốc đang dùng, cảnh báo (tim mạch, tiểu đường, thai kỳ…), nguồn khách, người giới thiệu, gia đình (liên kết hồ sơ) | `res.partner` |
| A3 | `dental_appointment` | Lịch hẹn theo **bác sĩ / ghế / phòng / chi nhánh**, kiểm tra trùng lịch, trạng thái (Đặt → Xác nhận → Đã đến → Đang điều trị → Hoàn tất / Hủy / Không đến), hàng chờ lễ tân (check-in), màn hình gọi bệnh nhân, nhắc lịch SMS/Zalo | `calendar.event`, `resource` |
| A4 | `dental_chart` | **Sơ đồ răng (Odontogram)** dạng widget OWL tương tác: click răng/mặt răng để ghi tình trạng & chỉ định; lịch sử theo thời gian; người lớn/trẻ em/hỗn hợp; nha chu đồ (periodontal chart) ở giai đoạn sau | OWL component |
| A5 | `dental_clinical` (EMR) | Phiếu khám, lý do đến khám, khám ngoài mặt/trong miệng, chẩn đoán, **tiến trình điều trị theo từng lần hẹn** (ghi chú SOAP), bác sĩ & phụ tá thực hiện, vật tư đã dùng, phiếu cam kết/đồng ý điều trị (ký điện tử trên tablet), khóa hồ sơ sau khi ký | model mới |
| A6 | `dental_treatment_plan` | **Kế hoạch điều trị** nhiều phương án (cơ bản/tiêu chuẩn/cao cấp), chia giai đoạn, theo răng; chuyển thành báo giá; bệnh nhân chấp thuận → tạo lịch hẹn & đơn hàng; theo dõi % hoàn thành | `sale.order`, `sale.order.line` |
| A7 | `dental_service` | Danh mục dịch vụ nha khoa (khám, cạo vôi, trám, nội nha, nhổ, implant, chỉnh nha, răng sứ, tẩy trắng…) với: thời lượng chuẩn, cần chỉ định răng hay không, **định mức vật tư (BOM)**, bảng giá theo chi nhánh/hạng thành viên, bảo hành | `product.template`, `product.pricelist` |
| A8 | `dental_billing` | Thanh toán **theo tiến độ điều trị**, đặt cọc, trả góp nhiều kỳ, công nợ bệnh nhân, hoàn tiền, nhiều phương thức (tiền mặt, CK, thẻ, QR VietQR), phiếu thu in khổ A5/K80, xuất **hóa đơn điện tử** (nối nhà cung cấp HĐĐT mà Bizapps đang tích hợp) | `account.move`, `account.payment`, `point_of_sale` (tùy chọn) |
| A9 | `dental_prescription` | Đơn thuốc theo mẫu Bộ Y tế, danh mục thuốc, liều dùng mẫu, in đơn, chuẩn bị liên thông **đơn thuốc quốc gia** (giai đoạn 2) | model mới + `product` |

### Nhóm B — Vận hành phòng khám

| # | Module | Chức năng chính | Kế thừa từ |
|---|--------|-----------------|------------|
| B1 | `dental_imaging` | Lưu ảnh trong miệng/ngoài mặt, X-quang, CBCT (file hoặc link PACS/viewer), so sánh trước–sau, gắn vào răng/lần điều trị | `ir.attachment` |
| B2 | `dental_lab` | **Phiếu gửi Labo** (răng sứ, khay chỉnh nha, hàm tháo lắp…): màu răng, vật liệu, hạn trả, trạng thái, thử sườn, chi phí labo → công nợ nhà cung cấp; cảnh báo trễ hạn | `purchase.order`, `res.partner` (labo) |
| B3 | `dental_inventory` | Trừ kho vật tư **tự động theo định mức** khi hoàn tất thủ thuật, kho theo chi nhánh/ghế, quản lý **lô – hạn dùng**, **serial implant** (truy xuất implant nào cắm cho bệnh nhân nào), cảnh báo tồn tối thiểu | `stock`, `stock.lot` |
| B4 | `dental_warranty` | **Thẻ bảo hành** implant/răng sứ/chỉnh nha: mã thẻ, thời hạn, điều kiện, lịch sử bảo hành — yếu tố cạnh tranh quan trọng tại thị trường VN | model mới |
| B5 | `dental_sterilization` (tùy chọn) | Quy trình tiệt khuẩn dụng cụ: mẻ hấp, chỉ thị, bộ dụng cụ dùng cho bệnh nhân nào | `maintenance` |
| B6 | `dental_equipment` | Thiết bị (ghế nha, máy X-quang, autoclave…): bảo trì định kỳ, hiệu chuẩn | `maintenance` |

### Nhóm C — Nhân sự & hoa hồng

| # | Module | Chức năng chính | Kế thừa từ |
|---|--------|-----------------|------------|
| C1 | `dental_staff` | Hồ sơ bác sĩ: chứng chỉ hành nghề (số, ngày cấp, phạm vi), chuyên khoa, lịch làm việc theo ca/chi nhánh, cảnh báo hết hạn chứng chỉ | `hr.employee`, `resource.calendar` |
| C2 | `dental_commission` | **Hoa hồng/thủ thuật phí** cho bác sĩ, phụ tá, tư vấn viên, telesale, người giới thiệu: theo % doanh thu / % thực thu / số tiền cố định / bậc thang; tính trên tiền đã thu; bảng kê hàng tháng xuất cho lương | model mới; nối `hr_payroll` OCA nếu dùng |
| C3 | `dental_kpi` | KPI: doanh thu/bác sĩ, tỉ lệ chốt kế hoạch điều trị, tỉ lệ quay lại, số ca/ghế/giờ | báo cáo |

### Nhóm D — Khách hàng, marketing, CSKH

| # | Module | Chức năng chính | Kế thừa từ |
|---|--------|-----------------|------------|
| D1 | `dental_crm` | Lead từ Facebook/TikTok/Zalo/Website/Hotline, phân bổ telesale, kịch bản tư vấn, chuyển lead → bệnh nhân + lịch hẹn, đo hiệu quả kênh/chiến dịch (chi phí/lead, chi phí/khách) | `crm`, `utm` |
| D2 | `dental_recall` | **Nhắc tái khám / chăm sóc sau điều trị** tự động (sau nhổ răng 1 ngày, sau implant 7 ngày, cạo vôi 6 tháng…), danh sách gọi điện CSKH, khảo sát hài lòng (NPS) | `mail.activity`, `survey` |
| D3 | `dental_loyalty` | Thẻ thành viên/hạng, gói dịch vụ trả trước, voucher, chương trình giới thiệu bạn bè | `loyalty` |
| D4 | `dental_zalo` | Tích hợp **Zalo OA / ZNS**: nhắc lịch, xác nhận lịch, gửi kết quả, chăm sóc sau điều trị (thay cho WhatsApp Enterprise) | connector mới |
| D5 | `dental_portal` | Cổng bệnh nhân: **đặt lịch online** (thay Appointment Enterprise), xem lịch hẹn, kế hoạch điều trị, hóa đơn, thanh toán online, thẻ bảo hành | `portal`, `website` |

### Nhóm E — Chuỗi & quản trị

| # | Module | Chức năng chính | Kế thừa từ |
|---|--------|-----------------|------------|
| E1 | `dental_multi_branch` | Chuỗi nhiều chi nhánh: hồ sơ bệnh nhân dùng chung, kho/doanh thu/phân quyền theo chi nhánh, chuyển bệnh nhân giữa chi nhánh, bảng giá theo chi nhánh | multi-company / `stock.warehouse` / analytic |
| E2 | `dental_insurance` | Bảo hiểm tư nhân/bảo lãnh viện phí: hợp đồng BH, hạn mức, phần BH chi trả – phần BN chi trả, hồ sơ yêu cầu bồi thường | model mới |
| E3 | `dental_dashboard` | Dashboard điều hành: doanh thu/thực thu, công nợ, lịch hẹn hôm nay, tỉ lệ lấp đầy ghế, tỉ lệ no-show, top dịch vụ, hiệu quả marketing | `spreadsheet_dashboard`, `board` |
| E4 | `dental_audit` | Nhật ký truy cập & chỉnh sửa hồ sơ bệnh án, che dữ liệu nhạy cảm theo vai trò, đồng ý xử lý dữ liệu cá nhân | `mail.tracking`, `ir.rule` |

---

## 3. Customize các app sẵn có của Odoo 17 Community

| App sẵn có | Vai trò trong Dental ERP | Hướng customize |
|---|---|---|
| **Contacts** (`res.partner`) | Bệnh nhân, labo, nhà cung cấp, công ty bảo hiểm | Thêm cờ `is_patient`, mã BN, trường y khoa, smart button (lịch hẹn, kế hoạch điều trị, công nợ, ảnh, đơn thuốc) |
| **Calendar** + **Resource** | Lịch hẹn | Thêm bác sĩ/ghế/chi nhánh/dịch vụ, chống trùng lịch, view lịch theo cột ghế/bác sĩ (OWL), trạng thái phòng khám |
| **Sales** (`sale.order`) | Báo giá & kế hoạch điều trị | Dòng đơn gắn răng/mặt răng/giai đoạn; nhiều phương án; mẫu in "Kế hoạch điều trị" thay cho báo giá |
| **Invoicing** (`account`) + l10n_vn của Bizapps | Thu tiền, công nợ, hóa đơn | Hóa đơn theo tiến độ/đặt cọc, phiếu thu, trả góp, liên kết HĐĐT; giữ nguyên hệ thống kế toán VN của Bizapps |
| **Point of Sale** (tùy chọn) | Quầy thu ngân / bán sản phẩm (bàn chải, nước súc miệng) | Nạp đơn từ kế hoạch điều trị vào POS để thu tiền nhanh |
| **Inventory** | Vật tư nha khoa, implant | Định mức vật tư theo dịch vụ, trừ kho tự động, lô/hạn dùng/serial |
| **Purchase** | Mua vật tư, đặt Labo | Loại đơn "Labo" có thông tin ca lâm sàng |
| **Employees / Attendances / Time Off** | Nhân sự | Chứng chỉ hành nghề, lịch ca theo chi nhánh/ghế |
| **CRM** | Lead marketing, telesale | Pipeline nha khoa, nguồn lead, chuyển đổi sang bệnh nhân + lịch hẹn |
| **Email Marketing / SMS / Survey** | Chăm sóc khách hàng | Mẫu nhắc lịch, khảo sát NPS sau điều trị |
| **Loyalty** (`sale_loyalty`) | Thẻ thành viên, voucher | Áp dụng cho dịch vụ nha khoa |
| **Website / Portal / Live Chat** | Đặt lịch online, cổng BN | Trang đặt lịch theo chi nhánh/bác sĩ/khung giờ trống |
| **Maintenance** | Thiết bị, tiệt khuẩn | Lịch bảo trì ghế nha, autoclave |
| **Project** (tùy chọn) | Ca chỉnh nha/implant dài hạn | Có thể dùng làm bảng theo dõi ca phức tạp |

**Phương án thay thế các app Enterprise** (không có trong Community):

| Enterprise | Thay thế |
|---|---|
| Appointment | `dental_appointment` + `dental_portal` (custom) |
| Studio | Phát triển trực tiếp trong addons |
| Sign | Ký trên tablet (widget chữ ký `signature` sẵn có) trong `dental_clinical` |
| Documents | `dental_imaging` dựa trên `ir.attachment` |
| Payroll | Xuất bảng hoa hồng / dùng OCA `payroll` hoặc giải pháp lương của Bizapps |
| WhatsApp / Marketing Automation | `dental_zalo` + `dental_recall` (cron + `mail.activity`) |
| Helpdesk | Khiếu nại/bảo hành xử lý trong `dental_warranty` + `mail.activity` |

---

## 4. Luồng nghiệp vụ chuẩn (end-to-end)

```
Lead (FB/Zalo/Web/Hotline) ──► CRM telesale ──► Đặt lịch hẹn
        │
        ▼
Lễ tân check-in ──► Hàng chờ ──► Bác sĩ khám (Phiếu khám + Sơ đồ răng + Ảnh/X-quang)
        │
        ▼
Kế hoạch điều trị (nhiều phương án) ──► Tư vấn viên chốt ──► BN đồng ý & ký
        │
        ▼
Điều trị theo từng lần hẹn ──► Trừ vật tư tự động ──► (Gửi Labo nếu cần) ──► Đơn thuốc
        │
        ▼
Thu tiền theo tiến độ / trả góp ──► Hóa đơn điện tử ──► Hoa hồng nhân viên
        │
        ▼
Thẻ bảo hành ──► Chăm sóc sau điều trị ──► Nhắc tái khám định kỳ ──► Khảo sát NPS
```

---

## 5. Phân quyền đề xuất

| Vai trò | Quyền chính |
|---|---|
| Lễ tân | Bệnh nhân (hành chính), lịch hẹn, check-in; không xem chi tiết bệnh án |
| Tư vấn viên / Telesale | Lead, lịch hẹn, kế hoạch điều trị (giá), không sửa bệnh án |
| Bác sĩ | Bệnh án, sơ đồ răng, kế hoạch điều trị, đơn thuốc, gửi labo — của bệnh nhân mình / chi nhánh mình |
| Phụ tá | Xem bệnh án, ghi vật tư sử dụng, ảnh |
| Thu ngân | Thanh toán, phiếu thu, công nợ |
| Kho | Vật tư, nhập/xuất, labo |
| Quản lý chi nhánh | Toàn bộ dữ liệu chi nhánh, báo cáo |
| Giám đốc / Chủ chuỗi | Toàn chuỗi, dashboard, cấu hình hoa hồng & giá |

---

## 6. Lộ trình triển khai đề xuất

| Giai đoạn | Phạm vi | Mục tiêu |
|---|---|---|
| **GĐ 1 – MVP vận hành** | A1–A8 (lõi), B3 cơ bản | Một phòng khám chạy được trọn vòng: hẹn → khám → kế hoạch → điều trị → thu tiền |
| **GĐ 2 – Lâm sàng nâng cao** | A9, B1, B2, B4, C1, C2 | Đơn thuốc, ảnh/X-quang, labo, bảo hành, hoa hồng |
| **GĐ 3 – Tăng trưởng** | D1–D5 | CRM, nhắc tái khám, Zalo, loyalty, đặt lịch online |
| **GĐ 4 – Chuỗi & tuân thủ** | E1–E4, B5, B6, C3 | Chuỗi chi nhánh, bảo hiểm, dashboard, audit, liên thông đơn thuốc quốc gia |

---

## 7. Cấu trúc thư mục dự kiến

```
ERP-module-nha-khoa/
├── docs/
├── addons/
│   ├── dental_base/
│   ├── dental_patient/
│   ├── dental_appointment/
│   ├── dental_chart/
│   ├── dental_clinical/
│   ├── dental_treatment_plan/
│   ├── dental_service/
│   ├── dental_billing/
│   └── ... (các module giai đoạn sau)
└── README.md
```

Mỗi module theo chuẩn Odoo 17: `__manifest__.py`, `models/`, `views/`, `security/` (`ir.model.access.csv` + record rules), `data/`, `report/` (QWeb), `static/src/` (OWL), `i18n/vi_VN.po`, `tests/`.

---

## 8. Câu hỏi cần anh/chị xác nhận trước khi code

1. **"DMAG"** là viết tắt của mô hình/tiêu chuẩn nào? (Để chuẩn hóa thuật ngữ, quy trình và báo cáo theo đúng mô hình đó.)
2. **Nền tảng Bizapps**: có thể cung cấp danh sách addons Bizapps đang cài (hoặc đẩy source vào repo) không? Đặc biệt: kế toán VN, HĐĐT (nhà cung cấp nào), lương, module đã có sẵn về y tế/phòng khám.
3. **Quy mô mục tiêu**: một phòng khám, hay chuỗi nhiều chi nhánh ngay từ đầu?
4. **Thu ngân**: dùng Invoicing thuần hay dùng POS?
5. **Hình ảnh X-quang/CBCT**: chỉ lưu file/ảnh, hay cần tích hợp phần mềm/thiết bị chụp cụ thể (PACS/DICOM)?
6. **Kênh nhắn tin**: Zalo OA/ZNS, SMS brandname nhà mạng nào?
7. **Phạm vi GĐ 1** ở mục 6 có phù hợp không, cần thêm/bớt module nào?
8. **Tiền tố module** muốn dùng (`dental_`, `bz_dental_`, hay tên thương hiệu riêng)?
